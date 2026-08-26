"""Shared pieces of the Option B prototype bench: paths, the block codec,
the BM25 formula, numpy scoring (full and block-max), and query drawing."""

from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import statistics
import time
from pathlib import Path

import numpy as np

from vfs.models.lexical import BM25_B, BM25_K1

SCRATCH = Path(os.environ.get("BM25B_SCRATCH", "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/9aca8a65-866f-4cbb-bc2b-685f1963370c/scratchpad"))
STORE = SCRATCH / "bench_lexical_clean.sqlite"
OPTION_B_PY = SCRATCH / "optionb_py.sqlite"
OPTION_B_RS = SCRATCH / "optionb_rs.sqlite"
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
RUSTBENCH = HERE / "rustbench" / "target" / "release" / "rustbench"

SCAN = (
    "SELECT c.id, c.entry_id, c.content FROM vfs_chunks c JOIN vfs e ON e.entry_id = c.entry_id "
    "WHERE e.chunked AND e.indexable AND e.deleted_at IS NULL ORDER BY c.id"
)
TOP_K = 10
EPOCH_A = 2  # the store's current lexical epoch
EPOCH_B = 1


# ---------------------------------------------------------------------------
# Codec (delta + LEB128 varint; the prototype's own, mirrors rustbench/codec.rs)
# ---------------------------------------------------------------------------


def put_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)


def decode_varints(blob: bytes) -> np.ndarray:
    """Vectorized LEB128 decode of every varint in *blob* (no count header)."""
    data = np.frombuffer(blob, dtype=np.uint8)
    continues = (data & 0x80) != 0
    ends = np.flatnonzero(~continues)
    starts = np.empty(ends.size, dtype=np.int64)
    starts[0] = 0
    starts[1:] = ends[:-1] + 1
    lengths = ends - starts + 1
    groups = np.repeat(np.arange(ends.size), lengths)
    shifts = 7 * (np.arange(data.size, dtype=np.int64) - starts[groups])
    payloads = (data & 0x7F).astype(np.int64) << shifts
    values = np.zeros(ends.size, dtype=np.int64)
    np.add.at(values, groups, payloads)
    return values


def decode_varints_fast(blob: bytes) -> np.ndarray:
    """Same result as :func:`decode_varints`, with a fast path when every
    byte is a single-byte varint (the common case for tfs and small deltas)."""
    data = np.frombuffer(blob, dtype=np.uint8)
    if not (data & 0x80).any():
        return data.astype(np.int64)
    return decode_varints(blob)


