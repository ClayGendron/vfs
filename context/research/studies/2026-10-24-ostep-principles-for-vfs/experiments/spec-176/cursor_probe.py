"""Spec 176 probe: keyset pages over (parent_id, name) and over path, with tombstones in the range.

Counts pages, statements, rows returned, and rows the index range hands to
the row filter; never times. The SQLite file database is built through vfs
(10,000 children under /big; 1,000 under /d with the first 900 deleted;
1,000 under /s with 9 of every 10 deleted; 10 directories of 100 files under
/n), then probed with stdlib sqlite3 so one counting SQL function can be the
only residual term: every row the index range delivers calls it exactly
once. The access predicates stay plain SQL so the planner can use them.
The keyset statements mimic the spec's design; no vfs code is changed.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path as FsPath

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.storage.backends.database import DatabaseStorage

HERE = FsPath(sys.argv[1])
DB = HERE / "probe.sqlite"
COLS = "path, name, kind"


async def build() -> dict[str, int]:
    if DB.exists():
        DB.unlink()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = VirtualFileSystem(storage=storage)
    sysa = Authority.system()
    await storage.first_touch()
    await fs.write([Entry(path=f"/big/f{i:05}.txt", content=f"row {i}\n") for i in range(10_000)], parents=True, authority=sysa)
    await fs.write([Entry(path=f"/d/c{i:04}.txt", content=f"c {i}\n") for i in range(1_000)], parents=True, authority=sysa)
    await fs.write([Entry(path=f"/s/c{i:04}.txt", content=f"s {i}\n") for i in range(1_000)], parents=True, authority=sysa)
    await fs.write([Entry(path=f"/n/d{j:02}/f{i:03}.txt", content="x") for j in range(10) for i in range(100)], parents=True, authority=sysa)
    gone_d = await fs.delete(observations=[Observation(path=f"/d/c{i:04}.txt", kind="file") for i in range(900)], authority=sysa)
    gone_s = await fs.delete(observations=[Observation(path=f"/s/c{i:04}.txt", kind="file") for i in range(1_000) if i % 10], authority=sysa)
    assert gone_d.success and gone_s.success
    live = {p: len((await fs.ls(p, authority=sysa)).observations) for p in ("/big", "/d", "/s")}
    await fs.close()
    return live


class Keep:
    """The one residual term: counts every delivered row, then applies the non-index facts."""

    def __init__(self) -> None:
        self.n = 0
        self.root = "/"
        self.max_slashes: int | None = None
        self.check_live = True

    def __call__(self, path: str, deleted_at: object) -> int:
        self.n += 1
        if self.check_live and deleted_at is not None:
            return 0
        if path == "/.vfs" or path.startswith("/.vfs/"):
            return 0
        if self.max_slashes is not None and path.count("/") > self.max_slashes:
            return 0
        return 1


def plan(conn: sqlite3.Connection, sql: str, params: tuple) -> str:
    return " | ".join(row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def page_ls(conn, keep, parent_id, after, limit, composite):
    keep.check_live = not composite
    live = "AND deleted_at IS NULL" if composite else ""
    key = "AND name > ?" if after is not None else ""
    sql = f"SELECT {COLS} FROM vfs_entries WHERE parent_id = ? {live} {key} AND keep(path, deleted_at) ORDER BY name LIMIT ?"
    params = (parent_id, after, limit + 1) if after is not None else (parent_id, limit + 1)
    keep.n = 0
    return conn.execute(sql, params).fetchall(), keep.n, plan(conn, sql, params)


def page_tree(conn, keep, root, after, limit, composite):
    keep.check_live = not composite
    live = "AND deleted_at IS NULL" if composite else ""
    lower = after if after is not None else root + "/"
    sql = (
        f"SELECT {COLS} FROM vfs_entries WHERE path > ? AND path < ? {live} AND keep(path, deleted_at) "
        "ORDER BY path LIMIT ?"
    )
    params = (lower, root + "0", limit + 1)
    keep.n = 0
    return conn.execute(sql, params).fetchall(), keep.n, plan(conn, sql, params)


def drain(conn, keep, pager, anchor, limit, composite, out, label, max_slashes=None):
    keep.max_slashes = max_slashes
    after = None
    seen: list[str] = []
    visits: list[int] = []
    returned: list[int] = []
    plans: list[str] = []
    while True:
        rows, visited, how = pager(conn, keep, anchor, after, limit, composite)
        plans.append(how)
        more = len(rows) > limit
        page = rows[:limit]
        seen.extend(r[0] for r in page)
        visits.append(visited)
        returned.append(len(page))
        if not more:
            break
        after = page[-1][1] if pager is page_ls else page[-1][0]
    out.append(
        f"{label}: pages={len(visits)} statements_per_page=1 rows={len(seen)} distinct={len(set(seen))} "
        f"in_order={seen == sorted(seen)} returned_per_page={returned} visited_per_page={visits}"
    )
    out.append(f"  plan, first page: {plans[0]}")
    if len(plans) > 1:
        out.append(f"  plan, later pages: {plans[-1]}")
    return seen


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    live = asyncio.run(build())
    out = [f"live children via fs.ls: {live}"]
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA case_sensitive_like = ON")
    keep = Keep()
    conn.create_function("keep", 2, keep)
    ids = {p: conn.execute("SELECT entry_id FROM vfs_entries WHERE path = ?", (p,)).fetchone()[0] for p in ("/big", "/d", "/s")}
    in_range = {p: conn.execute("SELECT count(*) FROM vfs_entries WHERE parent_id = ?", (ids[p],)).fetchone()[0] for p in ids}
    out.append(f"rows in each (parent_id, name) range, live and tombstoned: {in_range}")
    for composite in (False, True):
        if composite:
            conn.execute("CREATE INDEX ix_probe_parent_live_name ON vfs_entries (parent_id, deleted_at, name)")
            conn.execute("DROP INDEX ix_vfs_entries_deleted_at")
            conn.execute("CREATE INDEX ix_probe_deleted_path ON vfs_entries (deleted_at, path)")
            out.append("--- with (parent_id, deleted_at, name) added and (deleted_at) widened to (deleted_at, path) ---")
        else:
            out.append("--- today's indexes ---")
        big = drain(conn, keep, page_ls, ids["/big"], 1000, composite, out, "ls /big limit=1000")
        out.append(f"  union equals the 10,000 written: {set(big) == {f'/big/f{i:05}.txt' for i in range(10_000)}}")
        drain(conn, keep, page_ls, ids["/d"], 10, composite, out, "ls /d (first 900 of 1,000 deleted) limit=10")
        drain(conn, keep, page_ls, ids["/s"], 10, composite, out, "ls /s (9 of every 10 deleted) limit=10")
        drain(conn, keep, page_tree, "/s", 10, composite, out, "tree /s limit=10")
        drain(conn, keep, page_tree, "/big", 1000, composite, out, "tree /big limit=1000")
        drain(conn, keep, page_tree, "/n", 5, composite, out, "tree /n max_depth=1 (10 dirs x 100 files) limit=5", max_slashes=2)
    conn.close()
    text = "\n".join(out) + "\n"
    (HERE / "cursor_probe.out").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
