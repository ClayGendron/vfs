"""The docx renderer's work follows the text it writes: notes, parts, spans, merges, styles and the clock.

Every count here is of work done (paragraph text reads, inline walks,
characters handed to the Builder, rows drawn, style elements visited,
clock reads), never of seconds. Each document is built in process with
python-docx and edits to its parsed elements.
"""

from __future__ import annotations

import hashlib
import sys
from copy import deepcopy
from io import BytesIO
from typing import TYPE_CHECKING, Any

import docx
from docx.enum.section import WD_HEADER_FOOTER
from docx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.oxml.styles import CT_Styles
from docx.oxml.table import CT_Tc
from docx.oxml.text.paragraph import CT_P
from docx.styles import BabelFish

from vfs.models.media import DOCX
from vfs.rendering import RendererRegistry, Rendering, RenderLimits, RenderSource
from vfs.rendering.docx import DocxRenderer, _layout, _Notes, _Writer
from vfs.rendering.markdown import Builder, kept_length

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pytest

LIMITS = RenderLimits()
_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
# A comment of exactly forty characters.
COMMENT = "remark " * 5 + "abcde"
# One SHA-256 over the mixed document's renderings at every budget from 1 to 419 characters,
# each as the repr of its status, detail and text, captured on the renderer before its bounds.
CUT_DIGEST = "5df689925798fef101f1fa722215f5822e56b3ef27ab43b9748c9db0996dc080"
CUT_BUDGETS = range(1, 420)


def test_a_repeated_note_is_written_once_and_marked_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """Five references to one comment: its text once, then its bare marker; the note-once check dropped fails."""
    data = _repeated_comment()
    handed = _handed(monkeypatch)
    rendering = _render(data)
    line = f"see [comment 0: {COMMENT}]" + " [comment 0]" * 4
    assert len(COMMENT) == 40
    assert (rendering.status, rendering.text) == ("ok", line + "\n")
    assert sum(handed) == len(line)
    notes = _no_notes()
    notes.footnotes = {"7": "a footnote"}
    notes.comments = {"7": "a comment"}
    references = '<w:r><w:footnoteReference w:id="7"/><w:commentReference w:id="7"/></w:r>'
    text, _ = _Writer(Builder(LIMITS, input_bytes=1), notes)._inline(parse_xml(f"<w:p {_NS}>{references}</w:p>"))
    assert text == " [footnote 7: a footnote] [comment 7: a comment]"


def test_a_paragraph_stops_collecting_once_it_cannot_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    """500 kept characters past a 200 budget, or 300 bare note markers: one piece past what remains is built; the
    stop dropped, or counting text runs only, fails."""
    document = docx.Document()
    document.add_paragraph("short")
    long = document.add_paragraph()
    for _ in range(50):
        long.add_run("abcdefghij")
    data = _saved(document)
    handed = _handed(monkeypatch)
    rendering = _render(data, RenderLimits(chars=200))
    assert (rendering.status, rendering.detail) == ("truncated", "1 of 2 units within 200 characters")
    assert rendering.text == "short\n\n<!-- truncated: 1 of 2 units -->\n"
    assert sum(handed) <= len("short") + 200 + len("abcdefghij")
    # 193 characters remain after "short" and its blank, so the twentieth run is the one that passes them.
    assert sum(handed) == len("short") + 20 * len("abcdefghij")
    markers = docx.Document()
    paragraph = markers.add_paragraph("x")
    for _ in range(300):
        paragraph._p.append(parse_xml(f'<w:r {_NS}><w:footnoteReference w:id="1"/></w:r>'))
    data = _saved(markers)
    handed.clear()
    _render(data, RenderLimits(chars=200))
    # A note with no text is its bare marker, 11 kept characters, so the nineteenth takes them past 200.
    assert sum(handed) == len("x") + 19 * len(" [footnote 1]")


def test_a_paragraph_at_a_full_budget_is_still_cut() -> None:
    """A body that fills the budget exactly leaves nothing, and a footer opening with a tab still holds text; the
    stop taken when the kept characters only reach what remains drops the footer silently and reports ``ok``."""
    document = docx.Document()
    document.add_paragraph("x" * 9)
    document.sections[0].footer.paragraphs[0].text = "\tabc"
    rendering = _render(_saved(document), RenderLimits(chars=10))
    assert (rendering.status, rendering.detail) == ("truncated", "0 of 1 units within 10 characters")
    assert rendering.text == "xxxxxxxxx\n\n<!-- truncated: 0 of 1 units -->\n"


