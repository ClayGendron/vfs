"""Grep over the gram index: refusal gate, posting ladder, overlay scan.

The read side of content search, one snapshot per call: compile the
caller's pattern (uncompilable classifies invalid), plan folded grams
unconditionally, refuse a pattern with no gram predicate unless
``allow_scan=True`` opts into the scan tier, intersect the rarest
posting lists into candidate chunks, dedupe to entries, apply the
structural gates before any content fetch, verify every candidate with
Python ``re``, and union the flag-partitioned scan side (``NOT
encoded``) so index staleness can never lose a match. ``invert_match``
is scan-shaped by construction — no occurrence index narrows
non-matches — and runs the scan tier without ``allow_scan``; the
refusal gate is pattern-shaped.

Runtime budgets bound work, never correctness silently: a capped call
carries a warning-severity truncation record naming the refine moves.
Every function takes the op's live session and only executes SELECTs;
none begins or commits — ``backend.py`` owns the transaction.
"""

from __future__ import annotations

import re
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Final, NamedTuple

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import or_, select

from vfs.models import CONTENT_KINDS, Observation
from vfs.models.code_grams import GramOr, build_code_gram_query
from vfs.models.postings import PostingCorruptionError, decode_postings
from vfs.paths import Path
from vfs.pattern_matching import GlobFilter, compile_filter, compile_verifier, glob_defect, passes_filters, verify
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.descent import liveness_filters
from vfs.storage.backends.database.dialects import arm_budget, chunked
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.reads import ARM_FIXED_BINDS, effective_columns, meta_scoped, pattern_arm

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import Match
    from vfs.models.code_grams import GramKey, GramQuery
    from vfs.models.rows import EntryId, VFSTables
    from vfs.ops import CaseMode, GrepOutputMode
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.indexing import Epoch

# Runtime budgets (the spike's numbers): candidates fetched and
# verified, posting bytes decoded, and a wall-time deadline checked
# between ladder stages. A tripped budget truncates with a warning.
CANDIDATE_BUDGET: Final = 10_000
POSTING_BYTE_BUDGET: Final = 4 * 1024 * 1024
WALL_TIME_BUDGET: Final = 10.0

# Rarest-first intersection width — selectivity saturates by four grams.
_INTERSECT_GRAMS: Final = 4

_REFINE_GUIDANCE: Final = "narrow the pattern, add globs or ext filters, or scope with paths"


ChunkIds = Annotated[NDArray[np.int64], "sorted chunk-table ids - the posting doc ids"]


class PostingMeta(NamedTuple):
    """One posting row's price-list facts: priced before any blob is fetched."""

    doc_count: int
    byte_size: int


class ScanNominees(NamedTuple):
    """Scan-tier entry rows in path order, and whether the cap cut them."""

    rows: list[RowMapping]
    overflow: bool


