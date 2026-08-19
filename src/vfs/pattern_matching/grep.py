"""The grep match authority — one shared verifier for every surface.

Match semantics are defined once, in the shared Rust core: a grep
pattern is judged by ``vfs-core``'s regex-crate matcher, and the grep
pattern language is the regex-crate language (ripgrep's). Python ``re``
is not the authority — it serves only the pure-Python fallback engine,
whose rare divergences from the core (case-orbit corners of
``re.IGNORECASE``, spelling gaps like ``\\N{...}``) are the documented
residual of extension-less installs.

Both engines serve one language. A shared gate walks the sre AST and
refuses what the regex crate refuses — backreferences, look-arounds,
atomic groups, possessive quantifiers, conditional groups, the text
anchors ``\\A``/``\\Z``, the ASCII/locale flags — and refuses a pattern
that can only match a line terminator, so an extension-less install
never quietly serves a wider language than a wheel does.

Matching is line-shaped everywhere (*lines are presentation, not
matching*): bodies are scanned whole, each hit's enclosing line is
recovered around it, and ``\\n`` never participates in a match — the
core strips it from classes structurally; the fallback scans whole
bodies only when the walk proves the pattern cannot touch ``\\n``,
else it matches per line. Storage tiers verify their index/scan
candidates through these functions and the router filters chained
rows through the same ones, so the two surfaces cannot drift.

    verifier = compile_verifier("needle", fixed_strings=False,
                                word_regexp=False, case_mode="smart")
    hits = match_texts(texts, verifier, invert=False, before=0,
                       after=0, mode="lines", cap=None)
"""

from __future__ import annotations

import re

# The public sre_parse/sre_constants names are deprecated shims (3.11+); bind
# the live modules directly, matching the planner's convention.
from re import _constants as sre_constants  # ty: ignore[unresolved-import]
from re import _parser as sre_parse  # ty: ignore[unresolved-import]
from time import monotonic
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol

from vfs.models import Match
from vfs.native import extension
from vfs.paths import normalize_ext_channel
from vfs.pattern_matching.glob import PatternError, compile_filter, passes_filters

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import Any

    from vfs.ops import CaseMode, GrepOutputMode
    from vfs.paths import Path

# One hit line: 1-based context bounds, the hit line number, and the
# context block's text (hit line extended before/after, newline-joined).
MatchSpan = tuple[int, int, int, str]

# One candidate body: text, or its UTF-8 bytes fetched straight from
# storage — the two spellings verify identically on both engines.
Body = str | bytes


class ContentMatcher(Protocol):
    """The compiled verifier contract both engines implement.

    Texts go in as plain strings or as their UTF-8 bytes — content is
    valid UTF-8 by construction, so the spellings are interchangeable;
    ``budget`` is wall seconds from call start — bodies not reached in
    time are skipped and the second return reports incomplete. ``cap``
    bounds hit lines per body. Per-body results are exact, except that
    an engine may skip a body it did not reach or leave a partial count
    on the body the budget interrupted — the incomplete flag is the
    only partiality signal; no per-row marker exists.
    """

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]: ...

    def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        budget: float | None,
    ) -> tuple[list[list[MatchSpan]], bool]: ...


class GrepHit(NamedTuple):
    """One matched file: the mode-shaped match facts for its text.

    ``lines`` mode carries ``matches`` regions; ``count`` carries the
    (capped) hit count on ``score``; ``files`` carries neither.
    """

    path: Path
    matches: list[Match] | None
    score: float | None


# Characters both regex languages treat as meta — the fixed-string escape
# set. Deliberately not re.escape, whose extra escapes (space, &, ~, #)
# the regex crate rejects as unrecognized escape sequences.
_FIXED_META: Final = frozenset("\\.^$|?*+()[]{}")

_REFUSED_OPS: Final = {
    sre_constants.ASSERT: "look-around assertions are not supported",
    sre_constants.ASSERT_NOT: "look-around assertions are not supported",
    sre_constants.GROUPREF: "backreferences are not supported",
    sre_constants.GROUPREF_EXISTS: "conditional groups are not supported",
    sre_constants.ATOMIC_GROUP: "atomic groups are not supported",
    sre_constants.POSSESSIVE_REPEAT: "possessive quantifiers are not supported",
}
_REFUSED_ANCHORS: Final = {
    sre_constants.AT_BEGINNING_STRING: r"the text anchor \A is not supported; use ^",
    sre_constants.AT_END_STRING: r"the text anchor \Z is not supported; use $",
}
_LINE_TERMINATOR_MESSAGE: Final = "pattern matches a line terminator"