def decode_block(doc_ids: bytes, tfs: bytes, dls: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ids = np.cumsum(decode_varints_fast(doc_ids))
    return ids, decode_varints_fast(tfs), decode_varints_fast(dls)


# ---------------------------------------------------------------------------
# Formula
# ---------------------------------------------------------------------------


def idf(df: int, n_docs: int) -> float:
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def tf_norm(tf: np.ndarray | float, dl: np.ndarray | float, avg_dl: float):
    return tf * (BM25_K1 + 1.0) / (tf + BM25_K1 * (1.0 - BM25_B + BM25_B * dl / avg_dl))


def block_bound(term_idf: float, max_tf: int, min_dl: int, avg_dl: float) -> float:
    """An upper bound on any posting's weight in the block: tfc is increasing
    in tf and decreasing in dl, so (max_tf, min_dl) bounds every pair."""
    return term_idf * float(tf_norm(float(max_tf), float(min_dl), avg_dl))


# ---------------------------------------------------------------------------
# Scoring over fetched blocks
# ---------------------------------------------------------------------------

Block = tuple[str, int, int, int, int, bytes, bytes, bytes]  # term, block_no, doc_count, max_tf, min_dl, ids, tfs, dls


def topk(ids: np.ndarray, scores: np.ndarray, k: int = TOP_K) -> list[tuple[int, float]]:
    """Top-k by score desc, id asc — the same order as Option A's SQL."""
    if ids.size == 0:
        return []
    order = np.lexsort((ids, -scores))[:k]
    return [(int(ids[i]), float(scores[i])) for i in order]


def aggregate(all_ids: list[np.ndarray], all_scores: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    if not all_ids:
        return np.empty(0, dtype=np.int64), np.empty(0)
    ids = np.concatenate(all_ids)
    scores = np.concatenate(all_scores)
    uniq, inverse = np.unique(ids, return_inverse=True)
    return uniq, np.bincount(inverse, weights=scores, minlength=uniq.size)


def score_full(blocks: list[Block], idfs: dict[str, float], avg_dl: float, allow: np.ndarray | None = None):
    """Full evaluation: decode every block, weight every posting, aggregate."""
    all_ids: list[np.ndarray] = []
    all_scores: list[np.ndarray] = []
    for term, _no, _count, _max_tf, _min_dl, ids_b, tfs_b, dls_b in blocks:
        ids, tfs, dls = decode_block(ids_b, tfs_b, dls_b)
        all_ids.append(ids)
        all_scores.append(idfs[term] * tf_norm(tfs, dls, avg_dl))
    ids, scores = aggregate(all_ids, all_scores)
    if allow is not None:
        keep = np.isin(ids, allow)
        ids, scores = ids[keep], scores[keep]
    return topk(ids, scores), ids.size


def score_full_batched(blocks: list[Block], idfs: dict[str, float], avg_dl: float, allow: np.ndarray | None = None):
    """Full evaluation in one numpy pipeline: every block's blobs are
    concatenated per column and decoded once; a segmented cumsum (global
    cumsum minus each block's starting offset) restores absolute ids."""
    if not blocks:
        return [], 0
    counts = np.fromiter((b[2] for b in blocks), dtype=np.int64, count=len(blocks))
    ids_blob = b"".join(b[5] for b in blocks)
    tfs_blob = b"".join(b[6] for b in blocks)
    dls_blob = b"".join(b[7] for b in blocks)
    deltas = decode_varints_fast(ids_blob)
    run = np.cumsum(deltas)
    starts = np.cumsum(counts) - counts
    offsets = np.repeat(run[starts] - deltas[starts], counts)
    ids = run - offsets
    tfs = decode_varints_fast(tfs_blob)
    dls = decode_varints_fast(dls_blob)
    term_idf = np.repeat(np.fromiter((idfs[b[0]] for b in blocks), dtype=np.float64, count=len(blocks)), counts)
    scores = term_idf * tf_norm(tfs, dls, avg_dl)
    uniq, inverse = np.unique(ids, return_inverse=True)
    agg = np.bincount(inverse, weights=scores, minlength=uniq.size)
    if allow is not None:
        keep = np.isin(uniq, allow)
        uniq, agg = uniq[keep], agg[keep]
    return topk(uniq, agg), uniq.size


def score_blockmax(blocks: list[Block], idfs: dict[str, float], avg_dl: float, k: int = TOP_K):
    """Block-max MaxScore: terms in decreasing bound order; once the sum of
    the remaining terms' bounds cannot lift a new document over the current
    k-th score, only blocks whose range holds a candidate that could still
    cross it are decoded. Returns (top-k, blocks decoded, blocks skipped)."""
    by_term: dict[str, list[Block]] = {}
    for b in blocks:
        by_term.setdefault(b[0], []).append(b)
    # Per-term bound = max over its blocks; block id range from doc_count and deltas.
    term_bound = {t: max(block_bound(idfs[t], b[3], b[4], avg_dl) for b in bs) for t, bs in by_term.items()}
    order = sorted(by_term, key=lambda t: -term_bound[t])
    suffix = [0.0] * (len(order) + 1)
    for i in range(len(order) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + term_bound[order[i]]
    cand_ids = np.empty(0, dtype=np.int64)
    cand_scores = np.empty(0)
    theta = 0.0
    decoded = skipped = 0
    for i, term in enumerate(order):
        rest = suffix[i + 1]
        new_ids: list[np.ndarray] = []
        new_scores: list[np.ndarray] = []
        for b in by_term[term]:
            _t, _no, count, max_tf, min_dl, ids_b, tfs_b, dls_b = b
            ub = block_bound(idfs[term], max_tf, min_dl, avg_dl)
            if theta > 0.0 and ub + rest < theta:
                # New documents cannot enter; can an existing candidate in range?
                lo, hi = _block_range(ids_b)
                a = np.searchsorted(cand_ids, lo, side="left")
                z = np.searchsorted(cand_ids, hi, side="right")
                if a == z or float(cand_scores[a:z].max()) + ub + rest < theta:
                    skipped += 1
                    continue
            decoded += 1
            ids, tfs, dls = decode_block(ids_b, tfs_b, dls_b)
            new_ids.append(ids)
            new_scores.append(idfs[term] * tf_norm(tfs, dls, avg_dl))
        if new_ids:
            cand_ids, cand_scores = aggregate([cand_ids, *new_ids], [cand_scores, *new_scores])
        if cand_scores.size >= k:
            theta = float(np.partition(cand_scores, cand_scores.size - k)[cand_scores.size - k])
    return topk(cand_ids, cand_scores, k), decoded, skipped


def _block_range(ids_b: bytes) -> tuple[int, int]:
    """First and last doc id of a delta blob without decoding it in full."""
    data = np.frombuffer(ids_b, dtype=np.uint8)
    if not (data & 0x80).any():
        first = int(data[0])
        return first, int(data.sum(dtype=np.int64))
    values = decode_varints(ids_b)
    return int(values[0]), int(values.sum())


# ---------------------------------------------------------------------------
# Query drawing (as the lexical-leg study: mid-df, +common, +rare)
# ---------------------------------------------------------------------------


def draw_queries(store: sqlite3.Connection, epoch: int, per_arity: int = 15, seed: int = 7) -> dict[int, list[list[str]]]:
    n = store.execute("SELECT n_docs FROM vfs_lex_stats WHERE epoch = ?", (epoch,)).fetchone()[0]
    rows = store.execute("SELECT term, df FROM vfs_lex_df WHERE epoch = ?", (epoch,)).fetchall()
    mid = [t for t, df in rows if 0.002 * n <= df <= 0.02 * n]
    common = [t for t, df in rows if df > 0.2 * n]
    rare = [t for t, df in rows if 2 <= df < 0.002 * n]
    rng = random.Random(seed)
    queries: dict[int, list[list[str]]] = {1: [], 3: [], 6: []}
    for _ in range(per_arity):
        queries[1].append([rng.choice(mid)])
        queries[3].append(rng.sample(mid, 2) + [rng.choice(common)])
        queries[6].append([rng.choice(rare)] + rng.sample(mid, 4) + [rng.choice(common)])
    return queries


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------


def timed(fn, reps: int = 7):
    """Run *fn* *reps* times; return (median ms, last result)."""
    times = []
    result = None
    for _ in range(reps):
        t0 = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(times), result


def round_top(top: list[tuple[int, float]]) -> list[tuple[int, float]]:
    return [(i, round(s, 9)) for i, s in top]


def kendall_tau(a: list[int], b: list[int]) -> float | None:
    """Kendall tau over the ids common to both rankings (None if < 2)."""
    common = [x for x in a if x in b]
    if len(common) < 2:
        return None
    pa = {x: i for i, x in enumerate(a)}
    pb = {x: i for i, x in enumerate(b)}
    conc = disc = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            x, y = common[i], common[j]
            s = (pa[x] - pa[y]) * (pb[x] - pb[y])
            if s > 0:
                conc += 1
            elif s < 0:
                disc += 1
    return (conc - disc) / (conc + disc) if conc + disc else None


def dump_json(name: str, payload: dict) -> Path:
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / name
    out.write_text(json.dumps(payload, indent=1, default=str))
    return out


def dbstat_bytes(conn: sqlite3.Connection) -> dict[str, int]:
    """Per-table on-disk bytes from sqlite's dbstat virtual table."""
    return {name: int(b) for name, b in conn.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name")}
