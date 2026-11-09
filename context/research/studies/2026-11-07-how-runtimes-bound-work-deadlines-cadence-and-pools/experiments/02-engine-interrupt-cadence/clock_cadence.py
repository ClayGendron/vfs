"""Measure the cost of time.monotonic() and of a deadline check at three cadences.

Four loops of N iterations each do the same trivial work (an integer accumulate) and
differ only in how often they read the clock and compare it with an absolute deadline:
never, every item, every 64th item, every 1,024th item. Each loop is timed with
time.perf_counter_ns over RUNS repetitions; the median is reported, with each cadence
as a ratio over the bare loop. A fifth measurement times time.monotonic() alone.

Run from the vfs checkout: uv run python -I <this file>. Output is JSON on stdout so
the study can quote it; wall-clock numbers are facts about this machine, not budgets.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time

N = 1_000_000
RUNS = 7
CLOCK_CALLS = 1_000_000


def bare(n: int, deadline: float) -> int:
    acc = 0
    for i in range(n):
        acc += i
    return acc


def every_item(n: int, deadline: float) -> int:
    acc = 0
    for i in range(n):
        acc += i
        if time.monotonic() >= deadline:
            return -1
    return acc


def every_64(n: int, deadline: float) -> int:
    acc = 0
    for i in range(n):
        acc += i
        if i & 63 == 0 and time.monotonic() >= deadline:
            return -1
    return acc


def every_1024(n: int, deadline: float) -> int:
    acc = 0
    for i in range(n):
        acc += i
        if i & 1023 == 0 and time.monotonic() >= deadline:
            return -1
    return acc


def time_loop(fn, n: int) -> list[int]:
    samples = []
    for _ in range(RUNS):
        deadline = time.monotonic() + 3600.0
        t0 = time.perf_counter_ns()
        result = fn(n, deadline)
        t1 = time.perf_counter_ns()
        if result < 0:
            raise RuntimeError("deadline fired; the measurement is invalid")
        samples.append(t1 - t0)
    return samples


def time_clock_calls(calls: int) -> list[int]:
    samples = []
    mono = time.monotonic
    for _ in range(RUNS):
        t0 = time.perf_counter_ns()
        for _ in range(calls):
            mono()
        t1 = time.perf_counter_ns()
        samples.append(t1 - t0)
    return samples


def main() -> None:
    loops = {
        "bare": bare,
        "every_item": every_item,
        "every_64th": every_64,
        "every_1024th": every_1024,
    }
    medians = {name: statistics.median(time_loop(fn, N)) for name, fn in loops.items()}
    clock_median = statistics.median(time_clock_calls(CLOCK_CALLS))
    # The empty loop over range(CLOCK_CALLS) is subtracted so the per-call cost is the call alone.
    empty_median = statistics.median(time_loop(bare, CLOCK_CALLS))
    base = medians["bare"]
    out = {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "iterations": N,
        "runs": RUNS,
        "monotonic_ns_per_call": (clock_median - empty_median) / CLOCK_CALLS,
        "monotonic_resolution_ns": time.get_clock_info("monotonic").resolution * 1e9,
        "median_ns": medians,
        "ns_per_iteration": {k: v / N for k, v in medians.items()},
        "ratio_over_bare": {k: v / base for k, v in medians.items()},
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
