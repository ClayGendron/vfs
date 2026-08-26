"""The lexical index's reference tokenizer, BM25 formula, and pure builder.

The gram index nominates exact matches and carries no term frequencies;
the lexical index is the *ranked* leg beside it — its own term tables,
built whole per reindex under the gram epoch, so one BM25 formula ranks
identically on every engine and joins into one statement. This module
is the database-agnostic half: the tokenizer both indexer and query
share, the formula with its constants, and the streaming builder that
turns two passes over the chunk bodies into the rows the storage layer
writes.

The tokenizer is code-aware and deliberately plain. Runs of word
characters (``\\w+`` — letters, numerics, underscore) are the
identifiers; each identifier is emitted whole *and* split on
underscores and case changes into its parts::

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
retained so a single-term score reads as ``<= (k1 + 1) * idf``. The
per-posting weight ``idf * tfc(tf, dl)`` is precomputed at build time —
the query side sums stored weights and never re-derives the formula.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Final, NamedTuple

from vfs.models.code_grams import fold_content

if TYPE_CHECKING:
    from collections.abc import Sequence

# Hand-bumped on any tokenizer change; enters the epoch's options hash so
# a stored index is never read by a tokenizer that did not build it.
TOKENIZER_VERSION: Final = 1

BM25_K1: Final = 1.2
BM25_B: Final = 0.75

# A term's post-fold byte ceiling (longer terms are dropped, never cut)
# and character floor — one-character terms carry no ranking signal.
MAX_TERM_BYTES: Final = 64
MIN_TERM_CHARS: Final = 2

# Word runs: Python's ``\w`` is the Unicode alphanumerics plus underscore
# — the letters, numerics, and joiner an identifier is made of.
_WORD_RUN: Final = re.compile(r"\w+")


class DocRow(NamedTuple):
    """One indexed chunk: its row id, owning entry, and token count."""

    chunk_id: int
    entry_id: str
    dl: int


class TermRow(NamedTuple):
    """One (term, chunk) posting with its precomputed BM25 weight."""

    term: str
    chunk_id: int
    tf: int
    weight: float


class DfRow(NamedTuple):
    """One term's corpus statistics: document frequency and its idf."""

    term: str
    df: int
    idf: float


class CorpusStats(NamedTuple):
    """The corpus-wide BM25 inputs: document count and mean length."""

    n_docs: int
    avg_dl: float


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize(content: str) -> list[str]:
    """The reference tokenizer: folded terms in order, duplicates kept.

    Each word run is emitted whole; a run with more than one part (split
    on ``_`` and on case change) also emits each part. Digit-led pieces
    stay whole (``0x1f``), one-character terms are dropped, and a term
    over :data:`MAX_TERM_BYTES` after folding is dropped rather than
    truncated. Deterministic across processes: nothing here depends on
    hash order.
    """
    terms: list[str] = []
    for match in _WORD_RUN.finditer(content):
        run = match.group()
        parts = _identifier_parts(run)
        _emit(terms, run)
        if len(parts) > 1:
            for part in parts:
                _emit(terms, part)
    return terms


def options_fingerprint() -> str:
    """The lexical half of the epoch's options hash — read live, so a
    constant change (a retune, a tokenizer bump) forces a rebuild."""
    return f"bm25=k1:{BM25_K1},b:{BM25_B};tokenizer={TOKENIZER_VERSION};term_bytes={MAX_TERM_BYTES}"


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
# The builder
# ---------------------------------------------------------------------------


