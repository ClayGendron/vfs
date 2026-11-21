"""Drain ls and tree pages on Postgres under three index shapes; count rows each scan node visited."""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import asyncpg

SHAPES = {
    "today": [],
    "composite": [
        "CREATE INDEX ix_probe_parent_live_name ON vfs_entries (parent_id, deleted_at, name)",
        "CREATE INDEX ix_probe_deleted_path ON vfs_entries (deleted_at, path)",
    ],
    "partial": [
        "CREATE INDEX ix_probe_live_children ON vfs_entries (parent_id, name) WHERE deleted_at IS NULL",
        "CREATE INDEX ix_probe_live_path ON vfs_entries (path) WHERE deleted_at IS NULL",
    ],
}
COLUMNS = "path, name, kind, mime_type, content_hash, size_bytes, created_at, updated_at, deleted_at, entry_id"
META = "AND path <> '/.vfs' AND path NOT LIKE '/.vfs/%'"


def scans(node: dict) -> list[dict]:
    found = [node] if "Scan" in node["Node Type"] else []
    for child in node.get("Plans", []):
        found += scans(child)
    return found


async def explain(con: asyncpg.Connection, sql: str, *args: object) -> tuple[int, int, str]:
    raw = await con.fetchval("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, *args)
    plan = json.loads(raw)[0]["Plan"]
    nodes = scans(plan)
    visited = sum(n["Actual Rows"] + n.get("Rows Removed by Filter", 0) for n in nodes)
    rows = plan["Actual Rows"]
    names = ",".join(f"{n['Node Type']}:{n.get('Index Name', '-')}" for n in nodes)
    return rows, visited, names


async def drain_ls(con: asyncpg.Connection, parent: str, limit: int) -> str:
    pid = await con.fetchval("SELECT entry_id FROM vfs_entries WHERE path = $1", parent)
    after = None
    visited: list[int] = []
    total = 0
    plans: set[str] = set()
    while True:
        if after is None:
            sql = f"SELECT {COLUMNS} FROM vfs_entries WHERE parent_id = $1 AND deleted_at IS NULL {META} ORDER BY name LIMIT $2"
            args = (pid, limit + 1)
            rows = await con.fetch(sql, *args)
        else:
            sql = f"SELECT {COLUMNS} FROM vfs_entries WHERE parent_id = $1 AND deleted_at IS NULL {META} AND name > $3 ORDER BY name LIMIT $2"
            args = (pid, limit + 1, after)
            rows = await con.fetch(sql, *args)
        _n, seen, names = await explain(con, sql, *args)
        visited.append(seen)
        plans.add(names)
        total += min(len(rows), limit)
        if len(rows) <= limit:
            return f"rows={total} pages={len(visited)} visited={visited[:3]}..{visited[-1]} plans={sorted(plans)}"
        after = rows[limit - 1]["name"]


async def drain_tree(con: asyncpg.Connection, root: str, limit: int) -> str:
    after = root
    visited: list[int] = []
    total = 0
    plans: set[str] = set()
    while True:
        sql = (
            f"SELECT {COLUMNS} FROM vfs_entries WHERE path LIKE $4 AND path > $1 AND path < $2 "
            f"AND deleted_at IS NULL {META} ORDER BY path LIMIT $3"
        )
        args = (after, root + "0", limit + 1, root + "/%")
        rows = await con.fetch(sql, *args)
        _n, seen, names = await explain(con, sql, *args)
        visited.append(seen)
        plans.add(names)
        total += min(len(rows), limit)
        if len(rows) <= limit:
            return f"rows={total} pages={len(visited)} visited={visited[:3]}..{visited[-1]} plans={sorted(plans)}"
        after = rows[limit - 1]["path"]


async def main() -> None:
    con = await asyncpg.connect(host="/var/lib/postgresql", port=55432, user="postgres", database="postgres")
    await con.execute(pathlib.Path(sys.argv[1]).read_text())
    for shape, ddl in SHAPES.items():
        for statement in ddl:
            await con.execute(statement)
        await con.execute("ANALYZE vfs_entries")
        print(f"--- {shape} ---")
        for parent, limit in (("/big", 1000), ("/d", 10), ("/s", 10)):
            print(f"ls {parent} limit={limit}: {await drain_ls(con, parent, limit)}")
        for root, limit in (("/s", 10), ("/big", 1000), ("/d", 10)):
            print(f"tree {root} limit={limit}: {await drain_tree(con, root, limit)}")
        sizes = await con.fetch(
            "SELECT indexrelname, pg_relation_size(indexrelid) AS bytes FROM pg_stat_user_indexes "
            "WHERE indexrelname LIKE 'ix_probe%' ORDER BY 1"
        )
        print("   sizes:", {row["indexrelname"]: row["bytes"] for row in sizes})
        for statement in ddl:
            await con.execute("DROP INDEX " + statement.split()[2])
    await con.close()


asyncio.run(main())
