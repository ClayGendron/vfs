"""Validate the spec-130b review's four claims on the prototype's block store.

Runs over ``optionb_rs.sqlite`` (block 128, the design's reference build)
and the drawn 1/3/6-term queries of the benchmark:

1. **Fetch filter** — does ``WHERE max_weight >= θ`` (one scalar θ, the
   final top-10 floor) change any top-10? How many blocks does the
   WAND-correct per-term cut ``θ − Σ other terms' maxima`` actually skip,
   against the 65 % the docid-aligned in-memory block-max skipped?
2. **Scale** — the commonest terms' posting share, projected to the full
   linux checkout and to 10 M chunks in blob bytes; and for an
   all-common-terms query, how many blocks an impact-ordered fetch over
   summaries needs before top-10 saturates.
3. **Bound tightness** — ``idf · tfc(max_tf, min_dl)`` against the true
   per-block maximum, and how much tighter the skips get with the truth.
4. **Aligned skip from summaries** — a block of term *t* whose id range
   holds no posting of any other query term and whose bound is under θ
   can be left unfetched without decoding anything: the fraction of
   blocks (and bytes) that rule leaves in the engine.

    uv run --no-sync python review_validation.py
"""

from __future__ import annotations

import bisect
import json
import sqlite3
import statistics

import numpy as np

from common import (
    EPOCH_A,
    EPOCH_B,
    OPTION_B_RS,
    STORE,
    TOP_K,
    block_bound,
    decode_block,
    draw_queries,
    dump_json,
    tf_norm,
)

BLOCK_SQL = (
    "SELECT term, block_no, doc_count, max_tf, min_dl, doc_ids, tfs, dls "
    "FROM lex_postings WHERE epoch = ? AND term = ? ORDER BY block_no"
)


class Blk:
    __slots__ = ("bound", "bytes", "ids", "lo", "hi", "term", "true_max", "weights")

    def __init__(self, term: str, idf_t: float, avg_dl: float, row: tuple) -> None:
        _t, _no, _count, max_tf, min_dl, ids_b, tfs_b, dls_b = row
        ids, tfs, dls = decode_block(ids_b, tfs_b, dls_b)
        self.term = term
        self.ids = ids
        self.weights = idf_t * tf_norm(tfs, dls, avg_dl)
        self.bound = block_bound(idf_t, max_tf, min_dl, avg_dl)
        self.true_max = float(self.weights.max())
        self.lo, self.hi = int(ids[0]), int(ids[-1])
        self.bytes = len(ids_b) + len(tfs_b) + len(dls_b)


def load(conn: sqlite3.Connection, terms: list[str], idfs: dict[str, float], avg_dl: float) -> list[Blk]:
    out: list[Blk] = []
    for term in terms:
        out += [Blk(term, idfs[term], avg_dl, row) for row in conn.execute(BLOCK_SQL, (EPOCH_B, term))]
    return out


def score(blocks: list[Blk]) -> tuple[list[tuple[int, float]], float]:
    """Exact top-10 over *blocks* and the k-th score (0.0 when fewer than k docs)."""
    if not blocks:
        return [], 0.0
    ids = np.concatenate([b.ids for b in blocks])
    ws = np.concatenate([b.weights for b in blocks])
    uniq, inverse = np.unique(ids, return_inverse=True)
    agg = np.bincount(inverse, weights=ws, minlength=uniq.size)
    order = np.lexsort((uniq, -agg))[:TOP_K]
    top = [(int(uniq[i]), round(float(agg[i]), 9)) for i in order]  # rounded: the impact path compares against it
    theta = top[-1][1] if len(top) == TOP_K else 0.0
    return top, theta


