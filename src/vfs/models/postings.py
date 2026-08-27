"""Posting-list codec: delta+varint over strictly increasing doc ids.

One gram's doc list is one blob: a varint count, then LEB128 varints of
the strictly positive deltas between consecutive ids. Sorted input makes
every delta small (a dense run costs one byte per doc), and the count
header makes truncation and trailing garbage detectable.

This module owns the encoder and the refusal type. The decoder lives in
the engine (``crates/vfs-core/src/postings.rs``), fused with the grep
ladder's set algebra so doc ids never materialize on the host until
capped; the readable decoder is a test oracle. The codec refuses rather
than guesses: `encode_postings` raises `ValueError` on caller bugs
(unsorted or out-of-range ids), and the engine's decode raises on every
malformed blob class — truncated or over-wide varints, non-canonical
spellings, count mismatches, non-positive deltas, and int64 wraps —
which grep surfaces as `PostingCorruptionError`, so blob corruption is
loud, never silently-wrong search results.

This module also owns the posting-set **builder** surface: the
`PostingsBuilder` contract the engine implements and `postings_builder()`,
which serves it — per the seam's ownership rule (the format's owner
holds its dispatch; `vfs.native` only resolves the engine). The
readable reference builder is a test oracle (`tests/support/oracles`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

from vfs.native import extension

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_DOC_ID: Final = 2**63 - 1
"""Doc ids live in the signed-BIGINT range the chunk PK allocates from."""


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------


class PostingCorruptionError(Exception):
    """A posting blob failed structural validation in the engine's decode."""


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


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


class PostingsBuilder(Protocol):
    """The builder contract the engine implements (and the oracle mirrors).

    Docs are fed in strictly increasing doc-id order as pre-folded bytes;
    draining yields gram-ordered batches of ``(gram_key, blob, doc_count)``
    rows sliced by accumulated blob bytes (each batch carries at least one
    row). Feeding after the first drain raises ``ValueError``.
    """

    def add_docs(self, docs: list[tuple[int, bytes]]) -> None: ...

    def next_batch(self, byte_cap: int) -> list[tuple[int, bytes, int]] | None: ...


def postings_builder() -> PostingsBuilder:
    """A fresh posting-set builder from the engine."""
    return extension().PostingsBuilder()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _append_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
