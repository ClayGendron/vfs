"""Generated document fixtures for the rendering tests — bytes built in process, no files.

Every builder returns the bytes of a real file of its format, made with
the same library the renderer reads it with, so a test states what the
document holds and asserts what the rendering says about it.
"""

from __future__ import annotations

import re
import struct
import warnings
import zipfile
import zlib
from io import BytesIO
from typing import TYPE_CHECKING

import docx
import openpyxl
import pptx
import pypdf
from pptx.util import Inches
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def png_bytes(width: int = 2, height: int = 2) -> bytes:
    """A valid solid-red PNG of the given size."""
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def pdf_bytes(pages: Sequence[str | None]) -> bytes:
    """One page per item: its lines of Helvetica text, or a blank page for ``None``."""
    writer = pypdf.PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        fonts = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
        shown = " ".join(f"({line}) Tj T*" for line in text.split("\n"))
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td 14 TL {shown} ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def surrogate_pdf_bytes() -> bytes:
    """A one-page PDF whose ToUnicode map sends the glyph ``A`` to a lone surrogate (U+D800)."""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    cmap = DecodedStreamObject()
    cmap.set_data(
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
        b"/CMapName /Custom def 1 begincodespacerange <00> <FF> endcodespacerange "
        b"1 beginbfchar <41> <D800> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/ToUnicode"): writer._add_object(cmap),
        }
    )
    fonts = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (A) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def encrypted_pdf_bytes(pages: Sequence[str | None], password: str = "secret") -> bytes:
    """*pages* as a PDF that opens only with *password* (an empty one when ``password`` is empty)."""
    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(BytesIO(pdf_bytes(pages))))
    writer.encrypt(password, owner_password="owner")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# docx
# ---------------------------------------------------------------------------


def docx_bytes(
    paragraphs: Sequence[str] = (),
    *,
    title: str | None = None,
    headings: Sequence[tuple[int, str]] = (),
    table: Sequence[Sequence[str]] | None = None,
    header: str | None = None,
    footer: str | None = None,
    comment: str | None = None,
    picture: bool = False,
    second_section: bool = False,
) -> bytes:
    """A document in this body order: title, headings, paragraphs, table, then a picture.

    *comment* is attached to the first paragraph's runs; *header* and
    *footer* fill the first section's header and footer; with
    *second_section* a second section follows, its header and footer
    linked to the first's.
    """
    document = docx.Document()
    if title is not None:
        document.add_heading(title, 0)
    for level, text in headings:
        document.add_heading(text, level)
    written = [document.add_paragraph(text) for text in paragraphs]
    if comment is not None and written:
        document.add_comment(written[0].runs, text=comment, author="Reviewer")
    if table is not None:
        grid = document.add_table(rows=len(table), cols=max(len(row) for row in table))
        for r, row in enumerate(table):
            for c, cell in enumerate(row):
                grid.cell(r, c).text = cell
    if picture:
        document.add_picture(BytesIO(png_bytes()))
    section = document.sections[0]
    if header is not None:
        section.header.paragraphs[0].text = header
    if footer is not None:
        section.footer.paragraphs[0].text = footer
    if second_section:
        document.add_section()
        document.add_paragraph("second section text")
    out = BytesIO()
    document.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# pptx
# ---------------------------------------------------------------------------


def pptx_bytes(
    slides: Sequence[tuple[str | None, Sequence[str]]],
    *,
    notes: str | None = None,
    table: Sequence[Sequence[str]] | None = None,
    picture: bool = False,
    grouped: str | None = None,
    nested: str | None = None,
    blank_notes: bool = False,
) -> bytes:
    """One slide per ``(title, body lines)``; the extras land on the first slide.

    *grouped* puts a text box inside a group; *nested* puts one inside a
    group inside a group; *blank_notes* attaches an empty notes slide.
    """
    presentation = pptx.Presentation()
    for index, (title, lines) in enumerate(slides):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1 if title is not None else 6])
        if title is not None:
            slide.shapes.title.text = title
            slide.placeholders[1].text_frame.text = "\n".join(lines)
        else:
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
            box.text_frame.text = "\n".join(lines)
        if index:
            continue
        if notes is not None:
            slide.notes_slide.notes_text_frame.text = notes
        if table is not None:
            grid = slide.shapes.add_table(len(table), len(table[0]), Inches(1), Inches(3), Inches(4), Inches(1)).table
            for r, row in enumerate(table):
                for c, cell in enumerate(row):
                    grid.cell(r, c).text = cell
        if picture:
            slide.shapes.add_picture(BytesIO(png_bytes()), Inches(1), Inches(5)).name = "Logo"
        if grouped is not None:
            group = slide.shapes.add_group_shape()
            box = group.shapes.add_textbox(Inches(1), Inches(6), Inches(2), Inches(1))
            box.text_frame.text = grouped
        if nested is not None:
            inner = slide.shapes.add_group_shape().shapes.add_group_shape()
            box = inner.shapes.add_textbox(Inches(1), Inches(6), Inches(2), Inches(1))
            box.text_frame.text = nested
        if blank_notes:
            slide.notes_slide.notes_text_frame.text = ""
    out = BytesIO()
    presentation.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# xlsx
