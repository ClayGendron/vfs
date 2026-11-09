"""Compare a per-item mask test against chunked loops that check the clock between chunks.

The first experiment showed the per-item `i & 63 == 0` test, not the clock read, is most of
the cadence cost in CPython. This one times Lucene's shape instead: an outer loop over chunks
of 64 or 1,024 items that reads the clock once per chunk, and an inner loop that carries no
test at all. Same work, same deadline, same medians over RUNS repetitions, ratios over bare.

Run from the vfs checkout: uv run python -I <this file>.
"""

from __future__ import annotations

import json
import statistics
import time

N = 1_000_000
RUNS = 7


def bare(n: int, deadline: float) -> int:
    acc = 0
    for i in range(n):
        acc += i
    return acc


def masked(n: int, deadline: float, mask: int) -> int:
    acc = 0
    for i in range(n):
        acc += i
        if i & mask == 0 and time.monotonic() >= deadline:
            return -1
    return acc


def chunked(n: int, deadline: float, chunk: int) -> int:
    acc = 0
    for start in range(0, n, chunk):
        if time.monotonic() >= deadline:
            return -1
        for i in range(start, min(start + chunk, n)):
            acc += i
    return acc


def time_loop(fn) -> int:
    samples = []
    for _ in range(RUNS):
        deadline = time.monotonic() + 3600.0
        t0 = time.perf_counter_ns()
        result = fn(N, deadline)
        t1 = time.perf_counter_ns()
        if result < 0:
            raise RuntimeError("deadline fired; the measurement is invalid")
        samples.append(t1 - t0)
    return int(statistics.median(samples))


def main() -> None:
    loops = {
        "bare": bare,
        "masked_64": lambda n, d: masked(n, d, 63),
        "masked_1024": lambda n, d: masked(n, d, 1023),
        "chunked_64": lambda n, d: chunked(n, d, 64),
        "chunked_1024": lambda n, d: chunked(n, d, 1024),
    }
    medians = {name: time_loop(fn) for name, fn in loops.items()}
    base = medians["bare"]
    out = {
        "iterations": N,
        "runs": RUNS,
        "ns_per_iteration": {k: v / N for k, v in medians.items()},
        "ratio_over_bare": {k: round(v / base, 3) for k, v in medians.items()},
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
