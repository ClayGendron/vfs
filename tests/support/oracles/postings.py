"""The posting codec's and posting builder's oracles.

Byte-at-a-time LEB128, plain lists, dict accumulation: slow and
obviously right. The builder holds every gram's raw doc-id list (the
engine holds only compressed deltas) and drains through the product's
encoder, so its rows are byte-comparable with the engine's.
"""

from __future__ import annotations

from vfs.models.code_grams import GramKey, iter_byte_trigrams
from vfs.models.postings import encode_postings


def decode_varints(blob: bytes) -> list[int]:
    """Every LEB128 varint in *blob*, in order."""
    values: list[int] = []
    acc = shift = 0
    for byte in blob:
        acc |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            values.append(acc)
            acc = shift = 0
    return values


def decode_postings(blob: bytes) -> list[int]:
    """The inverse of ``encode_postings``: a count varint, then deltas."""
    values = decode_varints(blob)
    count, deltas = values[0], values[1:]
    assert count == len(deltas), "count header disagrees with the delta run"
    ids: list[int] = []
    previous = 0
    for delta in deltas:
        previous += delta
        ids.append(previous)
    return ids


class PurePostingsBuilder:
    """Dict accumulation, then the product codec, gram-ordered batches by byte cap."""

    def __init__(self) -> None:
        self._postings: dict[GramKey, list[int]] = {}
        self._last_doc = 0
        self._rows: list[tuple[int, bytes, int]] | None = None
        self._cursor = 0

    def add_docs(self, docs: list[tuple[int, bytes]]) -> None:
        if self._rows is not None:
            raise ValueError("builder is already draining; create a fresh one")
        for doc_id, data in docs:
            if doc_id <= self._last_doc:
                message = f"doc ids must be strictly increasing and positive; got {doc_id} after {self._last_doc}"
                raise ValueError(message)
            self._last_doc = doc_id
            for gram in set(iter_byte_trigrams(data)):
                self._postings.setdefault(gram, []).append(doc_id)

    def next_batch(self, byte_cap: int) -> list[tuple[int, bytes, int]] | None:
        if self._rows is None:
            self._rows = [(gram, encode_postings(ids), len(ids)) for gram, ids in sorted(self._postings.items())]
            self._postings = {}
        if self._cursor >= len(self._rows):
            return None
        batch: list[tuple[int, bytes, int]] = []
        batch_bytes = 0
        while self._cursor < len(self._rows):
            row = self._rows[self._cursor]
            if batch and batch_bytes + len(row[1]) > byte_cap:
                break
            batch.append(row)
            batch_bytes += len(row[1])
            self._cursor += 1
        return batch
