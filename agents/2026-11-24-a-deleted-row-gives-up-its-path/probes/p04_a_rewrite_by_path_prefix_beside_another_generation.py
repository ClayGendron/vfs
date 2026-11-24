"""Probe 04: what a move's descendant rewrite does once two directories, one deleted and one live, share a path.

Today's rewrite names its rows by path prefix with no liveness term, which is sound while a path holds one
row. The table below holds a deleted directory at ``/d`` with one deleted file, and a live directory at
``/d`` with one live file and one file deleted on its own. The live directory is moved to ``/e`` twice:
once with today's predicate and once with the live side alone.
"""

from __future__ import annotations

import sqlite3

SETUP = """
CREATE TABLE t (entry TEXT PRIMARY KEY, parent TEXT, path TEXT, deleted INTEGER, trash_root TEXT);
INSERT INTO t VALUES
  ('D0', 'root', '/d',   1, 'D0'),
  ('A',  'D0',   '/d/a', 1, 'D0'),
  ('D2', 'root', '/d',   0, NULL),
  ('B',  'D2',   '/d/b', 0, NULL),
  ('C',  'D2',   '/d/c', 1, 'C');
"""
TORN = (
    "SELECT count(*) FROM t m JOIN t r ON r.entry = m.trash_root"
    " WHERE m.entry <> r.entry AND substr(m.path, 1, length(r.path) + 1) <> r.path || '/'"
)


def show(conn: sqlite3.Connection, label: str) -> None:
    print(f"  {label}")
    for entry, parent, path, deleted, root in conn.execute("SELECT * FROM t ORDER BY entry"):
        state = f"deleted, set of {root}" if deleted else "live"
        print(f"    {entry}: parent={parent} path={path} ({state})")
    torn = conn.execute(TORN).fetchone()[0]
    print(f"    rows of a deleted set whose path is no longer beneath the set's root: {torn}")


for label, predicate in (
    ("today's predicate: path LIKE '/d/%'", "path LIKE '/d/%'"),
    ("the live side alone: path LIKE '/d/%' AND deleted = 0", "path LIKE '/d/%' AND deleted = 0"),
):
    conn = sqlite3.connect(":memory:")
    conn.executescript(SETUP)
    conn.execute("UPDATE t SET path = '/e' WHERE entry = 'D2'")
    moved = conn.execute(f"UPDATE t SET path = '/e' || substr(path, 3) WHERE {predicate}").rowcount
    print(f"== move the live /d to /e, descendants by {label}: {moved} row(s) rewritten")
    show(conn, "afterwards")
    conn.close()
