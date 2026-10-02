"""Per-query visibility cost as grants grow: five predicate shapes on one lean corpus.

The question: vfs compiles a caller's rights to OR'd path-prefix arms,
so a scan tests every row against every arm and the per-query cost
grows with the arm count. This probe asks which shape keeps that cost
flat. Every shape here returns the same rows; the probe asserts it.

Shapes, all built from the same minimised prefix set:

- ``like``      — today's form: ``path = p OR path LIKE 'p/%'`` per arm, OR'd.
- ``range``     — the same with ``path >= 'p/' AND path < 'p0'`` per arm.
- ``tree``      — the arms as disjoint byte ranges, sorted, and tested by a
                  balanced ``CASE path < split THEN left ELSE right`` tree:
                  about log2(2N) comparisons per row, still pure literals.
- ``stab``      — the ranges written once to a small ``cover`` table; each
                  row finds the greatest range start at or below its path
                  (one index probe, ``ORDER BY lo DESC LIMIT 1``) and checks
                  it lies before that range's end.
- ``drive``     — the same ``cover`` table joined from the range side:
                  one index range scan of the entry table per covering range.
- ``values``    — ``drive`` with the ranges shipped as a literal ``VALUES``
                  list instead of a table: no write, two binds per range.

Two statements per shape, shaped like glean's two scans under a partial
caller: ``count`` (visible chunk count and total length, the BM25
statistics) and ``top10`` (the ten best by a score column over every
visible chunk, the vector leg's shape).

    uv run --no-sync python probe.py --engine sqlite
    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
      uv run --no-sync python probe.py --engine postgres

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    and_,
    case,
    func,
    insert,
    literal,
    or_,
    event,
    select,
    true,
    values,
)
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models.rows import BytewiseString

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS_PER_CLAUSE = 400  # the literal OR forms split here, as vfs does past its depth budget
SEGMENTS_PER_CLAUSE = 1_000  # tree and values split here: 2,000 binds, SQL Server's floor
POINT_END = "\x01"  # [p, p + \x01) holds p alone: no lawful path carries a control byte


def tables(prefix: str) -> tuple[MetaData, Table, Table, Table]:
    md = MetaData()
    entry = Table(
        f"{prefix}_entry",
        md,
        Column("entry_id", Integer, primary_key=True, autoincrement=False),
        Column("path", BytewiseString(1024), nullable=False, unique=True, index=True),
    )
    docs = Table(
        f"{prefix}_docs",
        md,
        Column("chunk_id", Integer, primary_key=True, autoincrement=False),
        Column("entry_id", Integer, nullable=False, index=True),
        Column("dl", Integer, nullable=False),
        Column("score", Float, nullable=False),
    )
    cover = Table(
        f"{prefix}_cover",
        md,
        Column("set_id", Integer, nullable=False),
        Column("lo", BytewiseString(1024), nullable=False),
        Column("hi", BytewiseString(1024), nullable=False),
        PrimaryKeyConstraint("set_id", "lo"),
    )
    return md, entry, docs, cover


def corpus(tops: int, folders: int, files: int) -> list[str]:
    return [f"/t{t:02d}/f{f:03d}/doc{n:03d}.md" for t in range(tops) for f in range(folders) for n in range(files)]


def callers(paths: list[str], tops: int, folders: int) -> dict[str, list[str]]:
    """Caller label → its minimised prefix set (disjoint, none beneath another)."""
    every_folder = [f"/t{t:02d}/f{f:03d}" for t in range(tops) for f in range(folders)]
    rng = random.Random(30)
    out: dict[str, list[str]] = {}
    for n in (k for k in (1, 10, 100, 500) if k < len(every_folder)):
        out[f"{n} folders ({n / len(every_folder):.1%})"] = sorted(rng.sample(every_folder, n))
    out["10% via 1 top"] = ["/t00"]
    tenth = sorted(rng.sample(paths, len(paths) // 10))
    out[f"10% via {len(tenth)} files"] = tenth
    return out


def segments(prefixes: list[str]) -> list[tuple[str, str]]:
    """The prefixes as sorted disjoint half-open byte ranges ``[lo, hi)``."""
    out = []
    for p in prefixes:
        out.append((p, p + POINT_END))
        out.append((p + "/", p + "0"))
    return sorted(out)


def arm_like(path: Any, p: str) -> Any:
    return or_(path == p, path.like(p + "/%"))


def arm_range(path: Any, p: str) -> Any:
    return or_(path == p, and_(path >= p + "/", path < p + "0"))


def tree(path: Any, segs: list[tuple[str, str]]) -> Any:
    """A balanced CASE over sorted disjoint ranges, returning 1 inside and 0 outside."""
    if len(segs) == 1:
        lo, hi = segs[0]
        return case((and_(path >= lo, path < hi), literal(1)), else_=literal(0))
    mid = len(segs) // 2
    return case((path < segs[mid][0], tree(path, segs[:mid])), else_=tree(path, segs[mid:]))


async def main(engine_name: str, tops: int, folders: int, files: int, reps: int) -> None:
    url = (
        "sqlite+aiosqlite:///" + os.path.join("/tmp", f"authz-probe-{uuid4().hex[:6]}.sqlite")
        if engine_name == "sqlite"
        else os.environ["VFS_TEST_POSTGRES_URL"]
    )
    engine = create_async_engine(url)
    if engine_name == "sqlite":
        event.listen(engine.sync_engine, "connect", _case_sensitive_like)
    md, entry, docs, cover = tables(f"azp_{uuid4().hex[:8]}")
    paths = corpus(tops, folders, files)
    rng = random.Random(58)
    lines = [
        f"## {engine_name} — {len(paths):,} entries, one chunk each, median of {reps} warm runs (ms)\n",
        "| caller | arms | shape | count ms | top10 ms | rows seen |",
        "|---|---|---|---|---|---|",
    ]
    try:
        async with engine.begin() as conn:
            await conn.run_sync(md.create_all)
            for start in range(0, len(paths), 5_000):
                batch = range(start, min(start + 5_000, len(paths)))
                await conn.execute(insert(entry), [{"entry_id": i, "path": paths[i]} for i in batch])
                await conn.execute(
                    insert(docs),
                    [{"chunk_id": i, "entry_id": i, "dl": 100 + i % 97, "score": rng.random()} for i in batch],
                )
            if engine_name == "postgres":
                for t in (entry, docs):
                    await conn.exec_driver_sql(f"ANALYZE {t.name}")
        joined = docs.join(entry, entry.c.entry_id == docs.c.entry_id)
        for set_id, (label, prefixes) in enumerate(callers(paths, tops, folders).items()):
            segs = segments(prefixes)
            async with engine.begin() as conn:
                t0 = time.perf_counter()
                for start in range(0, len(segs), 2_000):
                    rows = [{"set_id": set_id, "lo": lo, "hi": hi} for lo, hi in segs[start : start + 2_000]]
                    await conn.execute(insert(cover), rows)
                if engine_name == "postgres":
                    await conn.exec_driver_sql(f"ANALYZE {cover.name}")
                cover_ms = (time.perf_counter() - t0) * 1000
            path = entry.c.path
            groups = [prefixes[i : i + ARMS_PER_CLAUSE] for i in range(0, len(prefixes), ARMS_PER_CLAUSE)]
            seg_groups = [segs[i : i + SEGMENTS_PER_CLAUSE] for i in range(0, len(segs), SEGMENTS_PER_CLAUSE)]
            predecessor = (
                select(cover.c.hi)
                .where(cover.c.set_id == set_id, cover.c.lo <= path)
                .order_by(cover.c.lo.desc())
                .limit(1)
                .scalar_subquery()
            )
            cjoin = joined.join(cover, and_(cover.c.set_id == set_id, path >= cover.c.lo, path < cover.c.hi))
            vjoins = [
                joined.join(v, and_(path >= v.c.lo, path < v.c.hi))
                for v in (
                    values(Column("lo", BytewiseString(1024)), Column("hi", BytewiseString(1024)), name="vc")
                    .data(g)
                    .cte(f"vc{i}")
                    for i, g in enumerate(seg_groups)
                )
            ]
            shapes: dict[str, tuple[list[Any], Any]] = {
                "like": ([or_(*(arm_like(path, p) for p in g)) for g in groups], joined),
                "range": ([or_(*(arm_range(path, p) for p in g)) for g in groups], joined),
                "tree": ([tree(path, g) == 1 for g in seg_groups], joined),
                "stab": ([path < predecessor], joined),
                "drive": ([cover.c.set_id == set_id], cjoin),
                "values": ([true()] * len(vjoins), vjoins),
            }
            expected: tuple[int, list[int]] | None = None
            for shape, (preds, sources) in shapes.items():
                count_t, top_t = [], []
                seen = 0
                for r in range(reps + 1):
                    async with engine.connect() as conn:
                        t0 = time.perf_counter()
                        total = 0
                        for pred, source in zip(preds, _sources(sources, len(preds)), strict=True):
                            stmt = select(func.count(), func.coalesce(func.sum(docs.c.dl), 0))
                            n, _dl = (await conn.execute(stmt.select_from(source).where(pred))).one()
                            total += n
                        t1 = time.perf_counter()
                        best: list[tuple[float, int]] = []
                        for pred, source in zip(preds, _sources(sources, len(preds)), strict=True):
                            stmt = (
                                select(docs.c.score, docs.c.chunk_id)
                                .select_from(source)
                                .where(pred)
                                .order_by(docs.c.score, docs.c.chunk_id)
                                .limit(10)
                            )
                            best += [(row.score, row.chunk_id) for row in await conn.execute(stmt)]
                        t2 = time.perf_counter()
                    top = [cid for _s, cid in sorted(best)[:10]]
                    if r == 0:
                        seen = total
                        if expected is None:
                            expected = (total, top)
                        assert (total, top) == expected, (label, shape, total, expected[0])
                        continue
                    count_t.append((t1 - t0) * 1000)
                    top_t.append((t2 - t1) * 1000)
                note = f" (+{cover_ms:.0f} ms cover write)" if shape == "stab" else ""
                row = (
                    f"| {label} | {len(prefixes)} | {shape}{note} | {statistics.median(count_t):.1f} "
                    f"| {statistics.median(top_t):.1f} | {seen:,} |"
                )
                print(row, flush=True)
                lines.append(row)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(md.drop_all)
        await engine.dispose()
    out = os.path.join(HERE, "runs", f"{engine_name}-{len(paths)}.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"-> {out}", flush=True)


def _case_sensitive_like(dbapi_connection: Any, _record: Any) -> None:
    """vfs sets this pragma on every SQLite connection, so a prefix LIKE can use the path index."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA case_sensitive_like = ON")
    cursor.close()


def _sources(sources: Any, n: int) -> list[Any]:
    return list(sources) if isinstance(sources, list) else [sources] * n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres"])
    ap.add_argument("--tops", type=int, default=10)
    ap.add_argument("--folders", type=int, default=100)
    ap.add_argument("--files", type=int, default=50)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    asyncio.run(main(a.engine, a.tops, a.folders, a.files, a.reps))
