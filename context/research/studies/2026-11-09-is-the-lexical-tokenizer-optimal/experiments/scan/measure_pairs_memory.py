"""Memory of the two-phase variant's first phase alone: stream every covered (id, entry_id) pair into a list.

Opens the store, measures current and peak RSS before and after the streaming drain
(``psutil``-free: ``ru_maxrss`` for the peak and the Mach task info through ``resource``
is not available, so the current RSS is read from ``/proc``-less macOS via ``ps``), and
tracemalloc's peak for the Python objects alone. Usage: uv run python measure_pairs_memory.py <db path>
"""

from __future__ import annotations

import asyncio
import os
import resource
import subprocess
import sys
import time
import tracemalloc

from sqlalchemy import select

from vfs.storage.backends import DatabaseStorage


def rss_now_mb() -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout
    return round(int(out.strip()) / 1024, 1)


def peak_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 1)


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{sys.argv[1]}")
    assert await storage._host.ensure_ready() is None
    t = storage._host.tables
    chunks, entry = t.chunks, t.entry
    scan = (
        select(chunks.c.id, chunks.c.entry_id)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(entry.c.chunked, entry.c.indexable, entry.c.deleted_at.is_(None))
        .order_by(chunks.c.id)
    )
    async with storage._host.session_factory() as session:
        print(f"before: rss={rss_now_mb()} MB peak={peak_mb()} MB")
        tracemalloc.start()
        t0 = time.perf_counter()
        pairs = []
        async for row in await session.stream(scan.execution_options(yield_per=256)):
            pairs.append((row.id, row.entry_id))
        wall = time.perf_counter() - t0
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"after: pairs={len(pairs)} wall={wall:.2f}s rss={rss_now_mb()} MB peak={peak_mb()} MB "
              f"tracemalloc current={current / 2**20:.1f} MB peak={peak / 2**20:.1f} MB")
    await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
