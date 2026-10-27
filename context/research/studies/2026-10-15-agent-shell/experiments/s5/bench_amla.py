"""Benchmark amla-sandbox 0.2.8 (QuickJS + shell inside one 15 MB wasm, wasmtime, stepping host-op loop).

Run from the vfs repo root:
    uv run --with amla-sandbox python context/research/studies/2026-10-15-agent-shell/experiments/s5/bench_amla.py

Measures cold start (first Sandbox + execute), console.log('hello'), a 1e6 loop,
and 1,000 tool calls through the capability-checked host-op loop. The wasm
runtime is AGPL/BUSL (study only); the Python package is MIT.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import time

from amla_sandbox import Sandbox, ToolCallCap, ToolDefinition


def rss_kb() -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True)
    return int(out.stdout.strip())


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def main() -> None:
    calls = 0

    def handler(method: str, params: dict) -> dict:
        nonlocal calls
        calls += 1
        return {"sum": params["a"] + params["b"]}

    rss0 = rss_kb()
    t = time.perf_counter()
    sb = Sandbox(
        tools=[ToolDefinition(name="add", description="add", parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}})],
        capabilities=[ToolCallCap(method_pattern="**", max_calls=1_000_000)],
        tool_handler=handler,
    )
    out = sb.execute("console.log('hello')")
    cold = time.perf_counter() - t
    rss1 = rss_kb()
    assert "hello" in out, out

    hello = []
    for _ in range(10):
        t = time.perf_counter()
        sb.execute("console.log('hello')")
        hello.append(time.perf_counter() - t)

    loop = []
    for _ in range(3):
        t = time.perf_counter()
        out = sb.execute("let s = 0; for (let i = 0; i < 1000000; i++) { s += i; } console.log(s)")
        loop.append(time.perf_counter() - t)
    assert "499999500000" in out, out

    rt = []
    for _ in range(3):
        calls = 0
        t = time.perf_counter()
        out = sb.execute("let acc = 0; for (let i = 0; i < 1000; i++) { acc = (await add({a: acc, b: 1})).sum; } console.log(acc)")
        rt.append(time.perf_counter() - t)
        assert "1000" in out and calls == 1000, (out, calls)
    rss2 = rss_kb()

    print("amla-sandbox 0.2.8 / wasmtime 49.0.0 / amla_sandbox.wasm 15.3 MB")
    print(f"cold start (Sandbox + first execute console.log): {cold * 1000:.0f} ms")
    print(f"console.log('hello') (median of 10): {median_ms(hello):.2f} ms")
    print(f"1e6-iteration loop (median of 3): {median_ms(loop):.0f} ms")
    print(f"1000 tool calls through the capability gate (median of 3): {median_ms(rt):.1f} ms -> {median_ms(rt):.0f} us/call")
    print(f"host RSS: before={rss0 // 1024} MB after cold={rss1 // 1024} MB end={rss2 // 1024} MB")


if __name__ == "__main__":
    main()
