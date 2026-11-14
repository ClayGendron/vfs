"""The four bundled renderers against generated documents: what each format becomes."""

from __future__ import annotations

import binascii
import zipfile
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any

import docx
import openpyxl
import pptx
import pytest
from docx.oxml import parse_xml

from tests.support.documents import (
    declared,
    docx_bytes,
    encrypted_pdf_bytes,
    pdf_bytes,
    pptx_bytes,
    recompressed,
    surrogate_pdf_bytes,
    xlsx_bytes,
)
from vfs.models.media import DOCX, PDF, PPTX, XLSX
from vfs.rendering import RendererRegistry, Rendering, RenderLimits, RenderSource
from vfs.rendering.docx import DocxRenderer, _heading_level, _Notes, _Writer
from vfs.rendering.markdown import Builder
from vfs.rendering.pdf import PdfRenderer
from vfs.rendering.pptx import PptxRenderer
from vfs.rendering.xlsx import Box, XlsxRenderer, _cell_text, regions

LIMITS = RenderLimits()
REGISTRY = RendererRegistry.bundled()
# Each Office format's media type and the library entry point its renderer opens the container with.
OFFICE = {
    "docx": (DOCX, docx, "Document"),
    "pptx": (PPTX, pptx, "Presentation"),
    "xlsx": (XLSX, openpyxl, "load_workbook"),
}


def _render(data: bytes, mime: str, name: str = "doc", limits: RenderLimits = LIMITS) -> Any:
    return REGISTRY.render(RenderSource(data, mime, name), limits)


class TestPdf:
    def test_one_page_block_per_page_with_empty_pages_visible(self) -> None:
        rendering = _render(pdf_bytes(["Hello quokka\nsecond line", None, "third page"]), PDF)
        assert rendering.status == "ok"
        assert rendering.text == (
            "<!-- page 1 -->\nHello quokka\nsecond line\n\n<!-- page 2 -->\n\n<!-- page 3 -->\nthird page\n"
        )
        assert [(u.kind, u.number, u.first_line) for u in rendering.units] == [
            ("page", 1, 1),
            ("page", 2, 5),
            ("page", 3, 7),
        ]

    def test_a_scanned_document_is_empty_not_silent(self) -> None:
        rendering = _render(pdf_bytes([None, None]), PDF)
        assert (rendering.status, rendering.text, rendering.detail) == ("empty", None, "no text in 2 units")

    def test_a_password_is_the_encrypted_state(self) -> None:
        rendering = _render(encrypted_pdf_bytes(["secret text"]), PDF, "locked.pdf")
        assert (rendering.status, rendering.text) == ("encrypted", None)
        assert rendering.detail == "pdf: password-protected, and the empty password does not open it"

    def test_an_empty_user_password_opens(self) -> None:
        rendering = _render(encrypted_pdf_bytes(["open text"], password=""), PDF)
        assert rendering.status == "ok"
        assert rendering.text is not None and "open text" in rendering.text

    def test_garbage_is_corrupt(self) -> None:
        rendering = _render(b"%PDF-1.4 garbage", PDF)
        assert (rendering.status, rendering.text) == ("corrupt", None)
        assert rendering.detail is not None and rendering.detail.startswith("pdf: PdfStreamError")

    def test_the_budget_cuts_at_a_page(self) -> None:
        rendering = PdfRenderer().render(
            RenderSource(pdf_bytes(["a" * 50, "b" * 50, "c" * 50]), PDF, "x"), RenderLimits(chars=80)
        )
        assert rendering.status == "truncated"
        assert rendering.detail == "1 of 3 units within 80 characters"
        assert rendering.text is not None and rendering.text.endswith("<!-- truncated: 1 of 3 units -->\n")