async def grep_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
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
    allow_scan: bool,
    columns: frozenset[str] | None,
) -> Result:
    """One row per matching entry, index side unioned with the scan side.

    Scoping arrives purely as pattern text on the ``globs`` channels —
    the router composes and residuates scope upstream; no path channel
    crosses this seam.
    """
    for glob_pattern in (*globs, *globs_not):
        defect = glob_defect(glob_pattern)
        if defect is not None:
            error = ResultError(kind=VFSErrorKind.invalid, message=f"grep glob {glob_pattern!r}: {defect}")
            return Result(ops=("grep",), errors=[error])
    try:
        verifier = compile_verifier(pattern, fixed_strings=fixed_strings, word_regexp=word_regexp, case_mode=case_mode)
    except re.error as exc:
        error = ResultError(kind=VFSErrorKind.invalid, message=f"grep pattern {pattern!r}: {exc}")
        return Result(ops=("grep",), errors=[error])
    plan = build_code_gram_query(pattern, fixed_strings=fixed_strings)
    if plan.is_any() and not invert_match and not allow_scan:
        message = (
            f"grep pattern {pattern!r} yields no indexable literal; "
            f"pass allow_scan=True to run the scan tier, or {_REFINE_GUIDANCE}"
        )
        return Result(ops=("grep",), errors=[ResultError(kind=VFSErrorKind.unindexable_pattern, message=message)])
    scan_all = invert_match or plan.is_any()

    errors: list[ResultError] = []
    admissions = list(dict.fromkeys(globs))
    exclusions = list(dict.fromkeys(globs_not))
    gates = [compile_filter(glob, ()) for glob in admissions]
    not_gates = [compile_filter(glob, ()) for glob in exclusions]
    wanted = frozenset(e.lstrip(".").lower() for e in ext)
    unwanted = frozenset(e.lstrip(".").lower() for e in ext_not)
    fetched = effective_columns(columns, content=columns is not None)
    deadline = monotonic() + WALL_TIME_BUDGET

    candidates: dict[str, RowMapping] = {}
    truncations: list[str] = []
    if not scan_all:
        try:
            chunk_ids = await _index_chunk_ids(session, tables, membership_budget, plan)
        except PostingCorruptionError as exc:
            error = ResultError(kind=VFSErrorKind.internal, message=f"grep posting blob is corrupt: {exc}")
            return Result(ops=("grep",), errors=[error])
        if chunk_ids.size > CANDIDATE_BUDGET:
            chunk_ids = chunk_ids[:CANDIDATE_BUDGET]
            truncations.append("candidate budget")
        for mapping in await _entries_for_chunks(session, tables, membership_budget, chunk_ids, fetched):
            if _passes_gates(Path(mapping["path"]), gates, not_gates, wanted, unwanted):
                candidates[mapping["path"]] = mapping
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")

    if not truncations or truncations == ["candidate budget"]:
        remaining = CANDIDATE_BUDGET - len(candidates)
        if remaining <= 0:
            if "candidate budget" not in truncations:
                truncations.append("candidate budget")
        else:
            nominated, overflow = await _entries_for_scan(
                session,
                tables,
                profile,
                parameter_budget,
                membership_budget,
                gates,
                wanted,
                everything=scan_all,
                fetched=fetched,
                limit=remaining,
            )
            if overflow:
                truncations.append("candidate budget")
            for mapping in nominated:
                if _passes_gates(Path(mapping["path"]), gates, not_gates, wanted, unwanted):
                    candidates.setdefault(mapping["path"], mapping)
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")

    ordered = [candidates[path] for path in sorted(candidates)]
    contents = await _content_for_entries(session, tables, membership_budget, [m["entry_id"] for m in ordered])
    rows: list[Observation] = []
    for mapping in ordered:
        if monotonic() > deadline:
            if "wall-time budget" not in truncations:
                truncations.append("wall-time budget")
            break
        text = contents.get(mapping["entry_id"])
        if text is None:
            continue
        verified = verify(
            text,
            verifier,
            invert=invert_match,
            before=before_context,
            after=after_context,
            mode=output_mode,
            cap=max_count,
        )
        if verified is None:
            continue
        matches, score = verified
        rows.append(_observe_hit(mapping, fetched, text, matches, score, mode=output_mode))
    for reason in truncations:
        message = f"grep result truncated at the {reason}; {_REFINE_GUIDANCE}"
        errors.append(ResultError(kind=VFSErrorKind.truncated, severity=Severity.warning, message=message))
    return Result(ops=("grep",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# The ladder — posting metadata, rarest-first intersection, chunk→entry
# ---------------------------------------------------------------------------


async def _index_chunk_ids(
    session: AsyncSession, tables: VFSTables, membership_budget: int, plan: GramQuery
) -> ChunkIds:
    """Candidate chunk ids for *plan* under the published epoch, sorted.

    No published epoch means no encoded entries: the index side is
    empty and the scan side owns everything. The posting-byte budget is
    enforced before any blob fetch via the stored ``byte_size``.
    """
    epoch = await current_epoch(session, tables)
    if epoch is None:
        return np.empty(0, dtype=np.int64)
    budget = [POSTING_BYTE_BUDGET]
    return await _chunk_ids_for_plan(session, tables, membership_budget, epoch, plan, budget)


async def _chunk_ids_for_plan(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    epoch: int,
    plan: GramQuery,
    budget: list[int],
) -> ChunkIds:
    """One plan node's candidates: OR unions branches, AND intersects grams."""
    if isinstance(plan, GramOr):
        parts = [
            await _chunk_ids_for_plan(session, tables, membership_budget, epoch, branch, budget)
            for branch in plan.branches
        ]
        return np.unique(np.concatenate(parts))
    grams = sorted(plan.required_grams())
    meta = await _posting_meta(session, tables, membership_budget, epoch, grams)
    if len(meta) < len(grams):
        # A required gram indexes nothing — no chunk can match.
        return np.empty(0, dtype=np.int64)
    chosen: list[GramKey] = []
    for gram in sorted(meta, key=lambda key: meta[key].doc_count):
        size = meta[gram].byte_size
        if chosen and (len(chosen) >= _INTERSECT_GRAMS or size > budget[0]):
            break
        chosen.append(gram)
        budget[0] -= size
    blobs = await _posting_blobs(session, tables, membership_budget, epoch, chosen)
    ids: NDArray[np.int64] | None = None
    for gram in chosen:
        decoded = decode_postings(blobs[gram])
        ids = decoded if ids is None else np.intersect1d(ids, decoded, assume_unique=True)
        if ids.size == 0:
            break
    return ids if ids is not None else np.empty(0, dtype=np.int64)


async def _posting_meta(
    session: AsyncSession, tables: VFSTables, membership_budget: int, epoch: Epoch, grams: Sequence[GramKey]
) -> dict[GramKey, PostingMeta]:
    """``gram → PostingMeta`` for the grams present in *epoch*."""
    posting = tables.posting_list
    meta: dict[GramKey, PostingMeta] = {}
    for chunk in chunked(list(grams), membership_budget):
        stmt = select(posting.c.gram_key, posting.c.doc_count, posting.c.byte_size).where(
            posting.c.epoch == epoch, posting.c.gram_key.in_(chunk)
        )
        for row in await session.execute(stmt):
            meta[row.gram_key] = PostingMeta(row.doc_count, row.byte_size)
    return meta


async def _posting_blobs(
    session: AsyncSession, tables: VFSTables, membership_budget: int, epoch: Epoch, grams: Sequence[GramKey]
) -> dict[GramKey, bytes]:
    """``gram → encoded posting blob`` — fetched only for the chosen grams."""
    posting = tables.posting_list
    blobs: dict[GramKey, bytes] = {}
    for chunk in chunked(list(grams), membership_budget):
        stmt = select(posting.c.gram_key, posting.c.postings).where(
            posting.c.epoch == epoch, posting.c.gram_key.in_(chunk)
        )
        for row in await session.execute(stmt):
            blobs[row.gram_key] = row.postings
    return blobs


async def _entries_for_chunks(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    chunk_ids: ChunkIds,
    fetched: frozenset[str],
) -> list[RowMapping]:
    """Candidate chunk ids deduped to their live, encoded entry rows.

    The two-stage id-first shape: entry rows come back without content —
    the structural Python gates run before any content is fetched.
    """
    entry, chunks = tables.entry, tables.chunks
    entry_ids: set[str] = set()
    for chunk in chunked(chunk_ids.tolist(), membership_budget):
        stmt = select(chunks.c.entry_id).where(chunks.c.id.in_(chunk)).distinct()
        entry_ids.update((await session.execute(stmt)).scalars())
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted(fetched - {"content"}))]
    rows: list[RowMapping] = []
    for chunk in chunked(sorted(entry_ids), membership_budget):
        stmt = select(*columns).where(
            entry.c.entry_id.in_(chunk), entry.c.encoded, entry.c.kind.in_(sorted(CONTENT_KINDS))
        )
        rows.extend((await session.execute(stmt)).mappings())
    return rows


