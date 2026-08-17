"""Grep over the gram index: refusal gate, posting ladder, overlay scan.

The read side of content search, one coherent epoch per call: compile
the caller's pattern (outside the grep pattern language classifies
invalid), plan folded grams unconditionally, refuse a pattern with no
gram predicate unless ``allow_scan=True`` opts into the scan tier,
intersect the rarest posting lists into candidate entries — with a
segment-bounded glob scope joining as an allow-list *before* the
candidate budget, so the budget counts scoped candidates and
truncation can never drop in-scope rows — apply the structural gates
off the rows' own stored facts (no per-candidate ``Path``) before any
content fetch, verify every candidate through the shared matcher (the
Rust core where the extension serves, its Python approximation
otherwise — batched per content batch, with the wall deadline carried
into the body loop), and union the flag-partitioned scan side
(``NOT encoded``) so index staleness can never lose a match.
``invert_match`` is scan-shaped by construction — no occurrence index
narrows non-matches — and runs the scan tier without ``allow_scan``;
the refusal gate is pattern-shaped.

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
from sqlalchemy import LargeBinary, and_, case, cast, or_, select

from vfs.models import CONTENT_KINDS, Match, Observation
from vfs.models.code_grams import GramOr, build_code_gram_query
from vfs.models.postings import PostingCorruptionError, decode_postings
from vfs.paths import Path, _under_meta_root, normalize_ext_channel
from vfs.pattern_matching import (
    GLOB_CHANNEL_LABELS,
    Body,
    GlobFilter,
    PatternError,
    compile_filter,
    compile_verifier,
    glob_defect,
    passes_row_filters,
)
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.descent import LIKE_ESCAPE, escape_like, liveness_filters
from vfs.storage.backends.database.dialects import StaleSnapshot, arm_budget, chunked
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.pathterms import allow_list_ids, compile_channel
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

    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.code_grams import GramKey, GramQuery
    from vfs.models.rows import EntryId, VFSTables
    from vfs.ops import CaseMode, GrepOutputMode
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.indexing import Epoch
    from vfs.storage.backends.database.pathterms import ChannelTerms

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

# Scoped-defer pricing, measured on the linux-scale store: ~75 µs to fetch
# and verify one candidate, ~0.055 µs per posting byte fetched+decoded+
# intersected, ~500 µs of statement setup per AND-group.
_CANDIDATE_COST_US: Final = 75.0
_POSTING_COST_US_PER_BYTE: Final = 0.055
_GROUP_SETUP_US: Final = 500.0

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
    channel = compile_channel(admissions)
    gated = bool(gates or not_gates or wanted or unwanted)
    fetched = effective_columns(columns, content=columns is not None)
    deadline = monotonic() + wall_seconds

    candidates: dict[str, RowMapping] = {}
    truncations: list[str] = []
    epoch: Epoch | None = None
    overlay_empty = False
    if not scan_all:
        epoch, overlay_empty = await _pointer_with_overlay(session, tables)
        await seam("grep:after-pointer-read")
        # The allow-list joins nomination before the budget: the budget
        # counts scoped candidates, so truncation cannot drop in-scope rows.
        allow = await allow_list_ids(session, tables, membership_budget, channel)
        if allow is not None and not allow:
            doc_ids: DocIds = np.empty(0, dtype=np.int64)
        else:
            allow_size = len(allow) if allow is not None else None
            try:
                laddered = await _index_doc_ids(session, tables, membership_budget, epoch, plan, deadline, allow_size)
            except PostingCorruptionError as exc:
                error = ResultError(kind=VFSErrorKind.internal, message=f"grep posting blob is corrupt: {exc}")
                return Result(ops=("grep",), errors=[error])
            if laddered is None:
                # The ladder priced above verifying the whole scope: the
                # allow-list itself is the candidate set, a lawful superset.
                doc_ids = np.asarray(allow, dtype=np.int64)
            elif allow is not None:
                doc_ids = np.intersect1d(laddered, np.asarray(allow, dtype=np.int64), assume_unique=True)
            else:
                doc_ids = laddered
        if doc_ids.size > CANDIDATE_BUDGET:
            doc_ids = doc_ids[:CANDIDATE_BUDGET]
            truncations.append("candidate budget")
        pushdown = _pushdown_terms(tables.entry, profile, membership_budget, channel, wanted, hide_meta=not gates)
        for mapping in await _entries_for_docs(session, tables, membership_budget, doc_ids, fetched, pushdown):
            if not gated or _passes_gates(mapping, gates, not_gates, wanted, unwanted):
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
        elif not overlay_empty:
            # Skipped only when the same-snapshot EXISTS proved the overlay
            # empty — the skip returns exactly what the scan would.
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
                if not gated or _passes_gates(mapping, gates, not_gates, wanted, unwanted):
                    candidates.setdefault(mapping["path"], mapping)
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")
    if not scan_all and await current_epoch(session, tables) != epoch:
        # A rival publish+reclaim landed mid-call: the tiers this call
        # read are a mix of epochs. Redrive whole from a fresh session.
        raise StaleSnapshot("the gram-index epoch pointer moved mid-grep")

    ordered = [candidates[path] for path in sorted(candidates)]
    rows: list[Observation] = []
    # The projection and populated mask are call-invariant: hoist them
    # out of the per-row assembly path.
    projected = tuple(fetched - {"content"})
    carry_content = "content" in fetched and output_mode == "lines"
    row_mask = fetched if carry_content else fetched - {"content"}
    if output_mode == "lines":
        row_mask = row_mask | {"matches"}
    elif output_mode == "count":
        row_mask = row_mask | {"score"}
    mask = frozenset(row_mask)
    for batch in _content_batches(ordered):
        if monotonic() > deadline:
            if "wall-time budget" not in truncations:
                truncations.append("wall-time budget")
            break
        ids = [m["entry_id"] for m in batch]
        contents = await _content_for_entries(session, tables, profile, membership_budget, ids)
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
                    rows.append(_observe_hit(mapping, projected, mask, text, None, score, carry_content=carry_content))
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
                    hit = _observe_hit(mapping, projected, mask, text, matches, None, carry_content=carry_content)
                    rows.append(hit)
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


async def _pointer_with_overlay(session: AsyncSession, tables: VFSTables) -> tuple[Epoch | None, bool]:
    """The epoch pointer plus an overlay-emptiness verdict, one statement.

    The overlay check rides the pointer read so both come from the same
    snapshot: an empty verdict lets the caller skip the scan tier with
    results identical to scanning. The predicate stays ORM-built — the
    negation renders as an inline literal on every dialect, which keeps
    the seek on the composite (encoded, kind) index reachable; the CASE
    wrapper is what lets engines without boolean select-list expressions
    (SQL Server) carry the EXISTS.
    """
    entry = tables.entry
    pending = select(entry.c.id).where(~entry.c.encoded, entry.c.kind.in_(sorted(CONTENT_KINDS))).exists()
    stmt = select(tables.meta.c.current_gram_epoch, case((pending, 1), else_=0)).where(tables.meta.c.id == 1)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None, False
    pointer, has_pending = row
    return pointer, not has_pending


async def _index_doc_ids(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    epoch: Epoch | None,
    plan: GramQuery,
    deadline: float,
    allow_size: int | None,
) -> DocIds | None:
    """Candidate entry doc ids for *plan* under the caller-read *epoch*, sorted.

    No published epoch means no encoded entries: the index side is
    empty and the scan side owns everything. The caller owns the epoch
    read — its post-ladder re-read is what detects a mid-call publish.
    The posting-byte budget is enforced before any blob fetch via the
    stored ``byte_size``.

    The ladder is priced before any blob is fetched: one metadata read
    covers every AND-group, the rarest-first choice fixes the byte bill,
    and when *allow_size* (the scoped allow-list's width) is cheaper to
    verify outright than that bill, the return is ``None`` — the caller
    takes the allow-list itself as the candidate set, a lawful superset.
    OR unions groups and AND intersects grams as ever, with the deadline
    consulted between groups: an expired union stops, and the caller's
    post-ladder check records the truncation loudly.
    """
    if epoch is None:
        return np.empty(0, dtype=np.int64)
    groups = _plan_groups(plan)
    grams = sorted({gram for group in groups for gram in group})
    meta = await _posting_meta(session, tables, membership_budget, epoch, grams)
    chosen = _choose_grams(groups, meta)
    if allow_size is not None and _ladder_defers(chosen, meta, allow_size):
        return None
    wanted = sorted({gram for group_chosen in chosen if group_chosen for gram in group_chosen})
    blobs = await _posting_blobs(session, tables, membership_budget, epoch, wanted)
    parts = [np.empty(0, dtype=np.int64)]
    for group_chosen in chosen:
        if monotonic() > deadline:
            break
        if not group_chosen:
            # None: a required gram indexes nothing, the group is empty.
            # []: a gramless group — it nominates nothing either way.
            continue
        ids: NDArray[np.int64] | None = None
        for gram in group_chosen:
            decoded = decode_postings(blobs[gram])
            ids = decoded if ids is None else np.intersect1d(ids, decoded, assume_unique=True)
            if ids.size == 0:
                break
        if ids is not None:
            parts.append(ids)
    return np.unique(np.concatenate(parts))


def _plan_groups(plan: GramQuery) -> list[tuple[GramKey, ...]]:
    """The plan's AND-groups in union order, each as its required grams."""
    if isinstance(plan, GramOr):
        groups: list[tuple[GramKey, ...]] = []
        for branch in plan.branches:
            groups.extend(_plan_groups(branch))
        return groups
    return [tuple(sorted(plan.required_grams()))]


def _choose_grams(
    groups: Sequence[tuple[GramKey, ...]], meta: dict[GramKey, PostingMeta]
) -> list[list[GramKey] | None]:
    """Each group's fetch list, rarest-first under the shared byte budget.

    ``None`` marks a group with a gram that indexes nothing — no entry
    can match it. The rarest gram of each group is budget-exempt, so a
    wide union's byte bill grows with its group count by design.
    """
    budget = POSTING_BYTE_BUDGET
    out: list[list[GramKey] | None] = []
    for group in groups:
        if any(gram not in meta for gram in group):
            out.append(None)
            continue
        chosen: list[GramKey] = []
        for gram in sorted(group, key=lambda key: meta[key].doc_count):
            size = meta[gram].byte_size
            if chosen and (len(chosen) >= _INTERSECT_GRAMS or size > budget):
                break
            chosen.append(gram)
            budget -= size
        out.append(chosen)
    return out


def _ladder_defers(chosen: Sequence[list[GramKey] | None], meta: dict[GramKey, PostingMeta], allow_size: int) -> bool:
    """Whether verifying the whole scope outright beats fetching the blobs.

    Both sides priced from measurement: the ladder at a per-group setup
    charge plus a per-byte fetch+decode+intersect rate over the chosen
    blobs, the scope at the per-candidate fetch+verify cost. Deferring
    only ever trades index work for verify work — recall is untouched.
    """
    posting_us = sum(
        _GROUP_SETUP_US + sum(meta[gram].byte_size for gram in group) * _POSTING_COST_US_PER_BYTE
        for group in chosen
        if group
    )
    return posting_us > allow_size * _CANDIDATE_COST_US


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
    pushdown: Sequence[ColumnElement[bool]],
) -> list[RowMapping]:
    """Candidate doc ids resolved to their live, encoded entry rows.

    The id-first shape: entry rows come back without content — the
    structural gates run before any content is fetched. ``size_bytes``
    always rides along (it prices the content batches), and ``ext`` and
    ``name`` ride for the string gate. *pushdown* carries the compiled
    column facts and the meta scope; its binds shrink the id chunk so
    the statement stays inside the declared budgets.
    """
    entry = tables.entry
    ride_along = {"size_bytes", "ext", "name"}
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | ride_along) - {"content"}))]
    per_chunk = max(1, membership_budget - _predicate_binds(pushdown))
    rows: list[RowMapping] = []
    for chunk in chunked(doc_ids.tolist(), per_chunk):
        stmt = select(*columns).where(
            entry.c.id.in_(chunk), entry.c.encoded, entry.c.kind.in_(sorted(CONTENT_KINDS)), *pushdown
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
    ride_along = {"size_bytes", "ext", "name"}
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | ride_along) - {"content"}))]
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
    mapping: RowMapping,
    gates: list[GlobFilter],
    not_gates: list[GlobFilter],
    wanted: frozenset[str],
    unwanted: frozenset[str],
) -> bool:
    """The authoritative structural gates, per candidate, off the row's own facts.

    Matches raw strings — the stored ``name`` and ``ext`` columns mirror
    the path by invariant, so no ``Path`` is minted per candidate. A
    meta row is admitted only by a gate whose literal prefix addresses
    the meta subtree — default enumeration hides ``/.vfs`` even when a
    wildcard gate would match it. The rest is the shared filter law.
    """
    path, name, ext = mapping["path"], mapping["name"], mapping["ext"]
    if _under_meta_root(path) and not any(gate.hits(path, name, ext) and meta_scoped(gate.pattern) for gate in gates):
        return False
    return passes_row_filters(path, name, ext, gates, not_gates, wanted, unwanted)


