"""Durability spike (W8): SQLite WAL synchronous=FULL vs NORMAL pricing.

The representative write op (one transaction): insert entry row + version
snapshot row + ~3.3KB content row, then bump the parent directory's
revision. 500 sequential single-op commits per mode, plus a batched
(10 ops/txn) variant for amortization context.

Run: SPIKE_OUT=<dir> uv run python .../bench_durability.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import DATA_DIR  # noqa: E402

OUT_DIR = Path(os.environ.get("SPIKE_OUT", DATA_DIR))
N_OPS = 500

DDL = """
CREATE TABLE entries (
    id INTEGER PRIMARY KEY, parent_id INTEGER, path TEXT UNIQUE NOT NULL,
    kind TEXT, revision INTEGER NOT NULL
);
CREATE TABLE content (node_id INTEGER PRIMARY KEY, data BLOB NOT NULL);
CREATE TABLE versions (
    node_id INTEGER NOT NULL, version INTEGER NOT NULL,
    is_snapshot INTEGER NOT NULL, stored TEXT NOT NULL,
    PRIMARY KEY (node_id, version)
);
"""


def load_payloads() -> list[bytes]:
    conn = sqlite3.connect(DATA_DIR / "corpus.db")
    rows = conn.execute("SELECT content FROM docs LIMIT ?", (N_OPS,)).fetchall()
    conn.close()
    return [r[0].encode() for r in rows]


def bench(mode: str, batch: int, payloads: list[bytes]) -> dict:
    db = OUT_DIR / f"durability_{mode}_{batch}.db"
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    conn = sqlite3.connect(db, isolation_level=None)
    conn.executescript(f"PRAGMA journal_mode=WAL; PRAGMA synchronous={mode};")
    conn.executescript(DDL)
    conn.execute("INSERT INTO entries VALUES (0, NULL, '/mnt', 'directory', 1)")

    times: list[float] = []
    i = 0
    while i < N_OPS:
        t0 = time.perf_counter()
        conn.execute("BEGIN IMMEDIATE")
        for _ in range(min(batch, N_OPS - i)):
            nid = i + 1
            body = payloads[i]
            conn.execute(
                "INSERT INTO entries VALUES (?,?,?,?,?)",
                (nid, 0, f"/mnt/file{nid}.txt", "file", 1),
            )
            conn.execute("INSERT INTO content VALUES (?,?)", (nid, body))
            conn.execute(
                "INSERT INTO versions VALUES (?,?,?,?)", (nid, 1, 1, body.decode())
            )
            conn.execute("UPDATE entries SET revision = revision + 1 WHERE id = 0")
            i += 1
        conn.execute("COMMIT")
        times.append(time.perf_counter() - t0)
    conn.close()
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    per_commit = sorted(times)
    return {
        "mode": mode,
        "ops_per_txn": batch,
        "commits": len(times),
        "commit_ms_p50": statistics.median(per_commit) * 1e3,
        "commit_ms_p99": per_commit[int(len(per_commit) * 0.99) - 1] * 1e3,
        "ops_per_second": N_OPS / sum(times),
    }


def main() -> None:
    payloads = load_payloads()
    results = []
    for mode in ("NORMAL", "FULL"):
        for batch in (1, 10):
            r = bench(mode, batch, payloads)
            results.append(r)
            print(
                f"  synchronous={mode:>6} batch={batch:>2}: "
                f"commit p50 {r['commit_ms_p50']:.3f} ms, p99 {r['commit_ms_p99']:.3f} ms, "
                f"{r['ops_per_second']:,.0f} ops/s",
                flush=True,
            )
    out = OUT_DIR / "bench_durability.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
