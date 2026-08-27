"""Property and corruption tests for the posting-list codec.

The codec is the durability boundary of the gram index: an encode bug
poisons every query against the epoch, and a decode bug that guesses
instead of refusing turns blob corruption into silently-wrong search
results. The battery here pins both directions — exact round-trips
through the engine's decode against the oracle, and loud refusals for
every malformed-blob class. The engine exposes no bare decoder; a
single-blob, single-group call to the candidate kernel is the decode.
"""

from __future__ import annotations

import random

import pytest

from tests.support.oracles.postings import decode_postings as oracle_decode
from vfs import _native
from vfs.models.postings import MAX_DOC_ID, encode_postings


def decode_postings(blob: bytes) -> list[int]:
    """One blob through the kernel: its ids, uncapped."""
    ids, total = _native.candidate_ids([[blob]], None, 1 << 31)
    assert total == len(ids)
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
            assert decode_postings(blob) == ids
            assert oracle_decode(blob) == ids

    def test_empty_list_round_trips_as_the_one_byte_zero_count(self) -> None:
        blob = encode_postings([])
        assert blob == b"\x00"
        assert decode_postings(blob) == []

    def test_singleton_and_bigint_edge_round_trip(self) -> None:
        for ids in ([1], [MAX_DOC_ID], [1, MAX_DOC_ID], list(range(1, 300))):
            assert decode_postings(encode_postings(ids)) == ids

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
        with pytest.raises(ValueError, match="empty"):
            decode_postings(b"")

    def test_truncated_varint(self) -> None:
        with pytest.raises(ValueError, match="truncated"):
            decode_postings(b"\x01\x81")

    def test_over_wide_varint(self) -> None:
        with pytest.raises(ValueError, match="over-wide"):
            decode_postings(b"\x01" + b"\x80" * 10 + b"\x01")

    def test_the_minimal_over_wide_varint_refuses(self) -> None:
        # Ten bytes is the first illegal width; a laxer cap decodes this
        # blob silently as [5] via uint64 wrap instead of refusing.
        with pytest.raises(ValueError, match="over-wide"):
            decode_postings(varint(1) + varint(2**64 + 5))

    def test_non_canonical_varint(self) -> None:
        # 1 encoded in two bytes: valid value, forbidden spelling.
        with pytest.raises(ValueError, match="non-canonical"):
            decode_postings(b"\x01\x81\x00")

    def test_count_mismatch(self) -> None:
        with pytest.raises(ValueError, match="count"):
            decode_postings(b"\x02\x01")

    def test_zero_delta(self) -> None:
        with pytest.raises(ValueError, match="delta"):
            decode_postings(b"\x02\x01\x00")

    def test_cumsum_overflow_wraps_are_refused(self) -> None:
        # Two max-range deltas overflow int64; the wrap must refuse,
        # never surface as a negative or non-monotone doc id.
        blob = varint(2) + varint(MAX_DOC_ID) + varint(MAX_DOC_ID)
        with pytest.raises(ValueError, match="monotone"):
            decode_postings(blob)
