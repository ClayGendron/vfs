"""S11 experiment A: Pyodide inside the Python process, under PythonMonkey (SpiderMonkey).

The host IS the Python process. Pyodide's loader runs in "shell" mode (d8-style `read`,
`readbuffer`, `load`, `print`) fed from Python functions, and the Emscripten filesystem
VFSFS (pyodide_pm_shim.js) calls a Python function synchronously for every node_op /
stream_op, which answers with a vfs verb under the caller's Authority. No SharedArrayBuffer,
no relay thread, no sidecar.

usage: uv run --with pythonmonkey python -I pyodide_pm_host.py [--json out.json] [--packages numpy,pandas,matplotlib]
       [--mode job|version|interrupt|oom]
"""

from __future__ import annotations

import asyncio
import json
import os
import posixpath
import resource
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import pythonmonkey as pm
from sqlalchemy import event

from vfs import VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.storage.backends import InMemoryStorage

HERE = Path(__file__).resolve().parent
S10 = HERE.parent / "s10" / "pyodide_untrusted"
PYODIDE_DIR = HERE / "untrusted" / "pyodide-pm"  # S10 npm copy with the shared-memory probe guarded (see report)
PKGCACHE = S10 / "pkgcache"
READ_COLUMNS = frozenset({"content", "data", "kind", "size_bytes", "mime_type", "version", "updated_at"})
ERRNO = {
    "vfs.not_found": 44, "vfs.exists": 20, "vfs.wrong_kind": 54, "vfs.not_empty": 55,
    "vfs.permission_denied": 2, "vfs.unauthenticated": 2, "vfs.read_only": 69, "vfs.invalid": 28,
    "vfs.cross_mount": 75,
}
CSV = "region,month,sales\n" + "\n".join(
    f"{r},{m},{(i * 37) % 100 + 10}"
    for i, (r, m) in enumerate((r, m) for r in ("north", "south", "east", "west") for m in range(1, 13))
) + "\n"


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


class Files:
    """The artifact table the loader reads from: the npm dir plus the wheel cache, by basename."""

    def __init__(self) -> None:
        self.reads: Counter[str] = Counter()
        self.bytes = 0

    def resolve(self, path: str) -> Path:
        name = posixpath.basename(path)
        for d in (PYODIDE_DIR, PKGCACHE):
            p = d / name
            if p.exists():
                return p
        raise FileNotFoundError(path)

    def read_text(self, path: str) -> str:
        self.reads[posixpath.basename(path)] += 1
        return self.resolve(path).read_text()

    def read_binary(self, path: str) -> bytearray:
        self.reads[posixpath.basename(path)] += 1
        b = self.resolve(path).read_bytes()
        self.bytes += len(b)
        return bytearray(b)