# Class-shorthand categories whose member set includes the newline.
_NEWLINE_CATEGORIES: Final = frozenset(
    {
        sre_constants.CATEGORY_SPACE,
        sre_constants.CATEGORY_NOT_DIGIT,
        sre_constants.CATEGORY_NOT_WORD,
    }
)

_NEWLINE_CODEPOINT: Final = 0x0A


# ---------------------------------------------------------------------------
# Structural filters — grep's batch form of glob's path gates
# ---------------------------------------------------------------------------


def filter_candidates(
    paths: Sequence[Path],
    *,
    ext: tuple[str, ...] = (),
    ext_not: tuple[str, ...] = (),
    globs: tuple[str, ...] = (),
    globs_not: tuple[str, ...] = (),
) -> list[Path]:
    """The paths that pass grep's structural gates, order preserved.

    Compiles each glob channel once and applies :func:`passes_filters`
    per path — the batch form for callers holding paths rather than
    enumerating storage. Callers gate ``glob_defect`` on the glob
    channels first.
    """
    gates = [compile_filter(glob, ()) for glob in dict.fromkeys(globs)]
    not_gates = [compile_filter(glob, ()) for glob in dict.fromkeys(globs_not)]
    wanted = normalize_ext_channel(ext)
    unwanted = normalize_ext_channel(ext_not)
    return [path for path in paths if passes_filters(path, gates, not_gates, wanted, unwanted)]


# ---------------------------------------------------------------------------
# The line law
# ---------------------------------------------------------------------------


def split_lines(text: str) -> list[str]:
    """Grep's line law: lines break on ``\\n`` only, final terminator dropped.

    ``str.splitlines`` also breaks on ``\\x0b \\x0c \\x1c-\\x1e \\x85``
    and U+2028/29 — bytes grep and ripgrep keep in-line — which would
    skew matches and line numbers against the field tools. The index
    fold normalizes ``\\r`` variants to ``\\n``; here ``\\r`` stays an
    ordinary in-line byte, the same treatment the external tools apply.
    """
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


# ---------------------------------------------------------------------------
# The verifier — compile once, verify per file
# ---------------------------------------------------------------------------


def compile_verifier(pattern: str, *, fixed_strings: bool, word_regexp: bool, case_mode: CaseMode) -> ContentMatcher:
    """The conformance-pinned modifier wrapping, gated, on the live engine.

    Escape (fixed strings), word-wrap, and smart case — judged on the raw
    pattern, any uppercase letter makes the search sensitive, ripgrep's
    rule — then the language gate, then the engine: the shared core where
    the extension serves, the Python ``re`` approximation otherwise.
    Refusals raise :class:`PatternError` with the reason.
    """
    text = _escape_fixed(pattern) if fixed_strings else pattern
    if word_regexp:
        text = rf"\b(?:{text})\b"
    insensitive = case_mode == "insensitive" or (case_mode == "smart" and not any(ch.isupper() for ch in pattern))
    whole_text_safe = _gate(text)
    ext = extension()
    if ext is not None:
        try:
            return _RustMatcher(ext.ContentMatcher(text, insensitive))
        except ValueError as exc:
            # The crate refuses a spelling the walk cannot see (e.g. \N{...}).
            raise PatternError(str(exc)) from exc
    flags = re.IGNORECASE if insensitive else 0
    return _PureMatcher(
        re.compile(text, flags),
        re.compile(text, flags | re.MULTILINE) if whole_text_safe else None,
    )


def verify(
    text: Body,
    verifier: ContentMatcher,
    *,
    invert: bool,
    before: int,
    after: int,
    mode: GrepOutputMode,
    cap: int | None,
) -> tuple[list[Match] | None, float | None] | None:
    """One body's verdict: ``None`` drops the row, else (matches, score).

    ``files`` short-circuits at the first verified hit and carries
    neither matches nor score; ``count`` reports the (capped) hit count
    on score; ``lines`` renders one region per hit line, context bounds
    clamped to the file.
    """
    if mode in ("files", "count"):
        counts, _ = verifier.count_lines([text], cap=1 if mode == "files" else cap, invert=invert, budget=None)
        if not counts[0]:
            return None
        return (None, None) if mode == "files" else (None, float(counts[0]))
    rows, _ = verifier.hit_lines([text], before=before, after=after, cap=cap, invert=invert, budget=None)
    if not rows[0]:
        return None
    return [Match(start=s, end=e, match=m, content=c) for s, e, m, c in rows[0]], None


