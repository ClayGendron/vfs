"""Batch gram-index maintenance: assess the dirty, build postings, publish.

The reindex verb's phases, each run by the backend in its own writer
transaction: re-derive per-entry state for entries whose rows no
longer reflect their content (semantic chunk rows for the embedding
pipeline, plus the ``indexable`` gram-eligibility stamp), build the
full posting set under a fresh epoch (invisible until published),
publish by flipping per-entry ``encoded`` flags and the current-epoch
pointer together, then reclaim dead epochs. Flag flips are
version-guarded but never attributed — a miss just leaves the row on
the scan side, which is always correct — while the epoch pointer flip
is a compare-and-set so concurrent reindexers cannot publish over each
other.

Gram extraction is entry-grain: one pass over each entry's full folded
body, posted under the entry's surrogate row id, run by the active
engine behind the :mod:`vfs.native` seam (Rust where the extension is
present, the pure reference otherwise — byte-identical output either
way). The extraction invariant: **every trigram of the entry's folded
body is in the entry's posted gram set** — no split, cut, or dropped
span can remove a trigram from the nomination stream. Chunk rows are
semantic-only (vector/BM25 retrieval units) and no gram-path code reads
them.

Eligibility gates bound index bloat, never coverage: an oversized,
gram-saturated, or sub-trigram body is stamped ``NOT indexable`` and
stays scan-side forever. (Binary bodies need no gate here — the entry
model refuses NUL content at the one write door.)

The flag algebra's invariant: **``encoded=True`` implies the entry's
grams are present in the current epoch.** Every coverage exit demotes
the flag — a content write resets both flags, and the delete claim
demotes ``encoded`` as it stamps ``deleted_at`` — so no reachable state
hides a live or trashed row from both tiers: an uncovered row is always
``NOT encoded``, which is exactly the scan side's partition.

One reindex runs at a time, arbitrated by a crash-safe lease on the
meta row: the verb claims it up front (a live rival refuses loudly,
naming the running lease's age), heartbeats it between phases, and
releases it best-effort at the end — a crashed run just stops
heartbeating, and the lease frees itself after the TTL with nothing
to clean up, because unpublished build rows are already inert. The
lease is an arbiter, never a guard correctness depends on: if a phase
outlives the TTL and a rival claims through, the epoch mint collision
and the publish CAS still arbitrate exactly as they do today.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import partial
from time import time
from typing import TYPE_CHECKING, Annotated, Any, Final, NamedTuple, cast

from sqlalchemy import bindparam, column, delete, func, insert, literal, or_, select, tuple_, update, values
from sqlalchemy.exc import IntegrityError

from vfs.models.chunk import Chunk
from vfs.models.chunking import chunk_generation
from vfs.models.code_grams import GRAM_SIZE, distinct_gram_count, folded_bytes, normalize_content
from vfs.models.postings import postings_builder
from vfs.models.rows import ENCODING_DELTA_VARINT
from vfs.paths import Path
from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.dialects import (
    ByteBatcher,
    StaleSnapshot,
    byte_chunked,
    chunked,
    statement_budget,
    supports_values_update,
)
from vfs.storage.backends.database.offload import call_offloaded
from vfs.storage.backends.database.reads import kind_membership
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

    from sqlalchemy import Select, Table, Update
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile

# The format half of the epoch fingerprint: every fold, extraction-grain,
# or gram-extraction change must hand-bump this to force the rebuild.
INDEX_FORMAT_VERSION: Final = 2

Epoch = Annotated[int, "one published gram-index generation; a missing pointer means no index side"]

# Zoekt's ingestion gates, entry-level: an ineligible body is stamped
# NOT indexable and served by the scan side forever — bloat, not coverage.
MAX_INDEXABLE_BYTES: Final = 2 * 1024 * 1024
MAX_DISTINCT_GRAMS: Final = 20_000

# SQLAlchemy's insertmanyvalues splits by bind-parameter count but takes no
# position on blob payload bytes; this budget bounds one insert's payload.
_POSTING_BATCH_BYTES: Final = 1 << 20

# One engine feed's content payload; bounds what a single extraction call
# copies across the seam, independent of corpus size.
_EXTRACT_BATCH_BYTES: Final = 32 * 1024 * 1024

# One split call's content payload, the extract budget's twin: bounds the
# batch encode's transient (~0.4x content measured) — never a corpus cap.
_SPLIT_BATCH_BYTES: Final = 32 * 1024 * 1024

_SCAN_YIELD_ROWS: Final = 256

# Lease staleness horizon and beat interval: the beat task pulses every
# interval, so the TTL tolerates four missed beats plus clock skew.
REINDEX_LEASE_TTL_MS: Final = 5 * 60 * 1000
REINDEX_HEARTBEAT_SECONDS: Final = 60.0


def index_options_hash() -> str:
    """The options half of the epoch fingerprint; any change forces rebuild."""
    options = f"gram={GRAM_SIZE};fold=nl+turkic-i+casefold;bytes={MAX_INDEXABLE_BYTES};grams={MAX_DISTINCT_GRAMS}"
    return hashlib.sha256(options.encode()).hexdigest()


@dataclass
class ReindexState:
    """Carry-over between the reindex phases' separate transactions."""

    previous_epoch: Epoch | None = None
    epoch: Epoch | None = None
    covered: list[tuple[str, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The single-runner lease — claim, heartbeat, release
# ---------------------------------------------------------------------------


async def claim_reindex_lease(session: AsyncSession, tables: VFSTables, token: str) -> Result:
    """Claim the reindex lease for *token*, or refuse naming the live run.

    One guarded UPDATE: the lease is free when the holder is NULL or the
    heartbeat is older than the TTL, so a crashed run frees itself by
    silence — there is no cleanup state. A zero-row claim means a rival
    is running; the refusal is the "reindex in progress" signal, loud
    and retryable, carrying the running lease's heartbeat age.
    """
    meta = tables.meta
    now = _now_ms()
    free = or_(meta.c.reindex_holder.is_(None), meta.c.reindex_heartbeat < now - REINDEX_LEASE_TTL_MS)
    claim = update(meta).where(meta.c.id == 1, free).values(reindex_holder=token, reindex_heartbeat=now)
    if cast("CursorResult[Any]", await session.execute(claim)).rowcount == 1:
        return Result(ops=("reindex",))
    held = (await session.execute(select(meta.c.reindex_heartbeat).where(meta.c.id == 1))).scalar_one_or_none()
    age = max(0, now - held) // 1000 if held is not None else 0
    message = f"a reindex is already running (lease heartbeat {age}s ago); retry after it finishes"
    return Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)])