class TestDocx:
    def test_body_order_headings_tables_header_first_footer_last(self) -> None:
        data = docx_bytes(
            ["Body para", "Second"],
            title="The Title",
            headings=[(1, "Section"), (2, "Sub")],
            table=[["h1", "h2"], ["a|b", "line1\nline2"]],
            header="HEADER",
            footer="FOOTER",
        )
        rendering = _render(data, DOCX)
        assert rendering.status == "ok"
        assert rendering.units == ()
        assert rendering.text == (
            "HEADER\n\n# The Title\n\n# Section\n\n## Sub\n\nBody para\n\nSecond\n\n"
            "| h1 | h2 |\n| --- | --- |\n| a\\|b | line1 line2 |\n\nFOOTER\n"
        )

    def test_comments_are_inline_at_their_reference_and_pictures_are_placeholders(self) -> None:
        rendering = _render(docx_bytes(["see note", "end"], comment="a reviewer comment", picture=True), DOCX)
        assert rendering.text == "see note [comment 0: a reviewer comment]\n\nend\n\n![Picture 1](embedded:1)\n"

    def test_footnotes_are_written_at_their_reference(self) -> None:
        # python-docx writes no footnotes, so the reference element is
        # staged directly against the writer with its note table.
        xml = (
            '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:r><w:t>text</w:t><w:tab/><w:t>more</w:t><w:br/><w:footnoteReference w:id="7"/>'
            '<w:footnoteReference w:id="8"/></w:r></w:p>'
        )
        notes = _Notes.__new__(_Notes)
        notes.footnotes = {"7": "the note"}
        notes.comments = {}
        text, pictures = _Writer(Builder(LIMITS, input_bytes=1), notes)._inline(parse_xml(xml))
        assert text == "text\tmore\n [footnote 7: the note] [footnote 8]"
        assert pictures == []

    def test_a_document_without_note_parts_has_none(self) -> None:
        document = docx.Document()
        notes = _Notes(document)
        assert (notes.footnotes, notes.comments) == ({}, {})

    def test_heading_styles_map_to_levels(self) -> None:
        assert _heading_level(None) is None
        assert _heading_level("Title") == 1
        assert _heading_level("Heading 3") == 3
        assert _heading_level("Heading X") is None
        assert _heading_level("Normal") is None

    def test_an_empty_document_is_empty(self) -> None:
        rendering = _render(docx_bytes([]), DOCX)
        assert (rendering.status, rendering.text) == ("empty", None)

    def test_a_bad_zip_is_corrupt(self) -> None:
        rendering = _render(b"PK\x03\x04junk", DOCX)
        assert (rendering.status, rendering.text) == ("corrupt", None)
        assert rendering.detail == "docx: BadZipFile: File is not a zip file"

    def test_the_budget_cuts_in_blocks(self) -> None:
        data = docx_bytes(["a" * 40, "b" * 40, "c" * 40])
        rendering = DocxRenderer().render(RenderSource(data, DOCX, "x"), RenderLimits(chars=60))
        assert rendering.status == "truncated"
        assert rendering.detail == "1 of 3 units within 60 characters"


class TestPptx:
    def test_slides_titles_tables_notes_pictures_and_groups(self) -> None:
        data = pptx_bytes(
            [("Slide T", ["bullet one", "bullet two"]), (None, ["plain box"])],
            notes="speaker notes",
            table=[["c00", "c01"], ["c10", "c11"]],
            picture=True,
            grouped="grouped text",
        )
        rendering = _render(data, PPTX)
        assert rendering.status == "ok"
        assert [(u.kind, u.number) for u in rendering.units] == [("slide", 1), ("slide", 2)]
        assert rendering.text == (
            "<!-- slide 1 -->\n\n## Slide T\n\nbullet one\n\nbullet two\n\n"
            "| c00 | c01 |\n| --- | --- |\n| c10 | c11 |\n\n"
            "![Logo](embedded:1)\n\ngrouped text\n\n### Notes\n\nspeaker notes\n\n"
            "<!-- slide 2 -->\nplain box\n"
        )

    def test_a_deck_without_text_is_empty(self) -> None:
        rendering = _render(pptx_bytes([(None, [""])]), PPTX)
        assert (rendering.status, rendering.text) == ("empty", None)

    def test_a_bad_zip_is_corrupt(self) -> None:
        rendering = _render(b"not a zip", PPTX)
        assert (rendering.status, rendering.text) == ("corrupt", None)
        assert rendering.detail is not None and rendering.detail.startswith("pptx: BadZipFile")

    def test_the_budget_cuts_at_a_slide(self) -> None:
        data = pptx_bytes([(None, ["a" * 60]), (None, ["b" * 60])])
        rendering = PptxRenderer().render(RenderSource(data, PPTX, "x"), RenderLimits(chars=100))
        assert rendering.status == "truncated"
        assert rendering.detail == "1 of 2 units within 100 characters"
        # Cut at the slide boundary itself: the second marker does not fit.
        data = pptx_bytes([(None, ["a" * 20]), (None, ["b" * 20])])
        rendering = PptxRenderer().render(RenderSource(data, PPTX, "x"), RenderLimits(chars=50))
        assert rendering.status == "truncated"
        assert len(rendering.units) == 1


