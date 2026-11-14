"""The docx renderer: body flow with tables interleaved, on python-docx.

Heading styles become heading levels (``Title`` the first, ``Heading
N`` the Nth), tables keep their place in body order with the first
row as header, section headers come first and footers last, and a
footnote or comment is written inline at its reference, bracketed and
marked. Embedded pictures are placeholders carrying the document's own
alt text. docx has no page concept any library trusts, so there are no
unit markers; the truncation count is in body blocks, and the unit cap
does not apply to them — the character budget bounds a document.

The work follows the text written: a note's text is written at its
first reference and marked after, a header or footer part is walked
once, a span is never wider than the table's grid, a merged cell is
read once, and styles are looked up in a table read once. A paragraph
or a table row stops being collected once it holds more than the budget
has left, and every loop that writes reads the clock once a block.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import cached_property
from io import BytesIO
from time import monotonic
from typing import TYPE_CHECKING, Any, Final

from vfs.deadline import Deadline
from vfs.models.media import DOCX
from vfs.rendering.markdown import Builder, flatten, kept_length
from vfs.rendering.seam import BundledRenderer, Rendering, container_refusal, failure_from, load_library

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from vfs.rendering.seam import RenderLimits, RenderSource

_W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_WP: Final = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"

_TITLE_STYLE: Final = "Title"
_HEADING_PREFIX: Final = "Heading "
# The values that turn an OOXML boolean attribute on; any other reads as off.
_ON: Final = frozenset({"1", "true", "on"})
# A vertical merge's continuation, the value python-docx reads for a bare ``w:vMerge``.
_CONTINUE: Final = "continue"


class DocxRenderer(BundledRenderer):
    """Body order to Markdown flow through python-docx."""

    name = "docx"
    extra = "docx"
    mimes = (DOCX,)
    package = "docx"
    distribution = "python-docx"
    revision = 2

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        docx = self.library
        started = monotonic()
        refused = container_refusal(
            source.data, limits, self.name, Deadline(at=started + limits.seconds), byte_limit=limits.container_bytes
        )
        if refused is not None:
            return refused
        try:
            document = docx.Document(BytesIO(source.data))
        except Exception as exc:  # a file python-docx cannot open is malformed input, not a surprise
            return failure_from(exc, self.name, "corrupt")
        styles = load_library("docx.styles")
        assert styles is not None  # the package opened the file; its styles module is present
        blocks = list(_blocks(document))
        builder = Builder(limits, input_bytes=len(source.data), total_units=len(blocks), started=started)
        writer = _Writer(builder, _Notes(document), _Styles(document, styles.BabelFish.internal2ui))
        writer.parts(section.header for section in document.sections)
        for number, block in enumerate(blocks, 1):
            if not builder.boundary(number):
                break
            if isinstance(block, docx.table.Table):
                writer.table(block)
            else:
                writer.paragraph(block)
        writer.parts(section.footer for section in document.sections)
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
    """Each note directly under the part's root, by id; a note nested in another is read as part of the outer."""
    try:
        part = document.part.part_related_by(reltype)
    except KeyError:
        return {}
    root = ET.fromstring(part.blob)
    texts: dict[str, str] = {}
    for note in root.findall(tag):
        note_id = note.get(f"{_W}id")
        if note_id is not None:
            texts[note_id] = flatten("".join(t.text or "" for t in note.iter(f"{_W}t")))
    return texts


class _Styles:
    """Each paragraph's style name from a table of the styles part, built in one pass at the first lookup.

    The table holds the first style of each id, as python-docx's query
    finds it, and the last paragraph style marked default. The type, the
    default and the name are read as raw attributes, so a value
    python-docx would refuse reads as not paragraph, not default or no
    name, and a declared id is only ever a key, never part of a query.
    """

    def __init__(self, document: Any, ui_name: Callable[[str], str]) -> None:
        self._document = document
        self._ui_name = ui_name
        self._names: dict[str, str | None] | None = None
        self._default: str | None = None

    def name(self, p: Any) -> str | None:
        """The name python-docx shows for paragraph element *p*'s style; the default's when its id names none."""
        if self._names is None:
            self._names = self._read()
        style_id = p.style
        if style_id and style_id in self._names:
            return self._names[style_id]
        return self._default

    def _read(self) -> dict[str, str | None]:
        names: dict[str, str | None] = {}
        seen: set[str] = set()
        for style in self._document.styles.element._iter_styles():
            paragraph = style.get(f"{_W}type") == "paragraph"
            element = style.find(f"{_W}name")
            value = None if element is None else element.get(f"{_W}val")
            name = None if value is None else self._ui_name(value)
            if paragraph and style.get(f"{_W}default") in _ON:
                self._default = name
            style_id = style.styleId
            if style_id is None or style_id in seen:
                continue
            seen.add(style_id)
            if paragraph:
                names[style_id] = name
        return names


