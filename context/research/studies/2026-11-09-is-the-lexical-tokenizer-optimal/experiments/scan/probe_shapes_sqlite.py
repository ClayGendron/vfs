"""Which spellings of the page statement make SQLite skip the per-execution Bloom filter.

Each shape keeps the same rows and order (chunks of covered entries,
ascending id, 256 a page) and is measured in-process through ctypes with
the statement-status counters, at one offset, three runs each, median
kept, plus a full keyset walk of the table for the shapes that drop the
filter. Usage: uv run python probe_shapes_sqlite.py <db path> <out json> <out text>
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

from explain_sqlite import FILTER, Native, plan_and_opcodes

COLS = "vfs_chunks.id, vfs_chunks.entry_id, vfs_chunks.content"
TAIL = "AND vfs_chunks.id > ? ORDER BY vfs_chunks.id LIMIT ?"

SHAPES = {
    "shipped_join": f"SELECT {COLS} FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id WHERE {FILTER} {TAIL}",
    "correlated_exists": (
        f"SELECT {COLS} FROM vfs_chunks WHERE EXISTS (SELECT 1 FROM vfs_entries WHERE vfs_entries.entry_id = vfs_chunks.entry_id AND {FILTER}) {TAIL}"
    ),
    "likelihood_0_99": (
        f"SELECT {COLS} FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id "
        "WHERE likelihood(vfs_entries.chunked = 1, 0.99) AND likelihood(vfs_entries.indexable = 1, 0.99) "
        f"AND likelihood(vfs_entries.deleted_at IS NULL, 0.99) {TAIL}"
    ),
    "likely": (
        f"SELECT {COLS} FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id "
        "WHERE likely(vfs_entries.chunked = 1) AND likely(vfs_entries.indexable = 1) "
        f"AND likely(vfs_entries.deleted_at IS NULL) {TAIL}"
    ),
    "unary_plus_terms": (
        f"SELECT {COLS} FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id "
        "WHERE +vfs_entries.chunked = 1 AND +vfs_entries.indexable = 1 AND +vfs_entries.deleted_at IS NULL "
        f"{TAIL}"
    ),
    "filter_in_on_clause": (
        f"SELECT {COLS} FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id AND {FILTER} "
        f"WHERE 1 {TAIL}"
    ),
    "scalar_subquery_filter": (
        f"SELECT {COLS} FROM vfs_chunks WHERE (SELECT 1 FROM vfs_entries WHERE vfs_entries.entry_id = vfs_chunks.entry_id AND {FILTER}) = 1 {TAIL}"
    ),
    "no_filter_join": (
        f"SELECT {COLS} FROM vfs_chunks JOIN vfs_entries ON vfs_entries.entry_id = vfs_chunks.entry_id WHERE 1 {TAIL}"
    ),
}


def main() -> None:
    db_path, out_json, out_text = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    native = Native()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db = native.open(db_path)
    max_id = conn.execute("SELECT max(id) FROM vfs_chunks").fetchone()[0]
    lines: list[str] = [f"python sqlite {sqlite3.sqlite_version}; ctypes {native.path} {native.version}"]
    report: dict[str, object] = {"python_sqlite_version": sqlite3.sqlite_version, "ctypes_lib_version": native.version, "shapes": {}}
    for name, sql in SHAPES.items():
        explained = plan_and_opcodes(conn, sql)
        native.run_page(db, sql, 0, 256)
        runs = [native.run_page(db, sql, max_id // 2, 256) for _ in range(3)]
        median = sorted(runs, key=lambda r: r["wall_ms"])[1]
        entry = {"sql": sql, **explained, "page": median}
        lines.append("")
        lines.append(f"== {name}")
        lines.append(sql)
        lines.extend(f"  {p}" for p in explained["plan"])
        lines.append(
            f"  page at last={max_id // 2}: rows={median['rows']} wall_ms={median['wall_ms']} vm_step={median['vm_step']} "
            f"fullscan_step={median['fullscan_step']} sort={median['sort']} filter_miss={median['filter_miss']} filter_hit={median['filter_hit']}"
        )
        if median["vm_step"] < 100_000 and name != "no_filter_join":
            walk = {"pages": 0, "rows": 0, "vm_step": 0, "walls_ms": []}
            last = 0
            t0 = time.perf_counter()
            while True:
                page = native.run_page(db, sql, last, 256)
                walk["pages"] += 1
                walk["vm_step"] += page["vm_step"]
                walk["walls_ms"].append(page["wall_ms"])
                if page["rows"] == 0:
                    break
                walk["rows"] += page["rows"]
                last = page["last_id"]
            walk["wall_s"] = round(time.perf_counter() - t0, 3)
            walls = walk.pop("walls_ms")
            walk["page_ms_median"] = round(statistics.median(walls), 3)
            walk["page_ms_max"] = round(max(walls), 3)
            entry["full_walk_256"] = walk
            lines.append(f"  full walk: {json.dumps(walk)}")
        report["shapes"][name] = entry
    native.lib.sqlite3_close(db)
    conn.close()
    out_text.write_text("\n".join(lines) + "\n")
    out_json.write_text(json.dumps(report, indent=2) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
