"""Experiment 3: tiered merge of delta segments.

Reuses exp2.db (base + 48 deltas of 500 docs). Merges 6 five-minute deltas
into one 30-minute segment, with and without tombstone (ghost) dropping;
then builds the tiered layout (3x60min + 1x30min + 6x5min = 10 segments
over the same 24,000 docs) and reruns the exp2 queries at that K.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import decode_postings, encode_postings, open_store  # noqa: E402
import exp2_read  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DB = exp2_read.DB


def merge_segments(conn: sqlite3.Connection, sources: list[int], target: int, tombstones: set[int] | None) -> dict:
    """Merge `sources` into a new segment `target`: per gram, union the sorted id lists and re-encode.

    Streams gram-ordered rows from sqlite (ORDER BY gram_key) so memory is one gram's lists at a time.
    """
    t0 = time.perf_counter()
    q = f"SELECT gram_key, postings FROM posting_list WHERE segment IN ({','.join('?' * len(sources))}) ORDER BY gram_key"
    rows_in = bytes_in = rows_out = bytes_out = 0
    dropped = 0
    decode_s = union_s = encode_s = insert_s = 0.0
    out_rows = []
    cur_gram = None
    lists: list[list[int]] = []
    cur = conn.cursor()
    cur.execute("BEGIN")

    def flush():
        nonlocal rows_out, bytes_out, dropped, union_s, encode_s, insert_s
        if cur_gram is None:
            return
        t1 = time.perf_counter()
        if len(lists) == 1:
            ids = lists[0]
        else:
            ids = sorted(set().union(*lists))
        if tombstones:
            before = len(ids)
            ids = [i for i in ids if i not in tombstones]
            dropped += before - len(ids)
        t2 = time.perf_counter()
        if ids:
            blob = encode_postings(ids)
            out_rows.append((target, cur_gram, blob, len(ids), len(blob)))
            rows_out += 1
            bytes_out += len(blob)
        t3 = time.perf_counter()
        union_s += t2 - t1
        encode_s += t3 - t2
        if len(out_rows) >= 2000:
            t4 = time.perf_counter()
            cur.executemany("INSERT INTO posting_list VALUES (?,?,?,?,?)", out_rows)
            insert_s += time.perf_counter() - t4
            out_rows.clear()

    for gram, blob in conn.execute(q, sources):
        rows_in += 1
        bytes_in += len(blob)
        if gram != cur_gram:
            flush()
            cur_gram = gram
            lists = []
        td = time.perf_counter()
        lists.append(decode_postings(blob))
        decode_s += time.perf_counter() - td
    flush()
    if out_rows:
        cur.executemany("INSERT INTO posting_list VALUES (?,?,?,?,?)", out_rows)
    docs = sum(r[0] for r in conn.execute(f"SELECT doc_count FROM manifest WHERE segment IN ({','.join('?' * len(sources))})", sources))
    cur.execute("INSERT OR REPLACE INTO manifest VALUES (?,?,?,?)", (target, docs, rows_out, bytes_out))
    cur.execute("COMMIT")
    return {
        "sources": sources,
        "target": target,
        "tombstones": len(tombstones or ()),
        "rows_in": rows_in,
        "bytes_in": bytes_in,
        "rows_out": rows_out,
        "bytes_out": bytes_out,
        "pairs_dropped": dropped,
        "decode_s": decode_s,
        "union_s": union_s,
        "encode_s": encode_s,
        "insert_s": insert_s,
        "total_s": time.perf_counter() - t0,
    }


if __name__ == "__main__":
    with open(exp2_read.STATE) as fh:
        state = json.load(fh)
    seg_docs = {int(k): v for k, v in state["seg_docs"].items()}
    conn = open_store(DB)
    results: dict = {"merges": []}

    # Merge 6 deltas (1..6) with no tombstones -> segment 100.
    results["merges"].append(merge_segments(conn, list(range(1, 7)), 100, None))
    print(json.dumps(results["merges"][-1]), flush=True)
    # Same merge, dropping docs that were re-posted later (segments 7..48 re-post disjoint base ids, so
    # simulate tombstones: 20% of segment 1..6's docs "re-posted or deleted since").
    import random

    rng = random.Random(5)
    merged_docs = [d for s in range(1, 7) for d in seg_docs[s]]
    tomb = set(rng.sample(merged_docs, len(merged_docs) // 5))
    results["merges"].append(merge_segments(conn, list(range(1, 7)), 101, tomb))
    print(json.dumps(results["merges"][-1]), flush=True)
    conn.execute("DELETE FROM posting_list WHERE segment IN (100,101)")
    conn.execute("DELETE FROM manifest WHERE segment IN (100,101)")
    conn.commit()

    # Tiered layout over the same 48 deltas: 3 x 60min (12 deltas each), 1 x 30min (6), 6 x 5min.
    tier_segments = []
    t_tier = time.perf_counter()
    for i, lo in enumerate((1, 13, 25)):
        results["merges"].append(merge_segments(conn, list(range(lo, lo + 12)), 200 + i, None))
        tier_segments.append(200 + i)
    results["merges"].append(merge_segments(conn, list(range(37, 43)), 210, None))
    tier_segments.append(210)
    tier_segments.extend(range(43, 49))
    results["tier_build_s"] = time.perf_counter() - t_tier
    results["tier_segments"] = tier_segments
    print("tier segments", tier_segments, flush=True)

    # Rerun the exp2 queries against base + tiered segments, by temporarily using exactly that live set.
    # run_queries takes K and uses range(0, K+1); emulate by renumbering: copy tiered segments into a fresh store.
    tier_db = os.path.join(HERE, "exp3_tier.db")
    for f in (tier_db, tier_db + "-wal", tier_db + "-shm"):
        if os.path.exists(f):
            os.remove(f)
    conn.execute(f"ATTACH DATABASE '{tier_db}' AS tier")
    conn.executescript(
        "CREATE TABLE tier.posting_list (segment INTEGER NOT NULL, gram_key INTEGER NOT NULL, postings BLOB NOT NULL, doc_count INTEGER NOT NULL, byte_size INTEGER NOT NULL, PRIMARY KEY (segment, gram_key)) WITHOUT ROWID;"
        "CREATE TABLE tier.manifest (segment INTEGER PRIMARY KEY, doc_count INTEGER NOT NULL, row_count INTEGER NOT NULL, byte_total INTEGER NOT NULL);"
    )
    for new_no, old in enumerate([0, *tier_segments]):
        conn.execute("INSERT INTO tier.posting_list SELECT ?, gram_key, postings, doc_count, byte_size FROM main.posting_list WHERE segment=?", (new_no, old))
        conn.execute("INSERT INTO tier.manifest SELECT ?, doc_count, row_count, byte_total FROM main.manifest WHERE segment=?", (new_no, old))
    conn.commit()
    conn.close()
    exp2_read.DB = tier_db
    results["tier_queries"] = exp2_read.run_queries(state, (len(tier_segments),), covered=list(range(1, 49)))
    with open(os.path.join(HERE, "exp3_results.json"), "w") as fh:
        json.dump(results, fh, indent=1)