async def heartbeat_reindex_lease(session: AsyncSession, tables: VFSTables, token: str) -> Result:
    """Refresh *token*'s heartbeat; a miss means the lease was taken.

    A zero-row refresh means the lease expired mid-run and a rival
    claimed through. The beat task flags it and the run stops at the
    next phase boundary — the rival is rebuilding everything this run
    would have published, and the epoch machinery arbitrates whatever
    already landed.
    """
    meta = tables.meta
    beat = update(meta).where(meta.c.id == 1, meta.c.reindex_holder == token).values(reindex_heartbeat=_now_ms())
    if cast("CursorResult[Any]", await session.execute(beat)).rowcount == 1:
        return Result(ops=("reindex",))
    return lease_lost_result()


def lease_lost_result() -> Result:
    """The one spelling of "a rival claimed through": conflict, retryable."""
    message = "the reindex lease expired mid-run and was claimed by a rival; this run stopped"
    return Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)])


async def release_reindex_lease(session: AsyncSession, tables: VFSTables, token: str) -> Result:
    """Release *token*'s lease, best-effort; a taken lease is left alone.

    The TTL, not this release, is the liveness guarantee — a release
    that never runs (crash, transport loss) costs one TTL of refused
    rivals and nothing else.
    """
    meta = tables.meta
    drop = update(meta).where(meta.c.id == 1, meta.c.reindex_holder == token)
    await session.execute(drop.values(reindex_holder=None, reindex_heartbeat=None))
    return Result(ops=("reindex",))


# ---------------------------------------------------------------------------
# Phase A — chunk the dirty
# ---------------------------------------------------------------------------


class _ChunkWork(NamedTuple):
    """One chunk pass's CPU product: flag pairs, resplit ids, fresh rows."""

    eligible: list[tuple[str, int]]
    ineligible: list[tuple[str, int]]
    resplit_ids: list[str]
    chunk_rows: list[dict[str, object]]


