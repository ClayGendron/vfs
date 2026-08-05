"""MSSQL benchmark gate: the batched pattern fan vs per-root dispatch.

The review's MSSQL observation (per-root queries beating a batched OR
fan there) became a chunk-width tuning question once ADR 031 moved
everything into one transaction — but "tuning question" must not become
an unexamined regression on one engine, so this gate measures both
shapes through the live executor before the 200-arm default stands for
the mssql dialect.

Measured 2026-08-05 (live docker leg, 2,000 files under 1,000 roots,
medians of 3, identical row sets verified): the batched fan wins at
both scales — K=100: 166 ms vs 629 ms per-root (3.8x); K=1,000:
4.72 s vs 6.57 s (1.4x). The review-era observation (per-root beating
a batched fan on MSSQL) does not reproduce through the
one-transaction executor; the 200-arm default stands for the mssql
dialect. Moved here 2026-08-05 at spec 092's mining pass.

Requires the docker MSSQL leg up (db_test skill) and the mssql extra:

    VFS_TEST_MSSQL_URL="mssql+aioodbc://sa:...@localhost:14330/master?..." \
      uv run python context/research/studies/2026-08-05-mssql-glob-fan-benchmark/mssql_fan_benchmark.py

Shape: K root directories of M files each; the batched leg is one
glob call carrying K composed patterns (the executor chunks at the
dialect budget); the per-root leg is K single-pattern calls — the
pre-092 dispatch shape. Medians of three, identical row sets verified.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

ROOT_COUNTS = (100, 1_000)
FILES_PER_ROOT = 2
ITERATIONS = 3


async def timed(coro_factory) -> tuple[float, int]:
    start = time.perf_counter()
    rows = await coro_factory()
    return time.perf_counter() - start, rows


async def main() -> int:
    url = os.environ.get("VFS_TEST_MSSQL_URL")
    if not url:
        print("VFS_TEST_MSSQL_URL is not set — start the mssql leg first (db_test skill)")
        return 2
    storage = DatabaseStorage(url=url, table_name="vfs_bench_fan")
    top = max(ROOT_COUNTS)
    entries = [
        Entry(path=Path(f"/part{i:05}/f{j}.parquet"), content=f"{i}-{j}")
        for i in range(top)
        for j in range(FILES_PER_ROOT)
    ]
    written = await storage.write(entries=entries, parents=True)
    assert written.success is True, written.errors
    print(f"seeded {len(entries)} files under {top} roots")

    for k in ROOT_COUNTS:
        patterns = tuple(f"/part{i:05}/**/*.parquet" for i in range(k))

        async def batched(patterns: tuple[str, ...] = patterns) -> int:
            result = await storage.glob(patterns=patterns)
            assert result.success is True
            return len(result.observations)

        async def per_root(patterns: tuple[str, ...] = patterns) -> int:
            total = 0
            for pattern in patterns:
                result = await storage.glob(patterns=(pattern,))
                assert result.success is True
                total += len(result.observations)
            return total

        expected = k * FILES_PER_ROOT
        batch_times, root_times = [], []
        for _ in range(ITERATIONS):
            elapsed, rows = await timed(batched)
            assert rows == expected, (rows, expected)
            batch_times.append(elapsed)
            elapsed, rows = await timed(per_root)
            assert rows == expected, (rows, expected)
            root_times.append(elapsed)
        batch = statistics.median(batch_times)
        root = statistics.median(root_times)
        print(
            f"K={k:>5}: batched fan {batch * 1000:8.1f} ms   "
            f"per-root {root * 1000:8.1f} ms   speedup {root / batch:5.1f}x"
        )

    await storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
