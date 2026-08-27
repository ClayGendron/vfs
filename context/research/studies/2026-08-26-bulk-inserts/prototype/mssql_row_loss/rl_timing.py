"""Probe L: cost of the safe forms. 4,000 entry rows, three shapes, each run
three times on the async mssql+aioodbc engine the tree uses:
  core           session.execute(insert(entry), rows) -- the tree's pinned "core" mode (Core's multirow VALUES pages)
  core_fast      same statement on an engine created with fast_executemany=True (SQLAlchemy's documented mode)
  array_inline   listener arms cursor.fast_executemany; statement compiled .inline() (no OUTPUT); exec_driver_sql per 131-row page
"""
from __future__ import annotations

import asyncio
import time

from sqlalchemy import bindparam, event, func, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

import rl_common as C

N = 4000


async def timed(engine, t, shape, rep):
    prefix = f"/l-{shape}-{rep}"
    rows = [C.entry_row(i, False, prefix=prefix) for i in range(N)]
    t0 = time.perf_counter()
    if shape.startswith("array_inline"):
        sql, params, page, names = C.compiled(engine.dialect, t.entry, rows)
        if shape == "array_inline_onecall":
            page = N
        sql = str(insert(t.entry).values({n: bindparam(n) for n in names}).inline().compile(dialect=engine.dialect))
        async with engine.begin() as conn:
            for chunk in C.chunked(params, page):
                await conn.exec_driver_sql(sql, list(chunk))
    else:
        async with engine.begin() as conn:
            await conn.execute(insert(t.entry), rows)
    seconds = time.perf_counter() - t0
    async with engine.connect() as conn:
        landed = await conn.scalar(select(func.count()).select_from(t.entry).where(t.entry.c.path.like(f"{prefix}/%")))
    C.record(probe="L-timing", shape=shape, rep=rep, n=N, landed=landed, seconds=round(seconds, 3), us_per_row=round(seconds / N * 1e6, 1))


async def main() -> None:
    plain = create_async_engine(C.URL_ASYNC, use_setinputsizes=False)
    fast = create_async_engine(C.URL_ASYNC, use_setinputsizes=False, fast_executemany=True)
    armed = create_async_engine(C.URL_ASYNC, use_setinputsizes=False)

    @event.listens_for(armed.sync_engine, "before_cursor_execute")
    def arm(conn, cursor, statement, parameters, context, executemany):
        if executemany:
            cursor.fast_executemany = True

    t = C.tables()
    async with plain.begin() as conn:
        await conn.run_sync(t.metadata.drop_all)
        await conn.run_sync(t.metadata.create_all)
    for rep in range(3):
        await timed(plain, t, "core", rep)
        await timed(fast, t, "core_fast", rep)
        await timed(armed, t, "array_inline", rep)
        await timed(armed, t, "array_inline_onecall", rep)
    async with plain.begin() as conn:
        await conn.run_sync(t.metadata.drop_all)
    for e in (plain, fast, armed):
        await e.dispose()


if __name__ == "__main__":
    asyncio.run(main())
