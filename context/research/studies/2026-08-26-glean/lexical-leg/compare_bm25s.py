"""Ranking agreement between the SQL BM25 statement and bm25s (method="lucene").

Runs in a throwaway venv that has bm25s + scipy installed (never the project
venv). Reads the tokens and SQL rankings that ``build_and_time.py
--export-tokens`` wrote, feeds bm25s the *same* pre-tokenized chunks, and
reports top-10 overlap, top-10 Kendall tau, and full-list Spearman/Kendall
over every chunk either side scored.

    <scratch>/lex/bin/python compare_bm25s.py results/tokens-10000.json results/rankings-10000.json
"""

from __future__ import annotations

import json
import sys
import time

import bm25s
import numpy as np
from scipy.stats import kendalltau, spearmanr

K1 = 1.2
B = 0.75


def main(tokens_path: str, rankings_path: str) -> None:
    data = json.load(open(tokens_path))
    rankings = json.load(open(rankings_path))
    chunk_ids = data["chunk_ids"]
    tokens = data["tokens"]
    t0 = time.perf_counter()
    retriever = bm25s.BM25(k1=K1, b=B, method="lucene")
    retriever.index(tokens, show_progress=False)
    index_seconds = time.perf_counter() - t0
    id_to_row = {cid: i for i, cid in enumerate(chunk_ids)}
    per_arity: dict[str, list[dict]] = {}
    for key, entry in rankings.items():
        arity = key.split(":")[0]
        query = entry["terms"]
        sql_top = [cid for cid, _ in entry["top"]]
        scores = retriever.get_scores(query)
        order = np.argsort(-scores, kind="stable")
        bm_top = [chunk_ids[i] for i in order[:50] if scores[i] > 0]
        top10_overlap = len(set(sql_top[:10]) & set(bm_top[:10])) / 10
        # rank agreement over the union of both top-50s: rank = position, missing = 51
        union = sorted(set(sql_top) | set(bm_top))
        sql_rank = {cid: i for i, cid in enumerate(sql_top)}
        bm_rank = {cid: i for i, cid in enumerate(bm_top)}
        a = [sql_rank.get(c, 51) for c in union]
        b = [bm_rank.get(c, 51) for c in union]
        tau = kendalltau(a, b).statistic if len(union) > 1 else 1.0
        # score-level agreement: SQL scores vs bm25s scores on the SQL top-50 (bm25s omits (k1+1); constant factor)
        sql_scores = np.array([s for _, s in entry["top"]])
        bm_scores = np.array([scores[id_to_row[cid]] for cid in sql_top])
        ratio = float(np.median(sql_scores / bm_scores)) if len(sql_top) and np.all(bm_scores > 0) else float("nan")
        rho = spearmanr(sql_scores, bm_scores).statistic if len(sql_top) > 2 else 1.0
        per_arity.setdefault(arity, []).append({"overlap10": top10_overlap, "tau_union50": tau, "score_ratio": ratio, "rho_scores": rho})
    summary = {"bm25s_index_seconds": round(index_seconds, 3), "n_chunks": len(tokens)}
    for arity, rows in per_arity.items():
        summary[arity] = {
            "n_queries": len(rows),
            "mean_overlap10": round(float(np.mean([r["overlap10"] for r in rows])), 4),
            "min_overlap10": round(float(np.min([r["overlap10"] for r in rows])), 4),
            "mean_tau_union50": round(float(np.nanmean([r["tau_union50"] for r in rows])), 4),
            "median_score_ratio": round(float(np.nanmedian([r["score_ratio"] for r in rows])), 4),
            "min_rho_scores": round(float(np.nanmin([r["rho_scores"] for r in rows])), 4),
        }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
