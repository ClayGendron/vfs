"""The lexical index's tokenizer, BM25 formula, block codec, builder and scorer.

The gram index nominates exact matches and carries no term frequencies;
the lexical index is the *ranked* leg beside it, built whole per reindex
under the gram epoch and stored the way grams are: one row per
``(term, block)`` holding up to :data:`BLOCK_SIZE` postings as three
delta+varint blobs, plus one summary row per term that bounds every
block without touching a posting. This module is the database-agnostic
half — the tokenizer both indexer and query share, the formula with
its constants, the codecs, and the pure-Python builder and scorer that
are the reference the Rust engine (``crates/vfs-core/src/lexical.rs``)
must match byte for byte. Per the seam's ownership rule, dispatch to the
active engine lives here beside the pure implementation.

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
retained so a single-term score reads as ``<= (k1 + 1) * idf``. Weights
are computed at query time from the stored ``tf`` and ``dl``; a block's
summary carries its *true* maximum weight, so a query can tell which
blocks of a common term could still change its top-k before fetching
them (:func:`competing_blocks`).
"""

from __future__ import annotations

import math
import re
import struct
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol

import numpy as np

from vfs.models.code_grams import fold_content
from vfs.models.postings import decode_postings, decode_varints, encode_postings
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

# Word runs: Python's ``\w`` is the Unicode alphanumerics plus underscore
# — the letters, numerics, and joiner an identifier is made of.
_WORD_RUN: Final = re.compile(r"\w+")

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
    """Folded terms in order, duplicates kept — from the active engine."""
    ext = extension()
    if ext is not None:
        return ext.tokenize(content)
    return pure_tokenize(content)


def pure_tokenize(content: str) -> list[str]:
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
    """The one builder contract both engines implement.

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
    """A fresh lexical builder from the active engine."""
    ext = extension()
    if ext is not None:
        return ext.LexicalBuilder()
    return PureLexicalBuilder()


class PureLexicalBuilder:
    """The reference builder: one streaming pass, blocks held until ``finish``.

    Per document: tokenize, count, append ``(delta, tf, dl)`` to each
    term's open block, seal a block at :data:`BLOCK_SIZE`. A block's true
    maximum weight needs the final ``idf`` and ``avg_dl``, so the sealed
    blocks stay resident (compressed) until :meth:`finish` computes every
    summary. Residency is dominated by the vocabulary, not the postings:
    each distinct term costs a few hundred bytes of per-term structure
    against a few bytes of blob (the Rust engine measured ~660 B per term
    on a 487 k-term corpus). An arena layout for the term streams, and a
    sharded build past one core, are the directions — never a declared
    corpus limit.
    """

    def __init__(self) -> None:
        self._terms: dict[str, _TermList] = {}
        self._n_docs = 0
        self._total_dl = 0
        self._last_doc = 0
        self._drained: list[tuple[str, _TermList, SummaryRow]] | None = None
        self._stats = CorpusStats(0, 0.0)
        self._df_cursor = 0
        self._block_cursor = 0
        self._block_offset = 0

    def add_docs(self, docs: list[tuple[int, str]]) -> list[int]:
        if self._drained is not None:
            raise ValueError("statistics are fixed; create a fresh builder")
        lengths: list[int] = []
        for doc_id, content in docs:
            if doc_id <= self._last_doc:
                message = f"doc ids must be strictly increasing and positive; got {doc_id} after {self._last_doc}"
                raise ValueError(message)
            tokens = pure_tokenize(content)
            counts: dict[str, int] = {}
            for term in tokens:
                counts[term] = counts.get(term, 0) + 1
            dl = len(tokens)
            for term, tf in counts.items():
                lst = self._terms.get(term)
                if lst is None:
                    lst = self._terms[term] = _TermList()
                lst.push(doc_id, tf, dl)
            self._last_doc = doc_id
            self._n_docs += 1
            self._total_dl += dl
            lengths.append(dl)
        return lengths

    def finish(self) -> tuple[int, float]:
        if self._drained is None:
            avg_dl = self._total_dl / self._n_docs if self._n_docs else 0.0
            self._stats = CorpusStats(self._n_docs, avg_dl)
            self._drained = [
                (term, lst, lst.summary(term, self._n_docs, avg_dl)) for term, lst in sorted(self._terms.items())
            ]
            self._terms = {}
        return self._stats

    def next_df_batch(self, row_cap: int) -> list[tuple[str, int, float, float, bytes]] | None:
        self.finish()
        assert self._drained is not None
        if self._df_cursor >= len(self._drained):
            return None
        end = min(self._df_cursor + max(row_cap, 1), len(self._drained))
        batch = [tuple(summary) for _term, _lst, summary in self._drained[self._df_cursor : end]]
        self._df_cursor = end
        return batch

    def next_batch(self, row_cap: int) -> list[tuple[str, int, int, bytes, bytes, bytes]] | None:
        self.finish()
        assert self._drained is not None
        if self._block_cursor >= len(self._drained):
            return None
        row_cap = max(row_cap, 1)
        batch: list[tuple[str, int, int, bytes, bytes, bytes]] = []
        while self._block_cursor < len(self._drained) and len(batch) < row_cap:
            term, lst, _summary = self._drained[self._block_cursor]
            blocks = lst.blocks()
            while self._block_offset < len(blocks) and len(batch) < row_cap:
                batch.append(lst.row(term, self._block_offset, blocks[self._block_offset]))
                self._block_offset += 1
            if self._block_offset >= len(blocks):
                lst.release()
                self._block_cursor += 1
                self._block_offset = 0
        return batch


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
    ``score DESC, chunk_id ASC`` — from the active engine.

    ``idfs`` is indexed by each block's ``term``; ``candidates``, when
    given, is a sorted id array the ranking is restricted to. Both
    engines accumulate in the same order (terms by descending bound,
    then block order, then posting order), so their sums are identical.
    """
    ext = extension()
    if ext is not None:
        raw = None if candidates is None else np.ascontiguousarray(candidates, dtype=np.int64).tobytes()
        return ext.lexical_score(list(blocks), list(idfs), avg_dl, k, raw)
    return pure_score_blocks(blocks, idfs, avg_dl, k, candidates=candidates)


