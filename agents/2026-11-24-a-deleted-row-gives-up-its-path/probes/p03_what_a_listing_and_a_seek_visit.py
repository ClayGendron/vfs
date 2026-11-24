"""Probe 03: what a listing and a point seek visit when deleted rows share a parent and a path.

Three tables, one per key shape, each loaded twice over: a directory of 10 live files beside 4,000 deleted
ones, and one path that holds 1 live file and 10,000 deleted ones. On SQLite the count is virtual-machine
steps, from the progress handler. On Postgres it is the plan's node, the rows it produced, the rows a
filter removed and the buffers it touched, from ``EXPLAIN (ANALYZE, BUFFERS)``. Nothing is timed.

The last three queries find the newest deleted row at a path. Two carry a term on the row itself, which
visits every deleted row at the path. The third is driven by its list of targets and seeks once for each.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path as FsPath

import asyncpg

sys.path.insert(0, str(FsPath(__file__).parent))

from harness import POSTGRES_URL

COLUMNS = "id {pk}, parent_id TEXT, path TEXT NOT NULL, name TEXT NOT NULL, deleted_at BIGINT"
TRASHED_PATH = "CREATE INDEX {t}_trashed_path ON {t} (path, deleted_at) WHERE deleted_at IS NOT NULL"
GENERATION = COLUMNS + ", name_generation BIGINT NOT NULL DEFAULT 0, UNIQUE (path, name_generation), "
DDL = {
    "live_only": [
        "CREATE TABLE {t} (" + COLUMNS + ")",
        "CREATE UNIQUE INDEX {t}_live_children ON {t} (parent_id, name) WHERE deleted_at IS NULL",
        "CREATE UNIQUE INDEX {t}_live_path ON {t} (path) WHERE deleted_at IS NULL",
        TRASHED_PATH,
    ],
    "generation": ["CREATE TABLE {t} (" + GENERATION + "UNIQUE (parent_id, name_generation, name))", TRASHED_PATH],
    "generation_last": ["CREATE TABLE {t} (" + GENERATION + "UNIQUE (parent_id, name, name_generation))", TRASHED_PATH],
}
LIVE = {"live_only": "deleted_at IS NULL", "generation": "name_generation = 0", "generation_last": "name_generation = 0"}
NEWEST = (
    "e.id = (SELECT n.id FROM {t} n WHERE n.path = e.path AND n.deleted_at IS NOT NULL"
    " ORDER BY n.deleted_at DESC, n.id DESC LIMIT 1)"
)
QUERIES = {
    "list the 10 live children of a directory holding 4,000 deleted ones": (
        "SELECT name FROM {t} WHERE parent_id = 'dir' AND {live} ORDER BY name LIMIT 100"
    ),
    "seek the live row at a path holding 10,000 deleted ones": "SELECT id FROM {t} WHERE path = '/churn' AND {live}",
    "seek the newest deleted row at that path": (
        "SELECT id FROM {t} WHERE path = '/churn' AND deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT 1"
    ),
    "count the deleted rows at that path": "SELECT count(*) FROM {t} WHERE path = '/churn' AND deleted_at IS NOT NULL",
    "the newest deleted row at each of two named paths, one of them that path, by a term on the row": (
        "SELECT e.id FROM {t} e WHERE e.path IN ('/churn', '/dir/gone0007') AND e.deleted_at IS NOT NULL AND {newest}"
    ),
    "a trash page: the newest deleted row at each of the first 100 paths beneath the directory": (
        "SELECT e.path FROM {t} e WHERE e.path > '/dir/' AND e.path < '/dir0' AND e.deleted_at IS NOT NULL"
        " AND {newest} ORDER BY e.path LIMIT 100"
    ),
}
DRIVEN = (
    "WITH targets(p) AS (VALUES {rows}) SELECT (SELECT n.id FROM {t} n WHERE n.path = targets.p"
    " AND n.deleted_at IS NOT NULL ORDER BY n.deleted_at DESC, n.id DESC LIMIT 1) FROM targets"
)
DRIVEN_LABEL = "the newest deleted row at each of 1,000 named paths, one of them that path, one seek for each target"
DRIVEN_PATHS = ["/churn"] + [f"/dir/gone{i:04d}" for i in range(999)]


def rows() -> list[tuple[str | None, str, str, int | None]]:
    """(parent_id, path, name, deleted_at) for both loads, in insert order, so a row's position is its id."""
    out: list[tuple[str | None, str, str, int | None]] = []
    out += [("dir", f"/dir/live{i:02d}", f"live{i:02d}", None) for i in range(10)]
    out += [("dir", f"/dir/gone{i:04d}", f"gone{i:04d}", 1_000 + i) for i in range(4_000)]
    out += [("root", "/churn", "churn", 10_000 + i) for i in range(10_000)]
    out += [("root", "/churn", "churn", None)]
    out += [("other", f"/other/f{i:05d}", f"f{i:05d}", None) for i in range(20_000)]
    return out


