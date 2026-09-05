"""Can a table-valued parameter reach SQL Server through aioodbc/pyodbc from ad hoc SQL?

Tries the pyodbc TVP conventions against a user-defined table type
(`CREATE TYPE ... AS TABLE (path varchar(1024) COLLATE utf8 PRIMARY KEY)`):
rows only, a leading [schema, type] list, and a stored procedure with a
READONLY parameter. Reports which form runs, the plan, canaries and locks.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from common import UTF8_BIN2, Probe, canary_hits


async def attempt(probe: Probe, label: str, sql: str, params: tuple) -> None:
    marker = sql.split("/* ")[1].split(" */")[0]
    async with probe.session() as s:
        await s.connection(execution_options={"vfs_writer": True})
        conn = await s.connection()
        t0 = time.perf_counter()
        try:
            rows = (await conn.exec_driver_sql(sql, params)).all()
        except Exception as exc:  # noqa: BLE001
            print(f"| {label:40} | ERROR: {str(exc)[:150]} |", flush=True)
            await s.rollback()
            return
        dt = (time.perf_counter() - t0) * 1000
        locks = {k: v for k, v in (await probe.locks(s)).items() if k.startswith(("KEY", "OBJECT"))}
        plan = await probe.plan(s, marker)
        print(f"| {label:40} | {len(rows)} | {canary_hits(rows)} | {dt:.0f} ms | {plan.shape if plan else '?'} est={plan.est_rows if plan else '?'} compile={plan.compile_ms if plan else '?'} | {locks} |", flush=True)
        await s.rollback()


async def main() -> None:
    async with Probe() as probe:
        await probe.grow(20_000)
        tn, typ = probe.tn, f"{probe.tn}_paths"
        async with probe.session() as s:
            conn = await s.connection()
            await conn.exec_driver_sql(f"CREATE TYPE {typ} AS TABLE (path varchar(1024) COLLATE {UTF8_BIN2} NOT NULL PRIMARY KEY)")
            await conn.exec_driver_sql(f"CREATE PROCEDURE {tn}_lock @keys {typ} READONLY AS SELECT /* mproc */ e.path, e.entry_id FROM {tn} e WITH (UPDLOCK) JOIN @keys k ON k.path = e.path")
            await s.commit()
        try:
            print("| form | found | canaries | ms | plan | locks |")
            print("|---|---|---|---|---|---|")
            values = probe.paths(2067)
            rows = [(v,) for v in values]
            m = lambda: f"m{uuid4().hex[:8]}"  # noqa: E731
            await attempt(probe, "ad hoc JOIN ?, rows only", f"SELECT /* {m()} */ e.path, e.entry_id FROM {tn} e WITH (UPDLOCK) JOIN ? AS k ON k.path = e.path", (rows,))
            # pyodbc's documented convention: the type name and schema as two leading strings.
            await attempt(probe, "ad hoc JOIN ?, [type, schema] + rows", f"SELECT /* {m()} */ e.path, e.entry_id FROM {tn} e WITH (UPDLOCK) JOIN ? AS k ON k.path = e.path", ([typ, "dbo"] + rows,))
            await attempt(probe, "sp_executesql READONLY param, [type, schema] + rows", f"EXEC sp_executesql N'SELECT /* {m()} */ e.path, e.entry_id FROM {tn} e WITH (UPDLOCK) JOIN @keys k ON k.path = e.path', N'@keys {typ} READONLY', @keys = ?", ([typ, "dbo"] + rows,))
            await attempt(probe, "sp_executesql, rows only", f"EXEC sp_executesql N'SELECT /* {m()} */ e.path, e.entry_id FROM {tn} e WITH (UPDLOCK) JOIN @keys k ON k.path = e.path', N'@keys {typ} READONLY', @keys = ?", (rows,))
            await attempt(probe, "stored procedure {CALL}", f"{{CALL {tn}_lock (?)}} /* mproc */", (rows,))
            await attempt(probe, "stored procedure EXEC", f"EXEC {tn}_lock ? /* mproc */", (rows,))
        finally:
            async with probe.session() as s:
                conn = await s.connection()
                await conn.exec_driver_sql(f"DROP PROCEDURE {tn}_lock")
                await conn.exec_driver_sql(f"DROP TYPE {typ}")
                await s.commit()


asyncio.run(main())
