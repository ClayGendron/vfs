"""Part A sweep: fusion *within* one index (the whole SciFact corpus, potion-8M
+ BM25 1.2/0.75). Answers: how sensitive is RRF to k; does CC beat RRF here;
does min-max vs z-score matter; and what a static prior does under the three
injection modes (extra RRF list / multiplicative boost / additive term) when
the prior is pure noise versus when it carries signal.

    <venv>/bin/python sweep_fusion.py > sweep.md
"""

from __future__ import annotations

import sys

import numpy as np
from ranx import Qrels, Run, evaluate

from common import SEED, Lexical, embed_all, load_scifact, minmax, rank_desc, rrf_from_ranks, zscore

TOP, DEPTH = 10, 100
METRICS = ["ndcg@10", "mrr@10", "recall@10"]


def main():
    corpus = load_scifact()
    qids = sorted(corpus.qrels)
    qrels = Qrels(corpus.qrels)
    dv, qv = embed_all("potion-8M", corpus)
    lex = Lexical(corpus.texts, 1.2, 0.75)
    legs = {}
    for q in qids:
        bm = lex.scores(corpus.queries[q])
        cos = dv @ qv[q]
        lt, vt = rank_desc(bm)[:DEPTH], rank_desc(cos)[:DEPTH]
        cand = np.unique(np.concatenate([lt, vt]))
        legs[q] = (bm, cos, lt, vt, cand)

    def run_of(fn):
        run = {}
        for q in qids:
            bm, cos, lt, vt, cand = legs[q]
            sc = fn(bm, cos, lt, vt, cand, q)
            order = cand[rank_desc(sc)[:TOP]]
            run[q] = {corpus.doc_ids[d]: float(TOP - i) for i, d in enumerate(order)}
        return evaluate(qrels, Run(run), METRICS)

    def rrf_fn(k, w=(1.0, 1.0)):
        def f(bm, cos, lt, vt, cand, q):
            lr = {int(d): i + 1 for i, d in enumerate(lt)}
            vr = {int(d): i + 1 for i, d in enumerate(vt)}
            fused = rrf_from_ranks([lr, vr], k, list(w))
            return np.array([fused.get(int(d), 0.0) for d in cand])
        return f

    def cc_fn(alpha, norm):
        def f(bm, cos, lt, vt, cand, q):
            return alpha * norm(cos[cand]) + (1 - alpha) * norm(bm[cand])
        return f

    out = ["## Single legs\n", "| leg | nDCG@10 | MRR@10 | Recall@10 |", "|---|---|---|---|"]
    for name, fn in (("BM25 only", lambda bm, cos, lt, vt, cand, q: bm[cand]), ("potion-8M cosine only", lambda bm, cos, lt, vt, cand, q: cos[cand])):
        s = run_of(fn)
        out.append(f"| {name} | {s['ndcg@10']:.4f} | {s['mrr@10']:.4f} | {s['recall@10']:.4f} |")

    out += ["\n## RRF: sensitivity to k (equal weights)\n", "| k | nDCG@10 | MRR@10 | Recall@10 |", "|---|---|---|---|"]
    for k in (0, 1, 5, 10, 30, 60, 100, 300, 1000):
        s = run_of(rrf_fn(k))
        out.append(f"| {k} | {s['ndcg@10']:.4f} | {s['mrr@10']:.4f} | {s['recall@10']:.4f} |")

    out += ["\n## Weighted RRF k=60: weight on the vector list\n", "| w_vec (w_lex=1) | nDCG@10 | MRR@10 | Recall@10 |", "|---|---|---|---|"]
    for w in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0):
        s = run_of(rrf_fn(60, (1.0, w)))
        out.append(f"| {w} | {s['ndcg@10']:.4f} | {s['mrr@10']:.4f} | {s['recall@10']:.4f} |")

    out += ["\n## Convex combination: alpha (weight on vector) x normalization\n", "| alpha | min-max nDCG@10 | z-score nDCG@10 | min-max R@10 | z-score R@10 |", "|---|---|---|---|---|"]
    for a in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        m, z = run_of(cc_fn(a, minmax)), run_of(cc_fn(a, zscore))
        out.append(f"| {a:.1f} | {m['ndcg@10']:.4f} | {z['ndcg@10']:.4f} | {m['recall@10']:.4f} | {z['recall@10']:.4f} |")

    # ---- static prior injection --------------------------------------------
    rng = np.random.default_rng(SEED)
    noise = rng.random(corpus.n)
    relevant_any = np.zeros(corpus.n)
    idx = {d: i for i, d in enumerate(corpus.doc_ids)}
    for q in qids:
        for d in corpus.qrels[q]:
            relevant_any[idx[d]] = 1.0
    # "signal" prior: a leak-shaped upper bound — relevance-correlated
    # centrality would look like this. Half noise, half signal.
    signal = minmax(0.5 * relevant_any + 0.5 * noise)
    priors = {"noise (uniform random)": noise, "signal (0.5*any-relevant + 0.5*noise)": signal}

    out += ["\n## Static prior injection (base: CC alpha=0.5 min-max, and RRF k=60)\n",
            "| prior | mode | nDCG@10 | MRR@10 | Recall@10 |", "|---|---|---|---|---|"]
    base_cc = run_of(cc_fn(0.5, minmax))
    base_rrf = run_of(rrf_fn(60))
    out.append(f"| none | CC base | {base_cc['ndcg@10']:.4f} | {base_cc['mrr@10']:.4f} | {base_cc['recall@10']:.4f} |")
    out.append(f"| none | RRF base | {base_rrf['ndcg@10']:.4f} | {base_rrf['mrr@10']:.4f} | {base_rrf['recall@10']:.4f} |")
    for pname, prior in priors.items():
        def rrf_extra(bm, cos, lt, vt, cand, q, prior=prior):
            lr = {int(d): i + 1 for i, d in enumerate(lt)}
            vr = {int(d): i + 1 for i, d in enumerate(vt)}
            pr = {int(d): r + 1 for r, d in enumerate(cand[rank_desc(prior[cand])])}
            fused = rrf_from_ranks([lr, vr, pr], 60)
            return np.array([fused[int(d)] for d in cand])
        def mult(beta, prior=prior):
            return lambda bm, cos, lt, vt, cand, q: cc_fn(0.5, minmax)(bm, cos, lt, vt, cand, q) * (1 + beta * prior[cand])
        def add(lam, prior=prior):
            return lambda bm, cos, lt, vt, cand, q: cc_fn(0.5, minmax)(bm, cos, lt, vt, cand, q) + lam * prior[cand]
        for mode, fn in (("extra RRF list (k=60, equal weight)", rrf_extra), ("multiplicative x(1+0.5p)", mult(0.5)), ("multiplicative x(1+2p)", mult(2.0)), ("additive +0.1p", add(0.1)), ("additive +0.3p", add(0.3))):
            s = run_of(fn)
            out.append(f"| {pname} | {mode} | {s['ndcg@10']:.4f} | {s['mrr@10']:.4f} | {s['recall@10']:.4f} |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
