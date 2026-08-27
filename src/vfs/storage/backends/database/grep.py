"""Grep over the gram index: refusal gate, posting ladder, overlay scan.

The read side of content search, one coherent epoch per call: compile
the caller's pattern (outside the grep pattern language classifies
invalid), plan folded grams unconditionally, refuse a pattern with no
gram predicate unless ``allow_scan=True`` opts into the scan tier,
intersect the rarest posting lists into candidate entries — one call
into the engine's candidate kernel, which decodes, intersects, unions,
meets the segment-bounded glob scope's allow-list *before* the
candidate budget (so the budget counts scoped candidates and
truncation can never drop in-scope rows), and caps, so doc ids never
materialize here until capped — apply the structural gates off the
rows' own stored facts (no per-candidate ``Path``) before any content
fetch, verify every candidate through the shared matcher (batched per
content batch on the backend-owned offload pool, the absolute wall
deadline crossing the hop), and union the flag-partitioned scan side
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
engines the re-read is a same-snapshot no-op. The overlay-emptiness
verdict follows the same discipline: the preamble's combined
pointer+EXISTS read is advisory — a non-empty verdict settles the
decision (the scan tier will run after the index tier, and no second
combined read is issued) — while skipping the scan is authorized only
by re-issuing the combined read *after* the candidate fetch it
vouches for. A rival
demotion committed before the fetch is committed before that read, so
the verdict sees it and the scan runs; a demotion committed after the
fetch means the fetch served the still-encoded row. Either way the
row is served with no isolation assumption, and the late read doubles
as the epoch recheck, so the skip path's statement count is unchanged.

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

from sqlalchemy import select

from vfs.models import Match, Observation
from vfs.models.code_grams import GramOr, build_code_gram_query
from vfs.models.postings import PostingCorruptionError
from vfs.native import extension
from vfs.paths import Path, normalize_ext_channel
from vfs.pattern_matching import (
    Body,
    PatternError,
    compile_filter,
    compile_verifier,
    expand_channel,
)
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.dialects import StaleSnapshot, arm_budget, byte_chunked, chunked
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.offload import VerifyOffload
from vfs.storage.backends.database.pathterms import allow_list_ids, compile_channel
from vfs.storage.backends.database.reads import (
    content_for_entries,
    effective_columns,
    kind_membership,
    pointer_with_overlay,
)
from vfs.storage.backends.database.scope import (
    CHANNEL_ARM_BINDS,
    FETCH_RIDE,
    Pushdown,
    entries_for_scan,
    passes_gates,
    pushdown_terms,
)
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.code_grams import GramKey, GramQuery
    from vfs.models.rows import VFSTables
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

# Scoped-defer pricing, measured on the linux-scale store: ~75 µs to fetch
# and verify one candidate, ~0.055 µs per posting byte fetched+decoded+
# intersected, ~500 µs of statement setup per AND-group.
_CANDIDATE_COST_US: Final = 75.0
_POSTING_COST_US_PER_BYTE: Final = 0.055
_GROUP_SETUP_US: Final = 500.0

_REFINE_GUIDANCE: Final = "narrow the pattern, add globs or ext filters, or scope with paths"


DocIds = Annotated[list[int], "sorted entries-table surrogate ids - the posting doc ids"]


class PostingMeta(NamedTuple):
    """One posting row's price-list facts: priced before any blob is fetched."""

    doc_count: int
    byte_size: int


