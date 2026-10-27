"""Benchmark bashkit's CPython 3.14.8 Wizer-snapshotted WASI guest under wasmtime-py.

The guest (crates/bashkit-cpython-wasm/artifacts/python.wasm.xz, unpacked into the
scratchpad) is a *reactor*: `wizer-initialize` already ran `Py_Initialize` and
imported ~70 stdlib modules at build time, so a call starts with a running
interpreter. Its contract: export `bashkit_run() -> i32`, exactly one preopen `/`
at fd 3, the stdlib zip served at /usr/local/lib/python314.zip, one instance per
call. It also imports `bashkit.http_request`/`http_take`, which we trap.

Run from the vfs repo root:
    uv run --with wasmtime python bench_wasmtime_cpython314_wizer.py <python314.wasm> <root-dir-with-usr/local/lib/python314.zip> [--epoch]
"""

from __future__ import annotations

import importlib.metadata
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import wasmtime


def rss_kb() -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True)
    return int(out.stdout.strip())


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def run_once(engine, module, linker, code: str, root: str, tmp: str, epoch: bool) -> tuple[float, str, int]:
    out_path = os.path.join(tmp, "out.txt")
    err_path = os.path.join(tmp, "err.txt")
    store = wasmtime.Store(engine)
    wasi = wasmtime.WasiConfig()
    wasi.argv = ("python3", "-c", code)
    wasi.env = [("PWD", "/")]
    wasi.preopen_dir(root, "/")
    wasi.stdout_file = out_path
    wasi.stderr_file = err_path
    store.set_wasi(wasi)
    if epoch:
        store.set_epoch_deadline(1)
    t = time.perf_counter()
    inst = linker.instantiate(store, module)
    rc = inst.exports(store)["bashkit_run"](store)
    elapsed = time.perf_counter() - t
    with open(out_path) as f:
        out = f.read()
    with open(err_path) as f:
        err = f.read()
    if err:
        print("stderr:", err[:500])
    return elapsed, out, rc


def main() -> None:
    wasm_path, root = sys.argv[1], sys.argv[2]
    epoch = "--epoch" in sys.argv
    rss0 = rss_kb()
    cfg = wasmtime.Config()
    if epoch:
        cfg.epoch_interruption = True
    engine = wasmtime.Engine(cfg)
    t = time.perf_counter()
    module = wasmtime.Module.from_file(engine, wasm_path)
    compile_s = time.perf_counter() - t
    rss1 = rss_kb()
    blob = module.serialize()
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    linker.define_unknown_imports_as_traps(module)

    with tempfile.TemporaryDirectory() as tmp:
        hello = []
        for _ in range(5):
            el, out, rc = run_once(engine, module, linker, "print('hello')", root, tmp, epoch)
            hello.append(el)
        assert out.strip() == "hello", (out, rc)
        loops = []
        for _ in range(3):
            el, out, rc = run_once(engine, module, linker, "s=0\nfor i in range(1000000): s+=i\nprint(s)", root, tmp, epoch)
            loops.append(el)
        assert out.strip() == "499999500000", out
        imp = []
        for _ in range(3):
            el, out, rc = run_once(engine, module, linker, "import csv, json, re, dataclasses, enum\nprint('ok')", root, tmp, epoch)
            imp.append(el)
        assert out.strip() == "ok", out
        interrupted = "n/a"
        if epoch:
            timer = threading.Timer(0.2, engine.increment_epoch)
            timer.start()
            t = time.perf_counter()
            try:
                run_once(engine, module, linker, "while True: pass", root, tmp, epoch)
                interrupted = "NOT interrupted"
            except wasmtime.Trap as e:
                interrupted = f"Trap {e.trap_code} after {(time.perf_counter() - t) * 1000:.0f} ms"
            timer.cancel()
    rss2 = rss_kb()
    print(f"wasmtime-py {importlib.metadata.version('wasmtime')}  CPython 3.14.8 Wizer snapshot (bashkit)  size={os.path.getsize(wasm_path) / 1e6:.1f} MB (+3.2 MB stdlib zip)  epoch={epoch}")
    print(f"Module.from_file (Cranelift compile): {compile_s * 1000:.0f} ms; cwasm={len(blob) / 1e6:.1f} MB")
    print(f"instantiate+bashkit_run print('hello'): first={hello[0] * 1000:.1f} ms, median of 5={median_ms(hello):.1f} ms")
    print(f"1e6-iteration loop, whole run (median of 3): {median_ms(loops):.0f} ms -> loop alone ~{(statistics.median(loops) - statistics.median(hello)) * 1000:.0f} ms")
    print(f"import csv,json,re,dataclasses,enum + print (median of 3): {median_ms(imp):.1f} ms")
    print(f"epoch interrupt of `while True`: {interrupted}")
    print(f"host RSS: before={rss0 // 1024} MB after compile={rss1 // 1024} MB end={rss2 // 1024} MB")


if __name__ == "__main__":
    main()
