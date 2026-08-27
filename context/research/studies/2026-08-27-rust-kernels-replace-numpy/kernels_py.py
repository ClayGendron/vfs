"""Stdlib-only twins of every numpy site (the pure-Python fallback arm).

Nothing here imports numpy. Arrays are plain lists (or ``array('q')`` /
``array('d')`` where a packed form is wanted). Each twin keeps the live
function's contract — the posting codec's corruption checks, the scorer's
accumulation order (so sums are bit-identical to numpy and Rust), and
``competing_blocks``' float-op order.
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from math import inf
from struct import Struct

MAX_DOC_ID = 2**63 - 1
_MAX_VARINT_BYTES = 9
_F64 = Struct("<d")
BM25_K1 = 1.2
BM25_B = 0.75


class PostingCorruptionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Site 1: varint / posting decode
# ---------------------------------------------------------------------------


def decode_varints(blob: bytes) -> list[int]:
    out: list[int] = []
    value = 0
    shift = 0
    width = 0
    for byte in blob:
        value |= (byte & 0x7F) << shift
        width += 1
        if byte & 0x80:
            shift += 7
        else:
            if width > _MAX_VARINT_BYTES:
                raise PostingCorruptionError("over-wide varint")
            if width > 1 and byte == 0:
                raise PostingCorruptionError("non-canonical varint spelling")
            out.append(value)
            value = 0
            shift = 0
            width = 0
    if width:
        raise PostingCorruptionError("truncated varint at end of blob")
    return out


def decode_postings(blob: bytes) -> list[int]:
    """Doc ids of a count-prefixed delta blob, with every structural check."""
    values = decode_varints(blob)
    if not values:
        raise PostingCorruptionError("empty posting blob")
    count = values[0]
    if count != len(values) - 1:
        raise PostingCorruptionError("count header mismatch")
    ids: list[int] = []
    append = ids.append
    doc = 0
    for delta in values[1:]:
        if delta < 1:
            raise PostingCorruptionError("non-positive delta")
        doc += delta
        append(doc)
    if ids and ids[-1] > MAX_DOC_ID:
        raise PostingCorruptionError("doc ids not monotone (int64 wrap)")
    return ids


def decode_postings_fused(blob: bytes) -> list[int]:
    """One-pass decode (no intermediate varint list) — the faster stdlib spelling."""
    ids: list[int] = []
    append = ids.append
    value = 0
    shift = 0
    width = 0
    doc = 0
    count = -1
    for byte in blob:
        value |= (byte & 0x7F) << shift
        width += 1
        if byte & 0x80:
            shift += 7
            continue
        if width > _MAX_VARINT_BYTES:
            raise PostingCorruptionError("over-wide varint")
        if width > 1 and byte == 0:
            raise PostingCorruptionError("non-canonical varint spelling")
        if count < 0:
            count = value
        else:
            if value < 1:
                raise PostingCorruptionError("non-positive delta")
            doc += value
            append(doc)
        value = 0
        shift = 0
        width = 0
    if width:
        raise PostingCorruptionError("truncated varint at end of blob")
    if count < 0:
        raise PostingCorruptionError("empty posting blob")
    if count != len(ids):
        raise PostingCorruptionError("count header mismatch")
    if ids and ids[-1] > MAX_DOC_ID:
        raise PostingCorruptionError("doc ids not monotone (int64 wrap)")
    return ids


# ---------------------------------------------------------------------------
# Site 2: the grep ladder's set algebra
# ---------------------------------------------------------------------------


def intersect_rarest(blobs: list[bytes]) -> list[int]:
    """Fused decode+intersect: rarest blob decoded, later blobs streamed.

    Survivors of each later blob are appended in that blob's (ascending)
    order, so the result is sorted without a final sort.
    """
    if not blobs:
        return []
    current: list[int] = decode_postings_fused(blobs[0])
    for blob in blobs[1:]:
        if not current:
            break
        members = set(current)
        kept: list[int] = []
        append = kept.append
        value = 0
        shift = 0
        width = 0
        doc = 0
        count = -1
        seen = 0
        for byte in blob:
            value |= (byte & 0x7F) << shift
            width += 1
            if byte & 0x80:
                shift += 7
                continue
            if width > _MAX_VARINT_BYTES:
                raise PostingCorruptionError("over-wide varint")
            if width > 1 and byte == 0:
                raise PostingCorruptionError("non-canonical varint spelling")
            if count < 0:
                count = value
            else:
                if value < 1:
                    raise PostingCorruptionError("non-positive delta")
                doc += value
                seen += 1
                if doc in members:
                    append(doc)
            value = 0
            shift = 0
            width = 0
        if width:
            raise PostingCorruptionError("truncated varint at end of blob")
        if count != seen:
            raise PostingCorruptionError("count header mismatch")
        current = kept
    return current


def union_sorted(parts: list[list[int]]) -> list[int]:
    if len(parts) == 1:
        return parts[0]
    return sorted(set().union(*parts))


def intersect_sorted(a: list[int], b: list[int]) -> list[int]:
    """Sorted intersection; hashes the shorter side."""
    if len(b) < len(a):
        a, b = b, a
    members = set(a)
    return [x for x in b if x in members]


# ---------------------------------------------------------------------------
# Site 3: the term summary codec
# ---------------------------------------------------------------------------


def decode_summary(blob: bytes) -> tuple[list[int], list[float]]:
    firsts: list[int] = []
    maxes: list[float] = []
    unpack = _F64.unpack_from
    position = 0
    first = 0
    n = len(blob)
    while position < n:
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
        maxes.append(unpack(blob, position)[0])
        position += 8
    return firsts, maxes


# ---------------------------------------------------------------------------
# Site 4: block selection between rounds
# ---------------------------------------------------------------------------


def competing_blocks(
    first_ids: list[int], max_weights: list[float], candidates: list[int], scores: list[float], theta: float, rest: float = 0.0
) -> list[int]:
    n = len(first_ids)
    best = [-inf] * n
    if candidates and n:
        for c, s in zip(candidates, scores):
            i = bisect_right(first_ids, c) - 1
            if i >= 0 and s > best[i]:
                best[i] = s
    out: list[int] = []
    for i in range(n):
        m = max_weights[i] + rest
        if m >= theta or best[i] + m >= theta:
            out.append(i)
    return out


# ---------------------------------------------------------------------------
# Site 5: the BM25 scorer
# ---------------------------------------------------------------------------


def _ordered(blocks, idfs):
    bound = [max((b.bound for b in blocks if b.term == term), default=-inf) for term in range(len(idfs))]
    return sorted(blocks, key=lambda b: (-bound[b.term], b.term)), bound


def _weight(tf: int, dl: int, avg_dl: float, term_idf: float) -> float:
    norm = BM25_K1 * (1.0 - BM25_B + BM25_B * dl / avg_dl)
    return term_idf * tf * (BM25_K1 + 1.0) / (tf + norm)


def _topk(partial: dict[int, float], k: int) -> list[tuple[int, float]]:
    return sorted(partial.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


def score_blocks_full(blocks, idfs, avg_dl: float, k: int, candidates: list[int] | None = None) -> list[tuple[int, float]]:
    """Every block decoded and weighted — the numpy reference's shape in loops."""
    if not blocks or k <= 0:
        return []
    ordered, _ = _ordered(blocks, idfs)
    admit = None if candidates is None else set(candidates)
    partial: dict[int, float] = {}
    for block in ordered:
        term_idf = idfs[block.term]
        ids = decode_postings_fused(block.doc_ids)
        tfs = decode_varints(block.tfs)
        dls = decode_varints(block.dls)
        for doc, tf, dl in zip(ids, tfs, dls):
            if admit is not None and doc not in admit:
                continue
            partial[doc] = partial.get(doc, 0.0) + _weight(tf, dl, avg_dl, term_idf)
    return _topk(partial, k)


