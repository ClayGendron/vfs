"""Shared corpus, index, BM25 and partition code for the statistics-leak study.

Runs in the repo venv (``uv run --no-sync python``) so the tokenizer and the
formula are vfs's own: ``vfs.models.lexical.tokenize`` (the Rust engine),
``idf`` and ``term_weight``. One SciFact abstract is one document and one
chunk. Scores leave the "server" the way ``glean`` emits them: min-max
scaled over the answer to the unit interval and rounded to nine decimals.

The corpus is BEIR SciFact from the harness cache (``tests/ranking/corpora.py``).
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tests.ranking.corpora import beir  # noqa: E402
from vfs.models.lexical import BM25_B, BM25_K1, idf, term_weight, tokenize  # noqa: E402

SEED = 20260905
SCORE_DECIMALS = 9  # vfs.storage.ranking.SCORE_DECIMALS
FILLER = "zzfill"  # a planted document's padding token; never queried


class Stats(NamedTuple):
    n_docs: int
    avg_dl: float
    df: dict[str, int]

    def idf(self, term: str) -> float:
        return idf(self.df.get(term, 0), self.n_docs)


class Index:
    """Per-document term frequencies and lengths plus an inverted index.

    Documents are integer positions; ``plant`` appends adversary-written
    documents and returns their positions.
    """

    def __init__(self, doc_ids: list[str], texts: list[str]):
        self.doc_ids = list(doc_ids)
        self.tf: list[dict[str, int]] = []
        self.dl: list[int] = []
        self.postings: dict[str, dict[int, int]] = {}
        for text in texts:
            self._add(tokenize(text))

    def _add(self, tokens: list[str]) -> int:
        position = len(self.tf)
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        self.tf.append(counts)
        self.dl.append(len(tokens))
        for term, tf in counts.items():
            self.postings.setdefault(term, {})[position] = tf
        return position

    def plant(self, tokens: list[str]) -> int:
        self.doc_ids.append(f"planted-{len(self.doc_ids)}")
        return self._add(tokens)

    @property
    def n(self) -> int:
        return len(self.tf)

    def stats_over(self, docs: set[int] | list[int]) -> Stats:
        """Exact BM25 statistics over a document subset (vfs's ``lex_stats`` + ``lex_df`` for that subset)."""
        docs = list(docs)
        df: dict[str, int] = {}
        total = 0
        for d in docs:
            total += self.dl[d]
            for term in self.tf[d]:
                df[term] = df.get(term, 0) + 1
        return Stats(len(docs), total / len(docs) if docs else 0.0, df)

    def raw_scores(self, terms: list[str], visible: set[int], stats: Stats) -> dict[int, float]:
        """BM25 over *visible* documents with *stats*: vfs's formula, term by term."""
        scores: dict[int, float] = {}
        for term in dict.fromkeys(terms):
            postings = self.postings.get(term)
            if not postings:
                continue
            term_idf = stats.idf(term)
            for d, tf in postings.items():
                if d in visible:
                    scores[d] = scores.get(d, 0.0) + term_weight(tf, self.dl[d], stats.avg_dl, term_idf)
        return scores


def load() -> tuple[Index, dict[str, list[str]], dict[str, dict[str, int]]]:
    corpus = beir("scifact")
    doc_ids = sorted(corpus.docs)
    index = Index(doc_ids, [corpus.docs[d] for d in doc_ids])
    queries = {qid: tokenize(text) for qid, text in corpus.queries.items()}
    position = {d: i for i, d in enumerate(doc_ids)}
    qrels = {
        qid: {position[d]: grade for d, grade in graded.items() if grade > 0 and d in position}
        for qid, graded in corpus.qrels.items()
    }
    return index, queries, {qid: g for qid, g in qrels.items() if g}


# ---------------------------------------------------------------------------
# The server: what a caller observes
# ---------------------------------------------------------------------------


def serve(index: Index, terms: list[str], visible: set[int], stats: Stats, limit: int | None = None) -> list[tuple[int, float]]:
    """The answer as ``glean`` shapes it: visible rows only, min-max scaled, nine decimals, score desc then doc."""
    raw = index.raw_scores(terms, visible, stats)
    if not raw:
        return []
    low, high = min(raw.values()), max(raw.values())
    span = high - low
    scaled = {d: round(1.0 if span == 0.0 else (s - low) / span, SCORE_DECIMALS) for d, s in raw.items()}
    ordered = sorted(scaled.items(), key=lambda item: (-item[1], item[0]))
    return ordered if limit is None else ordered[:limit]


def minmax(values: np.ndarray) -> np.ndarray:
    low, high = float(values.min()), float(values.max())
    if high - low == 0.0:
        return np.ones_like(values)
    return (values - low) / (high - low)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def ndcg_at(ranking: list[int], graded: dict[int, int], k: int = 10) -> float:
    """Järvelin–Kekäläinen nDCG@k with linear gains (ranx's default ``ndcg``)."""
    dcg = sum(graded.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranking[:k]))
    ideal = sorted(graded.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def evaluate(index: Index, queries: dict[str, list[str]], qrels: dict[str, dict[int, int]], visible: set[int], stats: Stats) -> float:
    """Mean nDCG@10 over the queries with at least one *visible* relevant document."""
    values = []
    for qid, terms in queries.items():
        graded = {d: g for d, g in qrels.get(qid, {}).items() if d in visible}
        if not graded:
            continue
        ranking = [d for d, _ in serve(index, terms, visible, stats, limit=10)]
        values.append(ndcg_at(ranking, graded))
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# Partitions
# ---------------------------------------------------------------------------


def random_hidden(n: int, h: float, seed: int = SEED) -> set[int]:
    rng = random.Random(seed)
    return set(rng.sample(range(n), int(round(h * n))))


def _hashed_tfidf(index: Index, dims: int = 4096) -> np.ndarray:
    stats = index.stats_over(range(index.n))
    matrix = np.zeros((index.n, dims), dtype=np.float32)
    for d in range(index.n):
        for term, tf in index.tf[d].items():
            slot = hash(term) % dims
            matrix[d, slot] += (1 + math.log(tf)) * stats.idf(term)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def topical_hidden(index: Index, h: float, seed: int = SEED, clusters: int = 12) -> set[int]:
    """A subject-shaped hidden set: k-means over hashed tf-idf, clusters
    swallowed in order of nearness to a seed cluster until ``h`` of the
    corpus is hidden (the last cluster by nearness to its centroid)."""
    rng = np.random.default_rng(seed)
    x = _hashed_tfidf(index)
    centroids = x[rng.choice(index.n, clusters, replace=False)]
    for _ in range(20):
        labels = np.argmax(x @ centroids.T, axis=1)
        for c in range(clusters):
            members = x[labels == c]
            if len(members):
                centroids[c] = members.mean(axis=0)
        centroids /= np.maximum(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-9)
    labels = np.argmax(x @ centroids.T, axis=1)
    seed_cluster = int(np.argmax(np.bincount(labels, minlength=clusters)))
    order = np.argsort(-(centroids @ centroids[seed_cluster]))
    target = int(round(h * index.n))
    hidden: list[int] = []
    for c in order:
        members = np.flatnonzero(labels == c)
        if len(hidden) + len(members) <= target:
            hidden.extend(int(m) for m in members)
        else:
            nearness = x[members] @ centroids[c]
            take = members[np.argsort(-nearness)[: target - len(hidden)]]
            hidden.extend(int(m) for m in take)
            break
    return set(hidden)


def partitions(index: Index, fractions=(0.1, 0.5, 0.9)) -> list[tuple[str, float, set[int]]]:
    out = []
    for h in fractions:
        out.append(("random", h, random_hidden(index.n, h)))
    for h in fractions:
        out.append(("topical", h, topical_hidden(index, h)))
    return out


# ---------------------------------------------------------------------------
# Vocabulary sample for the adversary
# ---------------------------------------------------------------------------

BANDS = ((1, 1), (2, 5), (6, 30), (31, 10**9))


def vocabulary_sample(index: Index, visible: set[int], per_band: int = 100, seed: int = SEED) -> list[str]:
    """Terms the caller can see, stratified by visible df; planted tokens excluded."""
    visible_df = index.stats_over(visible).df
    rng = random.Random(seed)
    sample: list[str] = []
    for lo, hi in BANDS:
        band = sorted(t for t, df in visible_df.items() if lo <= df <= hi and t != FILLER and not t.startswith("zq"))
        sample.extend(rng.sample(band, min(per_band, len(band))))
    return sample


def band_of(df: int) -> str:
    for lo, hi in BANDS:
        if lo <= df <= hi:
            return f"{lo}-{hi}" if hi < 10**9 else f"{lo}+"
    return "0"


def weight(tf: int, dl: int, avg_dl: float) -> float:
    """The idf-free part of vfs's term weight."""
    return term_weight(tf, dl, avg_dl, 1.0)


def df_from_idf(value: float, n_docs: int) -> float:
    """Invert Lucene's idf: ``df = (n + 0.5) / (e^idf - 1 + 1) - 0.5``."""
    return (n_docs + 0.5) / math.exp(value) - 0.5


__all__ = [
    "BM25_B",
    "BM25_K1",
    "FILLER",
    "SEED",
    "Index",
    "Stats",
    "band_of",
    "df_from_idf",
    "evaluate",
    "idf",
    "load",
    "minmax",
    "ndcg_at",
    "partitions",
    "random_hidden",
    "serve",
    "topical_hidden",
    "vocabulary_sample",
    "weight",
]
