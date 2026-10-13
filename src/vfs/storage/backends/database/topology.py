"""Topology-family statement builders for ``DatabaseStorage`` — delete,
restore, sweep, move, copy.

Topology verbs rewrite the namespace's shape — parent pointers, path
caches, the segment postings that mirror the path column, and the
tombstone that hides a row — so every one of them serializes: its first
statement takes the per-mount serialization point (nothing on SQLite,
whose writer transaction is the lock; a transaction-scoped advisory lock
on Postgres; an X-lock on the single meta row everywhere else), and
every read runs after it inside the same transaction, so refusal checks
judge post-rival state and later targets see earlier targets' effects.
Writes are deliberately *not* serialized with topology, so every
reparent/claim/destroy statement is guarded on the row's version at
the probe that judged it: a rival write committing inside the window
bumps the row and flips the guard, and the verb redrives whole from a
fresh snapshot — re-collection is correctness by construction. The
same discipline covers a destination-address claim lost to an
unserialized rival: the unique violation redrives, and the fresh
ladder returns the honest per-pair refusal with the caller's own
attribution — never a classification off mid-race state, never raw
driver text. Every guard proves it matched through what the dialect
verifiably reports (rowcount where sane, RETURNING where modeled) or
refuses ``unsupported``.

Delete moves nothing. It fetches one pre-batch committed snapshot for
classification, then walks targets in request order down the ladder
the conformance suite pins — root refusal, covered/repeat subsumption
judged against the snapshot, live ``not_empty`` on ``cascade=False`` —
and marks each surviving target with a tombstone: ``deleted_at`` and
``trash_root_id`` (the row's own id) on the row, guarded on its version,
then the same stamp on every live descendant in one statement, each
pointing at that root. Path, parent, name, label, owner, postings and
the fs mirror row are untouched, so permissions never notice a delete,
and a descendant tombstoned earlier keeps its own root and time. A
tombstoned row in the snapshot reads as absent, and its refusal carries
the trashed hint.

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

Move and copy share one pair ladder, pinned row for row by the
conformance suite: batch-shape refusals against the committed snapshot, live
per-pair reads, no-replace ``exists`` before the cycle checks, cycle
before occupant kind translation (the Linux rename-trap ordering), and
a byte-budget overflow refusing the pair before any statement runs. A
tombstoned source is absent; a tombstoned occupant holds its address
and refuses ``exists`` with the trashed hint. A move is a reparent of
the root plus descendant path rewrites, tombstoned descendants riding
with their tree. A copy mints fresh ULIDs at version 1 for the live rows
alone, never copies edges or ``external_id``, and an overwritten
occupant keeps its identity as a material update. Any per-pair error
fails the batch whole; the runner never commits a failed result.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from sqlalchemy import Update, bindparam, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from vfs.authority import owner_for
from vfs.models import Observation
from vfs.paths import MAX_PATH_LENGTH, ROOT, TRASH_ROOT, Path, byte_length
from vfs.results import ErrorKind, Result, ResultError, Severity, already_exists, classified
from vfs.storage.backends.database.descent import (
    TRASH_ROOT_KEY,
    ancestor_chain,
    classify_miss,
    classify_misses,
    descendant_filter,
    rows_by_path,
    subtree_filter,
    targets_with_ancestors,
    trashed_hint,
)
from vfs.storage.backends.database.dialects import (
    BLOB_PAGE_BYTES,
    StaleSnapshot,
    bulk_insert,
    byte_chunked,
    chunked,
    rows_per_statement,
)
from vfs.storage.backends.database.edges import insert_fs_rows, repoint_fs_row
from vfs.storage.backends.database.labels import label_of, posture_beneath
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.segments import insert_postings, move_postings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Any

    from sqlalchemy import Column, ColumnElement, Delete, Table
    from sqlalchemy.engine import CursorResult, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.paths import ObjectKind
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.grants import PostureRows
    from vfs.storage.protocol import ResolvedPair

# The pre-batch committed snapshot: classification and observation state.
_SNAPSHOT_COLUMNS: Final[tuple[str, ...]] = (
    "entry_id",
    "parent_id",
    "path",
    "name",
    "kind",
    "version",
    "size_bytes",
    "deleted_at",
)

# A transfer subtree adds the material columns a copy reproduces.
_SUBTREE_COLUMNS: Final[tuple[str, ...]] = (
    *_SNAPSHOT_COLUMNS,
    "content_hash",
    "mime_type",
    "ext",
    "lines",
    "source",
    "render_status",
    "render_source_hash",
    "render_generation",
    "render_detail",
    "render_units",
    "media_width",
    "media_height",
)
# The copied material beyond the snapshot: every column a copy carries verbatim.
_COPIED_COLUMNS: Final[tuple[str, ...]] = _SUBTREE_COLUMNS[len(_SNAPSHOT_COLUMNS) :]

# A restore target adds its root and what the caller's permit judges it by.
_TOMBSTONE_COLUMNS: Final[tuple[str, ...]] = (*_SNAPSHOT_COLUMNS, "trash_root_id", "owner_id", "everyone_level")


class _PendingTransfer(NamedTuple):
    """One executed pair's observation, captured at execution time.

    Shared by restore and move/copy. The captured values are the
    fallback: after the loop every pending destination is re-read in one
    chunked pass and the final values win — a later pair may have bumped
    an earlier destination — but a destination a later pair moved away
    falls back to these.
    """

    dest: Path
    status: Literal["created", "unchanged"]
    kind: ObjectKind
    version: int
    size_bytes: int


# How old a content row with no entry must be before the retention sweep
# reclaims it — the field's standard age fence, sized conservatively.
_ORPHAN_AGE_FENCE: Final = timedelta(hours=24)
_PATH_BUDGET: Final = f"the path would exceed {MAX_PATH_LENGTH} bytes"


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
    await _serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("delete",), errors=refused)
    snapshot = await _fetch_snapshot(session, entry, profile, membership_budget, targets)
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
        await _bump(session, entry, row["parent_id"])
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
    await _serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("restore",), errors=refused)
    pending: list[_PendingTransfer] = []
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
        await _bump(session, entry, row["parent_id"])
        pending.append(_PendingTransfer(target, "created", row["kind"], row["version"] + 1, row["size_bytes"]))
    if errors:
        return Result(ops=("restore",), errors=errors)
    finals = await _final_rows(session, entry, profile, membership_budget, [str(p.dest) for p in pending])
    rows = [_observe_transfer(p, finals.get(str(p.dest))) for p in pending]
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
    await _serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=("sweep",), errors=refused)
    if path != TRASH_ROOT:
        row = await _point_row(session, entry, str(path))
        if row is None:
            misses = await classify_misses(session, entry, [path], profile, membership_budget)
            return Result(ops=("sweep",), errors=misses)
        await _purge(session, tables, profile, membership_budget, subtree_filter(entry, str(path), profile))
        await _bump(session, entry, row["parent_id"])
        return Result(ops=("sweep",), observations=[_observe_deleted(path, row)])
    cutoff = datetime.now(UTC) - timedelta(days=trash_days)
    rows: list[Observation] = []
    columns = [entry.c[name] for name in _SNAPSHOT_COLUMNS]
    expired = (
        select(*columns)
        .where(entry.c.deleted_at < cutoff, entry.c.trash_root_id == entry.c.entry_id)
        .order_by(entry.c.path)
    )
    for root in (await session.execute(expired)).mappings().all():
        await _purge(session, tables, profile, membership_budget, entry.c.trash_root_id == root["entry_id"])
        await _bump(session, entry, root["parent_id"])
        rows.append(_observe_deleted(Path._brand(root["path"]), root))
    notes = await _reclaim_orphan_content(session, tables, profile, membership_budget)
    return Result(ops=("sweep",), observations=rows, errors=notes)


# ---------------------------------------------------------------------------
# Move / copy
# ---------------------------------------------------------------------------


async def transfer_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    op: Literal["move", "copy"],
    operations: list[ResolvedPair],
    authority: Authority | None,
    lock_key: int,
    gate: Callable[[AsyncSession], Awaitable[list[ResultError]]] | None = None,
) -> Result:
    """Adjudicate and apply a batch of moves or copies, pair by pair.

    Batch-shape refusals — duplicate move sources, a source inside
    another moved source — are judged against the committed pre-batch
    snapshot so the outcome is order-independent; every other check
    reads live state inside the serialized transaction, so later pairs
    see earlier pairs' effects. The per-pair ladder runs in the order
    the conformance suite pins: overlap, source miss (a tombstoned
    source is absent, with the trashed hint), root, rename-to-self,
    destination parent gate, an occupied destination refuses ``exists``
    before the cycle check (no transfer replaces an occupant, a
    tombstoned one included — displacement is the caller's delete, then
    the transfer again; an ancestor is an occupant before it is a
    cycle), the into-itself cycle as ``invalid``, then destination
    byte-overflow — no statement runs for a pair until every check has
    passed.
    """
    entry = tables.entry
    await _serialize(session, profile, tables.meta, lock_key)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=(op,), errors=refused)
    move_srcs = Counter(pair.src for pair in operations) if op == "move" else Counter[Path]()
    committed: dict[str, RowMapping] = {}
    if op == "move":
        committed = await _fetch_snapshot(session, entry, profile, membership_budget, list(move_srcs))
    committed_kinds = {path: row["kind"] for path, row in committed.items() if row["deleted_at"] is None}
    tombstones = {path: row["deleted_at"] for path, row in committed.items() if row["deleted_at"] is not None}
    await seam("transfer:post-snapshot")
    now = datetime.now(UTC)
    pending: list[_PendingTransfer] = []
    errors: list[ResultError] = []
    for pair in operations:
        src, dest = pair.src, pair.dest
        if src != ROOT and (move_srcs[src] > 1 or _covering_ancestor(src, move_srcs) is not None):
            errors.append(_overlap_error(src, move_srcs, committed_kinds, tombstones))
            continue
        src_row = await _point_row(session, entry, str(src))
        if src_row is None or src_row["deleted_at"] is not None:
            errors.append((await classify_misses(session, entry, [src], profile, membership_budget))[0])
            continue
        if src == ROOT or dest == ROOT:
            detail = f"{op}: the root directory may be neither source nor destination"
            errors.append(classified(ErrorKind.invalid, src, target=dest, detail=detail))
            continue
        if dest == src:
            # POSIX rename-to-self: a successful no-op, never a refusal.
            pending.append(
                _PendingTransfer(dest, "unchanged", src_row["kind"], src_row["version"], src_row["size_bytes"])
            )
            continue
        dest_parent_id = await _dest_parent_id(session, entry, dest, profile, membership_budget)
        if isinstance(dest_parent_id, ResultError):
            errors.append(dest_parent_id)
            continue
        # The rename ladder: exists first (an ancestor destination always
        # exists), then the into-itself cycle — no arm replaces an occupant.
        occupant = await _point_row(session, entry, str(dest))
        if occupant is not None:
            errors.append(_occupied(dest, occupant, target=src))
            continue
        if dest.startswith(src + "/"):
            errors.append(classified(ErrorKind.invalid, src, target=dest, detail=f"{op} of a directory into itself"))
            continue
        subtree = await _fetch_subtree(session, tables, profile, str(src))
        if op == "copy":
            # A copy reproduces the live tree: a tombstoned descendant stays where it is, restorable.
            subtree = [row for row in subtree if row["deleted_at"] is None]
        new_paths = {row["entry_id"]: str(dest) + row["path"][len(str(src)) :] for row in subtree}
        if any(byte_length(path) > MAX_PATH_LENGTH for path in new_paths.values()):
            errors.append(classified(ErrorKind.unaddressable, dest, target=src, detail=_PATH_BUDGET))
            continue
        # The reverse-ordering window: subtree collected, claim not yet
        # taken — a rival committing here must flip the claim's guard.
        await seam("transfer:post-collect")
        postures = await posture_beneath(session, tables, profile, membership_budget, str(dest))
        if op == "move":
            error = await _execute_move(
                session, tables, profile, membership_budget, src_row, dest, dest_parent_id, postures, now, op=op
            )
            if error is not None:
                errors.append(error)
                continue
            version = src_row["version"] + 1
        else:
            await _execute_copy(
                session,
                tables,
                profile,
                parameter_budget,
                membership_budget,
                subtree=subtree,
                src_row=src_row,
                dest=dest,
                dest_parent_id=dest_parent_id,
                new_paths=new_paths,
                postures=postures,
                authority=authority,
                now=now,
            )
            version = 1
        pending.append(_PendingTransfer(dest, "created", src_row["kind"], version, src_row["size_bytes"]))
    if errors:
        return Result(ops=(op,), errors=errors)
    finals = await _final_rows(session, entry, profile, membership_budget, [str(p.dest) for p in pending])
    rows = [_observe_transfer(p, finals.get(str(p.dest))) for p in pending]
    return Result(ops=(op,), observations=rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _serialize(session: AsyncSession, profile: DialectProfile, meta: Table, lock_key: int) -> None:
    """Take the serialization point — always the verb's first statement.

    SQLite needs nothing: the writer connection already opened
    ``BEGIN IMMEDIATE``. Postgres takes a transaction-scoped advisory
    lock on the mount's key. Everywhere else a self-assignment UPDATE
    X-locks the single meta row — portable, auto-released at commit,
    serializing rival topology verbs and first touch alike.
    """
    if profile.name == "sqlite":
        return
    if profile.name == "postgresql":
        await session.execute(select(func.pg_advisory_xact_lock(lock_key)))
        return
    await session.execute(update(meta).where(meta.c.id == 1).values(schema_format_version=meta.c.schema_format_version))


async def _fetch_snapshot(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, targets: list[Path]
) -> dict[str, RowMapping]:
    """One bounded fetch: targets, their ancestors, the root — tombstones included, for the caller to judge."""
    columns = [entry.c[name] for name in _SNAPSHOT_COLUMNS]
    return await rows_by_path(session, entry, targets_with_ancestors(targets), columns, profile, membership_budget)


async def _has_live_children(session: AsyncSession, entry: Table, entry_id: str) -> bool:
    # A one-row probe, not SELECT EXISTS(...) — T-SQL has no bare form.
    stmt = select(entry.c.id).where(entry.c.parent_id == entry_id, entry.c.deleted_at.is_(None)).limit(1)
    return (await session.execute(stmt)).first() is not None


async def _purge(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    scope: ColumnElement[bool],
) -> None:
    """Hard-delete the rows *scope* names across every family table, chunked.

    Collection and deletion repeat until the scope reads empty: writes
    are not serialized with topology, so a rival can commit a new child
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


