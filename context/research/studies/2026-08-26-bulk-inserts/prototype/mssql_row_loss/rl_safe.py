"""Probe K: the safe forms and the remaining mechanism check.
  inline_bare      bare pyodbc, statement compiled with .inline() (no OUTPUT), 300 and 1000 rows in one call
  output_packet    bare pyodbc, the OUTPUT statement, with SQL_ATTR_PACKET_SIZE 4096 vs 32767 (does the loss threshold scale?)
  core_sync        SQLAlchemy sync mssql+pyodbc create_engine(fast_executemany=True): conn.execute(insert(entry), rows) -- the documented path
  core_async       SQLAlchemy async mssql+aioodbc create_async_engine(fast_executemany=True), same
  listener_inline  the original async shape (listener arms the cursor) with the inline-compiled statement -- the fixed array mode
"""
from __future__ import annotations

import asyncio

import pyodbc
from sqlalchemy import bindparam, create_engine, event, func, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

import rl_common as C

SQL_ATTR_PACKET_SIZE = 112  # ODBC connection attribute; pyodbc exports no name for it


def inline_sql(dialect, table, names):
    return str(insert(table).values({n: bindparam(n) for n in names}).inline().compile(dialect=dialect))


def count(conn_exec, table, prefix):
    return conn_exec(select(func.count()).select_from(table).where(table.c.path.like(f"{prefix}/%")))


def bare(engine, t, n, prefix, sql_kind, packet=None):
    rows = [C.entry_row(i, False, prefix=prefix) for i in range(n)]
    sql, params, _, names = C.compiled(engine.dialect, t.entry, rows)
    if sql_kind == "inline":
        sql = inline_sql(engine.dialect, t.entry, names)
    kw = {"attrs_before": {SQL_ATTR_PACKET_SIZE: packet}} if packet else {}
    conn = pyodbc.connect(C.ODBC, autocommit=False, **kw)
    got_packet = packet
    error = None
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(sql, params)
        cur.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    conn.commit()
    landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {t.entry.name} WHERE path LIKE '{prefix}/%'").fetchval()
    conn.commit()
    conn.close()
    return landed, error, sql.split("VALUES")[0][-40:], got_packet


async def main() -> None:
    sync_engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(sync_engine)
    t.metadata.create_all(sync_engine)

    for n in (300, 1000):
        landed, error, tail, _ = bare(sync_engine, t, n, f"/k-inline-{n}", "inline")
        C.record(probe="K-safe", case="inline_bare", n=n, page=n, landed=landed, error=error, sql_tail=tail)
    for packet in (4096, 8192, 16384, 32767):
        landed, error, tail, got = bare(sync_engine, t, 1000, f"/k-pkt-{packet}", "output", packet=packet)
        C.record(probe="K-safe", case="output_packet", n=1000, page=1000, packet_requested=packet, packet_negotiated=got, landed=landed, error=error, sql_tail=tail)

    for setinputsizes in (False, True):
        eng = create_engine(C.URL_SYNC, fast_executemany=True, use_setinputsizes=setinputsizes)
        for n in (300, 1000):
            prefix = f"/k-core-sync-{setinputsizes}-{n}"
            rows = [C.entry_row(i, False, prefix=prefix) for i in range(n)]
            error, seen = None, []

            @event.listens_for(eng, "before_cursor_execute")
            def spy(conn, cursor, statement, parameters, context, executemany, seen=seen):
                if executemany:
                    seen.append((statement.split("VALUES")[0][-30:], len(parameters), cursor.fast_executemany))

            try:
                with eng.begin() as conn:
                    conn.execute(insert(t.entry), rows)
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:200]}"
            with eng.connect() as conn:
                landed = conn.scalar(select(func.count()).select_from(t.entry).where(t.entry.c.path.like(f"{prefix}/%")))
            C.record(probe="K-safe", case="core_sync_fast_executemany", use_setinputsizes=setinputsizes, n=n, landed=landed, error=error, executemany_calls=seen)
        eng.dispose()

    aeng = create_async_engine(C.URL_ASYNC, fast_executemany=True, use_setinputsizes=False)
    for n in (300, 1000):
        prefix = f"/k-core-async-{n}"
        rows = [C.entry_row(i, False, prefix=prefix) for i in range(n)]
        error, seen = None, []

        @event.listens_for(aeng.sync_engine, "before_cursor_execute")
        def spy2(conn, cursor, statement, parameters, context, executemany, seen=seen):
            if executemany:
                seen.append((statement.split("VALUES")[0][-30:], len(parameters), cursor.fast_executemany))

        try:
            async with aeng.begin() as conn:
                await conn.execute(insert(t.entry), rows)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
        async with aeng.connect() as conn:
            landed = await conn.scalar(select(func.count()).select_from(t.entry).where(t.entry.c.path.like(f"{prefix}/%")))
        C.record(probe="K-safe", case="core_async_fast_executemany", n=n, landed=landed, error=error, executemany_calls=seen)
    await aeng.dispose()

    leng = create_async_engine(C.URL_ASYNC, use_setinputsizes=False)

    @event.listens_for(leng.sync_engine, "before_cursor_execute")
    def arm(conn, cursor, statement, parameters, context, executemany):
        if executemany:
            cursor.fast_executemany = True

    for n in (300, 1000, 5000):
        prefix = f"/k-listener-inline-{n}"
        rows = [C.entry_row(i, False, prefix=prefix) for i in range(n)]
        sql, params, page, names = C.compiled(leng.dialect, t.entry, rows)
        sql = inline_sql(leng.dialect, t.entry, names)
        error = None
        try:
            async with leng.begin() as conn:
                for chunk in C.chunked(params, page):
                    await conn.exec_driver_sql(sql, list(chunk))
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
        async with leng.connect() as conn:
            landed = await conn.scalar(select(func.count()).select_from(t.entry).where(t.entry.c.path.like(f"{prefix}/%")))
        C.record(probe="K-safe", case="listener_inline", n=n, page=page, landed=landed, error=error, sql_tail=sql.split("VALUES")[0][-40:])
    await leng.dispose()
    t.metadata.drop_all(sync_engine)
    sync_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
