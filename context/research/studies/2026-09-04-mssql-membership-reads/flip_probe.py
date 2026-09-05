"""Where the IN-list plan flips seek -> scan, by list size, table size, key and bind typing.

Arms (all under WITH (UPDLOCK), the mkedge guard's spelling):
  nvarchar        the vfs engine as shipped (setinputsizes off): path IN (@P nvarchar, ...), list holds the canaries
  nvarchar-ascii  the same with an all-ASCII list
  varchar         a stock SQLAlchemy engine (setinputsizes on): path IN (@P varchar, ...)
  cast            the vfs engine, raw SQL: path IN (CAST(@P COLLATE <utf8 bin2> AS varchar(1024)), ...)
  cast-forceseek  the cast form under WITH (UPDLOCK, FORCESEEK)
  forceseek       the nvarchar form under WITH (UPDLOCK, FORCESEEK)
  entry_id        the vfs engine: entry_id IN (@P varbinary(16), ...)
Each cell runs up to three times in fresh sessions (rolled back); cold = first
run (includes compile), warm = best of the rest. Canaries = how many of the
three non-ASCII paths the statement found (3 = lossless binds).

    uv run python flip_probe.py [--sizes 20000,200000,1000000] [--lists 64,...]
"""

from __future__ import annotations

import argparse
import asyncio
import time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from common import UTF8_BIN2, Probe, canary_hits


async def run_cell(probe: Probe, arm: str, k: int, engine2, runs: int = 3) -> str:
    t = probe.tables
    marker = f"m{uuid4().hex[:8]}"
    hint = "WITH (UPDLOCK, FORCESEEK)" if arm.endswith("forceseek") else "WITH (UPDLOCK)"
    if arm == "entry_id":
        values = probe.ulids(k)
        stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.entry_id.in_(values))
    else:
        values = probe.paths(k, canaries=arm != "nvarchar-ascii")
        stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.path.in_(values))
    stmt = stmt.with_hint(t.entry, hint, dialect_name="mssql").prefix_with(f"/* {marker} */")
    raw = None
    if arm.startswith("cast"):
        elems = ", ".join(f"CAST(? COLLATE {UTF8_BIN2} AS varchar(1024))" for _ in values)
        raw = f"SELECT /* {marker} */ path, entry_id FROM {probe.tn} {hint} WHERE path IN ({elems})"
    times: list[float] = []
    rows = 0
    hits = 0
    locks: dict[str, int] = {}
    plan = None
    for i in range(runs):
        if arm == "varchar":
            session = AsyncSession(bind=engine2)
        else:
            session = probe.session()
        async with session:
            await session.connection(execution_options={"vfs_writer": True})
            t0 = time.perf_counter()
            if raw is not None:
                conn = await session.connection()
                result = await conn.exec_driver_sql(raw, tuple(values))
            else:
                result = await session.execute(stmt)
            got = result.all()
            times.append(time.perf_counter() - t0)
            rows = len(got)
            hits = canary_hits(got) if arm != "entry_id" else -1
            if i == 0:
                locks = await probe.locks(session)
                plan = await probe.plan(session, marker)
            await session.rollback()
        if times[0] > 15:
            break
    cold = times[0] * 1000
    warm = min(times[1:]) * 1000 if len(times) > 1 else float("nan")
    key = {kk: v for kk, v in locks.items() if kk.startswith(("KEY", "OBJECT", "PAGE"))}
    line = f"| {probe.rows:>9,} | {arm:14} | {k:5} | {rows:5} | {hits:2} | {cold:9.0f} | {warm:9.0f} | {plan} | {key} |"
    print(line, flush=True)
    return plan.shape.split(":")[0] if plan else "?", times[0]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="20000,200000,1000000")
    ap.add_argument("--lists", default="64,256,512,768,1024,1280,1536,2067")
    ap.add_argument("--arms", default="nvarchar,nvarchar-ascii,varchar,cast,cast-forceseek,forceseek,entry_id")
    args = ap.parse_args()
    sizes = [int(x) for x in args.sizes.split(",")]
    lists = [int(x) for x in args.lists.split(",")]
    arms = args.arms.split(",")
    async with Probe() as probe:
        engine2 = create_async_engine(probe.url)  # stock SQLAlchemy: setinputsizes on -> varchar binds
        try:
            print(f"table {probe.tn}")
            print("| rows | arm | list | found | canaries | cold ms | warm ms | plan | locks |")
            print("|---|---|---|---|---|---|---|---|---|")
            for n in sizes:
                secs = await probe.grow(n)
                print(f"grew to {probe.rows:,} rows in {secs:.0f}s", flush=True)
                for arm in arms:
                    for k in lists:
                        shape, cold = await run_cell(probe, arm, k, engine2)
                        if (shape == "SCAN" and cold > 20) or cold > 60:
                            print(f"| {probe.rows:>9,} | {arm:14} | >{k} | skipped: {shape} already {cold:.0f}s |", flush=True)
                            break
        finally:
            await engine2.dispose()


asyncio.run(main())