async def _claim(
    session: AsyncSession,
    profile: DialectProfile,
    stmt: Update | Delete,
    proof: Column[Any],
    *,
    miss: str,
) -> ResultError | None:
    """Execute a single-row guarded statement and prove exactly one row matched.

    The evidence ladder mirrors the write family's refusal doctrine:
    rowcount where the dialect declares it sane, RETURNING *proof* where
    the dialect models it, else a classified ``unsupported`` — an
    unverifiable guarded claim never proceeds. A proven zero-row outcome
    raises :class:`StaleSnapshot` with *miss* as its context.
    """
    dialect = session.get_bind().dialect
    returning = dialect.update_returning if isinstance(stmt, Update) else dialect.delete_returning
    if dialect.supports_sane_rowcount:
        matched = cast("CursorResult[Any]", await session.execute(stmt)).rowcount
    elif returning:
        matched = len((await session.execute(stmt.returning(proof))).all())
    else:
        detail = f"guarded claims cannot be verified on {profile.name}: no RETURNING, no sane rowcount"
        return classified(ErrorKind.unsupported, detail=detail)
    if matched == 0:
        raise StaleSnapshot(miss)
    return None


async def _tombstone_root(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    row: RowMapping,
    expected_version: int,
    now: datetime,
) -> ResultError | None:
    """Mark the named row deleted — its own root — guarded on the version the batch expects.

    Writes are not serialized with topology, and every child create or
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
    return await _claim(session, profile, stmt, entry.c.entry_id, miss=miss)


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
    parent = await _dest_parent_id(session, entry, target, profile, membership_budget)
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
    return await _claim(session, profile, stmt, entry.c.entry_id, miss=miss)


async def _revive_descendants(session: AsyncSession, entry: Table, root_id: str) -> None:
    """Clear the tombstone on every row of the root's set but the root — one statement, no version bump."""
    stmt = (
        update(entry)
        .where(entry.c.trash_root_id == root_id, entry.c.entry_id != root_id)
        .values(deleted_at=None, trash_root_id=None)
    )
    await session.execute(stmt)


