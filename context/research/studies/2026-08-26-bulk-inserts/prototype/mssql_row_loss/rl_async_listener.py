"""Probe A: the original shape — SQLAlchemy async mssql+aioodbc, listener arms
cursor.fast_executemany on the bulk statement's own cursor, rows sent via
connection.exec_driver_sql(sql, list_of_tuples), paged."""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine

import rl_common as C

PAGES = [int(p) for p in sys.argv[1].split(",") if p] if len(sys.argv) > 1 and sys.argv[1] else [None]
SHAPE = sys.argv[2] if len(sys.argv) > 2 else "entry_nullfree"
N = int(sys.argv[3]) if len(sys.argv) > 3 else 300
RUNS = int(sys.argv[4]) if len(sys.argv) > 4 else 1


async def main() -> None:
    engine = create_async_engine(C.URL_ASYNC, use_setinputsizes=False)
    t = C.tables()
    seen: list[dict] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def arm(conn, cursor, statement, parameters, context, executemany):
        if executemany:
            cursor.fast_executemany = True

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, executemany):
        if executemany:
            impl = cursor._cursor._impl  # the real pyodbc cursor
            seen.append({"rowcount": cursor.rowcount, "n": len(parameters), "messages": list(getattr(impl, "messages", []) or [])})

    async with engine.begin() as conn:
        await conn.run_sync(t.metadata.drop_all)
        await conn.run_sync(t.metadata.create_all)
    for run in range(RUNS):
        for page_override in PAGES:
            seen.clear()
            if SHAPE.startswith("entry"):
                table = t.entry
                rows = [C.entry_row(i, SHAPE == "entry_nulls", prefix=f"/r{run}p{page_override}") for i in range(N)]
                key = "path"
            else:
                table = t.lex_postings
                rows = [C.block_row(i, epoch=1000 * run + (page_override or 0)) for i in range(N)]
                key = "term"
            sql, params, page, names = C.compiled(engine.dialect, table, rows)
            page = page_override or page
            error = None
            try:
                async with engine.begin() as conn:
                    for chunk in C.chunked(params, page):
                        await conn.exec_driver_sql(sql, list(chunk))
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:200]}"
            async with engine.connect() as conn:
                if key == "path":
                    landed = set((await conn.execute(select(table.c.path).where(table.c.path.like(f"/r{run}p{page_override}/%")))).scalars())
                    expected = {r["path"] for r in rows}
                else:
                    landed = set((await conn.execute(select(table.c.term).where(table.c.epoch == 1000 * run + (page_override or 0)))).scalars())
                    expected = {r["term"] for r in rows}
            missing = sorted(expected - landed, key=lambda s: int(s.rsplit("/", 1)[-1].lstrip("t")))
            C.record(probe="A-async-listener", shape=SHAPE, n=N, page=page, run=run, landed=len(landed), expected=N,
                     error=error, calls=seen, missing=missing[:400], ncols=len(names))
    async with engine.begin() as conn:
        await conn.run_sync(t.metadata.drop_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
