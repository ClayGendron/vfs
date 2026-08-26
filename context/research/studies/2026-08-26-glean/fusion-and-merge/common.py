"""Shared corpus, embedders, lexical scorers and per-mount hybrid search for
the merge simulation. Run with the throwaway venv described in README.md.

Corpus: BEIR SciFact test split via ir_datasets (5,183 abstracts, 300 claims,
339 graded qrels). Embedders: model2vec potion-base-8M (256-d), potion-base-4M
(128-d) and a feature-hashing bag-of-words embedder (256-d) — three genuinely
different vector spaces. Lexical: bm25s with per-mount k1/b.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field

import bm25s
import ir_datasets
import numpy as np
from model2vec import StaticModel

SEED = 20260826
TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass
class Corpus:
    doc_ids: list[str]
    texts: list[str]
    queries: dict[str, str]
    qrels: dict[str, dict[str, int]]

    @property
    def n(self) -> int:
        return len(self.doc_ids)


def load_scifact(name: str | None = None) -> Corpus:
    ds = ir_datasets.load(name or os.environ.get("CORPUS", "beir/scifact/test"))
    docs = sorted(ds.docs_iter(), key=lambda d: d.doc_id)
    doc_ids = [d.doc_id for d in docs]
    texts = [f"{getattr(d, 'title', '')}\n{d.text}" for d in docs]
    queries = {q.query_id: q.text for q in ds.queries_iter()}
    qrels: dict[str, dict[str, int]] = {}
    for r in ds.qrels_iter():
        qrels.setdefault(r.query_id, {})[r.doc_id] = r.relevance
    queries = {q: t for q, t in queries.items() if q in qrels}
    return Corpus(doc_ids, texts, queries, qrels)


# ---------------------------------------------------------------------------
# Embedders — every mount gets a different vector space
# ---------------------------------------------------------------------------


class HashEmbedder:
    """Signed feature hashing of unigrams+bigrams, L2-normalised. Deterministic,
    offline, and deliberately weak — the 'GENERIC floor' mount's embedder."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _feat(self, tok: str) -> tuple[int, float]:
        h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        v = int.from_bytes(h, "little")
        return v % self.dim, 1.0 if (v >> 40) & 1 else -1.0

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = tokens(t)
            for tok in toks + [a + "_" + b for a, b in zip(toks, toks[1:])]:
                j, s = self._feat(tok)
                out[i, j] += s
        return l2(out)


