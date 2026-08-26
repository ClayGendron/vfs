"""Query-time bench on sqlite: Option A's in-SQL SUM(weight) top-10 against
Option B's block fetch + numpy scoring (full evaluation and block-max
skipping), with the ranking-agreement proof; then the fetched blocks are
handed to the Rust scorer for the decode+score comparison (no DB inside).

    uv run --no-sync python query_sqlite.py [reps]
"""

from __future__ import annotations

import io
import json
import sqlite3
import statistics
import struct
import subprocess
import sys

import numpy as np

from common import (
    EPOCH_A,
    EPOCH_B,
    OPTION_B_RS,
    RUSTBENCH,
    SCRATCH,
    STORE,
    TOP_K,
    draw_queries,
    dump_json,
    kendall_tau,
    round_top,
    score_blockmax,
    score_full,
    score_full_batched,
    timed,
)

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 7


def sql_a(terms: list[str]) -> str:
    marks = ", ".join("?" for _ in terms)
    return (
        f"SELECT chunk_id, SUM(weight) AS score FROM vfs_lex_terms WHERE epoch = {EPOCH_A} AND term IN ({marks}) "
        f"GROUP BY chunk_id ORDER BY score DESC, chunk_id LIMIT {TOP_K}"
    )


def sql_b(terms: list[str]) -> str:
    marks = ", ".join("?" for _ in terms)
    return f"SELECT term, block_no, doc_count, max_tf, min_dl, doc_ids, tfs, dls FROM lex_postings WHERE epoch = {EPOCH_B} AND term IN ({marks})"


def sql_df(terms: list[str]) -> str:
    marks = ", ".join("?" for _ in terms)
    return f"SELECT term, idf FROM lex_df WHERE epoch = {EPOCH_B} AND term IN ({marks})"


def pack_query(fh, avg_dl: float, idfs: dict[str, float], blocks) -> None:
    by_term: dict[str, list] = {}
    for b in blocks:
        by_term.setdefault(b[0], []).append(b)
    fh.write(struct.pack("<d", avg_dl))
    fh.write(struct.pack("<I", len(by_term)))
    for term, bs in by_term.items():
        fh.write(struct.pack("<d", idfs[term]))
        fh.write(struct.pack("<I", len(bs)))
        for _t, _no, count, max_tf, min_dl, ids, tfs, dls in bs:
            fh.write(struct.pack("<III", count, max_tf, min_dl))
            for blob in (ids, tfs, dls):
                fh.write(struct.pack("<I", len(blob)))
                fh.write(blob)


