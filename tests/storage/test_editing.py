"""The body an append leaves: the stored body and the tail, under the rule that a row keeps its source."""

from __future__ import annotations

import pytest

from vfs.storage.editing import appended


@pytest.mark.parametrize(
    ("stored", "tail", "joined"),
    [
        ("line0\n", "line1\n", "line0\nline1\n"),
        ("", "first\n", "first\n"),
        ("kept", "", "kept"),
        ("caf", "é".encode(), "café"),
        (b"\x00\x01", b"\x02", b"\x00\x01\x02"),
        (b"\x00\x01", "é", b"\x00\x01\xc3\xa9"),
        (b"", "text", b"text"),
    ],
    ids=["text+text", "empty+text", "text+empty", "text+utf8-bytes", "bytes+bytes", "bytes+text", "empty-bytes+text"],
)
def test_a_row_keeps_its_source_when_the_joined_body_allows(
    stored: str | bytes, tail: str | bytes, joined: str | bytes
) -> None:
    assert appended(stored, tail) == joined
    assert type(appended(stored, tail)) is type(stored)


@pytest.mark.parametrize("tail", [b"\xff\xfe", b"nul\x00byte"], ids=["not-utf8", "a-nul"])
def test_a_text_row_becomes_bytes_when_the_tail_cannot_be_text(tail: bytes) -> None:
    assert appended("old ", tail) == b"old " + tail