class Host:
    """vfs verbs under one Authority, called synchronously from JavaScript."""

    def __init__(self, fs: VirtualFileSystem, authority: Authority, loop: asyncio.AbstractEventLoop) -> None:
        self.fs, self.authority, self.loop = fs, authority, loop
        self.verbs: Counter[str] = Counter()
        self.ops: Counter[str] = Counter()
        self.sql_total = 0
        self.in_flight: list[str] = []
        self.sql_per_op: Counter[str] = Counter()
        self.trace: list[str] = []

    def count_sql(self, conn, cursor, statement, parameters, context, executemany):
        self.sql_total += 1
        if self.in_flight:
            self.sql_per_op[self.in_flight[-1]] += 1

    def run(self, coro):
        # JS called us on the main thread, outside any running loop: drive the verb to completion here.
        sys.stderr.write(f"[bridge] {coro.__qualname__ if hasattr(coro, '__qualname__') else coro}\n"); sys.stderr.flush()
        return self.loop.run_until_complete(coro)

    def fail(self, result) -> dict:
        kind = str(getattr(result.errors[0].kind, "value", result.errors[0].kind))
        return {"ok": False, "errno": ERRNO.get(kind, 29), "kind": kind}

    def bridge(self, op: str, path: str, extra):
        self.ops[op] += 1
        self.in_flight.append(op)
        try:
            return self._dispatch(op, path, extra)
        finally:
            self.in_flight.pop()

    def _dispatch(self, op: str, path: str, extra) -> dict:
        fs, a = self.fs, self.authority
        if op == "stat":
            self.verbs["stat"] += 1
            r = self.run(fs.stat(path=path, authority=a))
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            return {"ok": True, "kind": o.kind, "size": o.size_bytes or 0,
                    "mtime": o.updated_at.timestamp() if o.updated_at else 0}
        if op == "readdir":
            self.verbs["ls"] += 1
            r = self.run(fs.ls(path=path, authority=a))
            if r.errors:
                return self.fail(r)
            return {"ok": True, "entries": sorted(posixpath.basename(o.path) for o in r.observations)}
        if op == "read":
            self.verbs["read"] += 1
            r = self.run(fs.read(path=path, columns=READ_COLUMNS, authority=a))
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            body = o.data if o.data is not None else (o.content or "").encode()
            return {"ok": True, "data": bytearray(body)}
        if op == "write":
            self.verbs["write"] += 1
            body = bytes(extra)
            try:
                text = body.decode("utf-8")
                r = self.run(fs.write(path=path, content=text, parents=False, authority=a))
            except UnicodeDecodeError:
                r = self.run(fs.write(path=path, data=body, parents=False, authority=a))
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            self.trace.append(f"write {path} {len(body)}B -> version {o.version} mime {o.mime_type}")
            return {"ok": True}
        if op == "mkdir":
            self.verbs["mkdir"] += 1
            r = self.run(fs.mkdir(path, authority=a))
            return {"ok": True} if not r.errors else self.fail(r)
        if op == "unlink":
            self.verbs["delete"] += 1
            r = self.run(fs.delete(path=path, cascade=False, authority=a))
            return {"ok": True} if not r.errors else self.fail(r)
        if op == "rename":
            self.verbs["move"] += 1
            r = self.run(fs.move(src=path, dest=str(extra), authority=a))
            return {"ok": True} if not r.errors else self.fail(r)
        return {"ok": False, "errno": 52, "kind": "unsupported"}


async def setup_fs(loop) -> tuple[VirtualFileSystem, Authority, Host]:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    authority = Authority.of(Principal("agent-7", kind="agent"))
    await fs.write(path="/data/sales.csv", content=CSV, parents=True, authority=authority)
    await fs.mkdir("/out", authority=authority)
    await fs.mkdir("/scripts", authority=authority)
    await fs.write(path="/scripts/job.py", content=(HERE.parent / "s10" / "guest_job.py").read_text(), authority=authority)
    host = Host(fs, authority, loop)
    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", host.count_sql)
    return fs, authority, host


