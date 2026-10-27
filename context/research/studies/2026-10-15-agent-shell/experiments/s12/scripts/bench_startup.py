"""Step 7 cold-start benchmark: N in-process runs per (binary, program) with the module deserialized from .cwasm once.
Reports median/min wall seconds per run plus guest linear memory. Reuses shim/run_vfs.py's machinery.

    uv run --with wasmtime python scripts/bench_startup.py --zip build/python314-numpy.zip --runs 10 \
        floor:build/.../python.wasm:_start numpy:...:_start wizer:...:vfs_run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import resource
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shim"))
sys.path.insert(0, str(HERE.parent.parent / "s4"))
from run_vfs import ARGV0, ENV, ZIP_PATH, load_module, make_engine, run_guest  # noqa: E402
from shim import Counters, Shim  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402
from vfs.storage.backends import InMemoryStorage  # noqa: E402

PROGRAMS = {
    "pass": "pass",
    "print": "print('hello')",
    "import_numpy": "import numpy; print(numpy.__version__)",
    "arange_sum": "import numpy; print(numpy.arange(10).sum())",
}


async def bench(label: str, wasm: Path, entry: str, zip_path: Path, runs: int, init: bool, cache_zip: bool = False) -> dict:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    await fs.write(path=ZIP_PATH, data=zip_path.read_bytes(), parents=True)
    if cache_zip:
        # Experiment: memoize the stdlib zip row on the host. zipimport reopens the archive once per module and the
        # shim stages the whole row on every open; a real shim would cache by (path, version) and invalidate on write.
        real_read = fs.read
        cached: dict = {}

        async def cached_read(*, path, **kw):
            if path == ZIP_PATH:
                if path not in cached:
                    cached[path] = await real_read(path=path, **kw)
                return cached[path]
            return await real_read(path=path, **kw)

        fs.read = cached_read  # type: ignore[method-assign]
    engine = make_engine()
    cwasm = wasm.with_suffix(".bench.cwasm")
    module, load_s, how = load_module(engine, wasm, cwasm)
    loop = asyncio.get_running_loop()
    out = {"label": label, "wasm": str(wasm), "wasm_bytes": wasm.stat().st_size, "cwasm_bytes": cwasm.stat().st_size,
           "module_load": how, "module_load_seconds": round(load_s, 4), "entry": entry, "programs": {}}
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for name, code in PROGRAMS.items():
        times, mem, stdout, verbs = [], None, "", {}
        for _ in range(runs):
            counters = Counters()
            shim = Shim(fs, loop, [ARGV0, "-I", "-X", "utf8", "-c", code], b"", counters)
            shim.env = list(ENV)
            t0 = time.perf_counter()
            rc, _, trapped = await loop.run_in_executor(None, run_guest, engine, module, shim, [], entry, init)
            times.append(time.perf_counter() - t0)
            mem = getattr(shim, "memory_pages", 0) * 64 / 1024
            stdout, verbs = shim.stdout.decode(errors="replace").strip(), dict(counters.verbs)
            if rc != 0 or trapped:
                stdout = f"rc={rc} trapped={trapped} stderr={shim.stderr.decode(errors='replace')[-300:]}"
                break
        out["programs"][name] = {"median_s": round(statistics.median(times), 4), "min_s": round(min(times), 4), "runs": len(times),
                                 "memory_mib": mem, "verbs": verbs, "stdout": stdout[:120]}
    out["host_maxrss_mib_after"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024), 1)
    out["host_maxrss_mib_before"] = round(rss0 / (1024 * 1024), 1)
    await fs.close()
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache-zip", action="store_true")
    ap.add_argument("targets", nargs="+", help="label:path.wasm:entry[:init]")
    a = ap.parse_args()
    results = []
    for t in a.targets:
        parts = t.split(":")
        label, wasm, entry = parts[0], Path(parts[1]), parts[2]
        init = len(parts) > 3 and parts[3] == "init"
        r = await bench(label, wasm, entry, Path(a.zip), a.runs, init, a.cache_zip)
        results.append(r)
        print(f"== {label}: wasm {r['wasm_bytes']} B, cwasm {r['cwasm_bytes']} B, load {r['module_load']} {r['module_load_seconds']}s, host maxrss {r['host_maxrss_mib_after']} MiB")
        for name, pr in r["programs"].items():
            print(f"   {name:13s} median {pr['median_s']*1000:8.1f} ms  min {pr['min_s']*1000:8.1f} ms  mem {pr['memory_mib']:6.1f} MiB  verbs {pr['verbs']}  -> {pr['stdout'][:60]!r}")
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
