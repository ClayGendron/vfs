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

Every verb is set-based: it judges the whole batch against one bounded
fetch, then issues each kind of statement once per chunk of the batch,
so a 10,000-target call costs the same handful of round trips as a
one-target call on every engine.

Delete fetches one pre-batch committed snapshot for classification,
then walks targets in request order down the ladder the conformance
suite pins — root refusal, covered/repeat subsumption judged against
the snapshot, ``not_empty`` on ``cascade=False`` — and claims each
surviving target: ``deleted_at`` and ``trash_root_id`` (the row's own
id) on the row, guarded on its version, then the same stamp on every
live descendant of each claimed directory, each pointing at that root.
Path, parent, name, label, owner, postings and the fs mirror row are
untouched, and a descendant tombstoned earlier keeps its own root and
time. A tombstoned row in the snapshot reads as absent, and its refusal
carries the trashed hint.

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

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import bindparam, delete, func, select, update

from vfs.models import Observation
from vfs.paths import ROOT, TRASH_ROOT, Path
from vfs.results import ErrorKind, Result, ResultError, Severity, already_exists, classified
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    TRASH_ROOT_KEY,
    ancestor_chain,
    classify_miss,
    classify_misses,
    descendant_pattern,
    rows_by_path,
    subtree_filter,
    targets_with_ancestors,
    tombstone_side,
    tombstoned_roots,
    trashed_hint,
)
from vfs.storage.backends.database.dialects import StaleSnapshot, chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.serialized import (
    SNAPSHOT_COLUMNS,
    Claim,
    PendingRow,
    bump,
    bump_many,
    claim_rows,
    fetch_snapshot,
    final_rows,
    observe_final,
    point_row,
    serialize,
    snapshot_columns,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence

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
    parameter_budget: int,
    membership_budget: int,
    *,
    targets: list[Path],
    cascade: bool,
    authority: Authority | None,
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
) -> Result:
    """Adjudicate and apply a batch of deletes as a set.

    Misses, covered targets, and repeats are judged against the
    pre-batch committed snapshot — after an earlier target is tombstoned
    in-transaction, a live probe would blame the wrong path. The
    ``cascade=False`` occupancy check counts each directory target's
    live children once, in one chunked statement, and credits the
    children this batch claims ahead of it, so a target emptied earlier
    in the batch deletes cleanly. A tombstoned row in the snapshot is
    absent, and its miss carries the trashed hint. Each deleted row
    observes its pre-delete snapshot state plus the time of the delete.
    *authority* is accepted for signature parity; a delete changes no
    ownership. *gate* runs right after the serialization point, so its
    checks judge the state the batch will act on; any refusal fails the
    batch whole.

    Nothing is written until every target is judged: the claims run as
    one guarded set, the descendant stamps once per chunk of claimed
    directories, and each distinct parent is bumped once.
    """
    del authority
    entry = tables.entry
    await serialize(session, profile, tables.lock)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("delete",), errors=refused)
    snapshot = await fetch_snapshot(session, entry, profile, membership_budget, targets)
    await seam("delete:post-snapshot")
    live = {path: row for path, row in snapshot.items() if row["deleted_at"] is None}
    kinds = {path: row["kind"] for path, row in live.items()}
    tombstones = {path: row["deleted_at"] for path, row in snapshot.items() if row["deleted_at"] is not None}
    unique = set(targets)
    occupancy = Counter[str]()
    if not cascade:
        directories = [row["entry_id"] for row in live.values() if row["kind"] == "directory"]
        occupancy = await _live_child_counts(session, entry, profile, membership_budget, directories)
    now = datetime.now(UTC)
    seen: set[Path] = set()
    claims: list[RowMapping] = []
    emptied = Counter[str]()
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        if target == ROOT:
            errors.append(classified(ErrorKind.invalid, target, detail="the root directory cannot be deleted"))
            continue
        # A target inside another target's cascade — or a repeat — is
        # subsumed: judged against committed state, order-independent.
        covered = cascade and any(ancestor in unique for ancestor in ancestor_chain(target))
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
        if not cascade and occupancy[row["entry_id"]] > emptied[row["entry_id"]]:
            errors.append(classified(ErrorKind.not_empty, target))
            continue
        claims.append(row)
        emptied[row["parent_id"]] += 1
        rows.append(_observe_deleted(target, row, deleted_at=now))
    if errors:
        return Result(ops=("delete",), errors=errors)
    # The claim window: snapshot read, tombstones not yet set — a rival
    # child committing here bumps its parent and must flip the guard.
    await seam("delete:post-collect")
    refused = await _tombstone_roots(session, entry, profile, parameter_budget, membership_budget, claims, now)
    if refused is not None:
        return Result(ops=("delete",), errors=[refused])
    directories = [row for row in claims if row["kind"] == "directory"]
    await _tombstone_descendants(session, entry, profile, membership_budget, directories, now)
    await bump_many(session, entry, profile, membership_budget, [row["parent_id"] for row in claims])
    return Result(ops=("delete",), observations=rows)


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


