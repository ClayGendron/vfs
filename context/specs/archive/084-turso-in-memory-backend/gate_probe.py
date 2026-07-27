"""Reduced gate probe — characterize items (a)-(e) past the two adapter blockers.

Shims: has_stop class attribute; isolation_level set through the private
driver connection (both are triage evidence, not shippable fixes).
"""

from __future__ import annotations

import asyncio
import time
import traceback

from sqlalchemy import Column, Integer, MetaData, String, Table, event, insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from turso.sqlalchemy.dialect import AsyncAdapt_turso_dbapi

URL = "sqlite+aioturso:///:memory:"

if not hasattr(AsyncAdapt_turso_dbapi, "has_stop"):
    AsyncAdapt_turso_dbapi.has_stop = False
    print("[shim] AsyncAdapt_turso_dbapi.has_stop = False")


def banner(label: str) -> None:
    print(f"\n=== {label} ===")


def install_listener(sync_engine) -> None:
    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(dbapi_connection, _record, _proxy) -> None:
        # The public recipe fails (no isolation_level on the adapter);
        # reach the driver connection to keep probing.
        try:
            dbapi_connection.isolation_level = None
            print("[checkout] public isolation_level assignment worked")
        except AttributeError:
            inner = getattr(dbapi_connection, "_connection", None)
            print(f"[checkout] public assignment failed; inner={type(inner).__name__}")
            if inner is not None:
                try:
                    inner.isolation_level = None
                    print("[checkout] inner isolation_level = None worked")
                except Exception as exc:
                    print(f"[checkout] inner assignment failed: {type(exc).__name__}: {exc}")

    @event.listens_for(sync_engine, "begin")
    def _on_begin(conn) -> None:
        options = conn.get_execution_options()
        if options.get("vfs_no_begin"):
            return
        mode = "BEGIN IMMEDIATE" if options.get("vfs_writer") else "BEGIN"
        conn.exec_driver_sql(mode)


async def item_a() -> None:
    banner("(a) engine + BEGIN IMMEDIATE")
    t0 = time.perf_counter()
    try:
        engine = create_async_engine(URL)
        print(f"dialect.name={engine.dialect.name!r} driver={engine.dialect.driver!r}")
        print(f"default pool class for :memory:: {type(engine.pool).__name__}")
        install_listener(engine.sync_engine)
        async with engine.connect() as conn:
            conn2 = await conn.execution_options(vfs_writer=True)
            got = (await conn2.execute(text("SELECT 1"))).scalar()
            print(f"SELECT 1 under writer BEGIN -> {got}")
            await conn2.commit()
        await engine.dispose()
        print(f"done ({time.perf_counter() - t0:.3f}s)")
    except Exception:
        traceback.print_exc()


async def item_a2() -> None:
    banner("(a2) raw BEGIN IMMEDIATE parse, no listener")
    try:
        engine = create_async_engine(URL)
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.exec_driver_sql("CREATE TABLE bi (x INTEGER)")
            await conn.exec_driver_sql("COMMIT")
            print("BEGIN IMMEDIATE ... COMMIT parsed and ran")
        await engine.dispose()
    except Exception:
        traceback.print_exc()


async def item_b() -> None:
    banner("(b) pooled :memory: sharing")
    try:
        engine = create_async_engine(URL)
        print(f"pool: {type(engine.pool).__name__}")
        async with engine.connect() as c1:
            await c1.exec_driver_sql("CREATE TABLE t_shared (x INTEGER)")
            await c1.exec_driver_sql("INSERT INTO t_shared VALUES (42)")
            await c1.commit()
        async with engine.connect() as c2:
            try:
                got = (await c2.execute(text("SELECT x FROM t_shared"))).scalar()
                print(f"second checkout sees -> {got}")
            except Exception as exc:
                print(f"second checkout: {type(exc).__name__}: {exc}")

        async def reader() -> str:
            async with engine.connect() as c:
                try:
                    return f"sees {(await c.execute(text('SELECT x FROM t_shared'))).scalar()}"
                except Exception as exc:
                    return f"{type(exc).__name__}: {exc}"

        print(f"two concurrent checkouts: {await asyncio.gather(reader(), reader())}")
        await engine.dispose()
    except Exception:
        traceback.print_exc()
    try:
        engine2 = create_async_engine(URL, poolclass=StaticPool)
        async with engine2.connect() as c1:
            await c1.exec_driver_sql("CREATE TABLE t2 (x INTEGER)")
            await c1.exec_driver_sql("INSERT INTO t2 VALUES (7)")
            await c1.commit()
        async with engine2.connect() as c2:
            print(f"StaticPool second checkout sees -> {(await c2.execute(text('SELECT x FROM t2'))).scalar()}")
        await engine2.dispose()
    except Exception:
        print("StaticPool arm:")
        traceback.print_exc()


async def item_c() -> None:
    banner("(c) pragmas on :memory:")
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        for stmt in (
            "PRAGMA page_size = 16384",
            "PRAGMA journal_mode = WAL",
            "PRAGMA busy_timeout = 5000",
            "PRAGMA synchronous = FULL",
            "PRAGMA case_sensitive_like = ON",
        ):
            try:
                res = await conn.exec_driver_sql(stmt)
                try:
                    rows = res.fetchall()
                except Exception:
                    rows = "<no rows>"
                print(f"{stmt!r} -> ok, rows={rows}")
            except Exception as exc:
                print(f"{stmt!r} -> {type(exc).__name__}: {exc}")
    await engine.dispose()


async def item_d() -> None:
    banner("(d) dialect facts")
    engine = create_async_engine(URL)
    d = engine.dialect
    for attr in (
        "insertmanyvalues_max_parameters",
        "use_insertmanyvalues",
        "supports_multivalues_insert",
        "update_returning",
        "insert_returning",
        "delete_returning",
    ):
        print(f"{attr} = {getattr(d, attr, None)}")
    await engine.dispose()


async def item_e() -> None:
    banner("(e) SAVEPOINT + RETURNING")
    metadata = MetaData()
    t = Table("probe_e", metadata, Column("id", Integer, primary_key=True), Column("val", String))
    engine = create_async_engine(URL, poolclass=StaticPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            conn = await session.connection()
            await conn.run_sync(metadata.create_all)
            await conn.execute(insert(t).values(id=1, val="a"))
            try:
                async with conn.begin_nested():
                    await conn.execute(insert(t).values(id=2, val="b"))
                print("begin_nested commit -> ok")
            except Exception as exc:
                print(f"begin_nested commit -> {type(exc).__name__}: {exc}")
            try:
                sp = await conn.begin_nested()
                await conn.execute(insert(t).values(id=3, val="c"))
                await sp.rollback()
                rows = (await conn.execute(select(t.c.id))).scalars().all()
                print(f"savepoint rollback -> rows {rows} (expect [1, 2])")
            except Exception as exc:
                print(f"savepoint rollback -> {type(exc).__name__}: {exc}")
            try:
                res = await conn.execute(update(t).where(t.c.id == 1).values(val="z").returning(t.c.id, t.c.val))
                print(f"UPDATE..RETURNING -> {res.fetchall()}")
            except Exception as exc:
                print(f"UPDATE..RETURNING -> {type(exc).__name__}: {exc}")
            await session.commit()
    finally:
        await engine.dispose()


async def main() -> None:
    t0 = time.perf_counter()
    await item_a()
    await item_a2()
    await item_b()
    await item_c()
    await item_d()
    await item_e()
    print(f"\ntotal: {time.perf_counter() - t0:.3f}s")


if __name__ == "__main__":
    asyncio.run(main())
