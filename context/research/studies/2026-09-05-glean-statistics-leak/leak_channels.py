"""The three leak channels against vfs's BM25 under row grants, on SciFact.

For each partition (random / topical hidden fraction h) an adversary who can
read the visible rows and write a few documents of their own tries to learn,
for a vocabulary sample of visible terms, whether the term also occurs in
rows they cannot see, and how many. Three observation channels:

  a. scores  — glean's answer: visible rows with min-max-scaled scores (9 dp)
  b. stats   — the mount's ``lexical_stats`` export (n_docs, avg_dl, df per term)
  c. ranks   — the ordered rows only, no scores

Channel a plants two anchor tokens (4 and 64 documents) to solve N and
avg_dl from one query, then one two-term query per vocabulary term. Channel
c plants a 128-rung ladder of unique tokens and reads a term's idf off the
interleaving; it is given N and avg_dl (an upper bound on what ranks leak).

    uv run --no-sync python leak_channels.py > results.md   # then mitigations.py >> results.md
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    FILLER,
    Index,
    Stats,
    band_of,
    df_from_idf,
    idf,
    load,
    minmax,
    partitions,
    serve,
    vocabulary_sample,
    weight,
)

ANCHOR_A, ANCHOR_B = "zqanchora", "zqanchorb"
P_A, P_B = 4, 64
LADDER_RUNGS = 128
LADDER_LOW, LADDER_HIGH = 1.0, 16.0


# ---------------------------------------------------------------------------
# Planting
# ---------------------------------------------------------------------------


def plant_anchors(index: Index) -> list[int]:
    """Anchor A in 4 documents and anchor B in 64, lengths spread 20..2000 tokens."""
    planted = []
    for token, count in ((ANCHOR_A, P_A), (ANCHOR_B, P_B)):
        for i in range(count):
            dl = int(round(20 * (100 ** (i / max(count - 1, 1)))))
            planted.append(index.plant([token] + [FILLER] * (dl - 1)))
    return planted


def plant_ladder(index: Index, n_docs_after: int, avg_dl_after: float) -> list[tuple[int, str, float]]:
    """128 unique tokens, one document each, with (tf, dl) chosen so the raw
    score ``idf(1, N) * w(tf, dl)`` climbs geometrically from 1 to 16."""
    rungs = []
    idf1 = idf(1, n_docs_after)
    for j in range(LADDER_RUNGS):
        target = LADDER_LOW * (LADDER_HIGH / LADDER_LOW) ** (j / (LADDER_RUNGS - 1)) / idf1
        best = None
        for tf in range(1, 40):
            if tf * 2.2 / (tf + 0.3) <= target:
                continue
            k = tf * 2.2 / target - tf
            dl = ((k / 1.2) - 0.25) / 0.75 * avg_dl_after
            if dl < tf:
                continue
            dl_int = max(tf, int(round(dl)))
            realized = weight(tf, dl_int, avg_dl_after)
            err = abs(realized - target) / target
            if best is None or err < best[0]:
                best = (err, tf, dl_int, realized)
        assert best is not None, j
        _, tf, dl_int, realized = best
        token = f"zqladder{j:03d}"
        position = index.plant([token] * tf + [FILLER] * (dl_int - tf))
        rungs.append((position, token, realized))
    return rungs


# ---------------------------------------------------------------------------
# The adversary's solvers
# ---------------------------------------------------------------------------


def solve_rho(observed: np.ndarray, w_t: np.ndarray, w_a: np.ndarray) -> float:
    """``rho = idf_t / idf_a`` from min-max-scaled scores: least squares on a log grid, then golden section."""

    def loss(rho: float) -> float:
        return float(np.sum((minmax(rho * w_t + w_a) - observed) ** 2))

    grid = np.logspace(-4, 2, 1201)
    losses = np.array([loss(r) for r in grid])
    i = int(np.argmin(losses))
    lo, hi = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    a, b = math.log(lo), math.log(hi)
    phi = (math.sqrt(5) - 1) / 2
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = loss(math.exp(c)), loss(math.exp(d))
    for _ in range(80):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = loss(math.exp(c))
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = loss(math.exp(d))
    return math.exp((a + b) / 2)


def solve_avg_dl(observed: np.ndarray, tf: np.ndarray, dl: np.ndarray) -> float:
    """``avg_dl`` from a single-anchor query: idf cancels under min-max, the shape over dl is all avg_dl."""

    def loss(avg: float) -> float:
        return float(np.sum((minmax(tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * dl / avg))) - observed) ** 2))

    lo, hi = 5.0, 20000.0
    for _ in range(12):
        grid = np.exp(np.linspace(math.log(lo), math.log(hi), 200))
        best = grid[int(np.argmin([loss(a) for a in grid]))]
        lo, hi = best / 1.05, best * 1.05
    return float(best)


def solve_n(observed: np.ndarray, tf_a: np.ndarray, tf_b: np.ndarray, dl: np.ndarray, avg: float, n_floor: int, df_a: int, df_b: int) -> int:
    """``N`` from the two-anchor query with avg_dl known: the ratio ``idf(df_a, N) / idf(df_b, N)`` sets the shape."""
    wa = tf_a * 2.2 / (tf_a + 1.2 * (0.25 + 0.75 * dl / avg))
    wb = tf_b * 2.2 / (tf_b + 1.2 * (0.25 + 0.75 * dl / avg))

    def loss(n: float) -> float:
        return float(np.sum((minmax(idf(df_a, n) * wa + idf(df_b, n) * wb) - observed) ** 2))

    lo, hi = float(n_floor), float(n_floor) * 50
    for _ in range(10):
        grid = np.exp(np.linspace(math.log(lo), math.log(hi), 200))
        best = grid[int(np.argmin([loss(n) for n in grid]))]
        lo, hi = max(float(n_floor), best / 1.05), best * 1.05
    return min((loss(n), n) for n in range(max(n_floor, int(best) - 30), int(best) + 31))[1]


# ---------------------------------------------------------------------------
# One partition, three channels
# ---------------------------------------------------------------------------


class Tally:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, bool, int, int]] = []  # band, truth, predicted, df_h true, df_h est

    def add(self, band: str, truth: bool, predicted: bool, df_h: int, est: int) -> None:
        self.rows.append((band, truth, predicted, df_h, est))

    def summary(self, band: str | None = None) -> dict[str, float]:
        rows = [r for r in self.rows if band is None or r[0] == band]
        tp = sum(1 for r in rows if r[1] and r[2])
        fp = sum(1 for r in rows if not r[1] and r[2])
        fn = sum(1 for r in rows if r[1] and not r[2])
        tn = len(rows) - tp - fp - fn
        return {
            "n": len(rows),
            "base": (tp + fn) / len(rows) if rows else 0.0,
            "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "accuracy": (tp + tn) / len(rows) if rows else 0.0,
            "df_exact": sum(1 for r in rows if r[3] == r[4]) / len(rows) if rows else 0.0,
            "df_mae": sum(abs(r[3] - r[4]) for r in rows) / len(rows) if rows else 0.0,
        }


def fmt(s: dict[str, float]) -> str:
    return (
        f"{s['n']:>4} | {s['base']:.2f} | {s['precision']:.3f} | {s['recall']:.3f} | {s['accuracy']:.3f} | "
        f"{s['df_exact']:.3f} | {s['df_mae']:.2f}"
    )


HEADER = "| band | n | base rate | precision | recall | accuracy | df_h exact | df_h MAE |\n|---|---|---|---|---|---|---|---|"


def run_partition(base: Index, kind: str, h: float, hidden: set[int]) -> str:
    out: list[str] = []
    index = Index([], [])
    index.doc_ids, index.tf, index.dl = list(base.doc_ids), [dict(t) for t in base.tf], list(base.dl)
    index.postings = {t: dict(p) for t, p in base.postings.items()}
    original = set(range(index.n))
    visible0 = original - hidden
    n_v, n_h = len(visible0), len(hidden)
    visible_stats0 = index.stats_over(visible0)
    hidden_stats = index.stats_over(hidden)
    vocab = vocabulary_sample(index, visible0)

    # --- plant everything first: the adversary knows every document they wrote
    anchors = plant_anchors(index)
    ladder = plant_ladder(index, n_v + n_h + len(anchors) + LADDER_RUNGS, visible_stats0.avg_dl)
    planted = len(anchors) + len(ladder)
    everything = set(range(index.n))
    global_stats = index.stats_over(everything)
    visible = visible0 | set(anchors) | {p for p, _, _ in ladder}
    n_after, avg_after = global_stats.n_docs, global_stats.avg_dl
    out.append(f"### {kind} h={h:.0%}: visible {n_v}, hidden {n_h}, planted {planted}\n")

    # --- channel a: solve avg_dl from anchor B alone, then N from (A, B)
    t0 = time.time()
    answer = dict(serve(index, [ANCHOR_B], visible, global_stats))
    docs = sorted(answer)
    avg_est = solve_avg_dl(
        np.array([answer[d] for d in docs]),
        np.array([index.tf[d][ANCHOR_B] for d in docs], dtype=float),
        np.array([index.dl[d] for d in docs], dtype=float),
    )
    answer = dict(serve(index, [ANCHOR_A, ANCHOR_B], visible, global_stats))
    docs = sorted(answer)
    n_est = solve_n(
        np.array([answer[d] for d in docs]),
        np.array([index.tf[d].get(ANCHOR_A, 0) for d in docs], dtype=float),
        np.array([index.tf[d].get(ANCHOR_B, 0) for d in docs], dtype=float),
        np.array([index.dl[d] for d in docs], dtype=float),
        avg_est,
        n_v + planted,
        P_A,
        P_B,
    )
    solve_s = time.time() - t0
    out.append(
        f"- channel a corpus solve from two anchor queries ({len(docs)} rows): N_est={n_est} (true {n_after}, "
        f"hidden-size estimate {n_est - n_v - planted} vs true {n_h}); avg_dl_est={avg_est:.3f} "
        f"(true {avg_after:.3f}); {solve_s:.1f}s"
    )

    tallies = {"a-planted": Tally(), "a-oracle": Tally(), "b-stats": Tally(), "c-ranks": Tally()}
    ladder_tokens = [tok for _, tok, _ in ladder]
    ladder_score = {p: idf(1, n_after) * weight(index.tf[p][tok], index.dl[p], avg_after) for p, tok, _ in ladder}

    interval_widths = []
    for term in vocab:
        df_v = visible_stats0.df[term]
        df_h = hidden_stats.df.get(term, 0)
        truth = df_h >= 1
        band = band_of(df_v)

        # a. scores: query (term, anchor A); rows = visible term docs + the 4 anchor docs
        answer = dict(serve(index, [term, ANCHOR_A], visible, global_stats))
        rows = sorted(answer)
        obs = np.array([answer[d] for d in rows])
        for label, (n_use, avg_use) in (("a-planted", (n_est, avg_est)), ("a-oracle", (n_after, avg_after))):
            w_t = np.array([weight(index.tf[d][term], index.dl[d], avg_use) if term in index.tf[d] else 0.0 for d in rows])
            w_a = np.array([weight(index.tf[d][ANCHOR_A], index.dl[d], avg_use) if ANCHOR_A in index.tf[d] else 0.0 for d in rows])
            rho = solve_rho(obs, w_t, w_a)
            df_est = int(round(df_from_idf(rho * idf(P_A, n_use), n_use)))
            est_h = df_est - df_v
            tallies[label].add(band, truth, est_h >= 1, df_h, est_h)

        # b. stats: the export names df directly
        export_df = global_stats.df[term]
        est_h = export_df - df_v
        tallies["b-stats"].add(band, truth, est_h >= 1, df_h, est_h)

        # c. ranks: query (term + 128 ladder tokens); read the term's idf off the interleaving
        ranked = [d for d, _ in serve(index, [term, *ladder_tokens], visible, global_stats)]
        lo, hi = 0.0, float("inf")
        last_rung = float("inf")
        pending: list[int] = []
        for d in ranked:
            if d in ladder_score:
                s = ladder_score[d]
                for td in pending:  # term docs seen since the previous rung sit between last_rung and s
                    w = weight(index.tf[td][term], index.dl[td], avg_after)
                    lo, hi = max(lo, s / w), min(hi, last_rung / w)
                pending = []
                last_rung = s
            elif term in index.tf[d]:
                pending.append(d)
        for td in pending:
            w = weight(index.tf[td][term], index.dl[td], avg_after)
            hi = min(hi, last_rung / w)
        if hi == float("inf"):
            hi = idf(1, n_after)
        df_hi, df_lo = df_from_idf(lo, n_after) if lo > 0 else float(n_after), df_from_idf(hi, n_after)
        interval_widths.append(max(0.0, df_hi - df_lo))
        est = int(round((df_lo + df_hi) / 2))
        est_h = est - df_v
        tallies["c-ranks"].add(band, truth, est_h >= 1, df_h, est_h)

    hidden_only = sum(1 for t, d in hidden_stats.df.items() if t not in visible_stats0.df)
    out.append(
        f"- channel b: export gives N exactly ({global_stats.n_docs}); hidden vocabulary not visible anywhere: "
        f"{hidden_only} terms ({hidden_only / len(hidden_stats.df):.0%} of the hidden set's vocabulary), each "
        f"revealed by naming it in a query (k terms per query -> k dfs of ~{math.log2(n_after):.1f} bits each)"
    )
    out.append(f"- channel c: mean df interval width from the 128-rung ladder {np.mean(interval_widths):.2f} docs\n")
    for label, tally in tallies.items():
        out.append(f"**{label}**\n\n{HEADER}")
        out.append(f"| all | {fmt(tally.summary())} |")
        for lo_, hi_ in ((1, 1), (2, 5), (6, 30), (31, 10**9)):
            b = band_of(lo_)
            out.append(f"| df_v {b} | {fmt(tally.summary(b))} |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    base, _queries, _qrels = load()
    print("# The three channels on SciFact (vfs tokenizer and formula)\n")
    print(
        "Adversary: reads every visible row, plants 4 + 64 anchor documents (channel a) and a 128-document "
        "ladder (channel c), then asks one query per vocabulary term (400 terms, stratified by visible df). "
        "Truth: the term occurs in at least one hidden row. `df_h` is the hidden document frequency; the "
        "estimate is the adversary's. Channel c is handed the true N and avg_dl.\n"
    )
    for kind, h, hidden in partitions(base):
        t0 = time.time()
        print(run_partition(base, kind, h, hidden))
        print(f"_({time.time() - t0:.0f}s)_\n")


if __name__ == "__main__":
    main()
