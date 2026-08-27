"""The lexical engine's oracles: tokenizer, builder, BM25 scorer.

The tokenizer follows the running interpreter's ``\\w``, ``isupper``,
``islower`` and ``isdigit`` — the rules the engine's generated tables
were rendered from — so it agrees with the engine exactly on the
interpreter that generated those tables and may drift on a few code
points elsewhere. The builder is one streaming pass over plain byte
streams; the scorer evaluates every posting of every block with no
block-max skipping, the slow shape that cannot be wrong.
"""

from __future__ import annotations

import re
import struct
from bisect import bisect_right
from typing import TYPE_CHECKING, Final

from tests.support.oracles.postings import decode_postings, decode_varints
from vfs.models.code_grams import fold_content
from vfs.models.lexical import (
    BLOCK_SIZE,
    MAX_TERM_BYTES,
    MIN_TERM_CHARS,
    ScoreBlock,
    SummaryRow,
    encode_summary,
    idf,
    term_weight,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# Word runs: the interpreter's ``\w`` — Unicode alphanumerics plus underscore.
_WORD_RUN: Final = re.compile(r"\w+")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def pure_tokenize(content: str) -> list[str]:
    """Folded terms in order, duplicates kept.

    Each word run is emitted whole; a run with more than one part (split
    on ``_`` and on case change) also emits each part. Digit-led pieces
    stay whole (``0x1f``), one-character terms are dropped, and a term
    over ``MAX_TERM_BYTES`` after folding is dropped rather than
    truncated. Nothing here depends on hash order.
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


def _emit(terms: list[str], raw: str) -> None:
    term = fold_content(raw)
    if len(term) >= MIN_TERM_CHARS and len(term.encode()) <= MAX_TERM_BYTES:
        terms.append(term)


def _identifier_parts(run: str) -> list[str]:
    """Split on underscores, then on case changes; digit-led pieces stay whole."""
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
    previous = piece[index - 1]
    if previous.islower() or previous.isdigit():
        return True
    return previous.isupper() and index + 1 < len(piece) and piece[index + 1].islower()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _append_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)


# One block's (count, ids, tfs, dls) byte slices inside a term's streams.
_BlockSlices = tuple[int, slice, slice, slice]


class _TermList:
    """One term's postings as three byte streams, blocks back to back; deltas restart per block."""

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
        out: list[_BlockSlices] = []
        a = b = c = 0
        for count, ia, ib, ic in self.sealed:
            out.append((count, slice(a, ia), slice(b, ib), slice(c, ic)))
            a, b, c = ia, ib, ic
        if self.open_count:
            out.append((self.open_count, slice(a, len(self.ids)), slice(b, len(self.tfs)), slice(c, len(self.dls))))
        return out

    def summary(self, term: str, n_docs: int, avg_dl: float) -> SummaryRow:
        term_idf = idf(self.df, n_docs)
        firsts: list[int] = []
        maxes: list[float] = []
        for _count, ids, tfs, dls in self.blocks():
            firsts.append(decode_varints(bytes(self.ids[ids]))[0])
            pairs = zip(decode_varints(bytes(self.tfs[tfs])), decode_varints(bytes(self.dls[dls])), strict=True)
            maxes.append(max(term_weight(tf, dl, avg_dl, term_idf) for tf, dl in pairs))
        return SummaryRow(term, self.df, term_idf, max(maxes, default=0.0), encode_summary(firsts, maxes))

    def row(self, term: str, block_no: int, block: _BlockSlices) -> tuple[str, int, int, bytes, bytes, bytes]:
        count, ids, tfs, dls = block
        prefix = bytearray()
        _append_varint(prefix, count)
        return (term, block_no, count, bytes(prefix + self.ids[ids]), bytes(self.tfs[tfs]), bytes(self.dls[dls]))

    def release(self) -> None:
        self.ids = self.tfs = self.dls = bytearray()
        self.sealed = []


class PureLexicalBuilder:
    """One streaming pass; sealed blocks stay resident until ``finish`` fixes idf and avg_dl."""

    def __init__(self) -> None:
        self._terms: dict[str, _TermList] = {}
        self._n_docs = 0
        self._total_dl = 0
        self._last_doc = 0
        self._drained: list[tuple[str, _TermList, SummaryRow]] | None = None
        self._stats = (0, 0.0)
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
            self._stats = (self._n_docs, avg_dl)
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
# Summary decode and block selection
# ---------------------------------------------------------------------------


def decode_summary(blob: bytes) -> tuple[list[int], list[float]]:
    """Per block, the varint delta of its first id and its maximum as ``<d``."""
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
        maxes.append(struct.unpack_from("<d", blob, position)[0])
        position += 8
    return firsts, maxes


def competing_blocks(
    first_ids: Sequence[int],
    max_weights: Sequence[float],
    candidates: Sequence[int],
    scores: Sequence[float],
    theta: float,
    rest: float = 0.0,
) -> list[int]:
    """A block competes when its max (+ rest) clears theta alone, or lifted by its best candidate."""
    best = [float("-inf")] * len(first_ids)
    for candidate, score in zip(candidates, scores, strict=True):
        index = bisect_right(first_ids, candidate) - 1
        if index >= 0:
            best[index] = max(best[index], score)
    return [
        block
        for block, (maximum, lift) in enumerate(zip(max_weights, best, strict=True))
        if maximum + rest >= theta or lift + maximum + rest >= theta
    ]


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def pure_score_blocks(
    blocks: Sequence[ScoreBlock],
    idfs: Sequence[float],
    avg_dl: float,
    k: int,
    *,
    candidates: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """BM25 top-``k`` as ``(chunk_id, score)``, ``score DESC, chunk_id ASC``.

    Every posting of every block is weighted — no block-max skipping —
    accumulating in the engine's order (terms by descending bound, then
    block order, then posting order) so the float sums are identical.
    ``candidates``, when given, restricts the ranking to those ids.
    """
    if not blocks or k <= 0:
        return []
    bound = [max(b.bound for b in blocks if b.term == term) for term in range(len(idfs))]
    ordered = sorted(blocks, key=lambda b: (-bound[b.term], b.term))
    allowed = None if candidates is None else set(candidates)
    scores: dict[int, float] = {}
    for block in ordered:
        term_idf = idfs[block.term]
        ids = decode_postings(block.doc_ids)
        pairs = zip(ids, decode_varints(block.tfs), decode_varints(block.dls), strict=True)
        for doc_id, tf, dl in pairs:
            if allowed is not None and doc_id not in allowed:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + term_weight(tf, dl, avg_dl, term_idf)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:k]
