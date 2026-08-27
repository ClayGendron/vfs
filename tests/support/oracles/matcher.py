"""The grep matcher's oracle: Python ``re`` under the engine's line law.

Scans whole bodies (``\\n``-free patterns under ``re.MULTILINE``) when
the product's language walk proves it safe and the call has no context
or inversion to shape; otherwise splits and matches per line. A
budgeted call consults the deadline between ``_SLICE_LINES``-line
slices; expiry returns the partial hits found so far, reported
incomplete. ``re`` backtracking cannot be interrupted, so the wall is a
floor on this oracle, never a bound — the engine's linear matcher needs
no such caveat.
"""

from __future__ import annotations

import re
from re import _parser as sre_parse  # ty: ignore[unresolved-import]
from time import monotonic
from typing import TYPE_CHECKING, Final

from vfs.pattern_matching.grep import Body, MatchSpan, _escape_fixed, _gate, _walk_newline_capable, split_lines

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# Lines per deadline slice: the clock is consulted between slices.
_SLICE_LINES: Final = 16


def pure_verifier(pattern: str, *, fixed_strings: bool, word_regexp: bool, case_mode: str) -> _PureMatcher:
    """The product's modifier wrapping and gate, then the oracle matcher."""
    text = _escape_fixed(pattern) if fixed_strings else pattern
    if word_regexp:
        text = rf"\b(?:{text})\b"
    insensitive = case_mode == "insensitive" or (case_mode == "smart" and not any(ch.isupper() for ch in pattern))
    _gate(text)
    whole_text_safe = not _walk_newline_capable(sre_parse.parse(text))
    flags = re.IGNORECASE if insensitive else 0
    return _PureMatcher(
        re.compile(text, flags),
        re.compile(text, flags | re.MULTILINE) if whole_text_safe else None,
    )


def _as_text(body: Body) -> str:
    return body if isinstance(body, str) else body.decode("utf-8", "surrogatepass")


def _line_slices(text: str, bounded: bool) -> Iterator[tuple[int, int]]:
    """``(begin, stop)`` offsets on line boundaries, ``_SLICE_LINES`` per slice; one slice when unbounded."""
    if not bounded:
        yield 0, len(text)
        return
    begin = 0
    while begin < len(text):
        stop = begin
        for _ in range(_SLICE_LINES):
            newline = text.find("\n", stop)
            if newline == -1:
                stop = len(text)
                break
            stop = newline + 1
        yield begin, stop
        begin = stop


class _PureMatcher:
    def __init__(self, line_rx: re.Pattern[str], multi_rx: re.Pattern[str] | None) -> None:
        self._line_rx = line_rx
        self._multi_rx = multi_rx

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        deadline = None if budget is None else monotonic() + budget
        counts: list[int] = []
        for body in texts:
            if deadline is not None and monotonic() > deadline:
                return counts + [0] * (len(texts) - len(counts)), False
            text = _as_text(body)
            if self._multi_rx is not None and not invert:
                count, completed = self._count_whole(text, cap, deadline)
            else:
                count, completed = self._count_split(text, cap, invert, deadline)
            counts.append(count)
            if not completed:
                return counts + [0] * (len(texts) - len(counts)), False
        return counts, True

    def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        budget: float | None,
    ) -> tuple[list[list[MatchSpan]], bool]:
        deadline = None if budget is None else monotonic() + budget
        rows: list[list[MatchSpan]] = []
        for body in texts:
            if deadline is not None and monotonic() > deadline:
                return rows + [[] for _ in range(len(texts) - len(rows))], False
            text = _as_text(body)
            if self._multi_rx is not None and not invert and not before and not after:
                spans, completed = self._hits_whole(text, cap, deadline)
            else:
                spans, completed = self._hits_split(text, before, after, cap, invert, deadline)
            rows.append(spans)
            if not completed:
                return rows + [[] for _ in range(len(texts) - len(rows))], False
        return rows, True

    def _whole_matches(self, text: str, deadline: float | None) -> Iterator[tuple[int, int] | None]:
        """Whole-text hits as ``(line_start, match_end)``, one per hit line; ``None`` on expiry."""
        assert self._multi_rx is not None
        last_start = -1
        expired = False
        for begin, stop in _line_slices(text, deadline is not None):
            if deadline is not None and begin and monotonic() > deadline:
                expired = True
                break
            for found in self._multi_rx.finditer(text, begin, stop):
                # A zero-width match at the slice end is endpos posing as
                # end-of-string; the next slice judges it with real context.
                if found.start() == stop and stop < len(text):
                    continue
                start = text.rfind("\n", 0, found.start()) + 1
                if start >= len(text) or start == last_start:
                    continue
                last_start = start
                yield start, found.end()
        if expired:
            yield None

    def _count_whole(self, text: str, cap: int | None, deadline: float | None) -> tuple[int, bool]:
        count = 0
        for site in self._whole_matches(text, deadline):
            if site is None:
                return count, False
            count += 1
            if cap is not None and count >= cap:
                return count, True
        return count, True

    def _hits_whole(self, text: str, cap: int | None, deadline: float | None) -> tuple[list[MatchSpan], bool]:
        hits: list[MatchSpan] = []
        cursor = 0
        line_no = 1
        for site in self._whole_matches(text, deadline):
            if site is None:
                return hits, False
            start, match_end = site
            line_no += text.count("\n", cursor, start)
            cursor = start
            end = text.find("\n", match_end)
            content = text[start:] if end == -1 else text[start:end]
            hits.append((line_no, line_no, line_no, content))
            if cap is not None and len(hits) >= cap:
                return hits, True
        return hits, True

    def _count_split(self, text: str, cap: int | None, invert: bool, deadline: float | None) -> tuple[int, bool]:
        count = 0
        for index, line in enumerate(split_lines(text)):
            if deadline is not None and index and index % _SLICE_LINES == 0 and monotonic() > deadline:
                return count, False
            if (self._line_rx.search(line) is not None) is not invert:
                count += 1
                if cap is not None and count >= cap:
                    break
        return count, True

    def _hits_split(
        self, text: str, before: int, after: int, cap: int | None, invert: bool, deadline: float | None
    ) -> tuple[list[MatchSpan], bool]:
        lines = split_lines(text)
        hits: list[MatchSpan] = []
        for number, line in enumerate(lines, start=1):
            if deadline is not None and number > 1 and number % _SLICE_LINES == 1 and monotonic() > deadline:
                return hits, False
            if (self._line_rx.search(line) is not None) is not invert:
                start = max(1, number - before)
                end = min(len(lines), number + after)
                hits.append((start, end, number, "\n".join(lines[start - 1 : end])))
                if cap is not None and len(hits) >= cap:
                    break
        return hits, True