def test_a_header_part_named_by_many_sections_is_written_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Four sections name one header part: it is walked once; the part set dropped walks it four times."""
    document = docx.Document()
    document.add_paragraph("body")
    header = document.sections[0].header
    header.paragraphs[0].text = "h0"
    for number in range(1, 4):
        header.add_paragraph(f"h{number}")
    for _ in range(3):
        document.add_section()
    reference = document.sections[0]._sectPr.get_headerReference(WD_HEADER_FOOTER.PRIMARY)
    assert reference is not None
    for section in list(document.sections)[1:]:
        section._sectPr.add_headerReference(WD_HEADER_FOOTER.PRIMARY, reference.rId)
    data = _saved(document)
    walks = _walks(monkeypatch)
    rendering = _render(data)
    assert rendering.text == "h0\n\nh1\n\nh2\n\nh3\n\nbody\n"
    assert len(walks) == 8


def test_nothing_is_walked_once_the_budget_is_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cut in the body: the footer's paragraphs are never walked; the stopped return dropped walks them."""
    document = docx.Document()
    for letter in "abc":
        document.add_paragraph(letter * 40)
    footer = document.sections[0].footer
    footer.paragraphs[0].text = "f0"
    footer.add_paragraph("f1")
    footer.add_paragraph("f2")
    data = _saved(document)
    walks = _walks(monkeypatch)
    rendering = _render(data, RenderLimits(chars=60))
    assert (rendering.status, rendering.detail) == ("truncated", "1 of 3 units within 60 characters")
    assert len(walks) == 2


def test_nested_note_elements_are_read_once() -> None:
    """Ten footnote elements nested in one another are one note; notes read at every depth fail."""
    inner = ""
    for number, letter in reversed(list(enumerate("abcdefghij", 1))):
        inner = f'<w:footnote w:id="{number}"><w:p><w:r><w:t>{letter}</w:t></w:r></w:p>{inner}</w:footnote>'
    document = docx.Document()
    part = Part(
        PackURI("/word/footnotes.xml"),
        CONTENT_TYPE.WML_FOOTNOTES,
        f"<w:footnotes {_NS}>{inner}</w:footnotes>".encode(),
        document.part.package,
    )
    document.part.relate_to(part, RELATIONSHIP_TYPE.FOOTNOTES)
    assert _Notes(document).footnotes == {"1": "abcdefghij"}


def test_a_span_never_makes_more_cells_than_the_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """A span of five in a two-column grid adds one copy, and three spans of three on three columns add copies to
    the first alone; copies taken as the declared span, or a row counted in cell elements, fail."""
    document = docx.Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "first"
    table.cell(0, 1).text = "second"
    table._tbl.tr_lst[0].tc_lst[0].grid_span = 5
    data = _saved(document)
    reads = _counted(monkeypatch, CT_P, "text")
    rendering = _render(data)
    assert rendering.text == "| first | first | second |\n| --- | --- | --- |\n"
    assert len(reads) == 2
    spans = docx.Document()
    table = spans.add_table(rows=1, cols=3)
    for column, text in enumerate("abc"):
        table.cell(0, column).text = text
    for tc in table._tbl.tr_lst[0].tc_lst:
        tc.grid_span = 3
    rendering = _render(_saved(spans))
    assert rendering.text == "| a | a | a | b | c |\n| --- | --- | --- | --- | --- |\n"


def test_a_row_of_wide_spans_lays_out_in_proportion_to_its_cells() -> None:
    """200 cell elements each spanning past a 200-column grid lay out the grid plus one cell for each further
    element, 399, where a row counted in cell elements lays out 20,100."""
    width = 200
    cells = "".join(_tc(f"c{number}", span=width + 1) for number in range(width))
    tbl = parse_xml(f"<w:tbl {_NS}><w:tr>{cells}</w:tr></w:tbl>")
    layout = _layout(tbl.tr_lst, width)
    assert sum(copies for row in layout for _, copies in row) == 2 * width - 1


