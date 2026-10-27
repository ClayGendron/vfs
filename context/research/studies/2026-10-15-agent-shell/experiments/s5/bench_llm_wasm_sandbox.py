"""Benchmark llm-wasm-sandbox (CPython 3.12 WASI + QuickJS-NG CLI under wasmtime, fuel-metered).

Run from the vfs repo root:
    uv run --with llm-wasm-sandbox python context/research/studies/2026-10-15-agent-shell/experiments/s5/bench_llm_wasm_sandbox.py

Each `execute` writes the code to a host temp dir, preopens it, and runs `_start`
once; there is no persistent interpreter and no host-function model, so the
host-round-trip row is N/A here (it is measured for raw wasmtime separately).
"""

from __future__ import annotations

import os
import statistics
import subprocess
import time

from sandbox import ExecutionPolicy, RuntimeType, create_sandbox


def rss_kb() -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True)
    return int(out.stdout.strip())


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def bench(runtime: RuntimeType, hello: str, loop: str, label: str) -> None:
    rss0 = rss_kb()
    policy = ExecutionPolicy(fuel_budget=50_000_000_000)
    t0 = time.perf_counter()
    sb = create_sandbox(runtime=runtime, policy=policy)
    r = sb.execute(hello)
    cold = time.perf_counter() - t0
    rss1 = rss_kb()
    assert r.stdout.strip() == "hello", r.stdout
    fuel_hello = getattr(r, "fuel_consumed", None)

    warm = []
    for _ in range(5):
        t = time.perf_counter()
        r = sb.execute(hello)
        warm.append(time.perf_counter() - t)

    loops = []
    for _ in range(3):
        t = time.perf_counter()
        r = sb.execute(loop)
        loops.append(time.perf_counter() - t)
    assert r.stdout.strip() == "499999500000", r.stdout
    fuel_loop = getattr(r, "fuel_consumed", None)
    rss2 = rss_kb()

    print(f"[{label}]")
    print(f"  cold start (create_sandbox + first execute print): {cold * 1000:.0f} ms")
    print(f"  warm execute print('hello') (median of 5): {median_ms(warm):.0f} ms  fuel={fuel_hello}")
    print(f"  1e6-iteration loop, whole execute (median of 3): {median_ms(loops):.0f} ms  fuel={fuel_loop}")
    print(f"  host RSS: before={rss0 // 1024} MB after cold={rss1 // 1024} MB end={rss2 // 1024} MB")


def main() -> None:
    print("llm-wasm-sandbox 0.4.4 / wasmtime 38.0.0")
    bench(
        RuntimeType.PYTHON,
        "print('hello')",
        "s = 0\nfor i in range(1000000):\n    s += i\nprint(s)",
        "python.wasm (CPython 3.12.0, WLR build, 26.3 MB)",
    )
    bench(
        RuntimeType.JAVASCRIPT,
        "console.log('hello')",
        "let s = 0; for (let i = 0; i < 1000000; i++) { s += i; } console.log(s)",
        "quickjs.wasm (quickjs-ng qjs CLI, 1.4 MB)",
    )


if __name__ == "__main__":
    main()
