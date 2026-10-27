"""Benchmark pydantic-monty 1.1.0 (worker-subprocess pool) from Python.

Run from the vfs repo root:
    uv run --with pydantic-monty python context/research/studies/2026-10-15-agent-shell/experiments/s5/bench_monty.py

Measures: new pool (spawns the worker binary), checkout + first feed on a warm
pool, print('hello') through a CollectString sink, a 1e6-iteration loop, 1,000
guest->host->guest round trips through `external_lookup`, the size of a
mid-feed snapshot (`feed_start` + `dump`), and the worker's RSS.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import time

from pydantic_monty import CollectString, FunctionSnapshot, Monty, MontyComplete, MontyRuntimeError


def rss_kb(pid: int) -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


def median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000


def main() -> None:
    rss_host0 = rss_kb(os.getpid())
    t0 = time.perf_counter()
    pool = Monty(min_processes=1)
    pool.__enter__()
    new_pool = time.perf_counter() - t0

    # First checkout + feed on the fresh pool.
    t = time.perf_counter()
    with pool.checkout() as s:
        r = s.feed_run("1 + 1")
    first_checkout = time.perf_counter() - t
    assert r == 2

    # Warm checkout + feed, median of 20 with a short idle between (as the docs measure).
    warm = []
    for _ in range(20):
        time.sleep(0.05)
        t = time.perf_counter()
        with pool.checkout() as s:
            s.feed_run("1 + 1")
        warm.append(time.perf_counter() - t)

    # Default max_suspensions is 1000 per checkout (host calls); raise it for the round-trip test.
    with pool.checkout(limits={"max_suspensions": 100_000}) as session:
        worker_pid = session.worker_pid
        rss_worker0 = rss_kb(worker_pid) if worker_pid else 0

        hello = []
        for _ in range(20):
            sink = CollectString()
            t = time.perf_counter()
            session.feed_run("print('hello')", print_callback=sink)
            hello.append(time.perf_counter() - t)
        assert sink.output.strip() == "hello"

        loop = []
        for _ in range(5):
            t = time.perf_counter()
            r = session.feed_run("s = 0\nfor i in range(1000000):\n    s += i\ns")
            loop.append(time.perf_counter() - t)
        assert r == 499999500000

        calls = 0

        def host_add(a: int, b: int) -> int:
            nonlocal calls
            calls += 1
            return a + b

        rt_samples = []
        for _ in range(5):
            calls = 0
            t = time.perf_counter()
            r = session.feed_run(
                "acc = 0\nfor i in range(1000):\n    acc = host_add(acc, 1)\nacc",
                external_lookup={"host_add": host_add},
            )
            rt_samples.append(time.perf_counter() - t)
            assert r == 1000 and calls == 1000, (r, calls)

        rss_worker1 = rss_kb(worker_pid) if worker_pid else 0

    # Pause/resume: suspend at a host call, dump, measure bytes, resume.
    with pool.checkout() as s2:
        snap = s2.feed_start("items = [1, 2, 3]\ntotal = sum(items)\nreply = ask_subagent('summarise', total)\nreply + '!'")
        assert isinstance(snap, FunctionSnapshot) and snap.function_name == "ask_subagent"
        t = time.perf_counter()
        dump = s2.dump()
        dump_s = time.perf_counter() - t
        done = snap.resume({"return_value": "ok"})
        assert isinstance(done, MontyComplete) and done.output == "ok!"

    # Restore the dump into a fresh session and resume there (durable pause).
    with pool.checkout() as s3:
        t = time.perf_counter()
        restored = s3.load_snapshot(dump)
        load_s = time.perf_counter() - t
        assert isinstance(restored, FunctionSnapshot)
        done2 = restored.resume({"return_value": "later"})
        assert isinstance(done2, MontyComplete) and done2.output == "later!"

    # Interruptibility: an infinite loop against max_feed_duration_secs.
    with pool.checkout(limits={"max_feed_duration_secs": 0.2}) as s4:
        t = time.perf_counter()
        try:
            s4.feed_run("while True:\n    pass")
            interrupted = "NOT interrupted"
        except MontyRuntimeError as e:
            interrupted = f"MontyRuntimeError: {e.display(format='type-msg')}"
        interrupt_after = time.perf_counter() - t

    # Language-subset probes: what an agent might write that Monty rejects.
    probes = {
        "class with base": "class A: pass\nclass B(A): pass",
        "generator": "def g():\n    yield 1\nlist(g())",
        "match": "match 1:\n    case 1: pass",
        "import csv": "import csv",
        "import enum": "import enum",
        "dataclass": "from dataclasses import dataclass\n@dataclass\nclass P:\n    x: int\nP(1).x",
        "property": "class A:\n    @property\n    def x(self): return 1",
        "del": "d = {1: 2}\ndel d[1]",
        "walrus": "(y := 3) + 1",
        "with open": "with open('/tmp/x') as f: f.read()",
    }
    probe_results = {}
    with pool.checkout() as s5:
        for name, code in probes.items():
            try:
                s5.feed_run(code)
                probe_results[name] = "ok"
            except Exception as e:  # noqa: BLE001
                probe_results[name] = f"{type(e).__name__}: {str(e).splitlines()[-1][:70]}"

    rss_host1 = rss_kb(os.getpid())
    pool.__exit__(None, None, None)

    print("pydantic-monty 1.1.0 (worker binary: pydantic-monty-runtime 1.1.0)")
    print(f"new pool (spawn worker + handshake): {new_pool * 1000:.1f} ms")
    print(f"first checkout + feed_run('1 + 1'): {first_checkout * 1000:.2f} ms")
    print(f"warm checkout + feed_run after 50 ms idle (median of 20): {median_ms(warm):.2f} ms")
    print(f"print('hello') via CollectString (median of 20): {median_ms(hello):.3f} ms")
    print(f"1e6-iteration loop (median of 5): {median_ms(loop):.1f} ms")
    print(f"1000 host round trips via external_lookup (median of 5): {median_ms(rt_samples):.1f} ms -> {median_ms(rt_samples):.1f} us/call")
    print(f"mid-feed snapshot: dump={len(dump)} bytes in {dump_s * 1000:.2f} ms; load_snapshot into fresh session {load_s * 1000:.2f} ms; resumed OK")
    print(f"interrupt of `while True` with max_feed_duration_secs=0.2: {interrupted} after {interrupt_after * 1000:.0f} ms")
    print(f"worker RSS: idle={rss_worker0 // 1024} MB after loop+roundtrips={rss_worker1 // 1024} MB; host RSS before={rss_host0 // 1024} MB after={rss_host1 // 1024} MB")
    print("subset probes:")
    for k, v in probe_results.items():
        print(f"  {k:18s} {v}")


if __name__ == "__main__":
    main()