def test_a_vertical_merge_reads_its_text_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eight rows merged down one column: one text read, no walk up the column; a source read per call fails."""
    document = docx.Document()
    table = document.add_table(rows=8, cols=1)
    table.cell(0, 0).text = "root"
    table.cell(0, 0).merge(table.cell(7, 0))
    data = _saved(document)
    reads = _counted(monkeypatch, CT_P, "text")
    above = _counted(monkeypatch, CT_Tc, "_tc_above")
    rendering = _render(data)
    assert rendering.text == "| root |\n| --- |\n" + "| root |\n" * 7
    assert (len(reads), len(above)) == (1, 0)


def test_a_table_stops_drawing_once_the_budget_is_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 40-column span of 20 kept characters under 300: twelve cells are drawn; the in-row stop dropped draws 40."""
    document = docx.Document()
    table = document.add_table(rows=1, cols=40)
    table.cell(0, 0).text = "x" * 20
    table.cell(0, 0).merge(table.cell(0, 39))
    data = _saved(document)
    reads = _counted(monkeypatch, CT_P, "text")
    drawn = _drawn(monkeypatch)
    counts = _kept_lengths(monkeypatch)
    rendering = _render(data, RenderLimits(chars=300))
    assert (rendering.status, rendering.detail) == ("empty", "no text in 1 units")
    assert drawn == [12]
    assert (len(reads), len(counts)) == (1, 1)


def test_a_long_table_stops_reading_rows_once_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty rows under 300 characters: eleven text reads; rows read before they are drawn fail."""
    document = docx.Document()
    document.add_paragraph("short")
    table = document.add_table(rows=20, cols=2)
    table.cell(0, 0).text = "h1"
    table.cell(0, 1).text = "h2"
    for row in range(1, 20):
        table.cell(row, 0).text = f"{row:02d}" + "a" * 18
        table.cell(row, 1).text = f"{row:02d}" + "b" * 18
    data = _saved(document)
    reads = _counted(monkeypatch, CT_P, "text")
    rendering = _render(data, RenderLimits(chars=300))
    body = "".join(f"| {row:02d}{'a' * 18} | {row:02d}{'b' * 18} |\n" for row in range(1, 5))
    assert (rendering.status, rendering.detail) == ("truncated", "1 of 2 units within 300 characters")
    assert rendering.text == f"short\n\n| h1 | h2 |\n| --- | --- |\n{body}\n<!-- truncated: 1 of 2 units -->\n"
    assert len(reads) == 11


def test_ordinary_documents_render_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    """python-docx's own merges render today's text with one read per paragraph of each source."""
    data = _saved(_three_by_three(vertical=True))
    reads = _counted(monkeypatch, CT_P, "text")
    rendering = _render(data)
    assert rendering.text == (
        "| r0c0 r0c1 | r0c0 r0c1 | r0c2 |\n| --- | --- | --- |\n"
        "| r1c0 | r1c1 | r1c2 r2c2 |\n| r2c0 | r2c1 | r1c2 r2c2 |\n"
    )
    assert len(reads) == 9


def test_a_cut_lands_where_it_landed_before(monkeypatch: pytest.MonkeyPatch) -> None:
    """At every budget the mixed document renders as before and as with no stop; counting every character fails."""
    data = _mixed()
    renderings = [_cut_key(_render(data, RenderLimits(chars=budget))) for budget in CUT_BUDGETS]
    digest = hashlib.sha256()
    for key in renderings:
        digest.update(key.encode())
    assert digest.hexdigest() == CUT_DIGEST
    monkeypatch.setattr(Builder, "remaining", property(lambda _: sys.maxsize))
    unbounded = [_cut_key(_render(data, RenderLimits(chars=budget))) for budget in CUT_BUDGETS]
    assert unbounded == renderings


def test_the_docx_generation_names_its_new_revision() -> None:
    version = DocxRenderer().version
    assert version is not None and version.startswith("2+python-docx-")


def test_a_style_is_looked_up_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forty empty paragraphs visit each style element once; a lookup per paragraph, or a name read through
    python-docx's validating accessor, fails."""
    for nameless in (False, True):
        document = docx.Document()
        for _ in range(20):
            document.add_paragraph("")
        header = document.sections[0].header
        for _ in range(19):
            header.add_paragraph("")
        document.add_heading("Section", 2)
        document.add_paragraph("body")
        if nameless:
            document.styles.element.append(parse_xml(_style("Nameless", None)))
        styles = len(document.styles.element.findall(qn("w:style")))
        data = _saved(document)
        with monkeypatch.context() as patch:
            yielded = _yielded(patch)
            rendering = _render(data)
        assert (rendering.status, rendering.text) == ("ok", "## Section\n\nbody\n")
        assert len(yielded) == styles
    quoted = docx.Document()
    quoted.add_paragraph("quoted")._p.style = 'a"b'
    rendering = _render(_saved(quoted))
    assert (rendering.status, rendering.text) == ("ok", "quoted\n")


