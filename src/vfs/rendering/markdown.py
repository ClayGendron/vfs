"""The rendering's Markdown subset, built one line at a time under the limits.

Every construct a renderer emits is line-delimited — ATX headings,
paragraphs, GFM pipe tables one row per line, image placeholders, and
HTML-comment unit markers — so a grep hit always names a whole line
and a chunk boundary never splits a construct. The :class:`Builder`
owns the conventions renderers share: the marker grammar, the table
rules (``|`` escaped, in-cell breaks collapsed, blank cells empty),
the normalisation that keeps line numbers stable across re-renders
(trailing spaces stripped, blank runs collapsed to one, NULs and lone
surrogates removed, one final newline), the character and unit
budgets, the wall clock, and the status the finished rendering
carries.

    started = monotonic()
    pages = parse(data)
    builder = Builder(limits, input_bytes=len(data), total_units=len(pages), started=started)
    for number, page in enumerate(pages, 1):
        if not builder.unit("page", number):
            break
        builder.paragraph(page.text)
    rendering = builder.build()
"""

from __future__ import annotations

import re
from time import monotonic
from typing import TYPE_CHECKING, Final

from vfs.rendering.seam import RENDER_RATIO_FLOOR, Rendering, Unit, bounded_detail, failure, sanitize

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.models.media import RenderStatus
    from vfs.rendering.seam import RenderLimits

# A unit marker and the truncation notice are HTML comment lines: visible
# in grep output, survived by every join, never a control character.
_MARKER_OPEN: Final = "<!-- "
_MARKER_CLOSE: Final = " -->"
# A document line that reads as a marker is escaped, so unit k is always
# the k-th marker of its kind and the unit table rebuilds from the text.
_MARKER_LINE: Final = re.compile(r"^\s*<!--.*-->\s*$")
# Headroom kept out of a budget large enough to carry it, so a cut
# rendering with its notice still fits within ``RenderLimits.chars``.
_NOTICE_RESERVE: Final = 64

_WHITESPACE: Final = re.compile(r"\s+")
_MAX_HEADING_LEVEL: Final = 6


def unit_marker(kind: str, number: int, label: str | None = None) -> str:
    """``<!-- page 3 -->`` or ``<!-- sheet 2: Budget -->`` — one grammar for every unit kind."""
    text = f"{kind} {number}"
    if label is not None and (flat := flatten(label)):
        text = f"{text}: {flat}"
    return _MARKER_OPEN + text.replace("-->", "- ->") + _MARKER_CLOSE


def truncation_marker(done: int, total: int) -> str:
    """The visible last line of a cut rendering."""
    return f"{_MARKER_OPEN}truncated: {done} of {total} units{_MARKER_CLOSE}"


def flatten(text: str) -> str:
    """*text* as one line: every whitespace run one space, NULs and lone surrogates gone, ends trimmed."""
    return _WHITESPACE.sub(" ", sanitize(text)).strip()


def table_cell(value: object) -> str:
    """One pipe-table cell: ``None`` is empty, ``|`` is escaped, breaks collapse to a space."""
    if value is None:
        return ""
    return flatten(str(value)).replace("|", "\\|")