class _Writer:
    """Paragraphs, parts and tables onto the builder, notes inline, pictures as placeholders."""

    def __init__(self, builder: Builder, notes: _Notes, styles: _Styles | None = None) -> None:
        self._builder = builder
        self._notes = notes
        self._styles = styles
        self._pictures = 0
        self._written: set[tuple[str, str | None]] = set()
        self._parts: set[object] = set()

    def parts(self, items: Iterable[Any]) -> None:
        """Each header or footer part once, at the first section whose own definition names it.

        The clock is read before each paragraph, as the body reads it
        before each block, and an answer past it ends the walk.
        """
        for item in items:
            if item.is_linked_to_previous:
                continue
            part = item.part
            if part in self._parts:
                continue
            self._parts.add(part)
            for paragraph in item.paragraphs:
                if self._builder.out_of_time():
                    return
                self.paragraph(paragraph)

    def paragraph(self, paragraph: Any) -> None:
        if self._builder.stopped:
            return
        text, pictures = self._inline(paragraph._p)
        level = _heading_level(None if self._styles is None else self._styles.name(paragraph._p))
        if level is not None:
            self._builder.heading(level, text)
        else:
            self._builder.paragraph(text)
        for alt in pictures:
            self._pictures += 1
            self._builder.image(alt, self._pictures)

    def table(self, table: Any) -> None:
        """The table from its own elements: its width from the layout before any text is read, its rows drawn lazily.

        The layout is one pass over every cell element of the table, made before the first row is drawn and without
        the clock; its memory is one source per cell element, measured at about 150 bytes a cell element more than
        python-docx's own row lists held.
        """
        tbl = table._tbl
        rows = tbl.tr_lst
        declared = tbl.find(f"{_W}tblGrid")
        grid = 0 if declared is None else len(declared.findall(f"{_W}gridCol"))
        layout = _layout(rows, grid or max((len(tr.tc_lst) for tr in rows), default=0))
        width = max((sum(copies for _, copies in row) for row in layout), default=0)
        self._builder.table(self._rows(layout), width=width)

    def _rows(self, layout: list[list[tuple[_Source, int]]]) -> Iterator[list[str]]:
        """Each row's cell texts as the Builder pulls it.

        A row stops once its kept characters pass what the budget has
        left, read as the row is drawn; the Builder refuses that row, and
        nothing is drawn after it.
        """
        for row in layout:
            remaining = self._builder.remaining
            cells: list[str] = []
            kept = 0
            for source, copies in row:
                for _ in range(copies):
                    cells.append(source.text)
                    kept += source.kept
                    if kept > remaining:
                        yield cells
                        return
            yield cells

    def _inline(self, element: Any) -> tuple[str, list[str | None]]:
        """The paragraph's text with notes written at their references, and its pictures' alt texts.

        Collecting stops once the kept characters pass what the budget
        has left, because the Builder must then refuse the paragraph.
        """
        remaining = self._builder.remaining
        parts: list[str] = []
        pictures: list[str | None] = []
        kept = 0
        for node in element.iter():
            tag = node.tag
            if tag == f"{_W}t":
                piece = node.text or ""
            elif tag == f"{_W}tab":
                piece = "\t"
            elif tag in (f"{_W}br", f"{_W}cr"):
                piece = "\n"
            elif tag == f"{_W}footnoteReference":
                piece = self._note("footnote", node.get(f"{_W}id"), self._notes.footnotes)
            elif tag == f"{_W}commentReference":
                piece = self._note("comment", node.get(f"{_W}id"), self._notes.comments)
            else:
                if tag == f"{_WP}docPr":
                    pictures.append(node.get("descr") or node.get("title") or node.get("name"))
                continue
            parts.append(piece)
            kept += kept_length(piece)
            if kept > remaining:
                break
        return "".join(parts), pictures

    def _note(self, kind: str, note_id: str | None, texts: dict[str, str]) -> str:
        """The note's text at its first reference in the rendering, its bare marker at every later one."""
        text = texts.get(note_id or "", "")
        if not text or (kind, note_id) in self._written:
            return f" [{kind} {note_id}]"
        self._written.add((kind, note_id))
        return f" [{kind} {note_id}: {text}]"


def _layout(rows: Iterable[Any], grid: int) -> list[list[tuple[_Source, int]]]:
    """Each row as its cell elements' sources and the copies each adds, in one pass over the cell elements.

    A span is read as at least one and adds copies only while the row
    has fewer cells than *grid* columns, so every cell element keeps one
    cell. A vertical continuation takes the source that starts at its
    offset in the row above, with that source's span; one with nothing
    there is a cell of its own. Offsets count declared spans, as
    python-docx finds the cell above.
    """
    layout: list[list[tuple[_Source, int]]] = []
    above: dict[int, tuple[_Source, int]] = {}
    for tr in rows:
        here: dict[int, tuple[_Source, int]] = {}
        cells: list[tuple[_Source, int]] = []
        offset = tr.grid_before
        count = 0
        for tc in tr.tc_lst:
            span = tc.grid_span
            placed = above.get(offset) if tc.vMerge == _CONTINUE else None
            source, wide = (_Source(tc), span) if placed is None else placed
            here.setdefault(offset, (source, wide))
            copies = 1 + max(0, min(wide - 1, grid - count - 1))
            cells.append((source, copies))
            count += copies
            offset += span
        layout.append(cells)
        above = here
    return layout


class _Source:
    """The cell element a cell's text comes from: its text flattened, and its kept length counted, once."""

    def __init__(self, tc: Any) -> None:
        self._tc = tc

    @cached_property
    def text(self) -> str:
        return flatten("\n".join(p.text for p in self._tc.p_lst))

    @cached_property
    def kept(self) -> int:
        return kept_length(self.text)


def _heading_level(style: str | None) -> int | None:
    if style is None:
        return None
    if style == _TITLE_STYLE:
        return 1
    if style.startswith(_HEADING_PREFIX) and style[len(_HEADING_PREFIX) :].isdigit():
        return int(style[len(_HEADING_PREFIX) :])
    return None
