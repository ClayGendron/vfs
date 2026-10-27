"""Run a python.wasm under the s4 preview1 shim over an InMemoryStorage vfs (spike s12).

Reuses experiments/s4/shim.py unchanged (Shim, bind, Counters, the SQL spy); adds only
(1) the custom import `vfs.ping` bound with Linker.define_func (the verb door), and
(2) the layout: the stdlib zip is a *vfs row* at /usr/local/lib/python314.zip and argv0 is
/usr/local/bin/python.wasm, so getpath finds the prefix through the zip landmark and no host
directory is ever preopened.

    uv run --with wasmtime python shim/run_vfs.py --wasm X.wasm --zip python314.zip [--cwasm] -c 'code'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "s4"))

from shim import Counters, GuestExit, Shim, bind  # noqa: E402
from sqlalchemy import event  # noqa: E402
from wasmtime import Config, Engine, Linker, Module, Store  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402
from vfs.storage.backends import InMemoryStorage  # noqa: E402

ZIP_PATH = "/usr/local/lib/python314.zip"
ARGV0 = "/usr/local/bin/python.wasm"
ENV = ["PYTHONUTF8=1", "PYTHONHASHSEED=0", "LC_ALL=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1"]


def make_engine() -> Engine:
    return Engine(Config())


def load_module(engine: Engine, wasm: Path, cwasm: Path | None) -> tuple[Module, float, str]:
    t0 = time.perf_counter()
    if cwasm is not None and cwasm.exists() and cwasm.stat().st_mtime >= wasm.stat().st_mtime:  # a relinked wasm invalidates the cache
        module = Module.deserialize_file(engine, str(cwasm))
        how = "deserialize"
    else:
        module = Module.from_file(engine, str(wasm))
        how = "compile"
        if cwasm is not None:
            cwasm.write_bytes(module.serialize())
    return module, time.perf_counter() - t0, how


def run_guest(engine: Engine, module: Module, shim: Shim, pings: list[int], entry: str = "_start", init: bool = False) -> tuple[int, list[str], str | None]:
    linker = Linker(engine)
    stubbed = bind(linker, module, shim)
    for imp in module.imports:
        if imp.module == "vfs" and imp.name == "ping":
            def ping(n: int) -> int:
                pings.append(n)
                return n * 2 + 1
            linker.define_func("vfs", "ping", imp.type, ping)
    store = Store(engine)
    instance = linker.instantiate(store, module)
    exports = instance.exports(store)
    code, trapped = 0, None
    try:
        if init:
            exports["_initialize"](store)   # a reactor that was not snapshotted: run its constructors once
        result = exports[entry](store)
        if entry != "_start" and result is not None:
            code = int(result)
    except GuestExit as exit_:
        code = exit_.code
    except Exception as exc:  # a wasm trap
        code, trapped = -1, f"{type(exc).__name__}: {exc}"
    for fd in list(shim.fds):
        if fd > 3:
            shim.flush(shim.fds.pop(fd))
    shim.memory_pages = instance.exports(store)["memory"].size(store)  # linear memory at exit, in 64 KiB pages
    return code, stubbed, trapped


async def run(args: argparse.Namespace) -> dict:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    zip_bytes = Path(args.zip).read_bytes()
    await fs.write(path=ZIP_PATH, data=zip_bytes, parents=True)
    for fixture in args.fixture:
        src, dest = fixture.split(":", 1)
        body = Path(src).read_bytes()
        try:
            await fs.write(path=dest, content=body.decode("utf-8"), parents=True)
        except UnicodeDecodeError:
            await fs.write(path=dest, data=body, parents=True)
    counters = Counters()
    per_verb: Counter[str] = Counter()
    in_flight: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        counters.statements += 1
        if in_flight:
            per_verb[in_flight[-1]] += 1

    sync_engine = storage._host.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count)
    engine = make_engine()
    module, load_s, how = load_module(engine, Path(args.wasm), Path(args.cwasm) if args.cwasm else None)
    loop = asyncio.get_running_loop()
    argv = [ARGV0, "-I", "-X", "utf8"] + (["-c", args.code] if args.code else [args.script])
    shim = Shim(fs, loop, argv, args.stdin.encode() if args.stdin else b"", counters)
    shim.env = list(ENV)
    original_verb = shim.verb

    def attributed_verb(name, coro):
        async def wrapped():
            in_flight.append(name)
            try:
                return await coro
            finally:
                in_flight.pop()
        return original_verb(name, wrapped())

    shim.verb = attributed_verb  # type: ignore[method-assign]
    pings: list[int] = []
    t1 = time.perf_counter()
    code, stubbed, trapped = await loop.run_in_executor(None, run_guest, engine, module, shim, pings, args.entry, args.init)
    run_s = time.perf_counter() - t1
    event.remove(sync_engine, "before_cursor_execute", _count)
    after = {}
    for path in args.read_back:
        r = await fs.read(path=path)
        for o in r.observations:
            after[path] = {"content": o.content, "data_len": len(o.data) if o.data is not None else None,
                           "mime_type": o.mime_type, "size_bytes": o.size_bytes,
                           "data_head": (o.data[:8].hex() if o.data else None)}
        if r.errors:
            after[path] = {"errors": [str(e.kind) for e in r.errors]}
    await fs.close()
    return {
        "wasm": str(args.wasm), "wasm_bytes": Path(args.wasm).stat().st_size,
        "zip_bytes": len(zip_bytes), "module_load": how, "module_load_seconds": round(load_s, 4),
        "argv": argv, "exit_code": code, "trapped": trapped,
        "stdout": shim.stdout.decode(errors="replace"), "stderr": shim.stderr.decode(errors="replace")[-3000:],
        "run_seconds": round(run_s, 4),
        "preview1_calls": dict(sorted(counters.syscalls.items())), "preview1_calls_total": sum(counters.syscalls.values()),
        "unimplemented_called": dict(counters.unimplemented), "imports_stubbed": stubbed,
        "verbs": dict(counters.verbs), "verbs_total": sum(counters.verbs.values()),
        "sql_statements": counters.statements, "sql_statements_per_verb": dict(per_verb),
        "bytes_to_guest": counters.bytes_to_guest, "bytes_from_guest": counters.bytes_from_guest,
        "vfs_ping_calls": pings, "read_back": after, "trace": counters.trace[:120],
        "memory_pages": getattr(shim, "memory_pages", None), "memory_mib": round(getattr(shim, "memory_pages", 0) * 64 / 1024, 1),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--wasm", required=True)
    p.add_argument("--zip", required=True)
    p.add_argument("--cwasm", default=None, help="serialize/deserialize the compiled module here")
    p.add_argument("-c", dest="code", default=None)
    p.add_argument("--script", default=None, help="guest path of a script already placed as a fixture")
    p.add_argument("--stdin", default=None)
    p.add_argument("--fixture", action="append", default=[], help="hostfile:guestpath, written as a vfs row before the run")
    p.add_argument("--read-back", action="append", default=[], help="guest path to read from vfs after the run")
    p.add_argument("--out", default=None)
    p.add_argument("--entry", default="_start", help="export to call: _start (command) or vfs_run (reactor)")
    p.add_argument("--init", action="store_true", help="call _initialize before the entry (un-snapshotted reactor)")
    args = p.parse_args()
    rep = asyncio.run(run(args))
    if args.out:
        Path(args.out).write_text(json.dumps(rep, indent=2, default=str))
    print(f"exit={rep['exit_code']} trapped={rep['trapped']} load={rep['module_load']} {rep['module_load_seconds']}s run={rep['run_seconds']}s")
    print("verbs:", rep["verbs"], "sql:", rep["sql_statements"], "preview1 calls:", rep["preview1_calls_total"])
    print("unimplemented called:", rep["unimplemented_called"], "pings:", rep["vfs_ping_calls"], "memory MiB:", rep["memory_mib"])
    print("--- stdout ---"); print(rep["stdout"][:4000])
    if rep["stderr"].strip():
        print("--- stderr ---"); print(rep["stderr"][-3000:])


if __name__ == "__main__":
    main()
