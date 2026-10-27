"""Spec 177 probe: what does SQLAlchemy raise when the connection dies at COMMIT, and how does vfs classify it today?"""

from __future__ import annotations

import asyncio
import sys
import tempfile

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vfs.storage.backends.database import DatabaseStorage


async def main():
    path = tempfile.mkdtemp() + "/probe.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine)
    async with factory() as s:
        await s.execute(text("create table t (x int)"))
        await s.commit()
    async with factory() as s:
        await s.execute(text("insert into t values (1)"))
        conn = await s.connection()
        raw = await conn.get_raw_connection()
        await raw.driver_connection.close()  # the link dies before COMMIT is sent
        try:
            await s.commit()
        except DBAPIError as exc:
            print("raised:", type(exc).__name__, "| orig:", type(exc.orig).__name__,
                  "| connection_invalidated:", exc.connection_invalidated)
            storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{path}")
            await storage.first_touch()
            err = storage._host.classify_failure(exc, context="write")
            print("classified today:", err.kind, "retryable:", err.retryable)
            await storage.close()
    async with factory() as s:
        print("rows after:", (await s.execute(text("select count(*) from t"))).scalar())
    await engine.dispose()


asyncio.run(main())
