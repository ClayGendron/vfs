"""Trash-family statement builders for ``DatabaseStorage`` — delete,
restore, sweep.

A deleted row stays at its path with a tombstone: ``deleted_at`` and
``trash_root_id``, the row a delete named. The three verbs here set it,
clear it, and destroy what carries it. Each is a serialized verb
(``serialized.py``): its first statement takes the per-mount
serialization point, its claims are guarded on the version it judged,
and a guard miss redrives the whole verb from a fresh snapshot. Nothing
here rewrites a path, a parent pointer or a posting — that is
``topology.py``'s province — so permissions never notice a delete and
the postings never move.

Delete fetches one pre-batch committed snapshot for classification,
then walks targets in request order down the ladder the conformance
suite pins — root refusal, covered/repeat subsumption judged against
the snapshot, live ``not_empty`` on ``cascade=False`` — and marks each
surviving target with a tombstone: ``deleted_at`` and ``trash_root_id``
(the row's own id) on the row, guarded on its version, then the same
stamp on every live descendant in one statement, each pointing at that
root. Path, parent, name, label, owner, postings and the fs mirror row
are untouched, and a descendant tombstoned earlier keeps its own root
and time. A tombstoned row in the snapshot reads as absent, and its
refusal carries the trashed hint.

Restore clears the tombstone. It is addressed by the row's own path:
the row must be a tombstoned root (a row inside a tombstoned tree
refuses ``not_found`` naming the root that restores it), its parent must
be live (a tombstoned ancestor is ``not_found`` at that component, as
for every parent gate), and the site cannot be occupied — a live row at
the path is ``exists``. The clear is guarded on the root's version, then
the root's whole set clears by its id. The caller's permit sees the row
before any refusal is worded, so a caller who may not see it is
answered as if the target were absent.

Sweep is the only destroyer, and the address picks its arm. At the
trash view's head it reclaims every tombstoned root whose ``deleted_at``
has aged past the retention window, each with the rows sharing its
root id, through the purge arm; the retention arm also reclaims
orphaned content rows past an age fence, each surfacing as a warning.
At any other address sweep purges that subtree wholesale, immediately,
regardless of retention age — the root refuses ``invalid`` and a miss
classifies through the shared descent ladder.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, cast

from sqlalchemy import delete, select, update

from vfs.models import Observation
from vfs.paths import ROOT, TRASH_ROOT, Path
from vfs.results import ErrorKind, Result, ResultError, Severity, already_exists, classified
from vfs.storage.backends.database.descent import (
    TRASH_ROOT_KEY,
    classify_miss,
    classify_misses,
    descendant_filter,
    subtree_filter,
    trashed_hint,
)
from vfs.storage.backends.database.dialects import StaleSnapshot, chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.serialized import (
    SNAPSHOT_COLUMNS,
    PendingRow,
    bump,
    claim,
    dest_parent_id,
    fetch_snapshot,
    final_rows,
    observe_final,
    point_row,
    serialize,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Any

    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.engine import CursorResult, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile

# A restore target adds its root and what the caller's permit judges it by.
_TOMBSTONE_COLUMNS: Final[tuple[str, ...]] = (*SNAPSHOT_COLUMNS, "trash_root_id", "owner_id", "everyone_level")

# How old a content row with no entry must be before the retention sweep
# reclaims it — the field's standard age fence, sized conservatively.
_ORPHAN_AGE_FENCE: Final = timedelta(hours=24)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def delete_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    *,
    targets: list[Path],
    cascade: bool,
    authority: Authority | None,
    lock_key: int,
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
) -> Result:
    """Adjudicate and apply a batch of deletes as a set.

    Misses, covered targets, and repeats are judged against the
    pre-batch committed snapshot — after an earlier target is tombstoned
    in-transaction, a live probe would blame the wrong path — while the
    ``cascade=False`` occupancy check reads live state, so a target
    emptied earlier in the batch deletes cleanly. A tombstoned row in
    the snapshot is absent, and its miss carries the trashed hint. Each
    deleted row observes its pre-delete snapshot state plus the time of
    the delete. *authority* is accepted for signature parity; a delete
    changes no ownership. *gate* runs right after the serialization
    point, so its checks judge the state the batch will act on; any
    refusal fails the batch whole.
    """
    del authority
    entry = tables.entry
    await serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("delete",), errors=refused)
    snapshot = await fetch_snapshot(session, entry, profile, membership_budget, targets)
    await seam("delete:post-snapshot")
    live = {path: row for path, row in snapshot.items() if row["deleted_at"] is None}
    kinds = {path: row["kind"] for path, row in live.items()}
    tombstones = {path: row["deleted_at"] for path, row in snapshot.items() if row["deleted_at"] is not None}
    now = datetime.now(UTC)
    unique = set(targets)
    seen: set[Path] = set()
    rows: list[Observation] = []
    errors: list[ResultError] = []
    # Bumps this batch itself issued, by entry id: a later target's claim
    # guard expects its snapshot version plus exactly these.
    local_bumps = Counter[str]()
    for target in targets:
        if target == ROOT:
            errors.append(classified(ErrorKind.invalid, target, detail="the root directory cannot be deleted"))
            continue
        # A target inside another target's cascade — or a repeat — is
        # subsumed: judged against committed state, order-independent.
        covered = cascade and any(o != target and target.startswith(o + "/") for o in unique)
        if covered or target in seen:
            row = live.get(str(target))
            if row is None:
                errors.append(classify_miss(target, kinds, tombstones))
            else:
                rows.append(_observe_deleted(target, row, deleted_at=now))
            continue
        seen.add(target)
        row = live.get(str(target))
        if row is None:
            errors.append(classify_miss(target, kinds, tombstones))
            continue
        if not cascade and await _has_live_children(session, entry, row["entry_id"]):
            errors.append(classified(ErrorKind.not_empty, target))
            continue
        # The claim window: snapshot read, tombstone not yet set — a rival
        # child committing here bumps the row and must flip the guard.
        await seam("delete:post-collect")
        expected = row["version"] + local_bumps[row["entry_id"]]
        refused = await _tombstone_root(session, entry, profile, row, expected, now)
        if refused is not None:
            errors.append(refused)
            continue
        if row["kind"] == "directory":
            await _tombstone_descendants(session, entry, profile, str(target), row["entry_id"], now)
        await bump(session, entry, row["parent_id"])
        local_bumps[row["parent_id"]] += 1
        rows.append(_observe_deleted(target, row, deleted_at=now))
    if errors:
        return Result(ops=("delete",), errors=errors)
    return Result(ops=("delete",), observations=rows)


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


async def restore_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    *,
    targets: list[Path],
    authority: Authority | None,
    lock_key: int,
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
    permit: Callable[[AsyncSession, Path, RowMapping | None, ResultError | None], Awaitable[ResultError | None]]
    | None = None,
) -> Result:
    """Adjudicate and apply a batch of restores, target by target.

    Every check reads live state inside the serialized transaction, in
    request order — an earlier restore's effects are visible to later
    targets. The per-target ladder: the row at the path (no row
    classifies through the descent ladder; a live row is ``exists``; a
    tombstone inside another root's set is ``not_found`` naming that
    root), then the live parent gate (a tombstoned ancestor is
    ``not_found`` at that component) — no statement runs for a target
    until every check passes, and a refused row keeps its tombstone,
    since a failed batch never commits. *authority* is accepted for
    signature parity; a restore changes no ownership. *gate* runs once,
    right after the serialization point and before any row is looked
    up; *permit* then sees each target's row and the ladder's verdict,
    and its refusal wins — so a caller who may not see the row is
    answered before the ladder's wording could tell it anything.
    """
    del authority
    entry = tables.entry
    await serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("restore",), errors=refused)
    pending: list[PendingRow] = []
    errors: list[ResultError] = []
    for target in targets:
        row = await _tombstone_row(session, entry, str(target))
        verdict = await _restore_verdict(session, entry, profile, membership_budget, target, row)
        if permit is not None and (refused := await permit(session, target, row, verdict)) is not None:
            errors.append(refused)
            continue
        if verdict is not None:
            errors.append(verdict)
            continue
        assert row is not None
        # The claim window: ladder passed, tombstone not yet cleared — a
        # rival revive landing here bumps the row and flips the guard.
        await seam("restore:post-resolve")
        refused = await _revive_root(session, entry, profile, row)
        if refused is not None:
            errors.append(refused)
            continue
        await _revive_descendants(session, entry, row["entry_id"])
        await bump(session, entry, row["parent_id"])
        pending.append(PendingRow(target, "created", row["kind"], row["version"] + 1, row["size_bytes"]))
    if errors:
        return Result(ops=("restore",), errors=errors)
    finals = await final_rows(session, entry, profile, membership_budget, [str(p.path) for p in pending])
    rows = [observe_final(p, finals.get(str(p.path))) for p in pending]
    return Result(ops=("restore",), observations=rows)


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


async def sweep_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    *,
    path: Path,
    trash_days: int,
    authority: Authority | None,
    lock_key: int,
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
) -> Result:
    """Destroy at *path* — retention at the trash view's head, wholesale purge elsewhere.

    The head names the retention arm: every tombstoned root deleted
    more than *trash_days* ago purges with the rows sharing its root id,
    in path order, each observed as deleted; nothing tombstoned leaves
    nothing to do. Every retention-arm sweep also reclaims content rows
    that reference no entry once they age past the orphan fence, each
    surfacing as a warning. Any other address is the purge arm: the
    subtree purges wholesale regardless of retention age, live and
    tombstoned rows alike — the root refuses ``invalid`` and a miss
    classifies through the shared descent ladder. *authority* is
    accepted for signature parity; reclamation changes no ownership.
    """
    del authority
    entry = tables.entry
    if path == ROOT:
        fact = classified(ErrorKind.invalid, path, detail="the root directory cannot be swept")
        return Result(ops=("sweep",), errors=[fact])
    await serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("sweep",), errors=refused)
    if path != TRASH_ROOT:
        row = await point_row(session, entry, str(path))
        if row is None:
            misses = await classify_misses(session, entry, [path], profile, membership_budget)
            return Result(ops=("sweep",), errors=misses)
        await _purge(session, tables, profile, membership_budget, subtree_filter(entry, str(path), profile))
        await bump(session, entry, row["parent_id"])
        return Result(ops=("sweep",), observations=[_observe_deleted(path, row)])
    cutoff = datetime.now(UTC) - timedelta(days=trash_days)
    rows: list[Observation] = []
    columns = [entry.c[name] for name in SNAPSHOT_COLUMNS]
    expired = (
        select(*columns)
        .where(entry.c.deleted_at < cutoff, entry.c.trash_root_id == entry.c.entry_id)
        .order_by(entry.c.path)
    )
    for root in (await session.execute(expired)).mappings().all():
        await _purge(session, tables, profile, membership_budget, entry.c.trash_root_id == root["entry_id"])
        await bump(session, entry, root["parent_id"])
        rows.append(_observe_deleted(Path._brand(root["path"]), root))
    notes = await _reclaim_orphan_content(session, tables, profile, membership_budget)
    return Result(ops=("sweep",), observations=rows, errors=notes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _has_live_children(session: AsyncSession, entry: Table, entry_id: str) -> bool:
    # A one-row probe, not SELECT EXISTS(...) — T-SQL has no bare form.
    stmt = select(entry.c.id).where(entry.c.parent_id == entry_id, entry.c.deleted_at.is_(None)).limit(1)
    return (await session.execute(stmt)).first() is not None


async def _tombstone_root(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    row: RowMapping,
    expected_version: int,
    now: datetime,
) -> ResultError | None:
    """Mark the named row deleted — its own root — guarded on the version the batch expects.

    Writes are not serialized with this verb, and every child create or
    update bumps this row, so a rival committing between the snapshot
    and this claim flips the guard. *expected_version* is the snapshot
    version plus the bumps this batch itself already issued against the
    row. The miss raises :class:`StaleSnapshot`; the verb redrives whole
    from a fresh snapshot, which is correctness by construction.

    Stamping ``deleted_at`` also demotes ``encoded``: the next index
    build excludes this row, so leaving the flag up would make the row
    invisible to both grep tiers when it comes back. Demoted, it is
    served scan-side immediately — the trash view included — and a
    restore or revive finds ``chunked & ~encoded``, already pending
    re-coverage.
    """
    stmt = (
        update(entry)
        .where(entry.c.entry_id == row["entry_id"], entry.c.version == expected_version, entry.c.deleted_at.is_(None))
        .values(deleted_at=now, trash_root_id=row["entry_id"], encoded=False, version=entry.c.version + 1)
    )
    miss = "a rival write moved the entry past the delete's snapshot"
    return await claim(session, profile, stmt, entry.c.entry_id, miss=miss)


async def _tombstone_descendants(
    session: AsyncSession, entry: Table, profile: DialectProfile, root_path: str, root_id: str, now: datetime
) -> None:
    """Mark every live descendant deleted under *root_id* — one statement, whatever the subtree's size.

    Runs after the root claim. A descendant tombstoned earlier keeps
    its own root and time, so restore and sweep act on each delete's
    set alone. The statement sees the rows committed when it runs, so
    a child a rival landed after the snapshot rides with its parent; a
    rival landing afterwards finds its parent tombstoned at its own
    bump guard and redrives into a refusal.
    """
    stmt = (
        update(entry)
        .where(descendant_filter(entry, root_path, profile), entry.c.deleted_at.is_(None))
        .values(deleted_at=now, trash_root_id=root_id, encoded=False)
    )
    await session.execute(stmt)


async def _tombstone_row(session: AsyncSession, entry: Table, path: str) -> RowMapping | None:
    """The row at *path* on either side of the tombstone, with its root and what a permit judges it by."""
    columns = [entry.c[name] for name in _TOMBSTONE_COLUMNS]
    return (await session.execute(select(*columns).where(entry.c.path == path))).mappings().first()


async def _restore_verdict(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    target: Path,
    row: RowMapping | None,
) -> ResultError | None:
    """The restore ladder's refusal for *target*, or ``None`` when the row at it may be revived."""
    if row is None:
        return (await classify_misses(session, entry, [target], profile, membership_budget))[0]
    if row["deleted_at"] is None:
        return already_exists(target)
    if row["trash_root_id"] != row["entry_id"]:
        hint = {**trashed_hint(row["deleted_at"]), TRASH_ROOT_KEY: row["trash_root_id"]}
        return classified(ErrorKind.not_found, target, detail="inside a deleted tree; restore its root", data=hint)
    parent = await dest_parent_id(session, entry, target, profile, membership_budget)
    return parent if isinstance(parent, ResultError) else None


