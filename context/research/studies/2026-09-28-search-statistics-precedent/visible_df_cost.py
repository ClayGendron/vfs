"""What visible-set BM25 statistics cost on vfs's block postings, and what
they do to the stored block-max bounds.

Runs in the repo venv from this directory: ``uv run --no-sync python
visible_df_cost.py``. The index is built by vfs's own Rust engine
(``vfs.models.lexical.lexical_builder``), and every visible count is taken by
the engine's own decode-and-intersect (``candidate_ids``, the grep
prefilter's kernel). Corpus: BEIR SciFact from the harness cache, once at
its own size and once replicated to REPLICAS copies (same vocabulary, df
scaled) to see how the cost grows with the corpus. No database: this counts
blob bytes (what a query would fetch) and engine CPU, not round trips.

Four ways to get a query's visible df:

- ``full``: decode every block of every query term, intersect with the
  visible id set, count. Exact. Touches every block.
- ``complement``: decode only the blocks whose id range holds a hidden id,
  count the hidden postings, subtract from the stored df. Exact. Cheap when
  the hidden set is small or clustered.
- ``partition``: a stored df per (term, partition); sum over the caller's
  partitions. Exact when the visible set is a union of partitions.
- ``fast path``: the caller sees everything; the stored df is the answer.

And one soundness check: the stored per-block maximum weight was computed
with global idf and avg_dl. Under visible statistics it can be too low
(unsound: pruning could drop a true top-k row). The rescaled bound
``max_weight * idf_v / idf_g * max(1, avg_dl_v / avg_dl_g)`` is sound.
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests.ranking.corpora import beir  # noqa: E402
from vfs.models.lexical import decode_summary, idf, lexical_builder, term_weight, tokenize  # noqa: E402
from vfs.native import extension  # noqa: E402

SEED = 20260928
REPLICAS = 40
HIDDEN_SHARES = (0.05, 0.5, 0.9)


def build(texts: list[str], replicas: int):
    """The engine's lexical index over *texts* repeated *replicas* times, ids 1..N."""
    builder = lexical_builder()
    lengths: dict[int, int] = {}
    n = len(texts)
    for copy in range(replicas):
        docs = [(copy * n + i + 1, text) for i, text in enumerate(texts)]
        for (doc_id, _), dl in zip(docs, builder.add_docs(docs), strict=True):
            lengths[doc_id] = dl
    n_docs, avg_dl = builder.finish()
    summary: dict[str, tuple[int, float, list[int], list[float]]] = {}
    while (batch := builder.next_df_batch(50_000)) is not None:
        for term, df, term_idf, _max, blob in batch:
            decoded = decode_summary(blob)
            summary[term] = (df, term_idf, decoded.first_ids.tolist(), decoded.max_weights.tolist())
    blocks: dict[str, list[tuple[bytes, bytes, bytes]]] = {}
    while (batch := builder.next_batch(50_000)) is not None:
        for term, _no, _count, ids, tfs, dls in batch:
            blocks.setdefault(term, []).append((ids, tfs, dls))
    return n_docs, avg_dl, lengths, summary, blocks


def varints(blob: bytes) -> list[int]:
    out, value, shift = [], 0, 0
    for byte in blob:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            out.append(value)
            value, shift = 0, 0
    return out


def block_ids(blob: bytes) -> list[int]:
    raw = varints(blob)
    ids, prev = [], 0
    for delta in raw[1:]:
        prev += delta
        ids.append(prev)
    return ids


def hidden_sets(n_docs: int, share: float, rng: random.Random) -> dict[str, list[int]]:
    """A contiguous hidden folder (written together) and a scattered one."""
    size = int(n_docs * share)
    start = rng.randrange(1, n_docs - size + 2)
    return {
        "clustered": list(range(start, start + size)),
        "scattered": sorted(rng.sample(range(1, n_docs + 1), size)),
    }


def query_terms(queries: list[str], summary) -> list[list[str]]:
    return [[t for t in dict.fromkeys(tokenize(q)) if t in summary] for q in queries]


def cost_full(terms, blocks, visible):
    ext = extension()
    t0 = time.perf_counter()
    counts, nbytes, nblocks = {}, 0, 0
    for term in terms:
        groups = [[ids] for ids, _tf, _dl in blocks[term]]
        nbytes += sum(len(ids) for ids, _tf, _dl in blocks[term])
        nblocks += len(groups)
        counts[term] = ext.candidate_ids(groups, visible, 0)[1]
    return counts, nbytes, nblocks, time.perf_counter() - t0


