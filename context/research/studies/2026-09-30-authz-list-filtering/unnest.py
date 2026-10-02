"""Postgres only: the range join with the ranges bound as two arrays, against the VALUES list.

probe.py shows the ``values`` shape executes as fast as a table of
ranges on Postgres but loses end to end: 2,000 binds per statement cost
more to build and send than to run. Postgres can take the whole range
list as two array binds and ``unnest`` them, so the statement text and
bind count stay fixed however many ranges the caller holds. This
script times that against ``values`` and ``drive``.

    VFS_TEST_POSTGRES_URL=... uv run --no-sync python unnest.py

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import asyncio
import os
import random
import statistics
import time
from uuid import uuid4

from probe import SEGMENTS_PER_CLAUSE, callers, corpus, segments, tables
from sqlalchemy import Column, and_, func, insert, select, text, values
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models.rows import BytewiseString

HERE = os.path.dirname(os.path.abspath(__file__))
REPS = 5


async def main() -> None:
    engine = create_async_engine(os.environ["VFS_TEST_POSTGRES_URL"])
    md, entry, docs, cover = tables(f"azu_{uuid4().hex[:8]}")
    paths = corpus(10, 100, 50)
    lines = [
        f"## postgres — {len(paths):,} entries, the count statement end to end, median of {REPS} warm runs (ms)\n",
        "| caller | ranges | values (statements) | unnest (1 statement) | drive (table) |",
        "|---|---|---|---|---|",
    ]
    try:
        async with engine.begin() as conn:
            await conn.run_sync(md.create_all)
            rng = random.Random(58)
            for start in range(0, len(paths), 5_000):
                batch = range(start, min(start + 5_000, len(paths)))
                await conn.execute(insert(entry), [{"entry_id": i, "path": paths[i]} for i in batch])
                await conn.execute(
                    insert(docs),
                    [{"chunk_id": i, "entry_id": i, "dl": 100 + i % 97, "score": rng.random()} for i in batch],
                )
            for t in (entry, docs):
                await conn.exec_driver_sql(f"ANALYZE {t.name}")
        joined = docs.join(entry, entry.c.entry_id == docs.c.entry_id)
        unnest_sql = text(
            f"SELECT count(*), sum(d.dl) FROM {docs.name} d JOIN {entry.name} e ON e.entry_id = d.entry_id "
            'JOIN unnest(CAST(:los AS text[]), CAST(:his AS text[])) AS c(lo, hi) ON e.path >= c.lo COLLATE "C" '
            'AND e.path < c.hi COLLATE "C"'
        )
        for set_id, (label, prefixes) in enumerate(callers(paths, 10, 100).items()):
            segs = segments(prefixes)
            async with engine.begin() as conn:
                await conn.execute(insert(cover), [{"set_id": set_id, "lo": lo, "hi": hi} for lo, hi in segs])
                await conn.exec_driver_sql(f"ANALYZE {cover.name}")
            times: dict[str, list[float]] = {"values": [], "unnest": [], "drive": []}
            counts: dict[str, int] = {}
            for r in range(REPS + 1):
                async with engine.connect() as conn:
                    await conn.exec_driver_sql("SELECT 1")
                    t0 = time.perf_counter()
                    total = 0
                    for i in range(0, len(segs), SEGMENTS_PER_CLAUSE):
                        vc = values(Column("lo", BytewiseString(1024)), Column("hi", BytewiseString(1024)), name="vc")
                        vc = vc.data(segs[i : i + SEGMENTS_PER_CLAUSE]).cte("vc")
                        stmt = select(func.count()).select_from(
                            joined.join(vc, and_(entry.c.path >= vc.c.lo, entry.c.path < vc.c.hi))
                        )
                        total += (await conn.execute(stmt)).scalar_one()
                    t1 = time.perf_counter()
                    los, his = [lo for lo, _ in segs], [hi for _, hi in segs]
                    n_unnest = (await conn.execute(unnest_sql, {"los": los, "his": his})).one()[0]
                    t2 = time.perf_counter()
                    stmt = select(func.count()).select_from(
                        joined.join(
                            cover, and_(cover.c.set_id == set_id, entry.c.path >= cover.c.lo, entry.c.path < cover.c.hi)
                        )
                    )
                    n_drive = (await conn.execute(stmt)).scalar_one()
                    t3 = time.perf_counter()
                assert total == n_unnest == n_drive, (label, total, n_unnest, n_drive)
                counts[label] = total
                if r:
                    times["values"].append((t1 - t0) * 1000)
                    times["unnest"].append((t2 - t1) * 1000)
                    times["drive"].append((t3 - t2) * 1000)
            statements = -(-len(segs) // SEGMENTS_PER_CLAUSE)
            row = (
                f"| {label} | {len(segs):,} | {statistics.median(times['values']):.1f} ({statements}) "
                f"| {statistics.median(times['unnest']):.1f} | {statistics.median(times['drive']):.1f} |"
            )
            print(row, flush=True)
            lines.append(row)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(md.drop_all)
        await engine.dispose()
    with open(os.path.join(HERE, "runs", "postgres-unnest.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
