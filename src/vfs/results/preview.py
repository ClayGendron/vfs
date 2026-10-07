"""Query-biased previews for ranked hits — the excerpt an agent reads before the file.

A glean hit already carries its chunk text. The preview is cut from that
text alone: one fold of the chunk, a score per line from the query's
terms, the best short window of lines, the terms bolded in Markdown, and
hard caps on characters so a result page stays token-bounded by
construction. No second fetch ever happens here — that is the module's
speed contract, pinned by a test that counts the folds, splits and line
scores rather than the clock.

    >>> select_preview(
    ...     "def parse(stream):\\n    return tokens_from(stream)\\n", 10, ["tokens"]
    ... )
    Preview(text='def parse(stream):\\n    return **tokens**_from(stream)', start=10, end=11, matched=True)

Matching is by substring on the folded line with a whole-word bonus, so
``embed`` bolds ``embedding`` and ``chunk`` bolds ``chunk_index`` — the
superset of what the lexical leg matched, never less. A chunk with no
term in it takes its head window with no spans.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from itertools import pairwise
from math import log2
from typing import TYPE_CHECKING, Final, NamedTuple

from vfs.models.code_grams import fold_content
from vfs.pattern_matching.grep import split_lines

if TYPE_CHECKING:
    from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Display budgets — render-layer constants, never verb parameters
# ---------------------------------------------------------------------------

WINDOW_LINES: Final = 4
"""Lines a preview shows — the best contiguous window of the chunk."""

LINE_CHAR_CAP: Final = 160
"""Source characters kept per preview line; longer lines are trimmed around the first bold span."""

PREVIEW_CHAR_CAP: Final = 480
"""Characters per preview, bold markers included; the first line is always kept."""

BOLD: Final = "**"
"""The Markdown marker around a matched span — spans merge, so markers never nest."""

ELLIPSIS: Final = "…"

_PARTIAL_WORD_FACTOR: Final = 0.5
_EXTRA_OCCURRENCE_BONUS: Final = 0.25
_EXTRA_OCCURRENCE_CAP: Final = 1.0
_RUN_BONUS: Final = 0.5
_COVERAGE_BONUS: Final = 0.5

Span = tuple[int, int]
"""A half-open character range ``(start, end)`` in the original line."""


class Preview(NamedTuple):
    """A rendered excerpt with its absolute, 1-indexed line bounds."""

    text: str
    start: int
    end: int
    matched: bool
    """Whether any query term was found and bolded — ``False`` marks the head-window fallback."""


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select_preview(
    chunk_text: str,
    chunk_line_start: int,
    terms: Sequence[str],
    *,
    window: int = WINDOW_LINES,
    line_cap: int = LINE_CHAR_CAP,
    preview_cap: int = PREVIEW_CHAR_CAP,
) -> Preview:
    """Cut the best *window*-line excerpt of *chunk_text* for *terms*, bolded and capped.

    *chunk_line_start* is the chunk's first line in its file, 1-indexed;
    the returned bounds are absolute file lines and a sub-range of the
    chunk. *terms* are the query's folded terms as the lexical tokenizer
    emits them (folding is repeated here, idempotently, so an unfolded
    term still matches).

    Each line scores Σ over the *distinct* terms it contains of
    ``log2(1 + len(term))`` times (1.0 whole-word | 0.5 substring), plus a
    capped bonus per extra occurrence and a bonus for adjacent distinct
    terms. A window scores the sum of its lines plus a bonus per distinct
    term it covers; the best window wins, the earliest on ties. With no
    term anywhere in the chunk, the head window comes back unbolded.

    Fast by contract: one fold of the chunk, one substring scan per term,
    no I/O — tens of microseconds on a typical chunk. A result page is
    denser than typical by selection (its chunks won on these very terms):
    a 10-entry page of 30 regions costs one to two milliseconds in Python, proportional to
    term occurrences. If that share ever matters, the scan is a crate
    kernel's shape.
    """
    lines = split_lines(chunk_text) if chunk_text else []
    if not lines:
        return Preview("", chunk_line_start, chunk_line_start, False)
    query = _query_terms(terms)
    hits = _score_lines(chunk_text, lines, query) if query else []
    width = min(window, len(lines))
    first = _best_window(hits, width, query) if query else None
    matched = bool(hits) and first is not None
    first = first or 0

    rendered: list[str] = []
    total = 0
    last = first
    for index in range(first, first + width):
        spans = hits[index].spans if matched else ()
        text = _render_line(lines[index], spans, line_cap)
        if rendered and total + len(text) + 1 > preview_cap:
            break
        rendered.append(text)
        total += len(text) + 1
        last = index
    return Preview("\n".join(rendered), chunk_line_start + first, chunk_line_start + last, matched)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Query(NamedTuple):
    """The folded, deduplicated terms, their weights, the adjacency reach, and the any-term gate."""

    terms: tuple[str, ...]
    weights: dict[str, float]
    reach: int
    gate: re.Pattern[str]
    """One alternation of every term — a single C-level search decides whether a line needs scoring."""


class _LineHits(NamedTuple):
    """One line's score, the spans to bold, and the distinct terms it holds."""

    score: float
    spans: tuple[Span, ...]
    terms: frozenset[str]


_NO_HITS: Final = _LineHits(0.0, (), frozenset())