# ---------------------------------------------------------------------------
# The scan side — structural prefilter, bounded fetch, permanent overlay
# ---------------------------------------------------------------------------


async def _entries_for_scan(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    gates: list[GlobFilter],
    wanted: frozenset[str],
    *,
    everything: bool,
    fetched: frozenset[str],
    limit: int,
) -> ScanNominees:
    """Scan-tier candidate entry rows in path order, capped at *limit*.

    Serves three callers with one executor: the permanent ``NOT
    encoded`` overlay (*everything* false), the ``allow_scan`` opt-out,
    and ``invert_match`` (*everything* true). Structural narrowing rides
    the same LIKE-superset arms as glob; the flag partition and the
    content-kind gate ride beside the fan — the id-bounded fetch, not
    the fan plan, is what the budget protects here.
    """
    entry = tables.entry
    base = [entry.c.kind.in_(sorted(CONTENT_KINDS))]
    if not everything:
        base.append(~entry.c.encoded)
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted(fetched - {"content"}))]
    merged: dict[str, RowMapping] = {}
    overflow = False
    if gates:
        arms = [arm for gate in gates if (arm := pattern_arm(entry, gate, wanted, membership_budget)) is not None]
        if not arms:
            return ScanNominees([], False)
        ext_binds = len(wanted) if wanted and "" not in wanted and len(wanted) <= membership_budget else 0
        chunk_size = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ext_binds + len(CONTENT_KINDS))
        for chunk in chunked(arms, chunk_size):
            stmt = select(*columns).where(*base, or_(*chunk)).order_by(entry.c.path).limit(limit + 1)
            fetched_rows = list((await session.execute(stmt)).mappings())
            overflow = overflow or len(fetched_rows) > limit
            merged.update({mapping["path"]: mapping for mapping in fetched_rows})
    else:
        terms = [*base, entry.c.path != "/", *liveness_filters(entry, include_meta=False)]
        if wanted and "" not in wanted and len(wanted) <= membership_budget:
            terms.append(entry.c.ext.in_(sorted(wanted)))
        stmt = select(*columns).where(*terms).order_by(entry.c.path).limit(limit + 1)
        merged = {mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()}
    rows = [merged[path] for path in sorted(merged)]
    if len(rows) > limit:
        return ScanNominees(rows[:limit], True)
    return ScanNominees(rows, overflow)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _passes_gates(
    path: Path,
    gates: list[GlobFilter],
    not_gates: list[GlobFilter],
    wanted: frozenset[str],
    unwanted: frozenset[str],
) -> bool:
    """The authoritative structural gates, per candidate, path-derived.

    A meta row is admitted only by a gate whose literal prefix addresses
    the meta subtree — default enumeration hides ``/.vfs`` even when a
    wildcard gate would match it. The rest is the shared filter law.
    """
    if path.is_meta and not any(gate.matches(path) and meta_scoped(gate.pattern) for gate in gates):
        return False
    return passes_filters(path, gates, not_gates, wanted, unwanted)