async def _revive_root(
    session: AsyncSession, entry: Table, profile: DialectProfile, row: RowMapping
) -> ResultError | None:
    """Clear the root's tombstone, guarded on the version the ladder judged.

    A rival revive through ``write`` bumps the row inside the window and
    flips the guard; the miss raises :class:`StaleSnapshot`, and the
    fresh ladder answers ``exists`` for the row now live.
    """
    stmt = (
        update(entry)
        .where(entry.c.entry_id == row["entry_id"], entry.c.version == row["version"], entry.c.deleted_at.is_not(None))
        .values(deleted_at=None, trash_root_id=None, version=entry.c.version + 1)
    )
    miss = "a rival revived the entry past the restore's snapshot"
    return await claim(session, profile, stmt, entry.c.entry_id, miss=miss)


async def _revive_descendants(session: AsyncSession, entry: Table, root_id: str) -> None:
    """Clear the tombstone on every row of the root's set but the root — one statement, no version bump."""
    stmt = (
        update(entry)
        .where(entry.c.trash_root_id == root_id, entry.c.entry_id != root_id)
        .values(deleted_at=None, trash_root_id=None)
    )
    await session.execute(stmt)


async def _purge(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    scope: ColumnElement[bool],
) -> None:
    """Hard-delete the rows *scope* names across every family table, chunked.

    Collection and deletion repeat until the scope reads empty: writes
    are not serialized with this verb, so a rival can commit a new child
    between the collecting select and the deletes — purging from that
    stale id list alone would leave the child an orphan row.

    Entry rows go first in every chunk, and the side tables follow the
    same id set only once the entry delete is verified: in the old
    side-tables-first order a rival's content replace could commit a
    fresh body row after this purge's content delete had already run —
    an orphan no re-collection ever sees. With the entry row gone
    first, a rival's guarded write misses and takes its own rows down
    with it; whatever side rows remain here were committed before the
    entry delete and are swept by the passes below.
    """
    entry = tables.entry
    edges = tables.edges
    while ids := [row.entry_id for row in await session.execute(select(entry.c.entry_id).where(scope))]:
        await seam("purge:post-collect")
        for chunk in chunked(ids, membership_budget):
            await seam("purge:pre-entry-delete")
            result = cast(
                "CursorResult[Any]",
                await session.execute(delete(entry).where(membership(entry.c.entry_id, chunk, profile))),
            )
            # Collected entries cannot vanish under the serialization
            # point; a shortfall (where rowcount is sane) is a stale list.
            if 0 <= result.rowcount != len(chunk):
                raise StaleSnapshot(f"purge lost {len(chunk) - result.rowcount} collected row(s) mid-transaction")
            await session.execute(delete(tables.content).where(membership(tables.content.c.entry_id, chunk, profile)))
            await session.execute(delete(tables.blobs).where(membership(tables.blobs.c.entry_id, chunk, profile)))
            await session.execute(delete(tables.versions).where(membership(tables.versions.c.entry_id, chunk, profile)))
            subjects = tables.version_subjects
            await session.execute(delete(subjects).where(membership(subjects.c.entry_id, chunk, profile)))
            await session.execute(delete(tables.chunks).where(membership(tables.chunks.c.entry_id, chunk, profile)))
            await session.execute(delete(tables.segments).where(membership(tables.segments.c.entry_id, chunk, profile)))
            # Two single-list deletes: one OR'd statement would carry the
            # chunk's binds twice, doubling past the tightest engine cap.
            await session.execute(delete(edges).where(membership(edges.c.source_id, chunk, profile)))
            await session.execute(delete(edges).where(membership(edges.c.target_id, chunk, profile)))