async def _descendant_rewrites(
    session: AsyncSession, entry: Table, profile: DialectProfile, old_prefix: str, new_prefix: str
) -> list[dict[str, str]]:
    """Each descendant's id, old path, and recomputed path cache under the new prefix.

    Raw ``str`` slicing, no ``Path`` minted — the caller may still refuse
    the whole set on the byte budget before anything is applied. A
    tombstoned descendant rides along: its tree moves whole.
    """
    like = descendant_filter(entry, old_prefix, profile)
    found = await session.execute(select(entry.c.entry_id, entry.c.path).where(like))
    return [{"b_id": r.entry_id, "b_old": r.path, "b_path": new_prefix + r.path[len(old_prefix) :]} for r in found]


async def _apply_rewrites(
    session: AsyncSession, entry: Table, rows: list[dict[str, str]], postures: PostureRows
) -> None:
    """Executemany path-cache rewrite; bumps no versions and takes no guard.

    Nothing observable on a descendant changed, and one directory move
    must not flood the dirty overlay. Each row's everyone level is
    rewritten from *postures* — the destination's posture — in the same
    statement as its path.
    """
    if not rows:
        return
    stmt = (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"))
        .values(path=bindparam("b_path"), everyone_level=bindparam("b_level"))
    )
    params = [
        {"b_id": row["b_id"], "b_path": row["b_path"], "b_level": label_of(postures, row["b_path"])} for row in rows
    ]
    await session.execute(stmt, params)


