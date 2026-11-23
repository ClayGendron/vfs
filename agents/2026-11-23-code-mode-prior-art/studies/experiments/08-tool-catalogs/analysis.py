"""Post-hoc analysis of per_query.jsonl: the example-leakage control and the per-category tables.

Run: cd /home/user/vfs && uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/analysis.py
Writes analysis.json beside this file and prints Markdown tables.

Leakage control: the examples (V3) and the queries were written by one researcher in one sitting, so a
query may echo its target's example. Each GitHub query is put in a bucket by the number of key words it
shares with the examples of its acceptable tools: "echo" (two or more shared) or "fresh" (one or none).
The V3 gain is reported per bucket; the "fresh" bucket is the less contaminated estimate.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from queries_check import key_words  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LIMIT = 10


def metrics(ranks):
    n = len(ranks)
    if not n:
        return {"n": 0}
    def hit(k):
        return round(sum(1 for r in ranks if r is not None and r <= k) / n, 3)
    return {"n": n, "hit@1": hit(1), "hit@3": hit(3), "hit@5": hit(5),
            "mrr@10": round(sum(1 / r for r in ranks if r is not None and r <= LIMIT) / n, 3)}


def main():
    rows = [json.loads(line) for line in open(os.path.join(HERE, "per_query.jsonl"), encoding="utf-8")]
    queries = {q["id"]: q for q in json.load(open(os.path.join(HERE, "queries_tagged.json"), encoding="utf-8"))}
    examples = json.load(open(os.path.join(HERE, "github_examples.json"), encoding="utf-8"))
    overlap = {}
    for qid, q in queries.items():
        if not q["target"].startswith("github/"):
            continue
        accept = [q["target"], *q["alternates"]]
        ex_words = {w for label in accept for e in examples.get(label.split("/", 1)[1], []) for w in key_words(e)}
        overlap[qid] = sorted(set(q["grep_words"]) & ex_words)
    bucket = {qid: ("echo" if len(ws) >= 2 else "fresh") for qid, ws in overlap.items()}

    out = {"overlap": overlap, "bucket_sizes": {b: sum(1 for v in bucket.values() if v == b) for b in ("echo", "fresh")},
           "leakage": {}, "by_category": {}}
    methods = sorted({r["method"] for r in rows})
    for method in methods:
        for variant in ("V1", "V2", "V3"):
            sel = [r for r in rows if r["corpus"] == "github" and r["variant"] == variant and r["method"] == method]
            if not sel:
                continue
            for b in ("echo", "fresh"):
                out["leakage"][f"{method}/{variant}/{b}"] = metrics([r["rank"] for r in sel if bucket[r["id"]] == b])
    for corpus in ("combined", "github"):
        for variant in ("V1", "V2", "V3"):
            for method in methods:
                sel = [r for r in rows if r["corpus"] == corpus and r["variant"] == variant and r["method"] == method]
                for cat in ("named", "paraphrase"):
                    if sel:
                        out["by_category"][f"{corpus}/{variant}/{method}/{cat}"] = metrics(
                            [r["rank"] for r in sel if r["category"] == cat])
    with open(os.path.join(HERE, "analysis.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("bucket sizes:", out["bucket_sizes"])
    print("| method / variant / bucket | n | hit@1 | hit@3 | hit@5 | MRR@10 |")
    for k, v in out["leakage"].items():
        print(f"| {k} | {v['n']} | {v.get('hit@1')} | {v.get('hit@3')} | {v.get('hit@5')} | {v.get('mrr@10')} |")
    print("| corpus / variant / method / category | n | hit@1 | hit@3 | hit@5 | MRR@10 |")
    for k, v in out["by_category"].items():
        print(f"| {k} | {v['n']} | {v.get('hit@1')} | {v.get('hit@3')} | {v.get('hit@5')} | {v.get('mrr@10')} |")


if __name__ == "__main__":
    main()
