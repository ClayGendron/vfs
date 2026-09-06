"""The mitigations and their cost on SciFact: nDCG@10 on the visible qrels
under each statistics policy, the multiplayer subject-set case, the
cross-mount merge's export, the residual leak of each policy against the
score-channel adversary, and the cost model for visible-set statistics.

Policies (what N, avg_dl and df the mount scores with):

  global    the leak baseline: statistics over every row, hidden included
  visible   exact statistics over the caller's visible rows
  bucket2   global df rounded to the nearest power of two; N and avg_dl exact
  snapshot  every statistic over a fixed random half of the corpus, the same
            for every caller (a stale global snapshot)

    uv run --no-sync python mitigations.py >> results.md
"""

from __future__ import annotations

import math
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    SEED,
    Index,
    Stats,
    band_of,
    df_from_idf,
    evaluate,
    idf,
    load,
    ndcg_at,
    partitions,
    random_hidden,
    serve,
    vocabulary_sample,
    weight,
)
from leak_channels import ANCHOR_A, P_A, Tally, fmt, plant_anchors, solve_rho  # noqa: E402

FANOUT = 30  # fanout_depth(10) in vfs.rerank: 3 x the caller's limit


def bucket2(df: int) -> int:
    return 0 if df <= 0 else 2 ** int(round(math.log2(df)))


def policy_stats(index: Index, name: str, visible: set[int], snapshot: set[int]) -> Stats:
    if name == "global":
        return index.stats_over(range(index.n))
    if name == "visible":
        return index.stats_over(visible)
    if name == "bucket2":
        g = index.stats_over(range(index.n))
        return Stats(g.n_docs, g.avg_dl, {t: bucket2(d) for t, d in g.df.items()})
    if name == "snapshot":
        return index.stats_over(snapshot)
    raise ValueError(name)


POLICIES = ("global", "visible", "bucket2", "snapshot")


# ---------------------------------------------------------------------------
# 1. nDCG@10 per policy per partition
# ---------------------------------------------------------------------------