class TestXlsx:
    def test_sheets_regions_addresses_and_the_hidden_flag(self) -> None:
        data = xlsx_bytes(
            {
                "Budget": {"A1": "Item", "B1": 3.5, "A2": True, "B2": 7, "D5": "far"},
                "Hidden": {"A1": "secret"},
                "Blank": {},
            },
            hidden=["Hidden"],
        )
        rendering = _render(data, XLSX)
        assert rendering.status == "ok"
        assert [(u.kind, u.number, u.label, u.hidden) for u in rendering.units] == [
            ("sheet", 1, "Budget", False),
            ("sheet", 2, "Hidden", True),
            ("sheet", 3, "Blank", False),
        ]
        assert rendering.text == (
            "<!-- sheet 1: Budget -->\n\n## Budget\n\n"
            "|  | A | B |\n| --- | --- | --- |\n| 1 | Item | 3.5 |\n| 2 | TRUE | 7 |\n\n"
            "|  | D |\n| --- | --- |\n| 5 | far |\n\n"
            "<!-- sheet 2: Hidden -->\n\n## Hidden\n\n|  | A |\n| --- | --- |\n| 1 | secret |\n\n"
            "<!-- sheet 3: Blank -->\n\n## Blank\n"
        )

    def test_cell_values_render_as_a_reader_sees_them(self) -> None:
        assert _cell_text(True) == "TRUE"
        assert _cell_text(False) == "FALSE"
        assert _cell_text(0.1 + 0.2) == "0.3"
        assert _cell_text(3) == "3"
        assert _cell_text(date(2026, 10, 6)) == "2026-10-06"
        assert _cell_text(datetime(2026, 10, 6, 12, 30, tzinfo=UTC)) == "2026-10-06T12:30:00+00:00"
        assert _cell_text("x") == "x"

    def test_a_workbook_with_no_values_is_empty(self) -> None:
        rendering = _render(xlsx_bytes({"Sheet": {"A1": ""}}), XLSX)
        assert (rendering.status, rendering.text) == ("empty", None)

    def test_a_bad_zip_is_corrupt(self) -> None:
        rendering = _render(b"PK\x03\x04junk", XLSX)
        assert (rendering.status, rendering.text) == ("corrupt", None)
        assert rendering.detail is not None and rendering.detail.startswith("xlsx: BadZipFile")

    def test_an_oversized_sheet_is_cut_inside_its_table(self) -> None:
        data = xlsx_bytes({"Big": {f"A{row}": f"value {row}" for row in range(1, 60)}})
        rendering = XlsxRenderer().render(RenderSource(data, XLSX, "x"), RenderLimits(chars=120))
        assert rendering.status == "truncated"
        assert rendering.detail == "0 of 1 units within 120 characters"

    def test_the_revision_marks_the_changed_output(self) -> None:
        """The renderer's own output changed, so its revision rose and its generation names it: back to 1 fails."""
        assert XlsxRenderer.revision == 2
        version = XlsxRenderer().version
        assert version is not None and version.startswith("2+openpyxl-")


class TestXlsxRegions:
    def test_regions_follow_contiguous_cells_not_row_runs(self) -> None:
        cells = {(1, 1): "a", (2, 1): "b", (1, 5): "p", (2, 5): "q", (4, 3): "lone", (5, 4): "corner"}
        assert regions(cells) == [Box(1, 1, 2, 1), Box(1, 5, 2, 5), Box(4, 3, 5, 4)]

    def test_overlapping_boxes_merge(self) -> None:
        # Two regions whose bounding boxes overlap without touching: one table, no cell twice.
        cells = {(1, 1): "a", (2, 2): "b", (3, 3): "c", (1, 3): "x", (3, 1): "y"}
        cells.pop((2, 2))
        cells.update({(2, 5): "far"})
        boxes = regions({(1, 1): "a", (1, 3): "x", (3, 1): "y", (3, 3): "c", (2, 2): "b", (5, 5): "z", (4, 4): "w"})
        assert boxes == [Box(1, 1, 5, 5)]
        assert regions({}) == []

    def test_side_by_side_regions_render_as_separate_tables(self) -> None:
        rendering = _render(xlsx_bytes({"S": {"A1": "x", "A2": "y", "E1": "p", "E2": "q"}}), XLSX)
        assert rendering.text == (
            "<!-- sheet 1: S -->\n\n## S\n\n"
            "|  | A |\n| --- | --- |\n| 1 | x |\n| 2 | y |\n\n"
            "|  | E |\n| --- | --- |\n| 1 | p |\n| 2 | q |\n"
        )

    def test_the_budget_cuts_at_a_sheet_boundary(self) -> None:
        data = xlsx_bytes({"One": {"A1": "first sheet value"}, "Two": {"A1": "second sheet value"}})
        rendering = XlsxRenderer().render(RenderSource(data, XLSX, "x"), RenderLimits(chars=80))
        assert rendering.status == "truncated"
        assert rendering.detail == "1 of 2 units within 80 characters"
        assert len(rendering.units) == 1
        assert rendering.text is not None and "<!-- sheet 2" not in rendering.text

    def test_a_large_sheet_is_one_region_and_a_sparse_one_many(self) -> None:
        cells = {(row, column): "v" for row in range(1, 4_001) for column in range(1, 7)}
        assert regions(cells) == [Box(1, 1, 4_000, 6)]
        sparse = {(row, 1): "v" for row in range(1, 8_001, 2)}
        boxes = regions(sparse)
        assert boxes is not None and len(boxes) == 4_000

    def test_a_region_inside_another_region_s_box_merges_into_it(self) -> None:
        # A bar with a leg encloses a lone cell it never touches: one table, no cell twice.
        cells = {(1, column): "bar" for column in range(1, 6)} | {(2, 1): "leg", (3, 1): "leg", (3, 4): "lone"}
        assert regions(cells) == [Box(1, 1, 3, 5)]


