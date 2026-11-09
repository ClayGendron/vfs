"""Cost of a Deadline value type's tick against the inline check vfs writes today.

Four loops of N iterations doing trivial work (an integer add), each with a
different deadline check: none; the inline `i % 64 == 0 and monotonic() > deadline`;
a Deadline object whose `tick()` counts internally and reads the clock every 64th
call; and a Deadline object whose `expired()` reads the clock on every call.
Medians of 7 runs, so the memo can say whether a type is affordable per row.
"""

from __future__ import annotations

import platform
import statistics
import sys
from time import monotonic, perf_counter

N = 1_000_000
RUNS = 7
EVERY = 64


class Deadline:
    __slots__ = ("_at", "_count")

    def __init__(self, at: float) -> None:
        self._at = at
        self._count = 0

    def expired(self) -> bool:
        return monotonic() > self._at

    def tick(self) -> bool:
        self._count += 1
        return self._count % EVERY == 0 and monotonic() > self._at


def bare() -> int:
    total = 0
    for i in range(N):
        total += i
    return total


def inline(deadline: float) -> int:
    total = 0
    for i in range(N):
        if i % EVERY == 0 and monotonic() > deadline:
            break
        total += i
    return total


def typed_tick(deadline: Deadline) -> int:
    total = 0
    for i in range(N):
        if deadline.tick():
            break
        total += i
    return total


def typed_every(deadline: Deadline) -> int:
    total = 0
    for i in range(N):
        if deadline.expired():
            break
        total += i
    return total


def timed(fn, *args) -> float:
    samples = []
    for _ in range(RUNS):
        start = perf_counter()
        fn(*args)
        samples.append(perf_counter() - start)
    return statistics.median(samples)


def main() -> None:
    far = monotonic() + 3600.0
    base = timed(bare)
    rows = [
        ("no check", base),
        ("inline, every 64th", timed(inline, far)),
        ("Deadline.tick(), every 64th inside", timed(typed_tick, Deadline(far))),
        ("Deadline.expired(), every item", timed(typed_every, Deadline(far))),
    ]
    print(f"python {sys.version.split()[0]} on {platform.machine()} {platform.system()}; N={N:,}; medians of {RUNS}")
    print(f"{'loop':40s} {'ms':>9s} {'x bare':>7s} {'ns/item':>8s}")
    for name, seconds in rows:
        print(f"{name:40s} {seconds * 1e3:9.1f} {seconds / base:7.2f} {seconds / N * 1e9:8.1f}")
    clock = timed(lambda: [monotonic() for _ in range(N)])
    print(f"{'monotonic() alone, per call':40s} {clock * 1e3:9.1f} {'':7s} {clock / N * 1e9:8.1f}")


if __name__ == "__main__":
    main()