def test_a_style_reads_as_python_docx_reads_it() -> None:
    """Each case appends styles to the default part and styles one paragraph: the first style of an id wins, an
    id that is empty or names another type falls to the default, the last paragraph default wins, an off or a
    foreign default is no default, a style with no type or no name value is body text, and a default counts with
    no id or an id already seen. A later style of an id taking its place, a default of any type, any value read as
    on, a missing type read as paragraph, or the default read only from styles the id table keeps fails."""
    character = "character"
    kinds = (_style("Kinds", "Heading 2", character), _style("Kinds", "Heading 4"))
    cases: list[tuple[str, tuple[str, ...], str | None, str]] = [
        ("first of an id", (_style("Twice", "Heading 3"), _style("Twice", "Heading 5")), "Twice", "### text\n"),
        ("other type first", kinds, "Kinds", "text\n"),
        ("empty id", (_style("", "Heading 1"),), "", "text\n"),
        ("no id", (_style(None, "Heading 1"),), None, "text\n"),
        ("last default", (_style("Late", "Heading 6", default="1"),), None, "###### text\n"),
        ("true default", (_style("True", "Heading 5", default="true"),), None, "##### text\n"),
        ("on default", (_style("On", "Heading 4", default="on"),), None, "#### text\n"),
        ("off default", (_style("Off", "Heading 2", default="0"),), None, "text\n"),
        ("foreign default", (_style("Run", "Heading 1", character, default="1"),), None, "text\n"),
        ("no type", (_style("Untyped", "Heading 1", None),), "Untyped", "text\n"),
        ("default with no id", (_style(None, "Heading 2", default="1"),), None, "## text\n"),
        ("default of a seen id", (_style("Normal", "Heading 3", default="1"),), None, "### text\n"),
        ("no name value", (_style("Bare", None),), "Bare", "text\n"),
    ]
    for case, styles, style_id, text in cases:
        document = docx.Document()
        for style in styles:
            document.styles.element.append(parse_xml(style))
        paragraph = document.add_paragraph("text")
        if style_id is not None:
            paragraph._p.style = style_id
        rendering = _render(_saved(document))
        assert (rendering.status, rendering.text) == ("ok", text), case


