"""The xlsx renderer's work follows the cells a sheet stores and the text it writes: the read, the merge, the tables.

Every count here is of work done (padding cells read, rows walked or
drawn, steps taken, clock reads, cell values converted, positions read,
characters handed to the Builder), never of seconds. Each workbook is
built in process with openpyxl, and a few are then edited as bytes.
"""

from __future__ import annotations

import inspect
import random
import re
import zipfile
from collections import deque
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any

import openpyxl
import pytest
from openpyxl.cell.read_only import EmptyCell
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import CALENDAR_MAC_1904
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from tests.support.documents import xlsx_bytes
from vfs.deadline import CHECK_EVERY
from vfs.models.media import XLSX
from vfs.rendering import RendererRegistry, RenderLimits, RenderSource, markdown, xlsx
from vfs.rendering.markdown import Builder
from vfs.rendering.seam import load_library
from vfs.rendering.xlsx import Box, _cell_text, regions

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

LIMITS = RenderLimits()
REGISTRY = RendererRegistry.bundled()
# A worksheet's inline-string cell as openpyxl writes it (address, optional style, text), and the
# shared-strings part a workbook names such text from instead: its namespace and its content type.
_INLINE_STRING = re.compile(rb'<c r="([A-Z]+[0-9]+)"( s="[0-9]+")? t="inlineStr"><is>(.*?)</is></c>')
_MAIN = b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_SHARED_TYPE = (
    b'<Override PartName="/xl/sharedStrings.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
)


class _Steps:
    """A renderer's step that counts its calls and answers true for the first *allowed*, or for all of them."""

    def __init__(self, allowed: int | None = None) -> None:
        self.calls = 0
        self.allowed = allowed

    def __call__(self) -> bool:
        self.calls += 1
        return self.allowed is None or self.calls <= self.allowed


class _CountedCells(dict[tuple[int, int], str]):
    """A sheet's cells that count every position read through ``get``."""

    reads = 0

    def get(self, key: Any, default: Any = None, /) -> Any:
        self.reads += 1
        return super().get(key, default)


class TestXlsxRegions:
    def test_the_region_pass_and_the_merge_stop_at_their_step(self) -> None:
        """A step that answers false on its fiftieth call stops either pass there: one that ignores it fails. On a
        sheet whose merge probes, reads, collapses, inserts and folds in rounds, a stop on any call, wherever it
        falls, ends the pass on exactly that call: a site that ignores its step, or steps on, fails."""
        cells = _isolated(400)
        step = _Steps(allowed=49)
        assert regions(cells, step) is None
        assert step.calls == 50
        step = _Steps(allowed=49)
        assert xlsx._merged(sorted(Box(row, column, row, column) for row, column in cells), step) is None
        assert step.calls == 50
        draw = random.Random(3)
        mixed = _nested(3) | {(row, column + 20): "v" for row, column in _widening(3)}
        mixed |= {(row + 30, column): "v" for row in range(1, 11) for column in range(1, 11) if draw.random() < 0.3}
        whole = _Steps()
        assert regions(mixed, whole) == _folded(mixed)
        for allowed in range(whole.calls):
            step = _Steps(allowed=allowed)
            assert regions(mixed, step) is None
            assert step.calls == allowed + 1

    def test_the_merge_steps_in_proportion_to_the_cells(self) -> None:
        """Steps a stored cell stay under eight and flat across a doubling on three shapes: a merge that compares
        every pair of boxes, or re-probes every row of a widening region, fails. The exact totals hold every step
        site: a cell in each region pass, and in the merge a box, a probe, and an entry read, collapsed or inserted;
        dropping any one of them changes a total."""
        totals: dict[str, int] = {}
        for shape, small, large in ((_isolated, 400, 800), (_widening, 100, 200), (_nested, 25, 50)):
            rates = []
            for size in (small, large):
                cells = shape(size)
                step = _Steps()
                assert regions(cells, step) is not None
                totals[f"{shape.__name__[1:]} {size}"] = step.calls
                rates.append(step.calls / len(cells))
            assert max(rates) <= 8, (shape.__name__, rates)
            assert rates[1] <= 1.25 * rates[0], (shape.__name__, rates)
        assert totals == {
            "isolated 400": 2_400,
            "isolated 800": 4_800,
            "widening 100": 2_640,
            "widening 200": 5_240,
            "nested 25": 8_528,
            "nested 50": 33_928,
        }

    def test_no_two_tables_share_a_cell(self) -> None:
        """On 2,000 seeded random sheets no two boxes overlap, and each equals a fold of overlapping pairs until none
        is left: a fold that ends after its first round fails."""
        draw = random.Random(7)
        for _ in range(2_000):
            rows, columns, chance = draw.randint(3, 12), draw.randint(3, 12), draw.choice((0.1, 0.2, 0.3))
            cells = {
                (row, column): "v"
                for row in range(1, rows + 1)
                for column in range(1, columns + 1)
                if draw.random() < chance
            }
            boxes = regions(cells)
            assert boxes is not None
            assert not any(a.overlaps(b) for index, a in enumerate(boxes) for b in boxes[index + 1 :]), cells
            assert boxes == _folded(cells), cells
        # Three regions apart, the last folding in rounds whose column probes read lists of two groups: a column's
        # list kept by left edge in place of top edge reads a group above the probe and folds all three into one.
        cells = dict.fromkeys(((3, 3), (11, 3), (12, 2), (14, 2), (15, 3), (16, 1), (16, 3), (17, 1), (18, 2)), "v")
        assert regions(cells) == _folded(cells) == [Box(3, 3, 3, 3), Box(11, 2, 12, 3), Box(14, 1, 18, 3)]