class LexicalIndexBuilder:
    """Two passes over the chunk stream: statistics first, weighted rows second.

    A posting's weight needs the term's ``df`` and the corpus's ``avg_dl``,
    which only the last document fixes — so :meth:`observe` streams the
    corpus once for document lengths and frequencies, :meth:`finish`
    fixes the statistics and every term's idf, and :meth:`weigh` streams
    it again, re-tokenizing each batch into its weighted term rows. Both
    passes are streaming: the builder never holds a posting, only the
    vocabulary (one ``df`` per distinct term), so memory is bounded by
    the corpus's vocabulary rather than its size. The price is tokenizing
    every chunk twice — the tokenizer's share of the build is the one
    number that decides the Rust port.
    """

    def __init__(self) -> None:
        self._df: dict[str, int] = {}
        self._n_docs = 0
        self._total_dl = 0
        self._stats: CorpusStats | None = None
        self._idf: dict[str, float] = {}
        self._dfs: list[DfRow] = []

    def observe(self, docs: Sequence[tuple[int, str, str]]) -> list[DocRow]:
        """Pass one: count each ``(chunk_id, entry_id, content)`` into ``df``
        and the length totals; the batch's doc rows come back for writing."""
        if self._stats is not None:
            raise ValueError("statistics are fixed; create a fresh builder")
        rows: list[DocRow] = []
        for chunk_id, entry_id, content in docs:
            tokens = tokenize(content)
            for term in set(tokens):
                self._df[term] = self._df.get(term, 0) + 1
            self._n_docs += 1
            self._total_dl += len(tokens)
            rows.append(DocRow(chunk_id, entry_id, len(tokens)))
        return rows

    def finish(self) -> CorpusStats:
        """Fix the corpus statistics and every term's idf; idempotent."""
        if self._stats is None:
            avg_dl = self._total_dl / self._n_docs if self._n_docs else 0.0
            self._stats = CorpusStats(self._n_docs, avg_dl)
            self._dfs = [DfRow(term, df, idf(df, self._n_docs)) for term, df in sorted(self._df.items())]
            self._idf = {row.term: row.idf for row in self._dfs}
        return self._stats

    @property
    def dfs(self) -> Sequence[DfRow]:
        """Every term's statistics in term order; empty before :meth:`finish`."""
        return self._dfs

    def weigh(self, docs: Sequence[tuple[int, str, str]]) -> list[TermRow]:
        """Pass two: the batch's weighted term rows, term-ordered within the batch.

        Every term seen here was counted in pass one — the two passes read
        the same rows — so a term missing from the vocabulary is a caller
        bug and raises rather than scoring against a stale corpus.
        """
        stats = self.finish()
        rows: list[TermRow] = []
        for chunk_id, _entry_id, content in docs:
            tokens = tokenize(content)
            counts: dict[str, int] = {}
            for term in tokens:
                counts[term] = counts.get(term, 0) + 1
            dl = len(tokens)
            for term, tf in counts.items():
                rows.append(TermRow(term, chunk_id, tf, term_weight(tf, dl, stats.avg_dl, self._idf[term])))
        rows.sort()
        return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _emit(terms: list[str], raw: str) -> None:
    """Fold *raw* and append it when it clears the length gates."""
    term = fold_content(raw)
    if len(term) >= MIN_TERM_CHARS and len(term.encode()) <= MAX_TERM_BYTES:
        terms.append(term)


def _identifier_parts(run: str) -> list[str]:
    """Split one word run on underscores, then on case changes.

    A digit-led piece is kept whole (``0x1f`` never splits at ``f``); a
    case change is lower/digit→upper (``getValue``, ``sha256Hash``) or
    the last capital of an acronym run (``HTTPServer`` → ``HTTP``,
    ``Server``).
    """
    parts: list[str] = []
    for piece in run.split("_"):
        if not piece:
            continue
        if piece[0].isdigit():
            parts.append(piece)
            continue
        start = 0
        for index in range(1, len(piece)):
            if piece[index].isupper() and _case_boundary(piece, index):
                parts.append(piece[start:index])
                start = index
        parts.append(piece[start:])
    return parts


def _case_boundary(piece: str, index: int) -> bool:
    """True when the capital at *index* starts a new part."""
    previous = piece[index - 1]
    if previous.islower() or previous.isdigit():
        return True
    return previous.isupper() and index + 1 < len(piece) and piece[index + 1].islower()


__all__ = [
    "BM25_B",
    "BM25_K1",
    "MAX_TERM_BYTES",
    "MIN_TERM_CHARS",
    "TOKENIZER_VERSION",
    "CorpusStats",
    "DfRow",
    "DocRow",
    "LexicalIndexBuilder",
    "TermRow",
    "idf",
    "options_fingerprint",
    "term_weight",
    "tokenize",
]