async def _rewrite_descendants(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    old_prefix: str,
    new_prefix: str,
    postures: PostureRows,
) -> None:
    """Recompute descendant path caches under the moved prefix, collected live.

    Runs after the root claim, so a child committed inside the pre-claim
    window is carried. A late arrival whose rewritten path overflows the
    byte budget raises :class:`StaleSnapshot` instead of storing it —
    the redriven ladder then refuses the whole target honestly. The
    segment postings ride the same rewrite list, so they mirror the
    rewritten path caches inside this same transaction; the labels ride
    it too, from *postures*, the destination's posture.
    """
    rewrites = await _descendant_rewrites(session, tables.entry, profile, old_prefix, new_prefix)
    if any(byte_length(r["b_path"]) > MAX_PATH_LENGTH for r in rewrites):
        raise StaleSnapshot("a late arrival under the moved prefix overflows the path budget")
    await _apply_rewrites(session, tables.entry, rewrites, postures)
    moves = [(row["b_id"], row["b_old"], row["b_path"]) for row in rewrites]
    await move_postings(session, tables.segments, profile, membership_budget, moves)


async def _bump(session: AsyncSession, entry: Table, entry_id: str) -> None:
    """One unguarded SQL-side increment — a namespace change bumps its holder."""
    await session.execute(update(entry).where(entry.c.entry_id == entry_id).values(version=entry.c.version + 1))