def insert_sql(table: str, shape: str, marks: str) -> str:
    """The load's insert; a generation shape stamps a deleted row with a number of its own, as its id would."""
    if shape == "live_only":
        return f"INSERT INTO {table} (parent_id, path, name, deleted_at) VALUES ({marks})"
    last = "?" if "?" in marks else "$5"
    return f"INSERT INTO {table} (parent_id, path, name, deleted_at, name_generation) VALUES ({marks}, {last})"


def load(shape: str) -> list[tuple]:
    if shape == "live_only":
        return rows()
    return [(*row, 0 if row[3] is None else position) for position, row in enumerate(rows(), start=1)]


def on_sqlite() -> None:
    print("== SQLite", sqlite3.sqlite_version)
    for shape, ddl in DDL.items():
        conn = sqlite3.connect(":memory:")
        table = f"t_{shape}"
        for statement in ddl:
            conn.execute(statement.format(t=table, pk="INTEGER PRIMARY KEY AUTOINCREMENT"))
        conn.executemany(insert_sql(table, shape, "?, ?, ?, ?"), load(shape))
        conn.execute("ANALYZE")
        print(f" -- key shape {shape}")
        steps = [0]

        def tick(steps: list[int] = steps) -> int:
            steps[0] += 1
            return 0

        for label, query in QUERIES.items():
            sql = query.format(t=table, live=LIVE[shape], newest=NEWEST.format(t=table))
            plan = "; ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql))
            steps[0] = 0
            conn.set_progress_handler(tick, 1)
            returned = len(conn.execute(sql).fetchall())
            conn.set_progress_handler(None, 1)
            print(f"    {label}: rows={returned} vm_steps={steps[0]} plan={plan}")
        sql = DRIVEN.format(t=table, rows=", ".join("(?)" for _ in DRIVEN_PATHS))
        steps[0] = 0
        conn.set_progress_handler(tick, 1)
        found = [row[0] for row in conn.execute(sql, DRIVEN_PATHS)]
        conn.set_progress_handler(None, 1)
        hits = sum(1 for one in found if one is not None)
        print(f"    {DRIVEN_LABEL}: rows={len(found)} found={hits} vm_steps={steps[0]}")
        conn.close()


def leaf(node: dict) -> dict:
    while node.get("Plans"):
        node = node["Plans"][0]
    return node


async def on_postgres() -> None:
    if not POSTGRES_URL:
        print("VFS_PROBE_POSTGRES_URL is unset: the Postgres leg is skipped")
        return
    conn = await asyncpg.connect(POSTGRES_URL.replace("+asyncpg", ""))
    print("== Postgres", (await conn.fetchval("SHOW server_version")).split()[0])
    for shape, ddl in DDL.items():
        table = f"t_{shape}"
        await conn.execute(f"DROP TABLE IF EXISTS {table}")
        for statement in ddl:
            await conn.execute(statement.format(t=table, pk="BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"))
        await conn.executemany(insert_sql(table, shape, "$1, $2, $3, $4"), load(shape))
        await conn.execute(f"VACUUM ANALYZE {table}")
        print(f" -- key shape {shape}")
        for label, query in QUERIES.items():
            sql = query.format(t=table, live=LIVE[shape], newest=NEWEST.format(t=table))
            raw = await conn.fetchval("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql)
            plan = json.loads(raw)[0]["Plan"]
            node = leaf(plan)
            print(
                f"    {label}: rows={plan['Actual Rows']} node={node['Node Type']} index={node.get('Index Name')}"
                f" rows the node produced={node['Actual Rows']} removed by filter={node.get('Rows Removed by Filter', 0)}"
                f" buffers hit={plan['Shared Hit Blocks']}"
            )
        sql = DRIVEN.format(t=table, rows=", ".join(f"(${i}::text)" for i in range(1, len(DRIVEN_PATHS) + 1)))
        raw = await conn.fetchval("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, *DRIVEN_PATHS)
        plan = json.loads(raw)[0]["Plan"]
        print(f"    {DRIVEN_LABEL}: rows={plan['Actual Rows']} node={plan['Node Type']} buffers hit={plan['Shared Hit Blocks']}")
        await conn.execute(f"DROP TABLE {table}")
    await conn.close()


on_sqlite()
asyncio.run(on_postgres())