async def _content_for_entries(
    session: AsyncSession, tables: VFSTables, membership_budget: int, entry_ids: Sequence[EntryId]
) -> dict[EntryId, str]:
    """``entry_id → full body text`` for the final, gated candidate set."""
    content = tables.content
    out: dict[EntryId, str] = {}
    for chunk in chunked(sorted(set(entry_ids)), membership_budget):
        stmt = select(content.c.entry_id, content.c.content).where(content.c.entry_id.in_(chunk))
        out.update({row.entry_id: row.content for row in await session.execute(stmt)})
    return out


def _observe_hit(
    mapping: RowMapping,
    fetched: frozenset[str],
    text: str,
    matches: list[Match] | None,
    score: float | None,
    *,
    mode: GrepOutputMode,
) -> Observation:
    """One result row; ``files`` mode carries neither content nor matches."""
    populated = set(fetched)
    values: dict[str, object] = {field: mapping[field] for field in fetched - {"content"}}
    values["path"] = Path(mapping["path"])
    if "content" in fetched and mode != "files":
        values["content"] = text
    else:
        populated.discard("content")
    if matches is not None:
        values["matches"] = matches
        populated.add("matches")
    if score is not None:
        values["score"] = score
        populated.add("score")
    values["populated"] = frozenset(populated)
    return Observation.model_validate(values)
