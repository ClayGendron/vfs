"""SQLite only: the range join with every range in one JSON bind, against the VALUES list.

Postgres can bind the range list as two arrays (unnest.py). SQLite has
no arrays, but ``json_each`` turns one JSON text bind into rows, so the
statement stays one bind however many ranges the caller holds. SQL
Server (``OPENJSON``), Oracle and MariaDB (``JSON_TABLE``) have the same
shape; this script measures only SQLite.

    uv run --no-sync python jsonbind.py

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import time
from uuid import uuid4

from probe import SEGMENTS_PER_CLAUSE, _case_sensitive_like, callers, corpus, segments, tables
from sqlalchemy import Column, and_, event, func, insert, select, text, values
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models.rows import BytewiseString

HERE = os.path.dirname(os.path.abspath(__file__))
REPS = 5


async def main() -> None:
    db = os.path.join("/tmp", f"authz-json-{uuid4().hex[:6]}.sqlite")
    engine = create_async_engine("sqlite+aiosqlite:///" + db)
    event.listen(engine.sync_engine, "connect", _case_sensitive_like)
    md, entry, docs, _cover = tables(f"azj_{uuid4().hex[:8]}")
    paths = corpus(10, 100, 50)
    lines = [
        f"## sqlite — {len(paths):,} entries, the count statement end to end, median of {REPS} warm runs (ms)\n",
        "| caller | ranges | values (statements) | json_each (1 statement) |",
        "|---|---|---|---|",
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
        joined = docs.join(entry, entry.c.entry_id == docs.c.entry_id)
        json_sql = text(
            f"SELECT count(*) FROM json_each(:ranges) AS c JOIN {entry.name} e "
            "ON e.path >= c.value ->> 0 AND e.path < c.value ->> 1 "
            f"JOIN {docs.name} d ON d.entry_id = e.entry_id"
        )
        for label, prefixes in callers(paths, 10, 100).items():
            segs = segments(prefixes)
            times: dict[str, list[float]] = {"values": [], "json": []}
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
                    n_json = (await conn.execute(json_sql, {"ranges": json.dumps(segs)})).scalar_one()
                    t2 = time.perf_counter()
                assert total == n_json, (label, total, n_json)
                if r:
                    times["values"].append((t1 - t0) * 1000)
                    times["json"].append((t2 - t1) * 1000)
            statements = -(-len(segs) // SEGMENTS_PER_CLAUSE)
            row = (
                f"| {label} | {len(segs):,} | {statistics.median(times['values']):.1f} ({statements}) "
                f"| {statistics.median(times['json']):.1f} |"
            )
            print(row, flush=True)
            lines.append(row)
        async with engine.connect() as conn:
            plan = (await conn.execute(text("EXPLAIN QUERY PLAN " + json_sql.text), {"ranges": "[]"})).all()
        lines.append("\nPlan:\n\n```\n" + "\n".join(" | ".join(str(c) for c in row) for row in plan) + "\n```")
    finally:
        await engine.dispose()
        os.remove(db)
    with open(os.path.join(HERE, "runs", "sqlite-jsonbind.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