def test_header_paragraphs_read_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The clock past after two reads stops a five-paragraph header after two; the clock read dropped walks five."""
    document = docx.Document()
    header = document.sections[0].header
    header.paragraphs[0].text = "h1"
    for number in range(2, 6):
        header.add_paragraph(f"h{number}")
    document.add_paragraph("body")
    data = _saved(document)
    walks = _walks(monkeypatch)
    clock = _Clock(fresh=2)
    monkeypatch.setattr("vfs.rendering.docx.monotonic", lambda: 0.0)
    monkeypatch.setattr("vfs.deadline.monotonic", lambda: 0.0)
    monkeypatch.setattr("vfs.rendering.markdown.monotonic", clock)
    rendering = _render(data)
    assert (rendering.status, rendering.text) == ("partial", "h1\n\nh2\n")
    assert rendering.detail == "0 of 1 units within 60 seconds"
    assert (len(walks), clock.reads) == (2, 3)


def test_a_table_with_no_grid_keeps_its_columns() -> None:
    """A merged header in a table with no grid, or a grid of no columns, keeps each cell in its column; the fallback
    to the widest row dropped, or taken only when the grid element is missing, moves ``r0c2`` to the second."""
    for whole in (True, False):
        document = _three_by_three(vertical=False)
        tbl = document.tables[0]._tbl
        grid = tbl.find(qn("w:tblGrid"))
        for column in [grid] if whole else grid.findall(qn("w:gridCol")):
            column.getparent().remove(column)
        rendering = _render(_saved(document))
        assert rendering.text == (
            "| r0c0 r0c1 | r0c0 r0c1 | r0c2 |\n| --- | --- | --- |\n| r1c0 | r1c1 | r1c2 |\n| r2c0 | r2c1 | r2c2 |\n"
        ), whole


def test_a_continuation_finds_its_source_by_offset() -> None:
    """Offsets start after a row's late start and count declared spans; a continuation takes the first source at
    its offset in the row directly above, copied by that source's span and passing that span on to the row below,
    or is its own source when nothing starts there. Offsets from zero, from clamped copies, the last source at an
    offset, copies by the continuation's own span, that span passed on, or a source from two rows up fail."""
    passed_on = [_tc("root", span=2) + _tc("p"), _tc("", merged=True) + _tc("q"), _tc("", merged=True)]
    rendering = _render(_rows_table(3, passed_on))
    assert (rendering.status, rendering.text) == (
        "ok",
        "| root | root | p |\n| --- | --- | --- |\n| root | root | q |\n| root | root |  |\n",
    )
    rows = [
        '<w:trPr><w:gridBefore w:val="1"/></w:trPr>' + _tc("x") + _tc("y", merged=True),
        _tc("a") + _tc("", merged=True) + _tc("", merged=True),
        _tc("z", span=0) + _tc("w") + _tc("", merged=True),
        _tc("", merged=True),
        _tc("b", span=2) + _tc("c"),
        _tc("", merged=True) + _tc("d"),
    ]
    rendering = _render(_rows_table(3, rows))
    assert (rendering.status, rendering.text) == (
        "ok",
        "| x | y |  |\n| --- | --- | --- |\n| a | x | y |\n| z | w | x |\n| z |  |  |\n| b | b | c |\n| b | b | d |\n",
    )
    two_up = [
        _tc("top") + _tc("x"),
        '<w:trPr><w:gridBefore w:val="1"/></w:trPr>' + _tc("y"),
        _tc("", merged=True) + _tc("z"),
    ]
    rendering = _render(_rows_table(2, two_up))
    assert (rendering.status, rendering.text) == ("ok", "| top | x |\n| --- | --- |\n| y |  |\n|  | z |\n")


def test_a_malformed_late_start_fails_the_document() -> None:
    """A row whose ``w:gridBefore`` has no value, or one that is not an integer, fails the document as a malformed
    ``w:gridSpan`` does, a classified ``failed`` and never a raise; reading the late start leniently fails."""
    registry = RendererRegistry.bundled()
    for declared, detail in (
        ("<w:gridBefore/>", "docx: InvalidXmlError: required 'w:val' attribute not present"),
        ('<w:gridBefore w:val="x"/>', "docx: ValueError: invalid literal for int()"),
    ):
        data = _rows_table(2, [_tc("a") + _tc("b"), f"<w:trPr>{declared}</w:trPr>" + _tc("c") + _tc("d")])
        rendering = registry.render(RenderSource(data, DOCX, "doc.docx"), LIMITS)
        assert (rendering.status, rendering.text) == ("failed", None), declared
        assert rendering.detail is not None and rendering.detail.startswith(detail), rendering.detail