async def chunk_dirty(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    executor: Executor,
) -> Result:
    """Re-derive per-entry state for every live content entry that is stale.

    Two laws govern the pass. The **generation law** first re-dirties every
    entry whose stored chunks derive from a different engine or grammar
    generation, so shapes from different splitters never silently coexist —
    guarded by a lock-free existence probe, because the re-dirty UPDATE has
    no supporting index and engines that scan-lock unindexed updates (the
    MySQL family under REPEATABLE READ) would otherwise hold next-key locks
    on every scanned row for the whole reindex transaction, even when the
    statement matches nothing. The steady state pays one consistent read
    and issues no UPDATE at all.
    The **fingerprint-skip law** then spares re-splitting: a dirty entry
    whose current ``content_hash`` equals its stamped ``chunk_source_hash``
    under the current generation keeps its chunk rows untouched — a
    same-body overwrite or restore re-splits nothing — and only re-stamps
    its flags. Every remaining body splits through byte-bounded batched
    engine calls; per entry the fresh chunk rows replace the old, gram
    eligibility is stamped from the body just read, and ``chunked`` flips
    guarded on the version the content was read at — a guard miss leaves
    the entry dirty for the next run, and its just-written state unused.

    The pass's CPU — eligibility assessment, the splits, and chunk-row
    assembly — runs whole on the backend's offload pool
    (:func:`~vfs.storage.backends.database.offload.call_offloaded`), so
    the event loop keeps serving concurrent callers for its duration —
    except across a close that shuts the captured pool mid-pass, after
    which the whole split runs inline, correct and classified.
    Residency profile, honestly: the dirty set's rows (bodies included)
    are materialized before the hop, and the pass peaks at ~6.1x dirty
    content on the measured shapes — set by the chunk-insert
    executemany, linear in the dirty set; the split batches bound only
    the batch encode's transient. A streaming per-sub-batch
    delete/insert flush is the future direction if a deployment needs
    a tighter bound; the profile is a recorded suboptimality, never a
    designed corpus cap.
    """
    entry, content, chunks = tables.entry, tables.content, tables.chunks
    generation = chunk_generation()
    stale = or_(entry.c.chunk_generation.is_(None), entry.c.chunk_generation != generation)
    probe = select(literal(1)).where(entry.c.chunked, stale).limit(1)
    if (await session.execute(probe)).first() is not None:
        await session.execute(update(entry).where(entry.c.chunked, stale).values(chunked=False))
    dirty = (
        select(
            entry.c.entry_id,
            entry.c.version,
            entry.c.path,
            entry.c.ext,
            entry.c.content_hash,
            entry.c.chunk_source_hash,
            entry.c.chunk_generation,
            content.c.content,
        )
        .select_from(tables.content_joined())
        .where(kind_membership(entry).predicate, entry.c.deleted_at.is_(None), ~entry.c.chunked)
        .order_by(entry.c.id)
    )
    rows = (await session.execute(dirty)).all()
    if not rows:
        return Result(ops=("reindex",))
    await seam("reindex:before-chunk-split")
    work = await call_offloaded(executor, partial(_assess_and_split, rows, generation))
    for ids in chunked(work.resplit_ids, membership_budget):
        await session.execute(delete(chunks).where(chunks.c.entry_id.in_(ids)))
    if work.chunk_rows:
        await session.execute(insert(chunks), work.chunk_rows)
    await seam("reindex:before-chunk-flip")
    provenance = {"chunk_source_hash": entry.c.content_hash, "chunk_generation": generation}
    stamp = {"chunked": True, "indexable": True, **provenance}
    await _flip_flags(session, entry, profile, parameter_budget, membership_budget, work.eligible, assignments=stamp)
    stamp = {"chunked": True, "indexable": False, **provenance}
    await _flip_flags(session, entry, profile, parameter_budget, membership_budget, work.ineligible, assignments=stamp)
    return Result(ops=("reindex",))


# ---------------------------------------------------------------------------
# Phase B — build the next epoch (or decide there is nothing to do)
# ---------------------------------------------------------------------------