def cost_complement(terms, summary, blocks, hidden, hidden_ranges):
    """Decode only blocks whose [first_id, next_first_id) range meets a hidden id."""
    ext = extension()
    t0 = time.perf_counter()
    counts, nbytes, nblocks = {}, 0, 0
    for term in terms:
        df, _idf, firsts, _maxes = summary[term]
        touched = []
        for i, first in enumerate(firsts):
            end = firsts[i + 1] - 1 if i + 1 < len(firsts) else 1 << 62
            if meets(hidden_ranges, first, end):
                touched.append(i)
        groups = [[blocks[term][i][0]] for i in touched]
        nbytes += sum(len(g[0]) for g in groups)
        nblocks += len(groups)
        hidden_hits = ext.candidate_ids(groups, hidden, 0)[1] if groups else 0
        counts[term] = df - hidden_hits
    return counts, nbytes, nblocks, time.perf_counter() - t0


def cost_ranges(terms, summary, blocks, hidden, hidden_ranges):
    """Hidden ids as a few contiguous ranges (what path-ordered ids give a
    prefix): a block wholly inside a range counts its postings from the
    summary alone; only blocks straddling a range edge are fetched and decoded."""
    ext = extension()
    t0 = time.perf_counter()
    counts, nbytes, nblocks = {}, 0, 0
    for term in terms:
        df, _idf, firsts, _maxes = summary[term]
        last_size = df - 128 * (len(firsts) - 1)
        inside, straddle = 0, []
        for i, first in enumerate(firsts):
            end = firsts[i + 1] - 1 if i + 1 < len(firsts) else 1 << 62
            at = first_range(hidden_ranges, first)
            if at == len(hidden_ranges) or hidden_ranges[at][0] > end:
                continue
            if hidden_ranges[at][0] <= first and end <= hidden_ranges[at][1]:
                inside += 128 if i + 1 < len(firsts) else last_size
            else:
                straddle.append(i)
        groups = [[blocks[term][i][0]] for i in straddle]
        nbytes += sum(len(g[0]) for g in groups)
        nblocks += len(groups)
        edge_hits = ext.candidate_ids(groups, hidden, 0)[1] if groups else 0
        counts[term] = df - inside - edge_hits
    return counts, nbytes, nblocks, time.perf_counter() - t0


