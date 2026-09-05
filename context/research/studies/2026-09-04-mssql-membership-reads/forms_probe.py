"""Alternative membership forms on SQL Server: cost, plan, and lock profile under WITH (UPDLOCK).

The plan column is the *last* statement's plan (a remainder chunk may differ from the full chunks).
Every form resolves K sorted paths (three of them the non-ASCII canaries) to
(path, entry_id) inside one transaction, then reads the locks it holds and the
table's lock-promotion counters before rolling back. Forms:

  in-nvarchar-<n>   vfs as shipped: path IN (@P nvarchar, ...) chunked at n — ASCII list only: one
                    CJK element makes every statement a table-range seek (see codepage_probe.py)
  in-cast-<n>       raw: path IN (CAST(@P COLLATE utf8 AS varchar(1024)), ...) chunked at n
  in-cast-fs-<n>    the cast form with WITH (UPDLOCK, FORCESEEK)
  openjson-<n>      path IN (SELECT CAST(value COLLATE utf8 AS varchar(1024)) FROM OPENJSON(@json)), n paths per bind
  openjson-with     JOIN OPENJSON(@json) WITH (path varchar(1024) '$') — the code-page trap, canaries only
  values-<n>        JOIN (VALUES (@P),...) AS k(v) ON path = CAST(k.v COLLATE utf8 AS varchar(1024))
  values-fs-<n>     the same with FORCESEEK
  tvp               a user-defined table type + one TVP bind, via sp_executesql-style ad hoc SQL
  temp-<n>          CREATE TABLE #k, multirow INSERT pages of n (n <= 1000: INSERT ... VALUES caps at 1,000 rows), JOIN #k, DROP

    uv run python forms_probe.py [--sizes 20000,1000000] [--ks 2067,10000,20000] [--forms ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common import UTF8_BIN2, Probe, canary_hits
from vfs.storage.backends.database.dialects import chunked


def in_sql(tn: str, marker: str, n: int, hint: str, cast: bool) -> str:
    elem = f"CAST(? COLLATE {UTF8_BIN2} AS varchar(1024))" if cast else "?"
    return f"SELECT /* {marker} */ path, entry_id FROM {tn} {hint} WHERE path IN ({', '.join([elem] * n)})"


async def resolve(probe: Probe, session: AsyncSession, form: str, values: list[str], marker: str) -> tuple[list, int]:
    """Run *form* over *values*; return (rows, statements issued)."""
    tn = probe.tn
    t = probe.tables
    conn = await session.connection()
    name, _, arg = form.partition("-")
    parts = form.split("-")
    n = int(parts[-1]) if parts[-1].isdigit() else len(values)
    fs = "fs" in parts
    hint = "WITH (UPDLOCK, FORCESEEK)" if fs else "WITH (UPDLOCK)"
    rows: list = []
    stmts = 0
    if parts[0] == "in" and parts[1] == "nvarchar":
        for chunk in chunked(values, n):
            stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.path.in_(list(chunk))).with_hint(t.entry, hint, dialect_name="mssql").prefix_with(f"/* {marker} */")
            rows += (await session.execute(stmt)).all()
            stmts += 1
    elif parts[0] == "in":
        for chunk in chunked(values, n):
            rows += (await conn.exec_driver_sql(in_sql(tn, marker, len(chunk), hint, True), tuple(chunk))).all()
            stmts += 1
    elif parts[0] == "openjson" and parts[1:2] == ["with"]:
        sql = f"SELECT /* {marker} */ e.path, e.entry_id FROM {tn} e {hint} JOIN OPENJSON(?) WITH (path varchar(1024) '$') j ON j.path = e.path"
        rows += (await conn.exec_driver_sql(sql, (json.dumps(values),))).all()
        stmts += 1
    elif parts[0] == "openjson":
        sql = f"SELECT /* {marker} */ path, entry_id FROM {tn} {hint} WHERE path IN (SELECT CAST(j.value COLLATE {UTF8_BIN2} AS varchar(1024)) FROM OPENJSON(?) j)"
        for chunk in chunked(values, n):
            rows += (await conn.exec_driver_sql(sql, (json.dumps(list(chunk)),))).all()
            stmts += 1
    elif parts[0] == "values":
        for chunk in chunked(values, n):
            vals = ", ".join(["(?)"] * len(chunk))
            sql = f"SELECT /* {marker} */ e.path, e.entry_id FROM (VALUES {vals}) AS k(v) JOIN {tn} e {hint} ON e.path = CAST(k.v COLLATE {UTF8_BIN2} AS varchar(1024))"
            rows += (await conn.exec_driver_sql(sql, tuple(chunk))).all()
            stmts += 1
    elif parts[0] == "tvp":
        sql = f"SELECT /* {marker} */ e.path, e.entry_id FROM {tn} e {hint} JOIN ? AS k ON k.path = e.path"
        tvp = [("dbo", f"{tn}_paths")] + [(v,) for v in values]
        rows += (await conn.exec_driver_sql(sql, (tvp,))).all()
        stmts += 1
    elif parts[0] == "temp":
        await conn.exec_driver_sql(f"CREATE TABLE #k (path varchar(1024) COLLATE {UTF8_BIN2} NOT NULL PRIMARY KEY)")
        stmts += 1
        for chunk in chunked(values, n):
            await conn.exec_driver_sql(f"INSERT INTO #k (path) VALUES {', '.join(['(?)'] * len(chunk))}", tuple(chunk))
            stmts += 1
        rows += (await conn.exec_driver_sql(f"SELECT /* {marker} */ e.path, e.entry_id FROM {tn} e {hint} JOIN #k ON #k.path = e.path")).all()
        await conn.exec_driver_sql("DROP TABLE #k")
        stmts += 2
    else:
        raise ValueError(form)
    return rows, stmts


async def run_cell(probe: Probe, form: str, k: int, runs: int = 3) -> None:
    values = probe.paths(k, canaries=not form.startswith("in-nvarchar"))
    marker = f"m{uuid4().hex[:8]}"
    times: list[float] = []
    for i in range(runs):
        async with probe.session() as session:
            await session.connection(execution_options={"vfs_writer": True})
            before = await probe.promotions()
            t0 = time.perf_counter()
            try:
                rows, stmts = await resolve(probe, session, form, values, marker)
            except Exception as exc:  # noqa: BLE001 — a refused form is a finding
                print(f"| {probe.rows:>9,} | {form:16} | {k:6} | ERROR: {str(exc)[:160]} |", flush=True)
                await session.rollback()
                return
            times.append(time.perf_counter() - t0)
            if i == 0:
                locks = await probe.locks(session)
                plan = await probe.plan(session, marker)
                found, hits, nstmts = len(rows), canary_hits(rows), stmts
            await session.rollback()
            if i == 0:
                after = await probe.promotions()
        if times[0] > 20:
            break
    cold = times[0] * 1000
    warm = min(times[1:]) * 1000 if len(times) > 1 else float("nan")
    key = {kk: v for kk, v in locks.items() if kk.startswith(("KEY", "OBJECT"))}
    promo = (after[0] - before[0], after[1] - before[1])
    print(f"| {probe.rows:>9,} | {form:16} | {k:6} | {found:6} | {hits} | {nstmts:4} | {cold:8.0f} | {warm:8.0f} | {plan.shape if plan else '?'} abort={plan.early_abort if plan else '?'} compile={plan.compile_ms if plan else '?'}ms est={plan.est_rows if plan else '?'} | {key} | {promo} |", flush=True)


DEFAULT_FORMS = "in-nvarchar-512,in-nvarchar-2067,in-cast-512,in-cast-1000,in-cast-2067,in-cast-fs-2067,openjson-2067,openjson-10000,openjson-with,values-1000,values-2067,values-fs-2067,tvp,temp-1000"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="20000,1000000")
    ap.add_argument("--ks", default="2067,10000")
    ap.add_argument("--forms", default=DEFAULT_FORMS)
    args = ap.parse_args()
    async with Probe() as probe:
        async with probe.session() as s:
            conn = await s.connection()
            await conn.exec_driver_sql(f"CREATE TYPE {probe.tn}_paths AS TABLE (path varchar(1024) COLLATE {UTF8_BIN2} NOT NULL PRIMARY KEY)")
            await s.commit()
        try:
            print(f"table {probe.tn}")
            print("| rows | form | K | found | canaries | stmts | cold ms | warm ms | plan | locks | promotions (attempts, escalations) |")
            print("|---|---|---|---|---|---|---|---|---|---|---|")
            for n in [int(x) for x in args.sizes.split(",")]:
                secs = await probe.grow(n)
                print(f"grew to {probe.rows:,} rows in {secs:.0f}s", flush=True)
                for k in [int(x) for x in args.ks.split(",")]:
                    for form in args.forms.split(","):
                        if form == "openjson-with" and k != 2067:
                            continue
                        await run_cell(probe, form, k)
        finally:
            async with probe.session() as s:
                conn = await s.connection()
                await conn.exec_driver_sql(f"DROP TYPE {probe.tn}_paths")
                await s.commit()


asyncio.run(main())
