"""Spec 137's order-law check: does keeping every mount's own order cost the
union BM25 rerank anything?

Re-runs ``sim_merge.py``'s SciFact setup with the order-preserving variants
beside the unconstrained rerank, first on the study's heterogeneous mounts
(A/B/C — C is a deliberately bad local ranker) and then on vfs-shaped mounts:
one BM25 and one fusion law on every mount, differing only by embedder.

  (v')       union + BM25, corpus-wide stats (the spec's rerank, unconstrained)
  (v'-iso)   same, then per-mount isotonic repair (PAVA, non-increasing along mount rank)
  (v'-sfx)   same, then per-mount suffix-max repair
  (v'-heads) k-way merge picking the mount whose head has the higher rerank score
  (v-iso)    union-only stats + isotonic

    <study venv>/bin/python sim_order_law.py > results_order_law.md
"""

from __future__ import annotations

import sys
import time

import numpy as np
from common import SEED, MountConfig, embed_all, kmeans_split, load_scifact
from ranx import Qrels, Run, evaluate
from sim_merge import METRICS, MOUNTS, TOP, _union_bm25, build_mounts, merge_clay_union_bm25, merge_global_bm25, oracle_run

LIMITS = (10, 20, 50)
VFS_SETS = {
    "uniform: potion-8M / bm25(1.2,.75) / cc-minmax a=0.5 on all three": [
        MountConfig(f"{i}", "potion-8M", 1.2, 0.75, "cc-minmax", alpha=0.5) for i in range(3)
    ],
    "same law, embedders differ: potion-8M / potion-4M / hash-256": [
        MountConfig("A", "potion-8M", 1.2, 0.75, "cc-minmax", alpha=0.5),
        MountConfig("B", "potion-4M", 1.2, 0.75, "cc-minmax", alpha=0.5),
        MountConfig("C", "hash-256", 1.2, 0.75, "cc-minmax", alpha=0.5),
    ],
    "same law, lexical-only mounts (no embedder)": [
        MountConfig(f"{i}", "hash-256", 1.2, 0.75, "lexical-only") for i in range(3)
    ],
}


def pava(values):
    """Pool adjacent violators: the closest non-increasing sequence."""
    blocks = []
    for v in values:
        blocks.append([v, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] < blocks[-1][0] / blocks[-1][1]:
            s, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
    out = []
    for s, c in blocks:
        out.extend([s / c] * c)
    return out


def suffix_max(values):
    out, best = [], float("-inf")
    for v in reversed(values):
        best = max(best, v)
        out.append(best)
    return out[::-1]


def _scores(lists, ctx, global_stats):
    docs = [h.doc for l in lists for h in l]
    s = ctx["global_bm25"][docs] if global_stats else _union_bm25(lists, ctx)[1]
    return {d: float(v) for d, v in zip(docs, s)}


def _repaired(lists, ctx, repair, global_stats=True):
    s = _scores(lists, ctx, global_stats)
    keyed = []
    for mi, l in enumerate(lists):
        fixed = repair([s[h.doc] for h in l])
        keyed.extend((-f, mi, h.rank, h.doc) for f, h in zip(fixed, l))
    keyed.sort()
    return [k[3] for k in keyed]


def merge_iso(lists, ctx):
    return _repaired(lists, ctx, pava)


def merge_sfx(lists, ctx):
    return _repaired(lists, ctx, suffix_max)


def merge_iso_union(lists, ctx):
    return _repaired(lists, ctx, pava, global_stats=False)


def merge_heads(lists, ctx):
    s = _scores(lists, ctx, True)
    heads, out = [0] * len(lists), []
    while True:
        best = None
        for mi, l in enumerate(lists):
            if heads[mi] < len(l):
                key = (-s[l[heads[mi]].doc], mi)
                if best is None or key < best[0]:
                    best = (key, mi)
        if best is None:
            return out
        mi = best[1]
        out.append(lists[mi][heads[mi]].doc)
        heads[mi] += 1


def merge_naive(lists, ctx):
    hits = sorted((h for l in lists for h in l), key=lambda h: (-h.score, h.mount, h.rank))
    return [h.doc for h in hits]


STRATS = {
    "(v) union BM25, union stats": merge_clay_union_bm25,
    "(v') union BM25, corpus-wide stats": merge_global_bm25,
    "(v'-iso) + per-mount isotonic (PAVA)": merge_iso,
    "(v'-sfx) + per-mount suffix-max": merge_sfx,
    "(v'-heads) k-way merge on head scores": merge_heads,
    "(v-iso) union stats + isotonic": merge_iso_union,
    "(i) naive score sort": merge_naive,
}


def run_set(corpus, qids, qrels, whole, emb, splits, cfgs, limits, strats, out, t0):
    for split_name, split in splits.items():
        mounts = build_mounts(cfgs, split, corpus, emb)
        for limit in limits:
            per = {}
            for q in qids:
                ls = []
                for mi, m in enumerate(mounts):
                    hs = m.search(q, corpus.queries[q], limit)
                    for h in hs:
                        h.mount = mi
                    ls.append(hs)
                per[q] = ls
            gbm = {q: whole.lex.scores(corpus.queries[q]) for q in qids}
            out.append(f"### {split_name} split, m={limit}\n\n| strategy | nDCG@10 | MRR@10 | R@10 |\n|---|---|---|---|")
            for name, fn in strats.items():
                run = {}
                for q, ls in per.items():
                    ctx = {"texts": corpus.texts, "query": corpus.queries[q], "global_bm25": gbm[q]}
                    ordered = fn(ls, ctx)[:TOP]
                    run[q] = {corpus.doc_ids[d]: float(TOP - i) for i, d in enumerate(ordered)}
                sc = evaluate(qrels, Run(run, name=name), METRICS)
                out.append(f"| {name} | {sc['ndcg@10']:.4f} | {sc['mrr@10']:.4f} | {sc['recall@10']:.4f} |")
            out.append("")
            print(f"{split_name} m={limit} at {time.time() - t0:.0f}s", file=sys.stderr)


def main():
    t0 = time.time()
    corpus = load_scifact()
    qids = sorted(corpus.qrels)
    qrels = Qrels(corpus.qrels)
    emb = {name: embed_all(name, corpus) for name in ("potion-8M", "potion-4M", "hash-256")}
    oracle, whole = oracle_run(corpus, emb, qids)
    oracle_scores = evaluate(qrels, Run(oracle, name="oracle"), METRICS)
    rng = np.random.default_rng(SEED)
    splits = {"random": rng.integers(0, 3, size=corpus.n), "topic": kmeans_split(emb["potion-8M"][0], 3)}
    out = [f"# The order law on SciFact (seed {SEED}; oracle nDCG@10 {oracle_scores['ndcg@10']:.4f})\n"]
    out.append("## The study's heterogeneous mounts A/B/C (C is a deliberately bad local ranker)\n")
    study = {k: v for k, v in STRATS.items() if not k.startswith("(i)")}
    run_set(corpus, qids, qrels, whole, emb, splits, MOUNTS, LIMITS, study, out, t0)
    vfs_strats = {k: v for k, v in STRATS.items() if k.startswith(("(v')", "(v'-iso)", "(v'-heads)", "(i)"))}
    for set_name, cfgs in VFS_SETS.items():
        out.append(f"## vfs-shaped mounts — {set_name}\n")
        run_set(corpus, qids, qrels, whole, emb, splits, cfgs, (10, 30), vfs_strats, out, t0)
    print("\n".join(out))


if __name__ == "__main__":
    main()
