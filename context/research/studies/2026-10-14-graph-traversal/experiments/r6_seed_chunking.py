"""R6 experiment 4: 10,000 seeds in one call — chunked recursive CTE vs temp-table anchor vs frontier loop.

Run: cd /Users/claygendron/Git/Repos/vfs && uv run python <scratch>/experiments/r6_seed_chunking.py
"""

from __future__ import annotations

import random
import shutil

from sqlalchemy import Column, MetaData, String, Table, insert
from sqlalchemy.dialects import mssql, oracle, postgresql

from r6_common import (
    AUTHORED,
    DB,
    DB_10K,
    Edge,
    Entry,
    Path,
    StatementCounter,
    chunks_for,
    frontier_walk,
    live_entries,
    min_depth_select,
    open_storage,
    run,
    timed,
    walk_cte,
)
from vfs.models.rows import ULIDKey
from vfs.storage.backends.database.dialects import MARIADB, MSSQL, ORACLE, POSTGRESQL, chunked, membership_budget

BULK = 10_000
DEPTH = 2


def mariadb_dialect():
    try:
        from sqlalchemy.dialects.mysql.mariadb import MariaDBDialect

        return MariaDBDialect()
    except Exception:  # noqa: BLE001
        from sqlalchemy.dialects import mysql

        return mysql.dialect()


async def cte_chunked(storage, seeds, budget, depth=DEPTH):
    """One recursive-CTE statement per seed chunk; merge = min depth per node across chunks."""
    tables, profile = storage._host.tables, storage._host.profile
    merged: dict[str, int] = {}
    returned = 0
    async with storage._host.session_factory() as session:
        for chunk in chunked(seeds, budget):
            walk = walk_cte(tables, profile, chunk, "out", depth, edge_types=AUTHORED)
            found = (await session.execute(min_depth_select(walk))).all()
            returned += len(found)
            for node, d in found:
                if d < merged.get(node, 1 << 30):
                    merged[node] = d
    return merged, returned


