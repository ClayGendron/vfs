"""Grep over the gram index: refusal gate, posting ladder, overlay scan.

The read side of content search, one coherent epoch per call: compile
the caller's pattern (outside the grep pattern language classifies
invalid), plan folded grams unconditionally, refuse a pattern with no
gram predicate unless ``allow_scan=True`` opts into the scan tier,
intersect the rarest posting lists into candidate entries, apply the
structural gates before any content fetch, verify every candidate
through the shared matcher (the Rust core where the extension serves,
its Python approximation otherwise — batched per content batch, with
the wall deadline carried into the body loop), and union the
flag-partitioned scan side (``NOT encoded``) so index staleness can
never lose a match. ``invert_match`` is scan-shaped by construction —
no occurrence index narrows non-matches — and runs the scan tier
without ``allow_scan``; the refusal gate is pattern-shaped.

Epoch coherence is detected, never assumed: engines without a
repeatable-read pin read each statement at its own snapshot, so after
the last epoch-dependent read the pointer is re-read — movement means
a rival publish landed mid-call and the whole call redrives via
:class:`StaleSnapshot` (reclaim commits strictly after the publish
CAS, so every observable mix moves the pointer first). On pinned
engines the re-read is a same-snapshot no-op.

Runtime budgets bound work, never correctness silently: a capped call
carries a warning-severity truncation record naming the refine moves.
One declared exemption: the rarest gram of each AND-group is fetched
even when it alone exceeds ``POSTING_BYTE_BUDGET`` — strict
enforcement would silently lose index-side matches. The exemption is
per OR branch, so a wide-alternation union's fetch cost grows with
its branch count; that width is deliberately uncapped (bulk unions —
IOC lists, symbol sweeps — are a supported shape) and is bounded by
the wall-clock deadline instead, consulted between branches. When the
index side alone saturates ``CANDIDATE_BUDGET`` the scan overlay is
never consulted, and the truncation record says so by name.

Every function takes the op's live session and only executes SELECTs;
none begins or commits — ``backend.py`` owns the transaction.
"""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Annotated, Final, NamedTuple

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import or_, select

from vfs.models import CONTENT_KINDS, Match, Observation
from vfs.models.code_grams import GramOr, build_code_gram_query
from vfs.models.postings import PostingCorruptionError, decode_postings
from vfs.paths import Path, normalize_ext_channel
from vfs.pattern_matching import (
    GLOB_CHANNEL_LABELS,
    GlobFilter,
    PatternError,
    compile_filter,
    compile_verifier,
    glob_defect,
    passes_filters,
)
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.descent import liveness_filters
from vfs.storage.backends.database.dialects import StaleSnapshot, arm_budget, chunked
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.reads import (
    ARM_FIXED_BINDS,
    effective_columns,
    ext_membership,
    meta_scoped,
    pattern_arm,
)
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.code_grams import GramKey, GramQuery
    from vfs.models.rows import EntryId, VFSTables
    from vfs.ops import CaseMode, GrepOutputMode
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.indexing import Epoch

# Runtime budgets: candidates fetched and verified, posting bytes
# decoded, and a wall-time deadline checked between ladder stages and
# inside the matcher's body loop. A tripped budget truncates with a
# warning. The candidate budget is re-derived from the linux-scale
# sweep: candidate cost is ~75 µs each (fetch-dominated), so 25,000
# bounds a saturated call near ~2 s while un-truncating every
# benchmark row search semantics can justify.
CANDIDATE_BUDGET: Final = 25_000
POSTING_BYTE_BUDGET: Final = 4 * 1024 * 1024
WALL_TIME_BUDGET: Final = 10.0

# Bytes of candidate bodies resident at once: content is fetched,
# verified, and released in batches sized by the entries' size_bytes.
CONTENT_BYTE_BUDGET: Final = 32 * 1024 * 1024

# Rarest-first intersection width — selectivity saturates by four grams.
_INTERSECT_GRAMS: Final = 4

_REFINE_GUIDANCE: Final = "narrow the pattern, add globs or ext filters, or scope with paths"


