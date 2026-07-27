"""Contention spike (W7): SQLite two-writer discipline + Postgres move cycles.

Part A — two OS processes hammer one SQLite WAL database with
read-then-write transactions, BEGIN IMMEDIATE vs DEFERRED, busy_timeout
set. Counts SQLITE_BUSY (5) and SQLITE_BUSY_SNAPSHOT (517) by extended
errcode, retries needed, and per-op latency.

Part B — the Postgres move-cycle composition probe: two transactions each
run an ancestry check (recursive CTE) then move a directory; do two
individually-safe moves compose a parent-pointer cycle at READ COMMITTED
and REPEATABLE READ, and which mechanism (SERIALIZABLE, advisory lock)
closes it?

Run: SPIKE_OUT=<dir> uv run --with psycopg python .../bench_contention.py
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sqlite3
import statistics
import sys
import threading
import time
from pathlib import Path

import psycopg
import psycopg.errors

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import DATA_DIR  # noqa: E402

OUT_DIR = Path(os.environ.get("SPIKE_OUT", DATA_DIR))
OPS_PER_WORKER = 300
MAX_RETRIES = 1000
BUSY_TIMEOUT_MS = 5000


# ---------------------------------------------------------------------------
# Part A — SQLite two-writer
# ---------------------------------------------------------------------------


def sqlite_worker(db: str, mode: str, worker_id: int, barrier, out_q) -> None:
    conn = sqlite3.connect(db, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    stats = {"busy": 0, "busy_snapshot": 0, "retries": 0, "max_op_retries": 0, "latency": []}
    barrier.wait()
    for op in range(OPS_PER_WORKER):
        t0 = time.perf_counter()
        for _attempt in range(MAX_RETRIES):
            try:
                conn.execute("BEGIN IMMEDIATE" if mode == "immediate" else "BEGIN")
                row = conn.execute(
                    "SELECT revision FROM entries WHERE id = ?", (op % 50,)
                ).fetchone()
                conn.execute(
                    "UPDATE entries SET revision = ? WHERE id = ?",
                    (row[0] + 1, (op + worker_id * 7) % 50),
                )
                conn.execute("COMMIT")
                break
            except sqlite3.OperationalError as e:
                code = getattr(e, "sqlite_errorcode", None)
                if code == 517:
                    stats["busy_snapshot"] += 1
                elif code == 5:
                    stats["busy"] += 1
                else:
                    raise
                stats["retries"] += 1
                stats["max_op_retries"] = max(stats["max_op_retries"], _attempt + 1)
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                # In-transaction upgrade failures are NOT absorbed by
                # busy_timeout; bare spin-retry livelocks against a busy
                # rival (a no-backoff first run starved out at 100 retries).
                time.sleep(min(0.0002 * (_attempt + 1) ** 2, 0.01))
        else:
            raise RuntimeError(f"op {op} exhausted {MAX_RETRIES} retries in mode {mode}")
        stats["latency"].append(time.perf_counter() - t0)
    conn.close()
    out_q.put(stats)


def bench_sqlite_contention() -> dict:
    results = {}
    for mode in ("immediate", "deferred"):
        db = str(OUT_DIR / "contention.db")
        for s in ("", "-wal", "-shm"):
            Path(db + s).unlink(missing_ok=True)
        conn = sqlite3.connect(db)
        conn.executescript(
            "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);"
        )
        conn.executemany("INSERT INTO entries VALUES (?,?)", [(i, 0) for i in range(50)])
        conn.commit()
        conn.close()

        barrier = mp.Barrier(2)
        out_q: mp.Queue = mp.Queue()
        procs = [
            mp.Process(target=sqlite_worker, args=(db, mode, w, barrier, out_q))
            for w in range(2)
        ]
        t0 = time.monotonic()
        for p in procs:
            p.start()
        stats = [out_q.get() for _ in procs]
        for p in procs:
            p.join()
        wall = time.monotonic() - t0
        lat = sorted(t for s in stats for t in s["latency"])
        results[mode] = {
            "ops": 2 * OPS_PER_WORKER,
            "wall_seconds": round(wall, 2),
            "busy": sum(s["busy"] for s in stats),
            "busy_snapshot": sum(s["busy_snapshot"] for s in stats),
            "retries": sum(s["retries"] for s in stats),
            "max_op_retries": max(s["max_op_retries"] for s in stats),
            "latency_ms_p50": statistics.median(lat) * 1e3,
            "latency_ms_p99": lat[int(len(lat) * 0.99)] * 1e3,
            "latency_ms_max": lat[-1] * 1e3,
        }
        r = results[mode]
        print(
            f"  sqlite {mode:>9}: {r['ops']} ops in {r['wall_seconds']}s | "
            f"BUSY {r['busy']}, BUSY_SNAPSHOT {r['busy_snapshot']}, retries {r['retries']} "
            f"(max/op {r['max_op_retries']}) | "
            f"p50 {r['latency_ms_p50']:.2f} ms, p99 {r['latency_ms_p99']:.2f} ms, "
            f"max {r['latency_ms_max']:.1f} ms",
            flush=True,
        )
    return results


# ---------------------------------------------------------------------------
# Part B — Postgres move-cycle composition
# ---------------------------------------------------------------------------

ANCESTRY_SQL = """
WITH RECURSIVE anc AS (
    SELECT id, parent_id FROM nodes WHERE id = %s
    UNION ALL
    SELECT n.id, n.parent_id FROM nodes n JOIN anc ON n.id = anc.parent_id
)
SELECT count(*) FROM anc WHERE id = %s
"""

CYCLE_CHECK_SQL = """
WITH RECURSIVE walk AS (
    SELECT id, parent_id, ARRAY[id] AS seen, false AS cyc
    FROM nodes WHERE id = 2
    UNION ALL
    SELECT n.id, n.parent_id, walk.seen || n.id, n.id = ANY(walk.seen)
    FROM nodes n JOIN walk ON n.id = walk.parent_id
    WHERE NOT walk.cyc
)
SELECT bool_or(cyc) FROM walk
"""


def pg_reset(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS nodes")
    conn.execute("CREATE TABLE nodes (id int PRIMARY KEY, parent_id int)")
    conn.execute("INSERT INTO nodes VALUES (1, NULL), (2, 1), (3, 1)")


def try_compose_cycle(isolation: str) -> dict:
    """Interleave two safe-looking moves; return what happened."""
    admin = psycopg.connect(dbname="vfs_spike", autocommit=True)
    pg_reset(admin)
    c1 = psycopg.connect(dbname="vfs_spike")
    c2 = psycopg.connect(dbname="vfs_spike")
    outcome = {"isolation": isolation, "aborted": None, "cycle": None}
    try:
        for c in (c1, c2):
            c.execute(f"SET default_transaction_isolation = '{isolation}'")
            c.commit()
        # c1 plans: move a(2) under b(3) — safe iff a is not an ancestor of b.
        chk1 = c1.execute(ANCESTRY_SQL, (3, 2)).fetchone()[0]
        # c2 plans: move b(3) under a(2) — safe iff b is not an ancestor of a.
        chk2 = c2.execute(ANCESTRY_SQL, (2, 3)).fetchone()[0]
        assert chk1 == 0 and chk2 == 0, "both pre-checks must pass in-snapshot"
        c1.execute("UPDATE nodes SET parent_id = 3 WHERE id = 2")
        c2.execute("UPDATE nodes SET parent_id = 2 WHERE id = 3")
        c1.commit()
        c2.commit()
        outcome["aborted"] = False
    except psycopg.errors.SerializationFailure:
        outcome["aborted"] = True
        c1.rollback()
        c2.rollback()
    finally:
        c1.close()
        c2.close()
    outcome["cycle"] = bool(admin.execute(CYCLE_CHECK_SQL).fetchone()[0])
    admin.close()
    return outcome


def try_advisory_lock() -> dict:
    """Same race under a per-mount advisory lock + re-check; c2 must refuse."""
    admin = psycopg.connect(dbname="vfs_spike", autocommit=True)
    pg_reset(admin)
    events: dict = {"c2_refused": None}
    c1_locked = threading.Event()
    c1_may_commit = threading.Event()

    def mover_1() -> None:
        with psycopg.connect(dbname="vfs_spike") as c1:
            c1.execute("SELECT pg_advisory_xact_lock(42)")
            c1_locked.set()
            assert c1.execute(ANCESTRY_SQL, (3, 2)).fetchone()[0] == 0
            c1.execute("UPDATE nodes SET parent_id = 3 WHERE id = 2")
            c1_may_commit.wait()
            c1.commit()

    def mover_2() -> None:
        c1_locked.wait()
        with psycopg.connect(dbname="vfs_spike") as c2:
            threading.Timer(0.3, c1_may_commit.set).start()
            c2.execute("SELECT pg_advisory_xact_lock(42)")  # blocks until c1 commits
            ancestors = c2.execute(ANCESTRY_SQL, (2, 3)).fetchone()[0]
            if ancestors:
                events["c2_refused"] = True  # b IS now an ancestor of a: refuse
                c2.rollback()
            else:
                events["c2_refused"] = False
                c2.execute("UPDATE nodes SET parent_id = 2 WHERE id = 3")
                c2.commit()

    t1 = threading.Thread(target=mover_1)
    t2 = threading.Thread(target=mover_2)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    cycle = bool(admin.execute(CYCLE_CHECK_SQL).fetchone()[0])
    admin.close()
    return {"isolation": "read committed + advisory lock", "c2_refused": events["c2_refused"], "cycle": cycle}


def bench_pg_cycles() -> list[dict]:
    with psycopg.connect(dbname="postgres", autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname='vfs_spike'").fetchone():
            c.execute("CREATE DATABASE vfs_spike")
    results = []
    for isolation in ("read committed", "repeatable read", "serializable"):
        r = try_compose_cycle(isolation)
        results.append(r)
        print(
            f"  pg {isolation:>16}: aborted={r['aborted']}  cycle_committed={r['cycle']}",
            flush=True,
        )
    r = try_advisory_lock()
    results.append(r)
    print(
        f"  pg    advisory lock: c2_refused={r['c2_refused']}  cycle_committed={r['cycle']}",
        flush=True,
    )
    return results


def main() -> None:
    print("Part A - SQLite two-writer (2 processes x 300 read-then-write ops):")
    sqlite_results = bench_sqlite_contention()
    print("Part B - Postgres concurrent-move cycle composition:")
    pg_results = bench_pg_cycles()
    out = OUT_DIR / "bench_contention.json"
    out.write_text(json.dumps({"sqlite": sqlite_results, "pg_move_cycle": pg_results}, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