def aligned_skips(blocks: list[Blk], theta: float, use_true: bool) -> tuple[int, int]:
    """Blocks left unfetched by the summary rule: bound < θ and no other
    query term posts inside the block's id range. Returns (blocks, bytes)."""
    by_term: dict[str, list[Blk]] = {}
    for b in blocks:
        by_term.setdefault(b.term, []).append(b)
    others: dict[str, np.ndarray] = {}
    for term in by_term:
        rest = [b.ids for b in blocks if b.term != term]
        others[term] = np.sort(np.concatenate(rest)) if rest else np.empty(0, dtype=np.int64)
    skipped = skipped_bytes = 0
    for b in blocks:
        bound = b.true_max if use_true else b.bound
        if bound >= theta:
            continue
        o = others[b.term]
        i = bisect.bisect_left(o.tolist(), b.lo) if o.size < 64 else int(np.searchsorted(o, b.lo))
        if i < o.size and int(o[i]) <= b.hi:
            continue
        skipped += 1
        skipped_bytes += b.bytes
    return skipped, skipped_bytes


def two_round(blocks: list[Blk], use_true: bool, progressive: bool) -> tuple[int, int, int, int]:
    """The reviewer's fetch: every term but the commonest is fetched whole
    (round one) and scored; the commonest term's blocks are then fetched
    only when they can still change the top-10 — the block alone clears θ,
    or a candidate inside its id range could cross θ with its help. The
    progressive variant re-scores after each fetched block (a longer
    conversation with the engine); the batched one decides once. Returns
    (common blocks, common blocks skipped, common bytes, common bytes skipped)."""
    by_term: dict[str, list[Blk]] = {}
    for b in blocks:
        by_term.setdefault(b.term, []).append(b)
    if len(by_term) < 2:
        return 0, 0, 0, 0
    common = max(by_term, key=lambda t: sum(x.ids.size for x in by_term[t]))
    first = [x for x in blocks if x.term != common]
    ids = np.concatenate([x.ids for x in first])
    ws = np.concatenate([x.weights for x in first])
    cand_ids, inverse = np.unique(ids, return_inverse=True)
    cand_scores = np.bincount(inverse, weights=ws, minlength=cand_ids.size)

    def theta() -> float:
        if cand_scores.size < TOP_K:
            return 0.0
        return float(np.partition(cand_scores, cand_scores.size - TOP_K)[cand_scores.size - TOP_K])

    th = theta()
    skipped = skipped_bytes = 0
    rest = by_term[common]
    for x in rest:
        ub = x.true_max if use_true else x.bound
        if ub < th:
            lo = int(np.searchsorted(cand_ids, x.lo, side="left"))
            hi = int(np.searchsorted(cand_ids, x.hi, side="right"))
            if lo == hi or float(cand_scores[lo:hi].max()) + ub < th:
                skipped += 1
                skipped_bytes += x.bytes
                continue
        if progressive:
            merged_ids = np.concatenate([cand_ids, x.ids])
            merged_ws = np.concatenate([cand_scores, x.weights])
            cand_ids, inverse = np.unique(merged_ids, return_inverse=True)
            cand_scores = np.bincount(inverse, weights=merged_ws, minlength=cand_ids.size)
            th = theta()
    return len(rest), skipped, sum(x.bytes for x in rest), skipped_bytes


def impact_ordered_fetch(blocks: list[Blk]) -> dict:
    """Fetch blocks by true max descending (across terms) until no doc,
    fetched or not, can still enter or reorder the top-10; every
    unfetched contribution is bounded by the summary's per-block max."""
    by_term: dict[str, list[Blk]] = {}
    for b in blocks:
        by_term.setdefault(b.term, []).append(b)
    for bs in by_term.values():
        bs.sort(key=lambda b: b.lo)
    starts = {t: [b.lo for b in bs] for t, bs in by_term.items()}
    fetched: set[int] = set()
    partial: dict[int, float] = {}
    order = sorted(range(len(blocks)), key=lambda i: -blocks[i].true_max)
    fetched_bytes = 0
    for step, i in enumerate(order, start=1):
        b = blocks[i]
        fetched.add(id(b))
        fetched_bytes += b.bytes
        for doc, w in zip(b.ids.tolist(), b.weights.tolist(), strict=True):
            partial[doc] = partial.get(doc, 0.0) + w
        # Unfetched max per term, and the unfetched block covering a doc.
        unf = {t: max((x.true_max for x in bs if id(x) not in fetched), default=0.0) for t, bs in by_term.items()}
        top = sorted(partial.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_K]
        if len(top) < TOP_K:
            continue
        theta = top[-1][1]
        if sum(unf.values()) >= theta:
            continue  # an unseen doc could still enter

        def upper(doc: int) -> float:
            total = partial[doc]
            for t, bs in by_term.items():
                j = bisect.bisect_right(starts[t], doc) - 1
                if j >= 0 and bs[j].lo <= doc <= bs[j].hi and id(bs[j]) not in fetched:
                    total += bs[j].true_max
            return total

        if all(upper(doc) <= theta for doc in partial if doc not in {d for d, _ in top}) and all(
            upper(doc) == partial[doc] for doc, _ in top
        ):
            total_bytes = sum(x.bytes for x in blocks)
            return {
                "blocks_fetched": step,
                "blocks_total": len(blocks),
                "bytes_fetched": fetched_bytes,
                "bytes_total": total_bytes,
                "top10": [(d, round(v, 9)) for d, v in top],
            }
    return {"blocks_fetched": len(blocks), "blocks_total": len(blocks), "exhausted": True}