def match_texts(
    texts: Sequence[tuple[Path, Body]],
    verifier: ContentMatcher,
    *,
    invert: bool,
    before: int,
    after: int,
    mode: GrepOutputMode,
    cap: int | None,
) -> list[GrepHit | None]:
    """Verify each ``(path, text)`` pair; aligned with *texts*, ``None`` per miss.

    The batch form of :func:`verify` for callers holding content rather
    than enumerating storage — one engine call for the whole batch, so
    the core parallelizes across bodies. Alignment (not hits-only) is
    deliberate: duplicate paths with differing texts stay unambiguous.
    """
    bodies = [text for _, text in texts]
    results: list[GrepHit | None] = []
    if mode in ("files", "count"):
        counts, _ = verifier.count_lines(bodies, cap=1 if mode == "files" else cap, invert=invert, budget=None)
        for (path, _), count in zip(texts, counts, strict=True):
            if not count:
                results.append(None)
            else:
                results.append(GrepHit(path, None, float(count) if mode == "count" else None))
        return results
    rows, _ = verifier.hit_lines(bodies, before=before, after=after, cap=cap, invert=invert, budget=None)
    for (path, _), spans in zip(texts, rows, strict=True):
        if not spans:
            results.append(None)
        else:
            results.append(GrepHit(path, [Match(start=s, end=e, match=m, content=c) for s, e, m, c in spans], None))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _as_bytes(body: Body) -> bytes:
    """The core's spelling: bytes pass through, text encodes."""
    return body if isinstance(body, bytes) else body.encode("utf-8", "surrogatepass")


def _as_text(body: Body) -> str:
    """The pure engine's spelling: text passes through, bytes decode."""
    return body if isinstance(body, str) else body.decode("utf-8", "surrogatepass")


def _escape_fixed(text: str) -> str:
    """Escape a fixed string with the meta set both regex languages share."""
    return "".join("\\" + ch if ch in _FIXED_META else ch for ch in text)


def _gate(text: str) -> bool:
    """The language gate: refuse what the regex crate refuses.

    Returns whether whole-text scanning is law-safe for the pure engine —
    true when no construct in the pattern can match ``\\n`` (the core
    needs no such fact: it strips ``\\n`` structurally). Raises
    :class:`PatternError` on refusal; unknown constructs degrade to
    per-line matching, never to acceptance of a wider language.
    """
    try:
        parsed = sre_parse.parse(text)
    except re.error as exc:
        raise PatternError(str(exc)) from exc
    if parsed.state.flags & re.ASCII:
        raise PatternError("the ASCII flag (?a) is not supported")
    return not _walk_newline_capable(parsed)


def _walk_newline_capable(subpattern: Any) -> bool:
    """Refuse out-of-language ops; report whether any atom can match ``\\n``."""
    capable = False
    for op, av in subpattern:
        if op in _REFUSED_OPS:
            raise PatternError(_REFUSED_OPS[op])
        if op is sre_constants.AT:
            if av in _REFUSED_ANCHORS:
                raise PatternError(_REFUSED_ANCHORS[av])
        elif op is sre_constants.LITERAL:
            if av == _NEWLINE_CODEPOINT:
                raise PatternError(_LINE_TERMINATOR_MESSAGE)
        elif op is sre_constants.NOT_LITERAL:
            capable |= av != _NEWLINE_CODEPOINT
        elif op is sre_constants.IN:
            capable |= _class_admits_newline(av)
        elif op is sre_constants.BRANCH:
            for branch in av[1]:
                capable |= _walk_newline_capable(branch)
        elif op is sre_constants.SUBPATTERN:
            # The locale flag needs no twin check: sre itself refuses
            # (?L) on str patterns before the walk ever runs.
            _group, add_flags, _del_flags, sub = av
            if add_flags & re.ASCII:
                raise PatternError("the ASCII flag (?a) is not supported")
            capable |= _walk_newline_capable(sub)
        elif op in (sre_constants.MAX_REPEAT, sre_constants.MIN_REPEAT):
            capable |= _walk_newline_capable(av[2])
    return capable


def _class_admits_newline(items: list[Any]) -> bool:
    """Whether a class can match ``\\n``; refuse a class that matches only it."""
    negated = bool(items) and items[0][0] is sre_constants.NEGATE
    members = items[1:] if negated else items
    admits = False
    only_newline = True
    for op, av in members:
        if op is sre_constants.LITERAL:
            if av == _NEWLINE_CODEPOINT:
                admits = True
            else:
                only_newline = False
        elif op is sre_constants.RANGE:
            lo, hi = av
            if lo <= _NEWLINE_CODEPOINT <= hi:
                admits = True
            if (lo, hi) != (_NEWLINE_CODEPOINT, _NEWLINE_CODEPOINT):
                only_newline = False
        elif op is sre_constants.CATEGORY:
            only_newline = False
            if av in _NEWLINE_CATEGORIES:
                admits = True
        else:  # pragma: no cover - sre emits no other class atoms today
            # Unknown class atom: assume it can match \n (degrades the
            # pure engine to per-line, never widens the language).
            only_newline = False
            admits = True
    if negated:
        return not admits
    if admits and only_newline and members:
        raise PatternError(_LINE_TERMINATOR_MESSAGE)
    return admits