async def _reclaim_orphan_content(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int
) -> list[ResultError]:
    """Reclaim content rows that reference no entry, once past the age fence.

    The schema carries no foreign keys, so a body row orphaned before
    entry-first purge ordering landed — or by any residue an aborted
    transaction never cleaned — is unreachable by every path-addressed
    verb. The retention sweep drains them: rows older than the fence
    are deleted and each reclaim surfaces as a warning; younger rows
    survive until a later sweep, keeping any in-flight rival's freshly
    written body out of reach.
    """
    entry = tables.entry
    fence = datetime.now(UTC) - _ORPHAN_AGE_FENCE
    notes: list[ResultError] = []
    for body in (tables.content, tables.blobs):
        referenced = select(entry.c.id).where(entry.c.entry_id == body.c.entry_id)
        stmt = select(body.c.entry_id).where(~referenced.exists(), body.c.created_at < fence)
        orphans = sorted(row.entry_id for row in await session.execute(stmt))
        for chunk in chunked(orphans, membership_budget):
            await session.execute(delete(body).where(membership(body.c.entry_id, chunk, profile)))
        notes.extend(
            classified(
                ErrorKind.internal,
                detail=f"sweep reclaimed an orphaned {body.name} row for entry {entry_id}",
                severity=Severity.warning,
                data={"entry_id": entry_id},
            )
            for entry_id in orphans
        )
    return notes


def _observe_deleted(target: Path, row: RowMapping, *, deleted_at: datetime | None = None) -> Observation:
    return Observation(
        path=target,
        kind=row["kind"],
        size_bytes=row["size_bytes"],
        version=row["version"],
        status="deleted",
        deleted_at=deleted_at,
    )