async def grep_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    executor: Executor,
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
    try:
        admissions = expand_channel("globs", globs)
        exclusions = expand_channel("globs_not", globs_not)
    except PatternError as exc:
        return Result(ops=("grep",), errors=[ResultError(kind=VFSErrorKind.invalid, message=str(exc))])
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
    gates = [compile_filter(glob, ()) for glob in admissions]
    not_gates = [compile_filter(glob, ()) for glob in exclusions]
    wanted = normalize_ext_channel(ext)
    unwanted = normalize_ext_channel(ext_not)
    channel = compile_channel(admissions)
    gated = bool(gates or not_gates or wanted or unwanted)
    fetched = effective_columns(columns, content=columns is not None)
    deadline = monotonic() + wall_seconds
    # Channel fan in arms: the pruning loop spends one statement per arm
    # and the fetch one OR branch per arm, so both consumers share it.
    fan_arms = arm_budget(profile, parameter_budget, CHANNEL_ARM_BINDS)

    candidates: dict[str, RowMapping] = {}
    truncations: list[str] = []
    epoch: Epoch | None = None
    overlay_empty = False
    if not scan_all:
        epoch, overlay_empty = await pointer_with_overlay(session, tables)
        await seam("grep:after-pointer-read")
        # The allow-list joins nomination before the budget: the budget
        # counts scoped candidates, so truncation cannot drop in-scope rows.
        allow = await allow_list_ids(
            session,
            tables,
            membership_budget,
            channel,
            fan_arms=fan_arms,
            deadline=deadline,
        )
        if allow is not None and not allow:
            doc_ids: DocIds = []
            nominated_count = 0
        else:
            try:
                laddered = await _index_doc_ids(session, tables, membership_budget, epoch, plan, allow)
            except PostingCorruptionError as exc:
                error = ResultError(kind=VFSErrorKind.internal, message=f"grep posting blob is corrupt: {exc}")
                return Result(ops=("grep",), errors=[error])
            if laddered is None:
                # The ladder priced above verifying the whole scope: the
                # allow-list itself is the candidate set, a lawful superset.
                assert allow is not None
                doc_ids, nominated_count = allow[:CANDIDATE_BUDGET], len(allow)
            else:
                doc_ids, nominated_count = laddered
        if nominated_count > CANDIDATE_BUDGET and "candidate budget" not in truncations:
            truncations.append("candidate budget")
        pushdown = pushdown_terms(
            tables.entry, profile, fan_arms, membership_budget, channel, wanted, hide_meta=not gates
        )
        for mapping in await _entries_for_docs(session, tables, membership_budget, doc_ids, fetched, pushdown):
            if not gated or passes_gates(mapping, gates, not_gates, wanted, unwanted):
                candidates[mapping["path"]] = mapping
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")

    skip_verified = False
    if not truncations or truncations == ["candidate budget"]:
        remaining = CANDIDATE_BUDGET - len(candidates)
        if remaining <= 0:
            # The overlay was never consulted: freshly-written scan-side
            # entries are absent, and the record must say so by name.
            if "candidate budget" in truncations:
                truncations.remove("candidate budget")
            truncations.append("candidate budget, with the unindexed overlay not consulted")
        else:
            if not scan_all and overlay_empty:
                # The preamble verdict was advisory: the verdict that skips
                # the scan is read after the statements it vouches for.
                current, overlay_empty = await pointer_with_overlay(session, tables)
                if current != epoch:
                    raise StaleSnapshot("the gram-index epoch pointer moved mid-grep")
                skip_verified = overlay_empty
            if not overlay_empty:
                nominated, overflow = await entries_for_scan(
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
                if overflow and "candidate budget" not in truncations:
                    truncations.append("candidate budget")
                for mapping in nominated:
                    if not gated or passes_gates(mapping, gates, not_gates, wanted, unwanted):
                        candidates.setdefault(mapping["path"], mapping)
    if monotonic() > deadline and "wall-time budget" not in truncations:
        truncations.append("wall-time budget")
    if not scan_all and not skip_verified and await current_epoch(session, tables) != epoch:
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
    # Verify leaves the loop: each batch call runs on the backend-owned
    # pool, the absolute deadline crossing the hop (queue wait shortens
    # the budget, never the wall). Batches stay sequential by law.
    verify = VerifyOffload(verifier, executor)
    for batch in byte_chunked(ordered, _content_size, CONTENT_BYTE_BUDGET):
        if monotonic() > deadline:
            if "wall-time budget" not in truncations:
                truncations.append("wall-time budget")
            break
        ids = [m["entry_id"] for m in batch]
        contents = await content_for_entries(session, tables, profile, membership_budget, ids)
        paired = [(m, text) for m in batch if (text := contents.get(m["entry_id"])) is not None]
        if not paired:
            continue
        texts = [text for _, text in paired]
        if output_mode in ("files", "count"):
            cap = 1 if output_mode == "files" else max_count
            counts, completed = await verify.count_lines(texts, cap=cap, invert=invert_match, deadline=deadline)
            for (mapping, text), count in zip(paired, counts, strict=True):
                if count:
                    score = float(count) if output_mode == "count" else None
                    rows.append(_observe_hit(mapping, projected, mask, text, None, score, carry_content=carry_content))
        else:
            spans, completed = await verify.hit_lines(
                texts,
                before=before_context,
                after=after_context,
                cap=max_count,
                invert=invert_match,
                deadline=deadline,
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


async def _index_doc_ids(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    epoch: Epoch | None,
    plan: GramQuery,
    allow: DocIds | None,
) -> tuple[DocIds, int] | None:
    """At most ``CANDIDATE_BUDGET`` sorted candidate doc ids for *plan*
    under the caller-read *epoch*, plus the uncapped count.

    No published epoch means no encoded entries: the index side is
    empty and the scan side owns everything. The caller owns the epoch
    read — its post-ladder re-read is what detects a mid-call publish.
    The posting-byte budget is enforced before any blob fetch via the
    stored ``byte_size``.

    The ladder is priced before any blob is fetched: one metadata read
    covers every AND-group, the rarest-first choice fixes the byte bill,
    and when *allow* (the scoped allow-list) is cheaper to verify
    outright than that bill, the return is ``None`` — the caller takes
    the allow-list itself as the candidate set, a lawful superset. The
    chosen blobs then go to the engine's candidate kernel in one call:
    AND within each group rarest-first, OR across groups, the allow-list
    met, the cap applied — sub-millisecond even on the widest ladders,
    so the wall deadline is the fetches' concern, consulted by the
    caller after the ladder. A malformed blob raises
    :class:`PostingCorruptionError` with the codec's refusal.
    """
    if epoch is None:
        return [], 0
    groups = _plan_groups(plan)
    grams = sorted({gram for group in groups for gram in group})
    meta = await _posting_meta(session, tables, membership_budget, epoch, grams)
    chosen = _choose_grams(groups, meta)
    if allow is not None and _ladder_defers(chosen, meta, len(allow)):
        return None
    wanted = sorted({gram for group_chosen in chosen if group_chosen for gram in group_chosen})
    blobs = await _posting_blobs(session, tables, membership_budget, epoch, wanted)
    # None: a required gram indexes nothing, the group is empty. []: a
    # gramless group — it nominates nothing either way. Both drop here.
    fed = [[blobs[gram] for gram in group_chosen] for group_chosen in chosen if group_chosen]
    try:
        return extension().candidate_ids(fed, allow, CANDIDATE_BUDGET)
    except ValueError as exc:
        raise PostingCorruptionError(str(exc)) from exc


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
    pushdown: Pushdown,
) -> list[RowMapping]:
    """Candidate doc ids resolved to their live, encoded entry rows.

    The id-first shape: entry rows come back without content — the
    structural gates run before any content is fetched. ``size_bytes``
    always rides along (it prices the content batches), and ``ext`` and
    ``name`` ride for the string gate. *pushdown* carries its true bind
    spend, which shrinks the id chunk beside the statement's own base
    facts so the executed parameter count stays inside the budgets.
    """
    entry = tables.entry
    columns = [entry.c.entry_id, *(entry.c[field] for field in sorted((fetched | FETCH_RIDE) - {"content"}))]
    # The kind membership charges its element width; the encoded flag
    # renders as an inline literal on every dialect and binds nothing.
    kinds = kind_membership(entry)
    per_chunk = max(1, membership_budget - pushdown.binds - kinds.binds)
    rows: list[RowMapping] = []
    for chunk in chunked(doc_ids, per_chunk):
        stmt = select(*columns).where(entry.c.id.in_(chunk), entry.c.encoded, kinds.predicate, *pushdown.terms)
        rows.extend((await session.execute(stmt)).mappings())
    return rows


# ---------------------------------------------------------------------------
# The scan side — structural prefilter, bounded fetch, permanent overlay
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _content_size(mapping: RowMapping) -> int:
    """The verify batcher's exact metering: the row's stored byte size."""
    return mapping["size_bytes"] or 0


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