class TestXlsxRead:
    @pytest.mark.parametrize("far", [200, 400])
    def test_a_declared_dimension_pads_nothing(self, monkeypatch: pytest.MonkeyPatch, far: int) -> None:
        """A sheet declaring 26 columns and *far* rows around two cells reads no padding cell and draws no row from
        the library's walk, and steps alike at either height: reading through the public walk fails."""
        data = xlsx_bytes({"S": {"A1": "top", f"A{far}": "far"}}, dimension=f"A1:Z{far}")
        padding, walked = _count_padding(monkeypatch), _count_walk(monkeypatch)
        rendering = _render(data, XLSX)
        assert (padding, walked) == ([0], [0])
        assert rendering.text == (
            "<!-- sheet 1: S -->\n\n## S\n\n|  | A |\n| --- | --- |\n| 1 | top |\n\n"
            f"|  | A |\n| --- | --- |\n| {far} | far |\n"
        )
        steps = _count_steps(monkeypatch)
        _render(data, XLSX)
        assert steps == [16]

    def test_a_far_row_or_column_pads_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cells the writer's own dimension spans far apart read no padding and draw no walked row."""
        wide = get_column_letter(394)
        padding, walked = _count_padding(monkeypatch), _count_walk(monkeypatch)
        tall = _render(xlsx_bytes({"S": {"A1": "top", "A400": "far"}}), XLSX)
        across = _render(xlsx_bytes({"S": {"A1": "top", f"{wide}2": "far"}}), XLSX)
        assert (padding, walked) == ([0], [0])
        head = "<!-- sheet 1: S -->\n\n## S\n\n|  | A |\n| --- | --- |\n| 1 | top |\n\n"
        assert tall.text == head + "|  | A |\n| --- | --- |\n| 400 | far |\n"
        assert across.text == head + f"|  | {wide} |\n| --- | --- |\n| 2 | far |\n"

    def test_cells_outside_a_declared_dimension_render(self) -> None:
        """A cell past a declared one-cell dimension renders under its own address: filtering by it fails."""
        rendering = _render(xlsx_bytes({"S": {"A1": "inside", "C3": "outside"}}, dimension="A1:A1"), XLSX)
        assert rendering.text == (
            "<!-- sheet 1: S -->\n\n## S\n\n|  | A |\n| --- | --- |\n| 1 | inside |\n\n"
            "|  | C |\n| --- | --- |\n| 3 | outside |\n"
        )

    def test_a_malformed_sheet_renders_every_cell_it_stores(self) -> None:
        """A row stored after a higher one, a row element stored twice and one address stored twice all render,
        the first value at an address kept: a read that keeps the last value, or drops rows out of order, fails."""
        cell = '<c r="{}" t="inlineStr"><is><t>{}</t></is></c>'
        rows = (
            f'<row r="3">{cell.format("A3", "three")}</row>'
            f'<row r="1">{cell.format("A1", "first")}{cell.format("A1", "second")}</row>'
            f'<row r="6">{cell.format("C6", "six")}</row>'
            f'<row r="6">{cell.format("E6", "again")}</row>'
        )
        rendering = _render(_sheet_data(xlsx_bytes({"S": {"A1": "x"}}), rows.encode()), XLSX)
        assert rendering.text == (
            "<!-- sheet 1: S -->\n\n## S\n\n|  | A |\n| --- | --- |\n| 1 | first |\n\n"
            "|  | A |\n| --- | --- |\n| 3 | three |\n\n|  | C |\n| --- | --- |\n| 6 | six |\n\n"
            "|  | E |\n| --- | --- |\n| 6 | again |\n"
        )

    def test_the_sheet_read_reads_the_clock_on_the_cadence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With the clock past after three reads, a sheet of 1,000 cells converts 115 of them and renders its marker
        and heading as partial, and a sheet of 1,001 rows draws 127 of them: a read that takes no step fails. A
        clock that runs out in the region pass stops the sheet the same way, and every sheet source the read opened
        is closed, the stopped one included."""
        converted = _count_conversions(monkeypatch)
        sources = _count_sources(monkeypatch)
        data = xlsx_bytes({"S": _dense()})
        _clock(monkeypatch, readings=3)
        rendering = _render(data, XLSX)
        assert converted == [115]
        assert converted[0] <= 2 * CHECK_EVERY
        partial = ("partial", "<!-- sheet 1: S -->\n\n## S\n", "0 of 1 units within 60 seconds")
        assert (rendering.status, rendering.text, rendering.detail) == partial
        # The read takes 1,100 steps; the 19th read of the cadence, at step 1,216, lands in the region pass.
        _clock(monkeypatch, readings=20)
        rendering = _render(data, XLSX)
        assert converted == [115 + 1_000]
        assert (rendering.status, rendering.text, rendering.detail) == partial
        drawn = _count_stored_rows(monkeypatch)
        _clock(monkeypatch, readings=3)
        rendering = _render(_empty_rows(1_000), XLSX)
        assert drawn == [127]
        assert (rendering.status, rendering.text, rendering.detail) == partial
        # Each render opens a sheet's source twice: openpyxl to size the sheet as it loads, and the read.
        assert len(sources) == 6
        assert all(source.closed for source in sources)

    def test_the_stored_cell_read_matches_the_library_walk(self) -> None:
        """For every workbook the xlsx nodes build without a dimension, here and in ``test_renderers.py``, the
        parser's read keeps the public walk's cells."""
        reader = load_library("openpyxl.worksheet._reader")
        for data in _ordinary_workbooks():
            workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
            try:
                for sheet in workbook.worksheets:
                    assert xlsx._cells(xlsx._stored_rows(reader, workbook, sheet), _Steps()) == _walked(sheet)
            finally:
                workbook.close()

    def test_the_library_has_every_member_the_renderer_reads(self) -> None:
        """Each openpyxl name the renderer reaches past the public API for, so a library that lacks one fails here
        by name rather than rendering every workbook ``failed``."""
        data = xlsx_bytes({"Budget": {"A1": "numbat"}})
        workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        reader = load_library("openpyxl.worksheet._reader")
        parser = getattr(reader, "WorkSheetParser", None)
        members: list[tuple[str, object, tuple[str, ...]]] = [
            ("openpyxl", openpyxl, ("load_workbook", "utils")),
            ("openpyxl.utils", getattr(openpyxl, "utils", None), ("get_column_letter",)),
            ("openpyxl.worksheet._reader", reader, ("WorkSheetParser",)),
            ("WorkSheetParser", parser, ("parse",)),
            ("Workbook", workbook, ("worksheets", "data_only", "epoch", "close")),
            ("Workbook", workbook, ("_date_formats", "_timedelta_formats")),
            ("ReadOnlyWorksheet", sheet, ("_get_source", "_shared_strings", "sheet_state", "title")),
        ]
        missing = [f"{label}.{name}" for label, owner, names in members for name in names if not hasattr(owner, name)]
        keywords = () if parser is None else tuple(inspect.signature(parser).parameters)
        expected = ("src", "shared_strings", "data_only", "epoch", "date_formats", "timedelta_formats")
        missing += [f"WorkSheetParser({name})" for name in expected if name not in keywords]
        workbook.close()
        assert missing == []


class TestXlsxTables:
    @pytest.mark.parametrize("n", [100, 200])
    def test_a_region_table_builds_rows_only_while_they_fit(self, monkeypatch: pytest.MonkeyPatch, n: int) -> None:
        """One region of *n* corner-touching cells, an n by n box, reads at most a budget's worth of positions plus
        two rows: a table built whole before the Builder draws a row fails."""
        data = xlsx_bytes({"S": _diagonal(n)})
        counted = _count_cell_reads(monkeypatch)
        rendering = _render(data, XLSX, limits=RenderLimits(chars=4_000))
        reads = sum(cells.reads for cells in counted)
        assert reads <= 4_000 // 3 + 2 * (n + 1), reads
        assert (rendering.status, rendering.detail) == ("truncated", "0 of 1 units within 4000 characters")

    def test_a_row_naming_one_long_string_stops_at_the_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fifty cells naming one 10,000-character string under a 2,000-character budget hand the cell rule at most
        20,000 characters: a body row built whole before its fit test fails. A row after a row that fits stops at
        what that row left: a stop read once a table, or against the whole budget, hands over more."""
        handed = _count_cell_characters(monkeypatch)
        rendering = _render(_shared(xlsx_bytes({"S": _long_row()})), XLSX, limits=RenderLimits(chars=2_000))
        assert handed[0] <= 20_000, handed
        assert handed == [10_075]
        assert (rendering.status, rendering.detail) == ("truncated", "0 of 1 units within 2000 characters")
        handed[0] = 0
        after = {"A1": "a" * 1_000} | {f"{get_column_letter(column)}2": "b" * 100 for column in range(1, 51)}
        rendering = _render(_shared(xlsx_bytes({"S": after})), XLSX, limits=RenderLimits(chars=2_000))
        letters = sum(len(get_column_letter(column)) for column in range(1, 51))
        # The header's letters, row 1 whole, then row 2's number and cells until they pass what row 1 left.
        assert handed == [letters + 1 + 1_000 + 1 + 3 * 100]
        assert (rendering.status, rendering.detail) == ("truncated", "0 of 1 units within 2000 characters")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render(data: bytes, mime: str, name: str = "doc", limits: RenderLimits = LIMITS) -> Any:
    return REGISTRY.render(RenderSource(data, mime, name), limits)