def _pushdown_terms(
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    channel: ChannelTerms,
    wanted: frozenset[str],
    *,
    hide_meta: bool,
) -> list[ColumnElement[bool]]:
    """The SQL terms the candidate fetch may carry beside the id chunk.

    With no admission gates the meta scope moves into SQL — the string
    gate may then be skipped entirely. The caller's wanted-ext set rides
    under the membership rule, and the channel's compiled column facts
    ride as an OR over arms; both only ever narrow toward the authority,
    never past it.
    """
    terms: list[ColumnElement[bool]] = []
    if hide_meta:
        terms.extend(liveness_filters(entry, profile, include_meta=False))
    ride = ext_membership(entry, wanted, membership_budget)
    if ride.predicate is not None:
        terms.append(ride.predicate)
    facts = _channel_facts(entry, profile, channel)
    if facts is not None:
        terms.append(facts)
    return terms


def _channel_facts(entry: Table, profile: DialectProfile, channel: ChannelTerms) -> ColumnElement[bool] | None:
    """The channel's ``ext``/``name`` facts as one OR over arms, or ``None``.

    The channel is an OR, so the predicate is sound only when *every*
    arm pins at least one fact — an arm with none admits everything and
    makes the disjunction vacuous. Each ext fact carries the dotfile
    rescue (a stored NULL ext with the dot-suffix name), mirroring the
    scan tier's arm law.
    """
    arms: list[ColumnElement[bool]] = []
    for arm in channel.arms:
        facts: list[ColumnElement[bool]] = []
        if arm.ext is not None:
            facts.append(or_(entry.c.ext == arm.ext.ext, entry.c.name == arm.ext.dot_suffix))
        if arm.name is not None:
            if arm.name.prefix:
                prefix = escape_like(arm.name.text, profile) + "%"
                facts.append(entry.c.name.like(prefix, escape=LIKE_ESCAPE))
            else:
                facts.append(entry.c.name == arm.name.text)
        if not facts:
            return None
        arms.append(and_(*facts))
    return or_(*arms) if arms else None


