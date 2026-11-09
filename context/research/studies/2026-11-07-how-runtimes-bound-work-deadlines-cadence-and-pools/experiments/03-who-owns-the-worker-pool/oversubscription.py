"""Throughput of ContentMatcher.count_lines when N Python threads each submit a 256 x 1 MiB batch at once.

Read-only against the installed engine. Each submitting thread hands the same
256-body batch to the Rust kernel, which fans the batch across rayon's global
pool inside one call. Throughput is bytes scanned per second of wall time for
the whole concurrent round; medians of three rounds per width.
"""

from __future__ import annotations

import json
import os
import platform
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from vfs.native import extension

BODIES = 256
BODY_BYTES = 1 << 20
ROUNDS = 3


def make_batch() -> list[bytes]:
    rng = random.Random(7)
    alphabet = bytes(range(32, 127)) + b"\n" * 2
    out = []
    for _ in range(BODIES):
        out.append(bytes(rng.choices(alphabet, k=BODY_BYTES)))
    return out


def main() -> None:
    cores = os.cpu_count() or 1
    widths = sorted({1, 2, 4, cores, 2 * cores})
    pattern = sys.argv[1] if len(sys.argv) > 1 else "needle"
    matcher = extension().ContentMatcher(pattern, False)
    batch = make_batch()
    bytes_per_batch = BODIES * BODY_BYTES

    def one_call() -> int:
        counts, completed = matcher.count_lines(batch, cap=None, invert=False, budget=None)
        assert completed
        return sum(counts)

    one_call()  # warm
    report = {
        "pattern": pattern,
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpu_count": cores,
        "bodies": BODIES,
        "body_bytes": BODY_BYTES,
        "rounds": ROUNDS,
        "results": [],
    }
    for width in widths:
        with ThreadPoolExecutor(max_workers=width) as pool:
            samples = []
            for _ in range(ROUNDS):
                barrier = threading.Barrier(width)

                def job() -> int:
                    barrier.wait()
                    return one_call()

                t0 = time.perf_counter()
                futures = [pool.submit(job) for _ in range(width)]
                for f in futures:
                    f.result()
                elapsed = time.perf_counter() - t0
                samples.append(elapsed)
        median = statistics.median(samples)
        gib_s = width * bytes_per_batch / median / (1 << 30)
        report["results"].append(
            {
                "python_threads": width,
                "rounds_s": [round(s, 4) for s in samples],
                "median_s": round(median, 4),
                "aggregate_gib_per_s": round(gib_s, 2),
                "per_thread_gib_per_s": round(gib_s / width, 2),
            }
        )
        print(
            f"threads={width:3d} median={median:.4f}s aggregate={gib_s:.2f} GiB/s per-thread={gib_s / width:.2f} GiB/s",
            flush=True,
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
