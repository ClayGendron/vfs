"""Batch gram-index maintenance: assess the dirty, build postings, publish.

The rebuild verb's phases, each run by the backend in its own writer
transaction: re-derive per-entry state for entries whose rows no
longer reflect their content (semantic chunk rows for the embedding
pipeline, plus the ``indexable`` gram-eligibility stamp), build the
full posting set under a fresh epoch (invisible until published),
publish by flipping per-entry ``encoded`` flags and the current-epoch
pointer together, then reclaim dead epochs. Flag flips are
version-guarded but never attributed — a miss just leaves the row on
the scan side, which is always correct — while the epoch pointer flip
is a compare-and-set so concurrent rebuilders cannot publish over each
other.

Gram extraction is entry-grain: one pass over each entry's full folded
body, posted under the entry's surrogate row id, run by the active
engine behind the :mod:`vfs.native` seam (Rust where the extension is
present, the pure reference otherwise — byte-identical output either
way). The extraction invariant: **every trigram of the entry's folded
body is in the entry's posted gram set** — no split, cut, or dropped
span can remove a trigram from the nomination stream. Chunk rows are
semantic-only (vector/BM25 retrieval units) and no gram-path code reads
them; the lexical (BM25) index is built over them under the same epoch
(:mod:`~vfs.storage.backends.database.lexical`), so one publish and one
reclaim govern both indexes.

Eligibility gates bound index bloat, never coverage: an oversized,
gram-saturated, or sub-trigram body is stamped ``NOT indexable`` and
stays scan-side forever. (Binary bodies need no gate here — the entry
model refuses NUL content at the one write door.)

The flag algebra's invariant: **``encoded=True`` means nothing of the
row awaits the gram index: for a content row, its grams are present in
the current epoch; for a directory, which has nothing to index, it is
always true.** Every coverage exit demotes a content row's flag — a
content write resets both flags, and the delete claim demotes
``encoded`` as it stamps ``deleted_at`` — so no reachable state hides a
live or trashed row from both tiers: an uncovered content row is always
``NOT encoded``, which is exactly the scan side's partition. A directory
a store wrote false before this rule is repaired by its next rebuild
(:func:`collect_flag_drift`, :func:`repair_flag_drift`).

One rebuild runs at a time, arbitrated by a crash-safe lease on the
index-state row, which :mod:`~vfs.storage.backends.database.maintenance`
holds and whose phases claim, beat, fence and release it: the verb
claims it up front (a live rival refuses loudly, naming the running
lease's age), heartbeats it between phases, and releases it
best-effort at the end — a crashed run just stops
heartbeating, and the lease frees itself after the TTL with nothing
to clean up, because unpublished build rows are already inert. The
lease lives with the pointer on that row, apart from the admin lock,
and fences what the index rests on: a run whose lease was taken
commits no render landing, chunk pass, embed write or publish after
it. The build and the reclaims stay arbitrated by the epoch mint and
the live pointer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, Final, NamedTuple, cast

from sqlalchemy import bindparam, case, column, delete, func, insert, literal, or_, select, tuple_, update, values
from sqlalchemy.exc import IntegrityError

from vfs.batching import ByteBatcher, byte_chunked
from vfs.models.chunk import Chunk
from vfs.models.chunking import chunk_generation
from vfs.models.code_grams import GRAM_SIZE, distinct_gram_count, folded_bytes, normalize_content
from vfs.models.lexical import options_fingerprint
from vfs.models.links import link_generation
from vfs.models.postings import postings_builder
from vfs.models.rows import ENCODING_DELTA_VARINT
from vfs.offload import call_offloaded
from vfs.paths import Path
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.dialects import (
    StaleSnapshot,
    bulk_insert,
    chunked,
    is_unique_violation,
    statement_budget,
    supports_values_update,
)
from vfs.storage.backends.database.lexical import build_lexical_epoch
from vfs.storage.backends.database.links import LinkOutcome, LinkWork, extract_link_work, publish_links
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.reads import kind_membership
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

    from sqlalchemy import ColumnElement, Row, Select, Table, Update
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile

# The format half of the epoch fingerprint: every fold, extraction-grain,
# gram-extraction, or lexical-table change must hand-bump this to force the rebuild.
INDEX_FORMAT_VERSION: Final = 4

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

# The most entries one chunk-pass transaction holds: it bounds a foreground
# write's wait behind the pass and the slice's locks, never the dirty set.
CHUNK_SLICE_ENTRIES: Final = 256

# The most stored body one slice splits: exact bytes on SQL Server, encoding bytes on Postgres and MariaDB (exact where
# UTF-8), characters on Oracle and SQLite, within a factor of four everywhere; past it an entry is a slice of one.
CHUNK_SLICE_BYTES: Final = 1 << 20

_SCAN_YIELD_ROWS: Final = 256


def index_options_hash() -> str:
    """The options half of the epoch fingerprint; any change forces rebuild.

    The chunk generation is part of it: a bump re-splits every entry into fresh
    chunk ids, so the run that re-splits must also rebuild and publish.
    """
    grams = f"gram={GRAM_SIZE};fold=nl+turkic-i+casefold;bytes={MAX_INDEXABLE_BYTES};grams={MAX_DISTINCT_GRAMS}"
    return hashlib.sha256(f"{grams};{options_fingerprint()};chunks={chunk_generation()}".encode()).hexdigest()


@dataclass
class RebuildState:
    """Carry-over between the rebuild phases' separate transactions, for the run holding *token*'s lease."""

    token: str
    previous_epoch: Epoch | None = None
    epoch: Epoch | None = None
    covered: list[tuple[str, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase A — chunk the dirty
# ---------------------------------------------------------------------------


class _ChunkWork(NamedTuple):
    """One chunk pass's CPU product: flag pairs, resplit ids, fresh rows."""

    eligible: list[tuple[str, int]]
    ineligible: list[tuple[str, int]]
    resplit_ids: list[str]
    chunk_rows: list[dict[str, object]]
    links: list[LinkWork]