def _predicate_binds(pushdown: Sequence[ColumnElement[bool]]) -> int:
    """Bind slots the pushdown terms spend, off each compiled predicate."""
    return sum(len(term.compile().binds) for term in pushdown)


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
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    entry_ids: Sequence[EntryId],
) -> dict[EntryId, Body]:
    """``entry_id → full body`` for one verification batch.

    Where the profile declares ``content_bytes`` the body comes back as
    the column's UTF-8 bytes — the driver skips its decode and the
    matcher takes them as-is; only hit rows ever decode, at assembly.
    """
    content = tables.content
    body = cast(content.c.content, LargeBinary).label("content") if profile.content_bytes else content.c.content
    out: dict[EntryId, Body] = {}
    for chunk in chunked(sorted(set(entry_ids)), membership_budget):
        stmt = select(content.c.entry_id, body).where(content.c.entry_id.in_(chunk))
        out.update({row.entry_id: row.content for row in await session.execute(stmt)})
    return out


def _observe_hit(
    mapping: RowMapping,
    projected: tuple[str, ...],
    mask: frozenset[str],
    text: Body,
    matches: list[Match] | None,
    score: float | None,
    *,
    carry_content: bool,
) -> Observation:
    """One result row; only ``lines`` mode may carry the body.

    ``files`` and ``count`` verdicts retain no content — the body was
    needed to verify, never to report. Only hit rows reach here, so a
    bytes-fetched body decodes exactly once per hit. *projected* (the
    non-content fetched fields) and *mask* (the populated set) are
    call-invariant, hoisted by the caller off the per-row path.
    """
    values: dict[str, object] = {field: mapping[field] for field in projected}
    # Stored paths passed the gate at write time; re-brand without re-gating.
    values["path"] = Path._brand(mapping["path"])
    if carry_content:
        values["content"] = text if isinstance(text, str) else text.decode("utf-8", "surrogatepass")
    if matches is not None:
        values["matches"] = matches
    if score is not None:
        values["score"] = score
    values["populated"] = mask
    return Observation.model_validate(values)
