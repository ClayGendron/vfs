"""Filters over rows in hand: chained glob and chained grep, which resolve no path and dispatch to no entry.

A caller that holds rows hands them back to ``glob`` or ``grep`` as
*observations*. The router gates the call and passes the rows here.
These functions judge them against the glob gates, match their bodies,
and serve each row as held. Storage is reached only for a fact a row
lacks, and only through the :class:`RowSource` the caller hands in:
``stat`` for a missing kind, ``read`` for absent content.

    kept, completed = await judge_in_hand(gates, rows, deadline)

Each stage that matches rows runs on the process pool under a wall, and
a stage that reaches it returns what it finished and one ``truncated``
warning. :func:`judge_in_hand` is the judge-then-admit step both
filters share; the router's root probe calls it for the rows it statted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

from vfs.batching import byte_chunked
from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.models import CONTENT_KINDS
from vfs.offload import CONTENT_BYTE_BUDGET, call_offloaded, judge_rows, offload_pool, wall_truncation
from vfs.paths import extract_extension
from vfs.pattern_matching import PatternError, compile_gates, compile_verifier, match_texts
from vfs.results import ErrorKind, Result, classified

if TYPE_CHECKING:
    from vfs.authority import Authority
    from vfs.models import Observation
    from vfs.ops import CaseMode, GrepOutputMode
    from vfs.paths import ObjectKind, Path
    from vfs.pattern_matching import ContentMatcher, GlobGates, GrepHit
    from vfs.results import ResultError

# Chained grep's truncation advice: a chained call cannot take paths, so it never says to scope with them.
_CHAINED_REFINE_GUIDANCE: Final = "narrow the pattern, add globs or ext filters, or send fewer rows"

# Chained glob's truncation advice: its one stage is the filter over the rows in hand.
_CHAINED_GLOB_REFINE_GUIDANCE: Final = "narrow the pattern or its exclusions, or send fewer rows"


class RowSource(Protocol):
    """Who holds the rows' storage: the two reads a filter makes for a fact a row lacks."""

    async def read(
        self, *, observations: list[Observation], columns: frozenset[str], authority: Authority | None
    ) -> Result: ...

    async def stat(
        self, *, observations: list[Observation], columns: frozenset[str], authority: Authority | None
    ) -> Result: ...


# ---------------------------------------------------------------------------
# The filters
# ---------------------------------------------------------------------------


async def glob_rows_in_hand(
    source: RowSource,
    rows: list[Observation],
    *,
    arms: tuple[str, ...],
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    globs_not: tuple[str, ...],
    kind: ObjectKind | None,
    deadline: Deadline,
    authority: Authority | None,
) -> Result:
    """Chained glob: filter rows in hand, fetching only a missing kind fact.

    The path gates run over the rows as held — admission by any
    expanded arm, rejection by exclusion globs and the ext facts, no
    meta rule, duplicates and order preserved — judged in one hop on
    the process pool under *deadline*, the wall the caller read before
    it materialized the rows; a row the engine did not judge before it
    is dropped, with one ``truncated`` warning. A *kind* filter judged
    against a row that carries no kind stats exactly those rows in one
    batch — the load-bearing fact is fetched, never guessed — and a row
    that cannot be statted classifies loudly beside the healthy rows.
    The row cap is the caller's to apply.
    """
    gates = compile_gates(arms, globs_not, ext=ext, ext_not=ext_not)
    kept, completed = await judge_in_hand(gates, rows, deadline)
    errors: list[ResultError] = []
    if not completed:
        errors.append(wall_truncation(_CHAINED_GLOB_REFINE_GUIDANCE))
    if kind is not None:
        lacking = [row for row in kept if row.kind is None]
        fetched: dict[str, str | None] = {}
        if lacking:
            stat = await source.stat(observations=lacking, columns=frozenset(), authority=authority)
            errors.extend(stat.errors)
            fetched = {str(row.path): row.kind for row in stat.observations}
        kept = [row for row in kept if (row.kind if row.kind is not None else fetched.get(str(row.path))) == kind]
    return Result(ops=("glob",), observations=kept, errors=errors)


