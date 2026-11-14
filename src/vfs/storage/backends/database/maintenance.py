"""The index maintenance pipeline and the index lease.

The phases a full pass runs and the lease one pass holds at a time, written
as functions over a :class:`MaintenanceContext` that the backend builds per pass.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from functools import partial
from time import time
from typing import TYPE_CHECKING, Any, Final, Protocol, TypeVar, cast

from sqlalchemy import or_, select, update
from ulid import ULID

from vfs.batching import byte_chunked
from vfs.offload import call_offloaded, offload_pool
from vfs.paths import Path
from vfs.rendering.seam import failure
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.dialects import BLOB_PAGE_BYTES
from vfs.storage.backends.database.edges import EdgeRebuildState, collect_edge_drift, repair_edge_drift
from vfs.storage.backends.database.embed import (
    EMBED_PAGE_ROWS,
    EmbedReport,
    cached_vectors,
    clear_embeddings,
    count_refused,
    count_unembedded,
    embed_page,
    read_identity,
    refusal_key,
    refused_paths,
    select_unembedded,
    write_vectors,
)
from vfs.storage.backends.database.indexing import (
    ChunkCursor,
    FlagRebuildState,
    RebuildState,
    build_epoch,
    chunk_dirty,
    collect_flag_drift,
    publish_epoch,
    reclaim_built_epoch,
    reclaim_epochs,
    repair_flag_drift,
    stale_generation,
)
from vfs.storage.backends.database.render import (
    RENDER_PAGE_ROWS,
    Rendered,
    RenderReport,
    cached_renderings,
    count_unrendered,
    land_renderings,
    load_blobs,
    render_rows,
    row_size,
    select_render_dirty,
)
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.segments import SegmentRebuildState, collect_segment_drift, repair_segment_drift
from vfs.storage.backends.database.signals import (
    collect_graph,
    compute_signal,
    publish_signal,
    sweep_undeclared_signals,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.rendering.registry import RendererRegistry
    from vfs.rendering.seam import RenderLimits
    from vfs.storage.backends.database.engine import EngineHost
    from vfs.storage.ranking import Ranker

T = TypeVar("T")

# Lease staleness horizon and beat interval: the beat task pulses every
# interval, so the TTL tolerates four missed beats plus clock skew.
INDEX_LEASE_TTL_MS: Final = 5 * 60 * 1000
INDEX_LEASE_HEARTBEAT_SECONDS: Final = 60.0

# The lease-lost verdict's machine-readable mark on its ``ResultError``.
LEASE_LOST_DATA: Final = {"index_lease": "lost"}


class _Runner(Protocol):
    async def __call__(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]], /) -> Result: ...


class _RowsRunner(Protocol):
    async def __call__(self, op: str, fn: Callable[[AsyncSession], Awaitable[T]], /) -> T: ...


@dataclass(frozen=True)
class MaintenanceContext:
    """The backend as the pipeline reads it: the host, the render and rank settings, the four runners.

    ``ranker`` is a getter, not a value: the signal phase calls it when
    it starts, so a ranker set while a pass runs is the one that phase reads.
    """

    host: EngineHost
    renderers: RendererRegistry
    render_limits: RenderLimits
    ranker: Callable[[], Ranker]
    embed_concurrency: int
    embed_timeout: float
    execute: _Runner
    execute_maintenance: _Runner
    execute_leased: _Runner
    rows: _RowsRunner


# ---------------------------------------------------------------------------
# The verb
# ---------------------------------------------------------------------------


async def rebuild(context: MaintenanceContext) -> Result:
    """The full pass over *context*: claim the lease, run the phases, fill the vectors, release."""
    tables = context.host.tables
    token = str(ULID())
    claimed = await context.execute_maintenance("rebuild", lambda session: claim_index_lease(session, tables, token))
    if not claimed.success:
        return claimed
    async with _held_index_lease(context, tables, token) as lost:
        result = await _rebuild_phases(context, tables, lost, token)
        if not result.success or context.host.embedder is None:
            return result
        embedded = await _embed_step(context, tables, lost, token)
        errors = [*result.errors, *embedded.errors]
        extras = {**(result.model_extra or {}), **(embedded.model_extra or {})}
        return Result(ops=result.ops, observations=result.observations, errors=errors, **extras)


# ---------------------------------------------------------------------------
# The index lease
# ---------------------------------------------------------------------------


async def claim_index_lease(session: AsyncSession, tables: VFSTables, token: str) -> Result:
    """Claim the index lease for *token*, or refuse naming the live run.

    One guarded UPDATE: the lease is free when the holder is NULL or the
    heartbeat is older than the TTL, so a crashed run frees itself by
    silence — there is no cleanup state. A zero-row claim means a rival
    is running; the refusal is the "rebuild in progress" signal, loud
    and retryable, carrying the running lease's heartbeat age.
    """
    lease = tables.index_state
    now = _now_ms()
    free = or_(lease.c.lease_holder.is_(None), lease.c.lease_heartbeat < now - INDEX_LEASE_TTL_MS)
    claim = update(lease).where(lease.c.id == 1, free).values(lease_holder=token, lease_heartbeat=now)
    if cast("CursorResult[Any]", await session.execute(claim)).rowcount == 1:
        return Result(ops=("rebuild",))
    held = (await session.execute(select(lease.c.lease_heartbeat).where(lease.c.id == 1))).scalar_one_or_none()
    age = max(0, now - held) // 1000 if held is not None else 0
    detail = f"a rebuild is already running (lease heartbeat {age}s ago); retry after it finishes"
    return Result(ops=("rebuild",), errors=[classified(ErrorKind.conflict, retryable=True, detail=detail)])


async def heartbeat_index_lease(session: AsyncSession, tables: VFSTables, token: str) -> Result:
    """Refresh *token*'s heartbeat; a miss means the lease was taken.

    A zero-row refresh means the lease expired mid-run and a rival
    claimed through. The beat task flags it and the run stops at the
    next phase boundary — the rival is rebuilding everything this run
    would have published — and every commit the index rests on ends
    with this same statement (:func:`lease_fenced`), so none lands.
    """
    lease = tables.index_state
    beat = update(lease).where(lease.c.id == 1, lease.c.lease_holder == token).values(lease_heartbeat=_now_ms())
    if cast("CursorResult[Any]", await session.execute(beat)).rowcount == 1:
        return Result(ops=("rebuild",))
    return lease_lost_result()


def lease_fenced(
    tables: VFSTables, token: str, fn: Callable[[AsyncSession], Awaitable[Result]]
) -> Callable[[AsyncSession], Awaitable[Result]]:
    """*fn*, then the lease's heartbeat as the same transaction's last statement.

    A run whose lease was taken commits nothing: the zero-row heartbeat
    answers the lease-lost verdict, carrying *fn*'s own records, and the
    runner rolls the whole transaction back. Once the heartbeat has run,
    a rival's claim waits on the index-state row until this transaction ends.
    """

    async def fenced(session: AsyncSession) -> Result:
        result = await fn(session)
        if not result.success:
            return result
        held = await heartbeat_index_lease(session, tables, token)
        return result if held.success else with_notes(held, list(result.errors))

    return fenced


def lease_lost_result() -> Result:
    """The one spelling of "a rival claimed through": conflict, retryable,
    marked in ``data`` so the beat task can tell it from a transport
    conflict (a writer stalled behind the build's own lock, on SQLite)."""
    detail = "the index lease expired mid-run and was claimed by a rival; this run stopped"
    error = classified(ErrorKind.conflict, retryable=True, detail=detail, data=LEASE_LOST_DATA)
    return Result(ops=("rebuild",), errors=[error])


def with_notes(result: Result, notes: list[ResultError]) -> Result:
    """*result* carrying *notes* — an earlier phase's advisory records — ahead of its own."""
    if not notes:
        return result
    return Result(ops=result.ops, observations=result.observations, errors=[*notes, *result.errors])


def lease_lost(result: Result) -> bool:
    """Whether *result* is the lease-lost verdict itself, not another conflict."""
    return any(error.data == LEASE_LOST_DATA for error in result.errors)


async def release_index_lease(session: AsyncSession, tables: VFSTables, token: str) -> Result:
    """Release *token*'s lease, best-effort; a taken lease is left alone.

    The TTL, not this release, is the liveness guarantee — a release
    that never runs (crash, transport loss) costs one TTL of refused
    rivals and nothing else.
    """
    lease = tables.index_state
    drop = update(lease).where(lease.c.id == 1, lease.c.lease_holder == token)
    await session.execute(drop.values(lease_holder=None, lease_heartbeat=None))
    return Result(ops=("rebuild",))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _held_index_lease(context: MaintenanceContext, tables: VFSTables, token: str) -> AsyncIterator[asyncio.Event]:
    """Hold a claimed lease: beat underneath, then cancel and release.

    The beat task is cancelled and awaited *before* the best-effort
    release, so a stray beat can never resurrect a released lease.
    The yielded event is set when a beat proves the lease taken.
    """
    lost = asyncio.Event()
    beat = asyncio.create_task(_beat_index_lease(context, tables, token, lost))
    try:
        yield lost
    finally:
        beat.cancel()
        with suppress(asyncio.CancelledError):
            await beat
        await context.execute_maintenance("rebuild", lambda session: release_index_lease(session, tables, token))


async def _beat_index_lease(context: MaintenanceContext, tables: VFSTables, token: str, lost: asyncio.Event) -> None:
    """Pulse the lease heartbeat until cancelled or proven taken.

    A transient beat failure is not a lost lease — the TTL absorbs
    missed pulses, including a beat that never reaches its UPDATE
    because the build phase holds SQLite's write lock for longer
    than the beat's retries (that exhaustion is a ``conflict`` too);
    only the zero-row refresh, the marked lease-lost verdict, means
    a rival claimed through, and then the run must stop.
    """
    while True:
        await asyncio.sleep(INDEX_LEASE_HEARTBEAT_SECONDS)
        beat = await context.execute_maintenance(
            "rebuild", lambda session: heartbeat_index_lease(session, tables, token)
        )
        if lease_lost(beat):
            lost.set()
            return


async def _rebuild_phases(context: MaintenanceContext, tables: VFSTables, lost: asyncio.Event, token: str) -> Result:
    """The lease-held phases: the renderings, the gram epochs, then the re-convergence passes.

    The render stage runs first so the chunk pass splits the text it
    wrote in the same run; its counts ride out as the ``rendering``
    extra, at warning severity when bytes rows remain pending. The
    segment pass rebuilds the path-segment postings and the edge
    pass re-converges the fs mirror to ``parent_id`` — each wholesale
    in effect, guarded delta in application: a plain read diffs the
    table against the recomputed truth, and only found drift opens a
    writer transaction, applied under per-row guards. Their warnings
    (drift is a maintenance bug surfacing) ride on the verb's final
    Result. The flag pass has the same shape and repairs the
    directories a store wrote before a directory was created encoded;
    it is the store predating a rule, not a bug, so it is reported
    once, as a count, never retryable.
    """
    rendered, report = await _render_step(context, tables, lost, token)
    if rendered is not None:
        return rendered
    result = await _gram_phases(context, tables, lost, token)
    if not result.success:
        return result
    warnings: list[ResultError] = []
    if report.unrendered:
        warnings.append(
            classified(
                ErrorKind.unavailable,
                severity=Severity.warning,
                detail=f"{report.unrendered} binaries are still pending a rendering; run rebuild again",
                retryable=True,
                data=report.as_extra(),
            )
        )
    segment_state = SegmentRebuildState()
    outcome = await _reconverge(
        context,
        lost,
        lambda session: collect_segment_drift(session, tables, segment_state),
        lambda session: repair_segment_drift(
            session, tables, context.host.profile, context.host.membership_budget, segment_state
        ),
        lambda: segment_state.clean,
    )
    if isinstance(outcome, Result):
        return outcome
    warnings.extend(outcome)
    edge_state = EdgeRebuildState()
    outcome = await _reconverge(
        context,
        lost,
        lambda session: collect_edge_drift(session, tables, edge_state),
        lambda session: repair_edge_drift(
            session, tables, context.host.profile, context.host.membership_budget, edge_state
        ),
        lambda: edge_state.clean,
    )
    if isinstance(outcome, Result):
        return outcome
    warnings.extend(outcome)
    flag_state = FlagRebuildState()
    outcome = await _reconverge(
        context,
        lost,
        lambda session: collect_flag_drift(session, tables, flag_state),
        lambda session: repair_flag_drift(
            session, tables, context.host.profile, context.host.membership_budget, flag_state
        ),
        lambda: flag_state.clean,
    )
    if isinstance(outcome, Result):
        return outcome
    if flag_state.repaired:
        predated = "predated the rule that a directory never awaits the gram index"
        warnings.append(
            classified(
                ErrorKind.internal,
                severity=Severity.warning,
                detail=f"{flag_state.repaired} directories {predated}; repaired",
                retryable=False,
                data={"directories": flag_state.repaired},
            )
        )
    outcome = await _signal_phase(context, tables, lost)
    if isinstance(outcome, Result):
        return outcome
    extras = {"rendering": report.as_extra()} if report.touched else {}
    if not warnings and not extras:
        return result
    return Result(ops=result.ops, observations=result.observations, errors=[*result.errors, *warnings], **extras)


async def _render_step(
    context: MaintenanceContext, tables: VFSTables, lost: asyncio.Event, token: str
) -> tuple[Result | None, RenderReport]:
    """Render every dirty bytes row in short, resumable pages under the held lease.

    Pages advance by keyset and are cut by bytes in flight; each cut
    borrows the settled renderings its hashes already have, reads the
    rest's blobs, renders them on the offload pool with no
    transaction open, and lands in one short write. The lease's
    ``lost`` flag is checked before every landing — a straggler never
    stamps over a rival's run — and a stage with nothing to land
    never consults it, so the phases after it still run. Answers the
    failing Result, or ``None`` with the stage's counts.
    """
    registry, limits = context.renderers, context.render_limits
    claims = registry.claims()
    profile, budget = context.host.profile, context.host.membership_budget
    report = RenderReport()
    last = 0
    while True:
        select_page = partial(select_render_dirty, tables=tables, claims=claims, after=last, limit=RENDER_PAGE_ROWS)
        page = await context.rows("rebuild", select_page)
        if not page:
            break
        last = page[-1].id
        for cut in byte_chunked(page, row_size, BLOB_PAGE_BYTES):
            lend = partial(
                cached_renderings,
                tables=tables,
                profile=profile,
                membership_budget=budget,
                hashes=[row.content_hash for row in cut],
                claims=claims,
            )
            cached = await context.rows("rebuild", lend)
            wanted = [row.entry_id for row in cut if row.key(registry) not in cached]
            fetch = partial(load_blobs, tables=tables, profile=profile, membership_budget=budget, entry_ids=wanted)
            blobs = await context.rows("rebuild", fetch) if wanted else {}
            await seam("rebuild:before-render")
            work = partial(render_rows, cut, blobs, registry, limits, cached)
            rendered = await call_offloaded(offload_pool(), work)
            await seam("rebuild:before-render-land")
            if lost.is_set():
                return lease_lost_result(), report
            refused = await _land(context, tables, rendered, report, token)
            if refused is not None:
                return refused, report
    report.unrendered = await context.rows("rebuild", partial(count_unrendered, tables=tables))
    return None, report


async def _land(
    context: MaintenanceContext, tables: VFSTables, rendered: list[Rendered], report: RenderReport, token: str
) -> Result | None:
    """Land one cut; a refused landing is retried row by row, and a row still refused lands as failed.

    One bad row — a value the engine will not take, whatever the seam
    missed — must not stop the stage or the phases after it: the
    row's rendering is replaced by a ``failed`` state naming the
    engine's refusal, which the skip law then leaves alone. Answers
    the failing Result only when even that state cannot land, and the
    lease-lost verdict at once: every landing is fenced by the lease.
    """
    host = context.host
    land = partial(land_renderings, tables=tables, profile=host.profile, membership_budget=host.membership_budget)

    def fenced(batch: list[Rendered]) -> Awaitable[Result]:
        landing = partial(land, rendered=batch, report=report)
        return context.execute_leased("rebuild", lease_fenced(tables, token, landing))

    outcome = await fenced(rendered)
    if lease_lost(outcome):
        return outcome
    if outcome.success or len(rendered) == 0:
        return None
    for item in rendered:
        single = await fenced([item])
        if lease_lost(single):
            return single
        if single.success:
            continue
        reason = "; ".join(error.message for error in single.errors) or "the engine refused the row"
        quarantined = item._replace(rendering=failure("failed", f"landing refused: {reason}"), cached=False)
        fallback = await fenced([quarantined])
        if not fallback.success:
            return fallback
    return None


async def _gram_phases(context: MaintenanceContext, tables: VFSTables, lost: asyncio.Event, token: str) -> Result:
    """The gram-index phases; a lost lease stops at the next boundary.

    The chunk pass's advisory records (the extractor's unresolved
    count) ride out on whatever Result the phases end with.
    """
    state = RebuildState(token=token)
    result = await _chunk_pass(context, tables, lost, token)
    if not result.success:
        return result
    notes = list(result.errors)
    if lost.is_set():
        return lease_lost_result()
    result = await context.execute_maintenance(
        "rebuild", lambda session: build_epoch(session, tables, state, offload_pool())
    )
    if not result.success or state.epoch is None:
        return with_notes(result, notes)
    await seam("rebuild:before-publish")
    if lost.is_set():
        return lease_lost_result()
    epoch = state.epoch
    result = await context.execute_leased(
        "rebuild",
        lambda session: publish_epoch(
            session, tables, context.host.profile, context.host.parameter_budget, context.host.membership_budget, state
        ),
    )
    if not result.success:
        # The lost build's rows are unpublished residue — reclaim them
        # so a rival's next mint is not forced past a dead number.
        await context.execute_maintenance("rebuild", lambda session: reclaim_built_epoch(session, tables, epoch))
        return result
    await seam("rebuild:before-reclaim")
    reclaimed = await context.execute_maintenance("rebuild", lambda session: reclaim_epochs(session, tables))
    return with_notes(reclaimed, notes)


async def _chunk_pass(context: MaintenanceContext, tables: VFSTables, lost: asyncio.Event, token: str) -> Result:
    """The chunk pass, one leased and fenced slice a transaction; the committed slices' link counts make one
    record, which rides on the pass's Result or on the first failing one."""
    host = context.host
    cursor = ChunkCursor(stale=await context.rows("rebuild", partial(stale_generation, tables=tables)))
    while not cursor.done:
        if lost.is_set():
            return with_notes(lease_lost_result(), cursor.links_record())
        work = partial(
            chunk_dirty,
            tables=tables,
            profile=host.profile,
            parameter_budget=host.parameter_budget,
            membership_budget=host.membership_budget,
            executor=offload_pool(),
            cursor=cursor,
            carry_embeddings=not host.embedding_stale,
        )
        sliced = await context.execute_leased("rebuild", lease_fenced(tables, token, work))
        if not sliced.success:
            return with_notes(sliced, cursor.links_record())
        cursor.adopt()
    return Result(ops=("rebuild",), errors=cursor.links_record())


async def _reconverge(
    context: MaintenanceContext,
    lost: asyncio.Event,
    collect: Callable[[AsyncSession], Awaitable[Result]],
    repair: Callable[[AsyncSession], Awaitable[Result]],
    clean: Callable[[], bool],
) -> Result | list[ResultError]:
    """One collect/repair pass: its warnings on success, the failing Result otherwise."""
    collected = await context.execute("rebuild", collect)
    if not collected.success:
        return collected
    if clean():
        return []
    if lost.is_set():
        return lease_lost_result()
    repaired = await context.execute_maintenance("rebuild", repair)
    if not repaired.success:
        return repaired
    return list(repaired.errors)


async def _signal_phase(context: MaintenanceContext, tables: VFSTables, lost: asyncio.Event) -> Result | None:
    """Store every declared prior under a fresh generation; signals no longer declared are swept.

    The graph is collected once in a read transaction; each signal
    computes off the event loop and publishes in its own write
    transaction, the lease's ``lost`` flag checked between them.
    """
    ranker = context.ranker()
    if ranker.signals:
        graph = await context.rows("rebuild", partial(collect_graph, tables=tables))
        for signal in ranker.signals:
            if lost.is_set():
                return lease_lost_result()
            values = await compute_signal(offload_pool(), graph, signal)
            generation = str(ULID())
            publish = partial(publish_signal, tables=tables, signal=signal, generation=generation, values=values)
            published = await context.execute_maintenance("rebuild", publish)
            if not published.success:
                return published
    declared = [signal.name for signal in ranker.signals]
    swept = await context.execute_maintenance(
        "rebuild", partial(sweep_undeclared_signals, tables=tables, profile=context.host.profile, declared=declared)
    )
    return None if swept.success else swept


async def _embed_step(context: MaintenanceContext, tables: VFSTables, lost: asyncio.Event, token: str) -> Result:
    """Fill every NULL embedding in short, resumable batches under the held lease.

    A stale stored identity is migrated first — every vector
    cleared, the pair unstamped — so the first batch written stamps
    the configured space. Pages advance by keyset; each page's
    batches embed with no transaction open and land in one short
    write; the lease's ``lost`` flag is checked between pages. A
    transient provider failure ends the step with a warning and
    leaves the rest NULL for the next run; a text refused for its
    input is recorded, skipped from then on, and named in one
    ``invalid`` warning, and the step moves on. The result's
    ``embedding`` extra reports the counts.
    """
    provider = context.host.embedder
    assert provider is not None
    identity = (provider.model_id, provider.dimension)
    # Re-read, never trusted from first touch: a rival's run may have stamped or migrated since.
    context.host.embedding_identity = await context.rows("rebuild", partial(read_identity, tables=tables))
    if context.host.embedding_identity is not None and context.host.embedding_identity != identity:
        migration = lease_fenced(tables, token, lambda session: clear_embeddings(session, tables))
        cleared = await context.execute_leased("rebuild", migration)
        if not cleared.success:
            return cleared
        context.host.embedding_identity = None
    report = EmbedReport()
    key = refusal_key(provider)
    refused_entries: list[str] = []
    listed: set[str] = set()
    refused_rows = 0
    semaphore = asyncio.Semaphore(context.embed_concurrency)
    known: dict[str, list[float]] = {}
    budget = context.host.membership_budget
    last = 0
    while not lost.is_set():
        unembedded = partial(
            select_unembedded,
            tables=tables,
            after=last,
            limit=EMBED_PAGE_ROWS,
            key=key,
            profile=context.host.profile,
        )
        page = await context.rows("rebuild", unembedded)
        if not page:
            break
        last = page[-1].id
        hashes = [row.content_hash for row in page if row.content_hash is not None and row.content_hash not in known]
        lend = partial(
            cached_vectors, tables=tables, profile=context.host.profile, hashes=hashes, membership_budget=budget
        )
        known.update(await context.rows("rebuild", lend))
        await seam("rebuild:before-embed")
        outcome = await embed_page(page, provider, known, report, semaphore, timeout=context.embed_timeout)
        # A recorded refusal stamps too: the canary proved the provider answers in its space.
        answered = bool(outcome.vectors or outcome.refused)
        stamp = identity if answered and context.host.embedding_identity is None else None
        land = partial(
            write_vectors,
            tables=tables,
            pairs=outcome.vectors,
            stamp=stamp,
            refused=[row.content_hash for row in outcome.refused if row.content_hash is not None],
            key=key,
            profile=context.host.profile,
            membership_budget=budget,
        )
        written = await context.execute_leased("rebuild", lease_fenced(tables, token, land))
        if not written.success:
            return written
        if answered:
            context.host.embedding_identity = identity
        refused_rows += len(outcome.refused)
        for row in sorted(outcome.refused):
            if len(refused_entries) >= EMBED_PAGE_ROWS:
                break
            if row.entry_id is not None and row.entry_id not in listed:
                listed.add(row.entry_id)
                refused_entries.append(row.entry_id)
        if outcome.failure is not None:
            report.stopped_by = f"{type(outcome.failure).__name__}: {outcome.failure}"
            break
    if lost.is_set():
        return lease_lost_result()
    report.unembedded = await context.rows("rebuild", lambda session: count_unembedded(session, tables, key))
    report.refused = await context.rows("rebuild", lambda session: count_refused(session, tables, key))
    errors: list[ResultError] = []
    if refused_rows:
        paths = await context.rows(
            "rebuild",
            partial(
                refused_paths,
                tables=tables,
                entry_ids=refused_entries,
                profile=context.host.profile,
                membership_budget=budget,
            ),
        )
        detail = (
            f"the provider refused {refused_rows} chunks; they stay unembedded until their text,"
            f" the model or its declared caps change: {report.refusal}"
        )
        errors.append(
            classified(
                ErrorKind.invalid,
                Path(paths[0]) if paths else None,
                severity=Severity.warning,
                detail=detail,
                data={"provider": provider.model_id, "refused": refused_rows, "paths": paths},
            )
        )
    if report.stopped_by is not None:
        errors.append(
            classified(
                ErrorKind.unavailable,
                severity=Severity.warning,
                detail=f"embedding stopped after {report.requests} answered requests: {report.stopped_by}",
                retryable=True,
                data={"provider": provider.model_id},
            )
        )
    return Result(ops=("rebuild",), errors=errors, embedding=report.as_extra(provider.model_id))


def _now_ms() -> int:
    """Wall-clock epoch milliseconds — the lease's cross-instance currency."""
    return int(time() * 1000)