DocIds = Annotated[NDArray[np.int64], "sorted entries-table surrogate ids - the posting doc ids"]


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
    wall_seconds: float = WALL_TIME_BUDGET,
) -> Result:
    """One row per matching entry, index side unioned with the scan side.

    Scoping arrives purely as pattern text on the ``globs`` channels —
    the router composes and residuates scope upstream; no path channel
    crosses this seam. *wall_seconds* is the caller-configured wall-clock
    budget; the declared default keeps direct callers honest.
    """
    for label, channel in ((GLOB_CHANNEL_LABELS["globs"], globs), (GLOB_CHANNEL_LABELS["globs_not"], globs_not)):
        for glob_pattern in channel:
            defect = glob_defect(glob_pattern)
            if defect is not None:
                error = ResultError(kind=VFSErrorKind.invalid, message=f"{label} {glob_pattern!r}: {defect}")
                return Result(ops=("grep",), errors=[error])
    try:
        verifier = compile_verifier(pattern, fixed_strings=fixed_strings, word_regexp=word_regexp, case_mode=case_mode)
    except PatternError as exc:
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
    wanted = normalize_ext_channel(ext)
    unwanted = normalize_ext_channel(ext_not)
    fetched = effective_columns(columns, content=columns is not None)
    deadline = monotonic() + wall_seconds

    candidates: dict[str, RowMapping] = {}
    truncations: list[str] = []
    epoch: Epoch | None = None
    if not scan_all:
        epoch = await current_epoch(session, tables)
        await seam("grep:after-pointer-read")
        try:
            doc_ids = await _index_doc_ids(session, tables, membership_budget, epoch, plan, deadline)
        except PostingCorruptionError as exc:
            error = ResultError(kind=VFSErrorKind.internal, message=f"grep posting blob is corrupt: {exc}")
            return Result(ops=("grep",), errors=[error])
        if doc_ids.size > CANDIDATE_BUDGET:
            doc_ids = doc_ids[:CANDIDATE_BUDGET]
            truncations.append("candidate budget")
        for mapping in await _entries_for_docs(session, tables, membership_budget, doc_ids, fetched):
            if _passes_gates(Path(mapping["path"]), gates, not_gates, wanted, unwanted):
                candidates[mapping["path"]] = mapping
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")

    if not truncations or truncations == ["candidate budget"]:
        remaining = CANDIDATE_BUDGET - len(candidates)
        if remaining <= 0:
            # The overlay was never consulted: freshly-written scan-side
            # entries are absent, and the record must say so by name.
            if "candidate budget" in truncations:
                truncations.remove("candidate budget")
            truncations.append("candidate budget, with the unindexed overlay not consulted")
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
                deadline=deadline,
            )
            if overflow:
                truncations.append("candidate budget")
            for mapping in nominated:
                if _passes_gates(Path(mapping["path"]), gates, not_gates, wanted, unwanted):
                    candidates.setdefault(mapping["path"], mapping)
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")
    if not scan_all and await current_epoch(session, tables) != epoch:
        # A rival publish+reclaim landed mid-call: the tiers this call
        # read are a mix of epochs. Redrive whole from a fresh session.
        raise StaleSnapshot("the gram-index epoch pointer moved mid-grep")

    ordered = [candidates[path] for path in sorted(candidates)]
    rows: list[Observation] = []
    for batch in _content_batches(ordered):
        if monotonic() > deadline:
            if "wall-time budget" not in truncations:
                truncations.append("wall-time budget")
            break
        contents = await _content_for_entries(session, tables, membership_budget, [m["entry_id"] for m in batch])
        paired = [(m, text) for m in batch if (text := contents.get(m["entry_id"])) is not None]
        if not paired:
            continue
        texts = [text for _, text in paired]
        budget = max(0.0, deadline - monotonic())
        if output_mode in ("files", "count"):
            cap = 1 if output_mode == "files" else max_count
            counts, completed = verifier.count_lines(texts, cap=cap, invert=invert_match, budget=budget)
            for (mapping, text), count in zip(paired, counts, strict=True):
                if count:
                    score = float(count) if output_mode == "count" else None
                    rows.append(_observe_hit(mapping, fetched, text, None, score, mode=output_mode))
        else:
            spans, completed = verifier.hit_lines(
                texts,
                before=before_context,
                after=after_context,
                cap=max_count,
                invert=invert_match,
                budget=budget,
            )
            for (mapping, text), row in zip(paired, spans, strict=True):
                if row:
                    matches = [Match(start=s, end=e, match=m, content=c) for s, e, m, c in row]
                    rows.append(_observe_hit(mapping, fetched, text, matches, None, mode=output_mode))
        if not completed:
            # The matcher hit the wall mid-batch: bodies it never reached
            # are unverified, so the record must say so loudly.
            if "wall-time budget" not in truncations:
                truncations.append("wall-time budget")
            break
    for reason in truncations:
        message = f"grep result truncated at the {reason}; {_REFINE_GUIDANCE}"
        errors.append(ResultError(kind=VFSErrorKind.truncated, severity=Severity.warning, message=message))
    return Result(ops=("grep",), observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# The ladder — posting metadata, rarest-first intersection, doc→entry
# ---------------------------------------------------------------------------


async def _index_doc_ids(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    epoch: Epoch | None,
    plan: GramQuery,
    deadline: float,
) -> DocIds:
    """Candidate entry doc ids for *plan* under the caller-read *epoch*, sorted.

    No published epoch means no encoded entries: the index side is
    empty and the scan side owns everything. The caller owns the epoch
    read — its post-ladder re-read is what detects a mid-call publish.
    The posting-byte budget is enforced before any blob fetch via the
    stored ``byte_size``.
    """
    if epoch is None:
        return np.empty(0, dtype=np.int64)
    budget = [POSTING_BYTE_BUDGET]
    return await _doc_ids_for_plan(session, tables, membership_budget, epoch, plan, budget, deadline)


async def _doc_ids_for_plan(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    epoch: int,
    plan: GramQuery,
    budget: list[int],
    deadline: float,
) -> DocIds:
    """One plan node's candidates: OR unions branches, AND intersects grams.

    Branch width is deliberately uncapped (each branch fetches one
    budget-exempt rarest blob), so the deadline is consulted between
    branches: an expired union stops, and the caller's post-ladder
    check records the truncation loudly.
    """
    if isinstance(plan, GramOr):
        parts = [np.empty(0, dtype=np.int64)]
        for branch in plan.branches:
            if monotonic() > deadline:
                break
            parts.append(await _doc_ids_for_plan(session, tables, membership_budget, epoch, branch, budget, deadline))
        return np.unique(np.concatenate(parts))
    grams = sorted(plan.required_grams())
    meta = await _posting_meta(session, tables, membership_budget, epoch, grams)
    if len(meta) < len(grams):
        # A required gram indexes nothing — no entry can match.
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


async def _entries_for_docs(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    doc_ids: DocIds,
    fetched: frozenset[str],
) -> list[RowMapping]:
    """Candidate doc ids resolved to their live, encoded entry rows.

    The id-first shape: entry rows come back without content — the
    structural Python gates run before any content is fetched.
    ``size_bytes`` always rides along: it prices the content batches.
    """
    entry = tables.entry
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | {"size_bytes"}) - {"content"}))]
    rows: list[RowMapping] = []
    for chunk in chunked(doc_ids.tolist(), membership_budget):
        stmt = select(*columns).where(entry.c.id.in_(chunk), entry.c.encoded, entry.c.kind.in_(sorted(CONTENT_KINDS)))
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
    deadline: float,
) -> ScanNominees:
    """Scan-tier candidate entry rows in path order, capped at *limit*.

    Serves three callers with one executor: the permanent ``NOT
    encoded`` overlay (*everything* false), the ``allow_scan`` opt-out,
    and ``invert_match`` (*everything* true). Structural narrowing rides
    the same LIKE-superset arms as glob; the flag partition and the
    content-kind gate ride beside the fan — the id-bounded fetch, not
    the fan plan, is what the budget protects here. The merge is pruned
    to the lowest ``limit + 1`` paths as arm chunks arrive (per-chunk
    top-``limit + 1`` is a correct merge input), and the deadline is
    consulted between chunks — an expired loop stops, and the caller's
    post-scan check records the truncation loudly.
    """
    entry = tables.entry
    base = [entry.c.kind.in_(sorted(CONTENT_KINDS))]
    if not everything:
        base.append(~entry.c.encoded)
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | {"size_bytes"}) - {"content"}))]
    merged: dict[str, RowMapping] = {}
    overflow = False
    if gates:
        built = (pattern_arm(entry, gate, wanted, profile, membership_budget) for gate in gates)
        arms = [arm for arm in built if arm is not None]
        if not arms:
            return ScanNominees([], False)
        ride = ext_membership(entry, wanted, membership_budget)
        chunk_size = arm_budget(profile, parameter_budget, ARM_FIXED_BINDS + ride.binds + len(CONTENT_KINDS))
        for chunk in chunked(arms, chunk_size):
            if monotonic() > deadline:
                break
            stmt = select(*columns).where(*base, or_(*chunk)).order_by(entry.c.path).limit(limit + 1)
            fetched_rows = list((await session.execute(stmt)).mappings())
            overflow = overflow or len(fetched_rows) > limit
            merged.update({mapping["path"]: mapping for mapping in fetched_rows})
            if len(merged) > limit + 1:
                merged = {path: merged[path] for path in sorted(merged)[: limit + 1]}
    else:
        terms = [*base, entry.c.path != "/", *liveness_filters(entry, profile, include_meta=False)]
        ride = ext_membership(entry, wanted, membership_budget)
        if ride.predicate is not None:
            terms.append(ride.predicate)
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


def _content_batches(ordered: Sequence[RowMapping]) -> Iterator[list[RowMapping]]:
    """Path-ordered slices whose summed ``size_bytes`` fit the byte budget.

    One oversized entry rides alone — the floor of one row per batch
    keeps progress; the budget bounds residency, never eligibility.
    """
    batch: list[RowMapping] = []
    total = 0
    for mapping in ordered:
        size = mapping["size_bytes"] or 0
        if batch and total + size > CONTENT_BYTE_BUDGET:
            yield batch
            batch, total = [], 0
        batch.append(mapping)
        total += size
    if batch:
        yield batch


async def _content_for_entries(
    session: AsyncSession, tables: VFSTables, membership_budget: int, entry_ids: Sequence[EntryId]
) -> dict[EntryId, str]:
    """``entry_id → full body text`` for one verification batch."""
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
    """One result row; only ``lines`` mode may carry the body.

    ``files`` and ``count`` verdicts retain no content — the body was
    needed to verify, never to report.
    """
    populated = set(fetched)
    values: dict[str, object] = {field: mapping[field] for field in fetched - {"content"}}
    values["path"] = Path(mapping["path"])
    if "content" in fetched and mode == "lines":
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
