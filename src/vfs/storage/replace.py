"""Text replacement engine — smart edit with exact, line-trimmed, and block-anchor matching."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass
from typing import Final

# Work units one replace call's fuzzy fallback may spend: line comparisons past the
# linear pass, and Levenshtein cells. Exact matching is never charged.
FUZZY_WORK_BUDGET: Final = 4_000_000

# The matches a multi-match failure lists with context; the rest are counted.
_LISTED_MATCHES: Final = 3

BUDGET_REFUSAL: Final = (
    "old_string has no exact match, and the fuzzy fallback reached its work budget. Send the exact text to replace."
)


@dataclass
class Match:
    """Structured match result from a replacer."""

    start: int
    end: int
    text: str
    method: str
    confidence: float


@dataclass
class ReplaceResult:
    """Result of a replace operation."""

    success: bool
    content: str | None = None
    error: str | None = None
    matches: list[Match] | None = None
    method_used: str | None = None


@dataclass(frozen=True)
class _Lines:
    """One content's lines, split once: as written, stripped, and each line's start offset."""

    raw: list[str]
    stripped: list[str]
    starts: list[int]


@dataclass(frozen=True)
class EditOperation:
    """A single find-and-replace edit.

    Multiple ``EditOperation`` objects are applied sequentially — each sees
    the content left by the previous one.
    """

    old: str
    new: str
    replace_all: bool = False


Replacer = Callable[[str, str], Generator[Match]]


def normalize_line_endings(text: str) -> str:
    """Convert Windows line endings to Unix."""
    return text.replace("\r\n", "\n")


def _split_dropping_trailing_blank(text: str) -> list[str]:
    """Split on newlines, dropping the empty line a trailing newline leaves."""
    lines = text.split("\n")
    tail = lines.pop()
    if tail:
        lines.append(tail)
    return lines


def levenshtein(a: str, b: str) -> int:
    """Calculate Levenshtein distance between two strings, keeping two rows of the shorter one."""
    if a == "" or b == "":
        return max(len(a), len(b))
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def get_line_number(content: str, position: int) -> int:
    """Get 1-indexed line number for a position in content."""
    return _line_number(_lines_of(content), position)


def get_context_lines(content: str, start: int, end: int, context: int = 3) -> str:
    """Get matched text with surrounding context lines."""
    return _context(_lines_of(content), start, end, context)


# -----------------------------------------------------------------------------
# The fuzzy work budget
# -----------------------------------------------------------------------------


class FuzzyBudget:
    """The work units one ``replace`` call's fuzzy fallback may still spend.

    A unit is one line comparison beyond the first at each content line,
    or one Levenshtein cell. A block-anchor visit spends before it runs;
    a line-trimmed window is charged the comparisons it made, so a call
    overruns the budget by at most one window.
    """

    def __init__(self, units: int = FUZZY_WORK_BUDGET) -> None:
        self.left = units
        self.exhausted = False

    def spend(self, units: int) -> bool:
        """Take *units* when they fit; otherwise mark the budget exhausted and refuse."""
        if units > self.left:
            self.exhausted = True
            return False
        self.left -= units
        return True


# -----------------------------------------------------------------------------
# Replacers
# -----------------------------------------------------------------------------


def simple_replacer(content: str, find: str) -> Generator[Match]:
    """Exact match replacer."""
    start = 0
    while True:
        index = content.find(find, start)
        if index == -1:
            break
        yield Match(
            start=index,
            end=index + len(find),
            text=find,
            method="exact",
            confidence=1.0,
        )
        start = index + len(find)


def line_trimmed_replacer(content: str, find: str) -> Generator[Match]:
    """Match lines after stripping whitespace from each line."""
    yield from _line_trimmed(_lines_of(content), find, FuzzyBudget())


# Thresholds for BlockAnchorReplacer
SINGLE_CANDIDATE_THRESHOLD = 0.6
MULTIPLE_CANDIDATES_THRESHOLD = 0.3


def block_anchor_replacer(content: str, find: str) -> Generator[Match]:
    """Match blocks using first/last lines as anchors with fuzzy middle matching."""
    yield from _block_anchor(_lines_of(content), find, FuzzyBudget())


# The public replacers in the order `replace` tries its levels; `replace` runs
# the private budgeted forms in this same order.
REPLACERS: list[Replacer] = [
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
]


# -----------------------------------------------------------------------------
# Core Replace Function
# -----------------------------------------------------------------------------


def replace(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    budget: FuzzyBudget | None = None,
) -> ReplaceResult:
    """Replace old_string with new_string in content.

    Uses a three-level matching strategy:
    1. Exact match (confidence: 1.0)
    2. Line-trimmed match - ignores whitespace per line (confidence: 0.9)
    3. Block anchor match - matches first/last lines, fuzzy middle (confidence: 0.3-0.6)

    The two fuzzy levels share one :class:`FuzzyBudget` (a fresh one
    when none is given), which only they spend; a fuzzy level that
    spends it gives no verdict, and the call is refused with the
    exact-match requirement. An exact match is answered whatever the
    budget holds.
    """
    if not old_string:
        return ReplaceResult(
            success=False,
            error="old_string cannot be empty. Use the write tool to create new files.",
        )

    if old_string == new_string:
        return ReplaceResult(
            success=False,
            error="old_string and new_string must be different.",
        )

    content = normalize_line_endings(content)
    old_string = normalize_line_endings(old_string)
    new_string = normalize_line_endings(new_string)
    lines = _lines_of(content)
    spent = budget if budget is not None else FuzzyBudget()
    levels: list[Callable[[], Generator[Match]]] = [
        lambda: simple_replacer(content, old_string),
        lambda: _line_trimmed(lines, old_string, spent),
        lambda: _block_anchor(lines, old_string, spent),
    ]

    for fuzzy, level in enumerate(levels):
        matches = list(level())
        if fuzzy and spent.exhausted:
            return ReplaceResult(success=False, error=BUDGET_REFUSAL)

        if not matches:
            continue

        method = next(iter(matches)).method
        is_exact = method == "exact"

        if replace_all and not is_exact:
            return ReplaceResult(
                success=False,
                error=f"replace_all applies only to exact matches; the match found was fuzzy, by the '{method}' method",
            )

        if replace_all and is_exact:
            new_content = content.replace(old_string, new_string)
            return ReplaceResult(
                success=True,
                content=new_content,
                method_used=method,
                matches=matches,
            )

        if len(matches) == 1:
            [sole] = matches
            new_content = content[: sole.start] + new_string + content[sole.end :]
            return ReplaceResult(
                success=True,
                content=new_content,
                method_used=method,
                matches=[sole],
            )

        match_info = [
            f"Match at line {_line_number(lines, m.start)}:\n{_context(lines, m.start, m.end)}"
            for m in matches[:_LISTED_MATCHES]
        ]
        unlisted = len(matches) - _LISTED_MATCHES
        more = f"\n\n... and {unlisted} more matches" if unlisted > 0 else ""
        return ReplaceResult(
            success=False,
            error=(
                f"Found {len(matches)} matches. "
                "Provide more context in old_string to identify a unique match.\n\n"
                + "\n\n---\n\n".join(match_info)
                + more
            ),
            matches=matches,
        )

    return ReplaceResult(
        success=False,
        error="old_string not found in file content.",
    )


def apply_edits(content: str, edits: Sequence[EditOperation]) -> ReplaceResult:
    """Thread *edits* through :func:`replace` sequentially.

    Each edit sees the content the previous one left — the composition
    ``EditOperation`` promises. The first failure returns unchanged;
    success carries the final content. An empty sequence is a success
    that returns the input.
    """
    for op in edits:
        outcome = replace(content, op.old, op.new, replace_all=op.replace_all)
        if not outcome.success or outcome.content is None:
            return outcome
        content = outcome.content
    return ReplaceResult(success=True, content=content)


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def _lines_of(content: str) -> _Lines:
    raw = content.split("\n")
    starts: list[int] = []
    position = 0
    for line in raw:
        starts.append(position)
        position += len(line) + 1
    return _Lines(raw, [line.strip() for line in raw], starts)


def _line_number(lines: _Lines, position: int) -> int:
    return bisect_right(lines.starts, position)


def _context(lines: _Lines, start: int, end: int, context: int = 3) -> str:
    start_line = _line_number(lines, start) - 1
    end_line = _line_number(lines, end) - 1
    first = max(0, start_line - context)
    last = min(len(lines.raw), end_line + context + 1)
    return "\n".join(
        f"{i + 1:4d} {'>' if start_line <= i <= end_line else ' '} {lines.raw[i]}" for i in range(first, last)
    )


def _span(lines: _Lines, first: int, last: int) -> tuple[int, int, str]:
    """The start, end and text of the lines *first* through *last*."""
    start = lines.starts[first]
    end = lines.starts[last] + len(lines.raw[last])
    return start, end, "\n".join(lines.raw[first : last + 1])


def _line_trimmed(lines: _Lines, find: str, budget: FuzzyBudget) -> Generator[Match]:
    """Windows whose stripped lines equal *find*'s, scanned from each first-line hit."""
    wanted = [line.strip() for line in _split_dropping_trailing_blank(find)]
    if not wanted:
        return
    size = len(wanted)
    stripped = lines.stripped
    for i in range(len(stripped) - size + 1):
        if stripped[i] != wanted[0]:
            continue
        j = 1
        while j < size and stripped[i + j] == wanted[j]:
            j += 1
        if not budget.spend(min(j, size - 1)):
            return
        if j == size:
            start, end, text = _span(lines, i, i + size - 1)
            yield Match(start=start, end=end, text=text, method="line_trimmed", confidence=0.9)


