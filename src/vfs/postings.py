"""Posting-list codec for the code-gram index.

A posting list is the sorted ``doc_id`` set of a single gram. v1 packs it with
``delta+gamma``: gaps between consecutive ids, Elias-γ coded. The byte format is
ported verbatim from Google ``codesearch`` (``index/delta.go`` writer +
``index/read.go`` reader) so the two never produce incompatible blobs:

- ids are encoded as gaps from a running cursor that starts at ``-1`` (so the
  first gap is ``first_id + 1``);
- the list ends with a trailing **zero** gap as a terminator;
- Elias-γ cannot encode 0, so every value is remapped before coding —
  ``0 → 16`` and any ``v ≥ 16 → v + 1`` (``deltaZeroEnc = 16``,
  ``index/delta.go:31``; the reader inverts it);
- γ codes are written LSB-first within each byte and the partial trailing byte
  is flushed at end-of-blob.

Decode is **count-bounded**: the caller supplies ``doc_count`` (the posting
row's stored count), the decoder reads exactly that many gaps and then asserts
the trailing zero terminator — detecting truncation or corruption.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from collections.abc import Set as AbstractSet

# index/delta.go:31 — Elias-γ cannot encode 0, so 0 maps to this sentinel and
# every value >= it shifts up by one. The reader inverts the remap.
_DELTA_ZERO_ENC = 16


class PostingCorruptionError(ValueError):
    """Raised when a posting blob fails to decode (truncated, bad terminator)."""


class GammaWriter:
    """LSB-first Elias-γ bit writer (port of ``deltaWriter`` in delta.go)."""

    __slots__ = ("_out", "_b", "_nb")

    def __init__(self) -> None:
        self._out = bytearray()
        self._b = 0  # bit accumulator (unbounded Python int; flushed in bytes)
        self._nb = 0  # number of pending bits in the accumulator

    def _flush_bits(self) -> None:
        while self._nb >= 8:
            self._out.append(self._b & 0xFF)
            self._b >>= 8
            self._nb -= 8

    def _write_bits(self, x: int) -> None:
        # γ-code a strictly-positive integer: ``lg`` leading zero bits, a 1
        # marker bit, then the low ``lg`` mantissa bits. Python ints are
        # unbounded, so unlike delta.go we never split a wide mantissa — the
        # emitted bit sequence is identical because _flush_bits only drains
        # whole low bytes.
        if x <= 0:
            msg = f"gamma write of non-positive value {x}"
            raise ValueError(msg)
        lg = x.bit_length() - 1
        mantissa = x & ((1 << lg) - 1)
        self._nb += lg  # the lg leading zero bits
        if self._nb >= 8:
            self._flush_bits()
        self._b |= 1 << self._nb  # the marker bit
        self._nb += 1
        self._b |= mantissa << self._nb
        self._nb += lg
        if self._nb >= 8:
            self._flush_bits()

    def write_value(self, x: int) -> None:
        """Write a gap value, applying the zero-remap (0 and the terminator)."""
        if x == 0:
            x = _DELTA_ZERO_ENC
        elif x >= _DELTA_ZERO_ENC:
            x += 1
        self._write_bits(x)

    def finish(self) -> bytes:
        self._flush_bits()
        if self._nb > 0:
            self._out.append(self._b & 0xFF)
            self._b = 0
            self._nb = 0
        return bytes(self._out)


class GammaReader:
    """LSB-first Elias-γ bit reader (port of ``deltaReader`` in delta.go)."""

    __slots__ = ("_d", "_pos", "_b", "_nb")

    def __init__(self, data: bytes) -> None:
        self._d = data
        self._pos = 0
        self._b = 0  # current bit window
        self._nb = 0  # valid bits in the window

    def _next_byte(self) -> int:
        if self._pos >= len(self._d):
            raise PostingCorruptionError("posting blob truncated")
        byte = self._d[self._pos]
        self._pos += 1
        return byte

    def _read_bits(self) -> int:
        lg = 0
        # Count leading zero bits, refilling a byte at a time, until the window
        # holds a set bit.
        while self._b == 0:
            lg += self._nb
            self._b = self._next_byte()
            self._nb = 8
        nb = _trailing_zeros(self._b)
        lg += nb
        self._b >>= nb + 1  # consume the zeros and the marker bit
        self._nb -= nb + 1
        x = 1 << lg
        shift = 0
        # Read lg mantissa bits, consuming the window and refilling as needed.
        while self._nb < lg:
            x |= self._b << shift
            shift += self._nb
            lg -= self._nb
            self._b = self._next_byte()
            self._nb = 8
        x |= (self._b & ((1 << lg) - 1)) << shift
        self._b >>= lg
        self._nb -= lg
        return x

    def read_value(self) -> int:
        """Read a gap value, inverting the zero-remap."""
        i = self._read_bits()
        if i == _DELTA_ZERO_ENC:
            return 0
        if i > _DELTA_ZERO_ENC:
            return i - 1
        return i


def _trailing_zeros(value: int) -> int:
    # value is always > 0 here (the window holds a set bit).
    return (value & -value).bit_length() - 1


def encode_postings(doc_ids: Iterable[int]) -> bytes:
    """Encode a sorted, strictly-increasing ``doc_id`` set as a delta+γ blob.

    ``doc_ids`` MUST be sorted ascending with no duplicates; each gap is then
    ``>= 1`` as γ-coding requires. Raises ``ValueError`` otherwise.
    """
    writer = GammaWriter()
    prev = -1
    for doc_id in doc_ids:
        gap = doc_id - prev
        if gap <= 0:
            msg = f"doc_ids must be sorted ascending and distinct (got gap {gap})"
            raise ValueError(msg)
        writer.write_value(gap)
        prev = doc_id
    writer.write_value(0)  # trailing zero terminator
    return writer.finish()


def decode_postings(blob: bytes, doc_count: int) -> list[int]:
    """Decode a delta+γ blob into its ``doc_id`` list.

    Reads exactly ``doc_count`` gaps, then asserts the trailing zero
    terminator. Raises :class:`PostingCorruptionError` on truncation or a
    missing/!= 0 terminator.
    """
    reader = GammaReader(blob)
    doc_id = -1
    ids: list[int] = []
    for _ in range(doc_count):
        gap = reader.read_value()
        if gap <= 0:
            raise PostingCorruptionError("non-positive gap in posting list")
        doc_id += gap
        ids.append(doc_id)
    if reader.read_value() != 0:
        raise PostingCorruptionError("posting list missing zero terminator")
    return ids


def merge_postings(
    base_ids: Sequence[int], adds: Iterable[int], dels: AbstractSet[int] = frozenset()
) -> list[int]:
    """Merge a sorted posting list with staged adds, dropping deletes.

    Computes ``(base ∪ adds) − dels`` as an ascending, distinct list via a
    linear two-pointer merge that exploits the existing order — O(B + A·log A)
    rather than re-sorting the union. ``base_ids`` MUST be ascending and
    distinct (the decode output); ``adds`` may be any iterable. ``adds`` and
    ``dels`` are disjoint by construction (a ``doc_id`` maps to one entry, whose
    folded action is either add or delete), so an add never collides with a
    delete. The result feeds straight into :func:`encode_postings`.
    """
    new = sorted(adds)
    out: list[int] = []
    i = j = 0
    n_base, n_new = len(base_ids), len(new)
    while i < n_base and j < n_new:
        b, a = base_ids[i], new[j]
        if b < a:
            if b not in dels:
                out.append(b)
            i += 1
        elif a < b:
            out.append(a)  # a new add: absent from base, never in dels
            j += 1
        else:  # b == a: re-add of a present doc — keep once
            out.append(b)
            i += 1
            j += 1
    while i < n_base:
        b = base_ids[i]
        if b not in dels:
            out.append(b)
        i += 1
    out.extend(new[j:])
    return out
