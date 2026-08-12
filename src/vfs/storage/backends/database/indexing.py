"""Batch gram-index maintenance: chunk the dirty, build postings, publish.

The reindex verb's phases, each run by the backend in its own writer
transaction: chunk entries whose rows no longer reflect their content,
build the full posting set under a fresh epoch (invisible until
published), publish by flipping per-entry ``encoded`` flags and the
current-epoch pointer together, then reclaim dead epochs. Flag flips
are version-guarded but never attributed — a miss just leaves the row
on the scan side, which is always correct — while the epoch pointer
flip is a compare-and-set so concurrent reindexers cannot publish over
each other.

Eligibility gates bound index bloat, never coverage: an oversized or
gram-saturated body is marked ``chunked`` with zero chunk rows and
stays scan-side forever. (Binary bodies need no gate here — the entry
model refuses NUL content at the one write door.)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any, Final, cast

from sqlalchemy import bindparam, delete, exists, insert, select, update

from vfs.models import CONTENT_KINDS
from vfs.models.chunk import Chunk
from vfs.models.code_grams import GRAM_SIZE, unique_code_grams
from vfs.models.postings import encode_postings
from vfs.models.rows import ENCODING_DELTA_VARINT
from vfs.paths import Path
from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.dialects import chunked

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables

INDEX_FORMAT_VERSION: Final = 1

Epoch = Annotated[int, "one published gram-index generation; a missing pointer means no index side"]

# Zoekt's ingestion gates, entry-level: an ineligible body never chunks
# and is served by the scan side forever — bloat bounds, not coverage.
MAX_INDEXABLE_BYTES: Final = 2 * 1024 * 1024
MAX_DISTINCT_GRAMS: Final = 20_000

_POSTING_BATCH_BYTES: Final = 1 << 20
_POSTING_ROW_BINDS: Final = 6


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
# Phase A — chunk the dirty
# ---------------------------------------------------------------------------


async def chunk_dirty(session: AsyncSession, tables: VFSTables, membership_budget: int) -> Result:
    """Re-chunk every live content entry whose chunks are stale.

    Per entry: apply the eligibility gates, replace its chunk rows with
    the fresh split (or none), and flip ``chunked`` guarded on the
    version the content was read at — a guard miss leaves the entry
    dirty for the next run, and its just-written chunks unused.
    """
    entry, content, chunks = tables.entry, tables.content, tables.chunks
    dirty = (
        select(entry.c.entry_id, entry.c.version, entry.c.path, entry.c.ext, content.c.content)
        .select_from(tables.content_joined())
        .where(entry.c.kind.in_(CONTENT_KINDS), entry.c.deleted_at.is_(None), ~entry.c.chunked)
        .order_by(entry.c.id)
    )
    rows = (await session.execute(dirty)).all()
    if not rows:
        return Result(ops=("reindex",))
    flips: list[dict[str, object]] = []
    chunk_rows: list[dict[str, object]] = []
    for row in rows:
        flips.append({"b_id": row.entry_id, "b_ver": row.version})
        if row.content is None or not _indexable(row.content):
            continue
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
            for piece in Chunk.split(file=Path(row.path), content=row.content, ext=row.ext)
        )
    for ids in chunked([flip["b_id"] for flip in flips], membership_budget):
        await session.execute(delete(chunks).where(chunks.c.entry_id.in_(ids)))
    if chunk_rows:
        await session.execute(insert(chunks), chunk_rows)
    flip = (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_ver"))
        .values(chunked=True)
    )
    await session.execute(flip, flips)
    return Result(ops=("reindex",))


# ---------------------------------------------------------------------------
# Phase B — build the next epoch (or decide there is nothing to do)
# ---------------------------------------------------------------------------


async def build_epoch(session: AsyncSession, tables: VFSTables, parameter_budget: int, state: ReindexState) -> Result:
    """Build the full posting set under a fresh epoch, or no-op.

    The no-op check: no live entry awaits encoding and the current
    epoch's two-part fingerprint matches. Anything else rebuilds whole —
    posting rows are a regenerable cache, and format or options drift is
    a drop-and-rebuild, never a migration. ``state.epoch`` stays ``None``
    on the no-op path.
    """
    entry, chunks = tables.entry, tables.chunks
    state.previous_epoch = await current_epoch(session, tables)
    if not await _work_pending(session, tables, state.previous_epoch):
        return Result(ops=("reindex",))
    epoch = (state.previous_epoch or 0) + 1
    scan = (
        select(chunks.c.id, chunks.c.content, entry.c.entry_id, entry.c.version)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(entry.c.chunked, entry.c.deleted_at.is_(None))
        .order_by(chunks.c.id)
    )
    postings: dict[int, list[int]] = {}
    covered: dict[str, int] = {}
    for row in (await session.execute(scan)).all():
        covered[row.entry_id] = row.version
        for gram in unique_code_grams(row.content, folded=True):
            postings.setdefault(gram, []).append(row.id)
    state.covered = list(covered.items())
    rows: list[tuple[dict[str, object], int]] = []
    for gram, doc_ids in sorted(postings.items()):
        blob = encode_postings(doc_ids)
        values: dict[str, object] = {
            "epoch": epoch,
            "gram_key": gram,
            "postings": blob,
            "encoding": ENCODING_DELTA_VARINT,
            "doc_count": len(doc_ids),
            "byte_size": len(blob),
        }
        rows.append((values, len(blob)))
    for batch in _byte_capped(rows, parameter_budget):
        await session.execute(insert(tables.posting_list), batch)
    await session.execute(
        insert(tables.gram_epochs),
        [{"epoch": epoch, "format_version": INDEX_FORMAT_VERSION, "options_hash": index_options_hash()}],
    )
    state.epoch = epoch
    return Result(ops=("reindex",))


async def current_epoch(session: AsyncSession, tables: VFSTables) -> Epoch | None:
    """The published epoch pointer; ``None`` before the first publish."""
    pointer = select(tables.meta.c.current_gram_epoch).where(tables.meta.c.id == 1)
    return (await session.execute(pointer)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Phase C — publish: encoded flips and the pointer CAS, one transaction
# ---------------------------------------------------------------------------


async def publish_epoch(session: AsyncSession, tables: VFSTables, state: ReindexState) -> Result:
    """Flip covered entries' ``encoded`` and the epoch pointer together.

    Both in one transaction: a flag flip published before the pointer
    would let a reader treat an entry as index-side while its grams are
    still invisible. The pointer flip is a CAS on the epoch this build
    started from; a rival publishing first classifies as conflict.
    """
    entry, meta = tables.entry, tables.meta
    if state.covered:
        flip = (
            update(entry)
            .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_ver"))
            .values(encoded=True)
        )
        await session.execute(flip, [{"b_id": eid, "b_ver": ver} for eid, ver in state.covered])
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


async def reclaim_epochs(session: AsyncSession, tables: VFSTables, current: Epoch) -> Result:
    """Drop every posting and fingerprint row outside the current epoch."""
    await session.execute(delete(tables.posting_list).where(tables.posting_list.c.epoch != current))
    await session.execute(delete(tables.gram_epochs).where(tables.gram_epochs.c.epoch != current))
    return Result(ops=("reindex",))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _indexable(content: str) -> bool:
    if len(content.encode("utf-8")) > MAX_INDEXABLE_BYTES:
        return False
    return len(unique_code_grams(content, folded=True)) <= MAX_DISTINCT_GRAMS


async def _work_pending(session: AsyncSession, tables: VFSTables, current: Epoch | None) -> bool:
    entry, chunks = tables.entry, tables.chunks
    if current is None:
        return True
    fingerprint = select(tables.gram_epochs.c.format_version, tables.gram_epochs.c.options_hash).where(
        tables.gram_epochs.c.epoch == current
    )
    row = (await session.execute(fingerprint)).one_or_none()
    if row is None or row._tuple() != (INDEX_FORMAT_VERSION, index_options_hash()):
        return True
    pending = select(
        exists().where(
            entry.c.chunked,
            ~entry.c.encoded,
            entry.c.deleted_at.is_(None),
            exists().where(chunks.c.entry_id == entry.c.entry_id),
        )
    )
    return bool((await session.execute(pending)).scalar_one())


def _byte_capped(rows: list[tuple[dict[str, object], int]], parameter_budget: int) -> list[list[dict[str, object]]]:
    """Slice posting rows by bind count and accumulated blob bytes."""
    max_rows = max(1, parameter_budget // _POSTING_ROW_BINDS)
    batches: list[list[dict[str, object]]] = []
    batch: list[dict[str, object]] = []
    batch_bytes = 0
    for values, size in rows:
        if batch and (len(batch) >= max_rows or batch_bytes + size > _POSTING_BATCH_BYTES):
            batches.append(batch)
            batch, batch_bytes = [], 0
        batch.append(values)
        batch_bytes += size
    if batch:
        batches.append(batch)
    return batches
