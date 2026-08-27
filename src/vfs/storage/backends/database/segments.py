"""Path-segment posting maintenance — the write-path mirror of the ``path`` column.

One posting row per (segment, entry_id), where the segments are the
entry's ancestor directory names — deduped, verbatim, leaf excluded
(the ``name`` column already serves it). The table belongs to the path
column's consistency domain: every verb that writes or rewrites a
``path`` extends its own transaction with the delta computed here, so
the postings mirror the column at every commit boundary — no flag, no
overlay arm, no staleness window. Every entry row of every kind carries
its postings, trash included; liveness stays a resolution-time concern.

The reindex verb re-converges the table to the recomputed segments of
every stored path — a drop-and-rebuild's end state, so drift can never
accumulate — but applied as guarded deltas rather than a wholesale
replace: :func:`collect_segment_drift` computes the difference from a
plain read, and :func:`repair_segment_drift` applies each entry's delta
only while the row still holds the path the delta was computed from
(the row is locked for the check). A guard miss skips the row — the
concurrent writer's synchronous maintenance is the truth — so writers
are never blocked corpus-wide and never reverted from a stale snapshot.
Found drift is repaired *and reported loudly*: it means a path-writing
verb failed to maintain its postings, and that bug must surface.

The collect pass holds the corpus's (entry_id, path) pairs and the full
posting set in memory — the same whole-corpus profile as the gram
build, acknowledged rather than capped; streamed merge passes are the
future direction if a deployment needs a tighter bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update

from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.dialects import bulk_insert, chunked

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables

# Rows the collect pass streams per fetch — bounds driver buffering, not memory.
_SCAN_YIELD_ROWS = 1024


# ---------------------------------------------------------------------------
# Segment derivation
# ---------------------------------------------------------------------------


def path_segments(path: str) -> frozenset[str]:
    """The ancestor directory names of *path* — deduped, leaf excluded.

    ``/a/b/c.txt`` yields ``{"a", "b"}``; a root-level path (and the
    root row itself) yields the empty set and stores no posting rows.
    """
    return frozenset(path.split("/")[1:-1])


def segment_rows(entry_id: str, path: str) -> list[dict[str, str]]:
    """The posting rows for one entry, sorted for deterministic statements."""
    return [{"segment": segment, "entry_id": entry_id} for segment in sorted(path_segments(path))]


# ---------------------------------------------------------------------------
# Write-path maintenance — creates and path rewrites
# ---------------------------------------------------------------------------


async def insert_postings(session: AsyncSession, segments: Table, entries: Iterable[tuple[str, str]]) -> None:
    """Insert the posting rows for freshly created ``(entry_id, path)`` rows.

    ``bulk_insert`` pages it under the dialect's parameter budget, like
    the content insert beside it. Entries with no ancestor directories
    contribute nothing.
    """
    rows = [row for entry_id, path in entries for row in segment_rows(entry_id, path)]
    if rows:
        await bulk_insert(session, segments, rows)


async def move_postings(
    session: AsyncSession,
    segments: Table,
    membership_budget: int,
    moves: Sequence[tuple[str, str, str]],
) -> None:
    """Apply the posting delta for rewritten paths: ``(entry_id, old, new)`` rows.

    Per row the delta is set arithmetic on the ancestor names — segments
    shared by both paths are untouched. A row whose delta is exactly one
    removed and one added name rides the rename fast path: an in-place
    ``UPDATE`` scoped to the (old, new) pair's entry ids, safe by
    construction because the removed name is absent from the new set and
    the added name absent from the old. Every other row's delta lands as
    per-segment ``DELETE``\\ s and one bulk insert. All membership
    predicates chunk by the declared budget.
    """
    updates: dict[tuple[str, str], list[str]] = {}
    removals: dict[str, list[str]] = {}
    additions: list[dict[str, str]] = []
    for entry_id, old_path, new_path in moves:
        old_segments = path_segments(old_path)
        new_segments = path_segments(new_path)
        removed = old_segments - new_segments
        added = new_segments - old_segments
        if len(removed) == 1 and len(added) == 1:
            pair = (next(iter(removed)), next(iter(added)))
            updates.setdefault(pair, []).append(entry_id)
        else:
            for segment in sorted(removed):
                removals.setdefault(segment, []).append(entry_id)
            additions.extend({"segment": segment, "entry_id": entry_id} for segment in sorted(added))
    for (old_segment, new_segment), ids in updates.items():
        for chunk in chunked(ids, membership_budget):
            stmt = (
                update(segments)
                .where(segments.c.segment == old_segment, segments.c.entry_id.in_(chunk))
                .values(segment=new_segment)
            )
            await session.execute(stmt)
    for segment, ids in removals.items():
        for chunk in chunked(ids, membership_budget):
            await session.execute(delete(segments).where(segments.c.segment == segment, segments.c.entry_id.in_(chunk)))
    if additions:
        await bulk_insert(session, segments, additions)


# ---------------------------------------------------------------------------
# Reindex re-convergence — collect drift, repair it under path guards
# ---------------------------------------------------------------------------


@dataclass
class SegmentRebuildState:
    """Carry-over between the reindex segment phases' separate transactions."""

    deltas: list[EntryDelta] = field(default_factory=list)
    orphans: dict[str, list[str]] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.deltas and not self.orphans


