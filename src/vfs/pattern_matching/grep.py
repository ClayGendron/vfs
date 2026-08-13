"""The grep match authority — one compiled verifier for every surface.

Python ``re`` is the sole authority on what a grep pattern matches:
storage tiers verify their index/scan candidates through these
functions, and the router filters chained rows through the same ones,
so the two surfaces cannot drift. The posture mirrors
:mod:`vfs.pattern_matching.glob` for path patterns: prefilters elsewhere are
necessary facts; matching is decided here. Everything works on plain
paths and text, never on result rows.

    candidates = filter_candidates(paths, ext=("py",), ext_not=(),
                                   globs=("src/**",), globs_not=())
    verifier = compile_verifier("needle", fixed_strings=False,
                                word_regexp=False, case_mode="smart")
    hits = match_texts(texts, verifier, invert=False, before=0,
                       after=0, mode="lines", cap=None)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from vfs.models import Match
from vfs.paths import normalize_ext_channel
from vfs.pattern_matching.glob import compile_filter, passes_filters

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.ops import CaseMode, GrepOutputMode
    from vfs.paths import Path


class GrepHit(NamedTuple):
    """One matched file: the mode-shaped match facts for its text.

    ``lines`` mode carries ``matches`` regions; ``count`` carries the
    (capped) hit count on ``score``; ``files`` carries neither.
    """

    path: Path
    matches: list[Match] | None
    score: float | None


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
# The verifier — compile once, verify per file
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


def compile_verifier(pattern: str, *, fixed_strings: bool, word_regexp: bool, case_mode: CaseMode) -> re.Pattern[str]:
    """The conformance-pinned modifier wrapping: escape, word-wrap, case flags.

    Smart case is judged on the raw pattern — any uppercase letter makes
    the search sensitive, ripgrep's rule.
    """
    text = re.escape(pattern) if fixed_strings else pattern
    if word_regexp:
        text = rf"\b(?:{text})\b"
    insensitive = case_mode == "insensitive" or (case_mode == "smart" and not any(ch.isupper() for ch in pattern))
    return re.compile(text, re.IGNORECASE if insensitive else 0)


def verify(
    text: str,
    verifier: re.Pattern[str],
    *,
    invert: bool,
    before: int,
    after: int,
    mode: GrepOutputMode,
    cap: int | None,
) -> tuple[list[Match] | None, float | None] | None:
    """Per-line verification: ``None`` drops the row, else (matches, score).

    ``files`` short-circuits at the first verified hit and carries
    neither matches nor score; ``count`` reports the (capped) hit count
    on score; ``lines`` renders one region per hit line, context bounds
    clamped to the file.
    """
    lines = split_lines(text)
    hits: list[int] = []
    for number, line in enumerate(lines, start=1):
        if (verifier.search(line) is not None) is not invert:
            hits.append(number)
            if mode == "files" or (cap is not None and len(hits) >= cap):
                break
    if not hits:
        return None
    if mode == "files":
        return None, None
    if mode == "count":
        return None, float(len(hits))
    matches = [
        Match(
            start=(start := max(1, number - before)),
            end=(end := min(len(lines), number + after)),
            match=number,
            content="\n".join(lines[start - 1 : end]),
        )
        for number in hits
    ]
    return matches, None


def match_texts(
    texts: Sequence[tuple[Path, str]],
    verifier: re.Pattern[str],
    *,
    invert: bool,
    before: int,
    after: int,
    mode: GrepOutputMode,
    cap: int | None,
) -> list[GrepHit | None]:
    """Verify each ``(path, text)`` pair; aligned with *texts*, ``None`` per miss.

    The batch form of :func:`verify` for callers holding content rather
    than enumerating storage. Alignment (not hits-only) is deliberate:
    duplicate paths with differing texts stay unambiguous.
    """
    results: list[GrepHit | None] = []
    for path, text in texts:
        verified = verify(text, verifier, invert=invert, before=before, after=after, mode=mode, cap=cap)
        results.append(None if verified is None else GrepHit(path, *verified))
    return results
