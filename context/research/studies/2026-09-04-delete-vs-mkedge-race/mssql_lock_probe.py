"""R1: which MSSQL hint makes a rival delete wait behind the endpoint resolve?

Arms: plain (with_for_update, dropped by SQLAlchemy), UPDLOCK, UPDLOCK+HOLDLOCK,
REPEATABLEREAD (the shared-lock-held-to-commit spelling, the FOR KEY SHARE analogue).
Each arm: hold the lock in session A, launch B.delete, wait 3 s, report blocked or
not, then roll A back and let the delete finish (never cancel: aioodbc's thread
cannot be interrupted).
"""

import asyncio
import os
import sys
import time
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

ARMS = {
    "plain": None,
    "UPDLOCK": "WITH (UPDLOCK)",
    "UPDLOCK,HOLDLOCK": "WITH (UPDLOCK, HOLDLOCK)",
    "UPDLOCK,ROWLOCK": "WITH (UPDLOCK, ROWLOCK)",
    "REPEATABLEREAD": "WITH (REPEATABLEREAD)",
}


async def arm(url: str, name: str, hint: str | None) -> None:
    tn = f"vfs_{uuid4().hex[:10]}"
    a = DatabaseStorage(url=url, table_name=tn)
    b = DatabaseStorage(url=url, table_name=tn)
    try:
        await a.write(entries=[Entry(path=Path("/dst.py"), content="x")])
        t = a._host.tables
        stmt = select(t.entry.c.path, t.entry.c.entry_id).where(t.entry.c.path.in_(["/dst.py"]))
        stmt = stmt.with_hint(t.entry, hint, dialect_name="mssql") if hint else stmt.with_for_update()
        async with a._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            rows = (await session.execute(stmt)).all()
            assert rows
            iso = (await session.execute(text("SELECT CASE transaction_isolation_level WHEN 1 THEN 'RU' WHEN 2 THEN 'RC' WHEN 3 THEN 'RR' WHEN 4 THEN 'SER' WHEN 5 THEN 'SNAP' END FROM sys.dm_exec_sessions WHERE session_id = @@SPID"))).scalar()
            locks = (await session.execute(text("SELECT resource_type, request_mode, request_status, COUNT(*) FROM sys.dm_tran_locks WHERE request_session_id = @@SPID GROUP BY resource_type, request_mode, request_status"))).all()
            t0 = time.perf_counter()
            task = asyncio.ensure_future(b.delete(path=Path("/dst.py")))
            done, _ = await asyncio.wait([task], timeout=3.0)
            verdict = "BLOCKED" if not done else "PROCEEDED"
            await session.rollback()
            res = await task
            print(f"[{name:18}] iso={iso} delete {verdict} (finished after {time.perf_counter()-t0:.2f}s, success={res.success}) locks={[(r[0], r[1], r[2], r[3]) for r in locks]}")
    finally:
        await a.close()
        await b.close()
        eng = create_async_engine(url)
        async with eng.begin() as c:
            await c.run_sync(build_vfs_tables(table_name=tn).metadata.drop_all)
        await eng.dispose()


async def ensure_rcsi_db(master_url: str) -> str:
    eng = create_async_engine(master_url, isolation_level="AUTOCOMMIT")
    async with eng.connect() as c:
        await c.execute(text("IF DB_ID('vfs_rcsi') IS NULL CREATE DATABASE vfs_rcsi"))
        await c.execute(text("ALTER DATABASE vfs_rcsi SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE"))
        state = (await c.execute(text("SELECT is_read_committed_snapshot_on FROM sys.databases WHERE name='vfs_rcsi'"))).scalar()
        print("vfs_rcsi RCSI on:", state)
    await eng.dispose()
    return master_url.replace("/master?", "/vfs_rcsi?")


async def main() -> None:
    master_url = os.environ["VFS_TEST_MSSQL_URL"]
    urls = {"master (locking RC)": master_url}
    if "--rcsi" in sys.argv:
        urls["vfs_rcsi (RCSI)"] = await ensure_rcsi_db(master_url)
    for label, url in urls.items():
        print(f"=== {label}")
        for name, hint in ARMS.items():
            await arm(url, name, hint)


asyncio.run(main())