def pure_score_blocks(
    blocks: Sequence[ScoreBlock],
    idfs: Sequence[float],
    avg_dl: float,
    k: int,
    *,
    candidates: NDArray[np.int64] | None = None,
) -> list[tuple[int, float]]:
    """The reference scorer: full evaluation in one numpy pipeline.

    Every block is decoded and every posting weighted — no block-max
    skipping (the Python loop would lose to the batched decode); the
    Rust engine skips, and lands on the same top-k because a skipped
    block, by construction, could not have changed it.
    """
    if not blocks or k <= 0:
        return []
    bound = [max(b.bound for b in blocks if b.term == term) for term in range(len(idfs))]
    ordered = sorted(blocks, key=lambda b: (-bound[b.term], b.term))
    ids = np.concatenate([decode_postings(b.doc_ids) for b in ordered])
    tfs = decode_varints(b"".join(b.tfs for b in ordered))
    dls = decode_varints(b"".join(b.dls for b in ordered))
    counts = np.array([len(decode_postings(b.doc_ids)) for b in ordered], dtype=np.int64)
    term_idf = np.repeat(np.array([idfs[b.term] for b in ordered], dtype=np.float64), counts)
    weights = term_idf * tfs * (BM25_K1 + 1.0) / (tfs + BM25_K1 * (1.0 - BM25_B + BM25_B * dls / avg_dl))
    if candidates is not None:
        keep = np.isin(ids, candidates)
        ids, weights = ids[keep], weights[keep]
    if ids.size == 0:
        return []
    uniq, inverse = np.unique(ids, return_inverse=True)
    scores = np.bincount(inverse, weights=weights, minlength=uniq.size)
    order = np.lexsort((uniq, -scores))[:k]
    return [(int(uniq[i]), float(scores[i])) for i in order]


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


def _append_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)


# One block's (count, ids, tfs, dls) byte slices inside a term's streams.
_BlockSlices = tuple[int, slice, slice, slice]


class _TermList:
    """One term's postings as three byte streams, blocks back to back.

    Deltas restart at each block so a block decodes alone; ``sealed``
    holds each full block's ``(count, ids_end, tfs_end, dls_end)``.
    """

    __slots__ = ("df", "dls", "ids", "last_id", "open_count", "sealed", "tfs")

    def __init__(self) -> None:
        self.df = 0
        self.ids = bytearray()
        self.tfs = bytearray()
        self.dls = bytearray()
        self.sealed: list[tuple[int, int, int, int]] = []
        self.open_count = 0
        self.last_id = 0

    def push(self, doc_id: int, tf: int, dl: int) -> None:
        _append_varint(self.ids, doc_id - self.last_id)
        _append_varint(self.tfs, tf)
        _append_varint(self.dls, dl)
        self.last_id = doc_id
        self.open_count += 1
        self.df += 1
        if self.open_count == BLOCK_SIZE:
            self.sealed.append((self.open_count, len(self.ids), len(self.tfs), len(self.dls)))
            self.open_count = 0
            self.last_id = 0

    def blocks(self) -> list[_BlockSlices]:
        """Every block's ``(count, ids, tfs, dls)`` byte slices, the open block last."""
        out: list[_BlockSlices] = []
        a = b = c = 0
        for count, ia, ib, ic in self.sealed:
            out.append((count, slice(a, ia), slice(b, ib), slice(c, ic)))
            a, b, c = ia, ib, ic
        if self.open_count:
            out.append((self.open_count, slice(a, len(self.ids)), slice(b, len(self.tfs)), slice(c, len(self.dls))))
        return out

    def summary(self, term: str, n_docs: int, avg_dl: float) -> SummaryRow:
        """The term's row: idf, its maximum over every block, the summary blob."""
        term_idf = idf(self.df, n_docs)
        firsts: list[int] = []
        maxes: list[float] = []
        for _count, ids, tfs, dls in self.blocks():
            firsts.append(int(decode_varints(bytes(self.ids[ids]))[0]))
            block_tfs = decode_varints(bytes(self.tfs[tfs]))
            block_dls = decode_varints(bytes(self.dls[dls]))
            pairs = zip(block_tfs, block_dls, strict=True)
            maxes.append(max(term_weight(int(tf), int(dl), avg_dl, term_idf) for tf, dl in pairs))
        return SummaryRow(term, self.df, term_idf, max(maxes, default=0.0), encode_summary(firsts, maxes))

    def row(self, term: str, block_no: int, block: _BlockSlices) -> tuple[str, int, int, bytes, bytes, bytes]:
        count, ids, tfs, dls = block
        prefix = bytearray()
        _append_varint(prefix, count)
        return (term, block_no, count, bytes(prefix + self.ids[ids]), bytes(self.tfs[tfs]), bytes(self.dls[dls]))

    def release(self) -> None:
        self.ids = self.tfs = self.dls = bytearray()
        self.sealed = []


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
    "PureLexicalBuilder",
    "ScoreBlock",
    "SummaryRow",
    "competing_blocks",
    "decode_summary",
    "encode_postings",
    "encode_summary",
    "idf",
    "lexical_builder",
    "options_fingerprint",
    "pure_score_blocks",
    "pure_tokenize",
    "score_blocks",
    "term_weight",
    "tokenize",
]
