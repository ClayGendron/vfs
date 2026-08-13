"""Property and corruption tests for the posting-list codec.

The codec is the durability boundary of the gram index: an encode bug
poisons every query against the epoch, and a decode bug that guesses
instead of refusing turns blob corruption into silently-wrong search
results. The battery here pins both directions — exact round-trips
against a pure-Python reference, and loud `PostingCorruptionError`
refusals for every malformed-blob class.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from vfs.models.postings import MAX_DOC_ID, PostingCorruptionError, decode_postings, encode_postings


def reference_decode(blob: bytes) -> list[int]:
    """Byte-at-a-time LEB128 reference: count varint, then delta varints."""
    values: list[int] = []
    acc = shift = 0
    for byte in blob:
        acc |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            values.append(acc)
            acc = shift = 0
    count, deltas = values[0], values[1:]
    assert count == len(deltas)
    ids: list[int] = []
    prev = 0
    for delta in deltas:
        prev += delta
        ids.append(prev)
    return ids


def varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


class TestRoundTrip:
    def test_random_lists_round_trip_and_match_the_reference(self) -> None:
        rng = random.Random(0x5EED)
        for _ in range(200):
            size = rng.randrange(0, 500)
            deltas = [rng.choice((1, 2, 7, rng.randrange(1, 2**40))) for _ in range(size)]
            ids: list[int] = []
            prev = 0
            for delta in deltas:
                prev += delta
                ids.append(prev)
            blob = encode_postings(ids)
            decoded = decode_postings(blob)
            assert decoded.dtype == np.int64
            assert decoded.tolist() == ids
            assert reference_decode(blob) == ids

    def test_empty_list_round_trips_as_the_one_byte_zero_count(self) -> None:
        blob = encode_postings([])
        assert blob == b"\x00"
        assert decode_postings(blob).tolist() == []

    def test_singleton_and_bigint_edge_round_trip(self) -> None:
        for ids in ([1], [MAX_DOC_ID], [1, MAX_DOC_ID], list(range(1, 300))):
            assert decode_postings(encode_postings(ids)).tolist() == ids

    def test_dense_run_encodes_one_byte_per_delta(self) -> None:
        ids = list(range(1, 1001))
        blob = encode_postings(ids)
        # count varint (2 bytes for 1000) + 1000 one-byte deltas.
        assert len(blob) == 2 + 1000


class TestEncodeValidation:
    def test_non_increasing_ids_refuse(self) -> None:
        with pytest.raises(ValueError, match="strictly increasing"):
            encode_postings([3, 3])
        with pytest.raises(ValueError, match="strictly increasing"):
            encode_postings([5, 2])

    def test_out_of_range_ids_refuse(self) -> None:
        with pytest.raises(ValueError, match="strictly increasing"):
            encode_postings([0])
        with pytest.raises(ValueError, match="range"):
            encode_postings([MAX_DOC_ID + 1])


class TestCorruptionRefusals:
    def test_empty_blob(self) -> None:
        with pytest.raises(PostingCorruptionError, match="empty"):
            decode_postings(b"")

    def test_truncated_varint(self) -> None:
        with pytest.raises(PostingCorruptionError, match="truncated"):
            decode_postings(b"\x01\x81")

    def test_over_wide_varint(self) -> None:
        with pytest.raises(PostingCorruptionError, match="over-wide"):
            decode_postings(b"\x01" + b"\x80" * 10 + b"\x01")

    def test_the_minimal_over_wide_varint_refuses(self) -> None:
        # Ten bytes is the first illegal width; a laxer cap decodes this
        # blob silently as [5] via uint64 wrap instead of refusing.
        with pytest.raises(PostingCorruptionError, match="over-wide"):
            decode_postings(varint(1) + varint(2**64 + 5))

    def test_non_canonical_varint(self) -> None:
        # 1 encoded in two bytes: valid value, forbidden spelling.
        with pytest.raises(PostingCorruptionError, match="non-canonical"):
            decode_postings(b"\x01\x81\x00")

    def test_count_mismatch(self) -> None:
        with pytest.raises(PostingCorruptionError, match="count"):
            decode_postings(b"\x02\x01")

    def test_zero_delta(self) -> None:
        with pytest.raises(PostingCorruptionError, match="delta"):
            decode_postings(b"\x02\x01\x00")

    def test_cumsum_overflow_wraps_are_refused(self) -> None:
        # Two max-range deltas overflow int64; the wrap must refuse,
        # never surface as a negative or non-monotone doc id.
        blob = varint(2) + varint(MAX_DOC_ID) + varint(MAX_DOC_ID)
        with pytest.raises(PostingCorruptionError, match="monotone"):
            decode_postings(blob)
