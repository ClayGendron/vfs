"""Benchmark quickjs-rs (LangChain's QuickJS-NG in wasm under wasmtime) from Python.

Run from the vfs repo root:
    uv run --with quickjs-rs python context/research/studies/2026-10-15-agent-shell/experiments/s5/bench_quickjs_rs.py

Measures: cold start (first Runtime + Context, which compiles the guest wasm),
warm context creation, a print('hello') equivalent, a 1e6-iteration loop, and
1,000 guest->host->guest round trips. Reports wall-clock as a benchmark fact.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import time

from quickjs_rs import Runtime


def rss_kb() -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True)
    return int(out.stdout.strip())


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def main() -> None:
    rss0 = rss_kb()

    # Cold start: first Runtime + Context in this process (compiles / loads the guest wasm).
    t0 = time.perf_counter()
    rt = Runtime()
    ctx = rt.new_context(timeout=60.0)
    cold = time.perf_counter() - t0
    rss1 = rss_kb()

    # Warm context creation on the same runtime.
    warm = []
    for _ in range(10):
        t = time.perf_counter()
        c = rt.new_context(timeout=60.0)
        warm.append(time.perf_counter() - t)
        c.close()

    # Warm Runtime creation (second wasm instance, module already compiled).
    warm_rt = []
    for _ in range(5):
        t = time.perf_counter()
        r2 = Runtime()
        c2 = r2.new_context(timeout=60.0)
        warm_rt.append(time.perf_counter() - t)
        c2.close()
        r2.close()

    # print("hello"): quickjs-rs has no console; register a host `print` and call it.
    out: list[str] = []

    @ctx.function
    def print_(s: str) -> None:
        out.append(s)

    hello = []
    for _ in range(20):
        t = time.perf_counter()
        ctx.eval("print_('hello')")
        hello.append(time.perf_counter() - t)
    assert out[-1] == "hello"

    # 1e6-iteration loop.
    loop = []
    for _ in range(5):
        t = time.perf_counter()
        r = ctx.eval("(() => { let s = 0; for (let i = 0; i < 1000000; i++) { s += i; } return s; })()")
        loop.append(time.perf_counter() - t)
    assert r == 499999500000

    # Host round trip x 1000: guest calls host, host returns a value.
    calls = 0

    @ctx.function
    def host_add(a: int, b: int) -> int:
        nonlocal calls
        calls += 1
        return a + b

    rt_samples = []
    for _ in range(5):
        calls = 0
        t = time.perf_counter()
        r = ctx.eval("(() => { let acc = 0; for (let i = 0; i < 1000; i++) { acc = host_add(acc, 1); } return acc; })()")
        rt_samples.append(time.perf_counter() - t)
        assert r == 1000 and calls == 1000

    # Snapshot size of a small context.
    ctx.eval("globalThis.state = {n: 1, items: [1,2,3]}")
    snap = ctx.create_snapshot().to_bytes()

    try:
        mem = rt.memory_usage()
    except Exception as e:  # noqa: BLE001
        mem = {"error": f"{type(e).__name__}: {e}"}

    # Interruptibility: a tight loop against a 0.2 s timeout.
    c3 = rt.new_context(timeout=0.2)
    t = time.perf_counter()
    try:
        c3.eval("for(;;){}")
        interrupted = "NOT interrupted"
    except Exception as e:  # noqa: BLE001
        interrupted = f"{type(e).__name__}: {str(e)[:60]}"
    interrupt_after = time.perf_counter() - t
    c3.close()

    rss2 = rss_kb()

    print("quickjs-rs 0.2.5 / wasmtime 49.0.0")
    print(f"cold start (Runtime + Context, first in process): {cold * 1000:.1f} ms")
    print(f"warm new_context (median of 10): {median_ms(warm):.3f} ms")
    print(f"warm Runtime+Context (median of 5): {median_ms(warm_rt):.2f} ms")
    print(f"print('hello') via host fn (median of 20): {median_ms(hello):.3f} ms")
    print(f"1e6-iteration loop (median of 5): {median_ms(loop):.1f} ms")
    print(f"1000 host round trips (median of 5): {median_ms(rt_samples):.2f} ms  -> {median_ms(rt_samples) * 1000 / 1000:.1f} us/call")
    print(f"snapshot bytes (small context): {len(snap)}")
    print(f"interrupt of for(;;) with 0.2 s timeout: {interrupted} after {interrupt_after * 1000:.0f} ms")
    print(f"guest memory counters: malloc_size={mem.get('malloc_size')} memory_used_size={mem.get('memory_used_size')}")
    print(f"host RSS: before={rss0 // 1024} MB after cold={rss1 // 1024} MB end={rss2 // 1024} MB")


if __name__ == "__main__":
    main()
