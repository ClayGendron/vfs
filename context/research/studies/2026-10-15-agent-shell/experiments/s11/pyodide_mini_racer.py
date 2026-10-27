"""S11 experiment A2: Pyodide inside the Python process under py_mini_racer (V8 isolate).

The realm is bare V8 (no node, no browser). Python host functions can only be *async* here
(`wrap_py_function` renders as a Promise-returning JS function), so this experiment does
not attempt the synchronous VFSFS bridge; it measures what the V8 route gives: load time,
memory, `numpy.__version__`, interrupt (mini_racer's `timeout`), the hard memory limit, and
whether a wasm OOM takes the host process down. Artifacts reach the realm as base64 strings
pushed through `eval` (no file system, no fetch in the realm).

usage: uv run --with mini-racer python -I pyodide_mini_racer.py [--json out.json] [--packages numpy]
"""

from __future__ import annotations

import base64
import json
import resource
import sys
import time
from pathlib import Path

from py_mini_racer import MiniRacer

HERE = Path(__file__).resolve().parent
S10 = HERE.parent / "s10" / "pyodide_untrusted"
PYODIDE_DIR = S10 / "node_modules" / "pyodide"
PKGCACHE = S10 / "pkgcache"
SHIM = HERE / "pyodide_pm_shim.js"


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


PRELUDE = r"""
globalThis.__files = {};
globalThis.__b64 = (s) => {
  const bin = atob(s); const u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
};
globalThis.__stdout = []; globalThis.__stderr = [];
globalThis.__host = {
  readText: (p) => { const f = __files[p.split('/').pop()]; if (!f) throw new Error('no file ' + p); return new TextDecoder().decode(__b64(f)); },
  readBinary: (p) => { const f = __files[p.split('/').pop()]; if (!f) throw new Error('no file ' + p); return __b64(f); },
  urandom: (n) => { const u = new Uint8Array(n); for (let i = 0; i < n; i++) u[i] = (Math.random() * 256) | 0; return u; },
  print: (s) => __stdout.push(s), printErr: (s) => __stderr.push(s),
};
"""


def main() -> None:
    try:
        _main()
    finally:
        for c in list(_CTXS):
            try:
                c.close()
            except Exception:
                pass


_CTXS: list = []


