"""Which bind typing keeps non-ASCII paths, and what each canary costs under nvarchar binds.

Part 1 — per-canary cost: the shipped nvarchar form, a 64-element ASCII list
plus exactly one non-ASCII path at a time; reports the lock profile (a
table-level X means the seek range covered the table) and time.
Part 2 — the varchar bind (stock SQLAlchemy setinputsizes) on a database whose
default collation is UTF-8: does the lossy squeeze go away when the database,
not the column, is UTF-8? Creates `vfs_utf8` (COLLATE Latin1_General_100_BIN2_UTF8)
if missing and runs the varchar and nvarchar arms there.

    uv run python codepage_probe.py
"""

from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from common import CANARIES, Probe, canary_hits, synthetic_path


async def one(probe: Probe, session, label: str, values: list[str]) -> None:
    t = probe.tables
    marker = f"m{uuid4().hex[:8]}"
    stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.path.in_(values)).with_hint(t.entry, "WITH (UPDLOCK)", dialect_name="mssql").prefix_with(f"/* {marker} */")
    await session.connection(execution_options={"vfs_writer": True})
    t0 = time.perf_counter()
    rows = (await session.execute(stmt)).all()
    dt = (time.perf_counter() - t0) * 1000
    locks = {k: v for k, v in (await probe.locks(session)).items() if k.startswith(("KEY", "OBJECT"))}
    plan = await probe.plan(session, marker)
    print(f"| {label:34} | {len(rows):4} | {canary_hits(rows)} | {dt:7.0f} | {plan.shape if plan else '?'} params={plan.param_types if plan else '?'} | {locks} |", flush=True)
    await session.rollback()


async def part1() -> None:
    print("== part 1: one non-ASCII path in a 64-element nvarchar IN list (20k rows)")
    print("| list | found | canaries | ms | plan | locks |")
    print("|---|---|---|---|---|---|")
    async with Probe() as probe:
        await probe.grow(20_000)
        ascii63 = [synthetic_path(i) for i in range(63)]
        async with probe.session() as s:
            await one(probe, s, "64 ascii", ascii63 + [synthetic_path(63)])
        for c in CANARIES:
            async with probe.session() as s:
                await one(probe, s, f"63 ascii + {c!r}", sorted(ascii63 + [c]))
        async with probe.session() as s:
            await one(probe, s, "61 ascii + all three", sorted(ascii63[:61] + CANARIES))


async def part2() -> None:
    master = os.environ["VFS_TEST_MSSQL_URL"]
    eng = create_async_engine(master, isolation_level="AUTOCOMMIT")
    async with eng.connect() as c:
        await c.execute(text("IF DB_ID('vfs_utf8') IS NULL CREATE DATABASE vfs_utf8 COLLATE Latin1_General_100_BIN2_UTF8"))
        print("vfs_utf8 collation:", (await c.execute(text("SELECT DATABASEPROPERTYEX('vfs_utf8','Collation')"))).scalar())
    await eng.dispose()
    url = master.replace("/master?", "/vfs_utf8?")
    print("== part 2: varchar binds (stock SQLAlchemy, setinputsizes on) on a UTF-8-default database vs master (CP-1252)")
    print("| database / arm | found | canaries | ms | plan | locks |")
    print("|---|---|---|---|---|---|")
    for label, u in (("master CP-1252", master), ("vfs_utf8", url)):
        async with Probe(u) as probe:
            await probe.grow(20_000)
            stock = create_async_engine(u)
            try:
                async with AsyncSession(bind=stock) as s:
                    await one(probe, s, f"{label} / varchar (setinputsizes)", probe.paths(64))
                async with probe.session() as s:
                    await one(probe, s, f"{label} / nvarchar (vfs)", probe.paths(64))
            finally:
                await stock.dispose()


async def main() -> None:
    await part1()
    await part2()


asyncio.run(main())