# A pass's link counts before its first slice commits.
_NO_LINKS: Final = LinkOutcome(0, 0, 0)


@dataclass
class ChunkCursor:
    """Where the sliced chunk pass stands between its slices' transactions.

    ``pending`` carries the candidates an earlier byte cut left, with their meters, at most one read's worth
    (fewer than :data:`CHUNK_SLICE_ENTRIES`), so each is measured once a pass; ``links`` sums the committed
    slices' link counts. A slice writes the ``next_*`` values, adopted once it commits, so a redrive re-reads
    from the same place.
    """

    stale: bool = False
    after: int = 0
    pending: list[Row[Any]] = field(default_factory=list)
    links: LinkOutcome = _NO_LINKS
    done: bool = False
    next_after: int = 0
    next_pending: list[Row[Any]] = field(default_factory=list)
    next_links: LinkOutcome = _NO_LINKS

    def adopt(self) -> None:
        """Take the committed slice's place, carried candidates and link counts as the pass's own."""
        self.after, self.pending, self.links = self.next_after, self.next_pending, self.next_links

    def links_record(self) -> list[ResultError]:
        """The pass's one info record of extracted references that name no live entry, when there are any."""
        sources, edges, unresolved = self.links
        if not unresolved:
            return []
        detail = f"{unresolved} markdown references across {sources} documents name no live entry"
        data = {"leg": "links", "sources": sources, "edges": edges, "unresolved": unresolved}
        return [classified(ErrorKind.not_found, severity=Severity.info, detail=detail, data=data)]


async def stale_generation(session: AsyncSession, tables: VFSTables) -> bool:
    """Whether any chunked row derives from another chunk or link generation — the generation law's probe, a
    lock-free read once a run, so a steady state's slices carry no generation term, which no index supports."""
    entry = tables.entry
    probe = select(literal(1)).where(entry.c.chunked, _stale_generation(entry)).limit(1)
    return (await session.execute(probe)).first() is not None


