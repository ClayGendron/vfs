"""R2d: where the IN-list plan flips seek->scan, and the KEY-lock profile when it seeks."""

import asyncio
import os
import re
import time
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import chunked

N = 20_000
LOCKS = text("SELECT resource_type, request_mode, COUNT(*) AS n FROM sys.dm_tran_locks WHERE request_session_id = @@SPID GROUP BY resource_type, request_mode")
PLAN = text("SELECT TOP 1 CAST(qp.query_plan AS nvarchar(max)) FROM sys.dm_exec_requests r CROSS APPLY sys.dm_exec_query_plan(r.plan_handle) qp WHERE r.session_id = @@SPID")


async def main() -> None:
    url = os.environ["VFS_TEST_MSSQL_URL"]
    tn = f"vfs_{uuid4().hex[:10]}"
    a = DatabaseStorage(url=url, table_name=tn)
    try:
        await a.mkdir(path=Path("/n"))
        assert (await a.write(entries=[Entry(path=Path(f"/n/{i:06d}.py"), content="x") for i in range(N)])).success
        t = a._host.tables
        all_paths = sorted(f"/n/{i:06d}.py" for i in range(N))
        print("== single statement, plan by IN-list size")
        for size in (64, 128, 256, 512, 1024, 1500, 2067):
            paths = all_paths[:size]
            stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.path.in_(paths)).with_hint(t.entry, "WITH (UPDLOCK)", dialect_name="mssql")
            async with a._host.session_factory() as session:
                await session.connection(execution_options={"vfs_writer": True})
                t0 = time.perf_counter()
                n = len((await session.execute(stmt)).all())
                dt = time.perf_counter() - t0
                locks = {(r.resource_type, r.request_mode): r.n for r in await session.execute(LOCKS)}
                sql_text = (await session.execute(text("SELECT TOP 1 st.text FROM sys.dm_exec_cached_plans cp CROSS APPLY sys.dm_exec_sql_text(cp.plan_handle) st CROSS APPLY sys.dm_exec_query_plan(cp.plan_handle) qp WHERE st.text LIKE '%FROM " + tn + " WITH (UPDLOCK)%' AND st.text NOT LIKE '%dm_exec%' ORDER BY cp.usecounts ASC, LEN(st.text) DESC"))).scalar()
                plan = (await session.execute(text("SELECT TOP 1 CAST(qp.query_plan AS nvarchar(max)) FROM sys.dm_exec_cached_plans cp CROSS APPLY sys.dm_exec_sql_text(cp.plan_handle) st CROSS APPLY sys.dm_exec_query_plan(cp.plan_handle) qp WHERE st.text LIKE '%FROM " + tn + " WITH (UPDLOCK)%' AND st.text NOT LIKE '%dm_exec%' AND LEN(st.text) BETWEEN " + str(len(str(stmt.compile(dialect=a._host.engine.dialect, compile_kwargs={"render_postcompile": True})))-200) + " AND " + str(len(str(stmt.compile(dialect=a._host.engine.dialect, compile_kwargs={"render_postcompile": True})))+200)))).scalar() or ""
                ops = [o for o in re.findall(r'PhysicalOp="([^"]+)"', plan) if "Scan" in o or "Seek" in o]
                print(f"  size={size:5} rows={n:5} {dt*1000:8.1f} ms plan={sorted(set(ops))} locks={sorted(locks.items())}")
                await session.rollback()
        print("== whole 20k batch in one transaction, chunk=500 (seek plans)")
        async with a._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            t0 = time.perf_counter()
            peak: dict[tuple[str, str], int] = {}
            k = 0
            for chunk in chunked(all_paths, 500):
                stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.path.in_(chunk)).with_hint(t.entry, "WITH (UPDLOCK)", dialect_name="mssql")
                (await session.execute(stmt)).all()
                k += 1
                if k % 8 == 0 or k == 40:
                    locks = {(r.resource_type, r.request_mode): r.n for r in await session.execute(LOCKS)}
                    for key, v in locks.items():
                        peak[key] = max(peak.get(key, 0), v)
            print(f"  {k} statements in {time.perf_counter()-t0:.1f}s; peak locks={sorted(peak.items())}; escalated={any(rt=='OBJECT' and m in ('U','X') for rt, m in peak)}")
            await session.rollback()
    finally:
        await a.close()
        eng = create_async_engine(url)
        async with eng.begin() as c:
            await c.run_sync(build_vfs_tables(table_name=tn).metadata.drop_all)
        await eng.dispose()


asyncio.run(main())