def _covering_ancestor(src: Path, move_srcs: Counter[Path]) -> Path | None:
    """The batch move source whose subtree contains *src*, if any."""
    return next((ancestor for ancestor in ancestor_chain(src) if move_srcs[ancestor] > 0), None)


def _overlap_error(
    src: Path, move_srcs: Counter[Path], committed_kinds: dict[str, str], tombstones: dict[str, datetime]
) -> ResultError:
    """Classify an overlapping move source against the committed snapshot.

    The miss outranks the batch-shape conflict: a duplicated or covered
    source that never existed classifies its own miss, order-independent.
    """
    if str(src) not in committed_kinds:
        return classify_miss(src, committed_kinds, tombstones)
    if move_srcs[src] > 1:
        return classified(ErrorKind.invalid, src, detail="duplicate move source in batch")
    ancestor = _covering_ancestor(src, move_srcs)
    detail = "inside another source this batch also moves"
    return classified(ErrorKind.invalid, src, target=ancestor, detail=detail)


def _occupied(dest: Path, occupant: RowMapping, *, target: Path) -> ResultError:
    """The ``exists`` refusal for a transfer onto *dest*; a tombstoned occupant holds its address and says so."""
    deleted_at = occupant["deleted_at"]
    if deleted_at is None:
        return already_exists(dest, target=target)
    return classified(ErrorKind.exists, dest, target=target, data=trashed_hint(deleted_at))


