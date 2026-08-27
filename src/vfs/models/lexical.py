"""The lexical index's tokenizer, BM25 formula, block codec, builder and scorer.

The gram index nominates exact matches and carries no term frequencies;
the lexical index is the *ranked* leg beside it, built whole per reindex
under the gram epoch and stored the way grams are: one row per
``(term, block)`` holding up to :data:`BLOCK_SIZE` postings as three
delta+varint blobs, plus one summary row per term that bounds every
block without touching a posting. This module is the database-agnostic
half — the tokenizer both indexer and query share, the formula with
its constants, the codecs, and the dispatch to the Rust engine
(``crates/vfs-core/src/lexical.rs``) for tokenizing, building and
scoring. The readable reference implementations the engine is pinned
against are test oracles (``tests/support/oracles/lexical.py``).

The tokenizer is code-aware and deliberately plain. Runs of word
characters (letters, numerics, underscore — the engine's generated
Unicode tables) are the identifiers; each identifier is emitted whole
*and* split on underscores and case changes into its parts::

    PostingsBuilder  ->  postingsbuilder, postings, builder
    pthread_create   ->  pthread_create, pthread, create
    HTTPServer       ->  httpserver, http, server

so a query for ``builder`` finds the class and a query for the whole
identifier ranks it above its parts. Every term passes through the gram
index's :func:`~vfs.models.code_grams.fold_content` (Turkic-i pre-fold,
then casefold) so the two indexes agree on what a letter is. There is no
stemming and no stop list: a code corpus's most frequent terms are
language keywords whose low idf already discounts them, and stemming
prose (``indexes`` → ``index``) would merge identifiers a programmer
keeps distinct.

The formula is Lucene's BM25: ``idf = ln(1 + (N - df + 0.5)/(df + 0.5))``
(never negative), exact document length, the ``(k1 + 1)`` numerator
retained so a single-term score reads as ``<= (k1 + 1) * idf``. Weights
are computed at query time from the stored ``tf`` and ``dl``; a block's
summary carries its *true* maximum weight, so a query can tell which
blocks of a common term could still change its top-k before fetching
them (:func:`competing_blocks`).
"""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol

import numpy as np

from vfs.models.postings import encode_postings
from vfs.native import extension

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

# Hand-bumped on any tokenizer change; enters the epoch's options hash so
# a stored index is never read by a tokenizer that did not build it.
TOKENIZER_VERSION: Final = 1

BM25_K1: Final = 1.2
BM25_B: Final = 0.75

# A term's post-fold byte ceiling (longer terms are dropped, never cut)
# and character floor — one-character terms carry no ranking signal.
MAX_TERM_BYTES: Final = 64
MIN_TERM_CHARS: Final = 2

# Postings per block, and the wire format's name in the options hash.
BLOCK_SIZE: Final = 128
BLOCK_CODEC: Final = "ids:count+delta+varint;tfs,dls:varint;summary:delta+varint,le-f64"

_SUMMARY_MAX: Final = struct.Struct("<d")


class SummaryRow(NamedTuple):
    """One term's statistics and its block summary (``blocks`` is the blob)."""

    term: str
    df: int
    idf: float
    max_weight: float
    blocks: bytes


class BlockRow(NamedTuple):
    """One block of a term's postings: three blobs over ``doc_count`` postings."""

    term: str
    block_no: int
    doc_count: int
    doc_ids: bytes
    tfs: bytes
    dls: bytes


class CorpusStats(NamedTuple):
    """The corpus-wide BM25 inputs: document count and mean length."""

    n_docs: int
    avg_dl: float


class ScoreBlock(NamedTuple):
    """A fetched block for the scorer: its query-term index and summary bound."""

    term: int
    bound: float
    doc_ids: bytes
    tfs: bytes
    dls: bytes


class BlockSummary(NamedTuple):
    """A decoded summary: each block's first chunk id and true maximum weight."""

    first_ids: NDArray[np.int64]
    max_weights: NDArray[np.float64]


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize(content: str) -> list[str]:
    """Folded terms in order, duplicates kept — from the engine.

    Each word run is emitted whole; a run with more than one part (split
    on ``_`` and on case change) also emits each part. Digit-led pieces
    stay whole (``0x1f``), one-character terms are dropped, and a term
    over :data:`MAX_TERM_BYTES` after folding is dropped rather than
    truncated. Deterministic across processes and interpreters: the
    character classes are the engine's generated tables.
    """
    return extension().tokenize(content)


def options_fingerprint() -> str:
    """The lexical half of the epoch's options hash — read live, so a
    constant change (a retune, a tokenizer bump, a block resize) forces a rebuild."""
    return (
        f"bm25=k1:{BM25_K1},b:{BM25_B};tokenizer={TOKENIZER_VERSION};"
        f"term_bytes={MAX_TERM_BYTES};block={BLOCK_SIZE};codec={BLOCK_CODEC}"
    )


# ---------------------------------------------------------------------------
# The formula
# ---------------------------------------------------------------------------