async def build_epoch(session: AsyncSession, tables: VFSTables, state: ReindexState, executor: Executor) -> Result:
    """Build the full posting set under a fresh epoch, or no-op.

    The no-op check: no live entry awaits encoding and the current
    epoch's two-part fingerprint matches. Anything else rebuilds whole —
    posting rows are a regenerable cache, and format or options drift is
    a drop-and-rebuild, never a migration. ``state.epoch`` stays ``None``
    on the no-op path.

    The fresh epoch is minted past every *built* epoch, not just the
    published pointer, so a build that committed and then died before
    publishing never poisons the number line — its rows are skipped now
    and reclaimed once a later publish moves the pointer past them. A
    rival building the same number concurrently collides on the posting
    PK; that collision is a stale snapshot, redriven whole, and an
    exhausted redrive leaves as a clean ``conflict`` — driver text never
    reaches a public ``Result``.

    Extraction and posting encode run in the active engine
    (:mod:`vfs.native`): content streams through in bounded batches in
    ascending row-id order, and the builder's gram-ordered drain feeds
    byte-capped inserts. The build's CPU — the fold-and-feed of each
    batch and every drain call — hops through the backend's offload
    pool, so the loop keeps serving while the engine works — except
    across a close that shuts the captured pool, after which the
    remaining feeds and drains run inline, correct and classified.
    Peak build memory is the accumulated posting set — compressed
    delta blobs in the Rust engine, raw id lists in the pure fallback
    — held for the whole build and paid whenever any entry is dirty. A
    known
    suboptimality, deliberately not converted into a designed corpus
    cap; gram-range partitioned passes are the future direction if a
    deployment ever needs a tighter bound.
    """
    entry = tables.entry
    state.previous_epoch = await current_epoch(session, tables)
    if not await _work_pending(session, tables, state.previous_epoch):
        return Result(ops=("reindex",))
    built = (await session.execute(select(func.max(tables.gram_epochs.c.epoch)))).scalar_one()
    epoch = max(built or 0, state.previous_epoch or 0) + 1
    scan = (
        select(entry.c.id, entry.c.entry_id, entry.c.version, tables.content.c.content)
        .select_from(tables.content_joined())
        .where(entry.c.chunked, entry.c.indexable, entry.c.deleted_at.is_(None), tables.content.c.content.isnot(None))
        .order_by(entry.c.id)
    )
    builder = postings_builder()
    covered: dict[str, int] = {}
    # Content length in characters is the batch's byte proxy (exact for
    # ASCII-dominant code); the fold itself runs inside the hop.
    batcher: ByteBatcher[tuple[int, str]] = ByteBatcher(_doc_size, _EXTRACT_BATCH_BYTES)
    rows = await session.stream(scan.execution_options(yield_per=_SCAN_YIELD_ROWS))
    async for row in rows:
        covered[row.entry_id] = row.version
        full = batcher.add((row.id, row.content))
        if full is not None:
            await call_offloaded(executor, partial(_feed_docs, builder, full))
    final = batcher.flush()
    if final is not None:
        await call_offloaded(executor, partial(_feed_docs, builder, final))
    state.covered = list(covered.items())
    drain = partial(builder.next_batch, _POSTING_BATCH_BYTES)
    try:
        while (drained := await call_offloaded(executor, drain)) is not None:
            await session.execute(
                insert(tables.posting_list),
                [
                    {
                        "epoch": epoch,
                        "gram_key": gram,
                        "postings": blob,
                        "encoding": ENCODING_DELTA_VARINT,
                        "doc_count": doc_count,
                        "byte_size": len(blob),
                    }
                    for gram, blob, doc_count in drained
                ],
            )
        await session.execute(
            insert(tables.gram_epochs),
            [{"epoch": epoch, "format_version": INDEX_FORMAT_VERSION, "options_hash": index_options_hash()}],
        )
    except IntegrityError as exc:
        raise StaleSnapshot(f"a rival reindex already built epoch {epoch}") from exc
    state.epoch = epoch
    return Result(ops=("reindex",))


