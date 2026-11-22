"""Which index keeps a listing page's read work bounded on SQLite: composite or partial.

Builds a database through vfs, then drains the page statements in plain SQL with every
index-usable term in SQL and one registered function as the only residual term, which
counts each row the index range hands over. Counts only; nothing is timed.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys

from vfs import AsyncVirtualFileSystem, SQLiteStorage
from vfs.authority import Authority
from vfs.models import Entry, Observation
from vfs.paths import Path

SYSTEM = Authority.system()
DB = sys.argv[1]

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


async def build() -> None:
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=DB))
    await fs.write([Entry(path=Path(f"/big/f{i:05d}.txt"), content="x") for i in range(10_000)], parents=True, authority=SYSTEM)
    await fs.write([Entry(path=Path(f"/d/f{i:05d}.txt"), content="x") for i in range(1_000)], parents=True, authority=SYSTEM)
    await fs.write([Entry(path=Path(f"/s/f{i:05d}.txt"), content="x") for i in range(1_000)], parents=True, authority=SYSTEM)
    await fs.delete(observations=[Observation(path=Path(f"/d/f{i:05d}.txt")) for i in range(900)], authority=SYSTEM)
    await fs.delete(
        observations=[Observation(path=Path(f"/s/f{i:05d}.txt")) for i in range(1_000) if i % 10], authority=SYSTEM
    )
    await fs.close()


def drain_ls(con: sqlite3.Connection, parent: str, limit: int) -> tuple[list[int], int, str]:
    pid = con.execute("SELECT entry_id FROM vfs_entries WHERE path = ?", (parent,)).fetchone()[0]
    visited: list[int] = []
    after = None
    total = 0
    plan = ""
    while True:
        counter = [0]
        con.create_function("seen", 0, lambda: counter.__setitem__(0, counter[0] + 1) or 1, deterministic=False)
        sql = (
            "SELECT name FROM vfs_entries WHERE parent_id = ? AND deleted_at IS NULL"
            + (" AND name > ?" if after else "")
            + " AND seen() ORDER BY name LIMIT ?"
        )
        args = (pid, after, limit + 1) if after else (pid, limit + 1)
        plan = " | ".join(row[3] for row in con.execute("EXPLAIN QUERY PLAN " + sql, args))
        rows = [row[0] for row in con.execute(sql, args)]
        visited.append(counter[0])
        page = rows[:limit]
        total += len(page)
        if len(rows) <= limit:
            return visited, total, plan
        after = page[-1]


def drain_tree(con: sqlite3.Connection, root: str, limit: int) -> tuple[list[int], int, str]:
    visited: list[int] = []
    after = root
    total = 0
    plan = ""
    while True:
        counter = [0]
        con.create_function("seen", 0, lambda: counter.__setitem__(0, counter[0] + 1) or 1, deterministic=False)
        sql = "SELECT path FROM vfs_entries WHERE deleted_at IS NULL AND path > ? AND path < ? AND seen() ORDER BY path LIMIT ?"
        args = (after, root + "0", limit + 1)
        plan = " | ".join(row[3] for row in con.execute("EXPLAIN QUERY PLAN " + sql, args))
        rows = [row[0] for row in con.execute(sql, args)]
        visited.append(counter[0])
        page = rows[:limit]
        total += len(page)
        if len(rows) <= limit:
            return visited, total, plan
        after = page[-1]


def main() -> None:
    asyncio.run(build())
    for shape, ddl in SHAPES.items():
        con = sqlite3.connect(DB)
        con.execute("PRAGMA case_sensitive_like = ON")
        for statement in ddl:
            con.execute(statement)
        con.execute("ANALYZE")
        print(f"--- {shape} ---")
        for parent, limit in (("/big", 1000), ("/d", 10), ("/s", 10)):
            visited, total, plan = drain_ls(con, parent, limit)
            print(f"ls {parent} limit={limit}: rows={total} pages={len(visited)} visited={visited[:3]}..{visited[-1]}")
            print(f"   plan: {plan}")
        for root, limit in (("/s", 10), ("/big", 1000)):
            visited, total, plan = drain_tree(con, root, limit)
            print(f"tree {root} limit={limit}: rows={total} pages={len(visited)} visited={visited[:3]}..{visited[-1]}")
            print(f"   plan: {plan}")
        for statement in ddl:
            con.execute("DROP INDEX " + statement.split()[2])
        con.commit()
        con.close()


main()
