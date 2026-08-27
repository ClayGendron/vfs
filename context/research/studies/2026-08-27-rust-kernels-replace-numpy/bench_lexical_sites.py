"""Sites 3, 4 and 5 on the full linux store: summary decode, block selection, BM25 scoring.

Queries are drawn the way the spec 130 landing drew them (seed 7):
1-term = one mid-df term (0.2–2 % of chunks); 3-term = two mid + one
common (> 20 %); 6-term = one rare + four mid + one common; plus the
adversarial all-common ``struct if``. Every term's blocks are fetched
whole once, then:

- site 3: ``decode_summary`` over the query's summary blobs;
- site 5: the scorer over every fetched block at k = 10 and K = 1,000,
  numpy (``pure_score_blocks``) vs stdlib (full and block-skip
  spellings) vs Rust (``vfs._native.lexical_score``);
- site 4: the two-round protocol — heads (block_no < 8) scored, then
  ``competing_blocks`` per overflowing term — numpy vs stdlib vs Rust.

Results are asserted identical across arms before timing.
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import vfs_kernels_rs as rs
from sqlalchemy import select

import kernels_py as kp
from benchlib import DB, REPEATS, dump, machine, peak_kb, timed_ms
from vfs import _native
from vfs.models.lexical import ScoreBlock, competing_blocks, decode_summary, pure_score_blocks
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.lexical import lexical_stats

HEAD_BLOCKS = 8
PER_ARITY = 10


def draw_queries(con: sqlite3.Connection, seed: int = 7) -> dict[str, list[list[str]]]:
    n = con.execute("SELECT n_docs FROM vfs_lex_stats").fetchone()[0]
    rows = con.execute("SELECT term, df FROM vfs_lex_df").fetchall()
    mid = [t for t, df in rows if 0.002 * n <= df <= 0.02 * n]
    common = [t for t, df in rows if df > 0.2 * n]
    rare = [t for t, df in rows if 2 <= df < 0.002 * n]
    rng = random.Random(seed)
    out: dict[str, list[list[str]]] = {"1": [], "3": [], "6": []}
    for _ in range(PER_ARITY):
        out["1"].append([rng.choice(mid)])
        out["3"].append(rng.sample(mid, 2) + [rng.choice(common)])
        out["6"].append([rng.choice(rare)] + rng.sample(mid, 4) + [rng.choice(common)])
    return out


async def fetch_all(storage, epoch, terms):
    tables = storage._host.tables
    postings = tables.lex_postings
    async with storage._host.session_factory() as session:
        stats = await lexical_stats(session, tables, epoch, terms, 500)
        present = [t for t in terms if t in stats.terms]
        summaries = {t: decode_summary(stats.terms[t].blocks) for t in present}
        fetched = (
            select(postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)
            .where(postings.c.epoch == epoch, postings.c.term.in_(present))
            .order_by(postings.c.term, postings.c.block_no)
        )
        by_term = {t: [] for t in present}
        for row in await session.execute(fetched):
            bound = float(summaries[row.term].max_weights[row.block_no])
            by_term[row.term].append(
                ScoreBlock(present.index(row.term), bound, bytes(row.doc_ids), bytes(row.tfs), bytes(row.dls))
            )
    idfs = [stats.terms[t].idf for t in present]
    blobs = {t: stats.terms[t].blocks for t in present}
    return present, by_term, summaries, blobs, idfs, stats.avg_dl


def round_one(present, by_term, idfs, avg_dl, k):
    """Heads scored whole (k = ∞) → theta, sorted candidates, their scores."""
    heads = [b for t in present for b in by_term[t][:HEAD_BLOCKS]]
    everything = _native.lexical_score(heads, idfs, avg_dl, 10**9)
    theta = everything[k - 1][1] if len(everything) >= k else 0.0
    scores_of = dict(everything)
    cands = sorted(scores_of)
    return heads, theta, cands, [scores_of[c] for c in cands]


def site4_arms(present, by_term, summaries, blobs, idfs, avg_dl, k):
    heads, theta, cands, tail = round_one(present, by_term, idfs, avg_dl, k)
    overflowing = sorted(
        (t for t in present if len(by_term[t]) > HEAD_BLOCKS), key=lambda t: -float(summaries[t].max_weights.max())
    )
    if not overflowing:
        return None
    rests = {
        t: sum(float(summaries[o].max_weights.max()) for o in overflowing[i + 1 :]) for i, t in enumerate(overflowing)
    }
    cands_np = np.asarray(cands, dtype=np.int64)
    tail_np = np.asarray(tail, dtype=np.float64)
    py_sum = {t: kp.decode_summary(blobs[t]) for t in overflowing}
    rs_sum = {t: rs.decode_summary(blobs[t]) for t in overflowing}
    cands_q, tail_d = kp.to_q(cands), kp.to_d(tail)

    def run_numpy():
        return [competing_blocks(summaries[t], cands_np, tail_np, theta, rests[t]).tolist() for t in overflowing]

    def run_stdlib():
        return [kp.competing_blocks(*py_sum[t], cands, tail, theta, rests[t]) for t in overflowing]

    def run_rust():
        return [kp.from_q(rs.competing_blocks(*rs_sum[t], cands_q, tail_d, theta, rests[t])) for t in overflowing]

    a, b, c = run_numpy(), run_stdlib(), run_rust()
    assert a == b == c, "competing_blocks arms disagree"
    return {
        "overflowing_terms": len(overflowing),
        "summary_blocks": sum(len(summaries[t].first_ids) for t in overflowing),
        "candidates": len(cands),
        "competing": sum(len(x) for x in a),
        "numpy_ms": timed_ms(run_numpy),
        "stdlib_ms": timed_ms(run_stdlib),
        "rust_ms": timed_ms(run_rust),
    }


def med(rows, key):
    vals = [r[key] for r in rows if r is not None and key in r]
    return round(statistics.median(vals), 3) if vals else None


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    queries = draw_queries(con)
    commonest = [t for t, _ in con.execute("SELECT term, df FROM vfs_lex_df ORDER BY df DESC LIMIT 2")]
    queries["all_common"] = [commonest]
    chunk_ids = [r[0] for r in con.execute("SELECT chunk_id FROM vfs_lex_docs ORDER BY chunk_id")]
    cand_set = sorted(random.Random(3).sample(chunk_ids, 5000))
    async with storage._host.session_factory() as session:
        epoch = await current_epoch(session, storage._host.tables)

    per_query = []
    for arity, qs in queries.items():
        for terms in qs:
            present, by_term, summaries, blobs, idfs, avg_dl = await fetch_all(storage, epoch, terms)
            blocks = [b for t in present for b in by_term[t]]
            row = {"arity": arity, "terms": present, "blocks": len(blocks), "postings": 0}
            row["postings"] = sum(len(kp.decode_postings_fused(b.doc_ids)) for b in blocks)
            # --- site 3 ---------------------------------------------------
            sblobs = [blobs[t] for t in present]
            ref = [(s.first_ids.tolist(), s.max_weights.tolist()) for s in (decode_summary(b) for b in sblobs)]
            assert ref == [kp.decode_summary(b) for b in sblobs]
            assert ref == [(kp.from_q(f), kp.from_d(m)) for f, m in (rs.decode_summary(b) for b in sblobs)]
            row["summary_blocks"] = sum(len(f) for f, _ in ref)
            row["summary_numpy_ms"] = timed_ms(lambda: [decode_summary(b) for b in sblobs])
            row["summary_stdlib_ms"] = timed_ms(lambda: [kp.decode_summary(b) for b in sblobs])
            row["summary_rust_ms"] = timed_ms(lambda: [rs.decode_summary(b) for b in sblobs])
            row["summary_rust_tolist_ms"] = timed_ms(
                lambda: [(kp.from_q(f), kp.from_d(m)) for f, m in (rs.decode_summary(b) for b in sblobs)]
            )
            # --- site 5 ---------------------------------------------------
            for k in (10, 1000):
                a = pure_score_blocks(blocks, idfs, avg_dl, k)
                b_ = kp.score_blocks_full(blocks, idfs, avg_dl, k)
                c = kp.score_blocks_skip(blocks, idfs, avg_dl, k)
                d = _native.lexical_score(blocks, idfs, avg_dl, k)
                assert a == b_ == c == d, f"scorer arms disagree at k={k}"
                row[f"score_k{k}_numpy_ms"] = timed_ms(lambda: pure_score_blocks(blocks, idfs, avg_dl, k))
                row[f"score_k{k}_stdlib_full_ms"] = timed_ms(lambda: kp.score_blocks_full(blocks, idfs, avg_dl, k))
                row[f"score_k{k}_stdlib_skip_ms"] = timed_ms(lambda: kp.score_blocks_skip(blocks, idfs, avg_dl, k))
                row[f"score_k{k}_rust_ms"] = timed_ms(lambda: _native.lexical_score(blocks, idfs, avg_dl, k))
            row["score_k10_numpy_peak_kb"] = peak_kb(lambda: pure_score_blocks(blocks, idfs, avg_dl, 10))
            row["score_k10_stdlib_skip_peak_kb"] = peak_kb(lambda: kp.score_blocks_skip(blocks, idfs, avg_dl, 10))
            cnp = np.asarray(cand_set, dtype=np.int64)
            a = pure_score_blocks(blocks, idfs, avg_dl, 10, candidates=cnp)
            assert a == kp.score_blocks_skip(blocks, idfs, avg_dl, 10, candidates=cand_set)
            assert a == _native.lexical_score(blocks, idfs, avg_dl, 10, cnp.tobytes())
            row["score_cand_numpy_ms"] = timed_ms(lambda: pure_score_blocks(blocks, idfs, avg_dl, 10, candidates=cnp))
            row["score_cand_stdlib_skip_ms"] = timed_ms(
                lambda: kp.score_blocks_skip(blocks, idfs, avg_dl, 10, candidates=cand_set)
            )
            row["score_cand_rust_ms"] = timed_ms(lambda: _native.lexical_score(blocks, idfs, avg_dl, 10, cnp.tobytes()))
            # --- site 4 ---------------------------------------------------
            for k in (10, 1000):
                s4 = site4_arms(present, by_term, summaries, blobs, idfs, avg_dl, k)
                if s4 is not None:
                    row[f"select_k{k}"] = s4
            per_query.append(row)
            print(
                f"{arity:<10} blocks={len(blocks):>5} post={row['postings']:>7,} | summary np={row['summary_numpy_ms']:.3f} "
                f"py={row['summary_stdlib_ms']:.3f} rs={row['summary_rust_ms']:.3f} | k10 np={row['score_k10_numpy_ms']:.2f} "
                f"pyfull={row['score_k10_stdlib_full_ms']:.2f} pyskip={row['score_k10_stdlib_skip_ms']:.2f} "
                f"rs={row['score_k10_rust_ms']:.2f} | K1000 np={row['score_k1000_numpy_ms']:.2f} "
                f"pyskip={row['score_k1000_stdlib_skip_ms']:.2f} rs={row['score_k1000_rust_ms']:.2f} | "
                f"sel10 {row.get('select_k10', {}).get('numpy_ms', '-')}/{row.get('select_k10', {}).get('stdlib_ms', '-')}/"
                f"{row.get('select_k10', {}).get('rust_ms', '-')}",
                flush=True,
            )

    summary = {}
    for arity in queries:
        rows = [r for r in per_query if r["arity"] == arity]
        keys = [k for k in rows[0] if k.endswith("_ms") or k.endswith("_kb") or k in ("blocks", "postings", "summary_blocks")]
        summary[arity] = {k: med(rows, k) for k in keys}
        for kk in ("select_k10", "select_k1000"):
            sub = [r[kk] for r in rows if kk in r]
            if sub:
                summary[arity][kk] = {k: round(statistics.median([s[k] for s in sub]), 3) for k in sub[0]}
    # the commonest terms' summaries alone (site 3 at its widest)
    widest = []
    for t, blob in con.execute("SELECT term, blocks FROM vfs_lex_df ORDER BY df DESC LIMIT 3"):
        widest.append(
            {
                "term": t,
                "blocks": len(kp.decode_summary(blob)[0]),
                "numpy_ms": timed_ms(lambda: decode_summary(blob)),
                "stdlib_ms": timed_ms(lambda: kp.decode_summary(blob)),
                "rust_ms": timed_ms(lambda: rs.decode_summary(blob)),
                "numpy_peak_kb": peak_kb(lambda: decode_summary(blob)),
                "stdlib_peak_kb": peak_kb(lambda: kp.decode_summary(blob)),
            }
        )
    await storage.close()
    dump(
        "lexical_sites.json",
        {"machine": machine(), "repeats": REPEATS, "summary": summary, "widest_summaries": widest, "per_query": per_query},
    )
    import json

    print(json.dumps(summary, indent=1))
    print(json.dumps(widest, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