class TestEmbeddedDepthAndGuards:
    def test_a_group_past_the_depth_limit_is_dropped_as_partial(self) -> None:
        data = pptx_bytes([(None, ["top"])], nested="deep text")
        shallow = PptxRenderer().render(RenderSource(data, PPTX, "x"), RenderLimits(embedded_depth=1))
        assert shallow.status == "partial"
        assert shallow.text is not None and "deep text" not in shallow.text
        assert shallow.detail == "embedded objects past 1000 dropped"
        deep = PptxRenderer().render(RenderSource(data, PPTX, "x"), RenderLimits(embedded_depth=2))
        assert deep.status == "ok"
        assert deep.text is not None and "deep text" in deep.text

    def test_blank_notes_add_no_sub_block(self) -> None:
        rendering = _render(pptx_bytes([(None, ["body"])], blank_notes=True), PPTX)
        assert rendering.text == "<!-- slide 1 -->\nbody\n"

    def test_a_linked_header_is_written_once(self) -> None:
        rendering = _render(docx_bytes(["one"], header="HEADER", footer="FOOTER", second_section=True), DOCX)
        assert rendering.text == "HEADER\n\none\n\nsecond section text\n\nFOOTER\n"

    def test_a_lone_surrogate_from_the_parser_is_replaced(self) -> None:
        rendering = _render(surrogate_pdf_bytes(), PDF)
        assert rendering.status == "ok"
        assert rendering.text == "<!-- page 1 -->\n\ufffd\n"
        rendering.text.encode("utf-8")