class _RustMatcher:
    """The shared core's matcher: bytes pass through, text encodes at the seam."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        bodies = [_as_bytes(body) for body in texts]
        counts, completed = self._inner.count_lines(bodies, cap=cap, invert=invert, budget=budget)
        return list(counts), completed

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
        bodies = [_as_bytes(body) for body in texts]
        rows, completed = self._inner.hit_lines(
            bodies, before=before, after=after, cap=cap, invert=invert, budget=budget
        )
        decoded = [[(s, e, m, content.decode("utf-8", "surrogatepass")) for s, e, m, content in row] for row in rows]
        return decoded, completed


# Lines per deadline slice on the pure engine: the clock is consulted
# between slices, so one slice's worth of matching is the check's grain.
_SLICE_LINES: Final = 16


def _line_slices(text: str, bounded: bool) -> Iterator[tuple[int, int]]:
    """``(begin, stop)`` offsets on line boundaries, ``_SLICE_LINES`` per slice.

    Unbounded calls get the whole body as one slice — the fast path pays
    nothing. Boundaries land just after ``\\n``, so ``^``/``$`` and word
    boundaries judge identically to an unsliced scan (the language gate
    already refused look-arounds and text anchors).
    """
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
    """The fallback engine: Python ``re`` under the same line law.

    Scans whole bodies (``\\n``-free patterns, ``re.MULTILINE`` keeping
    the per-line anchor law) when the gate proved it safe and the call
    has no context or inversion to shape; otherwise splits and matches
    per line — always correct, the reference shape.

    A budgeted call consults the deadline *within* each body, between
    ``_SLICE_LINES``-line slices: expiry mid-body returns the partial
    hits found so far — a lawful subset — reported incomplete. The
    residual between checks is one slice's matching, and it is a floor,
    not a bound: ``re`` backtracking cannot be interrupted, and its
    cost grows exponentially with line content under a pathological
    pattern — measured for ``(a+)+bcd``: 273 ms for a 16-line slice of
    18-character lines, 65 ms for one 20-character line, doubling per
    two characters from there. A body inside one slice pays that cost
    whole after the single check at body entry. An overrun leaves the
    results exact — the wall is breached, never the answer — and the
    incomplete flag stays a data-completeness signal, not a wall one.

    Before its first deadline consult, a budgeted body also pays linear
    pre-work the clock never sees: the bytes decode (``_as_text``) on
    both paths, and on the split path an eager line split — about 2.4 times
    the body's size in transient residency, measured as a ~7 % overrun
    of the 10 s default wall at 512 MiB. A lazy line iterator alone
    would not close it; the decode is a second linear pass.
    """

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

    def _count_whole(self, text: str, cap: int | None, deadline: float | None) -> tuple[int, bool]:
        assert self._multi_rx is not None
        count = 0
        last_start = -1
        for begin, stop in _line_slices(text, deadline is not None):
            if deadline is not None and begin and monotonic() > deadline:
                return count, False
            for found in self._multi_rx.finditer(text, begin, stop):
                # A zero-width match at the slice end is ``endpos`` posing as
                # end-of-string; the next slice judges it with real context.
                if found.start() == stop and stop < len(text):
                    continue
                start = text.rfind("\n", 0, found.start()) + 1
                if start >= len(text) or start == last_start:
                    continue
                last_start = start
                count += 1
                if cap is not None and count >= cap:
                    return count, True
        return count, True

    def _hits_whole(self, text: str, cap: int | None, deadline: float | None) -> tuple[list[MatchSpan], bool]:
        assert self._multi_rx is not None
        hits: list[MatchSpan] = []
        last_start = -1
        cursor = 0
        line_no = 1
        for begin, stop in _line_slices(text, deadline is not None):
            if deadline is not None and begin and monotonic() > deadline:
                return hits, False
            for found in self._multi_rx.finditer(text, begin, stop):
                # A zero-width match at the slice end is ``endpos`` posing as
                # end-of-string; the next slice judges it with real context.
                if found.start() == stop and stop < len(text):
                    continue
                start = text.rfind("\n", 0, found.start()) + 1
                if start >= len(text) or start == last_start:
                    continue
                last_start = start
                line_no += text.count("\n", cursor, start)
                cursor = start
                end = text.find("\n", found.end())
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