# ---------------------------------------------------------------------------


# The dimension element a worksheet part states its extent in, as the writer spells it.
_DIMENSION = re.compile(rb'<dimension ref="[^"]*"/>')


def xlsx_bytes(
    sheets: Mapping[str, Mapping[str, object]], *, hidden: Sequence[str] = (), dimension: str | None = None
) -> bytes:
    """One sheet per name holding the given ``cell address → value`` entries; *hidden* names are hidden.

    A *dimension* (``"A1:Z200"``) is stated by every worksheet part in
    place of the one the writer computed from its cells.
    """
    workbook = openpyxl.Workbook()
    first = True
    for name, cells in sheets.items():
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        sheet.title = name
        for address, value in cells.items():
            sheet[address] = value
        if name in hidden:
            sheet.sheet_state = "hidden"
    out = BytesIO()
    workbook.save(out)
    if dimension is None:
        return out.getvalue()
    stated = f'<dimension ref="{dimension}"/>'.encode()
    restated = BytesIO()
    with zipfile.ZipFile(out) as source, zipfile.ZipFile(restated, "w") as target:
        for info in source.infolist():
            body = source.read(info)
            if info.filename.startswith("xl/worksheets/sheet"):
                body, count = _DIMENSION.subn(stated, body, count=1)
                assert count == 1  # the writer states a dimension in every worksheet part
            target.writestr(_entry(info, info.compress_type), body)
    return restated.getvalue()


# ---------------------------------------------------------------------------
# Container directories
# ---------------------------------------------------------------------------

# The zip format's central-directory entry and end-record signatures, and the entry's field
# offsets: flags, method, CRC-32, uncompressed size, the three lengths, the name.
_ENTRY_SIGNATURE = b"PK\x01\x02"
_END_SIGNATURE = b"PK\x05\x06"
_FLAGS_AT = 8
_METHOD_AT = 10
_CRC_AT = 16
_SIZE_AT = 24
_LENGTHS_AT = 28
_NAME_AT = 46
# What an alias's stored name carries past the member's name, which zipfile drops on reading it.
_ALIAS_TAIL = "\x00alias"


def declared(
    data: bytes,
    member: str,
    *,
    file_size: int | None = None,
    method: int | None = None,
    crc: int | None = None,
    flags: int | None = None,
) -> bytes:
    """*data* with *member*'s last central-directory entry declaring another size, method, CRC-32 or flag word.

    Only the directory changes: the member's stream and its local header
    are left as written, which is what a reader that trusts the directory
    must be checked against. A name listed twice has its last entry
    changed, the one zipfile resolves the name to.
    """
    out = bytearray(data)
    end = data.rfind(_END_SIGNATURE)
    count, _, offset = struct.unpack_from("<HII", data, end + 10)
    found = None
    for _ in range(count):
        assert data[offset : offset + 4] == _ENTRY_SIGNATURE
        name_length, extra_length, comment_length = struct.unpack_from("<HHH", data, offset + _LENGTHS_AT)
        if data[offset + _NAME_AT : offset + _NAME_AT + name_length].decode("utf-8") == member:
            found = offset
        offset += _NAME_AT + name_length + extra_length + comment_length
    if found is None:
        raise KeyError(member)
    fields = (("<H", _FLAGS_AT, flags), ("<H", _METHOD_AT, method), ("<I", _CRC_AT, crc), ("<I", _SIZE_AT, file_size))
    for layout, at, value in fields:
        if value is not None:
            struct.pack_into(layout, out, found + at, value)
    return bytes(out)


def recompressed(data: bytes, method: int) -> bytes:
    """*data* written again through ``zipfile`` with every member compressed by *method*."""
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(_entry(info, method), source.read(info))
    return out.getvalue()


def duplicated(data: bytes, member: str) -> bytes:
    """*data* written again with a second entry for *member*, its stream a copy, appended last."""
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(_entry(info, info.compress_type), source.read(info))
        info = source.getinfo(member)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)  # zipfile warns of the duplicate it is asked to write
            target.writestr(_entry(info, info.compress_type), source.read(info))
    return out.getvalue()


def aliased(data: bytes, member: str) -> bytes:
    """*data* written again with a second entry appended last, its stream a copy of *member*'s, whose stored
    name differs from *member*'s but which zipfile reads back as *member*'s name."""
    placeholder = member + "~" * len(_ALIAS_TAIL)
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(_entry(info, info.compress_type), source.read(info))
        info = source.getinfo(member)
        alias = zipfile.ZipInfo(placeholder, info.date_time)
        alias.compress_type = info.compress_type
        target.writestr(alias, source.read(info))
    written = out.getvalue()
    assert written.count(placeholder.encode()) == 2  # the alias's local header and its directory entry
    return written.replace(placeholder.encode(), (member + _ALIAS_TAIL).encode())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _entry(info: zipfile.ZipInfo, method: int) -> zipfile.ZipInfo:
    """A fresh entry for *info*'s name and time, compressed by *method*."""
    entry = zipfile.ZipInfo(info.filename, info.date_time)
    entry.compress_type = method
    return entry
