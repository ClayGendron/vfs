"""Cross-mount merge simulation.

One corpus (SciFact) is split into three mounts — randomly, and by topic
(k-means on potion-8M embeddings). Each mount runs a *different* embedder,
different BM25 parameters and a different in-mount fusion function, and
exposes a score on its own scale. The router only sees each mount's top-m
(m in {10, 20, 50}); every merge strategy must produce the corpus top-10 from
those lists. Strategies are scored with ranx against the single-index oracle
(mount A's hybrid stack over the whole corpus).

    uv run --python <venv>/bin/python sim_merge.py  > results.md
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict

import numpy as np
from ranx import Qrels, Run, evaluate

from common import (
    SEED,
    Hit,
    Lexical,
    Mount,
    MountConfig,
    embed_all,
    kmeans_split,
    load_scifact,
    minmax,
    rank_desc,
    rrf_from_ranks,
    zscore,
)

LIMITS = (10, 20, 50)
TOP = 10
METRICS = ["ndcg@10", "mrr@10", "recall@10"]

# Three deliberately heterogeneous mounts. A ~ a Postgres+pgvector mount
# (RRF in SQL); B ~ a SQLite mount fusing with a convex combination in [0,1];
# C ~ the GENERIC floor: hashing embedder, loose BM25, RRF with a small k,
# and a score scaled x100 so a naive sort is dominated by it.
MOUNTS = [
    MountConfig("A:potion8M/bm25(1.2,.75)/rrf60", "potion-8M", 1.2, 0.75, "rrf", k=60),
    MountConfig("B:potion4M/bm25(.9,.4)/cc-minmax", "potion-4M", 0.9, 0.4, "cc-minmax", alpha=0.5),
    MountConfig("C:hash256/bm25(2.0,1.0)/rrf10x100", "hash-256", 2.0, 1.0, "rrf", k=10, scale=100.0),
]
MOUNTS_LEXONLY_C = [
    MOUNTS[0],
    MOUNTS[1],
    MountConfig("C:lexical-only bm25(2.0,1.0)", "hash-256", 2.0, 1.0, "lexical-only"),
]


# ---------------------------------------------------------------------------
# Merge strategies: (hits per mount) -> ordered global doc ids
# ---------------------------------------------------------------------------


def merge_naive(lists, ctx):
    """Today's Result.top: one sort by each mount's exposed score."""
    hits = [h for l in lists for h in l]
    hits.sort(key=lambda h: (-h.score, h.mount, h.rank))
    return [h.doc for h in hits]


def merge_round_robin(lists, ctx):
    out = []
    for r in range(max(len(l) for l in lists)):
        for l in lists:
            if r < len(l):
                out.append(l[r].doc)
    return out


def merge_rrf(lists, ctx, k=60.0):
    """RRF across mount lists. Mounts are disjoint, so every doc has one
    rank: this is rank interleaving with ties broken by mount order."""
    sc = rrf_from_ranks([{h.doc: h.rank for h in l} for l in lists], k)
    return sorted(sc, key=lambda d: (-sc[d], d))


def _merge_norm(lists, norm):
    hits, scores = [], []
    for l in lists:
        if not l:
            continue
        s = norm(np.array([h.score for h in l], dtype=np.float64))
        hits.extend(l)
        scores.extend(s.tolist())
    order = sorted(range(len(hits)), key=lambda i: (-scores[i], hits[i].mount, hits[i].rank))
    return [hits[i].doc for i in order]


def merge_minmax(lists, ctx):
    return _merge_norm(lists, minmax)


def merge_zscore(lists, ctx):
    return _merge_norm(lists, zscore)


def _union_bm25(lists, ctx, k1=1.2, b=0.75):
    """Clay's reranker: BM25 built over the union's own text only."""
    docs = [h.doc for l in lists for h in l]
    lex = Lexical([ctx["texts"][d] for d in docs], k1, b)
    return docs, lex.scores(ctx["query"])


def merge_clay_union_bm25(lists, ctx):
    docs, s = _union_bm25(lists, ctx)
    local_rank = {h.doc: (h.mount, h.rank) for l in lists for h in l}
    order = sorted(range(len(docs)), key=lambda i: (-s[i], local_rank[docs[i]]))
    return [docs[i] for i in order]


def merge_global_bm25(lists, ctx):
    """Same rerank, but with corpus-wide BM25 statistics (the mounts export
    df/avgdl, or the router keeps a global lexical index)."""
    docs = [h.doc for l in lists for h in l]
    s = ctx["global_bm25"][docs]
    local_rank = {h.doc: (h.mount, h.rank) for l in lists for h in l}
    order = sorted(range(len(docs)), key=lambda i: (-s[i], local_rank[docs[i]]))
    return [docs[i] for i in order]


def merge_union_fusion_rrf(lists, ctx, k=60.0):
    """Union + in-process fusion: RRF of (in-process BM25 rank over the union)
    and (rank by per-mount min-max normalised vector cosine)."""
    docs, s = _union_bm25(lists, ctx)
    lex_rank = {docs[i]: r + 1 for r, i in enumerate(rank_desc(s))}
    cos = np.concatenate([minmax(np.array([h.cos for h in l])) if l else np.array([]) for l in lists])
    vec_rank = {docs[i]: r + 1 for r, i in enumerate(rank_desc(cos))}
    sc = rrf_from_ranks([lex_rank, vec_rank], k)
    return sorted(sc, key=lambda d: (-sc[d], d))


def merge_union_fusion_cc(lists, ctx, alpha=0.5):
    """Union + convex combination: alpha*minmax_per_mount(cos) +
    (1-alpha)*minmax(union BM25)."""
    docs, s = _union_bm25(lists, ctx)
    lex = minmax(s)
    cos = np.concatenate([minmax(np.array([h.cos for h in l])) if l else np.array([]) for l in lists])
    sc = alpha * cos + (1 - alpha) * lex
    order = rank_desc(sc)
    return [docs[i] for i in order]


def merge_union_fusion_cc_global(lists, ctx, alpha=0.5):
    """As above but the lexical leg uses corpus-wide statistics."""
    docs = [h.doc for l in lists for h in l]
    lex = minmax(ctx["global_bm25"][docs])
    cos = np.concatenate([minmax(np.array([h.cos for h in l])) if l else np.array([]) for l in lists])
    sc = alpha * cos + (1 - alpha) * lex
    order = rank_desc(sc)
    return [docs[i] for i in order]


STRATEGIES = {
    "(i) naive score sort (Result.top)": merge_naive,
    "(ii) round-robin interleave": merge_round_robin,
    "(iii) RRF across mounts k=60": merge_rrf,
    "(iv-a) min-max per mount, then sort": merge_minmax,
    "(iv-b) z-score per mount, then sort": merge_zscore,
    "(v) Clay: union + in-process BM25 (union stats)": merge_clay_union_bm25,
    "(v') union + BM25 with corpus-wide stats": merge_global_bm25,
    "(vi-a) union + RRF(union BM25, per-mount minmax cos)": merge_union_fusion_rrf,
    "(vi-b) union + CC 0.5(union BM25 mm, per-mount mm cos)": merge_union_fusion_cc,
    "(vi-c) union + CC 0.5 with corpus-wide BM25 stats": merge_union_fusion_cc_global,
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def build_mounts(cfgs, split, corpus, emb):
    mounts = []
    for i, cfg in enumerate(cfgs):
        idx = np.where(split == i)[0]
        dv, qv = emb[cfg.embedder]
        mounts.append(Mount(cfg, idx, Lexical([corpus.texts[j] for j in idx], cfg.k1, cfg.b), dv[idx], qv))
    return mounts


def oracle_run(corpus, emb, qrels_q, depth=100):
    """Single index: mount A's stack over the whole corpus."""
    cfg = MOUNTS[0]
    dv, qv = emb[cfg.embedder]
    whole = Mount(cfg, np.arange(corpus.n), Lexical(corpus.texts, cfg.k1, cfg.b), dv, qv)
    run = {}
    for q in qrels_q:
        hits = whole.search(q, corpus.queries[q], TOP, depth)
        run[q] = {corpus.doc_ids[h.doc]: float(TOP - i) for i, h in enumerate(hits)}
    return run, whole


