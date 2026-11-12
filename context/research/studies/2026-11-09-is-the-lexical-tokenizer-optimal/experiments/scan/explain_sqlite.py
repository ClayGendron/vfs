"""Explain the lexical build's page statement on SQLite and count what one page visits.

Opens a read-only connection to the copied 100,000-file store and, for
the exact statement ``_chunk_batches`` issues (compiled with literal
binds by the harness), prints ``EXPLAIN QUERY PLAN``, the ``EXPLAIN``
opcode count, and the statement-status counters SQLite keeps per prepared
statement (``sqlite3_stmt_status``: FULLSCAN_STEP, SORT, AUTOINDEX,
VM_STEP, FILTER_MISS/HIT), read through ctypes against the Homebrew
libsqlite3 because Python's ``sqlite3`` module does not expose them. The
same counters are read for the alternatives' page statements and for
pages at several ``last`` offsets, so the study can say whether a page's
cost grows with its position in the table.

Usage: uv run python explain_sqlite.py <db path> <out json> <out text>
"""

from __future__ import annotations

import ctypes
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

LIB_CANDIDATES = ["/opt/homebrew/opt/sqlite/lib/libsqlite3.dylib", "/usr/lib/libsqlite3.dylib"]

SQLITE_OK, SQLITE_ROW, SQLITE_DONE = 0, 100, 101
SQLITE_OPEN_READONLY, SQLITE_OPEN_URI = 0x1, 0x40
STATUS = {
    "fullscan_step": 1,
    "sort": 2,
    "autoindex": 3,
    "vm_step": 4,
    "reprepare": 5,
    "run": 6,
    "filter_miss": 7,
    "filter_hit": 8,
}

FILTER = "vfs_entries.chunked = 1 AND vfs_entries.indexable = 1 AND vfs_entries.deleted_at IS NULL"

STATEMENTS = {
    "shipped_join": (
        "SELECT vfs_chunks.id, vfs_chunks.entry_id, vfs_chunks.content FROM vfs_chunks "
        "JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id "
        f"WHERE {FILTER} AND vfs_chunks.id > ? ORDER BY vfs_chunks.id LIMIT ?"
    ),
    "exists_subquery": (
        "SELECT vfs_chunks.id, vfs_chunks.entry_id, vfs_chunks.content FROM vfs_chunks "
        "WHERE vfs_chunks.entry_id IN (SELECT vfs_entries.entry_id FROM vfs_entries WHERE "
        f"{FILTER}) AND vfs_chunks.id > ? ORDER BY vfs_chunks.id LIMIT ?"
    ),
    "cross_join_chunks_outer": (
        "SELECT vfs_chunks.id, vfs_chunks.entry_id, vfs_chunks.content FROM vfs_chunks "
        "CROSS JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id "
        f"WHERE {FILTER} AND vfs_chunks.id > ? ORDER BY vfs_chunks.id LIMIT ?"
    ),
    "chunks_alone": (
        "SELECT vfs_chunks.id, vfs_chunks.entry_id, vfs_chunks.content FROM vfs_chunks "
        "WHERE vfs_chunks.id > ? ORDER BY vfs_chunks.id LIMIT ?"
    ),
    "ids_only_join": (
        "SELECT vfs_chunks.id, vfs_chunks.entry_id FROM vfs_chunks "
        "JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id "
        f"WHERE {FILTER} AND vfs_chunks.id > ? ORDER BY vfs_chunks.id LIMIT ?"
    ),
}