def l2(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


EMBEDDERS = {
    "potion-8M": lambda: StaticModel.from_pretrained("minishlab/potion-base-8M"),
    "potion-4M": lambda: StaticModel.from_pretrained("minishlab/potion-base-4M"),
    "hash-256": lambda: HashEmbedder(256),
}


def embed_all(name: str, corpus: Corpus) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    model = EMBEDDERS[name]()
    docs = l2(np.asarray(model.encode(corpus.texts), dtype=np.float32))
    qids = list(corpus.queries)
    qv = l2(np.asarray(model.encode([corpus.queries[q] for q in qids]), dtype=np.float32))
    return docs, dict(zip(qids, qv))


# ---------------------------------------------------------------------------
# Lexical scorer — bm25s over an arbitrary doc subset, arbitrary k1/b
# ---------------------------------------------------------------------------


class Lexical:
    def __init__(self, texts: list[str], k1: float, b: float):
        self.n = len(texts)
        self.bm = bm25s.BM25(k1=k1, b=b)
        self.bm.index(bm25s.tokenize(texts, stopwords="en", show_progress=False), show_progress=False)

    def scores(self, query: str) -> np.ndarray:
        toks = bm25s.tokenize([query], stopwords="en", return_ids=False, show_progress=False)[0]
        if not toks:
            return np.zeros(self.n, dtype=np.float32)
        return np.asarray(self.bm.get_scores(toks), dtype=np.float32)


# ---------------------------------------------------------------------------
# Fusion primitives (within one mount and for the merge strategies)
# ---------------------------------------------------------------------------


def rank_desc(scores: np.ndarray, ids: np.ndarray | None = None) -> np.ndarray:
    """Indices sorted by score desc, ties broken by doc position (stable)."""
    order = np.lexsort((np.arange(len(scores)), -scores))
    return order if ids is None else ids[order]


def minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        return np.ones_like(x) if hi > 0 else np.zeros_like(x)
    return (x - lo) / (hi - lo)


def zscore(x: np.ndarray) -> np.ndarray:
    sd = float(x.std())
    return (x - x.mean()) / sd if sd > 1e-12 else np.zeros_like(x)


def rrf_from_ranks(rank_lists: list[dict[int, int]], k: float, weights=None) -> dict[int, float]:
    weights = weights or [1.0] * len(rank_lists)
    out: dict[int, float] = {}
    for w, rl in zip(weights, rank_lists):
        for d, r in rl.items():
            out[d] = out.get(d, 0.0) + w / (k + r)
    return out


@dataclass
class Hit:
    doc: int  # global doc index
    score: float  # the mount's exposed (native) score
    bm25: float  # raw BM25 from the mount's lexical leg
    cos: float  # raw cosine from the mount's vector leg
    rank: int  # 1-based rank inside the mount's list
    mount: int


@dataclass
class MountConfig:
    name: str
    embedder: str
    k1: float
    b: float
    fusion: str  # "rrf" | "cc-minmax" | "cc-zscore" | "lexical-only"
    k: float = 60.0
    alpha: float = 0.5  # weight on the vector leg for cc-*
    scale: float = 1.0  # multiplies the exposed score (score-scale heterogeneity)


@dataclass
class Mount:
    cfg: MountConfig
    docs: np.ndarray  # global doc indices held by this mount
    lex: Lexical
    dvec: np.ndarray  # embeddings of this mount's docs (rows align with docs)
    qvec: dict[str, np.ndarray]
    cache: dict = field(default_factory=dict)

    def search(self, qid: str, query: str, limit: int, depth: int = 100) -> list[Hit]:
        """The mount's own hybrid top-`limit`. Both legs are scored over the
        candidate union (a DB backend holding both columns can do this), the
        mount fuses with its native function and returns its native score."""
        bm = self.lex.scores(query)
        cos = self.dvec @ self.qvec[qid]
        lex_top = rank_desc(bm)[:depth]
        vec_top = rank_desc(cos)[:depth]
        if self.cfg.fusion == "lexical-only":
            cand = lex_top
        else:
            cand = np.unique(np.concatenate([lex_top, vec_top]))
        f = self.cfg.fusion
        if f == "rrf":
            lr = {int(d): i + 1 for i, d in enumerate(lex_top)}
            vr = {int(d): i + 1 for i, d in enumerate(vec_top)}
            fused = rrf_from_ranks([lr, vr], self.cfg.k)
            sc = np.array([fused.get(int(d), 0.0) for d in cand], dtype=np.float32)
        elif f in ("cc-minmax", "cc-zscore"):
            norm = minmax if f == "cc-minmax" else zscore
            a = self.cfg.alpha
            sc = a * norm(cos[cand]) + (1 - a) * norm(bm[cand])
        elif f == "lexical-only":
            sc = bm[cand]
        else:
            raise ValueError(f)
        sc = sc * self.cfg.scale
        order = rank_desc(sc)[:limit]
        return [
            Hit(int(self.docs[cand[i]]), float(sc[i]), float(bm[cand[i]]), float(cos[cand[i]]), r + 1, -1)
            for r, i in enumerate(order)
        ]


def kmeans_split(x: np.ndarray, k: int, seed: int = SEED, iters: int = 30) -> np.ndarray:
    rng = np.random.default_rng(seed)
    cent = x[rng.choice(len(x), k, replace=False)]
    lab = np.zeros(len(x), dtype=int)
    for _ in range(iters):
        lab = np.argmax(x @ cent.T, axis=1)
        for j in range(k):
            m = x[lab == j]
            if len(m):
                cent[j] = m.mean(axis=0)
        cent = l2(cent)
    return lab