@dataclass
class EntryDelta:
    """One entry's posting drift, pinned to the path it was computed from."""

    entry_id: str
    path: str
    missing: list[str]
    excess: list[str]


async def collect_segment_drift(session: AsyncSession, tables: VFSTables, state: SegmentRebuildState) -> Result:
    """Diff the posting table against the recomputed segments of every path.

    A plain read — no writer is blocked. Each drifted entry's delta is
    recorded with the path it was computed from, which becomes the
    repair pass's guard; posting rows naming an entry id with no entry
    row at all are recorded as orphans (their guard is that absence).
    """
    entry, segments = tables.entry, tables.segments
    stored: dict[str, set[str]] = {}
    posting_scan = select(segments.c.segment, segments.c.entry_id).execution_options(yield_per=_SCAN_YIELD_ROWS)
    async for row in await session.stream(posting_scan):
        stored.setdefault(row.entry_id, set()).add(row.segment)
    entry_scan = select(entry.c.entry_id, entry.c.path).execution_options(yield_per=_SCAN_YIELD_ROWS)
    async for row in await session.stream(entry_scan):
        expected = path_segments(row.path)
        held = stored.pop(row.entry_id, set())
        missing = sorted(expected - held)
        excess = sorted(held - expected)
        if missing or excess:
            state.deltas.append(EntryDelta(row.entry_id, row.path, missing, excess))
    state.orphans = {entry_id: sorted(held) for entry_id, held in stored.items()}
    return Result(ops=("reindex",))


async def repair_segment_drift(
    session: AsyncSession, tables: VFSTables, membership_budget: int, state: SegmentRebuildState
) -> Result:
    """Apply the collected deltas, each guarded by the path it was computed from.

    The guard re-read locks the entry rows (``FOR UPDATE``), so a rival
    path rewrite serializes against this repair instead of interleaving
    with it. A delta whose row now holds a different path — or holds one
    where the orphan check expected none — is skipped: the rival's
    synchronous maintenance is the truth. Every applied repair surfaces
    as a warning: drift is a maintenance bug being surfaced, never
    silently absorbed.
    """
    entry, segments = tables.entry, tables.segments
    ids = [delta.entry_id for delta in state.deltas] + list(state.orphans)
    current: dict[str, str] = {}
    for chunk in chunked(ids, membership_budget):
        guard = select(entry.c.entry_id, entry.c.path).where(entry.c.entry_id.in_(chunk)).with_for_update()
        current.update({row.entry_id: row.path for row in await session.execute(guard)})
    confirmed = [delta for delta in state.deltas if current.get(delta.entry_id) == delta.path]
    orphaned = {entry_id: held for entry_id, held in state.orphans.items() if entry_id not in current}
    removals: dict[str, list[str]] = {}
    additions: list[dict[str, str]] = []
    for delta in confirmed:
        for segment in delta.excess:
            removals.setdefault(segment, []).append(delta.entry_id)
        additions.extend({"segment": segment, "entry_id": delta.entry_id} for segment in delta.missing)
    for entry_id, held in orphaned.items():
        for segment in held:
            removals.setdefault(segment, []).append(entry_id)
    for segment, segment_ids in removals.items():
        for chunk in chunked(segment_ids, membership_budget):
            await session.execute(delete(segments).where(segments.c.segment == segment, segments.c.entry_id.in_(chunk)))
    if additions:
        await bulk_insert(session, segments, additions)
    warnings = [_drift_warning(delta) for delta in confirmed]
    warnings.extend(_orphan_warning(entry_id, held) for entry_id, held in orphaned.items())
    return Result(ops=("reindex",), errors=warnings)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _drift_warning(delta: EntryDelta) -> ResultError:
    message = (
        f"Reindex repaired segment postings for entry {delta.entry_id} at {delta.path}: "
        f"{len(delta.missing)} missing, {len(delta.excess)} excess"
    )
    return ResultError(
        kind=VFSErrorKind.internal,
        message=message,
        severity=Severity.warning,
        data={"entry_id": delta.entry_id, "missing": delta.missing, "excess": delta.excess},
    )


def _orphan_warning(entry_id: str, held: list[str]) -> ResultError:
    message = f"Reindex reclaimed {len(held)} orphaned segment posting(s) for entry {entry_id}: no entry row"
    return ResultError(
        kind=VFSErrorKind.internal,
        message=message,
        severity=Severity.warning,
        data={"entry_id": entry_id, "excess": held},
    )
