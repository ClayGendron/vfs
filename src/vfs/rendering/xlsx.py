"""The xlsx renderer: one sheet block per sheet, cell regions as pipe tables, on openpyxl.

Every sheet renders, visible and hidden alike — the text is in the
file and hiding is a view property — with the hidden flag in the unit
table. Within a sheet each contiguous region of non-empty cells (cells
touching by side or corner) is its own table, so a sparse sheet is not
a grid of blanks; regions whose bounding boxes overlap fold into one
until no two overlap, so no cell is in two tables. The header row is
the Excel column letters and the first column the 1-based row number,
so a grep hit reads as a cell address and a sheet with no header row
renders without inventing one. Every stored cell renders at its own
address, whatever extent the sheet declares. The workbook opens
read-only with computed values; formulas render as their cached
results.

Cost profile, as built. A sheet is read through openpyxl's own sheet
parser, so the read costs the rows and cells the sheet stores, never
the extent it declares or the extent its farthest cell addresses,
which the library's public walk pads with empty rows and cells. The
region pass is two union-find passes, linear in the stored non-empty
cells. The merge keeps a row index and a column index of the groups
formed so far, at most two entries a stored cell: a box probes its own
rows, and a fold probes only the rows and columns its bounds gain past
the largest box known to meet no other group, so the merge's work is
of the order of the cells times their logarithm. A table reaches the
Builder one row at a time and a row stops once it cannot fit, so a
table builds at most the character budget over three grid positions,
plus its header and the one row that does not fit. Every loop over a
sheet counts a step, and the render clock is read every 64 steps. One
sheet's stored non-empty cells and the merge's index are held at once;
a region pass that streams rows into tables is the direction if a
deployment needs a tighter bound.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from collections.abc import Callable
from datetime import date, time
from io import BytesIO
from itertools import chain
from time import monotonic
from typing import TYPE_CHECKING, Any, NamedTuple

from vfs.deadline import Deadline
from vfs.models.media import XLSX
from vfs.rendering.markdown import Builder, kept_length
from vfs.rendering.seam import BundledRenderer, Rendering, container_refusal, failure_from, load_library

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from vfs.rendering.seam import RenderLimits, RenderSource

Cells = dict[tuple[int, int], str]
# One item of a walk over a sheet counted; ``False`` when the renderer must stop.
Step = Callable[[], bool]
# A row as the library's sheet parser yields it: its index and the fields of each cell it stores.
StoredRow = tuple[int, list[dict[str, Any]]]


def _unbounded() -> bool:
    """A step that never stops: the default for a caller that runs no render clock."""
    return True


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
    revision = 2

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        openpyxl = self.library
        started = monotonic()
        refused = container_refusal(
            source.data, limits, self.name, Deadline(at=started + limits.seconds), byte_limit=limits.workbook_bytes
        )
        if refused is not None:
            return refused
        try:
            workbook = openpyxl.load_workbook(BytesIO(source.data), read_only=True, data_only=True)
        except Exception as exc:  # a file openpyxl cannot open is malformed input, not a surprise
            return failure_from(exc, self.name, "corrupt")
        try:
            reader = load_library("openpyxl.worksheet._reader")
            assert reader is not None  # the package opened the file; its sheet parser is present
            letter = openpyxl.utils.get_column_letter
            sheets = workbook.worksheets
            builder = Builder(limits, input_bytes=len(source.data), total_units=len(sheets), started=started)
            for number, sheet in enumerate(sheets, 1):
                hidden = sheet.sheet_state != "visible"
                if not builder.unit("sheet", number, sheet.title, hidden=hidden):
                    break
                builder.heading(2, sheet.title, structural=True)
                cells = _cells(_stored_rows(reader, workbook, sheet), builder.step)
                boxes = None if cells is None else regions(cells, builder.step)
                if cells is None or boxes is None:
                    # The clock stopped the read or the region pass: a sheet read in part is not laid out.
                    break
                for box in boxes:
                    if not builder.table(_table(cells, box, letter, builder), width=box.right - box.left + 2):
                        break
        finally:
            workbook.close()
        return builder.build()


# ---------------------------------------------------------------------------
# Regions — contiguous cells, linear in the cell count
# ---------------------------------------------------------------------------


def regions(cells: Cells, step: Step = _unbounded) -> list[Box] | None:
    """The bounding boxes of *cells*' contiguous regions, top to bottom then left to right; ``None`` at a stopped step.

    Two cells are contiguous when they touch by side or corner. Each
    connected set of cells is one region; boxes that overlap fold into
    one until no two overlap, so no cell is rendered in two tables.
    Union-find over the cells takes one step a cell in each of its two
    passes, so the pass is linear in their number; the merge costs what
    :func:`_merged` says. Two passes take no step: building the parent
    table here and collecting the surviving boxes at the merge's end,
    each linear in what it is handed, the cells and the merge's groups,
    with no work an item past a constant.
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
        if not step():
            return None
        for neighbour in ((row, column + 1), (row + 1, column - 1), (row + 1, column), (row + 1, column + 1)):
            if neighbour in parent:
                parent[find(neighbour)] = find((row, column))
    boxes: dict[tuple[int, int], Box] = {}
    for cell in cells:
        if not step():
            return None
        root = find(cell)
        row, column = cell
        box = boxes.get(root)
        boxes[root] = Box(row, column, row, column) if box is None else box.union(Box(row, column, row, column))
    return _merged(sorted(boxes.values()), step)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stored_rows(reader: Any, workbook: Any, sheet: Any) -> Iterator[StoredRow]:
    """The rows *sheet* stores, each its index and its cells' fields, read by openpyxl's own sheet parser.

    The public walk (``iter_rows``) yields a row for every index from 1
    to the extent the sheet declares or its farthest cell addresses, and
    pads each row to that width, so it costs the extent, not the cells.
    The parser yields only the rows and cells the sheet stores, its
    values decoded by the library. It is reached through private names,
    ``openpyxl.worksheet._reader.WorkSheetParser``, the sheet's
    ``_get_source`` and ``_shared_strings``, and the workbook's
    ``_date_formats`` and ``_timedelta_formats``, built as the library's
    own read-only walk builds it. The source closes when the walk ends
    or is abandoned.
    """
    with sheet._get_source() as source:
        parser = reader.WorkSheetParser(
            source,
            sheet._shared_strings,
            data_only=workbook.data_only,
            epoch=workbook.epoch,
            date_formats=workbook._date_formats,
            timedelta_formats=workbook._timedelta_formats,
        )
        yield from parser.parse()