async def current_epoch(session: AsyncSession, tables: VFSTables) -> Epoch | None:
    """The published epoch pointer; ``None`` before the first publish."""
    pointer = select(tables.meta.c.current_gram_epoch).where(tables.meta.c.id == 1)
    return (await session.execute(pointer)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Phase C — publish: encoded flips and the pointer CAS, one transaction
# ---------------------------------------------------------------------------


async def publish_epoch(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    state: ReindexState,
) -> Result:
    """Flip covered entries' ``encoded`` and the epoch pointer together.

    Both in one transaction: a flag flip published before the pointer
    would let a reader treat an entry as index-side while its grams are
    still invisible. The pointer flip is a CAS on the epoch this build
    started from; a rival publishing first classifies as conflict.
    """
    entry, meta = tables.entry, tables.meta
    if state.covered:
        await _flip_flags(
            session, entry, profile, parameter_budget, membership_budget, state.covered, assignments={"encoded": True}
        )
    cas = (
        update(meta).where(meta.c.id == 1, meta.c.current_gram_epoch.is_(None)).values(current_gram_epoch=state.epoch)
        if state.previous_epoch is None
        else update(meta)
        .where(meta.c.id == 1, meta.c.current_gram_epoch == state.previous_epoch)
        .values(current_gram_epoch=state.epoch)
    )
    result = cast("CursorResult[Any]", await session.execute(cas))
    if result.rowcount != 1:
        message = f"reindex lost the epoch pointer race publishing epoch {state.epoch}"
        return Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.conflict, message=message)])
    return Result(ops=("reindex",))


async def reclaim_epochs(session: AsyncSession, tables: VFSTables) -> Result:
    """Drop every posting and fingerprint row strictly below the live pointer.

    The pointer is re-read inside this transaction, never taken from the
    caller's memory: reclaim runs after publish in its own transaction,
    and a rival publishing in that window would have its fresh epoch
    destroyed by a stale ``!= mine`` sweep. Strictly-below is safe under
    any interleaving — epochs are minted monotonically past every built
    number, so nothing at or above the live pointer is ever dead.
    """
    current = await current_epoch(session, tables)
    if current is None:
        return Result(ops=("reindex",))
    await session.execute(delete(tables.posting_list).where(tables.posting_list.c.epoch < current))
    await session.execute(delete(tables.gram_epochs).where(tables.gram_epochs.c.epoch < current))
    return Result(ops=("reindex",))


async def reclaim_built_epoch(session: AsyncSession, tables: VFSTables, built: Epoch) -> Result:
    """Drop a build that lost its publish — never rows the pointer names."""
    current = await current_epoch(session, tables)
    if current == built:
        return Result(ops=("reindex",))
    await session.execute(delete(tables.posting_list).where(tables.posting_list.c.epoch == built))
    await session.execute(delete(tables.gram_epochs).where(tables.gram_epochs.c.epoch == built))
    return Result(ops=("reindex",))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    """Wall-clock epoch milliseconds — the lease's cross-instance currency."""
    return int(time() * 1000)


def _assess_and_split(rows: Sequence[Any], generation: str) -> _ChunkWork:
    """The chunk pass's CPU pipeline, whole — runs on the offload pool.

    Assess eligibility and the fingerprint skip per row, split the
    remainder in byte-bounded batches, and assemble the fresh chunk
    rows. Pure over its inputs: no session, no shared state.
    """
    eligible: list[tuple[str, int]] = []
    ineligible: list[tuple[str, int]] = []
    resplit_ids: list[str] = []
    split_targets: list[Any] = []
    for row in rows:
        body_ok = row.content is not None and _indexable(row.content)
        (eligible if body_ok else ineligible).append((row.entry_id, row.version))
        skipped = (
            row.content_hash is not None
            and row.content_hash == row.chunk_source_hash
            and row.chunk_generation == generation
        )
        if skipped:
            continue
        resplit_ids.append(row.entry_id)
        if body_ok:
            split_targets.append(row)
    chunk_rows: list[dict[str, object]] = []
    # Content length in characters is the byte proxy — exact in the
    # ASCII-dominant regime; boundaries change nothing the splitter emits.
    for batch in byte_chunked(split_targets, _row_content_size, _SPLIT_BATCH_BYTES):
        batches = Chunk.split_batch([(Path(row.path), row.content, row.ext) for row in batch])
        chunk_rows.extend(
            {
                "entry_id": row.entry_id,
                "chunk_index": piece.chunk_index,
                "line_start": piece.line_start,
                "line_end": piece.line_end,
                "content_hash": piece.content_hash,
                "encoded": False,
                "content": piece.content,
            }
            for row, pieces in zip(batch, batches, strict=True)
            for piece in pieces
        )
    return _ChunkWork(eligible, ineligible, resplit_ids, chunk_rows)


