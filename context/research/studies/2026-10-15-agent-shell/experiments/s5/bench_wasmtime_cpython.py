"""Benchmark CPython-on-WASI driven directly with wasmtime-py (no sandbox package).

Run from the vfs repo root:
    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s5/bench_wasmtime_cpython.py <python.wasm> [--epoch]

The binary is read-only input (an untrusted artifact, run only under wasmtime).
Measures: module compile, serialize/deserialize (the compile-once cache), RSS
after compile, instantiate + `_start` for print('hello') (cold and warm), the
1e6 loop, and a `host round trip` approximation: CPython-on-WASI has no
host-function import a Python program can call, so the only guest->host door is
a WASI syscall. We count 1,000 `fd_write` calls (print to stdout, flushed) as the
closest analogue and label it as such.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import importlib.metadata

import wasmtime


def rss_kb() -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True)
    return int(out.stdout.strip())


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def run_once(engine: wasmtime.Engine, module: wasmtime.Module, linker: wasmtime.Linker, code: str, tmp: str, epoch: bool) -> tuple[float, str, int | None]:
    out_path = os.path.join(tmp, "out.txt")
    store = wasmtime.Store(engine)
    wasi = wasmtime.WasiConfig()
    wasi.argv = ("python", "-c", code)
    wasi.stdout_file = out_path
    wasi.inherit_stderr()
    store.set_wasi(wasi)
    if epoch:
        store.set_epoch_deadline(1)
    t = time.perf_counter()
    inst = linker.instantiate(store, module)
    exit_code: int | None = None
    try:
        inst.exports(store)["_start"](store)
        exit_code = 0
    except wasmtime.ExitTrap as e:
        exit_code = e.code
    elapsed = time.perf_counter() - t
    with open(out_path) as f:
        return elapsed, f.read(), exit_code


def main() -> None:
    wasm_path = sys.argv[1]
    epoch = "--epoch" in sys.argv
    size = os.path.getsize(wasm_path)
    rss0 = rss_kb()

    cfg = wasmtime.Config()
    if epoch:
        cfg.epoch_interruption = True
    engine = wasmtime.Engine(cfg)

    t = time.perf_counter()
    module = wasmtime.Module.from_file(engine, wasm_path)
    compile_s = time.perf_counter() - t
    rss1 = rss_kb()

    t = time.perf_counter()
    blob = module.serialize()
    ser_s = time.perf_counter() - t
    with tempfile.TemporaryDirectory() as tmp:
        cwasm = os.path.join(tmp, "python.cwasm")
        with open(cwasm, "wb") as f:
            f.write(blob)
        t = time.perf_counter()
        module2 = wasmtime.Module.deserialize_file(engine, cwasm)
        deser_s = time.perf_counter() - t

        linker = wasmtime.Linker(engine)
        linker.define_wasi()

        hello = []
        outs = []
        for _ in range(5):
            el, out, code = run_once(engine, module2, linker, "print('hello')", tmp, epoch)
            hello.append(el)
            outs.append((out.strip(), code))
        assert outs[-1][0] == "hello", outs

        loops = []
        for _ in range(3):
            el, out, code = run_once(engine, module2, linker, "s=0\nfor i in range(1000000): s+=i\nprint(s)", tmp, epoch)
            loops.append(el)
        assert out.strip() == "499999500000", out

        # 1,000 WASI fd_write calls (sys.stdout.write + flush), the only guest->host door.
        syscalls = []
        for _ in range(3):
            el, out, code = run_once(engine, module2, linker, "import sys\nfor i in range(1000):\n    sys.stdout.write('x')\n    sys.stdout.flush()", tmp, epoch)
            syscalls.append(el)
        assert out == "x" * 1000

        interrupted = "n/a (run without --epoch)"
        if epoch:
            # A watchdog bumps the epoch after 0.2 s; the spinning guest must trap.
            timer = threading.Timer(0.2, engine.increment_epoch)
            timer.start()
            t = time.perf_counter()
            try:
                run_once(engine, module2, linker, "while True: pass", tmp, epoch)
                interrupted = "NOT interrupted"
            except wasmtime.Trap as e:
                interrupted = f"Trap {e.trap_code} after {(time.perf_counter() - t) * 1000:.0f} ms"
            timer.cancel()

    rss2 = rss_kb()
    print(f"wasmtime-py {importlib.metadata.version('wasmtime')}  binary={wasm_path}  size={size / 1e6:.1f} MB  epoch={epoch}")
    print(f"Module.from_file (Cranelift compile): {compile_s * 1000:.0f} ms;  serialize: {ser_s * 1000:.0f} ms ({len(blob) / 1e6:.1f} MB cwasm);  deserialize_file: {deser_s * 1000:.1f} ms")
    print(f"instantiate+_start print('hello'): first={hello[0] * 1000:.0f} ms, median of 5={median_ms(hello):.0f} ms")
    print(f"1e6-iteration loop, whole run incl. start (median of 3): {median_ms(loops):.0f} ms  -> loop alone ~{(statistics.median(loops) - statistics.median(hello)) * 1000:.0f} ms")
    print(f"1000 fd_write syscalls, whole run incl. start (median of 3): {median_ms(syscalls):.0f} ms -> ~{(statistics.median(syscalls) - statistics.median(hello)) * 1000:.1f} ms over hello")
    print(f"epoch interrupt of `while True`: {interrupted}")
    print(f"host RSS: before={rss0 // 1024} MB after compile={rss1 // 1024} MB end={rss2 // 1024} MB")


if __name__ == "__main__":
    main()
