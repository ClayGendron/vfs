"""Batch-write spike (W5): 1K-entry batch statement counts and wall-clock.

One batch = 1,000 entries, each with metadata row + ~3.3KB content row +
version snapshot row (3,000 rows across three tables), committed in ONE
transaction. Strategies: per-row execute (the anti-pattern), executemany,
and multi-row VALUES chunked by the dialect parameter budget. Postgres
adds COPY. Statement counts are computed from the budgets; times measured.

Run: SPIKE_OUT=<dir> uv run --with psycopg python .../bench_batch_write.py
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import DATA_DIR  # noqa: E402

OUT_DIR = Path(os.environ.get("SPIKE_OUT", DATA_DIR))
N = 1000
REPEATS = 3

DDL_SQLITE = """
CREATE TABLE entries (
    id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, kind TEXT,
    revision INTEGER NOT NULL, updated_at TEXT
);
CREATE TABLE content (node_id INTEGER PRIMARY KEY, data BLOB NOT NULL);
CREATE TABLE versions (
    node_id INTEGER NOT NULL, version INTEGER NOT NULL,
    is_snapshot INTEGER NOT NULL, stored TEXT NOT NULL,
    PRIMARY KEY (node_id, version)
);
"""

DDL_PG = DDL_SQLITE.replace("INTEGER PRIMARY KEY", "int PRIMARY KEY").replace(
    "BLOB", "bytea"
).replace("is_snapshot INTEGER", "is_snapshot boolean")


def load_rows() -> tuple[list, list, list]:
    conn = sqlite3.connect(DATA_DIR / "corpus.db")
    docs = conn.execute("SELECT id, path, content FROM docs LIMIT ?", (N,)).fetchall()
    conn.close()
    entries = [(i, f"/mnt/{p}#{i}", "file", 1, "2026-07-13T00:00:00Z") for i, p, _ in docs]
    content = [(i, c.encode()) for i, _, c in docs]
    versions = [(i, 1, True, c) for i, _, c in docs]
    return entries, content, versions


def values_chunks(rows: list, cols: int, budget: int) -> list[list]:
    per_stmt = max(1, budget // cols)
    return [rows[i : i + per_stmt] for i in range(0, len(rows), per_stmt)]


def stmt_count(budget: int) -> int:
    return sum(
        math.ceil(N / max(1, budget // cols)) for cols in (5, 2, 4)
    )


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def bench_sqlite(entries: list, content: list, versions: list) -> dict:
    out: dict = {}

    def fresh() -> tuple[sqlite3.Connection, Path]:
        db = OUT_DIR / "batch_sqlite.db"
        for s in ("", "-wal", "-shm"):
            Path(str(db) + s).unlink(missing_ok=True)
        c = sqlite3.connect(db)
        c.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
        c.executescript(DDL_SQLITE)
        return c, db

    def run(strategy) -> float:
        best = math.inf
        for _ in range(REPEATS):
            c, _db = fresh()
            t0 = time.perf_counter()
            c.execute("BEGIN IMMEDIATE")
            strategy(c)
            c.commit()
            best = min(best, time.perf_counter() - t0)
            c.close()
        return best

    def per_row(c: sqlite3.Connection) -> None:
        for e in entries:
            c.execute("INSERT INTO entries VALUES (?,?,?,?,?)", e)
        for r in content:
            c.execute("INSERT INTO content VALUES (?,?)", r)
        for v in versions:
            c.execute("INSERT INTO versions VALUES (?,?,?,?)", v)

    def many(c: sqlite3.Connection) -> None:
        c.executemany("INSERT INTO entries VALUES (?,?,?,?,?)", entries)
        c.executemany("INSERT INTO content VALUES (?,?)", content)
        c.executemany("INSERT INTO versions VALUES (?,?,?,?)", versions)

    def multirow(budget: int):
        def go(c: sqlite3.Connection) -> None:
            for table, rows, cols in (
                ("entries", entries, 5),
                ("content", content, 2),
                ("versions", versions, 4),
            ):
                ph = "(" + ",".join("?" * cols) + ")"
                for chunk in values_chunks(rows, cols, budget):
                    c.execute(
                        f"INSERT INTO {table} VALUES " + ",".join([ph] * len(chunk)),
                        [x for row in chunk for x in row],
                    )
        return go

    out["per_row_execute"] = {"stmts": 3 * N, "seconds": run(per_row)}
    out["executemany"] = {"stmts": "3 prepared (3,000 bindings)", "seconds": run(many)}
    out["multirow_32766"] = {"stmts": stmt_count(32766), "seconds": run(multirow(32766))}
    out["multirow_999_legacy"] = {"stmts": stmt_count(999), "seconds": run(multirow(999))}
    return out


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------


def bench_pg(entries: list, content: list, versions: list) -> dict:
    out: dict = {}
    with psycopg.connect(dbname="postgres", autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname='vfs_spike'").fetchone():
            c.execute("CREATE DATABASE vfs_spike")

    def run(strategy) -> float:
        best = math.inf
        for _ in range(REPEATS):
            with psycopg.connect(dbname="vfs_spike") as c:
                c.execute("DROP TABLE IF EXISTS entries, content, versions")
                for stmt in DDL_PG.strip().split(";"):
                    if stmt.strip():
                        c.execute(stmt)
                c.commit()
                t0 = time.perf_counter()
                strategy(c)
                c.commit()
                best = min(best, time.perf_counter() - t0)
        return best

    def per_row(c) -> None:
        with c.cursor() as cur:
            for e in entries:
                cur.execute("INSERT INTO entries VALUES (%s,%s,%s,%s,%s)", e)
            for r in content:
                cur.execute("INSERT INTO content VALUES (%s,%s)", r)
            for v in versions:
                cur.execute("INSERT INTO versions VALUES (%s,%s,%s,%s)", v)

    def many(c) -> None:
        with c.cursor() as cur:
            cur.executemany("INSERT INTO entries VALUES (%s,%s,%s,%s,%s)", entries)
            cur.executemany("INSERT INTO content VALUES (%s,%s)", content)
            cur.executemany("INSERT INTO versions VALUES (%s,%s,%s,%s)", versions)

    def multirow(c) -> None:
        budget = 65535
        with c.cursor() as cur:
            for table, rows, cols in (
                ("entries", entries, 5),
                ("content", content, 2),
                ("versions", versions, 4),
            ):
                ph = "(" + ",".join(["%s"] * cols) + ")"
                for chunk in values_chunks(rows, cols, budget):
                    cur.execute(
                        f"INSERT INTO {table} VALUES " + ",".join([ph] * len(chunk)),
                        [x for row in chunk for x in row],
                    )

    def copy(c) -> None:
        with c.cursor() as cur:
            with cur.copy("COPY entries FROM STDIN") as cp:
                for e in entries:
                    cp.write_row(e)
            with cur.copy("COPY content FROM STDIN") as cp:
                for r in content:
                    cp.write_row(r)
            with cur.copy("COPY versions FROM STDIN") as cp:
                for v in versions:
                    cp.write_row(v)

    out["per_row_execute"] = {"stmts": 3 * N, "seconds": run(per_row)}
    out["executemany_pipeline"] = {"stmts": "3 prepared (pipelined)", "seconds": run(many)}
    out["multirow_65535"] = {"stmts": stmt_count(65535), "seconds": run(multirow)}
    out["copy"] = {"stmts": 3, "seconds": run(copy)}
    return out


def main() -> None:
    entries, content, versions = load_rows()
    total_bytes = sum(len(c) for _, c in content)
    print(f"batch: {N} entries, {total_bytes / 1e6:.1f} MB content, x2 (version rows)")
    results = {"sqlite": bench_sqlite(entries, content, versions)}
    for k, v in results["sqlite"].items():
        print(f"  sqlite {k:>22}: {v['seconds'] * 1e3:8.1f} ms  ({v['stmts']} stmts)")
    results["postgres"] = bench_pg(entries, content, versions)
    for k, v in results["postgres"].items():
        print(f"  pg     {k:>22}: {v['seconds'] * 1e3:8.1f} ms  ({v['stmts']} stmts)")
    out = OUT_DIR / "bench_batch_write.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