def _row_content_size(row: Any) -> int:
    """The split batcher's metering: content length, chars as byte proxy."""
    return len(row.content)


def _doc_size(doc: tuple[int, str]) -> int:
    """The extract batcher's metering: content length, chars as byte proxy."""
    _row_id, content = doc
    return len(content)


def _feed_docs(builder: Any, batch: list[tuple[int, str]]) -> None:
    """Fold and feed one extract batch — the build's CPU, off the loop."""
    builder.add_docs([(row_id, folded_bytes(content)) for row_id, content in batch])


def _indexable(content: str) -> bool:
    data = normalize_content(content)
    if not (GRAM_SIZE <= len(data) <= MAX_INDEXABLE_BYTES):
        return False
    return distinct_gram_count(folded_bytes(content), MAX_DISTINCT_GRAMS) <= MAX_DISTINCT_GRAMS


async def _work_pending(session: AsyncSession, tables: VFSTables, current: Epoch | None) -> bool:
    if current is None:
        return True
    fingerprint = select(tables.gram_epochs.c.format_version, tables.gram_epochs.c.options_hash).where(
        tables.gram_epochs.c.epoch == current
    )
    row = (await session.execute(fingerprint)).one_or_none()
    if row is None or row._tuple() != (INDEX_FORMAT_VERSION, index_options_hash()):
        return True
    return (await session.execute(_pending_probe(tables.entry))).first() is not None


async def _flip_flags(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    pairs: list[tuple[str, int]],
    *,
    assignments: dict[str, Any],
) -> None:
    """Version-guarded set-based flag stamp; a miss leaves rows scan-side.

    Set-based on every declared engine — a VALUES join where the profile
    proves it, a row-constructor IN where tuples are accepted — because
    the per-pair executemany degrades to one round trip per row on the
    MySQL family and MSSQL. The executemany stays as the generic floor.
    """
    if not pairs:
        return
    dialect = session.get_bind().dialect
    if supports_values_update(profile, dialect):
        per_statement = statement_budget(
            lambda rows: _values_flip_stmt(entry, rows, assignments=assignments),
            pairs[0],
            dialect,
            parameter_budget=parameter_budget,
            row_width=2,
            row_cap=membership_budget,
        )
        for chunk in chunked(pairs, per_statement):
            await session.execute(_values_flip_stmt(entry, chunk, assignments=assignments))
        return
    if profile.tuple_in:
        for chunk in chunked(pairs, max(1, membership_budget // 2)):
            guard = tuple_(entry.c.entry_id, entry.c.version).in_(chunk)
            await session.execute(update(entry).where(guard).values(**assignments))
        return
    stmt = (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_ver"))
        .values(**assignments)
    )
    await session.execute(stmt, [{"b_id": eid, "b_ver": ver} for eid, ver in pairs])


def _values_flip_stmt(entry: Table, rows: Sequence[tuple[str, int]], *, assignments: dict[str, Any]) -> Update:
    """One guarded flag stamp over a VALUES join carrying *rows*."""
    incoming = values(
        column("v_id", entry.c.entry_id.type),
        column("v_ver", entry.c.version.type),
        name="incoming",
    ).data(list(rows))
    where = [entry.c.entry_id == incoming.c.v_id, entry.c.version == incoming.c.v_ver]
    return update(entry).where(*where).values(**assignments)


def _pending_probe(entry: Table) -> Select[tuple[int]]:
    """Row-presence probe for entries awaiting encoding, legal on every dialect.

    Kept as row presence — a bare ``SELECT EXISTS (...)`` is invalid
    T-SQL, where an EXISTS predicate may only sit inside a WHERE.
    """
    return (
        select(literal(1))
        .where(entry.c.chunked, ~entry.c.encoded, entry.c.indexable, entry.c.deleted_at.is_(None))
        .limit(1)
    )
