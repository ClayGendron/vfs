"""Unit tests for the delta+gamma posting codec and the posting merge.

Pure-Python, no database. Covers codec round-trip, the byte-format contract
(golden vectors that lock the on-disk format), the encode strict-monotonic
guard, decode corruption detection, and ``merge_postings`` against a
brute-force set oracle.
"""

from __future__ import annotations

import random

import pytest

from vfs.postings import (
    GammaWriter,
    PostingCorruptionError,
    decode_postings,
    encode_postings,
    merge_postings,
)

# --- codec round-trip -------------------------------------------------------


@pytest.mark.parametrize(
    "ids",
    [
        [],
        [1],
        [10, 20, 30],
        [1, 2, 3, 4, 5],
        list(range(1, 201)),  # dense run — gamma collapses the 1-gaps
        [16, 17, 31, 32, 33],  # straddles the deltaZeroEnc=16 remap boundary
        [1, 1_000_000],  # large gap
        [5, 21, 22],
        [2**40, 2**40 + 1],  # large doc_ids
    ],
)
def test_codec_roundtrip(ids: list[int]) -> None:
    assert decode_postings(encode_postings(ids), len(ids)) == ids


def test_codec_roundtrip_randomized() -> None:
    rng = random.Random(1234)
    for _ in range(3000):
        ids = sorted(rng.sample(range(1, 1_000_000), rng.randint(0, 80)))
        assert decode_postings(encode_postings(ids), len(ids)) == ids


# --- byte-format contract ---------------------------------------------------
# Golden vectors lock the on-disk posting format. A change here means the format
# changed — which must instead happen through the per-row ``encoding`` tag,
# never by mutating gamma's bytes.


@pytest.mark.parametrize(
    ("ids", "hexstr"),
    [
        ([10, 20, 30], "38140a02"),
        ([1], "8200"),
        ([1, 2, 3, 4, 5], "7a08"),
        ([16, 17, 31, 32, 33], "50a28700"),
        ([1, 1_000_000], "02004020a14300"),
        ([5, 21, 22], "144608"),
    ],
)
def test_codec_byte_format_stable(ids: list[int], hexstr: str) -> None:
    assert encode_postings(ids).hex() == hexstr


# --- encode contract --------------------------------------------------------


def test_encode_rejects_unsorted() -> None:
    with pytest.raises(ValueError):
        encode_postings([3, 1, 2])


def test_encode_rejects_duplicates() -> None:
    with pytest.raises(ValueError):
        encode_postings([1, 1, 2])


# --- decode corruption detection --------------------------------------------


def test_decode_wrong_count_too_small_raises() -> None:
    # doc_count too small ⇒ the value after the last gap isn't the 0 terminator.
    with pytest.raises(PostingCorruptionError):
        decode_postings(encode_postings([10, 20, 30]), 2)


def test_decode_wrong_count_too_large_raises() -> None:
    # doc_count too large ⇒ reads the terminator as a gap (0 ⇒ non-positive).
    with pytest.raises(PostingCorruptionError):
        decode_postings(encode_postings([10, 20, 30]), 5)


def test_decode_truncated_raises() -> None:
    with pytest.raises(PostingCorruptionError):
        decode_postings(encode_postings([100, 200, 300])[:1], 3)


def test_decode_negative_count_raises() -> None:
    with pytest.raises(PostingCorruptionError):
        decode_postings(encode_postings([1, 2]), -1)


def test_decode_trailing_data_raises() -> None:
    with pytest.raises(PostingCorruptionError):
        decode_postings(encode_postings([1, 2]) + b"junk", 2)


def test_decode_trailing_zero_byte_raises() -> None:
    with pytest.raises(PostingCorruptionError):
        decode_postings(encode_postings([1, 2]) + b"\x00", 2)


def test_decode_over_wide_gamma_raises() -> None:
    w = GammaWriter()
    w.write_value(1 << 80)  # a gap no real doc-id set could produce
    w.write_value(0)
    with pytest.raises(PostingCorruptionError):
        decode_postings(w.finish(), 1)


def test_encode_accepts_max_doc_id() -> None:
    max_id = (1 << 63) - 1
    assert decode_postings(encode_postings([max_id]), 1) == [max_id]


def test_encode_rejects_out_of_range_doc_id() -> None:
    with pytest.raises(ValueError):
        encode_postings([1 << 63])  # one past signed BIGINT max


def test_decode_rejects_out_of_range_doc_id() -> None:
    # A blob whose gamma is in-range but whose accumulated doc_id overflows
    # signed BIGINT (gap = 2**63 - (-1) yields doc_id 2**63).
    w = GammaWriter()
    w.write_value((1 << 63) + 1)
    w.write_value(0)
    with pytest.raises(PostingCorruptionError):
        decode_postings(w.finish(), 1)


# --- merge_postings ---------------------------------------------------------


def test_merge_basic() -> None:
    assert merge_postings([1, 2, 3], [3, 4, 5], set()) == [1, 2, 3, 4, 5]


def test_merge_default_dels() -> None:
    assert merge_postings([1, 2, 3], [4, 5]) == [1, 2, 3, 4, 5]


def test_merge_deletes() -> None:
    assert merge_postings([1, 2, 3, 4], [], {2, 4}) == [1, 3]


def test_merge_empty_base() -> None:
    assert merge_postings([], [9, 1, 5], set()) == [1, 5, 9]


def test_merge_empty_result() -> None:
    assert merge_postings([1, 2], [], {1, 2}) == []


def test_merge_add_of_present_dedup() -> None:
    assert merge_postings([1, 2, 3], [2, 3, 4], set()) == [1, 2, 3, 4]


def test_merge_oracle_randomized() -> None:
    rng = random.Random(11)
    for _ in range(5000):
        base = sorted(rng.sample(range(1, 500), rng.randint(0, 60)))
        adds = set(rng.sample(range(1, 500), rng.randint(0, 30)))
        # adds and dels are disjoint by the codec contract.
        del_pool = (set(base) | set(rng.sample(range(1, 500), 10))) - adds
        dels = (
            set(rng.sample(sorted(del_pool), min(len(del_pool), rng.randint(0, 15))))
            if del_pool
            else set()
        )
        got = merge_postings(base, adds, dels)
        assert got == sorted((set(base) | adds) - dels)
        assert all(got[i] < got[i + 1] for i in range(len(got) - 1))  # strictly increasing