def main() -> None:
    store = sqlite3.connect(STORE)
    optb = sqlite3.connect(OPTION_B_RS)
    avg_dl = optb.execute("SELECT avg_dl FROM lex_stats").fetchone()[0]
    assert abs(avg_dl - store.execute("SELECT avg_dl FROM vfs_lex_stats").fetchone()[0]) < 1e-9
    queries = draw_queries(store, EPOCH_A)
    per_query: list[dict] = []
    bin_path = SCRATCH / "query_blocks.bin"
    packed: list[bytes] = []
    for arity, qs in queries.items():
        for terms in qs:
            a_ms, a_rows = timed(lambda: store.execute(sql_a(terms), terms).fetchall(), REPS)
            a_top = [(int(c), float(s)) for c, s in a_rows]

            def fetch():
                idfs = dict(optb.execute(sql_df(terms), terms).fetchall())
                return idfs, optb.execute(sql_b(terms), terms).fetchall()

            fetch_ms, (idfs, blocks) = timed(fetch, REPS)
            full_ms, (b_top, n_cands) = timed(lambda: score_full_batched(blocks, idfs, avg_dl), REPS)
            perblock_ms, (pb_top, _) = timed(lambda: score_full(blocks, idfs, avg_dl), REPS)
            assert round_top(pb_top) == round_top(b_top)
            bm_ms, (bm_top, decoded, skipped) = timed(lambda: score_blockmax(blocks, idfs, avg_dl), REPS)
            postings = sum(b[2] for b in blocks)
            blob_bytes = sum(len(b[5]) + len(b[6]) + len(b[7]) for b in blocks)
            a_r, b_r, bm_r = round_top(a_top), round_top(b_top), round_top(bm_top)
            per_query.append(
                {
                    "arity": arity,
                    "terms": terms,
                    "dfs": {t: int(store.execute("SELECT df FROM vfs_lex_df WHERE epoch=? AND term=?", (EPOCH_A, t)).fetchone()[0]) for t in terms},
                    "postings": postings,
                    "blocks": len(blocks),
                    "blob_bytes": blob_bytes,
                    "candidates": n_cands,
                    "a_ms": a_ms,
                    "b_fetch_ms": fetch_ms,
                    "b_full_score_ms": full_ms,
                    "b_full_score_perblock_ms": perblock_ms,
                    "b_full_total_ms": fetch_ms + full_ms,
                    "b_blockmax_score_ms": bm_ms,
                    "b_blockmax_total_ms": fetch_ms + bm_ms,
                    "blocks_decoded": decoded,
                    "blocks_skipped": skipped,
                    "a_top": a_r,
                    "agree_full": a_r == b_r,
                    "agree_blockmax": a_r == bm_r,
                    "tau_full": kendall_tau([i for i, _ in a_top], [i for i, _ in b_top]),
                    "tau_blockmax": kendall_tau([i for i, _ in a_top], [i for i, _ in bm_top]),
                    "max_abs_score_diff": max((abs(x[1] - y[1]) for x, y in zip(a_top, b_top)), default=0.0),
                }
            )
            buf = io.BytesIO()
            pack_query(buf, avg_dl, idfs, blocks)
            packed.append(buf.getvalue())
    with bin_path.open("wb") as fh:
        fh.write(struct.pack("<I", len(packed)))
        for p in packed:
            fh.write(p)
    # Rust decode+score over the same fetched blocks.
    rust = json.loads(subprocess.run([str(RUSTBENCH), "score", str(bin_path), str(REPS)], check=True, capture_output=True, text=True).stdout)
    for q, r in zip(per_query, rust):
        q["rust_full_score_ms"] = r["median_ms"]
        q["agree_rust"] = q["a_top"] == [(int(i), round(s, 9)) for i, s in r["top"]]
    summary = {}
    for arity in (1, 3, 6):
        rows = [q for q in per_query if q["arity"] == arity]
        summary[arity] = {
            "n": len(rows),
            "median_postings": statistics.median(q["postings"] for q in rows),
            "median_blocks": statistics.median(q["blocks"] for q in rows),
            "median_blob_bytes": statistics.median(q["blob_bytes"] for q in rows),
            "a_ms": statistics.median(q["a_ms"] for q in rows),
            "b_fetch_ms": statistics.median(q["b_fetch_ms"] for q in rows),
            "b_full_score_ms": statistics.median(q["b_full_score_ms"] for q in rows),
            "b_full_score_perblock_ms": statistics.median(q["b_full_score_perblock_ms"] for q in rows),
            "b_full_total_ms": statistics.median(q["b_full_total_ms"] for q in rows),
            "b_blockmax_score_ms": statistics.median(q["b_blockmax_score_ms"] for q in rows),
            "b_blockmax_total_ms": statistics.median(q["b_blockmax_total_ms"] for q in rows),
            "rust_full_score_ms": statistics.median(q["rust_full_score_ms"] for q in rows),
            "blocks_skipped_total": sum(q["blocks_skipped"] for q in rows),
            "blocks_total": sum(q["blocks"] for q in rows),
            "agree_full": sum(q["agree_full"] for q in rows),
            "agree_blockmax": sum(q["agree_blockmax"] for q in rows),
            "agree_rust": sum(q["agree_rust"] for q in rows),
            "min_tau_full": min(q["tau_full"] for q in rows),
            "min_tau_blockmax": min(q["tau_blockmax"] for q in rows),
            "max_abs_score_diff": max(q["max_abs_score_diff"] for q in rows),
        }
    out = dump_json("query_sqlite.json", {"reps": REPS, "summary": summary, "queries": per_query})
    print(json.dumps(summary, indent=1))
    print(out)


if __name__ == "__main__":
    main()