async def chunk_dirty(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    executor: Executor,
    *,
    cursor: ChunkCursor,
    carry_embeddings: bool = True,
) -> Result:
    """Re-derive per-entry state for the next slice of live content entries that are stale.

    One slice a transaction: the cursor's carried candidates, then the
    next entries past them, at most :data:`CHUNK_SLICE_ENTRIES` and no
    more than fit :data:`CHUNK_SLICE_BYTES` of the text the chunker will
    split, always at least one; the bodies are re-read by id under the
    same terms, so a carried meter can only mis-size a slice. The
    **generation law**: when the run's probe (:func:`stale_generation`)
    found a chunked row of another generation, the slice also reads those
    entries, each keeping its old chunk rows until its own slice replaces
    them; otherwise it reads ``NOT chunked`` alone. The
    **fingerprint-skip law**: an entry whose ``content_hash`` equals its
    stamped ``chunk_source_hash`` under the current generation keeps its
    chunk rows and only re-stamps its flags. Gram eligibility is stamped
    from the body just read, and ``chunked`` flips guarded on the version
    read and on the row being live, before any chunk or edge row is
    written, so the slice takes each entry's row before its derived rows,
    the purge's order; a guard miss leaves the entry dirty for the next
    run. The fresh chunk rows then replace the old; a rival chunk pass's
    rows met there raise :class:`StaleSnapshot`. The **extracted links**
    ride the slice: markdown bodies their stamp pair does not cover parse
    in the same offload hop, their out-edges are rewritten
    (:func:`~vfs.storage.backends.database.links.publish_links`), and the
    stamps flip with ``chunked``; the counts add to the cursor's.

    The CPU runs on the offload pool (:func:`~vfs.offload.call_offloaded`),
    inline only across a shutdown of the captured pool. Residency,
    honestly: a slice peaks at ~6.1x its content on the measured shapes
    (the chunk-insert executemany); an entry past the byte budget is a
    slice of one, its own body the bound — never a designed cap. **The
    chunk row is the embedding cache**: with *carry_embeddings* each
    re-split entry's stored vectors are carried onto the fresh rows with
    the same ``content_hash``.
    """
    entry, content, chunks = tables.entry, tables.content, tables.chunks
    generation = chunk_generation()
    links_generation = link_generation()
    awaiting = or_(~entry.c.chunked, _stale_generation(entry)) if cursor.stale else ~entry.c.chunked
    terms = [kind_membership(entry).predicate, entry.c.deleted_at.is_(None), awaiting]
    wanted = min(membership_budget, CHUNK_SLICE_ENTRIES) - len(cursor.pending)
    past = cursor.pending[-1].id if cursor.pending else cursor.after
    fresh = (await session.execute(_size_read(tables, profile, terms, past=past, wanted=wanted))).all()
    candidates = [*cursor.pending, *fresh]
    kept = _slice_ids(candidates)
    cursor.next_after, cursor.next_pending = kept[-1] if kept else cursor.after, candidates[len(kept) :]
    cursor.done, cursor.next_links = len(fresh) < wanted and not cursor.next_pending, cursor.links
    if not kept:
        return Result(ops=("rebuild",))
    dirty = (
        select(
            entry.c.entry_id,
            entry.c.version,
            entry.c.path,
            entry.c.ext,
            entry.c.content_hash,
            entry.c.chunk_source_hash,
            entry.c.chunk_generation,
            entry.c.link_source_hash,
            entry.c.link_generation,
            content.c.content,
        )
        .select_from(tables.content_joined())
        .where(membership(entry.c.id, kept, profile), *terms)
        .order_by(entry.c.id)
    )
    rows = (await session.execute(dirty)).all()
    await seam("rebuild:before-chunk-split")
    work = await call_offloaded(executor, partial(_assess_and_split, rows, generation, links_generation))
    await seam("rebuild:before-chunk-flip")
    provenance = {
        "chunk_source_hash": entry.c.content_hash,
        "chunk_generation": generation,
        "link_source_hash": entry.c.content_hash,
        "link_generation": links_generation,
    }
    stamp = {"chunked": True, "indexable": True, **provenance}
    await _flip_flags(session, entry, profile, parameter_budget, membership_budget, work.eligible, assignments=stamp)
    stamp = {"chunked": True, "indexable": False, **provenance}
    await _flip_flags(session, entry, profile, parameter_budget, membership_budget, work.ineligible, assignments=stamp)
    carried = await _carried_embeddings(session, chunks, work, profile, membership_budget) if carry_embeddings else {}
    for ids in chunked(work.resplit_ids, membership_budget):
        await session.execute(delete(chunks).where(membership(chunks.c.entry_id, ids, profile)))
    if work.chunk_rows:
        try:
            await bulk_insert(session, chunks, work.chunk_rows)
        except IntegrityError as exc:
            if not is_unique_violation(exc):
                raise
            raise StaleSnapshot("a rival chunk pass wrote the same entries' chunk rows") from exc
    if carried:
        await _carry_embeddings(session, chunks, work, carried)
    links = await publish_links(session, tables, profile, membership_budget, work.links)
    cursor.next_links = LinkOutcome(*(total + count for total, count in zip(cursor.links, links, strict=True)))
    return Result(ops=("rebuild",))


