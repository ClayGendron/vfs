"""Build the chunk-granularity gram posting family on the clone.

New tables only (proto_*); existing tables untouched. Doc ids are dense,
entry-major (sorted by entry path, then chunk_index), so each entry's
chunks form one contiguous doc-id interval. Gram emission is purely
chunk-local (no boundary tail) via the live engine behind vfs.native —
same fold, same codec, same builder as the live file-level build.
"""
from __future__ import annotations

import json
import time

import sqlite3

from vfs.native import active_core, folded_bytes, postings_builder

DB = "linux-chunk.sqlite"
EXTRACT_BATCH_BYTES = 32 * 1024 * 1024   # mirrors indexing._EXTRACT_BATCH_BYTES
POSTING_BATCH_BYTES = 1 << 20            # mirrors indexing._POSTING_BATCH_BYTES


def main() -> None:
    t_start = time.perf_counter()
    db = sqlite3.connect(DB)
    db.execute("pragma journal_mode=WAL")
    db.execute("pragma synchronous=OFF")
    db.execute("drop table if exists proto_chunk_postings")
    db.execute("drop table if exists proto_chunk_map")
    db.execute("drop table if exists proto_entry_intervals")
    db.execute(
        """create table proto_chunk_postings (
             gram_key integer primary key,
             postings blob not null,
             encoding smallint not null default 1,
             doc_count integer not null,
             byte_size integer not null)"""
    )
    db.execute(
        """create table proto_chunk_map (
             doc_id integer primary key,
             chunk_rowid integer not null,
             entry_sid integer not null,
             entry_id_hex text not null,
             path text not null,
             line_start integer not null,
             line_end integer not null,
             nbytes integer not null)"""
    )
    db.execute(
        """create table proto_entry_intervals (
             entry_sid integer primary key,
             doc_lo integer not null,
             doc_hi integer not null,
             path text not null)"""
    )
    db.commit()

    scan = db.execute(
        """select e.path, e.id as sid, hex(e.entry_id) as eid, c.id as crow,
                  c.chunk_index, c.line_start, c.line_end, c.content
           from vfs_chunks c join vfs e on e.entry_id = c.entry_id
           where e.encoded = 1
           order by e.path, c.chunk_index"""
    )
    builder = postings_builder()
    doc_id = 0
    batch: list[tuple[int, bytes]] = []
    batch_bytes = 0
    map_rows: list[tuple] = []
    intervals: dict[int, list] = {}
    fold_feed_s = 0.0
    n_chunks = 0
    t0 = time.perf_counter()
    for path, sid, eid, crow, _ci, ls, le, content in scan:
        doc_id += 1
        n_chunks += 1
        data = folded_bytes(content)
        batch.append((doc_id, data))
        batch_bytes += len(data)
        map_rows.append((doc_id, crow, sid, eid, path, ls, le, len(content.encode("utf-8"))))
        iv = intervals.get(sid)
        if iv is None:
            intervals[sid] = [doc_id, doc_id, path]
        else:
            iv[1] = doc_id
        if batch_bytes >= EXTRACT_BATCH_BYTES:
            builder.add_docs(batch)
            batch, batch_bytes = [], 0
        if len(map_rows) >= 50_000:
            db.executemany("insert into proto_chunk_map values (?,?,?,?,?,?,?,?)", map_rows)
            map_rows = []
            print(f"  fed {n_chunks} chunks", flush=True)
    if batch:
        builder.add_docs(batch)
    if map_rows:
        db.executemany("insert into proto_chunk_map values (?,?,?,?,?,?,?,?)", map_rows)
    db.executemany(
        "insert into proto_entry_intervals values (?,?,?,?)",
        [(sid, lo, hi, p) for sid, (lo, hi, p) in intervals.items()],
    )
    db.commit()
    fold_feed_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    rows_total = 0
    blob_bytes = 0
    while (drained := builder.next_batch(POSTING_BATCH_BYTES)) is not None:
        db.executemany(
            "insert into proto_chunk_postings (gram_key, postings, encoding, doc_count, byte_size) "
            "values (?,?,1,?,?)",
            [(gram, blob, doc_count, len(blob)) for gram, blob, doc_count in drained],
        )
        rows_total += len(drained)
        blob_bytes += sum(len(b) for b, in ((blob,) for _, blob, _ in drained))
    db.commit()
    db.execute("create index ix_proto_map_entry on proto_chunk_map (entry_sid)")
    db.commit()
    drain_s = time.perf_counter() - t0

    live_rows, live_bytes = db.execute(
        "select count(*), sum(byte_size) from vfs_grams_posting_list where epoch = (select current_gram_epoch from vfs_meta)"
    ).fetchone()
    total_s = time.perf_counter() - t_start
    out = {
        "engine": active_core(),
        "chunks_indexed": n_chunks,
        "entries_covered": len(intervals),
        "fold_feed_seconds": round(fold_feed_s, 2),
        "drain_insert_seconds": round(drain_s, 2),
        "total_seconds": round(total_s, 2),
        "chunk_posting_rows": rows_total,
        "chunk_blob_bytes": blob_bytes,
        "live_posting_rows": live_rows,
        "live_blob_bytes": live_bytes,
        "blob_ratio": round(blob_bytes / live_bytes, 3),
        "row_ratio": round(rows_total / live_rows, 3),
    }
    print(json.dumps(out, indent=2))
    with open("build_stats.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