def test_the_library_has_every_member_the_renderer_reads() -> None:
    """Each python-docx name the renderer reaches past the public API for, so a library that lacks one fails here
    by name rather than rendering every table or style ``failed``."""
    document = docx.Document()
    table = document.add_table(rows=1, cols=1)
    paragraph = document.add_paragraph("text")
    header = document.sections[0].header
    # Read leniently, so a missing styles element or table module is reported by name below.
    styles = getattr(document.styles, "element", None)
    members: list[tuple[str, object, tuple[str, ...]]] = [
        ("Document", document, ("iter_inner_content", "sections", "styles", "part")),
        ("DocumentPart", document.part, ("part_related_by",)),
        ("Styles", document.styles, ("element",)),
        ("CT_Styles", styles, ("_iter_styles",)),
        ("CT_Style", None if styles is None else styles.findall(qn("w:style"))[0], ("styleId",)),
        ("BabelFish", BabelFish, ("internal2ui",)),
        ("docx", docx, ("Document", "table")),
        ("docx.table", getattr(docx, "table", None), ("Table",)),
        ("Table", table, ("_tbl",)),
        ("CT_Tbl", table._tbl, ("tr_lst", "find")),
        ("CT_Row", table._tbl.tr_lst[0], ("grid_before", "tc_lst")),
        ("CT_Tc", table._tbl.tr_lst[0].tc_lst[0], ("grid_span", "vMerge", "p_lst")),
        ("Paragraph", paragraph, ("_p",)),
        ("CT_P", paragraph._p, ("text", "style", "iter")),
        ("_Header", header, ("is_linked_to_previous", "part", "paragraphs")),
        ("_Footer", document.sections[0].footer, ("is_linked_to_previous", "part", "paragraphs")),
        ("Part", Part, ("blob",)),
    ]
    missing = [f"{label}.{name}" for label, owner, names in members for name in names if not hasattr(owner, name)]
    assert missing == []


def test_a_stopped_row_ends_the_draw() -> None:
    """Under a budget of one character the first row stops at its first cell and nothing is drawn after it."""
    cell = "<w:tc><w:p><w:r><w:t>{}</w:t></w:r></w:p></w:tc>"
    row = "<w:tr>" + cell.format("ab") + cell.format("cd") + "</w:tr>"
    tbl = parse_xml(f"<w:tbl {_NS}>{row}{row}</w:tbl>")
    writer = _Writer(Builder(RenderLimits(chars=1), input_bytes=1), _no_notes())
    assert list(writer._rows(_layout(tbl.tr_lst, 2))) == [["ab"]]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Clock:
    """A clock that answers 0.0 for its first *fresh* reads and a time far past any deadline after."""

    def __init__(self, fresh: int) -> None:
        self.fresh = fresh
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return 0.0 if self.reads <= self.fresh else 1e9


def _render(data: bytes, limits: RenderLimits = LIMITS) -> Rendering:
    return DocxRenderer().render(RenderSource(data, DOCX, "doc.docx"), limits)


def _saved(document: Any) -> bytes:
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def _no_notes() -> _Notes:
    notes = _Notes.__new__(_Notes)
    notes.footnotes = {}
    notes.comments = {}
    return notes


def _repeated_comment() -> bytes:
    """One paragraph whose comment's reference run is repeated four more times after it."""
    document = docx.Document()
    paragraph = document.add_paragraph("see")
    document.add_comment(paragraph.runs, text=COMMENT, author="Reviewer")
    reference = paragraph._p.xpath(".//w:commentReference")[0].getparent()
    for _ in range(4):
        paragraph._p.append(deepcopy(reference))
    return _saved(document)


def _three_by_three(*, vertical: bool) -> Any:
    """Cells ``r{row}c{column}``, the first two header cells merged, and with *vertical* the last column's lower two."""
    document = docx.Document()
    table = document.add_table(rows=3, cols=3)
    for row in range(3):
        for column in range(3):
            table.cell(row, column).text = f"r{row}c{column}"
    table.cell(0, 0).merge(table.cell(0, 1))
    if vertical:
        table.cell(1, 2).merge(table.cell(2, 2))
    return document


def _mixed() -> bytes:
    """Headings, whitespace runs, a break and a tab, a marker-like line, pipes and a merged table, on a styles part
    cut to the styles it uses so that four hundred renders stay cheap."""
    document = docx.Document()
    document.add_heading("The Title", 0)
    document.add_heading("A  section", 2)
    paragraph = document.add_paragraph("  spaced   words  ")
    paragraph.add_run("tail").add_break()
    paragraph.add_run("after the break\tand a tab")
    document.add_paragraph("<!-- page 2 -->")
    document.add_paragraph("a | b | c pipes")
    document.add_paragraph("   ")
    table = document.add_table(rows=3, cols=3)
    for row in range(3):
        for column in range(3):
            table.cell(row, column).text = f"r{row}c{column} x|y"
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(1, 2).merge(table.cell(2, 2))
    document.add_heading("Closing", 1)
    document.add_paragraph("the last paragraph of the mixed document")
    styles = document.styles.element
    for style in styles.findall(qn("w:style")):
        if style.get(qn("w:styleId")) not in {"Normal", "Title", "Heading1", "Heading2"}:
            styles.remove(style)
    for latent in styles.findall(qn("w:latentStyles")):
        styles.remove(latent)
    for rid, relationship in list(document.part.rels.items()):
        if relationship.reltype.endswith("/stylesWithEffects"):
            document.part.drop_rel(rid)
    return _saved(document)