# ---------------------------------------------------------------------------
# Phase B — build the next epoch (or decide there is nothing to do)
# ---------------------------------------------------------------------------


async def build_epoch(session: AsyncSession, tables: VFSTables, state: RebuildState, executor: Executor) -> Result:
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
    byte-capped inserts. The lexical index builds under the same epoch
    after the postings drain, from the chunk rows of exactly the entries
    the posting scan covered, chosen by that set and never by their flags,
    so both indexes hold one set of entries whatever commits between the
    reads. The build's CPU — the fold-and-feed of each
    batch and every drain call — hops through the process's offload
    pool, so the loop keeps serving while the engine works — except
    across a shutdown of the captured pool, after which the
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
        return Result(ops=("rebuild",))
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
            await bulk_insert(
                session,
                tables.posting_list,
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
        await seam("rebuild:before-lexical")
        await build_lexical_epoch(session, tables, epoch, executor, covered)
        await session.execute(
            insert(tables.gram_epochs),
            [{"epoch": epoch, "format_version": INDEX_FORMAT_VERSION, "options_hash": index_options_hash()}],
        )
    except IntegrityError as exc:
        raise StaleSnapshot(f"a rival rebuild already built epoch {epoch}") from exc
    state.epoch = epoch
    return Result(ops=("rebuild",))


async def current_epoch(session: AsyncSession, tables: VFSTables) -> Epoch | None:
    """The published epoch pointer; ``None`` before the first publish."""
    pointer = select(tables.index_state.c.current_gram_epoch).where(tables.index_state.c.id == 1)
    return (await session.execute(pointer)).scalar_one_or_none()


async def pointer_with_overlay(session: AsyncSession, tables: VFSTables) -> tuple[Epoch | None, bool]:
    """The epoch pointer plus an overlay-emptiness verdict, one statement.

    Issued twice on the skip path, once when the preamble verdict is
    non-empty: the preamble read is advisory (non-empty settles it —
    the scan tier will run, and no second combined read is issued),
    while the authoritative post-fetch read's empty verdict alone
    permits skipping the scan — with results identical to scanning —
    and doubles as the epoch recheck. The predicate stays ORM-built — the
    negation renders as an inline literal on every dialect, which keeps
    the seek on the composite (encoded, kind) index reachable; the CASE
    wrapper is what lets engines without boolean select-list expressions
    (SQL Server) carry the EXISTS.
    """
    entry, state = tables.entry, tables.index_state
    pending = select(entry.c.id).where(~entry.c.encoded, kind_membership(entry).predicate).exists()
    stmt = select(state.c.current_gram_epoch, case((pending, 1), else_=0)).where(state.c.id == 1)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None, False
    pointer, has_pending = row
    return pointer, not has_pending


# ---------------------------------------------------------------------------
# Phase C — publish: encoded flips and the pointer CAS, one transaction
# ---------------------------------------------------------------------------


async def publish_epoch(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    state: RebuildState,
) -> Result:
    """Flip covered entries' ``encoded`` and the epoch pointer together.

    Both in one transaction: a flag flip published before the pointer
    would let a reader treat an entry as index-side while its grams are
    still invisible. The pointer flip is a CAS on the epoch this build
    started from and on the lease holder, so a rival publishing first,
    or a rival that claimed this run's lease, classifies as conflict and
    a run whose lease was taken publishes nothing.
    """
    entry, index = tables.entry, tables.index_state
    if state.covered:
        await _flip_flags(
            session, entry, profile, parameter_budget, membership_budget, state.covered, assignments={"encoded": True}
        )
    pointer = index.c.current_gram_epoch
    started = pointer.is_(None) if state.previous_epoch is None else pointer == state.previous_epoch
    cas = update(index).where(index.c.id == 1, started, index.c.lease_holder == state.token)
    result = cast("CursorResult[Any]", await session.execute(cas.values(current_gram_epoch=state.epoch)))
    if result.rowcount != 1:
        detail = f"rebuild lost the index publish race for epoch {state.epoch}"
        return Result(ops=("rebuild",), errors=[classified(ErrorKind.conflict, detail=detail)])
    return Result(ops=("rebuild",))


async def reclaim_epochs(session: AsyncSession, tables: VFSTables) -> Result:
    """Drop every epoch-scoped row — postings, lexical, fingerprint — strictly below the live pointer.

    The pointer is re-read inside this transaction, never taken from the
    caller's memory: reclaim runs after publish in its own transaction,
    and a rival publishing in that window would have its fresh epoch
    destroyed by a stale ``!= mine`` sweep. Strictly-below is safe under
    any interleaving — epochs are minted monotonically past every built
    number, so nothing at or above the live pointer is ever dead.
    """
    current = await current_epoch(session, tables)
    if current is None:
        return Result(ops=("rebuild",))
    for table in tables.epoch_scoped():
        await session.execute(delete(table).where(table.c.epoch < current))
    return Result(ops=("rebuild",))


async def reclaim_built_epoch(session: AsyncSession, tables: VFSTables, built: Epoch) -> Result:
    """Drop a build that lost its publish — never rows the pointer names."""
    current = await current_epoch(session, tables)
    if current == built:
        return Result(ops=("rebuild",))
    for table in tables.epoch_scoped():
        await session.execute(delete(table).where(table.c.epoch == built))
    return Result(ops=("rebuild",))


# ---------------------------------------------------------------------------
# Flag repair — directories a store wrote before they were created encoded
# ---------------------------------------------------------------------------


@dataclass
class FlagRebuildState:
    """Carry-over between the rebuild flag phases' separate transactions."""

    ids: list[str] = field(default_factory=list)
    repaired: int = 0

    @property
    def clean(self) -> bool:
        return not self.ids


async def collect_flag_drift(session: AsyncSession, tables: VFSTables, state: FlagRebuildState) -> Result:
    """Find the directory rows still flagged as awaiting the index.

    A plain read — no writer is blocked. On a store this rule wrote it
    is one seek on the (encoded, kind) index that returns nothing; on an
    earlier store it returns every directory once, the only time the
    result grows with the store.
    """
    entry = tables.entry
    scan = select(entry.c.entry_id).where(entry.c.kind == "directory", ~entry.c.encoded)
    async for row in await session.stream(scan.execution_options(yield_per=_SCAN_YIELD_ROWS)):
        state.ids.append(row.entry_id)
    return Result(ops=("rebuild",))


async def repair_flag_drift(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    state: FlagRebuildState,
) -> Result:
    """Flip the collected directories true, each guarded on still being an unencoded directory.

    Chunked by the membership budget, so no statement grows with the
    count. The guard keeps a row whose kind changed under its id from
    being stamped covered with no grams; the count of rows flipped is
    what the backend reports.
    """
    entry = tables.entry
    for chunk in chunked(sorted(state.ids), membership_budget):
        stmt = (
            update(entry)
            .where(membership(entry.c.entry_id, chunk, profile), entry.c.kind == "directory", ~entry.c.encoded)
            .values(encoded=True)
        )
        state.repaired += cast("CursorResult[Any]", await session.execute(stmt)).rowcount
    return Result(ops=("rebuild",))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stale_generation(entry: Table) -> ColumnElement[bool]:
    """A row's stored chunks or links derive from another generation than the running engine's."""
    generation, links_generation = chunk_generation(), link_generation()
    return or_(
        entry.c.chunk_generation.is_(None),
        entry.c.chunk_generation != generation,
        entry.c.link_generation.is_(None),
        entry.c.link_generation != links_generation,
    )


def _size_read(tables: VFSTables, profile: DialectProfile, terms: list[Any], *, past: int, wanted: int) -> Select[Any]:
    """The next *wanted* candidates past *past* with their meters: chosen in a derived table that carries the
    limit, and only then joined to their stored text and sized by the profile's stored-length function."""
    entry, content = tables.entry, tables.content
    picked = select(entry.c.id, entry.c.entry_id, entry.c.source, entry.c.size_bytes).where(entry.c.id > past, *terms)
    chosen = picked.order_by(entry.c.id).limit(wanted).subquery("candidates")
    stored = func.coalesce(getattr(func, profile.stored_length)(content.c.content), 0)
    meter = case((chosen.c.source == "bytes", stored), else_=chosen.c.size_bytes).label("meter")
    joined = chosen.outerjoin(content, content.c.entry_id == chosen.c.entry_id)
    return select(chosen.c.id, meter).select_from(joined).order_by(chosen.c.id)


def _slice_ids(candidates: Sequence[Any]) -> list[int]:
    """The leading candidates' ids while their running meter stays within the byte budget; the first always."""
    kept: list[int] = []
    total = 0
    for row in candidates:
        total += row.meter
        if kept and total > CHUNK_SLICE_BYTES:
            break
        kept.append(row.id)
    return kept


def _assess_and_split(rows: Sequence[Any], generation: str, links_generation: str) -> _ChunkWork:
    """The chunk pass's CPU pipeline, whole — runs on the offload pool.

    Assess eligibility and the fingerprint skip per row, split the
    remainder in byte-bounded batches, assemble the fresh chunk rows,
    and extract the markdown references the link stamps do not cover.
    Pure over its inputs: no session, no shared state.
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
    return _ChunkWork(eligible, ineligible, resplit_ids, chunk_rows, extract_link_work(rows, links_generation))


async def _carried_embeddings(
    session: AsyncSession, chunks: Table, work: _ChunkWork, profile: DialectProfile, membership_budget: int
) -> dict[str, list[float]]:
    """``content_hash → vector`` for the re-split entries' embedded rows whose hash a fresh row keeps."""
    wanted = {cast("str", row["content_hash"]) for row in work.chunk_rows}
    carried: dict[str, list[float]] = {}
    if not wanted:
        return carried
    for ids in chunked(work.resplit_ids, membership_budget):
        stmt = select(chunks.c.content_hash, chunks.c.embedding).where(
            membership(chunks.c.entry_id, ids, profile), chunks.c.embedding.isnot(None)
        )
        for row in await session.execute(stmt):
            if row.content_hash in wanted and row.content_hash not in carried:
                carried[row.content_hash] = list(row.embedding)
    return carried


async def _carry_embeddings(
    session: AsyncSession, chunks: Table, work: _ChunkWork, carried: dict[str, list[float]]
) -> None:
    """Land the carried vectors on the fresh rows by ``(entry, hash)`` — an UPDATE, never part of the bulk insert.

    The bulk insert may be a binary COPY, and a native vector column has
    no binary codec on that path; an executemany UPDATE binds the vector
    through the column's own type on every engine.
    """
    targets = {
        (cast("str", row["entry_id"]), cast("str", row["content_hash"]))
        for row in work.chunk_rows
        if cast("str", row["content_hash"]) in carried
    }
    stmt = (
        update(chunks)
        .where(chunks.c.entry_id == bindparam("b_entry"), chunks.c.content_hash == bindparam("b_hash"))
        .values(embedding=bindparam("b_vec"))
    )
    params = [{"b_entry": entry_id, "b_hash": digest, "b_vec": carried[digest]} for entry_id, digest in sorted(targets)]
    await session.execute(stmt, params)


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
    A flip lands only on a live row, since a delete's descendants and a
    restore's members change ``deleted_at`` with no version bump.
    """
    if not pairs:
        return
    live = entry.c.deleted_at.is_(None)
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
            await session.execute(update(entry).where(guard, live).values(**assignments))
        return
    stmt = (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_ver"), live)
        .values(**assignments)
    )
    await session.execute(stmt, [{"b_id": eid, "b_ver": ver} for eid, ver in pairs])


def _values_flip_stmt(entry: Table, rows: Sequence[tuple[str, int]], *, assignments: dict[str, Any]) -> Update:
    """One guarded flag stamp over a VALUES join carrying *rows*, landing on live rows alone."""
    incoming = values(
        column("v_id", entry.c.entry_id.type),
        column("v_ver", entry.c.version.type),
        name="incoming",
    ).data(list(rows))
    where = [entry.c.entry_id == incoming.c.v_id, entry.c.version == incoming.c.v_ver, entry.c.deleted_at.is_(None)]
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
