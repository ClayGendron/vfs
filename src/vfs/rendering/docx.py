"""The docx renderer: body flow with tables interleaved, on python-docx.

Heading styles become heading levels (``Title`` the first, ``Heading
N`` the Nth), tables keep their place in body order with the first
row as header, section headers come first and footers last, and a
footnote or comment is written inline at its reference, bracketed and
marked. Embedded pictures are placeholders carrying the document's own
alt text. docx has no page concept any library trusts, so there are no
unit markers; the truncation count is in body blocks, and the unit cap
does not apply to them — the character budget bounds a document.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from io import BytesIO
from time import monotonic
from typing import TYPE_CHECKING, Any, Final

from vfs.models.media import DOCX
from vfs.rendering.markdown import Builder, flatten
from vfs.rendering.seam import BundledRenderer, Rendering, failure_from

if TYPE_CHECKING:
    from collections.abc import Iterator

    from vfs.rendering.seam import RenderLimits, RenderSource

_W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_WP: Final = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"

_TITLE_STYLE: Final = "Title"
_HEADING_PREFIX: Final = "Heading "


class DocxRenderer(BundledRenderer):
    """Body order to Markdown flow through python-docx."""

    name = "docx"
    extra = "docx"
    mimes = (DOCX,)
    package = "docx"
    distribution = "python-docx"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        docx = self.library
        started = monotonic()
        try:
            document = docx.Document(BytesIO(source.data))
        except Exception as exc:  # a file python-docx cannot open is malformed input, not a surprise
            return failure_from(exc, self.name, "corrupt")
        blocks = list(_blocks(document))
        builder = Builder(limits, input_bytes=len(source.data), total_units=len(blocks), started=started)
        writer = _Writer(builder, _Notes(document))
        for section in document.sections:
            if not section.header.is_linked_to_previous:
                writer.paragraphs(section.header.paragraphs)
        for number, block in enumerate(blocks, 1):
            if not builder.boundary(number):
                break
            if isinstance(block, docx.table.Table):
                writer.table(block)
            else:
                writer.paragraph(block)
        for section in document.sections:
            if not section.footer.is_linked_to_previous:
                writer.paragraphs(section.footer.paragraphs)
        return builder.build()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _blocks(document: Any) -> Iterator[Any]:
    """The body's paragraphs and tables in document order — python-docx's own typed walk."""
    return document.iter_inner_content()


class _Notes:
    """Footnote and comment texts by id, read from their parts when the document has them."""

    def __init__(self, document: Any) -> None:
        self.footnotes = _note_texts(document, f"{_REL}footnotes", f"{_W}footnote")
        self.comments = _note_texts(document, f"{_REL}comments", f"{_W}comment")


def _note_texts(document: Any, reltype: str, tag: str) -> dict[str, str]:
    try:
        part = document.part.part_related_by(reltype)
    except KeyError:
        return {}
    root = ET.fromstring(part.blob)
    texts: dict[str, str] = {}
    for note in root.iter(tag):
        note_id = note.get(f"{_W}id")
        if note_id is not None:
            texts[note_id] = flatten("".join(t.text or "" for t in note.iter(f"{_W}t")))
    return texts


class _Writer:
    """Paragraphs and tables onto the builder, notes inline, pictures as placeholders."""

    def __init__(self, builder: Builder, notes: _Notes) -> None:
        self._builder = builder
        self._notes = notes
        self._pictures = 0

    def paragraphs(self, paragraphs: Any) -> None:
        for paragraph in paragraphs:
            self.paragraph(paragraph)

    def paragraph(self, paragraph: Any) -> None:
        text, pictures = self._inline(paragraph._p)
        level = _heading_level(paragraph.style.name if paragraph.style is not None else None)
        if level is not None:
            self._builder.heading(level, text)
        else:
            self._builder.paragraph(text)
        for alt in pictures:
            self._pictures += 1
            self._builder.image(alt, self._pictures)

    def table(self, table: Any) -> None:
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        self._builder.table(rows)

    def _inline(self, element: Any) -> tuple[str, list[str | None]]:
        """The paragraph's text with notes written at their references, and its pictures' alt texts."""
        parts: list[str] = []
        pictures: list[str | None] = []
        for node in element.iter():
            tag = node.tag
            if tag == f"{_W}t":
                parts.append(node.text or "")
            elif tag == f"{_W}tab":
                parts.append("\t")
            elif tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
            elif tag == f"{_W}footnoteReference":
                parts.append(_note("footnote", node.get(f"{_W}id"), self._notes.footnotes))
            elif tag == f"{_W}commentReference":
                parts.append(_note("comment", node.get(f"{_W}id"), self._notes.comments))
            elif tag == f"{_WP}docPr":
                pictures.append(node.get("descr") or node.get("title") or node.get("name"))
        return "".join(parts), pictures


def _note(kind: str, note_id: str | None, texts: dict[str, str]) -> str:
    text = texts.get(note_id or "", "")
    return f" [{kind} {note_id}: {text}]" if text else f" [{kind} {note_id}]"


def _heading_level(style: str | None) -> int | None:
    if style is None:
        return None
    if style == _TITLE_STYLE:
        return 1
    if style.startswith(_HEADING_PREFIX) and style[len(_HEADING_PREFIX) :].isdigit():
        return int(style[len(_HEADING_PREFIX) :])
    return None