def main():
    t0 = time.time()
    corpus = load_scifact()
    qids = sorted(corpus.qrels)
    qrels = Qrels(corpus.qrels)
    print(f"<!-- corpus {corpus.n} docs, {len(qids)} queries, seed {SEED} -->", file=sys.stderr)
    emb = {name: embed_all(name, corpus) for name in ("potion-8M", "potion-4M", "hash-256")}
    print(f"<!-- embedded in {time.time()-t0:.0f}s -->", file=sys.stderr)

    oracle, whole = oracle_run(corpus, emb, qids)
    global_lex = whole.lex
    oracle_scores = evaluate(qrels, Run(oracle, name="oracle"), METRICS)

    rng = np.random.default_rng(SEED)
    splits = {
        "random": rng.integers(0, 3, size=corpus.n),
        "topic (k-means k=3 on potion-8M)": kmeans_split(emb["potion-8M"][0], 3),
    }
    results = {}
    tables = []
    for mount_set_name, cfgs in (("hybrid A/B/C", MOUNTS), ("C lexical-only", MOUNTS_LEXONLY_C)):
        for split_name, split in splits.items():
            sizes = [int((split == i).sum()) for i in range(3)]
            mounts = build_mounts(cfgs, split, corpus, emb)
            # per-mount-alone quality (each mount over its own slice), for context
            for limit in LIMITS:
                per_mount_lists = {}
                for q in qids:
                    ls = []
                    for mi, m in enumerate(mounts):
                        hs = m.search(q, corpus.queries[q], limit)
                        for h in hs:
                            h.mount = mi
                        ls.append(hs)
                    per_mount_lists[q] = ls
                # recall ceiling of the union at this limit
                union_run = {q: {corpus.doc_ids[h.doc]: 1.0 for l in ls for h in l} for q, ls in per_mount_lists.items()}
                ceiling = evaluate(qrels, Run(union_run, name="union"), [f"recall@{3*limit}", "recall@10"])
                rows = []
                # how many union docs have zero lexical overlap with the query, and how many of those are relevant
                zero_total = zero_rel = 0
                for q, ls in per_mount_lists.items():
                    docs = [h.doc for l in ls for h in l]
                    s = Lexical([corpus.texts[d] for d in docs], 1.2, 0.75).scores(corpus.queries[q])
                    for d, sc in zip(docs, s):
                        if sc <= 0:
                            zero_total += 1
                            zero_rel += corpus.qrels[q].get(corpus.doc_ids[d], 0) > 0
                gbm = {q: global_lex.scores(corpus.queries[q]) for q in qids}
                for sname, fn in STRATEGIES.items():
                    run = {}
                    for q, ls in per_mount_lists.items():
                        ctx = {"texts": corpus.texts, "query": corpus.queries[q], "global_bm25": gbm[q]}
                        ordered = fn(ls, ctx)[:TOP]
                        run[q] = {corpus.doc_ids[d]: float(TOP - i) for i, d in enumerate(ordered)}
                    sc = evaluate(qrels, Run(run, name=sname), METRICS)
                    rows.append((sname, sc))
                    results[(mount_set_name, split_name, limit, sname)] = sc
                tables.append((mount_set_name, split_name, sizes, limit, rows, ceiling, zero_total, zero_rel, len(qids)))
                print(f"<!-- {mount_set_name} / {split_name} / m={limit} done at {time.time()-t0:.0f}s -->", file=sys.stderr)

    # ---- report ----------------------------------------------------------
    out = []
    out.append(f"## Oracle (single index, mount A stack, top-{TOP})\n")
    out.append("| nDCG@10 | MRR@10 | Recall@10 |\n|---|---|---|")
    out.append(f"| {oracle_scores['ndcg@10']:.4f} | {oracle_scores['mrr@10']:.4f} | {oracle_scores['recall@10']:.4f} |\n")
    for mount_set_name, split_name, sizes, limit, rows, ceiling, zt, zr, nq in tables:
        out.append(f"## Mounts: {mount_set_name} — split: {split_name} (sizes {sizes}) — per-mount limit m={limit}\n")
        out.append(f"Union recall ceiling at 3m={3*limit}: {ceiling[f'recall@{3*limit}']:.4f}. "
                   f"Union docs with zero BM25 overlap: {zt} ({zt/(3*limit*nq):.1%} of union), of which relevant: {zr}.\n")
        out.append("| strategy | nDCG@10 | MRR@10 | Recall@10 | nDCG vs oracle |\n|---|---|---|---|---|")
        for sname, sc in rows:
            out.append(f"| {sname} | {sc['ndcg@10']:.4f} | {sc['mrr@10']:.4f} | {sc['recall@10']:.4f} | {sc['ndcg@10']-oracle_scores['ndcg@10']:+.4f} |")
        out.append("")
    print("\n".join(out))
    with open("results.json", "w") as f:
        json.dump({" | ".join(map(str, k)): v for k, v in results.items()} | {"oracle": oracle_scores}, f, indent=1)


if __name__ == "__main__":
    main()
