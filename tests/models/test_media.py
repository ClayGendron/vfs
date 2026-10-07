"""The sniffed media type: magic decides, names and declared types only narrow."""

from __future__ import annotations

import pytest

from vfs.models.media import (
    OCTET_STREAM,
    OOXML_TYPES,
    RENDER_STATUSES,
    RENDERED_STATUSES,
    SOURCES,
    ZIP,
    sniff_mime,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
GIF87 = b"GIF87a\x01\x00"
GIF89 = b"GIF89a\x01\x00"
TIFF_LE = b"II*\x00\x08\x00\x00\x00"
TIFF_BE = b"MM\x00*\x00\x00\x00\x08"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
PKZIP = b"PK\x03\x04\x14\x00\x06\x00"


@pytest.mark.parametrize(
    ("head", "mime"),
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (GIF87, "image/gif"),
        (GIF89, "image/gif"),
        (TIFF_LE, "image/tiff"),
        (TIFF_BE, "image/tiff"),
        (WEBP, "image/webp"),
    ],
)
def test_magic_decides_the_family_over_any_declaration(head: bytes, mime: str) -> None:
    assert sniff_mime(head) == mime
    assert sniff_mime(head, declared="text/plain", ext="txt") == mime


def test_a_riff_container_that_is_not_webp_is_not_an_image() -> None:
    assert sniff_mime(b"RIFF\x24\x00\x00\x00WAVEfmt ") == OCTET_STREAM


class TestZipContainers:
    def test_the_extension_picks_the_office_type(self) -> None:
        for ext, mime in OOXML_TYPES.items():
            assert sniff_mime(PKZIP, ext=ext) == mime
            assert sniff_mime(PKZIP, ext=ext.upper()) == mime

    def test_a_declared_office_type_is_kept_when_the_name_says_nothing(self) -> None:
        docx = OOXML_TYPES["docx"]
        assert sniff_mime(PKZIP, declared=docx) == docx
        assert sniff_mime(PKZIP, declared=docx, ext="bin") == docx

    def test_a_bare_zip_stays_a_zip(self) -> None:
        assert sniff_mime(PKZIP) == ZIP
        assert sniff_mime(PKZIP, declared="text/plain", ext="zip") == ZIP

    def test_the_extension_outranks_a_contradicting_declaration(self) -> None:
        assert sniff_mime(PKZIP, declared=OOXML_TYPES["docx"], ext="xlsx") == OOXML_TYPES["xlsx"]


class TestUnrecognised:
    def test_keeps_the_declared_type(self) -> None:
        assert sniff_mime(b"\x00\x01\x02", declared="application/x-custom") == "application/x-custom"

    def test_falls_to_an_octet_stream(self) -> None:
        assert sniff_mime(b"") == OCTET_STREAM
        assert sniff_mime(b"hello", ext="txt") == OCTET_STREAM


def test_the_status_vocabulary_is_closed_and_rendered_is_a_subset() -> None:
    assert RENDERED_STATUSES < RENDER_STATUSES
    assert "pending" in RENDER_STATUSES
    assert "pending" not in RENDERED_STATUSES
    assert {"text", "bytes"} == SOURCES