class _RestoreLadder:
    """The restore ladder over one pre-batch fetch, carrying the batch's own revivals forward.

    Every target is judged against the fetched rows plus what earlier
    targets in the batch revived: a set revived earlier reads live for a
    later target — its root is ``exists``, its directories are live
    parents — so request order has exactly the effect a live-state
    ladder had, from one bounded fetch. Nothing unserialized can change
    what the ladder reads: a revive through ``write`` reaches only a
    file, and a file is never a parent.
    """

    def __init__(self, found: Mapping[str, RowMapping]) -> None:
        self._kinds = {path: row["kind"] for path, row in found.items() if row["deleted_at"] is None}
        self._tombstones = {path: row["deleted_at"] for path, row in found.items() if row["deleted_at"] is not None}
        self._sets: dict[str, list[RowMapping]] = defaultdict(list)
        for row in found.values():
            if row["trash_root_id"] is not None:
                self._sets[row["trash_root_id"]].append(row)
        self._revived: set[str] = set()

    def row(self, row: RowMapping | None) -> Mapping[Any, Any] | None:
        """*row* as the batch now sees it: live once its set was revived by an earlier target."""
        if row is None or row["trash_root_id"] not in self._revived:
            return row
        return {**row, "deleted_at": None, "trash_root_id": None}

    def verdict(self, target: Path, row: Mapping[Any, Any] | None) -> ResultError | None:
        """The ladder's refusal for *target*, or ``None`` when the row at it may be revived."""
        if row is None:
            return classify_miss(target, self._kinds, self._tombstones)
        if row["deleted_at"] is None:
            return already_exists(target)
        if row["trash_root_id"] != row["entry_id"]:
            hint = {**trashed_hint(row["deleted_at"]), TRASH_ROOT_KEY: row["trash_root_id"]}
            return classified(ErrorKind.not_found, target, detail="inside a deleted tree; restore its root", data=hint)
        if any(self._kinds.get(ancestor) != "directory" for ancestor in ancestor_chain(target)):
            return classify_miss(target, self._kinds, self._tombstones)
        return None

    def revive(self, root: Mapping[Any, Any]) -> None:
        """Record that *root*'s set is revived: every fetched member of it now reads live."""
        self._revived.add(root["entry_id"])
        for member in self._sets[root["entry_id"]]:
            self._kinds[member["path"]] = member["kind"]
            self._tombstones.pop(member["path"], None)