def _block_anchor(lines: _Lines, find: str, budget: FuzzyBudget) -> Generator[Match]:
    """Blocks between a first-anchor line and the next last-anchor line, scored on their middles."""
    wanted = [line.strip() for line in _split_dropping_trailing_blank(find)]
    if len(wanted) < 3:
        return
    stripped = lines.stripped
    last_at = [j for j, line in enumerate(stripped) if line == wanted[-1]]
    candidates: list[tuple[int, int]] = []
    for i, line in enumerate(stripped):
        if line != wanted[0]:
            continue
        k = bisect_left(last_at, i + 2)
        if k < len(last_at):
            candidates.append((i, last_at[k]))
    if not candidates:
        return

    def similarity(first: int, last: int) -> float | None:
        actual = last - first + 1
        checked = min(len(wanted) - 2, actual - 2)
        total = 0.0
        for j in range(1, min(len(wanted) - 1, actual - 1)):
            have, want = stripped[first + j], wanted[j]
            if not budget.spend(len(have) * len(want) + 1):
                return None
            longest = max(len(have), len(want))
            if longest:
                total += 1 - levenshtein(have, want) / longest
        return total / checked

    scored: list[tuple[float, int, int]] = []
    for first, last in candidates:
        score = similarity(first, last)
        if score is None:
            return
        scored.append((score, first, last))
    threshold = SINGLE_CANDIDATE_THRESHOLD if len(scored) == 1 else MULTIPLE_CANDIDATES_THRESHOLD
    best, first, last = max(scored, key=lambda item: item[0])
    if best >= threshold:
        start, end, text = _span(lines, first, last)
        yield Match(start=start, end=end, text=text, method="block_anchor", confidence=best)
