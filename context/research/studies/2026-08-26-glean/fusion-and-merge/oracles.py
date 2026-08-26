"""Single-index oracle variants for the merge simulation: what the best
whole-corpus ranker achieves, so merge strategies are judged against the
right ceiling (the RRF k=60 oracle in sim_merge.py is mount A's stack, not
the best fusion on this corpus).

    CORPUS=beir/scifact/test <venv>/bin/python oracles.py
"""

from __future__ import annotations

import numpy as np
from ranx import Qrels, Run, evaluate

from common import Lexical, embed_all, load_scifact, minmax, rank_desc, rrf_from_ranks

TOP, DEPTH = 10, 100
METRICS = ["ndcg@10", "mrr@10", "recall@10"]


def main():
    corpus = load_scifact()
    qids = sorted(corpus.qrels)
    qrels = Qrels(corpus.qrels)
    dv, qv = embed_all("potion-8M", corpus)
    lex = Lexical(corpus.texts, 1.2, 0.75)
    variants = {
        "BM25(1.2,.75) only": lambda bm, cos, lt, vt, cand: bm[cand],
        "potion-8M cosine only": lambda bm, cos, lt, vt, cand: cos[cand],
        "RRF k=60 (sim_merge oracle)": None,
        "RRF k=5": None,
        "CC min-max alpha=0.3": lambda bm, cos, lt, vt, cand: 0.3 * minmax(cos[cand]) + 0.7 * minmax(bm[cand]),
        "CC min-max alpha=0.5": lambda bm, cos, lt, vt, cand: 0.5 * minmax(cos[cand]) + 0.5 * minmax(bm[cand]),
    }
    print("| whole-corpus ranker | nDCG@10 | MRR@10 | Recall@10 |\n|---|---|---|---|")
    for name, fn in variants.items():
        run = {}
        for q in qids:
            bm = lex.scores(corpus.queries[q])
            cos = dv @ qv[q]
            lt, vt = rank_desc(bm)[:DEPTH], rank_desc(cos)[:DEPTH]
            cand = np.unique(np.concatenate([lt, vt]))
            if fn is None:
                k = 60 if "60" in name else 5
                fused = rrf_from_ranks([{int(d): i + 1 for i, d in enumerate(lt)}, {int(d): i + 1 for i, d in enumerate(vt)}], k)
                sc = np.array([fused.get(int(d), 0.0) for d in cand])
            else:
                sc = fn(bm, cos, lt, vt, cand)
            order = cand[rank_desc(sc)[:TOP]]
            run[q] = {corpus.doc_ids[d]: float(TOP - i) for i, d in enumerate(order)}
        s = evaluate(qrels, Run(run), METRICS)
        print(f"| {name} | {s['ndcg@10']:.4f} | {s['mrr@10']:.4f} | {s['recall@10']:.4f} |")


if __name__ == "__main__":
    main()