async def grep_rows_in_hand(
    source: RowSource,
    rows: list[Observation],
    *,
    pattern: str,
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    globs: tuple[str, ...],
    globs_not: tuple[str, ...],
    case_mode: CaseMode,
    fixed_strings: bool,
    word_regexp: bool,
    invert_match: bool,
    before_context: int,
    after_context: int,
    output_mode: GrepOutputMode,
    max_count: int | None,
    columns: frozenset[str] | None,
    authority: Authority | None,
) -> Result:
    """Chained grep: filter the rows in hand, fetching only absent content.

    Path gates and the match run over the rows as held, each stage
    on the process pool under its own wall: the gates in one hop,
    and only the rows they judged are read and matched. A
    row without content is read through its own entry — a row that
    cannot be read classifies loudly beside the healthy rows'
    matches — while a row whose known kind carries no content never
    matches and is skipped without error, a filter's non-match. The
    index tier is never involved, so the refusal gate and
    ``allow_scan`` have no meaning on this path.
    """
    try:
        verifier = compile_verifier(pattern, fixed_strings=fixed_strings, word_regexp=word_regexp, case_mode=case_mode)
    except PatternError as exc:
        return Result(ops=("grep",), errors=[classified(ErrorKind.invalid, detail=f"grep pattern {pattern!r}: {exc}")])
    gates = compile_gates(globs, globs_not, ext=ext, ext_not=ext_not)
    # The filter reads its own wall only when it has a pattern to judge.
    deadline = Deadline.after(WALL_TIME_BUDGET) if gates.has_patterns else Deadline.never()
    candidates, filtered = await judge_in_hand(gates, rows, deadline)
    absent = [row for row in candidates if row.content is None and (row.kind is None or row.kind in CONTENT_KINDS)]
    errors: list[ResultError] = []
    contents: dict[str, str] = {}
    if absent:
        read = await source.read(observations=absent, columns=frozenset({"content"}), authority=authority)
        errors = list(read.errors)
        contents = {str(row.path): row.content for row in read.observations if row.content is not None}
    texted: list[tuple[Observation, str]] = []
    for row in candidates:
        text = row.content if row.content is not None else contents.get(str(row.path))
        if text is not None:
            texted.append((row, text))
    unique: dict[tuple[str, str], int] = {}
    bodies: list[tuple[Path, str]] = []
    for row, text in texted:
        key = (str(row.path), text)
        if key not in unique:
            unique[key] = len(bodies)
            bodies.append((row.path, text))
    hits, truncation = await _match_in_hand(
        bodies,
        verifier,
        invert=invert_match,
        before=before_context,
        after=after_context,
        mode=output_mode,
        cap=max_count,
    )
    matched = []
    for row, text in texted:
        hit = hits[unique[(str(row.path), text)]]
        if hit is not None:
            matched.append(_hit_row(row, text, hit, mode=output_mode, columns=columns))
    # An unfinished filter's record stands for the matching stage's identical one.
    errors.extend(truncation if filtered else [wall_truncation(_CHAINED_REFINE_GUIDANCE)])
    return Result(ops=("grep",), observations=matched, errors=errors)


# ---------------------------------------------------------------------------
# Judge, then admit
# ---------------------------------------------------------------------------


async def judge_in_hand(
    gates: GlobGates, rows: list[Observation], deadline: Deadline
) -> tuple[list[Observation], bool]:
    """The rows in hand *gates* admit, judged in one hop on the process pool; and whether all were judged.

    Rows keep their order and duplicates, and no meta rule applies:
    what a caller holds is never hidden. With no rows, or no pattern
    to judge, no hop is made and *deadline* is not read.
    """
    if not rows or not gates.has_patterns:
        return [row for row in rows if gates.admits(0, extract_extension(row.path))], True
    judged = [(str(row.path), row.path.name) for row in rows]
    verdicts, completed = await judge_rows(offload_pool(), gates, judged, deadline=deadline)
    kept = [
        row for row, verdict in zip(rows, verdicts, strict=True) if gates.admits(verdict, extract_extension(row.path))
    ]
    return kept, completed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _match_in_hand(
    bodies: list[tuple[Path, str]],
    verifier: ContentMatcher,
    *,
    invert: bool,
    before: int,
    after: int,
    mode: GrepOutputMode,
    cap: int | None,
) -> tuple[list[GrepHit | None], list[ResultError]]:
    """Each distinct body's hit, in byte batches on the process pool, under one wall.

    The deadline is absolute and the budget is cut at worker start, so
    time queued for a thread shortens it. Batches are metered in
    characters, an ASCII-dominant proxy, as the reindex batchers are.
    A wall passed before a batch, or a batch the matcher could not
    finish, stops matching with one truncation warning.
    """
    deadline = Deadline.after(WALL_TIME_BUDGET)
    hits: list[GrepHit | None] = []
    finished = True
    for batch in byte_chunked(range(len(bodies)), lambda index: len(bodies[index][1]), CONTENT_BYTE_BUDGET):
        if deadline.expired():
            finished = False
            break
        texts = [bodies[index] for index in batch]

        def work(texts: list[tuple[Path, str]] = texts) -> tuple[list[GrepHit | None], bool]:
            budget = deadline.remaining()
            return match_texts(
                texts, verifier, invert=invert, before=before, after=after, mode=mode, cap=cap, budget=budget
            )

        found, completed = await call_offloaded(offload_pool(), work)
        hits.extend(found)
        if not completed:
            finished = False
            break
    if finished:
        return hits, []
    hits.extend([None] * (len(bodies) - len(hits)))
    return hits, [wall_truncation(_CHAINED_REFINE_GUIDANCE)]


def _hit_row(
    row: Observation,
    text: str,
    hit: GrepHit,
    *,
    mode: GrepOutputMode,
    columns: frozenset[str] | None,
) -> Observation:
    """One chained-grep hit: the row as held, match facts attached.

    ``files`` mode carries neither content nor matches; fetched
    content attaches only when the caller projected it.
    """
    populated = set(row.populated)
    update: dict[str, object] = {}
    if mode == "files":
        update["content"] = None
        populated.discard("content")
    elif row.content is None and columns is not None and "content" in columns:
        update["content"] = text
        populated.add("content")
    if hit.matches is not None:
        # A copy per row: rows sharing one body never share a mutable list.
        update["matches"] = list(hit.matches)
        populated.add("matches")
    if hit.score is not None:
        update["score"] = hit.score
        populated.add("score")
    update["populated"] = frozenset(populated)
    return row.model_copy(update=update)
