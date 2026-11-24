"""The vid: twenty hex characters naming one entry at one version of one mount."""

from __future__ import annotations

import pytest
from ulid import ULID

from vfs.vid import VID_LENGTH, VidMint, is_vid

_MOUNT = str(ULID())


def _keys(count: int) -> list[bytes]:
    return [ULID().bytes for _ in range(count)]


def test_a_vid_is_twenty_lowercase_hex_characters():
    mint = VidMint(_MOUNT)
    vids = [mint.mint(key, version) for version, key in enumerate(_keys(1_000), start=1)]
    assert VID_LENGTH == 20
    assert sum(is_vid(vid) for vid in vids) == 1_000


def test_one_entry_at_one_version_has_one_vid_and_no_other_row_shares_it():
    """Mutation guarded: a mint that drops the version or the mount key from the digest."""
    mint = VidMint(_MOUNT)
    pairs = [(key, version) for key in _keys(2_500) for version in (1, 2, 3, 4)]
    first = [mint.mint(key, version) for key, version in pairs]
    again = [VidMint(_MOUNT).mint(key, version) for key, version in pairs]
    other = VidMint(str(ULID()))
    assert len(set(first)) == 10_000
    assert sum(a != b for a, b in zip(first, again, strict=True)) == 0
    assert sum(other.mint(key, version) == vid for (key, version), vid in zip(pairs, first, strict=True)) == 0


@pytest.mark.parametrize(
    "value",
    [
        "0" * 19,
        "0" * 21,
        "A" + "0" * 19,
        "g" + "0" * 19,
        '"' + "0" * 18 + '"',
        "",
        12345678901234567890,
        b"0" * 20,
        None,
    ],
    ids=["19-chars", "21-chars", "upper-case", "non-hex", "quoted", "empty", "integer", "bytes", "none"],
)
def test_is_vid_refuses_each_malformed_value(value: object):
    assert is_vid(value) is False


def test_version_zero_names_the_entry_and_no_row():
    """A version no row reaches mints lawfully and differs from version one's."""
    mint = VidMint(_MOUNT)
    key = ULID().bytes
    assert is_vid(mint.mint(key, 0))
    assert mint.mint(key, 0) != mint.mint(key, 1)