async def _point_row(session: AsyncSession, entry: Table, path: str) -> RowMapping | None:
    """The row at *path* on either side of the tombstone — the caller judges ``deleted_at``."""
    columns = [entry.c[name] for name in _SNAPSHOT_COLUMNS]
    return (await session.execute(select(*columns).where(entry.c.path == path))).mappings().first()


async def _dest_parent_id(
    session: AsyncSession, entry: Table, dest: Path, profile: DialectProfile, membership_budget: int
) -> str | ResultError:
    """The destination's parent id after the live POSIX parent gate.

    A missing or tombstoned ancestor is ``not_found`` at that component
    (the tombstone carries its hint), a non-directory is ``wrong_kind``
    there — the shared descent ladder, read live so a parent minted by
    an earlier pair in the batch counts.
    """
    chain = ancestor_chain(dest)
    paths = [*(str(ancestor) for ancestor in chain), "/"]
    columns = [entry.c.entry_id, entry.c.path, entry.c.kind, entry.c.deleted_at]
    found = await rows_by_path(session, entry, paths, columns, profile, membership_budget)
    kinds = {path: row["kind"] for path, row in found.items() if row["deleted_at"] is None}
    tombstones = {path: row["deleted_at"] for path, row in found.items() if row["deleted_at"] is not None}
    if any(kinds.get(ancestor) != "directory" for ancestor in chain):
        return classify_miss(dest, kinds, tombstones)
    return found[str(dest.parent_dir)]["entry_id"]


async def _fetch_subtree(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, src: str
) -> list[RowMapping]:
    """The source row and every descendant, with the metadata columns a copy reproduces.

    Narrow rows only — never a body: a copy reads bodies afterwards in
    bytes-bounded pages (:func:`_copy_bodies`), each guarded on the
    version read here, so a rival's commit between the two reads is a
    redrive rather than a torn ``content_hash``.
    """
    entry = tables.entry
    columns: list[Any] = [entry.c[name] for name in _SUBTREE_COLUMNS]
    return list((await session.execute(select(*columns).where(subtree_filter(entry, src, profile)))).mappings())


