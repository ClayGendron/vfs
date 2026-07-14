"""Content-layout spike (W4): inline blob vs separate table vs chunk rows.

Measures, per layout x content size: metadata-only revision-bump latency
and WAL bytes written (the overflow-chain rewrite hazard), full content
read, and full content rewrite. Layout (b) additionally runs a page_size
grid. SQLite WAL, synchronous=NORMAL, one implicit transaction per op
(the backend's one-session-per-op shape); wal_autocheckpoint=0 so WAL
growth is a clean write-amplification proxy.

Run: SPIKE_OUT=<dir> uv run python .../bench_content_layout.py
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

SIZES = [("1KB", 1024, 400), ("16KB", 16 * 1024, 400), ("128KB", 128 * 1024, 150), ("1MB", 1 << 20, 40)]
CHUNK_BYTES = 4000  # near-TOAST-shaped chunk rows
PAGE_SIZES = [4096, 8192, 16384]
N_OPS = 100  # ops measured per (layout, size) cell


def corpus_bytes(total_needed: int) -> bytes:
    conn = sqlite3.connect(DATA_DIR / "corpus.db")
    buf = bytearray()
    cur = conn.execute("SELECT content FROM docs LIMIT 40000")
    while len(buf) < total_needed:
        rows = cur.fetchmany(1000)
        if not rows:
            break
        for (c,) in rows:
            buf.extend(c.encode())
    conn.close()
    return bytes(buf)


def fresh_db(path: Path, page_size: int) -> sqlite3.Connection:
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA page_size = {page_size}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    return conn


def wal_size(path: Path) -> int:
    wal = Path(str(path) + "-wal")
    return wal.stat().st_size if wal.exists() else 0


SCHEMAS = {
    "inline": """
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, kind TEXT,
            revision INTEGER NOT NULL, updated_at TEXT, content BLOB
        );
    """,
    "separate": """
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, kind TEXT,
            revision INTEGER NOT NULL, updated_at TEXT
        );
        CREATE TABLE content (node_id INTEGER PRIMARY KEY, data BLOB NOT NULL);
    """,
    "chunks": """
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, kind TEXT,
            revision INTEGER NOT NULL, updated_at TEXT
        );
        CREATE TABLE content_chunks (
            node_id INTEGER NOT NULL, seq INTEGER NOT NULL, data BLOB NOT NULL,
            PRIMARY KEY (node_id, seq)
        ) WITHOUT ROWID;
    """,
}


def populate(conn: sqlite3.Connection, layout: str, n_rows: int, blob: bytes) -> None:
    conn.executescript(SCHEMAS[layout])
    for i in range(n_rows):
        meta = (i, f"/mnt/dir{i % 20}/file{i}.txt", "file", 1000 + i, "2026-07-13T00:00:00Z")
        if layout == "inline":
            conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?)", (*meta, blob))
        else:
            conn.execute("INSERT INTO entries VALUES (?,?,?,?,?)", meta)
            if layout == "separate":
                conn.execute("INSERT INTO content VALUES (?,?)", (i, blob))
            else:
                conn.executemany(
                    "INSERT INTO content_chunks VALUES (?,?,?)",
                    [
                        (i, s, blob[off : off + CHUNK_BYTES])
                        for s, off in enumerate(range(0, len(blob), CHUNK_BYTES))
                    ],
                )
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def timed_ops(conn: sqlite3.Connection, db: Path, op, ids: list[int]) -> dict:
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    wal0 = wal_size(db)
    times = []
    for i in ids:
        t0 = time.perf_counter()
        op(i)
        times.append(time.perf_counter() - t0)
    return {
        "ms_p50": statistics.median(times) * 1e3,
        "ms_p99": statistics.quantiles(times, n=100)[98] * 1e3 if len(times) >= 100 else max(times) * 1e3,
        "wal_bytes_per_op": (wal_size(db) - wal0) // len(ids),
    }


def bench_cell(layout: str, size_label: str, size: int, n_rows: int, page_size: int, corpus: bytes) -> dict:
    db = OUT_DIR / f"layout_{layout}_{size_label}_{page_size}.db"
    conn = fresh_db(db, page_size)
    blob = corpus[:size]
    # Alternating rewrite payloads: repeating one payload would hit SQLite's
    # unchanged-region skip in btreeOverwriteContent and undercount WAL bytes.
    payloads = [corpus[size : 2 * size], corpus[2 * size : 3 * size]]
    populate(conn, layout, n_rows, blob)
    ids = [i % n_rows for i in range(N_OPS)]
    cell: dict = {}

    # 1. metadata-only revision bump, same serial width (stays 2-byte int).
    def bump_same(i: int) -> None:
        conn.execute("UPDATE entries SET revision = revision + 1 WHERE id = ?", (i,))
        conn.commit()

    cell["meta_bump_same_width"] = timed_ops(conn, db, bump_same, ids)

    # 2. metadata-only bump that flips serial width every time (1B <-> 3B int).
    flip = {}

    def bump_flip(i: int) -> None:
        flip[i] = not flip.get(i, False)
        conn.execute("UPDATE entries SET revision = ? WHERE id = ?", (100 if flip[i] else 100000, i))
        conn.commit()

    cell["meta_bump_width_change"] = timed_ops(conn, db, bump_flip, ids)

    # 3. full content read.
    if layout == "inline":
        def read(i: int) -> None:
            conn.execute("SELECT content FROM entries WHERE id = ?", (i,)).fetchone()
    elif layout == "separate":
        def read(i: int) -> None:
            conn.execute("SELECT data FROM content WHERE node_id = ?", (i,)).fetchone()
    else:
        def read(i: int) -> None:
            rows = conn.execute(
                "SELECT data FROM content_chunks WHERE node_id = ? ORDER BY seq", (i,)
            ).fetchall()
            b"".join(r[0] for r in rows)

    cell["content_read"] = timed_ops(conn, db, read, ids)

    # 4. full content rewrite (same-size, per-row alternating payload) + bump.
    row_toggle: dict[int, int] = {}

    def next_payload(i: int) -> bytes:
        row_toggle[i] = row_toggle.get(i, 0) ^ 1
        return payloads[row_toggle[i]]

    if layout == "inline":
        def rewrite(i: int) -> None:
            conn.execute(
                "UPDATE entries SET content = ?, revision = revision + 1 WHERE id = ?",
                (next_payload(i), i),
            )
            conn.commit()
    elif layout == "separate":
        def rewrite(i: int) -> None:
            conn.execute("UPDATE content SET data = ? WHERE node_id = ?", (next_payload(i), i))
            conn.execute("UPDATE entries SET revision = revision + 1 WHERE id = ?", (i,))
            conn.commit()
    else:
        def rewrite(i: int) -> None:
            b = next_payload(i)
            conn.execute("DELETE FROM content_chunks WHERE node_id = ?", (i,))
            conn.executemany(
                "INSERT INTO content_chunks VALUES (?,?,?)",
                [
                    (i, s, b[off : off + CHUNK_BYTES])
                    for s, off in enumerate(range(0, len(b), CHUNK_BYTES))
                ],
            )
            conn.execute("UPDATE entries SET revision = revision + 1 WHERE id = ?", (i,))
            conn.commit()

    cell["content_rewrite"] = timed_ops(conn, db, rewrite, ids)

    conn.close()
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    return cell


def main() -> None:
    corpus = corpus_bytes(3 << 20)
    results: dict = {"layouts": {}, "page_size_grid": {}}
    for layout in SCHEMAS:
        results["layouts"][layout] = {}
        for size_label, size, n_rows in SIZES:
            cell = bench_cell(layout, size_label, size, n_rows, 4096, corpus)
            results["layouts"][layout][size_label] = cell
            m = cell["meta_bump_same_width"]
            w = cell["meta_bump_width_change"]
            print(
                f"{layout:>9} {size_label:>6}: bump same-width {m['ms_p50']:.3f} ms "
                f"({m['wal_bytes_per_op']} B/op) | width-flip {w['ms_p50']:.3f} ms "
                f"({w['wal_bytes_per_op']} B/op) | read {cell['content_read']['ms_p50']:.3f} ms "
                f"| rewrite {cell['content_rewrite']['ms_p50']:.3f} ms",
                flush=True,
            )
    for ps in PAGE_SIZES:
        results["page_size_grid"][ps] = {}
        for size_label, size, n_rows in [("128KB", 128 * 1024, 150), ("1MB", 1 << 20, 40)]:
            cell = bench_cell("separate", size_label, size, n_rows, ps, corpus)
            results["page_size_grid"][ps][size_label] = {
                "content_read": cell["content_read"],
                "content_rewrite": cell["content_rewrite"],
            }
            print(
                f"page_size {ps:>5} {size_label:>6}: read {cell['content_read']['ms_p50']:.3f} ms "
                f"| rewrite {cell['content_rewrite']['ms_p50']:.3f} ms "
                f"({cell['content_rewrite']['wal_bytes_per_op']} B/op)",
                flush=True,
            )
    out = OUT_DIR / "bench_content_layout.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