def ranges_of(ids: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for i in ids:
        if out and out[-1][1] == i - 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def first_range(ranges: list[tuple[int, int]], lo: int) -> int:
    """Index of the first range ending at or after *lo* (binary search)."""
    a, b = 0, len(ranges)
    while a < b:
        m = (a + b) // 2
        if ranges[m][1] < lo:
            a = m + 1
        else:
            b = m
    return a


def meets(ranges: list[tuple[int, int]], lo: int, hi: int) -> bool:
    # binary search for the first range ending at or after lo
    a, b = 0, len(ranges)
    while a < b:
        m = (a + b) // 2
        if ranges[m][1] < lo:
            a = m + 1
        else:
            b = m
    return a < len(ranges) and ranges[a][0] <= hi


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def row(label, values):
    return f"| {label} | {statistics.mean(values):,.1f} | {statistics.median(values):,.1f} | {pct(values, 0.95):,.1f} | {max(values):,.1f} |"


def cost_study(texts, queries, replicas, rng):
    t0 = time.perf_counter()
    n_docs, avg_dl, _lengths, summary, blocks = build(texts, replicas)
    print(f"\n## Cost at {replicas} x SciFact: N = {n_docs:,}, vocabulary {len(summary):,}, "
          f"postings {sum(s[0] for s in summary.values()):,}, "
          f"id-blob bytes {sum(len(b[0]) for bl in blocks.values() for b in bl):,} (build {time.perf_counter() - t0:.1f}s)\n")
    qterms = query_terms(queries, summary)
    head = [sum(len(ids) for term in terms for ids, _t, _d in blocks[term][:8]) for terms in qterms]
    print("Today's ranking fetch, lower bound (head blocks only, id blobs; tf and dl blobs roughly double it):\n")
    print("| per query | mean | median | p95 | max |\n|---|---|---|---|---|")
    print(row("head id-blob KB", [h / 1024 for h in head]))
    for share in HIDDEN_SHARES:
        for shape, hidden in hidden_sets(n_docs, share, rng).items():
            hidden_set = set(hidden)
            visible = [i for i in range(1, n_docs + 1) if i not in hidden_set]
            hr = ranges_of(hidden)
            full_ms, full_kb, full_blocks, comp_ms, comp_kb, comp_blocks = [], [], [], [], [], []
            rng_ms, rng_kb, rng_blocks = [], [], []
            mismatches = 0
            for terms in qterms:
                c1, b1, n1, s1 = cost_full(terms, blocks, visible)
                c2, b2, n2, s2 = cost_complement(terms, summary, blocks, hidden, hr)
                c3, b3, n3, s3 = cost_ranges(terms, summary, blocks, hidden, hr)
                mismatches += (c1 != c2) + (c1 != c3)
                rng_ms.append(s3 * 1000); rng_kb.append(b3 / 1024); rng_blocks.append(n3)
                full_ms.append(s1 * 1000); full_kb.append(b1 / 1024); full_blocks.append(n1)
                comp_ms.append(s2 * 1000); comp_kb.append(b2 / 1024); comp_blocks.append(n2)
            print(f"\n### hidden {share:.0%}, {shape} ({len(hidden):,} hidden ids; {len(hr):,} id ranges; methods disagree on {mismatches} queries)\n")
            print("| per query | mean | median | p95 | max |\n|---|---|---|---|---|")
            print(row("full: blocks decoded", full_blocks))
            print(row("full: id-blob KB fetched", full_kb))
            print(row("full: engine ms (decode + intersect)", full_ms))
            print(row("complement: blocks decoded", comp_blocks))
            print(row("complement: id-blob KB fetched", comp_kb))
            print(row("complement: engine ms", comp_ms))
            print(row("ranges: boundary blocks decoded", rng_blocks))
            print(row("ranges: id-blob KB fetched", rng_kb))
            print(row("ranges: engine ms", rng_ms))


def partition_study(texts, rng):
    """Rows a per-(term, partition) df table needs, against the global summary."""
    n = len(texts)
    token_sets = [set(tokenize(t)) for t in texts]
    vocab = set().union(*token_sets)
    print(f"\n## Per-partition df rows on SciFact (global summary rows: {len(vocab):,})\n")
    print("| partitions | shape | (term, partition) rows | x global |\n|---|---|---|---|")
    for parts in (4, 16, 64, 256):
        for shape in ("contiguous", "random"):
            if shape == "contiguous":
                label = [i * parts // n for i in range(n)]
            else:
                label = [rng.randrange(parts) for _ in range(n)]
            pairs = set()
            for i, terms in enumerate(token_sets):
                p = label[i]
                pairs.update((term, p) for term in terms)
            print(f"| {parts} | {shape} | {len(pairs):,} | {len(pairs) / len(vocab):.2f} |")


def bound_study(texts, rng):
    """Is the stored block maximum still an upper bound under visible statistics?"""
    n_docs, avg_dl, lengths, summary, blocks = build(texts, 1)
    print(f"\n## Block-max bounds under visible statistics (SciFact, N = {n_docs:,})\n")
    print("| hidden | shape | blocks | stored bound too low | rescaled bound too low | median true/rescaled |")
    print("|---|---|---|---|---|---|")
    for share in HIDDEN_SHARES:
        for shape, hidden in hidden_sets(n_docs, share, rng).items():
            hidden_set = set(hidden)
            vis = [i for i in range(1, n_docs + 1) if i not in hidden_set]
            n_v = len(vis)
            avg_v = sum(lengths[i] for i in vis) / n_v
            total = low_stored = low_rescaled = 0
            ratios = []
            for term, (df, idf_g, _firsts, maxes) in summary.items():
                parsed = [(block_ids(ids), varints(tfs), varints(dls)) for ids, tfs, dls in blocks[term]]
                df_v = sum(1 for ids, _t, _d in parsed for i in ids if i not in hidden_set)
                if df_v == 0:
                    continue
                idf_v = idf(df_v, n_v)
                scale = idf_v / idf_g * max(1.0, avg_v / avg_dl)
                for (ids, tfs, dls), stored in zip(parsed, maxes, strict=True):
                    weights = [term_weight(tf, dl, avg_v, idf_v) for i, tf, dl in zip(ids, tfs, dls, strict=True) if i not in hidden_set]
                    if not weights:
                        continue
                    true_max = max(weights)
                    total += 1
                    low_stored += true_max > stored * (1 + 1e-12)
                    low_rescaled += true_max > stored * scale * (1 + 1e-12)
                    ratios.append(true_max / (stored * scale))
            print(f"| {share:.0%} | {shape} | {total:,} | {low_stored:,} ({low_stored / total:.1%}) | {low_rescaled:,} | {statistics.median(ratios):.3f} |")


def main() -> None:
    corpus = beir("scifact")
    texts = list(corpus.docs.values())
    queries = list(corpus.queries.values())
    rng = random.Random(SEED)
    print("# Visible-set statistics on vfs block postings (SciFact, vfs engine)")
    bound_study(texts, rng)
    partition_study(texts, rng)
    cost_study(texts, queries, 1, rng)
    cost_study(texts, queries, REPLICAS, rng)


if __name__ == "__main__":
    main()