def _main() -> None:
    args = sys.argv[1:]
    out = None
    if "--json" in args:
        i = args.index("--json"); out = Path(args[i + 1]); del args[i:i + 2]
    packages = ["numpy"]
    if "--packages" in args:
        i = args.index("--packages"); packages = args[i + 1].split(","); del args[i:i + 2]
    report: dict = {"packages": packages, "rss_mb_start": round(rss_mb(), 1)}

    t0 = time.perf_counter()
    ctx = MiniRacer(); _CTXS.append(ctx)
    report["v8"] = ctx.v8_version
    # mini_racer has no atob; a tiny one.
    ctx.eval(r"""
globalThis.atob ??= (s) => { const T='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'; let o=''; let b=0, n=0;
  for (const c of s) { if (c === '=') break; b = (b << 6) | T.indexOf(c); n += 6; if (n >= 8) { n -= 8; o += String.fromCharCode((b >> n) & 255); } }
  return o; };
""")
    ctx.eval(PRELUDE)
    ctx.eval(SHIM.read_text())
    # Push the artifacts: the npm core plus the wheels the packages need (by lock-file name).
    t = time.perf_counter()
    pushed = 0
    for p in list(PYODIDE_DIR.glob("*")) + list(PKGCACHE.glob("*")):
        if p.name in ("pyodide.asm.js", "pyodide.js", "pyodide.mjs", "pyodide.js.map", "pyodide.mjs.map", "console.html", "README.md", "ffi.d.ts", "pyodide.d.ts"):
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        ctx.eval(f"__files[{json.dumps(p.name)}] = {json.dumps(b64)}")
        pushed += len(b64)
    report["push_ms"] = round((time.perf_counter() - t) * 1000)
    report["pushed_mb_b64"] = round(pushed / 1048576, 1)
    report["rss_mb_after_push"] = round(rss_mb(), 1)

    t = time.perf_counter()
    ctx.eval((PYODIDE_DIR / "pyodide.asm.js").read_text())
    ctx.eval((PYODIDE_DIR / "pyodide.js").read_text())
    report["eval_scripts_ms"] = round((time.perf_counter() - t) * 1000)
    report["env"] = ctx.eval("typeof loadPyodide + ' ' + typeof _createPyodideModule + ' read=' + typeof read + ' load=' + typeof load")

    t = time.perf_counter()
    promise = ctx.eval("globalThis.__p = loadPyodide({indexURL: '/pyodide/', stdout: __host.print, stderr: __host.printErr}).then(p => { globalThis.pyodide = p; return 'loaded'; })")
    report["loadPyodide_result"] = str(promise.get(timeout=120))
    report["loadPyodide_ms"] = round((time.perf_counter() - t) * 1000)
    report["rss_mb_after_load"] = round(rss_mb(), 1)
    report["python_version"] = ctx.eval("String(pyodide.runPython('import sys; sys.version'))")

    if packages:
        t = time.perf_counter()
        report["loadPackage_result"] = str(ctx.eval(f"pyodide.loadPackage({json.dumps(packages)}).then((r) => JSON.stringify({{loaded: Object.keys(pyodide.loadedPackages), stderr: __stderr.slice(-5)}}))").get(timeout=120))
        report["loadPackage_ms"] = round((time.perf_counter() - t) * 1000)
        report["rss_mb_after_packages"] = round(rss_mb(), 1)
        t = time.perf_counter()
        try:
            report["numpy"] = ctx.eval("String(pyodide.runPython('import numpy as np; a = np.arange(10.0); str(np.__version__) + \" sum=\" + str(a.sum())'))")
        except Exception as e:  # noqa: BLE001
            report["numpy"] = f"{type(e).__name__}: {str(e)[:300]}"
            report["numpy_stderr"] = ctx.eval("__stderr.join('\\n')")[-1500:]
        report["numpy_first_import_ms"] = round((time.perf_counter() - t) * 1000)

    # The JavaScript door: what does `import js` see in this realm?
    report["js_door"] = ctx.eval("String(pyodide.runPython(\"import js; ' '.join(n+'='+str(hasattr(js,n)) for n in ['process','Deno','Bun','require','fetch','read','readbuffer','load','__files','__host','WebAssembly'])\"))")

    # Interrupt: mini_racer's own timeout terminates execution in the isolate.
    t = time.perf_counter()
    try:
        ctx.eval("pyodide.runPython('while True: pass')", timeout_sec=0.3)
        report["interrupt"] = "returned?!"
    except Exception as e:  # noqa: BLE001
        report["interrupt"] = f"{type(e).__name__} after {round((time.perf_counter() - t) * 1000)} ms"
    try:
        report["alive_after_interrupt"] = ctx.eval("String(pyodide.runPython('1+1'))")
    except Exception as e:  # noqa: BLE001
        report["alive_after_interrupt"] = f"{type(e).__name__}: {str(e)[:200]}"

    # Memory: wasm linear memory growth vs V8's hard limit; does an OOM kill the process?
    ctx.set_hard_memory_limit(1_500_000_000)
    t = time.perf_counter()
    try:
        r = ctx.eval("String(pyodide.runPython('import numpy as np\\nxs=[]\\nfor i in range(200): xs.append(np.ones(50_000_000, dtype=np.uint8))\\nlen(xs)'))", timeout_sec=60)
        report["oom"] = f"returned {r}"
    except Exception as e:  # noqa: BLE001
        report["oom"] = f"{type(e).__name__}: {str(e)[:300]}"
    report["oom_ms"] = round((time.perf_counter() - t) * 1000)
    report["hard_limit_reached"] = ctx.was_hard_memory_limit_reached()
    report["rss_mb_after_oom"] = round(rss_mb(), 1)
    try:
        report["alive_after_oom"] = ctx.eval("String(pyodide.runPython('1+1'))")
    except Exception as e:  # noqa: BLE001
        report["alive_after_oom"] = f"{type(e).__name__}: {str(e)[:200]}"
    report["host_process_alive"] = True

    # A second isolate: the per-session cost.
    t = time.perf_counter()
    ctx2 = MiniRacer(); _CTXS.append(ctx2)
    ctx2.eval("globalThis.atob = " + ctx.eval("String(globalThis.atob)"))
    ctx2.eval(PRELUDE)
    ctx2.eval(SHIM.read_text())
    for name in ("pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"):
        ctx2.eval(f"__files[{json.dumps(name)}] = {json.dumps(base64.b64encode((PYODIDE_DIR / name).read_bytes()).decode())}")
    ctx2.eval((PYODIDE_DIR / "pyodide.asm.js").read_text())
    ctx2.eval((PYODIDE_DIR / "pyodide.js").read_text())
    ctx2.eval("loadPyodide({indexURL: '/pyodide/'}).then(p => { globalThis.pyodide = p; return 'ok'; })").get(timeout=120)
    report["second_isolate_load_ms"] = round((time.perf_counter() - t) * 1000)
    report["rss_mb_two_isolates"] = round(rss_mb(), 1)
    report["second_isolate_runs"] = ctx2.eval("String(pyodide.runPython('2+2'))")
    ctx2.close()

    report["wall_s"] = round(time.perf_counter() - t0, 2)
    report["stdout"] = ctx.eval("__stdout.join('\\n')")[-800:]
    report["stderr"] = ctx.eval("__stderr.join('\\n')")[-800:]
    ctx.close()
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if out:
        out.write_text(text)


if __name__ == "__main__":
    main()
