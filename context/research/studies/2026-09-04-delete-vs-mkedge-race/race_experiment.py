"""Stage the delete-vs-mkedge race on the real engines.

Experiment A (per engine): freeze mkedge at the "mkedge:before-insert"
seam, run a genuine rival delete of the target endpoint through a second
DatabaseStorage on the same tables, let it commit, then resume mkedge.
Observe: both results, the end state (authored rows / trashed target),
whether reindex reclaims the stray, and what restore resurrects.

Experiment C (postgres only): does a rival delete's trash rewrite block
against FOR KEY SHARE / FOR UPDATE held on the entry row?
"""

import asyncio
import os
import sys
import traceback
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models import Edge, Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage, seams

ENGINES = [
    ("postgres", "VFS_TEST_POSTGRES_URL"),
    ("mariadb", "VFS_TEST_MARIADB_URL"),
    ("mssql", "VFS_TEST_MSSQL_URL"),
    ("oracle", "VFS_TEST_ORACLE_URL"),
]


async def authored_edges(storage):
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        rows = (
            await session.execute(
                select(tables.edges.c.source_id, tables.edges.c.target_id, tables.edges.c.edge_type).where(
                    tables.edges.c.edge_type != "fs"
                )
            )
        ).all()
    return [tuple(r) for r in rows]


async def entry_paths(storage):
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(tables.entry.c.path))).scalars().all()
    return sorted(rows)


async def run_engine(name, url):
    table_name = f"vfs_{uuid4().hex[:10]}"
    a = DatabaseStorage(url=url, table_name=table_name)
    b = DatabaseStorage(url=url, table_name=table_name)
    report = {"engine": name}
    try:
        w = await a.write(entries=[Entry(path=Path("/src.py"), content="x"), Entry(path=Path("/dst.py"), content="x")])
        assert w.success, w.errors

        delete_result = {}

        async def rival():
            try:
                res = await asyncio.wait_for(b.delete(path=Path("/dst.py")), timeout=30)
                delete_result["success"] = res.success
                delete_result["errors"] = [f"{e.kind}:{e.message[:80]}" for e in res.errors]
                obs = res.observations
                delete_result["trash_path"] = str(obs[0].trash_path) if obs and obs[0].trash_path else None
            except TimeoutError:
                delete_result["success"] = "TIMEOUT (blocked >30s)"

        edge = Edge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
        with seams.installed("mkedge:before-insert", rival):
            mk = await asyncio.wait_for(a.mkedge(edges=[edge]), timeout=60)
        report["rival_delete"] = delete_result
        report["mkedge"] = {
            "success": mk.success,
            "statuses": [o.status for o in mk.observations],
            "errors": [f"{e.kind}:{e.message[:80]}" for e in mk.errors],
        }
        report["stray_after_commit"] = await authored_edges(a)

        rx = await a.reindex()
        report["reindex_warnings"] = [f"{e.kind}:{e.message[:80]}" for e in rx.errors]
        report["stray_after_reindex"] = await authored_edges(a)

        if delete_result.get("trash_path"):
            rs = await b.restore(path=Path(delete_result["trash_path"]))
            report["restore_success"] = rs.success
            report["stray_after_restore"] = await authored_edges(a)
            rm = await a.rmedge(edges=[edge])
            report["rmedge_after_restore"] = (
                [o.status for o in rm.observations],
                [f"{e.kind}" for e in rm.errors],
            )
    except Exception:
        report["exception"] = traceback.format_exc()[-800:]
    finally:
        await a.close()
        await b.close()
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(build_vfs_tables(table_name=table_name).metadata.drop_all)
        finally:
            await engine.dispose()
    return report


async def lock_probe(url):
    """Postgres: does delete's trash rewrite block on KEY SHARE / FOR UPDATE?"""
    out = {}
    for mode, kwargs in [("FOR KEY SHARE", {"key_share": True}), ("FOR UPDATE", {})]:
        table_name = f"vfs_{uuid4().hex[:10]}"
        a = DatabaseStorage(url=url, table_name=table_name)
        b = DatabaseStorage(url=url, table_name=table_name)
        try:
            w = await a.write(entries=[Entry(path=Path("/dst.py"), content="x")])
            assert w.success
            tables = a._host.tables
            async with a._host.session_factory() as session:
                await session.connection(execution_options={"vfs_writer": True})
                held = (
                    await session.execute(
                        select(tables.entry.c.entry_id)
                        .where(tables.entry.c.path == "/dst.py")
                        .with_for_update(**kwargs)
                    )
                ).scalar_one()
                assert held
                try:
                    res = await asyncio.wait_for(b.delete(path=Path("/dst.py")), timeout=5)
                    out[mode] = f"delete proceeded (success={res.success})"
                except TimeoutError:
                    out[mode] = "delete BLOCKED behind the lock"
                await session.rollback()
        finally:
            await a.close()
            await b.close()
            engine = create_async_engine(url)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(build_vfs_tables(table_name=table_name).metadata.drop_all)
            finally:
                await engine.dispose()
    return out


async def main():
    for name, env in ENGINES:
        url = os.environ.get(env)
        if not url:
            print(f"== {name}: SKIP (no url)")
            continue
        print(f"== {name}")
        report = await run_engine(name, url)
        for k, v in report.items():
            if k != "engine":
                print(f"  {k}: {v}")
    pg = os.environ.get("VFS_TEST_POSTGRES_URL")
    if pg:
        print("== postgres lock probe")
        for k, v in (await lock_probe(pg)).items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