def idf(df: int, n_docs: int) -> float:
    """Lucene's smoothed idf: positive for every ``df <= n_docs``."""
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def term_weight(tf: int, dl: int, avg_dl: float, term_idf: float) -> float:
    """One posting's BM25 contribution: ``idf * tf(k1+1) / (tf + k1(1 - b + b*dl/avg_dl))``."""
    norm = BM25_K1 * (1.0 - BM25_B + BM25_B * dl / avg_dl)
    return term_idf * tf * (BM25_K1 + 1.0) / (tf + norm)


# ---------------------------------------------------------------------------
# Summary codec
# ---------------------------------------------------------------------------


def encode_summary(first_ids: Sequence[int], max_weights: Sequence[float]) -> bytes:
    """Per block, the varint delta of its first id and its maximum as ``<d``."""
    out = bytearray()
    previous = 0
    for first, weight in zip(first_ids, max_weights, strict=True):
        _append_varint(out, first - previous)
        out += _SUMMARY_MAX.pack(weight)
        previous = first
    return bytes(out)


def decode_summary(blob: bytes) -> BlockSummary:
    """The inverse of :func:`encode_summary`."""
    firsts: list[int] = []
    maxes: list[float] = []
    position = 0
    first = 0
    while position < len(blob):
        delta = 0
        shift = 0
        while True:
            byte = blob[position]
            position += 1
            delta |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        first += delta
        firsts.append(first)
        maxes.append(_SUMMARY_MAX.unpack_from(blob, position)[0])
        position += _SUMMARY_MAX.size
    return BlockSummary(np.array(firsts, dtype=np.int64), np.array(maxes, dtype=np.float64))


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


class LexicalBuilder(Protocol):
    """The builder contract the engine implements (and the oracle mirrors).

    ``add_docs`` takes ``(chunk_id, content)`` pairs in strictly increasing
    id order and returns each document's token count; ``finish`` fixes
    the statistics (idempotent; feeding afterwards raises ``ValueError``);
    the two drains yield term-ordered batches of at most ``row_cap``
    summary rows and block rows respectively, ``None`` when exhausted.
    """

    def add_docs(self, docs: list[tuple[int, str]]) -> list[int]: ...

    def finish(self) -> tuple[int, float]: ...

    def next_df_batch(self, row_cap: int) -> list[tuple[str, int, float, float, bytes]] | None: ...

    def next_batch(self, row_cap: int) -> list[tuple[str, int, int, bytes, bytes, bytes]] | None: ...


def lexical_builder() -> LexicalBuilder:
    """A fresh lexical builder from the engine."""
    return extension().LexicalBuilder()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_blocks(
    blocks: Sequence[ScoreBlock],
    idfs: Sequence[float],
    avg_dl: float,
    k: int,
    *,
    candidates: NDArray[np.int64] | None = None,
) -> list[tuple[int, float]]:
    """BM25 top-``k`` over fetched blocks as ``(chunk_id, score)``,
    ``score DESC, chunk_id ASC`` — from the engine.

    ``idfs`` is indexed by each block's ``term``; ``candidates``, when
    given, is a sorted id array the ranking is restricted to. The engine
    accumulates in a fixed order (terms by descending bound, then block
    order, then posting order), so its sums are reproducible and the
    oracle's match them.
    """
    raw = None if candidates is None else np.ascontiguousarray(candidates, dtype=np.int64).tobytes()
    return extension().lexical_score(list(blocks), list(idfs), avg_dl, k, raw)


def competing_blocks(
    summary: BlockSummary,
    candidates: NDArray[np.int64],
    scores: NDArray[np.float64],
    theta: float,
    rest: float = 0.0,
) -> NDArray[np.int64]:
    """The block numbers of a term that can still change a top-k.

    A block competes when its maximum (plus ``rest``, the summed maxima
    of the other terms not yet fetched) clears ``theta`` — the current
    k-th score, ``0.0`` while fewer than k candidates exist — on its
    own, or when the best-scored candidate inside its id range would
    cross ``theta`` with that lift. ``candidates`` is sorted; each lies
    in at most one block, so the answer is bounded by their count.
    """
    maxes = summary.max_weights + rest
    best = np.full(summary.first_ids.size, -np.inf)
    if candidates.size and summary.first_ids.size:
        index = np.searchsorted(summary.first_ids, candidates, side="right") - 1
        inside = index >= 0
        np.maximum.at(best, index[inside], scores[inside])
    return np.flatnonzero((maxes >= theta) | (best + maxes >= theta)).astype(np.int64)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _append_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)


__all__ = [
    "BLOCK_CODEC",
    "BLOCK_SIZE",
    "BM25_B",
    "BM25_K1",
    "MAX_TERM_BYTES",
    "MIN_TERM_CHARS",
    "TOKENIZER_VERSION",
    "BlockRow",
    "BlockSummary",
    "CorpusStats",
    "LexicalBuilder",
    "ScoreBlock",
    "SummaryRow",
    "competing_blocks",
    "decode_summary",
    "encode_postings",
    "encode_summary",
    "idf",
    "lexical_builder",
    "options_fingerprint",
    "score_blocks",
    "term_weight",
    "tokenize",
]