def _style(
    style_id: str | None, name: str | None, kind: str | None = "paragraph", *, default: str | None = None
) -> str:
    """One ``w:style`` element's XML: its id, type and default attributes where given, and its name, a ``w:name``
    with no value when *name* is ``None``."""
    attributes = "".join(
        f' w:{attribute}="{value}"'
        for attribute, value in (("type", kind), ("styleId", style_id), ("default", default))
        if value is not None
    )
    named = "<w:name/>" if name is None else f'<w:name w:val="{name}"/>'
    return f"<w:style {_NS}{attributes}>{named}</w:style>"


def _tc(text: str, *, span: int | None = None, merged: bool = False) -> str:
    """One ``w:tc`` element's XML holding *text*, with a declared span and a vertical continuation where given."""
    properties = ("" if span is None else f'<w:gridSpan w:val="{span}"/>') + ("<w:vMerge/>" if merged else "")
    return f"<w:tc><w:tcPr>{properties}</w:tcPr><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"


def _rows_table(columns: int, rows: list[str]) -> bytes:
    """A document of one table on a grid of *columns*, whose rows are the given ``w:tr`` contents."""
    document = docx.Document()
    tbl = document.add_table(rows=0, cols=columns)._tbl
    for row in rows:
        tbl.append(parse_xml(f"<w:tr {_NS}>{row}</w:tr>"))
    return _saved(document)


def _cut_key(rendering: Rendering) -> str:
    return repr((rendering.status, rendering.detail, rendering.text))


def _counted(monkeypatch: pytest.MonkeyPatch, owner: type, name: str) -> list[object]:
    """Each read of the property *name* of *owner* from now on, recorded as the element read."""
    original = getattr(owner, name)
    seen: list[object] = []

    def read(self: object) -> object:
        seen.append(self)
        return original.fget(self)

    monkeypatch.setattr(owner, name, property(read))
    return seen


def _kept_lengths(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every text the docx renderer counts the kept characters of from now on."""
    counted: list[str] = []

    def count(text: str) -> int:
        counted.append(text)
        return kept_length(text)

    monkeypatch.setattr("vfs.rendering.docx.kept_length", count)
    return counted


def _handed(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The length of every text handed to ``Builder.paragraph`` from now on."""
    original = Builder.paragraph
    lengths: list[int] = []

    def paragraph(self: Builder, text: str) -> None:
        lengths.append(len(text))
        original(self, text)

    monkeypatch.setattr(Builder, "paragraph", paragraph)
    return lengths


def _walks(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every paragraph element ``_Writer._inline`` walks from now on."""
    original = _Writer._inline
    walked: list[object] = []

    def inline(self: _Writer, element: Any) -> tuple[str, list[str | None]]:
        walked.append(element)
        return original(self, element)

    monkeypatch.setattr(_Writer, "_inline", inline)
    return walked


def _drawn(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The cell count of every row ``Builder.table`` draws from now on, recorded as it is drawn."""
    original = Builder.table
    widths: list[int] = []

    def table(self: Builder, rows: Iterable[Any], **options: Any) -> bool:
        def drawing() -> Any:
            for row in rows:
                widths.append(len(row))
                yield row

        return original(self, drawing(), **options)

    monkeypatch.setattr(Builder, "table", table)
    return widths


def _yielded(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every style element python-docx's walk of the styles part yields from now on."""
    original = CT_Styles._iter_styles
    seen: list[object] = []

    def iter_styles(self: CT_Styles) -> Any:
        for style in original(self):
            seen.append(style)
            yield style

    monkeypatch.setattr(CT_Styles, "_iter_styles", iter_styles)
    return seen