async def restore_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    targets: list[Path],
    authority: Authority | None,
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
    permit: Callable[[AsyncSession, Path, Mapping[str, Any] | None, ResultError | None], Awaitable[ResultError | None]]
    | None = None,
) -> Result:
    """Adjudicate and apply a batch of restores as a set, judged in request order.

    One bounded fetch brings every target, its ancestors and the root,
    tombstones included; the ladder judges each target against it and
    against what earlier targets in the batch revived. The per-target
    ladder: the row at the path (no row classifies through the descent
    ladder; a live row is ``exists``; a tombstone inside another root's
    set is ``not_found`` naming that root), then the live parent gate (a
    tombstoned ancestor is ``not_found`` at that component) — no
    statement runs until every target passes, and a refused row keeps
    its tombstone, since a failed batch never commits. *authority* is
    accepted for signature parity; a restore changes no ownership.
    *gate* runs once, right after the serialization point and before
    any row is looked up; *permit* then sees each target's row and the
    ladder's verdict, and its refusal wins — so a caller who may not
    see the row is answered before the ladder's wording could tell it
    anything.

    The claims run as one guarded set, each root's members clear once
    per chunk of roots, and each distinct parent is bumped once.
    """
    del authority
    entry = tables.entry
    await serialize(session, profile, tables.lock)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("restore",), errors=refused)
    columns = snapshot_columns(entry, _TOMBSTONE_COLUMNS)
    found = await rows_by_path(session, entry, targets_with_ancestors(targets), columns, profile, membership_budget)
    ladder = _RestoreLadder(found)
    pending: list[PendingRow] = []
    claims: list[RowMapping] = []
    errors: list[ResultError] = []
    for target in targets:
        fetched = found.get(str(target))
        row = ladder.row(fetched)
        verdict = ladder.verdict(target, row)
        if permit is not None and (refused := await permit(session, target, row, verdict)) is not None:
            errors.append(refused)
            continue
        if verdict is not None:
            errors.append(verdict)
            continue
        assert fetched is not None
        ladder.revive(fetched)
        claims.append(fetched)
        pending.append(PendingRow(target, "created", fetched["kind"], fetched["version"] + 1, fetched["size_bytes"]))
    if errors:
        return Result(ops=("restore",), errors=errors)
    # The claim window: ladder passed, tombstones not yet cleared — a
    # rival revive landing here bumps the row and flips the guard.
    await seam("restore:post-resolve")
    refused = await _revive_roots(session, entry, profile, parameter_budget, membership_budget, claims)
    if refused is not None:
        return Result(ops=("restore",), errors=[refused])
    await _revive_sets(session, entry, profile, membership_budget, [row["entry_id"] for row in claims])
    await bump_many(session, entry, profile, membership_budget, [row["parent_id"] for row in claims])
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
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
) -> Result:
    """Destroy at *path* — retention at the trash view's head, wholesale purge elsewhere.

    The head names the retention arm: every tombstoned root deleted
    more than *trash_days* ago purges with the rows sharing its root id,
    observed as deleted in path order; nothing tombstoned leaves nothing
    to do. The expired roots purge once per chunk of root ids and each
    distinct parent is bumped once, so the cost is flat in the number
    of roots. Every retention-arm sweep also reclaims content rows that
    reference no entry once they age past the orphan fence, each
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
    await serialize(session, profile, tables.lock)
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
    expired = (
        select(*snapshot_columns(entry))
        .where(entry.c.deleted_at < cutoff, tombstoned_roots(entry))
        .order_by(entry.c.path)
    )
    roots = (await session.execute(expired)).mappings().all()
    # A root revived by a rival write mid-purge is live again: the
    # tombstone proof misses it, and the redrive no longer finds it expired.
    still_tombstoned = tombstone_side(entry, trashed=True)
    for chunk in chunked([root["entry_id"] for root in roots], membership_budget):
        scope = membership(entry.c.trash_root_id, chunk, profile)
        await _purge(session, tables, profile, membership_budget, scope, proof=still_tombstoned)
    await bump_many(session, entry, profile, membership_budget, [root["parent_id"] for root in roots])
    rows = [_observe_deleted(Path._brand(root["path"]), root) for root in roots]
    notes = await _reclaim_orphan_content(session, tables, profile, membership_budget)
    return Result(ops=("sweep",), observations=rows, errors=notes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _live_child_counts(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, parent_ids: Iterable[str]
) -> Counter[str]:
    """Live children per parent id, one grouped count per chunk of parents.

    The ``cascade=False`` occupancy check: a count rather than an
    existence probe, so the children this batch claims ahead of a
    directory can be credited against it in request order.
    """
    counts = Counter[str]()
    for chunk in chunked(sorted(set(parent_ids)), membership_budget):
        stmt = (
            select(entry.c.parent_id, func.count())
            .where(membership(entry.c.parent_id, chunk, profile), tombstone_side(entry, trashed=False))
            .group_by(entry.c.parent_id)
        )
        for parent_id, count in await session.execute(stmt):
            counts[parent_id] = count
    return counts


async def _tombstone_roots(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    rows: Sequence[RowMapping],
    now: datetime,
) -> ResultError | None:
    """Mark every claimed row deleted — each its own root — guarded on the version the snapshot judged.

    Writes are not serialized with this verb, and every child create or
    update bumps its parent, so a rival committing between the snapshot
    and this claim flips the guard. The miss raises
    :class:`StaleSnapshot`; the verb redrives whole from a fresh
    snapshot, which is correctness by construction.

    Stamping ``deleted_at`` also demotes ``encoded``: the next index
    build excludes the row, so leaving the flag up would make the row
    invisible to both grep tiers when it comes back. Demoted, it is
    served scan-side immediately — the trash view included — and a
    restore or revive finds ``chunked & ~encoded``, already pending
    re-coverage.
    """
    claims = [Claim(row["entry_id"], row["version"]) for row in rows]
    assign = {"deleted_at": now, "trash_root_id": entry.c.entry_id, "encoded": False, "version": entry.c.version + 1}
    miss = "a rival write moved an entry past the delete's snapshot"
    side = tombstone_side(entry, trashed=False)
    return await claim_rows(
        session, entry, profile, parameter_budget, membership_budget, claims, side=side, assign=assign, miss=miss
    )


async def _tombstone_descendants(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    membership_budget: int,
    roots: Sequence[RowMapping],
    now: datetime,
) -> None:
    """Mark every live descendant of each claimed directory deleted under it — one statement per chunk of roots.

    Runs after the root claims. A descendant tombstoned earlier keeps
    its own root and time, so restore and sweep act on each delete's
    set alone. The statement sees the rows committed when it runs, so
    a child a rival landed after the snapshot rides with its parent; a
    rival landing afterwards finds its parent tombstoned at its own
    bump guard and redrives into a refusal.
    """
    if not roots:
        return
    stmt = (
        update(entry)
        .where(entry.c.path.like(bindparam("b_pattern"), escape=LIKE_ESCAPE), tombstone_side(entry, trashed=False))
        .values(deleted_at=now, trash_root_id=bindparam("b_root"), encoded=False)
    )
    params = [{"b_pattern": descendant_pattern(row["path"], profile), "b_root": row["entry_id"]} for row in roots]
    for chunk in chunked(params, membership_budget):
        await session.execute(stmt, chunk)


async def _revive_roots(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    rows: Sequence[RowMapping],
) -> ResultError | None:
    """Clear every claimed root's tombstone, guarded on the version the ladder judged.

    A rival revive through ``write`` bumps the row inside the window and
    flips the guard; the miss raises :class:`StaleSnapshot`, and the
    fresh ladder answers ``exists`` for the row now live.
    """
    claims = [Claim(row["entry_id"], row["version"]) for row in rows]
    assign = {"deleted_at": None, "trash_root_id": None, "version": entry.c.version + 1}
    miss = "a rival revived an entry past the restore's snapshot"
    side = tombstone_side(entry, trashed=True)
    return await claim_rows(
        session, entry, profile, parameter_budget, membership_budget, claims, side=side, assign=assign, miss=miss
    )


async def _revive_sets(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, root_ids: Sequence[str]
) -> None:
    """Clear the tombstone on every member of the claimed roots' sets — one statement per chunk, no version bump.

    Runs after the root claims, which already cleared each root's own
    ``trash_root_id``, so only the members still match.
    """
    for chunk in chunked(root_ids, membership_budget):
        stmt = (
            update(entry)
            .where(membership(entry.c.trash_root_id, chunk, profile))
            .values(deleted_at=None, trash_root_id=None)
        )
        await session.execute(stmt)


async def _purge(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    scope: ColumnElement[bool],
    *,
    proof: ColumnElement[bool] | None = None,
) -> None:
    """Hard-delete the rows *scope* names across every family table, chunked.

    Collection and deletion repeat until the scope reads empty: writes
    are not serialized with this verb, so a rival can commit a new child
    between the collecting select and the deletes — purging from that
    stale id list alone would leave the child an orphan row.

    Every entry delete re-proves *proof* beside the collected ids — a
    bind-free predicate, never the id list again — so a row that left
    the scope in the window is missed, not destroyed: the retention arm
    proves each row is still tombstoned, and a root a rival write
    revived between the collect and the delete survives. A shortfall
    raises :class:`StaleSnapshot` and the verb redrives. The wholesale
    arm passes no proof: nothing unserialized can move a row out of a
    subtree.

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
            stmt = delete(entry).where(membership(entry.c.entry_id, chunk, profile))
            if proof is not None:
                stmt = stmt.where(proof)
            result = cast("CursorResult[Any]", await session.execute(stmt))
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

    The orphan test is an anti-join over the whole body table — a body
    row is an orphan by the absence of its entry, which no index on the
    body row can witness — so each retention sweep scans ``vfs_content``
    and ``vfs_blobs`` end to end, inside the serialized transaction. On
    a corpus of many millions of bodies that scan is the sweep's
    dominant cost; the direction is to run the reclaim rarely, as its
    own maintenance verb, or to reclaim at purge time and retire the
    scan.
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


def _observe_deleted(target: Path, row: Mapping[Any, Any], *, deleted_at: datetime | None = None) -> Observation:
    return Observation(
        path=target,
        kind=row["kind"],
        size_bytes=row["size_bytes"],
        version=row["version"],
        status="deleted",
        deleted_at=deleted_at,
    )
