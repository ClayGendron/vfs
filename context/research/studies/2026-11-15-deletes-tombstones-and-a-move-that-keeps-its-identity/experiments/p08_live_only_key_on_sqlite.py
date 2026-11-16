"""Probe 08: can SQLite declare a unique key over live rows only, and a unique key that carries a generation.

A plain in-process sqlite3 database, no vfs code: the question is what
the engine accepts, so the table is a three-column stand-in.
"""

from __future__ import annotations

import sqlite3


def attempt(db: sqlite3.Connection, label: str, sql: str, params: tuple = ()) -> None:
    try:
        db.execute(sql, params)
        print(f"  ok      {label}")
    except sqlite3.Error as exc:
        print(f"  REFUSED {label}: {exc}")


def main() -> None:
    print(f"sqlite library {sqlite3.sqlite_version}")
    print("== option 1: the unique key covers live rows only (a partial unique index)")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE e (id INTEGER PRIMARY KEY, entry_id TEXT UNIQUE, parent_id TEXT, name TEXT, path TEXT, deleted_at TEXT)")
    attempt(db, "create unique index on path where deleted_at is null", "CREATE UNIQUE INDEX uq_live_path ON e (path) WHERE deleted_at IS NULL")
    attempt(db, "create unique index on (parent_id, name) where deleted_at is null", "CREATE UNIQUE INDEX uq_live_name ON e (parent_id, name) WHERE deleted_at IS NULL")
    attempt(db, "a live row at /d/a.txt", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('A', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "tombstone it", "UPDATE e SET deleted_at = '2026-11-15' WHERE entry_id = 'A'")
    attempt(db, "a second, live row at /d/a.txt", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('B', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "tombstone the second too (two tombstones at one path)", "UPDATE e SET deleted_at = '2026-11-16' WHERE entry_id = 'B'")
    attempt(db, "a third, live row at /d/a.txt", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('C', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "a fourth, live row at /d/a.txt (must be refused)", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('X', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "restore the first while the third is live (must be refused)", "UPDATE e SET deleted_at = NULL WHERE entry_id = 'A'")
    print("  rows:", db.execute("SELECT entry_id, path, deleted_at FROM e ORDER BY id").fetchall())
    print("  plan, live lookup by path:", [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT * FROM e WHERE path = '/d/a.txt' AND deleted_at IS NULL")])
    print("  plan, any-row lookup by path:", [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT * FROM e WHERE path = '/d/a.txt'")])
    print("  plan, live children by name:", [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT * FROM e WHERE parent_id = 'D' AND deleted_at IS NULL ORDER BY name")])

    print("== option 3: the unique key gains a generation (0 for the live row, a fresh value for each tombstone)")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE e (id INTEGER PRIMARY KEY, entry_id TEXT UNIQUE, parent_id TEXT, name TEXT, path TEXT, deleted_at TEXT, generation INTEGER NOT NULL DEFAULT 0, UNIQUE (path, generation), UNIQUE (parent_id, name, generation))")
    attempt(db, "a live row at /d/a.txt", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('A', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "tombstone it, generation = its own row id", "UPDATE e SET deleted_at = '2026-11-15', generation = id WHERE entry_id = 'A'")
    attempt(db, "a second, live row at /d/a.txt", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('B', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "tombstone the second too", "UPDATE e SET deleted_at = '2026-11-16', generation = id WHERE entry_id = 'B'")
    attempt(db, "a third, live row at /d/a.txt", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('C', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "a fourth, live row at /d/a.txt (must be refused)", "INSERT INTO e (entry_id, parent_id, name, path) VALUES ('X', 'D', 'a.txt', '/d/a.txt')")
    attempt(db, "restore the first while the third is live (must be refused)", "UPDATE e SET deleted_at = NULL, generation = 0 WHERE entry_id = 'A'")
    print("  rows:", db.execute("SELECT entry_id, path, deleted_at, generation FROM e ORDER BY id").fetchall())
    print("  plan, live lookup by path:", [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT * FROM e WHERE path = '/d/a.txt' AND generation = 0")])
    print("  plan, live children by name:", [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT * FROM e WHERE parent_id = 'D' AND generation = 0 ORDER BY name")])

    print("== option 1 without a partial index: a nullable key column (the spelling for an engine with no partial index)")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE e (id INTEGER PRIMARY KEY, entry_id TEXT UNIQUE, path TEXT, deleted_at TEXT, live_path TEXT UNIQUE)")
    attempt(db, "a live row", "INSERT INTO e (entry_id, path, live_path) VALUES ('A', '/d/a.txt', '/d/a.txt')")
    attempt(db, "tombstone it: live_path goes NULL", "UPDATE e SET deleted_at = '2026-11-15', live_path = NULL WHERE entry_id = 'A'")
    attempt(db, "a second, live row", "INSERT INTO e (entry_id, path, live_path) VALUES ('B', '/d/a.txt', '/d/a.txt')")
    attempt(db, "tombstone the second: two NULLs under one unique key", "UPDATE e SET deleted_at = '2026-11-16', live_path = NULL WHERE entry_id = 'B'")
    attempt(db, "a third, live row", "INSERT INTO e (entry_id, path, live_path) VALUES ('C', '/d/a.txt', '/d/a.txt')")
    attempt(db, "a fourth, live row (must be refused)", "INSERT INTO e (entry_id, path, live_path) VALUES ('X', '/d/a.txt', '/d/a.txt')")


main()