def score_blocks_skip(blocks, idfs, avg_dl: float, k: int, candidates: list[int] | None = None) -> list[tuple[int, float]]:
    """The Rust engine's block-max skip, in Python: same accumulation order, same sums."""
    if not blocks or k <= 0:
        return []
    ordered, bound = _ordered(blocks, idfs)
    order = [t for t in range(len(idfs)) if bound[t] > -inf]
    order.sort(key=lambda t: (-bound[t], t))
    rest = [0.0] * (len(order) + 1)
    for i in range(len(order) - 1, -1, -1):
        rest[i] = rest[i + 1] + bound[order[i]]
    admit = None if candidates is None else set(candidates)
    partial: dict[int, float] = {}
    theta = 0.0
    for position, term in enumerate(order):
        remaining = rest[position + 1]
        term_idf = idfs[term]
        for block in ordered:
            if block.term != term:
                continue
            ids = decode_postings_fused(block.doc_ids)
            if theta > 0.0 and block.bound + remaining < theta:
                lift = block.bound + remaining
                get = partial.get
                if not any((p := get(doc)) is not None and p + lift >= theta for doc in ids):
                    continue
            tfs = decode_varints(block.tfs)
            dls = decode_varints(block.dls)
            for doc, tf, dl in zip(ids, tfs, dls):
                if admit is not None and doc not in admit:
                    continue
                partial[doc] = partial.get(doc, 0.0) + _weight(tf, dl, avg_dl, term_idf)
        if k > 0 and len(partial) >= k:
            theta = sorted(partial.values(), reverse=True)[k - 1]
    return _topk(partial, k)


def to_q(values: list[int]) -> bytes:
    return array("q", values).tobytes()


def to_d(values: list[float]) -> bytes:
    return array("d", values).tobytes()


def from_q(raw: bytes) -> list[int]:
    a = array("q")
    a.frombytes(raw)
    return a.tolist()


def from_d(raw: bytes) -> list[float]:
    a = array("d")
    a.frombytes(raw)
    return a.tolist()