async def _execute_move(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    src_row: RowMapping,
    dest: Path,
    dest_parent_id: str,
    postures: PostureRows,
    now: datetime,
    *,
    op: str,
) -> ResultError | None:
    """Reparent the root, rewrite descendants, bump both parents.

    The destination was probed empty by the ladder; nothing is ever
    unlinked here — no transfer destroys. The root claim is guarded on
    the version read this pair (a rival write bumping the source
    mid-window flips it). Every moved row takes the everyone level its
    new path has under *postures*, the destination's posture, in the
    statement that rewrites its path. A unique violation on the claim —
    a rival write took the destination address after this pair's
    occupant probe — redrives: the fresh ladder returns the honest
    per-pair refusal, never a classification off mid-race state.
    """
    entry = tables.entry
    stmt = (
        update(entry)
        .where(entry.c.entry_id == src_row["entry_id"], entry.c.version == src_row["version"])
        .values(
            parent_id=dest_parent_id,
            name=dest.name,
            path=str(dest),
            ext=dest.ext,
            everyone_level=label_of(postures, str(dest)),
            version=entry.c.version + 1,
            updated_at=now,
        )
    )
    try:
        async with session.begin_nested():
            refused = await _claim(
                session, profile, stmt, entry.c.entry_id, miss=f"a rival write moved the source mid-{op}"
            )
    except IntegrityError as exc:
        raise StaleSnapshot(f"a rival write took the destination before this {op}'s claim") from exc
    if refused is not None:
        return refused
    # The moved root's fs mirror row re-sources by id.
    await repoint_fs_row(session, tables.edges, src_row["entry_id"], dest_parent_id)
    root_move = [(src_row["entry_id"], src_row["path"], str(dest))]
    await move_postings(session, tables.segments, profile, membership_budget, root_move)
    await _rewrite_descendants(session, tables, profile, membership_budget, src_row["path"], str(dest), postures)
    await _bump(session, entry, src_row["parent_id"])
    # Both parents bump even when identical — two increments, per the
    # conformance contract.
    await _bump(session, entry, dest_parent_id)
    return None


async def _execute_copy(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    subtree: list[RowMapping],
    src_row: RowMapping,
    dest: Path,
    dest_parent_id: str,
    new_paths: dict[str, str],
    postures: PostureRows,
    authority: Authority | None,
    now: datetime,
) -> None:
    """Mint the copied tree under a probed-empty destination.

    Every row is fresh: new ULIDs at version 1, ownership follows the
    writer, the everyone level is the destination's (*postures*), and
    neither ``external_id`` nor any edge row is copied. A
    rival child committed under the destination mid-window merges
    rather than refusing: the outcome equals the legal serial history
    copy-then-write, and a copy destroys nothing. Bodies are copied
    after the rows, in bytes-bounded pages, each page's source rows
    guarded on the version the metadata read saw, so the stamped
    ``content_hash``/``size_bytes`` and the copied body cannot straddle
    a rival's commit — a changed version redrives. A unique violation on
    the inserts — a rival write took an address under the destination
    after the occupant probe — redrives the verb: the fresh ladder
    returns the honest per-pair refusal at the address the race
    actually reached.
    """
    entry = tables.entry
    root_id = src_row["entry_id"]
    id_map = {row["entry_id"]: str(ULID()) for row in subtree}
    values = [
        {
            "entry_id": id_map[row["entry_id"]],
            "parent_id": dest_parent_id if row["entry_id"] == root_id else id_map[row["parent_id"]],
            "path": new_paths[row["entry_id"]],
            "name": dest.name if row["entry_id"] == root_id else row["name"],
            "kind": row["kind"],
            "version": 1,
            **{name: row[name] for name in _COPIED_COLUMNS},
            "ext": dest.ext if row["entry_id"] == root_id else row["ext"],
            "size_bytes": row["size_bytes"],
            "owner_id": owner_for(authority),
            "everyone_level": label_of(postures, new_paths[row["entry_id"]]),
            "created_at": now,
            "updated_at": now,
        }
        for row in subtree
    ]
    for chunk in chunked(values, rows_per_statement(parameter_budget, values)):
        try:
            async with session.begin_nested():
                await bulk_insert(session, entry, list(chunk))
        except IntegrityError as exc:
            raise StaleSnapshot("a rival write took an address under the destination mid-copy") from exc
    copied = [(id_map[row["entry_id"]], new_paths[row["entry_id"]]) for row in subtree]
    await insert_postings(session, tables.segments, copied)
    # Fresh ids get fresh fs mirror rows; authored edges are never copied.
    mirror = [
        (dest_parent_id if row["entry_id"] == root_id else id_map[row["parent_id"]], id_map[row["entry_id"]])
        for row in subtree
    ]
    await insert_fs_rows(session, tables.edges, mirror)
    await _copy_bodies(session, tables, profile, membership_budget, subtree, id_map, now)
    await _bump(session, entry, dest_parent_id)