def main() -> None:
    b = sqlite3.connect(OPTION_B_RS)
    a = sqlite3.connect(STORE)
    n_docs, avg_dl = b.execute("SELECT n_docs, avg_dl FROM lex_stats WHERE epoch = ?", (EPOCH_B,)).fetchone()
    idfs = dict(b.execute("SELECT term, idf FROM lex_df WHERE epoch = ?", (EPOCH_B,)))
    dfs = dict(b.execute("SELECT term, df FROM lex_df WHERE epoch = ?", (EPOCH_B,)))
    queries = draw_queries(a, EPOCH_A)

    # --- 1 & 3 & 4: per-query filter analyses -------------------------------
    per_arity: dict[int, dict] = {}
    for arity, qs in queries.items():
        acc: dict[str, list] = {k: [] for k in ("single_theta_wrong", "single_skip", "cut_skip", "cut_skip_true", "aligned_skip", "aligned_bytes", "aligned_skip_true", "aligned_bytes_true", "inmem_skip", "blocks", "bytes")}
        for terms in qs:
            blocks = load(b, terms, idfs, avg_dl)
            exact, theta = score(blocks)
            acc["blocks"].append(len(blocks))
            acc["bytes"].append(sum(x.bytes for x in blocks))
            # (1a) one scalar θ as a per-row filter.
            kept = [x for x in blocks if x.bound >= theta]
            top_filtered, _ = score(kept)
            acc["single_theta_wrong"].append(top_filtered != exact)
            acc["single_skip"].append(len(blocks) - len(kept))
            # (1b) the per-term MaxScore cut, with the loose bound and the true max.
            for key, attr in (("cut_skip", "bound"), ("cut_skip_true", "true_max")):
                term_max = {}
                for x in blocks:
                    term_max[x.term] = max(term_max.get(x.term, 0.0), getattr(x, attr))
                total = sum(term_max.values())
                skips = sum(1 for x in blocks if getattr(x, attr) < theta - (total - term_max[x.term]))
                acc[key].append(skips)
            # (4) the summary rule (no decode needed): bound under θ and no other term in range.
            s, sb = aligned_skips(blocks, theta, use_true=False)
            acc["aligned_skip"].append(s)
            acc["aligned_bytes"].append(sb)
            s, sb = aligned_skips(blocks, theta, use_true=True)
            acc["aligned_skip_true"].append(s)
            acc["aligned_bytes_true"].append(sb)
            for key, use_true, progressive in (
                ("two_round", False, False),
                ("two_round_true", True, False),
                ("two_round_prog", False, True),
                ("two_round_prog_true", True, True),
            ):
                n, s, nb, sb = two_round(blocks, use_true, progressive)
                acc.setdefault(key, []).append((n, s, nb, sb))
        per_arity[arity] = {
            "queries": len(qs),
            "blocks_median": statistics.median(acc["blocks"]),
            "single_theta_top10_changed": sum(acc["single_theta_wrong"]),
            "single_theta_skip_pct": round(100 * sum(acc["single_skip"]) / sum(acc["blocks"]), 1),
            "per_term_cut_skip_pct": round(100 * sum(acc["cut_skip"]) / sum(acc["blocks"]), 1),
            "per_term_cut_skip_pct_true_max": round(100 * sum(acc["cut_skip_true"]) / sum(acc["blocks"]), 1),
            "aligned_skip_pct": round(100 * sum(acc["aligned_skip"]) / sum(acc["blocks"]), 1),
            "aligned_bytes_pct": round(100 * sum(acc["aligned_bytes"]) / sum(acc["bytes"]), 1),
            "aligned_skip_pct_true_max": round(100 * sum(acc["aligned_skip_true"]) / sum(acc["blocks"]), 1),
            "aligned_bytes_pct_true_max": round(100 * sum(acc["aligned_bytes_true"]) / sum(acc["bytes"]), 1),
            "common_term_blocks_pct_of_query": round(100 * sum(r[0] for r in acc["two_round"]) / sum(acc["blocks"]), 1),
            "common_term_bytes_pct_of_query": round(100 * sum(r[2] for r in acc["two_round"]) / sum(acc["bytes"]), 1),
            **{
                f"{key}_common_skip_pct": round(100 * sum(r[1] for r in acc[key]) / max(1, sum(r[0] for r in acc[key])), 1)
                for key in ("two_round", "two_round_true", "two_round_prog", "two_round_prog_true")
            },
            **{
                f"{key}_query_bytes_saved_pct": round(100 * sum(r[3] for r in acc[key]) / sum(acc["bytes"]), 1)
                for key in ("two_round", "two_round_true", "two_round_prog", "two_round_prog_true")
            },
        }

    # --- 3: bound tightness over every block ---------------------------------
    ratios = []
    for term, idf_t in idfs.items():
        if dfs[term] < 128:
            continue  # single partial blocks dominate the vocabulary; sample the multi-block terms
        for row in b.execute(BLOCK_SQL, (EPOCH_B, term)):
            blk = Blk(term, idf_t, avg_dl, row)
            ratios.append(blk.true_max / blk.bound)
    tight = {
        "blocks_sampled": len(ratios),
        "true_over_loose_median": round(statistics.median(ratios), 4),
        "true_over_loose_p10": round(float(np.percentile(ratios, 10)), 4),
        "true_over_loose_min": round(min(ratios), 4),
        "exact_share_pct": round(100 * sum(1 for r in ratios if r > 0.999999) / len(ratios), 1),
    }

    # --- 2: scale projection and the all-common query ------------------------
    common = sorted(dfs.items(), key=lambda kv: -kv[1])[:10]
    bytes_per_posting = 13_440_647 / sum(dfs.values())
    linux_chunks = 32_243 * (80_000 / 4_000)  # the sample is 4,000 of ~80k source files
    projection = [
        {
            "term": t,
            "df_share_pct": round(100 * df / n_docs, 1),
            "linux_blob_mb": round(df / n_docs * linux_chunks * bytes_per_posting / 2**20, 1),
            "ten_million_blob_mb": round(df / n_docs * 10_000_000 * bytes_per_posting / 2**20, 1),
            "ten_million_blocks": int(df / n_docs * 10_000_000 / 128),
        }
        for t, df in common
    ]
    two_common = [common[0][0], common[1][0]]
    blocks = load(b, two_common, idfs, avg_dl)
    impact = impact_ordered_fetch(blocks)
    exact, _ = score(blocks)
    impact["matches_exact"] = impact.get("top10") == exact

    payload = {
        "store": {"n_docs": n_docs, "avg_dl": avg_dl, "bytes_per_posting": round(bytes_per_posting, 3)},
        "filters_by_arity": per_arity,
        "bound_tightness": tight,
        "scale_projection": projection,
        "all_common_query": {"terms": two_common, **{k: v for k, v in impact.items() if k != "top10"}},
    }
    out = dump_json("review_validation.json", payload)
    print(json.dumps(payload, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
