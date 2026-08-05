"""Posting-list codec: delta+varint over strictly increasing doc ids.

One gram's doc list is one blob: a varint count, then LEB128 varints of
the strictly positive deltas between consecutive ids. Sorted input makes
every delta small (a dense run costs one byte per doc), and the count
header makes truncation and trailing garbage detectable. Decode is
numpy-vectorized — posting reads are the hot path of every indexed grep.

The codec refuses rather than guesses: `encode_postings` raises
`ValueError` on caller bugs (unsorted or out-of-range ids), and
`decode_postings` raises `PostingCorruptionError` on every malformed
blob class — truncated or over-wide varints, non-canonical spellings,
count mismatches, non-positive deltas, and int64 wraps — so blob
corruption is loud, never silently-wrong search results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterable

    from numpy.typing import NDArray

MAX_DOC_ID: Final = 2**63 - 1
"""Doc ids live in the signed-BIGINT range the chunk PK allocates from."""

# ceil(63 / 7): the widest canonical varint a legal value can need.
_MAX_VARINT_BYTES: Final = 9


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------


class PostingCorruptionError(Exception):
    """A posting blob failed structural validation during decode."""


def encode_postings(doc_ids: Iterable[int]) -> bytes:
    """Encode strictly increasing doc ids as a count-prefixed delta+varint blob."""
    ids = list(doc_ids)
    out = bytearray()
    _append_varint(out, len(ids))
    prev = 0
    for doc_id in ids:
        if doc_id > MAX_DOC_ID:
            raise ValueError(f"doc id {doc_id} outside the signed-BIGINT range")
        if doc_id <= prev:
            raise ValueError(f"doc ids must be strictly increasing and positive; got {doc_id} after {prev}")
        _append_varint(out, doc_id - prev)
        prev = doc_id
    return bytes(out)


def decode_postings(blob: bytes) -> NDArray[np.int64]:
    """Decode a posting blob to the int64 doc-id array, refusing corruption."""
    data = np.frombuffer(blob, dtype=np.uint8)
    if data.size == 0:
        raise PostingCorruptionError("empty posting blob (a valid empty list is one zero byte)")
    continues = (data & 0x80) != 0
    if bool(continues[-1]):
        raise PostingCorruptionError("truncated varint at end of blob")
    ends = np.flatnonzero(~continues)
    starts = np.empty(ends.size, dtype=np.int64)
    starts[0] = 0
    starts[1:] = ends[:-1] + 1
    lengths = ends - starts + 1
    if int(lengths.max()) > _MAX_VARINT_BYTES:
        raise PostingCorruptionError("over-wide varint")
    if bool(np.any((lengths > 1) & (data[ends] == 0))):
        raise PostingCorruptionError("non-canonical varint spelling")
    groups = np.repeat(np.arange(ends.size), lengths)
    shifts = 7 * (np.arange(data.size, dtype=np.int64) - starts[groups])
    payloads = (data & 0x7F).astype(np.int64) << shifts
    values = np.zeros(ends.size, dtype=np.int64)
    np.add.at(values, groups, payloads)
    count, deltas = int(values[0]), values[1:]
    if count != deltas.size:
        raise PostingCorruptionError(f"count header says {count}, blob holds {deltas.size}")
    if count == 0:
        return np.empty(0, dtype=np.int64)
    if int(deltas.min()) < 1:
        raise PostingCorruptionError("non-positive delta")
    # Positive deltas keep true ids monotone and positive; an int64 wrap
    # always passes through a non-positive value, so sign is the check.
    ids = np.cumsum(deltas)
    if int(ids.min()) <= 0:
        raise PostingCorruptionError("doc ids not monotone (int64 wrap)")
    return ids


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _append_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