async def main() -> None:
    shutil.copy(DB, DB_10K)
    storage = await open_storage(DB_10K)
    host = storage._host
    tables, profile = host.tables, host.profile

    entries = await live_entries(storage)
    core = sorted(m["path"] for m in entries.values() if m["kind"] == "file")
    bulk = [f"/bulk/{i // 500:02}/g{i:04}.py" for i in range(BULK)]
    with timed(f"write {BULK} bulk files in one call"):
        written = await storage.write(entries=[Entry(path=Path(p), content="# bulk\n") for p in bulk], parents=True)
    assert written.success, written.errors[:2]
    rng = random.Random(10_000)
    edges = []
    for p in bulk:
        edges.append(Edge(source=Path(p), target=Path(rng.choice(core)), edge_type="imports"))
        edges.append(Edge(source=Path(p), target=Path(rng.choice(bulk)), edge_type="references"))
    with timed(f"mkedge {len(edges)} edges in one call"):
        made = await storage.mkedge(edges=edges, provenance="user")
    assert made.success, made.errors[:2]
    entries = await live_entries(storage)
    seeds = sorted(i for i, m in entries.items() if m["path"].startswith("/bulk/") and m["kind"] == "file")
    print(f"graph: {len(entries)} live entries; seeds = the {len(seeds)} /bulk files; "
          f"each seed has one `imports` edge into the 2,000-file core and one `references` edge to another seed")

    print("\nSeed chunking by membership_budget(profile, parameter_budget) = min(in_list_budget, binds - 32):")
    print(f"    {'dialect':<11} {'binds (SQLAlchemy)':>18} {'in_list_budget':>15} {'membership_budget':>18} {'chunks for 10k':>15}")
    live = ("sqlite (live)", host.engine.dialect, profile)
    for name, dialect, prof in (
        live,
        ("postgresql", postgresql.dialect(), POSTGRESQL),
        ("mariadb", mariadb_dialect(), MARIADB),
        ("mssql", mssql.dialect(), MSSQL),
        ("oracle", oracle.dialect(), ORACLE),
    ):
        pb = dialect.insertmanyvalues_max_parameters
        mb = membership_budget(prof, pb)
        print(f"    {name:<11} {pb:>18} {prof.in_list_budget:>15} {mb:>18} {chunks_for(len(seeds), mb):>15}")

    counter = StatementCounter(storage)
    results = {}
    print(f"\nRecursive CTE per seed chunk, out, depth {DEPTH}, authored types (statements counted via before_cursor_execute):")
    print(f"    {'budget':<22} {'chunks':>6} {'statements':>10} {'rows returned':>13} {'distinct nodes':>14}")
    for label, budget in (("sqlite 32,668", host.membership_budget), ("mssql 2,000", 2_000), ("oracle 1,000", 1_000)):
        counter.clear()
        with timed(f"CTE per chunk @ {label}"):
            merged, returned = await cte_chunked(storage, seeds, budget)
        results[label] = merged
        print(f"    {label:<22} {chunks_for(len(seeds), budget):>6} {counter.count:>10} {returned:>13} {len(merged):>14}")
    first = next(iter(results.values()))
    print(f"    merged results identical across chunkings: {all(r == first for r in results.values())}")
    print(f"    sample statement prefixes: {sorted({s.split('(')[0][:40] for s in counter.statements})}")

    print("\nTemp-table anchor: CREATE TEMP TABLE + INSERT seeds + ONE walk statement (SQLite, through the backend's session)")
    meta = MetaData()
    seeds_t = Table("r6_seeds", meta, Column("node", ULIDKey(), primary_key=True), prefixes=["TEMPORARY"])
    counter.clear()
    async with host.session_factory() as session:
        conn = await session.connection()
        with timed("temp table create+insert+walk+drop"):
            await conn.run_sync(seeds_t.create)
            await session.execute(insert(seeds_t), [{"node": s} for s in seeds])
            walk = walk_cte(tables, profile, None, "out", DEPTH, edge_types=AUTHORED, anchor_rows=seeds_t)
            found = (await session.execute(min_depth_select(walk))).all()
            await conn.run_sync(seeds_t.drop)
        await session.rollback()
    temp_result = {n: d for n, d in found}
    kinds = [s.strip().split(" ", 1)[0] for s in counter.statements]
    print(f"    statements={counter.count} ({', '.join(kinds)}); rows returned={len(found)}; == chunked CTE: {temp_result == first}")
    print("    [NOT RUN: other engines] Postgres/MariaDB: CREATE TEMPORARY TABLE is per-session, one DDL + bulk INSERT; "
          "SQL Server: #temp tables likewise; Oracle: DDL commits the transaction and global temporary tables must be "
          "pre-created (18c+ private temp tables ORA$PTT_ exist). The seeds still cost one bind each on the INSERT, "
          "chunked by the bind budget, so the statement count is 1 + ceil(S / budget) + 1, never fewer than the IN-list form.")

    print(f"\nFrontier loop (one non-recursive statement per hop per frontier chunk), out, authored types:")
    print(f"    {'budget':<22} {'depth':>5} {'statements':>10} {'rows returned':>13} {'distinct nodes':>14} {'== CTE':>7}")
    for label, budget in (("sqlite 32,668", host.membership_budget), ("mssql 2,000", 2_000), ("oracle 1,000", 1_000)):
        for depth in (DEPTH, 4):
            counter.clear()
            got, work = await frontier_walk(storage, seeds, "out", depth, budget, edge_types=AUTHORED)
            check = got == first if depth == DEPTH else "-"
            print(f"    {label:<22} {depth:>5} {work['statements']:>10} {work['rows_returned']:>13} {len(got):>14} {check!s:>7}")
    print("\nRecursive CTE per chunk at depth 4 for the same budgets (statement count is depth-independent):")
    for label, budget in (("sqlite 32,668", host.membership_budget), ("mssql 2,000", 2_000), ("oracle 1,000", 1_000)):
        counter.clear()
        merged, returned = await cte_chunked(storage, seeds, budget, depth=4)
        print(f"    {label:<22} depth 4: statements={counter.count} rows returned={returned} distinct nodes={len(merged)}")
    counter.detach()
    await storage.close()


if __name__ == "__main__":
    run(main)