def _isolated(count: int) -> dict[tuple[int, int], str]:
    """*count* cells no two of which touch, twenty to a row, two apart."""
    return {(2 * (index // 20) + 1, 2 * (index % 20) + 1): "v" for index in range(count)}


def _widening(boxes: int) -> dict[tuple[int, int], str]:
    """A tall region three columns wide, and *boxes* two-cell regions below its top, each overlapping the region's
    bounds by one column and widening them by one more, so each folds in alone."""
    height = 3 * boxes + 8
    cells = {(row, 1): "v" for row in range(1, height + 1)} | {(1, 2): "v", (1, 3): "v"}
    for column in range(3, boxes + 3):
        cells[3 * column, column] = "v"
        cells[3 * column + 1, column + 1] = "v"
    return cells


def _nested(count: int) -> dict[tuple[int, int], str]:
    """*count* regions along the bottom and right edges of squares three apart, each enclosing the last."""
    cells: dict[tuple[int, int], str] = {}
    for number in range(1, count + 1):
        side = 3 * number
        cells |= {(side, column): "v" for column in range(1, side + 1)}
        cells |= {(row, side): "v" for row in range(1, side + 1)}
    return cells


def _folded(cells: Mapping[tuple[int, int], str]) -> list[Box]:
    """The reference: regions by breadth-first search over side and corner neighbours, their boxes, and any
    overlapping pair folded until none is left."""
    unseen = set(cells)
    boxes: list[Box] = []
    while unseen:
        start = unseen.pop()
        box = Box(*start, *start)
        queue = deque([start])
        while queue:
            row, column = queue.popleft()
            box = box.union(Box(row, column, row, column))
            for near in ((row + dr, column + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                if near in unseen:
                    unseen.remove(near)
                    queue.append(near)
        boxes.append(box)
    while pair := next(
        ((i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes)) if boxes[i].overlaps(boxes[j])), None
    ):
        i, j = pair
        boxes[i] = boxes[i].union(boxes.pop(j))
    return sorted(boxes)


def _count_padding(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts reads of an empty cell's value, the padding the library's walk hands out, and answers the count."""
    reads = [0]

    def value(_: object) -> None:
        reads[0] += 1

    monkeypatch.setattr(EmptyCell, "value", property(value))
    return reads


def _count_walk(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts the rows the library's read-only walk yields, and answers the count."""
    real = ReadOnlyWorksheet._cells_by_row
    drawn = [0]

    def walk(self: ReadOnlyWorksheet, *args: Any, **kwargs: Any) -> Iterator[Any]:
        for row in real(self, *args, **kwargs):
            drawn[0] += 1
            yield row

    monkeypatch.setattr(ReadOnlyWorksheet, "_cells_by_row", walk)
    return drawn


def _count_steps(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts the calls of ``Builder.step``, and answers the count."""
    real = Builder.step
    calls = [0]

    def step(self: Builder) -> bool:
        calls[0] += 1
        return real(self)

    monkeypatch.setattr(Builder, "step", step)
    return calls


def _count_conversions(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts the cell values the renderer converts to text, and answers the count."""
    real = xlsx._cell_text
    calls = [0]

    def convert(value: object) -> str:
        calls[0] += 1
        return real(value)

    monkeypatch.setattr(xlsx, "_cell_text", convert)
    return calls


def _clock(monkeypatch: pytest.MonkeyPatch, *, readings: int) -> list[int]:
    """The renderer's and the Builder's clock as one counter, ``0.0`` for its first *readings* reads and past the
    render's seconds after, with the container check's clock held at ``0.0``; answers the count of reads."""
    reads = [0]

    def clock() -> float:
        reads[0] += 1
        return 0.0 if reads[0] <= readings else LIMITS.seconds + 1.0

    monkeypatch.setattr("vfs.rendering.xlsx.monotonic", clock)
    monkeypatch.setattr("vfs.rendering.markdown.monotonic", clock)
    monkeypatch.setattr("vfs.deadline.monotonic", lambda: 0.0)
    return reads


def _count_sources(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Records every worksheet source openpyxl opens, and answers the record."""
    real = ReadOnlyWorksheet._get_source
    opened: list[Any] = []

    def source(self: ReadOnlyWorksheet) -> Any:
        opened.append(real(self))
        return opened[-1]

    monkeypatch.setattr(ReadOnlyWorksheet, "_get_source", source)
    return opened


def _dense() -> dict[str, object]:
    """1,000 cells in 100 rows of ten."""
    return {f"{get_column_letter(column)}{row}": "v" for row in range(1, 101) for column in range(1, 11)}


def _empty_rows(count: int) -> bytes:
    """A workbook whose sheet ``S`` stores ``A1`` and then *count* row elements holding no cell."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "S"
    sheet["A1"] = "top"
    for row in range(2, count + 2):
        sheet.row_dimensions[row].height = 20
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()


def _count_stored_rows(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts the rows the renderer draws from the sheet's parser, and answers the count."""
    real = xlsx._stored_rows
    drawn = [0]

    def rows(*args: Any) -> Iterator[Any]:
        for row in real(*args):
            drawn[0] += 1
            yield row

    monkeypatch.setattr(xlsx, "_stored_rows", rows)
    return drawn


def _ordinary_workbooks() -> list[bytes]:
    """Every workbook the xlsx nodes build without a dimension, and one holding a value of every other type."""
    return [
        xlsx_bytes(
            {
                "Budget": {"A1": "Item", "B1": 3.5, "A2": True, "B2": 7, "D5": "far"},
                "Hidden": {"A1": "secret"},
                "Blank": {},
            },
            hidden=["Hidden"],
        ),
        xlsx_bytes({"Sheet": {"A1": ""}}),
        xlsx_bytes({"Big": {f"A{row}": f"value {row}" for row in range(1, 60)}}),
        xlsx_bytes({"S": {"A1": "x", "A2": "y", "E1": "p", "E2": "q"}}),
        xlsx_bytes({"One": {"A1": "first sheet value"}, "Two": {"A1": "second sheet value"}}),
        xlsx_bytes({"One": {"A1": "first"}, "Two": {"A1": "second"}}),
        xlsx_bytes({"Shown": {"A1": "x"}, "Hidden": {"A1": "secret"}}, hidden=["Hidden"]),
        xlsx_bytes({"Typed": {"A1": "Item", "B1": 3.5, "A2": True, "B2": 7, "C3": date(2026, 10, 6)}}),
        xlsx_bytes({"Budget": {"A1": "numbat"}}),
        xlsx_bytes({"S": {"A1": "top", "A400": "far"}}),
        xlsx_bytes({"S": {"A1": "top", f"{get_column_letter(394)}2": "far"}}),
        xlsx_bytes({"S": _dense()}),
        _empty_rows(1_000),
        xlsx_bytes({"S": _diagonal(100)}),
        xlsx_bytes({"S": _long_row()}),
        xlsx_bytes(
            {
                "Values": {
                    "A1": time(9, 30),
                    "A2": datetime.fromisoformat("2026-10-06T12:30"),  # Excel stores no zone
                    "A3": -0.25,
                    "A4": "=1+1",
                    "A5": False,
                    "A6": timedelta(hours=26),
                }
            }
        ),
        _shared(xlsx_bytes({"Shared": {"A1": "one", "B1": "one", "A2": " two ", "B2": "a&b<c>", "C3": "one"}})),
        _mac_epoch(),
    ]


def _mac_epoch() -> bytes:
    """A workbook on the 1904 date system holding a date and a date-time."""
    workbook = openpyxl.Workbook()
    workbook.epoch = CALENDAR_MAC_1904
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"] = date(2026, 10, 6)
    sheet["A2"] = datetime.fromisoformat("2026-10-06T12:30")
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()


def _walked(sheet: Any) -> dict[tuple[int, int], str]:
    """The reference read: the text of every cell the library's public walk yields with a value."""
    cells: dict[tuple[int, int], str] = {}
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None and (text := _cell_text(cell.value)):
                cells[cell.row, cell.column] = text
    return cells


def _diagonal(n: int) -> dict[str, object]:
    """*n* cells each touching the next only at a corner: one region whose box is n by n."""
    return {f"{get_column_letter(index)}{index}": "v" for index in range(1, n + 1)}


def _count_cell_reads(monkeypatch: pytest.MonkeyPatch) -> list[_CountedCells]:
    """Wraps the sheet read so each sheet's cells count the positions read from them, and answers those cells."""
    real = xlsx._cells
    counted: list[_CountedCells] = []

    def read(*args: Any) -> Any:
        cells = real(*args)
        if cells is None:
            return None
        counted.append(_CountedCells(cells))
        return counted[-1]

    monkeypatch.setattr(xlsx, "_cells", read)
    return counted


def _long_row() -> dict[str, object]:
    """Row 1 of fifty cells holding one 10,000-character string."""
    text = "w" * 10_000
    return {f"{get_column_letter(column)}1": text for column in range(1, 51)}


def _count_cell_characters(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Sums the length of the text of every value handed to the Builder's cell rule, and answers the sum."""
    real = markdown.table_cell
    handed = [0]

    def cell(value: object) -> str:
        if value is not None:
            handed[0] += len(str(value))
        return real(value)

    monkeypatch.setattr(markdown, "table_cell", cell)
    return handed


def _shared(data: bytes) -> bytes:
    """*data* with every inline string moved into one shared-strings part, each distinct string stored once and
    named by index from its cells, as Excel itself writes a workbook."""
    strings: dict[bytes, int] = {}

    def share(match: re.Match[bytes]) -> bytes:
        index = strings.setdefault(match[3], len(strings))
        return b'<c r="%s"%s t="s"><v>%d</v></c>' % (match[1], match[2] or b"", index)

    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            body = source.read(info)
            if info.filename.startswith("xl/worksheets/sheet"):
                body = _INLINE_STRING.sub(share, body)
            elif info.filename == "[Content_Types].xml":
                body = body.replace(b"</Types>", _SHARED_TYPE + b"</Types>")
            target.writestr(info.filename, body)
        items = b"".join(b"<si>%s</si>" % text for text in strings)
        table = b'<sst xmlns="%s" count="%d" uniqueCount="%d">%s</sst>' % (_MAIN, len(strings), len(strings), items)
        target.writestr("xl/sharedStrings.xml", table)
    return out.getvalue()


def _sheet_data(data: bytes, rows: bytes) -> bytes:
    """*data* with its first worksheet's stored rows replaced by *rows*, as a hand-written sheet may store them."""
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            body = source.read(info)
            if info.filename == "xl/worksheets/sheet1.xml":
                body, count = re.subn(rb"<sheetData>.*</sheetData>", b"<sheetData>" + rows + b"</sheetData>", body)
                assert count == 1
            target.writestr(info.filename, body)
    return out.getvalue()