async def _copy_bodies(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    subtree: list[RowMapping],
    id_map: dict[str, str],
    now: datetime,
) -> None:
    """Copy the subtree's bodies under the fresh ids, one bytes-bounded page in flight at a time.

    The content-bearing rows are cut by their recorded sizes under the
    blob page; each cut's bodies are read with the row's current
    version and hash and refused as stale when either differs from the
    metadata read — a rival wrote the source between the two reads, and
    the copy redrives whole rather than stamping a torn pair.
    """
    entry, content, blobs = tables.entry, tables.content, tables.blobs
    bearing = [row for row in subtree if row["kind"] != "directory"]
    observed = {row["entry_id"]: (row["version"], row["content_hash"]) for row in bearing}
    joined = tables.bodies_joined(content=True, data=True)
    for cut in byte_chunked(bearing, lambda row: cast("int", row["size_bytes"]), BLOB_PAGE_BYTES):
        texts: list[dict[str, object]] = []
        binaries: list[dict[str, object]] = []
        for ids in chunked([row["entry_id"] for row in cut], membership_budget):
            stmt = (
                select(entry.c.entry_id, entry.c.version, entry.c.content_hash, content.c.content, blobs.c.data)
                .select_from(joined)
                .where(membership(entry.c.entry_id, ids, profile))
            )
            for row in await session.execute(stmt):
                if (row.version, row.content_hash) != observed[row.entry_id]:
                    raise StaleSnapshot(f"a rival write changed {row.entry_id} under the copy")
                if row.content is not None:
                    texts.append({"entry_id": id_map[row.entry_id], "created_at": now, "content": row.content})
                if row.data is not None:
                    binaries.append({"entry_id": id_map[row.entry_id], "created_at": now, "data": row.data})
        await bulk_insert(session, content, texts)
        await bulk_insert(session, blobs, binaries)


async def _final_rows(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, dests: list[str]
) -> dict[str, RowMapping]:
    """One bounded re-read of every pending destination after the batch."""
    columns = [entry.c.path, entry.c.kind, entry.c.version, entry.c.size_bytes]
    return await rows_by_path(session, entry, dests, columns, profile, membership_budget)


def _observe_transfer(pending: _PendingTransfer, final: RowMapping | None) -> Observation:
    if final is None:
        return Observation(
            path=pending.dest,
            kind=pending.kind,
            size_bytes=pending.size_bytes,
            version=pending.version,
            status=pending.status,
        )
    return Observation(
        path=pending.dest,
        kind=final["kind"],
        size_bytes=final["size_bytes"],
        version=final["version"],
        status=pending.status,
    )


def _observe_deleted(target: Path, row: RowMapping, *, deleted_at: datetime | None = None) -> Observation:
    return Observation(
        path=target,
        kind=row["kind"],
        size_bytes=row["size_bytes"],
        version=row["version"],
        status="deleted",
        deleted_at=deleted_at,
    )