class Native:
    """The handful of sqlite3 C entry points the counters need."""

    def __init__(self) -> None:
        for path in LIB_CANDIDATES:
            try:
                self.lib = ctypes.CDLL(path)
                self.path = path
                break
            except OSError:
                continue
        else:
            raise SystemExit("no libsqlite3 found")
        lib = self.lib
        lib.sqlite3_libversion.restype = ctypes.c_char_p
        lib.sqlite3_open_v2.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_char_p]
        lib.sqlite3_prepare_v2.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_char_p),
        ]
        lib.sqlite3_bind_int64.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int64]
        lib.sqlite3_step.argtypes = [ctypes.c_void_p]
        lib.sqlite3_reset.argtypes = [ctypes.c_void_p]
        lib.sqlite3_finalize.argtypes = [ctypes.c_void_p]
        lib.sqlite3_stmt_status.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        lib.sqlite3_column_bytes.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_int64.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_int64.restype = ctypes.c_int64
        lib.sqlite3_errmsg.argtypes = [ctypes.c_void_p]
        lib.sqlite3_errmsg.restype = ctypes.c_char_p
        lib.sqlite3_close.argtypes = [ctypes.c_void_p]
        self.version = lib.sqlite3_libversion().decode()

    def open(self, db_path: str) -> ctypes.c_void_p:
        handle = ctypes.c_void_p()
        rc = self.lib.sqlite3_open_v2(
            f"file:{db_path}?mode=ro".encode(), ctypes.byref(handle), SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, None
        )
        assert rc == SQLITE_OK, rc
        return handle

    def run_page(self, db, sql: str, last: int, limit: int) -> dict[str, object]:
        stmt = ctypes.c_void_p()
        rc = self.lib.sqlite3_prepare_v2(db, sql.encode(), -1, ctypes.byref(stmt), None)
        assert rc == SQLITE_OK, (rc, self.lib.sqlite3_errmsg(db))
        self.lib.sqlite3_bind_int64(stmt, 1, last)
        self.lib.sqlite3_bind_int64(stmt, 2, limit)
        rows, content_bytes, last_id = 0, 0, last
        t0 = time.perf_counter()
        while (rc := self.lib.sqlite3_step(stmt)) == SQLITE_ROW:
            rows += 1
            last_id = self.lib.sqlite3_column_int64(stmt, 0)
            if "content" in sql.split("FROM", 1)[0]:
                content_bytes += self.lib.sqlite3_column_bytes(stmt, 2)
        wall = time.perf_counter() - t0
        assert rc == SQLITE_DONE, (rc, self.lib.sqlite3_errmsg(db))
        counters = {name: self.lib.sqlite3_stmt_status(stmt, code, 0) for name, code in STATUS.items()}
        self.lib.sqlite3_finalize(stmt)
        return {"last": last, "limit": limit, "rows": rows, "content_bytes": content_bytes, "last_id": last_id, "wall_ms": round(1000 * wall, 3), **counters}


def plan_and_opcodes(conn: sqlite3.Connection, sql: str) -> dict[str, object]:
    plan = conn.execute("EXPLAIN QUERY PLAN " + sql, (0, 256)).fetchall()
    opcodes = conn.execute("EXPLAIN " + sql, (0, 256)).fetchall()
    return {
        "plan": [f"{'  ' * 0}id={r[0]} parent={r[1]} {r[3]}" for r in plan],
        "opcodes": len(opcodes),
        "opcode_names": sorted({r[1] for r in opcodes}),
    }