def _query_terms(terms: Sequence[str]) -> _Query | None:
    folded = tuple(dict.fromkeys(fold_content(term) for term in terms if term))
    if not folded:
        return None
    weights = {term: log2(1 + len(term)) for term in folded}
    gate = re.compile("|".join(re.escape(term) for term in folded))
    return _Query(folded, weights, max(len(term) for term in folded) + 2, gate)


def _score_lines(chunk_text: str, lines: list[str], query: _Query) -> list[_LineHits]:
    """Every line's hits, or an empty list when no term occurs anywhere in the chunk.

    The chunk folds once; newlines survive folding, so the folded lines
    align with the originals one for one. Each term is then walked over
    the whole folded chunk in C and its occurrences bucketed by line, so
    the Python work is proportional to occurrences, not lines times terms.
    """
    folded_all = fold_content(chunk_text)
    if query.gate.search(folded_all) is None:
        return []
    folded_lines = split_lines(folded_all)
    starts = [0]
    for folded in folded_lines:
        starts.append(starts[-1] + len(folded) + 1)
    found: dict[int, list[_Occurrence]] = {}
    for term in query.terms:
        at = folded_all.find(term)
        while at >= 0:
            end = at + len(term)
            whole = (at == 0 or not _is_word_char(folded_all[at - 1])) and (
                end >= len(folded_all) or not _is_word_char(folded_all[end])
            )
            index = bisect_right(starts, at) - 1
            found.setdefault(index, []).append(_Occurrence(term, at - starts[index], end - starts[index], whole))
            at = folded_all.find(term, end)
    return [
        _score_line(lines[index], folded_lines[index], found[index], query) if index in found else _NO_HITS
        for index in range(len(lines))
    ]


class _Occurrence(NamedTuple):
    """One term hit inside a line: folded offsets and whether it stands as a whole word."""

    term: str
    start: int
    end: int
    whole: bool


def _score_line(line: str, folded: str, occurrences: list[_Occurrence], query: _Query) -> _LineHits:
    # A fold never drops a character, so an unchanged length means an identity map.
    offsets = None if len(folded) == len(line) else _fold_offsets(line)
    spans = [(hit.start, hit.end) if offsets is None else (offsets[hit.start], offsets[hit.end]) for hit in occurrences]
    counts: dict[str, int] = {}
    best: dict[str, float] = {}
    for hit in occurrences:
        counts[hit.term] = counts.get(hit.term, 0) + 1
        best[hit.term] = max(best.get(hit.term, 0.0), 1.0 if hit.whole else _PARTIAL_WORD_FACTOR)
    score = 0.0
    for term, count in counts.items():
        score += query.weights[term] * best[term]
        score += min(_EXTRA_OCCURRENCE_BONUS * (count - 1), _EXTRA_OCCURRENCE_CAP)
    if len(counts) >= 2:
        positions = sorted(hit.start for hit in occurrences)
        runs = sum(1 for a, b in pairwise(positions) if b - a <= query.reach)
        score += _RUN_BONUS * min(runs, len(counts) - 1)
    return _LineHits(score, _merge_spans(spans), frozenset(counts))


def _fold_offsets(line: str) -> list[int]:
    """``folded index → original index`` for a line whose fold may change length."""
    offsets: list[int] = []
    for index, char in enumerate(line):
        offsets.extend([index] * len(fold_content(char)))
    offsets.append(len(line))
    return offsets


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def _merge_spans(spans: list[Span]) -> tuple[Span, ...]:
    if not spans:
        return ()
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _best_window(hits: list[_LineHits], width: int, query: _Query) -> int | None:
    """The first line of the best-scoring window, or ``None`` when nothing scores.

    The coverage bonus is bounded by the term count, so a window whose
    line sum cannot beat the leader even with every term covered is
    skipped before its term sets are unioned.
    """
    best_first: int | None = None
    best_score = 0.0
    scores = [hit.score for hit in hits]
    ceiling = _COVERAGE_BONUS * len(query.terms)
    for first in range(len(hits) - width + 1):
        score = sum(scores[first : first + width])
        if score <= 0.0 or score + ceiling <= best_score:
            continue
        covered = frozenset().union(*(hit.terms for hit in hits[first : first + width]))
        score += _COVERAGE_BONUS * len(covered)
        if score > best_score:
            best_first, best_score = first, score
    return best_first


def _render_line(line: str, spans: tuple[Span, ...], cap: int) -> str:
    """Bold *spans* in *line*, trimmed to *cap* source characters around the first span.

    Trimming happens on source offsets before the markers go in, so a
    bold span is never cut through and markers always balance.
    """
    low, high = 0, len(line)
    if len(line) > cap:
        first = spans[0][0] if spans else 0
        low = max(0, first - cap // 3) if first > cap // 2 else 0
        high = min(len(line), low + cap)
    pieces: list[str] = [ELLIPSIS] if low > 0 else []
    cursor = low
    for start, end in spans:
        start, end = max(start, low), min(end, high)
        if start >= end:
            continue
        pieces.append(line[cursor:start])
        pieces.append(f"{BOLD}{line[start:end]}{BOLD}")
        cursor = end
    pieces.append(line[cursor:high])
    if high < len(line):
        pieces.append(ELLIPSIS)
    return "".join(pieces)
