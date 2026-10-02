"""The plans behind probe.py's numbers: how each engine runs ``like``, ``tree``, ``drive`` and ``values``.

Loads the same corpus, grants one caller 500 folders, and prints the
engine's plan for the ``count`` statement in each shape.

    uv run --no-sync python plans.py --engine sqlite
    VFS_TEST_POSTGRES_URL=... uv run --no-sync python plans.py --engine postgres

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import time
from uuid import uuid4

from probe import (
    SEGMENTS_PER_CLAUSE,
    _case_sensitive_like,
    arm_like,
    corpus,
    segments,
    tables,
    tree,
)
from sqlalchemy import Column, and_, event, func, insert, or_, select, values
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models.rows import BytewiseString

HERE = os.path.dirname(os.path.abspath(__file__))


async def main(engine_name: str, arms: int, jit: bool) -> None:
    url = (
        "sqlite+aiosqlite:///" + os.path.join("/tmp", f"authz-plans-{uuid4().hex[:6]}.sqlite")
        if engine_name == "sqlite"
        else os.environ["VFS_TEST_POSTGRES_URL"]
    )
    engine = create_async_engine(url)
    if engine_name == "sqlite":
        event.listen(engine.sync_engine, "connect", _case_sensitive_like)
    md, entry, docs, cover = tables(f"azq_{uuid4().hex[:8]}")
    paths = corpus(10, 100, 50)
    folders = sorted({p.rsplit("/", 1)[0] for p in paths})
    prefixes = sorted(random.Random(30).sample(folders, arms))
    segs = segments(prefixes)
    out = [
        f"## {engine_name} — {len(paths):,} entries, {arms} folder grants, the count statement, jit={'on' if jit else 'off'}\n"
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
            await conn.execute(insert(cover), [{"set_id": 0, "lo": lo, "hi": hi} for lo, hi in segs])
            if engine_name == "postgres":
                for t in (entry, docs, cover):
                    await conn.exec_driver_sql(f"ANALYZE {t.name}")
        path = entry.c.path
        joined = docs.join(entry, entry.c.entry_id == docs.c.entry_id)
        vc = values(Column("lo", BytewiseString(1024)), Column("hi", BytewiseString(1024)), name="vc")
        vc = vc.data(segs[:SEGMENTS_PER_CLAUSE]).cte("vc")
        shapes = {
            "like (first 400 arms)": (joined, or_(*(arm_like(path, p) for p in prefixes[:400]))),
            "tree (first 1,000 ranges)": (joined, tree(path, segs[:SEGMENTS_PER_CLAUSE]) == 1),
            "drive": (joined.join(cover, and_(cover.c.set_id == 0, path >= cover.c.lo, path < cover.c.hi)), None),
            "values (first 1,000 ranges)": (joined.join(vc, and_(path >= vc.c.lo, path < vc.c.hi)), None),
        }
        for label, (source, pred) in shapes.items():
            stmt = select(func.count(), func.sum(docs.c.dl)).select_from(source)
            if pred is not None:
                stmt = stmt.where(pred)
            compiled = stmt.compile(engine.sync_engine, compile_kwargs={"literal_binds": True})
            prefix = "EXPLAIN QUERY PLAN " if engine_name == "sqlite" else "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) "
            async with engine.connect() as conn:
                if engine_name == "postgres" and not jit:
                    await conn.exec_driver_sql("SET jit = off")
                t0 = time.perf_counter()
                rows = (await conn.exec_driver_sql(prefix + str(compiled))).all()
                took = (time.perf_counter() - t0) * 1000
            text = "\n".join(" | ".join(str(c)[:160] for c in row) for row in rows)
            out.append(f"### {label} ({took:.0f} ms with EXPLAIN)\n\n```\n{text}\n```\n")
            print(out[-1], flush=True)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(md.drop_all)
        await engine.dispose()
    suffix = "" if jit or engine_name != "postgres" else "-nojit"
    with open(os.path.join(HERE, "runs", f"plans-{engine_name}{suffix}.md"), "w") as f:
        f.write("\n".join(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres"])
    ap.add_argument("--arms", type=int, default=500)
    ap.add_argument("--no-jit", action="store_true", help="Postgres: SET jit = off before each plan")
    a = ap.parse_args()
    asyncio.run(main(a.engine, a.arms, not a.no_jit))
