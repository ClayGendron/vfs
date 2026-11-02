"""Experiment 4: BM25 idf drift when 5% of docs are re-posted and the deltas' df are ignored.

Base: lexical_builder over N docs (version 0). Re-post 5% of docs with version 1 (changed
content) and make the rewritten docs introduce one brand-new "hot" term so the drift has a
worst case. Compare, per term:
  base-only  idf(df_base, N)            -- what the overlay does today
  summed     idf(df_base + df_delta, N + N_new)  -- naive per-segment sum (double counts re-posts)
  true       idf(df_true, N)            -- a full rebuild on the current corpus
"""

from __future__ import annotations

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import IDENTS, PROSE_VOCAB, RARE_POOL, make_doc  # noqa: E402
from vfs.models.lexical import idf, lexical_builder  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
HOT = "hotfixmarker"


def df_table(docs: list[tuple[int, str]], chunk: int = 2000) -> tuple[dict[str, int], int, float, float]:
    b = lexical_builder()
    t0 = time.perf_counter()
    for i in range(0, len(docs), chunk):
        b.add_docs(docs[i : i + chunk])
    n, avg_dl = b.finish()
    df: dict[str, int] = {}
    while (batch := b.next_df_batch(50_000)) is not None:
        for term, d, _idf, _mw, _blocks in batch:
            df[term] = d
    return df, n, avg_dl, time.perf_counter() - t0


def main() -> None:
    rng = random.Random(9)
    reposted = set(rng.sample(range(1, N + 1), N // 20))
    t0 = time.perf_counter()
    base_docs = [(i, make_doc(i, 0)) for i in range(1, N + 1)]
    gen_s = time.perf_counter() - t0
    df_base, n_base, avg_base, build_base_s = df_table(base_docs)
    delta_docs = [(i, make_doc(i, 1) + f"\n{HOT} {HOT}\n") for i in sorted(reposted)]
    df_delta, n_delta, avg_delta, build_delta_s = df_table(delta_docs)
    current = [(i, text) for i, text in base_docs if i not in reposted] + delta_docs
    current.sort()
    df_true, n_true, avg_true, build_true_s = df_table(current)

    terms = [HOT, "return", "self", "none", "raise", PROSE_VOCAB[0], PROSE_VOCAB[50], PROSE_VOCAB[500], PROSE_VOCAB[3000],
             IDENTS[0].split("_")[0], IDENTS[100], IDENTS[1500], RARE_POOL[123], RARE_POOL[4567]]
    rows = []
    for t in terms:
        db, dd, dt = df_base.get(t, 0), df_delta.get(t, 0), df_true.get(t, 0)
        i_base = idf(db, n_base)
        i_sum = idf(db + dd, n_base + n_delta)  # naive per-segment sum: re-posted docs counted twice in df and N
        i_true = idf(dt, n_true)
        rows.append({
            "term": t, "df_base": db, "df_delta": dd, "df_true": dt,
            "idf_base_only": i_base, "idf_summed": i_sum, "idf_true": i_true,
            "err_base_only_pct": (i_base - i_true) / i_true * 100 if i_true else None,
            "err_summed_pct": (i_sum - i_true) / i_true * 100 if i_true else None,
        })
    # Corpus-wide drift: over every term in the true table, abs relative idf error of base-only stats.
    errs = []
    for t, dt in df_true.items():
        it = idf(dt, n_true)
        ib = idf(df_base.get(t, 0), n_base)
        errs.append(abs(ib - it) / it)
    errs.sort()
    summary = {
        "N": N, "reposted": len(reposted), "n_base": n_base, "avg_dl_base": avg_base, "avg_dl_true": avg_true,
        "terms_true": len(df_true), "terms_base": len(df_base),
        "terms_only_in_delta": len(set(df_delta) - set(df_base)),
        "gen_s": gen_s, "lexical_build_base_s": build_base_s, "lexical_build_delta_s": build_delta_s, "lexical_build_true_s": build_true_s,
        "idf_abs_rel_err_base_only": {"median": errs[len(errs) // 2], "p90": errs[int(len(errs) * 0.9)], "p99": errs[int(len(errs) * 0.99)], "max": errs[-1]},
        "rows": rows,
    }
    print(json.dumps(summary, indent=1))
    with open(os.path.join(HERE, "exp4_results.json"), "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