class Builder:
    """One rendering under construction: its lines, its units, its budgets, its verdict.

    Units are opened with :meth:`unit` (a marker line) or :meth:`boundary`
    (no marker, for formats without a unit concept); either answers
    ``False`` once a budget is spent or the wall clock has run out, and
    the renderer stops. A unit counts as complete when the next one
    opens or the build closes it, so the truncation notice counts whole
    units. The character budget is checked on every line, so an
    oversized unit is cut inside itself and nothing renders past the
    budget; the unit cap (``RenderLimits.pages``) applies to marked
    units only, because a markerless format counts body blocks, not
    pages. The clock is checked at unit boundaries and table rows; it
    starts at *started* (the renderer's entry, before parsing) or now.
    """

    def __init__(
        self, limits: RenderLimits, *, input_bytes: int, total_units: int | None = None, started: float | None = None
    ) -> None:
        self._limits = limits
        self._input_bytes = input_bytes
        self._deadline = (monotonic() if started is None else started) + limits.seconds
        reserve = _NOTICE_RESERVE if limits.chars > 4 * _NOTICE_RESERVE else 0
        self._budget = limits.chars - reserve
        self._total_units = total_units
        self._lines: list[str] = []
        self._chars = 0
        self._units: list[Unit] = []
        self._complete = 0
        self._open = False
        self._cut_by: str | None = None
        self._bombed = False
        self._timed_out = False
        self._embedded = 0
        self._dropped = False
        self._has_text = False

    # -- budgets ----------------------------------------------------------

    @property
    def spent(self) -> bool:
        """Whether the character budget is used up."""
        return self._chars >= self._budget

    @property
    def stopped(self) -> bool:
        """Whether a cut or the ratio guard has ended this rendering; nothing more is appended."""
        return self._cut_by is not None or self._bombed

    def out_of_time(self) -> bool:
        """Whether the wall clock has run out; remembered once seen."""
        if not self._timed_out and monotonic() > self._deadline:
            self._timed_out = True
        return self._timed_out

    # -- units --------------------------------------------------------------

    def boundary(self, number: int) -> bool:
        """Open unit *number* with no marker; ``False`` when the renderer must stop."""
        self._close_unit()
        if self.stopped:
            return False
        if self.spent:
            self._cut_by = "characters"
            return False
        if self.out_of_time():
            return False
        self._open = True
        return True

    def unit(self, kind: str, number: int, label: str | None = None, *, hidden: bool = False) -> bool:
        """Open unit *number* of *kind* with its marker line; ``False`` when the renderer must stop."""
        if not self.stopped and number > self._limits.pages:
            self._close_unit()
            self._cut_by = "units"
            return False
        if not self.boundary(number):
            return False
        self._blank()
        unit = Unit(kind, number, label, len(self._lines) + 1, hidden)
        if not self._append(unit_marker(kind, number, label)):
            return False
        self._units.append(unit)
        return True

    # -- constructs -------------------------------------------------------

    def heading(self, level: int, text: str, *, structural: bool = False) -> None:
        """An ATX heading; a *structural* one names a unit (a sheet's title) and is not the document's text."""
        flat = flatten(text)
        if not flat or self.stopped:
            return
        self._blank()
        line = "#" * max(1, min(level, _MAX_HEADING_LEVEL)) + " " + flat
        emitted = self._append(line) if structural else self._text(line)
        if emitted:
            self._blank()

    def paragraph(self, text: str) -> None:
        """*text*'s lines as a paragraph: blank lines inside it collapse, one blank after."""
        emitted = False
        for raw in sanitize(text).splitlines():
            line = raw.rstrip()
            if line.strip():
                if not self._text(line):
                    return
                emitted = True
            elif emitted:
                self._blank()
        if emitted:
            self._blank()

    def table(self, rows: Sequence[Sequence[object]]) -> bool:
        """A GFM pipe table whose first row is the header; ``False`` when cut mid-table."""
        if not rows or self.stopped:
            return not self.stopped
        width = max(len(row) for row in rows)
        self._blank()
        for index, row in enumerate(rows):
            if index and self.out_of_time():
                # Cut inside the unit: it closes incomplete, uncounted.
                self._open = False
                return False
            cells = [table_cell(value) for value in row] + [""] * (width - len(row))
            if not self._text("| " + " | ".join(cells) + " |"):
                return False
            if index == 0 and not self._append("|" + " --- |" * width):
                return False
        self._blank()
        return True

    def image(self, alt: str | None, number: int) -> None:
        """An embedded image's placeholder, or nothing once the embedded budget is spent."""
        if self.stopped:
            return
        if self._embedded >= self._limits.embedded_count:
            self._dropped = True
            return
        self._embedded += 1
        self._blank()
        if self._append(f"![{flatten(alt or '')}](embedded:{number})"):
            self._blank()

    def drop_embedded(self) -> None:
        """Record that an embedded object was left out (a container past the depth limit)."""
        self._dropped = True

    # -- the verdict ----------------------------------------------------------

    def build(self) -> Rendering:
        """Close the rendering: its status, its text (or none), its units, its reason."""
        self._close_unit()
        total = len(self._units) if self._total_units is None else self._total_units
        if self._bombed:
            ratio = self._limits.ratio
            detail = f"{self._chars} output characters exceed {ratio}x the {self._input_bytes}-byte input"
            return failure("failed", detail)
        if not self._has_text:
            return failure("empty", f"no text in {total} units")
        status: RenderStatus = "ok"
        detail: str | None = None
        if self._cut_by == "characters":
            status = "truncated"
            detail = f"{self._complete} of {total} units within {self._limits.chars} characters"
        elif self._cut_by == "units":
            status = "truncated"
            detail = f"{self._complete} of {total} units within the {self._limits.pages}-unit cap"
        elif self._timed_out:
            status = "partial"
            detail = f"{self._complete} of {total} units within {self._limits.seconds:g} seconds"
        elif self._dropped:
            status = "partial"
            detail = f"embedded objects past {self._limits.embedded_count} dropped"
        while self._lines and not self._lines[-1]:
            self._lines.pop()
        if status == "truncated":
            self._lines.extend(("", truncation_marker(self._complete, total)))
        text = "\n".join(self._lines) + "\n"
        return Rendering(status, text, tuple(self._units), None if detail is None else bounded_detail(detail))

    # -- internal -----------------------------------------------------------

    def _close_unit(self) -> None:
        if self._open:
            self._complete += 1
            self._open = False

    def _text(self, line: str) -> bool:
        """A line of the document's own text; a line that reads as a marker is escaped."""
        if _MARKER_LINE.match(line):
            line = "\\" + line.lstrip()
        if not self._append(line):
            return False
        self._has_text = True
        return True

    def _append(self, line: str) -> bool:
        """Append one line within the budget; ``False`` cuts the open unit when it would not fit."""
        if self.stopped:
            return False
        clean = sanitize(line).rstrip()
        if self._chars + len(clean) + 1 > self._budget:
            self._cut_by = "characters"
            self._open = False
            return False
        self._lines.append(clean)
        self._chars += len(clean) + 1
        ratio = self._limits.ratio
        if self._chars > RENDER_RATIO_FLOOR and self._chars > ratio * max(1, self._input_bytes):
            self._bombed = True
        return True

    def _blank(self) -> None:
        if self._lines and self._lines[-1] and not self.stopped and self._chars < self._budget:
            self._lines.append("")
            self._chars += 1