def _cells(rows: Iterable[StoredRow], step: Step) -> Cells | None:
    """``(row, column) → text`` for every stored cell holding a value, the first at an address kept.

    One step a stored row and one a stored cell; ``None`` at a stopped
    step, so a sheet read in part is never laid out.
    """
    cells: Cells = {}
    for _, stored in rows:
        if not step():
            return None
        for cell in stored:
            if not step():
                return None
            value = cell["value"]
            if value is None:
                continue
            text = _cell_text(value)
            if text:
                cells.setdefault((cell["row"], cell["column"]), text)
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


def _extent(box: Box) -> int:
    """Rows plus columns of *box*, less two."""
    return box.bottom - box.top + box.right - box.left


class _Probe(NamedTuple):
    """One lookup of one row's or one column's list, over the span from *low* to *high* across it."""

    lines: dict[int, list[_Group]]
    line: int
    low: int
    high: int


class _Group:
    """Region boxes folded into one, with the box that bounds them; a member points at its root."""

    __slots__ = ("bottom", "left", "parent", "right", "top")

    top: int
    left: int
    bottom: int
    right: int
    parent: _Group

    def __init__(self, box: Box) -> None:
        self.top, self.left, self.bottom, self.right = box
        self.parent = self

    def box(self) -> Box:
        return Box(self.top, self.left, self.bottom, self.right)

    def size(self) -> int:
        """Rows plus columns of the group's box: the measure a fold keeps its largest group by."""
        return _extent(self.box())


