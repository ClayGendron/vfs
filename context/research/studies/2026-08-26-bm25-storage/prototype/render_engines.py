"""Render the engine results (results/engine_*.json) as the memo's markdown tables."""

from __future__ import annotations

import json
from pathlib import Path

from common import RESULTS

ORDER = ["postgres", "mysql", "mssql", "oracle"]


def mb(b: int) -> str:
    return f"{b / 2**20:.1f} MB"


def main() -> None:
    runs = {}
    for name in ORDER:
        p = RESULTS / f"engine_{name}.json"
        if p.exists():
            runs[name] = json.loads(p.read_text())
    print("### 3a. Load wall and bytes per engine\n")
    print("| engine | A `terms` rows load | B `postings` rows load | A `terms` bytes | B `postings` bytes | shared `df` | shared `docs` | B/A bytes (postings) |")
    print("|---|---|---|---|---|---|---|---|")
    for name, r in runs.items():
        L = r["load"]
        by = L["bytes"]
        print(
            f"| {name} | 3,094,397 in **{L['a_terms']['wall_s']} s** | 499,590 in **{L['b_postings']['wall_s']} s** | **{mb(by['bm25a_terms'])}** | **{mb(by['bm25b_postings'])}** | {mb(by['bm25b_df'])} | {mb(by['bm25b_docs'])} | {by['bm25b_postings'] / by['bm25a_terms']:.2f}× |"
        )
    print("\n### 3b. Unscoped top-10 (S1), medians in ms\n")
    print("| engine | arity | **A** in-engine SUM | B fetch (df + blocks, 2 stmts) | B fetch (joined, 1 stmt) | B numpy score | **B total (2 stmts)** | **B total (1 stmt)** | agree |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, r in runs.items():
        for arity in ("1", "3", "6"):
            s = r["summary"][arity]
            j = s.get("b_s1_fetch1_ms")
            j1 = s.get("b_s1_total1_ms")
            print(
                f"| {name} | {arity} | **{s['a_s1_ms']:.2f}** | {s['b_s1_fetch_ms']:.2f} | {f'{j:.2f}' if j is not None else 'n/a'} | {s['b_s1_score_ms']:.2f} | **{s['b_s1_total_ms']:.2f}** | {f'**{j1:.2f}**' if j1 is not None else 'n/a'} | {s['agree']['agree_s1']}/15, τ={s['min_tau_s1']} |"
            )
    print("\n### 3c. Scoped shapes, medians in ms\n")
    print("| engine | arity | **A** S3 ext join | B S3 client-filter | **B S3 semi-join** | probes | **A** S5 allow-list join | B S5 client-filter | **B S5 semi-join** | agree (S3 c/s, S5 c/s) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, r in runs.items():
        for arity in ("1", "3", "6"):
            s = r["summary"][arity]
            ag = s["agree"]
            print(
                f"| {name} | {arity} | **{s['a_s3_ms']:.2f}** | {s['b_s3_client_ms']:.2f} | **{s['b_s3_semi_ms']:.2f}** | ≤{s['semi_probes_max']} | **{s['a_s5_ms']:.2f}** | {s['b_s5_client_ms']:.2f} | **{s['b_s5_semi_ms']:.2f}** | {ag['agree_s3_client']}/{ag['agree_s3_semi']}, {ag['agree_s5_client']}/{ag['agree_s5_semi']} |"
            )
    print("\nScope-set fetch alone (query-independent; the client-filter rows above pay it every query):\n")
    print("| engine | ext = 'c' chunk ids | ms | 500-entry allow-list chunk ids | ms |")
    print("|---|---|---|---|---|")
    for name, r in runs.items():
        sf = r["scope_fetch"]
        print(f"| {name} | {sf['ext']['chunk_ids']:,} | {sf['ext']['ms']:.2f} | {sf['allow']['chunk_ids']:,} | {sf['allow']['ms']:.2f} |")


if __name__ == "__main__":
    main()