def main() -> None:
    db_path, out_json, out_text = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    native = Native()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    lines: list[str] = []
    report: dict[str, object] = {
        "python_sqlite_version": sqlite3.sqlite_version,
        "ctypes_lib": native.path,
        "ctypes_lib_version": native.version,
        "db": db_path,
    }
    counts = {}
    for name, sql in [
        ("chunks", "SELECT count(*) FROM vfs_chunks"),
        ("entries", "SELECT count(*) FROM vfs_entries"),
        ("entries_covered", f"SELECT count(*) FROM vfs_entries WHERE {FILTER}"),
        ("chunks_covered", f"SELECT count(*) FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id WHERE {FILTER}"),
        ("max_chunk_id", "SELECT max(id) FROM vfs_chunks"),
        ("min_chunk_id", "SELECT min(id) FROM vfs_chunks"),
        ("chunk_content_bytes", "SELECT sum(length(CAST(content AS BLOB))) FROM vfs_chunks"),
        ("chunk_content_chars", "SELECT sum(length(content)) FROM vfs_chunks"),
        ("page_size", "PRAGMA page_size"),
        ("page_count", "PRAGMA page_count"),
    ]:
        counts[name] = conn.execute(sql).fetchone()[0]
    report["counts"] = counts
    lines.append(f"store: {json.dumps(counts)}")
    indexes = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND tbl_name IN ('vfs_chunks','vfs_entries') ORDER BY tbl_name, name"
    ).fetchall()
    report["indexes"] = [{"name": n, "table": t, "sql": s} for n, t, s in indexes]
    lines.append("indexes:")
    lines.extend(f"  {t}.{n}: {s}" for n, t, s in indexes)
    stat1 = conn.execute("SELECT tbl, idx, stat FROM sqlite_stat1 WHERE tbl IN ('vfs_chunks','vfs_entries') ORDER BY tbl, idx").fetchall()
    report["sqlite_stat1"] = [{"tbl": t, "idx": i, "stat": s} for t, i, s in stat1]
    lines.append("sqlite_stat1:")
    lines.extend(f"  {t} {i}: {s}" for t, i, s in stat1)

    db = native.open(db_path)
    report["statements"] = {}
    max_id = counts["max_chunk_id"]
    offsets = [0, max_id // 10, max_id // 4, max_id // 2, (3 * max_id) // 4, max_id - 2000]
    for name, sql in STATEMENTS.items():
        lines.append("")
        lines.append(f"== {name}")
        lines.append(sql)
        explained = plan_and_opcodes(conn, sql)
        lines.append("EXPLAIN QUERY PLAN:")
        lines.extend(f"  {p}" for p in explained["plan"])
        lines.append(f"EXPLAIN opcodes: {explained['opcodes']}")
        entry: dict[str, object] = {"sql": sql, **explained, "pages": []}
        # Warm the cache on this statement once, then measure each offset three times and keep the median.
        native.run_page(db, sql, 0, 256)
        for last in offsets:
            runs = [native.run_page(db, sql, last, 256) for _ in range(3)]
            median = sorted(runs, key=lambda r: r["wall_ms"])[1]
            entry["pages"].append(median)
            lines.append(
                f"  last={last:>8} rows={median['rows']:>3} content_bytes={median['content_bytes']:>7} wall_ms={median['wall_ms']:>8.3f} "
                f"fullscan_step={median['fullscan_step']} sort={median['sort']} autoindex={median['autoindex']} vm_step={median['vm_step']} "
                f"filter_miss={median['filter_miss']} filter_hit={median['filter_hit']}"
            )
        for limit in (1024, 4096, 16384):
            runs = [native.run_page(db, sql, max_id // 2, limit) for _ in range(3)]
            median = sorted(runs, key=lambda r: r["wall_ms"])[1]
            entry["pages"].append(median)
            lines.append(
                f"  last={max_id // 2:>8} limit={limit:>5} rows={median['rows']:>5} content_bytes={median['content_bytes']:>8} wall_ms={median['wall_ms']:>8.3f} "
                f"fullscan_step={median['fullscan_step']} sort={median['sort']} vm_step={median['vm_step']}"
            )
        report["statements"][name] = entry

    # A full keyset walk of the shipped statement, 256 a page, in-process: the scan's floor with no driver.
    lines.append("")
    lines.append("== full keyset walk of shipped_join, 256 a page, in-process ctypes")
    walk = {"pages": 0, "rows": 0, "content_bytes": 0, "walls_ms": [], "vm_step": 0, "fullscan_step": 0}
    last = 0
    t0 = time.perf_counter()
    while True:
        page = native.run_page(db, STATEMENTS["shipped_join"], last, 256)
        walk["pages"] += 1
        walk["walls_ms"].append(page["wall_ms"])
        walk["vm_step"] += page["vm_step"]
        walk["fullscan_step"] += page["fullscan_step"]
        if page["rows"] == 0:
            break
        walk["rows"] += page["rows"]
        walk["content_bytes"] += page["content_bytes"]
        last = page["last_id"]
    walk["wall_s"] = round(time.perf_counter() - t0, 3)
    walls = walk.pop("walls_ms")
    walk["page_ms_median"] = round(statistics.median(walls), 3)
    walk["page_ms_p99"] = round(sorted(walls)[min(len(walls) - 1, round(0.99 * (len(walls) - 1)))], 3)
    walk["page_ms_max"] = round(max(walls), 3)
    report["full_walk_shipped_256"] = walk
    lines.append(json.dumps(walk))

    lines.append("")
    lines.append("== full keyset walk of chunks_alone, 256 a page, in-process ctypes")
    walk2 = {"pages": 0, "rows": 0, "content_bytes": 0, "vm_step": 0}
    last = 0
    t0 = time.perf_counter()
    while True:
        page = native.run_page(db, STATEMENTS["chunks_alone"], last, 256)
        walk2["pages"] += 1
        walk2["vm_step"] += page["vm_step"]
        if page["rows"] == 0:
            break
        walk2["rows"] += page["rows"]
        walk2["content_bytes"] += page["content_bytes"]
        last = page["last_id"]
    walk2["wall_s"] = round(time.perf_counter() - t0, 3)
    report["full_walk_chunks_alone_256"] = walk2
    lines.append(json.dumps(walk2))

    native.lib.sqlite3_close(db)
    conn.close()
    out_text.write_text("\n".join(lines) + "\n")
    out_json.write_text(json.dumps(report, indent=2) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