class _Index:
    """The groups formed so far, listed under every row and every column their members' own boxes span.

    A row's list is ordered by its groups' left edges and a column's by
    their top edges. The groups are pairwise apart, so that order is
    also the order of their far edges, which a probe bisects; a group's
    edges are read through its root, and no root's bounds change while
    a fold runs, so every list stays ordered.
    """

    __slots__ = ("columns", "rows")

    def __init__(self) -> None:
        self.rows: dict[int, list[_Group]] = {}
        self.columns: dict[int, list[_Group]] = {}

    @staticmethod
    def find(group: _Group) -> _Group:
        """*group*'s root, halving the path to it."""
        while group.parent is not group:
            group.parent = group.parent.parent
            group = group.parent
        return group

    def meet(
        self, lines: dict[int, list[_Group]], line: int, low: int, high: int, found: set[_Group], step: Step
    ) -> list[_Group] | None:
        """The roots not in *found* that *line*'s list holds from *low* to *high*; ``None`` at a stopped step.

        One probe: a step, one bisection to the first group whose far
        edge reaches *low*, then a step for each entry read while its
        near edge is at most *high*. A run of entries naming one root is
        collapsed to one entry as it is read, a step before each delete.
        """
        if not step():
            return None
        met: list[_Group] = []
        entries = lines.get(line)
        if entries is None:
            return met
        near, far = ("left", "right") if lines is self.rows else ("top", "bottom")
        index = bisect_left(entries, low, key=lambda group: getattr(self.find(group), far))
        previous = None
        while index < len(entries):
            root = self.find(entries[index])
            if getattr(root, near) > high:
                break
            if not step():
                return None
            if root is previous:
                del entries[index]
                continue
            previous = root
            if root not in found:
                met.append(root)
            index += 1
        return met

    def add(self, group: _Group, box: Box, step: Step) -> bool:
        """List *group* under each row and each column of *box*, a step before each; ``False`` at a stopped step."""
        for row in range(box.top, box.bottom + 1):
            if not step():
                return False
            insort(self.rows.setdefault(row, []), group, key=lambda member: self.find(member).left)
        for column in range(box.left, box.right + 1):
            if not step():
                return False
            insort(self.columns.setdefault(column, []), group, key=lambda member: self.find(member).top)
        return True


def _merged(boxes: list[Box], step: Step) -> list[Box] | None:
    """*boxes*, given top then left, folded until no two overlap and sorted; ``None`` at a stopped step.

    Each box probes its own rows over its own columns. A box that meets
    no group is indexed as a group of its own; otherwise it folds in
    rounds. A round's bounds grow to cover the groups the last round
    met, and it probes only the rows and columns those bounds gain past
    the largest box known to meet no other group: the bounds before the
    round, or a group the last round met. A round that meets nothing
    ends the fold, and the box and every group it met join the largest
    of them. The index holds at most two entries a stored cell, each
    inserted once; a fold's probes come to the rows and columns its
    bounds gain past its first such box, and its entries read add the
    groups met again in later rounds. The work is of the order of the
    cells times their logarithm, with a step on each box, probe, entry
    read, entry collapsed and entry inserted.
    """
    index = _Index()
    groups: list[_Group] = []
    for box in boxes:
        if not step():
            return None
        found: set[_Group] = set()
        met: list[_Group] = []
        bounds = box
        rows = range(box.top, box.bottom + 1)
        probes: Iterable[_Probe] = (_Probe(index.rows, row, box.left, box.right) for row in rows)
        while True:
            fresh: list[_Group] = []
            for lines, line, low, high in probes:
                new = index.meet(lines, line, low, high, found, step)
                if new is None:
                    return None
                found.update(new)
                fresh += new
            if not fresh:
                break
            clear = max((bounds, *(group.box() for group in fresh)), key=_extent)
            for group in fresh:
                bounds = bounds.union(group.box())
            met += fresh
            probes = _delta(index, bounds, clear)
        node = _Group(box)
        if met:
            survivor = max(met, key=_Group.size)
            for group in met:
                group.parent = survivor
            survivor.top, survivor.left, survivor.bottom, survivor.right = bounds
            node.parent = survivor
        else:
            groups.append(node)
        if not index.add(node, box, step):
            return None
    return sorted(group.box() for group in groups if group.parent is group)


def _delta(index: _Index, bounds: Box, clear: Box) -> Iterator[_Probe]:
    """The probes of *bounds* outside *clear*: its rows outside clear's rows across its columns, then its columns
    outside clear's columns across clear's rows."""
    for row in chain(range(bounds.top, clear.top), range(clear.bottom + 1, bounds.bottom + 1)):
        yield _Probe(index.rows, row, bounds.left, bounds.right)
    for column in chain(range(bounds.left, clear.left), range(clear.right + 1, bounds.right + 1)):
        yield _Probe(index.columns, column, clear.top, clear.bottom)


def _table(cells: Cells, box: Box, column_letter: Any, builder: Builder) -> Iterator[list[str]]:
    """One region as table rows, each built when the Builder draws it: letters across, row numbers down.

    A body row stops once its cells' kept characters pass what the
    budget has left as the row starts, since such a row cannot fit and
    the Builder refuses it whole or stopped alike; so a table builds at
    most the budget over three grid positions, plus its header and the
    one row that does not fit.
    """
    columns = range(box.left, box.right + 1)
    yield ["", *(column_letter(column) for column in columns)]
    for row in range(box.top, box.bottom + 1):
        remaining = builder.remaining
        line = [str(row)]
        kept = 0
        for column in columns:
            text = cells.get((row, column), "")
            line.append(text)
            kept += kept_length(text)
            if kept > remaining:
                break
        yield line
