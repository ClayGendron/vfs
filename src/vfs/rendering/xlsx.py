"""The xlsx renderer: one sheet block per sheet, cell regions as pipe tables, on openpyxl.

Every sheet renders, visible and hidden alike — the text is in the
file and hiding is a view property — with the hidden flag in the unit
table. Within a sheet each contiguous region of non-empty cells (cells
touching by side or corner) is its own table, so a sparse sheet is not
a grid of blanks; regions whose bounding boxes overlap merge into one.
The header row is the Excel column letters and the first column the
1-based row number, so a grep hit reads as a cell address and a sheet
with no header row renders without inventing one. The workbook opens
read-only with computed values; formulas render as their cached
results.

Residency profile, honestly: a sheet's non-empty cells are collected
before its regions are laid out, so one render holds one sheet's cells
at a time — linear in that sheet's cell count, never the workbook's,
and the region pass is linear too. Streaming rows straight into tables
is the direction if a deployment needs a tighter bound.
"""

from __future__ import annotations

from datetime import date, time
from io import BytesIO
from time import monotonic
from typing import TYPE_CHECKING, Any, NamedTuple

from vfs.models.media import XLSX
from vfs.rendering.markdown import Builder
from vfs.rendering.seam import BundledRenderer, Rendering, failure_from

if TYPE_CHECKING:
    from vfs.rendering.seam import RenderLimits, RenderSource

Cells = dict[tuple[int, int], str]


class Box(NamedTuple):
    """One region's bounding box, rows and columns inclusive."""

    top: int
    left: int
    bottom: int
    right: int

    def overlaps(self, other: Box) -> bool:
        return (
            self.top <= other.bottom
            and other.top <= self.bottom
            and self.left <= other.right
            and other.left <= self.right
        )

    def union(self, other: Box) -> Box:
        return Box(
            min(self.top, other.top),
            min(self.left, other.left),
            max(self.bottom, other.bottom),
            max(self.right, other.right),
        )


class XlsxRenderer(BundledRenderer):
    """Sheets to sheet blocks through openpyxl."""

    name = "xlsx"
    extra = "xlsx"
    mimes = (XLSX,)
    package = "openpyxl"
    distribution = "openpyxl"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        openpyxl = self.library
        started = monotonic()
        try:
            workbook = openpyxl.load_workbook(BytesIO(source.data), read_only=True, data_only=True)
        except Exception as exc:  # a file openpyxl cannot open is malformed input, not a surprise
            return failure_from(exc, self.name, "corrupt")
        try:
            sheets = workbook.worksheets
            builder = Builder(limits, input_bytes=len(source.data), total_units=len(sheets), started=started)
            for number, sheet in enumerate(sheets, 1):
                hidden = sheet.sheet_state != "visible"
                if not builder.unit("sheet", number, sheet.title, hidden=hidden):
                    break
                builder.heading(2, sheet.title, structural=True)
                cells = _cells(sheet)
                for box in regions(cells):
                    if not builder.table(_table(cells, box, openpyxl.utils.get_column_letter)):
                        break
        finally:
            workbook.close()
        return builder.build()


# ---------------------------------------------------------------------------
# Regions — contiguous cells, linear in the cell count
# ---------------------------------------------------------------------------


def regions(cells: Cells) -> list[Box]:
    """The bounding boxes of *cells*' contiguous regions, top to bottom then left to right.

    Two cells are contiguous when they touch by side or corner. Each
    connected set of cells is one region; boxes that overlap merge, so
    no cell is rendered twice. Union-find over the cells, so the pass
    is linear in their number.
    """
    parent: dict[tuple[int, int], tuple[int, int]] = {cell: cell for cell in cells}

    def find(cell: tuple[int, int]) -> tuple[int, int]:
        root = cell
        while parent[root] != root:
            root = parent[root]
        while parent[cell] != root:
            parent[cell], cell = root, parent[cell]
        return root

    for row, column in cells:
        for neighbour in ((row, column + 1), (row + 1, column - 1), (row + 1, column), (row + 1, column + 1)):
            if neighbour in parent:
                parent[find(neighbour)] = find((row, column))
    boxes: dict[tuple[int, int], Box] = {}
    for cell in cells:
        root = find(cell)
        row, column = cell
        box = boxes.get(root)
        boxes[root] = Box(row, column, row, column) if box is None else box.union(Box(row, column, row, column))
    return _merged(sorted(boxes.values()))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _merged(boxes: list[Box]) -> list[Box]:
    """*boxes* with every overlapping pair folded into one, in order."""
    out: list[Box] = []
    for box in boxes:
        merged = box
        kept: list[Box] = []
        for other in out:
            if merged.overlaps(other):
                merged = merged.union(other)
            else:
                kept.append(other)
        kept.append(merged)
        out = kept
    return sorted(out)


def _table(cells: Cells, box: Box, column_letter: Any) -> list[list[str]]:
    """One region as table rows: letters across, row numbers down, blanks empty."""
    columns = range(box.left, box.right + 1)
    header = ["", *(column_letter(column) for column in columns)]
    body = [[str(row), *(cells.get((row, column), "") for column in columns)] for row in range(box.top, box.bottom + 1)]
    return [header, *body]


def _cells(sheet: Any) -> Cells:
    """``(row, column) → text`` for every cell of *sheet* that holds a value."""
    cells: Cells = {}
    for row in sheet.iter_rows():
        for cell in row:
            value = cell.value
            if value is None:
                continue
            text = _cell_text(value)
            if text:
                cells[cell.row, cell.column] = text
    return cells


def _cell_text(value: object) -> str:
    """A cell's value as the text a reader would see in the cell."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return f"{value:.15g}"
    if isinstance(value, (date, time)):
        return value.isoformat()
    return str(value)