def quality_table(index: Index, queries, qrels, snapshot: set[int]) -> str:
    out = ["## 1. nDCG@10 on the visible qrels, per statistics policy\n"]
    everything = set(range(index.n))
    out.append(f"All rows visible, global statistics: **{evaluate(index, queries, qrels, everything, index.stats_over(everything)):.4f}**\n")
    out.append("| split | h | visible | queries | " + " | ".join(POLICIES) + " |")
    out.append("|---|---|---|---|" + "---|" * len(POLICIES))
    for kind, h, hidden in partitions(index):
        visible = everything - hidden
        n_q = sum(1 for qid in queries if any(d in visible for d in qrels.get(qid, {})))
        cells = [f"{evaluate(index, queries, qrels, visible, policy_stats(index, p, visible, snapshot)):.4f}" for p in POLICIES]
        out.append(f"| {kind} | {h:.0%} | {len(visible)} | {n_q} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 2. Multiplayer: the subject set's intersection
# ---------------------------------------------------------------------------


def subject_set_table(index: Index, queries, qrels) -> str:
    out = ["## 2. Multiplayer: statistics over the subject set's intersection\n"]
    out.append("Each principal sees a random 70% of the corpus (or a topical 70% for the topical row); the session sees the intersection.\n")
    out.append("| principals | mix | intersection | queries | global stats | intersection stats | each principal's own stats (mean) |")
    out.append("|---|---|---|---|---|---|---|")
    everything = set(range(index.n))
    from common import topical_hidden

    for s, mix in ((1, "random"), (2, "random"), (3, "random"), (5, "random"), (2, "topical+random"), (3, "topical+random")):
        views = []
        for i in range(s):
            if mix.startswith("topical") and i == 0:
                views.append(everything - topical_hidden(index, 0.3, seed=SEED + 7))
            else:
                views.append(everything - random_hidden(index.n, 0.3, seed=SEED + 100 + i))
        meet = set.intersection(*views)
        n_q = sum(1 for qid in queries if any(d in meet for d in qrels.get(qid, {})))
        g = evaluate(index, queries, qrels, meet, index.stats_over(everything))
        m = evaluate(index, queries, qrels, meet, index.stats_over(meet))
        own = statistics.mean(evaluate(index, queries, qrels, meet, index.stats_over(v)) for v in views)
        out.append(f"| {s} | {mix} | {len(meet)} ({len(meet) / index.n:.0%}) | {n_q} | {g:.4f} | {m:.4f} | {own:.4f} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 3. The merge: what each mount exports
# ---------------------------------------------------------------------------


def isotonic(values: list[float]) -> list[float]:
    pools: list[list[float]] = []
    for v in values:
        pools.append([v, 1.0])
        while len(pools) > 1 and pools[-2][0] / pools[-2][1] < pools[-1][0] / pools[-1][1]:
            t, c = pools.pop()
            pools[-1][0] += t
            pools[-1][1] += c
    return [t / c for t, c in pools for _ in range(int(c))]


def merge_table(index: Index, queries, qrels) -> str:
    out = ["## 3. The cross-mount merge: per-mount export vs the union fallback\n"]
    out.append(
        "Two mounts (random halves), the caller sees a random 50% of each. Each mount ranks its visible rows to "
        f"depth {FANOUT} with its own policy; the router re-scores the union with the summed exports (or the "
        "union's own texts) and applies the order law.\n"
    )
    rng = random.Random(SEED + 3)
    everything = list(range(index.n))
    rng.shuffle(everything)
    mounts = [set(everything[: index.n // 2]), set(everything[index.n // 2 :])]
    hidden = random_hidden(index.n, 0.5, seed=SEED + 4)
    visible = [m - hidden for m in mounts]
    meet = visible[0] | visible[1]
    global_stats = [index.stats_over(m) for m in mounts]
    visible_stats = [index.stats_over(v) for v in visible]

    def summed(parts: list[Stats]) -> Stats:
        n = sum(p.n_docs for p in parts)
        total = sum(p.n_docs * p.avg_dl for p in parts)
        df: dict[str, int] = {}
        for p in parts:
            for t, d in p.df.items():
                df[t] = df.get(t, 0) + d
        return Stats(n, total / n, df)

    def merged_ndcg(local: list[Stats], export: str) -> float:
        values = []
        for qid, terms in queries.items():
            graded = {d: g for d, g in qrels.get(qid, {}).items() if d in meet}
            if not graded:
                continue
            lists = [[d for d, _ in serve(index, terms, visible[i], local[i], limit=FANOUT)] for i in range(2)]
            if export == "union":
                union = {d for l in lists for d in l}
                stats = index.stats_over(union)
            elif export == "visible":
                stats = summed(visible_stats)
            else:
                stats = summed(global_stats)
            keyed = []
            for mi, l in enumerate(lists):
                raw = index.raw_scores(terms, set(l), stats)
                fixed = isotonic([raw.get(d, 0.0) for d in l])
                keyed.extend((-f, mi, r, d) for r, (f, d) in enumerate(zip(fixed, l)))
            keyed.sort()
            values.append(ndcg_at([k[3] for k in keyed], graded))
        return sum(values) / len(values)

    single_visible = evaluate(index, queries, qrels, meet, index.stats_over(meet))
    single_global = evaluate(index, queries, qrels, meet, index.stats_over(range(index.n)))
    out.append(f"One index over the caller's visible rows, visible stats: {single_visible:.4f}; global stats: {single_global:.4f}\n")
    out.append("| mount-local stats | export summed by the router | nDCG@10 | leaks hidden df? |")
    out.append("|---|---|---|---|")
    for local_name, local in (("global", global_stats), ("visible", visible_stats)):
        for export in ("global", "visible", "union"):
            if local_name == "visible" and export == "global":
                continue
            leaks = "yes: df over hidden rows" if "global" in (local_name, export) else "no"
            out.append(f"| {local_name} | {export} | {merged_ndcg(local, export):.4f} | {leaks} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 4. Residual leak per policy (score-channel adversary, oracle N and avg_dl)
# ---------------------------------------------------------------------------


def residual_leak_table(base: Index, snapshot: set[int]) -> str:
    out = ["## 4. Residual leak: the score-channel adversary against each policy\n"]
    out.append(
        "Random and topical h=50%. The adversary plants the anchors, is handed the policy's N and avg_dl "
        "(the most it could learn), recovers each term's *policy* df from one two-term query, and predicts "
        "\"present in hidden rows\" by the rule that is certain under that policy: recovered df above the "
        "visible df (global, snapshot), or a different bucket (bucket2).\n"
    )
    out.append("| split | policy | recovered = policy df exactly | base rate | precision | recall | accuracy |")
    out.append("|---|---|---|---|---|---|---|")
    for kind, h, hidden in partitions(base, fractions=(0.5,)):
        index = Index([], [])
        index.doc_ids, index.tf, index.dl = list(base.doc_ids), [dict(t) for t in base.tf], list(base.dl)
        index.postings = {t: dict(p) for t, p in base.postings.items()}
        original = set(range(index.n))
        visible0 = original - hidden
        visible_stats0 = index.stats_over(visible0)
        hidden_stats = index.stats_over(hidden)
        vocab = vocabulary_sample(index, visible0)
        anchors = plant_anchors(index)
        visible = visible0 | set(anchors)
        snap = snapshot | set(anchors)  # the adversary's rows entered after the snapshot? no: assume re-snapshotted
        for policy in POLICIES:
            stats = policy_stats(index, policy, visible, snap)
            df_a = stats.df.get(ANCHOR_A, 0)
            exact = 0
            tally = Tally()
            for term in vocab:
                df_v = visible_stats0.df[term]
                df_h = hidden_stats.df.get(term, 0)
                answer = dict(serve(index, [term, ANCHOR_A], visible, stats))
                rows = sorted(answer)
                obs = np.array([answer[d] for d in rows])
                w_t = np.array([weight(index.tf[d][term], index.dl[d], stats.avg_dl) if term in index.tf[d] else 0.0 for d in rows])
                w_a = np.array([weight(index.tf[d][ANCHOR_A], index.dl[d], stats.avg_dl) if ANCHOR_A in index.tf[d] else 0.0 for d in rows])
                rho = solve_rho(obs, w_t, w_a)
                recovered = int(round(df_from_idf(rho * idf(df_a, stats.n_docs), stats.n_docs)))
                exact += recovered == stats.df.get(term, 0)
                if policy == "bucket2":
                    predicted = recovered != bucket2(df_v)
                else:
                    predicted = recovered > df_v
                tally.add(band_of(df_v), df_h >= 1, predicted, df_h, recovered - df_v)
            s = tally.summary()
            out.append(
                f"| {kind} | {policy} | {exact / len(vocab):.3f} | {s['base']:.2f} | {s['precision']:.3f} | "
                f"{s['recall']:.3f} | {s['accuracy']:.3f} |"
            )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 5. Cost model
# ---------------------------------------------------------------------------


def cost_table(index: Index, queries) -> str:
    out = ["## 5. Cost model: visible-set df per query\n"]
    g = index.stats_over(range(index.n))
    ks, rows = [], []
    for terms in queries.values():
        present = [t for t in dict.fromkeys(terms) if t in g.df]
        ks.append(len(present))
        rows.append(sum(g.df[t] for t in present))
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]
    out.append(f"Corpus: N = {index.n}, vocabulary {len(g.df)}, mean dl {g.avg_dl:.0f} tokens, total postings {sum(len(p) for p in index.postings.values())}.\n")
    out.append("| per SciFact query | mean | median | p95 | max |")
    out.append("|---|---|---|---|---|")
    out.append(f"| distinct indexed terms k | {statistics.mean(ks):.1f} | {q(ks, .5)} | {q(ks, .95)} | {max(ks)} |")
    out.append(f"| posting rows under the query's terms (sum of global df) | {statistics.mean(rows):.0f} | {q(rows, .5)} | {q(rows, .95)} | {max(rows)} |")
    out.append(f"| same, as a share of N | {statistics.mean(rows) / index.n:.2f} | {q(rows, .5) / index.n:.2f} | {q(rows, .95) / index.n:.2f} | {max(rows) / index.n:.2f} |")
    stop = sum(1 for t, d in g.df.items() if d > index.n * 0.2)
    top = sorted(g.df.items(), key=lambda kv: -kv[1])[:8]
    out.append(f"\nTerms in more than 20% of documents: {stop} ({', '.join(t for t, _ in top)}, ...). They carry most of the rows and almost none of the score.\n")
    return "\n".join(out) + "\n"


def main() -> None:
    index, queries, qrels = load()
    snapshot = random_hidden(index.n, 0.5, seed=SEED + 11)
    print("# Mitigations on SciFact (vfs tokenizer and formula)\n")
    for section in (quality_table, subject_set_table, merge_table):
        t0 = time.time()
        print(section(index, queries, qrels, snapshot) if section is quality_table else section(index, queries, qrels))
        print(f"_({time.time() - t0:.0f}s)_\n")
    t0 = time.time()
    print(residual_leak_table(index, snapshot))
    print(f"_({time.time() - t0:.0f}s)_\n")
    print(cost_table(index, queries))


if __name__ == "__main__":
    main()