class TestContainerCheck:
    @pytest.mark.parametrize("name", ["docx", "pptx", "xlsx"])
    def test_each_office_renderer_refuses_before_its_library_opens(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """A bzip2 container is refused and its library never called: the check's call deleted from that
        renderer hands the container to the library, which opens it. With the render started at 0 and the
        clock just past its seconds the fixture is refused unverified, and at exactly its seconds it is not: a
        renderer passing a deadline that never expires, or one wider than its seconds, renders the first."""
        mime = OFFICE[name][0]
        data = _office(name)
        bzip2 = recompressed(data, zipfile.ZIP_BZIP2)
        opens = _count_opens(monkeypatch, name)
        refused = _render(bzip2, mime)
        assert (refused.status, refused.text) == ("corrupt", None)
        assert refused.detail is not None and refused.detail.startswith(f"{name}: member ")
        assert "uses compression method 12" in refused.detail
        assert opens == []
        assert _render(data, mime).status == "ok"
        assert len(opens) == 1
        monkeypatch.setattr(f"vfs.rendering.{name}.monotonic", lambda: 0.0)
        monkeypatch.setattr("vfs.deadline.monotonic", lambda: LIMITS.seconds + 0.001)
        detail = f"{name}: the container was not verified within {LIMITS.seconds:g} seconds"
        assert _render(data, mime) == Rendering("failed", detail=detail)
        assert len(opens) == 1
        monkeypatch.setattr("vfs.deadline.monotonic", lambda: LIMITS.seconds)
        assert _render(data, mime).detail != detail
        assert len(opens) == 2

    def test_every_office_fixture_renders_as_it_did_without_the_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every fixture option and junk input renders the same with the check replaced by one admitting all."""
        cases = [
            *(
                (data, DOCX)
                for data in (
                    docx_bytes(["Body"], title="The Title"),
                    docx_bytes(["Body"], headings=[(1, "Section"), (2, "Sub")]),
                    docx_bytes(["Body"], table=[["h1", "h2"], ["a", "b"]]),
                    docx_bytes(["Body"], header="HEADER"),
                    docx_bytes(["Body"], footer="FOOTER"),
                    docx_bytes(["see note", "end"], comment="a reviewer comment"),
                    docx_bytes(["Body"], picture=True),
                    docx_bytes(["one"], header="HEADER", footer="FOOTER", second_section=True),
                    docx_bytes([]),
                )
            ),
            *(
                (data, PPTX)
                for data in (
                    pptx_bytes([("Slide T", ["bullet"])], notes="speaker notes"),
                    pptx_bytes([("Slide T", ["bullet"])], table=[["c00", "c01"], ["c10", "c11"]]),
                    pptx_bytes([("Slide T", ["bullet"])], picture=True),
                    pptx_bytes([(None, ["top"])], grouped="grouped text"),
                    pptx_bytes([(None, ["top"])], nested="deep text"),
                    pptx_bytes([(None, ["body"])], blank_notes=True),
                    pptx_bytes([("One", ["first"]), (None, ["plain box"])]),
                    pptx_bytes([(None, [""])]),
                )
            ),
            *(
                (data, XLSX)
                for data in (
                    xlsx_bytes({"One": {"A1": "first"}, "Two": {"A1": "second"}}),
                    xlsx_bytes({"Shown": {"A1": "x"}, "Hidden": {"A1": "secret"}}, hidden=["Hidden"]),
                    xlsx_bytes({"Typed": {"A1": "Item", "B1": 3.5, "A2": True, "B2": 7, "C3": date(2026, 10, 6)}}),
                    xlsx_bytes({"Sheet": {"A1": ""}}),
                )
            ),
            (b"PK\x03\x04junk", DOCX),
            (b"not a zip", PPTX),
            (b"PK\x03\x04junk", XLSX),
        ]
        checked = [_render(data, mime) for data, mime in cases]
        for module in ("docx", "pptx", "xlsx"):
            monkeypatch.setattr(f"vfs.rendering.{module}.container_refusal", _admit_all)
        assert [_render(data, mime) for data, mime in cases] == checked

    @pytest.mark.parametrize("name", ["docx", "pptx", "xlsx"])
    def test_each_office_renderer_refuses_an_overrun_before_its_library_opens(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """The largest member one byte past its declaration, its checksum the cut stream's: the check's call
        deleted from that renderer hands the library the cut member."""
        data = _office(name)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            largest = max(archive.infolist(), key=lambda info: info.file_size)
            stream = archive.read(largest)
        cut = len(stream) - 1
        overrun = declared(data, largest.filename, file_size=cut, crc=binascii.crc32(stream[:cut]))
        opens = _count_opens(monkeypatch, name)
        refused = _render(overrun, OFFICE[name][0])
        assert (refused.status, refused.text) == ("corrupt", None)
        assert refused.detail is not None and refused.detail.startswith(f"{name}: member ")
        assert f"holds more than the {cut} bytes" in refused.detail
        assert opens == []

    @pytest.mark.parametrize("name", ["docx", "pptx", "xlsx"])
    def test_each_office_renderer_measures_against_its_own_byte_limit(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """One byte under the declared total in its own family's limit refuses, in the other's renders: a
        renderer passing the other family's limit fails both."""
        mime = OFFICE[name][0]
        data = _office(name)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
        own, other = ("workbook_bytes", "container_bytes") if name == "xlsx" else ("container_bytes", "workbook_bytes")
        opens = _count_opens(monkeypatch, name)
        refused = _render(data, mime, limits=RenderLimits(**{own: total - 1}))
        detail = f"{name}: the container declares {total} uncompressed bytes, 1 past the {total - 1}-byte limit"
        assert refused == Rendering("failed", detail=detail)
        assert opens == []
        assert _render(data, mime, limits=RenderLimits(**{other: total - 1})).status == "ok"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _office(name: str) -> bytes:
    """The container check's fixture of each Office format."""
    if name == "docx":
        return docx_bytes(["A wombat digs"])
    if name == "pptx":
        return pptx_bytes([("Echidna", ["spines"])])
    return xlsx_bytes({"Budget": {"A1": "numbat"}})


def _count_opens(monkeypatch: pytest.MonkeyPatch, name: str) -> list[object]:
    """Wraps *name*'s library entry point so each call is recorded, and answers the record."""
    _, module, attribute = OFFICE[name]
    real = getattr(module, attribute)
    calls: list[object] = []

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, attribute, counting)
    return calls


def _admit_all(*_: object, **__: object) -> None:
    """A container check that admits every container: the renderers as they were without one."""
    return None