def main() -> None:
    args = sys.argv[1:]
    out = None
    if "--json" in args:
        i = args.index("--json"); out = Path(args[i + 1]); del args[i:i + 2]
    packages = ["numpy", "pandas", "matplotlib"]
    if "--packages" in args:
        i = args.index("--packages"); packages = args[i + 1].split(","); del args[i:i + 2]
    mode = "job"
    if "--mode" in args:
        i = args.index("--mode"); mode = args[i + 1]; del args[i:i + 2]

    report: dict = {"mode": mode, "packages": packages, "rss_mb_start": round(rss_mb(), 1)}
    # The vfs verbs live on an asyncio loop in a worker thread; JS calls arrive on the main thread.
    loop = asyncio.new_event_loop()
    fs, authority, host = loop.run_until_complete(setup_fs(loop))

    files = Files()
    guest_out: list[str] = []
    guest_err: list[str] = []
    pm.eval("globalThis.__host = {}")
    host_obj = pm.eval("globalThis.__host")
    host_obj.readText = files.read_text
    host_obj.readBinary = files.read_binary
    host_obj.urandom = lambda n: bytearray(os.urandom(int(n)))
    host_obj.print = lambda s: guest_out.append(str(s) + "\n")
    host_obj.printErr = lambda s: guest_err.append(str(s) + "\n")

    t0 = time.perf_counter()
    pm.eval((HERE / "pyodide_pm_shim.js").read_text())
    report["env_detect"] = pm.eval('typeof read + " " + typeof load + " " + typeof readbuffer + " " + typeof TextDecoder')
    # pyodide.asm.js defines the global `_createPyodideModule`; evaluating it here means the
    # loader never needs a module loader (its loadScript is skipped when the global exists).
    t = time.perf_counter()
    pm.eval((PYODIDE_DIR / "pyodide.asm.js").read_text())
    report["eval_asm_js_ms"] = round((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    pm.eval((PYODIDE_DIR / "pyodide.js").read_text())
    report["eval_loader_ms"] = round((time.perf_counter() - t) * 1000)
    report["loadPyodide_type"] = pm.eval("typeof loadPyodide")

    async def boot():
        t = time.perf_counter()
        py = await pm.eval(
            "(o) => loadPyodide({indexURL: '/pyodide/', stdout: o.print, stderr: o.printErr})"
        )(host_obj)
        report["loadPyodide_ms"] = round((time.perf_counter() - t) * 1000)
        report["rss_mb_after_load"] = round(rss_mb(), 1)
        report["python_version"] = str(py.runPython("import sys; sys.version"))
        if packages:
            t = time.perf_counter()
            # One package per call: a single loadPackage(["numpy","pandas","matplotlib"]) never
            # returns under PythonMonkey (pairs do); its parallel wheel loads stall the event loop.
            for name in packages:
                await py.loadPackage([name])
            report["loadPackage_ms"] = round((time.perf_counter() - t) * 1000)
            report["rss_mb_after_packages"] = round(rss_mb(), 1)
        return py

    py = asyncio.run(boot())
    report["loader_reads"] = dict(files.reads)
    report["loader_bytes_mb"] = round(files.bytes / 1048576, 1)

    if mode == "version":
        report["numpy_version"] = str(py.runPython("import numpy; numpy.__version__"))
        report["imports"] = str(py.runPython(
            "import importlib\n"
            "mods=['numpy','pandas','scipy','matplotlib','PIL','yaml','bs4','dateutil','pydantic','sqlite3','lxml','openpyxl','docx']\n"
            "out=[]\n"
            "for m in mods:\n"
            "    try:\n"
            "        mod=importlib.import_module(m); out.append(m+'='+str(getattr(mod,'__version__','ok')))\n"
            "    except Exception as e:\n"
            "        out.append(m+'=FAIL:'+type(e).__name__)\n"
            "' '.join(out)"))
        report["js_door"] = str(py.runPython(
            "import js\n"
            "names=['process','Deno','Bun','require','fetch','read','readbuffer','load','__host','python']\n"
            "' '.join(n+'='+str(hasattr(js,n)) for n in names)"))
        report["python_global_from_guest"] = str(py.runPython(
            "import js\n"
            "try:\n    r = str(js.python)[:80]\nexcept Exception as e:\n    r='ERR '+type(e).__name__\nr"))
    elif mode == "job":
        def step(msg):
            sys.stderr.write(f"[step] {msg}\n"); sys.stderr.flush()
        step("mounting")
        stats = pm.eval("__mountVFSFS")(py, host.bridge, "/vfs")
        step("mounted")
        t = time.perf_counter()
        exit_code, error = 0, None
        try:
            src = str(py.runPython("open('/vfs/scripts/job.py').read()"))
            step(f"script read: {len(src)} chars")
            py.runPython(src)
            step("script done")
        except Exception as e:  # noqa: BLE001
            exit_code, error = 1, str(e)[:2000]
        report["run_ms"] = round((time.perf_counter() - t) * 1000)
        report["exit"] = exit_code
        report["error"] = error
        report["bridge_calls"] = int(stats.calls)
        report["bridge_ms"] = int(stats.ms)
        report["ops"] = dict(host.ops)
        report["verbs"] = dict(host.verbs)
        report["sql_total"] = host.sql_total
        report["sql_per_op"] = dict(host.sql_per_op)
        report["trace"] = host.trace

        async def after():
            r = await fs.read(path="/out/plot.png", columns=READ_COLUMNS, authority=authority)
            if r.errors:
                return {"png_error": str(r.errors[0].kind)}
            o = r.observations[0]
            s = await fs.read(path="/out/summary.csv", columns=READ_COLUMNS, authority=authority)
            return {
                "png_row": {"path": o.path, "kind": o.kind, "mime_type": o.mime_type, "size_bytes": o.size_bytes,
                            "version": o.version, "data_is_png": bool(o.data and o.data[:8] == b"\x89PNG\r\n\x1a\n"),
                            "content_is_none": o.content is None},
                "summary_row": None if s.errors else {"mime_type": s.observations[0].mime_type,
                                                      "content_head": (s.observations[0].content or "")[:100]},
                "trash": sorted(posixpath.basename(x.path) for x in (await fs.ls(path="/.vfs/trash", authority=authority)).observations),
            }
        report.update(loop.run_until_complete(after()))
    elif mode == "door":
        # What a hostile script reaches through `import js` in this realm, before and after we close the door.
        probe = (HERE / "door_probe.py").read_text()
        report["door_open"] = str(py.runPython(probe))
        # Close it: the loader is done, so the shell API and the host table can go; so can PythonMonkey's `python`.
        report["delete_results"] = pm.eval(
            "() => ['python','__host','read','readbuffer','load','os','print','printErr'].map(n => { try { const d = delete globalThis[n]; return n + ':' + d + ':' + typeof globalThis[n]; } catch (e) { return n + ':ERR:' + e.message; } }).join(' ')"
        )()
        report["door_closed"] = str(py.runPython(probe))
        report["pm_require_from_guest"] = str(py.runPython(
            "import js\ntry:\n    r = str(js.require)[:40]\nexcept Exception as e:\n    r = type(e).__name__\nr"))
    elif mode == "two":
        # A second Pyodide instance in the same SpiderMonkey realm: the per-session cost without isolation.
        async def second():
            t = time.perf_counter()
            py2 = await pm.eval("(o) => loadPyodide({indexURL: '/pyodide/', stdout: o.print, stderr: o.printErr})")(host_obj)
            report["second_loadPyodide_ms"] = round((time.perf_counter() - t) * 1000)
            report["rss_mb_two_instances"] = round(rss_mb(), 1)
            report["second_runs"] = str(py2.runPython("import sys; sys.version[:6]"))
            report["instances_share_globals"] = str(py2.runPython("import js; str(js.pyodide is not None) if hasattr(js,'pyodide') else 'no js.pyodide'"))
        asyncio.run(second())
    elif mode == "interrupt":
        # Can a Python thread flip Pyodide's interrupt buffer while JS runs on the main thread?
        buf = bytearray(4)
        py.setInterruptBuffer(pm.eval("(b) => new Int32Array(b.buffer ?? b)")(buf))
        fired = {"at": None}

        def fire():
            time.sleep(0.3)
            buf[0] = 2
            fired["at"] = time.perf_counter()
        th = threading.Thread(target=fire); th.start()
        t = time.perf_counter()
        try:
            py.runPython("while True: pass")
            report["interrupt"] = "never returned"
        except Exception as e:  # noqa: BLE001
            report["interrupt"] = f"{type(e).__name__}: {str(e)[-120:]}"
        report["interrupt_ms"] = round((time.perf_counter() - t) * 1000)
        report["thread_ran_at_ms"] = None if fired["at"] is None else round((fired["at"] - t) * 1000)
    elif mode == "oom":
        t = time.perf_counter()
        try:
            py.runPython("import numpy as np\nxs=[]\nwhile True: xs.append(np.ones(50_000_000, dtype=np.uint8))")
            report["oom"] = "never returned"
        except Exception as e:  # noqa: BLE001
            report["oom"] = f"{type(e).__name__}: {str(e)[-300:]}"
        report["oom_ms"] = round((time.perf_counter() - t) * 1000)
        report["rss_mb_after_oom"] = round(rss_mb(), 1)
        report["still_alive"] = str(py.runPython("1+1"))

    report["wall_s"] = round(time.perf_counter() - t0, 2)
    report["rss_mb_end"] = round(rss_mb(), 1)
    report["guest_stdout"] = "".join(guest_out)[-1500:]
    report["guest_stderr"] = "".join(guest_err)[-800:]
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if out:
        out.write_text(text)
    os._exit(0)  # PythonMonkey's event loop thread would otherwise hold the process


if __name__ == "__main__":
    main()
