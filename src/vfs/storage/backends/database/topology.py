"""Topology-family statement builders for ``DatabaseStorage`` — delete, move, copy.

Topology verbs rewrite the namespace's shape — parent pointers and path
caches — so every one of them serializes: its first statement takes the
per-mount serialization point (nothing on SQLite, whose writer
transaction is the lock; a transaction-scoped advisory lock on
Postgres; an X-lock on the single meta row everywhere else), and every
read runs after it inside the same transaction, so refusal checks judge
post-rival state and later targets see earlier targets' effects.

Delete stages nothing: it fetches one pre-batch committed snapshot for
classification, then walks targets in request order mirroring the
memory backend's ladder — root refusal, covered/repeat subsumption
judged against the snapshot, live ``not_empty`` on ``cascade=False``.
The default arm reparents the row into an hourly trash bucket (path
rewritten, original site recorded, name swapped to the entry's ULID so
same-named deletes never collide); ``permanent`` purges the subtree's
rows across every family table. Trash-side paths are backend-authored
raw strings, never ``Path`` values — a deep row's trash path may
lawfully exceed the public path budget.

Move and copy share one pair ladder mirroring the memory backend row
for row: batch-shape refusals against the committed snapshot, live
per-pair reads, no-replace ``exists`` before the cycle checks, cycle
before occupant kind translation (the Linux rename-trap ordering), and
a byte-budget overflow refusing the pair before any statement runs. A
move is a reparent of the root plus descendant path rewrites — and the
restore gesture: it clears trash metadata unconditionally. A copy
mints fresh ULIDs at version 1, never copies edges or ``external_id``,
and an overwritten occupant keeps its identity as a material update.
Any per-pair error fails the batch whole; the runner never commits a
failed result.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, NamedTuple

from sqlalchemy import bindparam, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from vfs.models import Observation
from vfs.paths import MAX_PATH_LENGTH, METADATA_ROOT, ROOT, TRASH_ROOT, Path, byte_length
from vfs.results import Result, ResultError, VFSErrorKind, already_exists, classified
from vfs.storage.backends.database.descent import (
    LIKE_ESCAPE,
    ancestor_chain,
    classify_miss,
    classify_misses,
    escape_like,
)
from vfs.storage.backends.database.dialects import chunked, rows_per_statement
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy import Table
    from sqlalchemy.engine import Row, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.paths import ObjectKind
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.protocol import ResolvedPair

# The pre-batch committed snapshot: classification and observation state.
_SNAPSHOT_COLUMNS: Final[tuple[str, ...]] = ("entry_id", "parent_id", "path", "name", "kind", "version", "size_bytes")

# A transfer subtree adds the material columns a copy reproduces.
_SUBTREE_COLUMNS: Final[tuple[str, ...]] = (*_SNAPSHOT_COLUMNS, "content_hash", "mime_type", "ext", "lines")


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
    permanent: bool,
    cascade: bool,
    user_id: str | None,
    lock_key: int,
) -> Result:
    """Adjudicate and apply a batch of deletes as a set.

    Misses, covered targets, and repeats are judged against the
    pre-batch committed snapshot — after an earlier target is trashed
    in-transaction, a live probe would blame the wrong path — while the
    ``cascade=False`` occupancy check reads live state, so a target
    emptied earlier in the batch deletes cleanly. Each deleted row
    observes its pre-delete snapshot state; there is no post-commit row
    to stat at the requested path.
    """
    entry = tables.entry
    await _serialize(session, profile, tables.meta, lock_key)
    snapshot = await _fetch_snapshot(session, entry, membership_budget, targets)
    await seam("delete:post-snapshot")
    kinds = {path: row["kind"] for path, row in snapshot.items()}
    now = datetime.now(UTC)
    trash = _TrashChain(entry, root_id=snapshot["/"]["entry_id"], user_id=user_id, now=now)
    unique = set(targets)
    seen: set[Path] = set()
    rows: list[Observation] = []
    errors: list[ResultError] = []
    for target in targets:
        if target == ROOT:
            errors.append(classified(VFSErrorKind.invalid, "Cannot delete the root directory", target))
            continue
        # A target inside another target's cascade — or a repeat — is
        # subsumed: judged against committed state, order-independent.
        covered = cascade and any(o != target and target.startswith(o + "/") for o in unique)
        if covered or target in seen:
            row = snapshot.get(str(target))
            if row is None:
                errors.append(classify_miss(target, kinds))
            else:
                rows.append(_observe_deleted(target, row))
            continue
        seen.add(target)
        row = snapshot.get(str(target))
        if row is None:
            errors.append(classify_miss(target, kinds))
            continue
        if not cascade and await _has_live_children(session, entry, row["entry_id"]):
            errors.append(classified(VFSErrorKind.not_empty, f"Directory not empty: {target}", target))
            continue
        if permanent:
            await _purge_subtree(session, tables, membership_budget, str(target))
        else:
            bucket_id = await trash.ensure(session, target)
            if isinstance(bucket_id, ResultError):
                errors.append(bucket_id)
                continue
            trash_path = await _reparent_to_trash(session, entry, row, bucket_id, trash.bucket_path, now)
            await _rewrite_descendants(session, entry, str(target), trash_path)
            await _bump(session, entry, bucket_id)
        await _bump(session, entry, row["parent_id"])
        rows.append(_observe_deleted(target, row))
    if errors:
        return Result(ops=("delete",), errors=errors)
    return Result(ops=("delete",), observations=rows)


# ---------------------------------------------------------------------------
# Move / copy
# ---------------------------------------------------------------------------


class _PendingTransfer(NamedTuple):
    """One executed pair's observation, captured at execution time.

    The captured values are the fallback: after the loop every pending
    destination is re-read in one chunked pass and the final values win —
    a later pair may have bumped an earlier destination — but a
    destination a later pair moved away falls back to these.
    """

    dest: Path
    status: Literal["created", "updated", "unchanged"]
    kind: ObjectKind
    version: int
    size_bytes: int


async def transfer_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    op: Literal["move", "copy"],
    operations: list[ResolvedPair],
    overwrite: bool,
    user_id: str | None,
    lock_key: int,
) -> Result:
    """Adjudicate and apply a batch of moves or copies, pair by pair.

    Batch-shape refusals — duplicate move sources, a source inside
    another moved source — are judged against the committed pre-batch
    snapshot so the outcome is order-independent; every other check
    reads live state inside the serialized transaction, so later pairs
    see earlier pairs' effects. The per-pair ladder mirrors the memory
    backend row for row: overlap, source miss, root, rename-to-self,
    destination parent gate, no-replace ``exists`` before the cycle
    checks, cycle in both directions as one ``invalid`` kind, occupant
    kind, occupant emptiness, then destination byte-overflow — no
    statement runs for a pair until every check has passed.
    """
    entry = tables.entry
    await _serialize(session, profile, tables.meta, lock_key)
    move_srcs = Counter(pair.src for pair in operations) if op == "move" else Counter[Path]()
    committed: dict[str, RowMapping] = {}
    if op == "move":
        committed = await _fetch_snapshot(session, entry, membership_budget, list(move_srcs))
    committed_kinds = {path: row["kind"] for path, row in committed.items()}
    await seam("transfer:post-snapshot")
    now = datetime.now(UTC)
    pending: list[_PendingTransfer] = []
    errors: list[ResultError] = []
    for pair in operations:
        src, dest = pair.src, pair.dest
        if src != ROOT and (move_srcs[src] > 1 or _covering_ancestor(src, move_srcs) is not None):
            errors.append(_overlap_error(src, move_srcs, committed, committed_kinds))
            continue
        src_row = await _point_row(session, entry, str(src))
        if src_row is None:
            errors.append((await classify_misses(session, entry, [src], membership_budget))[0])
            continue
        if src == ROOT or dest == ROOT:
            errors.append(classified(VFSErrorKind.invalid, f"Cannot {op} the root directory"))
            continue
        if dest == src:
            # POSIX rename-to-self: a successful no-op, never a refusal.
            pending.append(
                _PendingTransfer(dest, "unchanged", src_row["kind"], src_row["version"], src_row["size_bytes"])
            )
            continue
        dest_parent_id = await _dest_parent_id(session, entry, dest, membership_budget)
        if isinstance(dest_parent_id, ResultError):
            errors.append(dest_parent_id)
            continue
        # The rename ladder: no-replace exists first, cycle next (one
        # kind, both directions), then kind, then emptiness — last.
        occupant = await _point_row(session, entry, str(dest))
        if occupant is not None and not overwrite:
            errors.append(already_exists(dest))
            continue
        if dest.startswith(src + "/"):
            errors.append(classified(VFSErrorKind.invalid, f"Cannot {op} {src} into itself: {dest}"))
            continue
        if src.startswith(dest + "/"):
            errors.append(classified(VFSErrorKind.invalid, f"Cannot {op} {src} onto its own ancestor: {dest}"))
            continue
        if occupant is not None:
            if (src_row["kind"] == "directory") != (occupant["kind"] == "directory"):
                errors.append(classified(VFSErrorKind.wrong_kind, f"Cannot {op} onto: {dest}", dest))
                continue
            if occupant["kind"] == "directory" and await _has_live_children(session, entry, occupant["entry_id"]):
                errors.append(classified(VFSErrorKind.not_empty, f"Directory not empty: {dest}", dest))
                continue
        subtree = await _fetch_subtree(session, entry, str(src))
        new_paths = {row["entry_id"]: str(dest) + row["path"][len(str(src)) :] for row in subtree}
        if any(byte_length(path) > MAX_PATH_LENGTH for path in new_paths.values()):
            message = f"Cannot {op} {src}: Path too long (max {MAX_PATH_LENGTH} bytes)"
            errors.append(classified(VFSErrorKind.unaddressable, message, dest))
            continue
        if op == "move":
            await _execute_move(session, tables, membership_budget, src_row, dest, dest_parent_id, occupant, now)
            version = src_row["version"] + 1
        else:
            version = await _execute_copy(
                session,
                tables,
                parameter_budget,
                membership_budget,
                subtree=subtree,
                src_row=src_row,
                dest=dest,
                dest_parent_id=dest_parent_id,
                occupant=occupant,
                new_paths=new_paths,
                user_id=user_id,
                now=now,
            )
        status: Literal["created", "updated"] = "updated" if occupant is not None else "created"
        pending.append(_PendingTransfer(dest, status, src_row["kind"], version, src_row["size_bytes"]))
    if errors:
        return Result(ops=(op,), errors=errors)
    finals = await _final_rows(session, entry, membership_budget, [str(p.dest) for p in pending])
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
    session: AsyncSession, entry: Table, membership_budget: int, targets: list[Path]
) -> dict[str, RowMapping]:
    """Chunked ``path IN`` selects: targets, their ancestors, the root."""
    paths = {str(t) for t in targets} | {str(a) for t in targets for a in ancestor_chain(t)} | {"/"}
    columns = [entry.c[name] for name in _SNAPSHOT_COLUMNS]
    snapshot: dict[str, RowMapping] = {}
    for chunk in chunked(sorted(paths), membership_budget):
        stmt = select(*columns).where(entry.c.path.in_(chunk))
        snapshot.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return snapshot


async def _has_live_children(session: AsyncSession, entry: Table, entry_id: str) -> bool:
    # A one-row probe, not SELECT EXISTS(...) — T-SQL has no bare form.
    stmt = select(entry.c.id).where(entry.c.parent_id == entry_id).limit(1)
    return (await session.execute(stmt)).first() is not None


async def _purge_subtree(session: AsyncSession, tables: VFSTables, membership_budget: int, target: str) -> None:
    """Hard-delete the subtree's rows across every family table, chunked."""
    entry = tables.entry
    subtree = or_(
        entry.c.path == target,
        entry.c.path.like(escape_like(target) + "/%", escape=LIKE_ESCAPE),
    )
    ids = [row.entry_id for row in await session.execute(select(entry.c.entry_id).where(subtree))]
    edges = tables.edges
    for chunk in chunked(ids, membership_budget):
        await session.execute(delete(tables.content).where(tables.content.c.entry_id.in_(chunk)))
        await session.execute(delete(tables.versions).where(tables.versions.c.entry_id.in_(chunk)))
        await session.execute(delete(tables.chunks).where(tables.chunks.c.entry_id.in_(chunk)))
        await session.execute(delete(edges).where(or_(edges.c.source_id.in_(chunk), edges.c.target_id.in_(chunk))))
        await session.execute(delete(entry).where(entry.c.entry_id.in_(chunk)))


class _TrashChain:
    """The ``/.vfs/trash/<hour-bucket>`` chain, minted lazily once per batch.

    Writes are not serialized with topology, so a rival write op can
    mint these directories concurrently — the designed benign race:
    each link inserts under a savepoint, and a unique-violation loser
    simply re-selects the winner's row. A non-directory occupant
    anywhere in the chain refuses the target with ``wrong_kind`` (trash
    is an ordinary writable subtree; a user file may squat there).
    """

    def __init__(self, entry: Table, *, root_id: str, user_id: str | None, now: datetime) -> None:
        self._entry = entry
        self._root_id = root_id
        self._user_id = user_id
        self._now = now
        self.bucket_path = f"{TRASH_ROOT}/{now:%Y-%m-%d-%H}"
        self._bucket_id: str | None = None

    async def ensure(self, session: AsyncSession, target: Path) -> str | ResultError:
        """The bucket's entry id, minting missing links; an error refuses *target*."""
        if self._bucket_id is not None:
            return self._bucket_id
        entry = self._entry
        parent_id = self._root_id
        for link in (METADATA_ROOT, TRASH_ROOT, self.bucket_path):
            row = (await session.execute(select(entry.c.entry_id, entry.c.kind).where(entry.c.path == link))).first()
            if row is None:
                row = await self._mint(session, link, parent_id)
            if row.kind != "directory":
                return classified(VFSErrorKind.wrong_kind, f"Not a directory: {link}", Path(link), target=target)
            parent_id = row.entry_id
        self._bucket_id = parent_id
        return parent_id

    async def _mint(self, session: AsyncSession, link: str, parent_id: str) -> Row[Any]:
        probe = select(self._entry.c.entry_id, self._entry.c.kind).where(self._entry.c.path == link)
        try:
            async with session.begin_nested():
                await session.execute(
                    insert(self._entry).values(
                        entry_id=str(ULID()),
                        parent_id=parent_id,
                        path=link,
                        name=link.rsplit("/", 1)[-1],
                        kind="directory",
                        version=1,
                        owner_id=self._user_id,
                        created_at=self._now,
                        updated_at=self._now,
                    )
                )
            await _bump(session, self._entry, parent_id)
        except IntegrityError:
            # The benign race: a rival write minted this link first.
            pass
        return (await session.execute(probe)).one()


async def _reparent_to_trash(
    session: AsyncSession, entry: Table, row: RowMapping, bucket_id: str, bucket_path: str, now: datetime
) -> str:
    """Rewrite the row into the bucket; its ULID becomes its in-bucket name.

    Deliberately unguarded: under the serialization point the row cannot
    vanish, and a concurrent edit composes — both bump SQL-side off the
    current row, and the reparent touches no material column.
    """
    trash_path = f"{bucket_path}/{row['entry_id']}"
    await session.execute(
        update(entry)
        .where(entry.c.entry_id == row["entry_id"])
        .values(
            parent_id=bucket_id,
            name=row["entry_id"],
            path=trash_path,
            original_parent_id=row["parent_id"],
            original_name=row["name"],
            deleted_at=now,
            version=entry.c.version + 1,
        )
    )
    return trash_path


async def _rewrite_descendants(session: AsyncSession, entry: Table, old_prefix: str, new_prefix: str) -> None:
    """Recompute descendant path caches under the moved prefix, in Python.

    Raw ``str`` slicing only — trash-side paths may lawfully exceed the
    public path budget, so no ``Path`` is ever minted here. Descendant
    rewrites bump no versions and take no guard: nothing observable on
    the descendant changed, and one directory delete must not flood the
    dirty overlay.
    """
    like = entry.c.path.like(escape_like(old_prefix) + "/%", escape=LIKE_ESCAPE)
    found = await session.execute(select(entry.c.entry_id, entry.c.path).where(like))
    rows = [{"b_id": r.entry_id, "b_path": new_prefix + r.path[len(old_prefix) :]} for r in found]
    if not rows:
        return
    stmt = update(entry).where(entry.c.entry_id == bindparam("b_id")).values(path=bindparam("b_path"))
    await session.execute(stmt, rows)


async def _bump(session: AsyncSession, entry: Table, entry_id: str) -> None:
    """One unguarded SQL-side increment — a namespace change bumps its holder."""
    await session.execute(update(entry).where(entry.c.entry_id == entry_id).values(version=entry.c.version + 1))


def _covering_ancestor(src: Path, move_srcs: Counter[Path]) -> Path | None:
    """The batch move source whose subtree contains *src*, if any."""
    return next((ancestor for ancestor in ancestor_chain(src) if move_srcs[ancestor] > 0), None)


def _overlap_error(
    src: Path, move_srcs: Counter[Path], committed: dict[str, RowMapping], committed_kinds: dict[str, str]
) -> ResultError:
    """Classify an overlapping move source against the committed snapshot.

    The miss outranks the batch-shape conflict: a duplicated or covered
    source that never existed classifies its own miss, order-independent.
    """
    if str(src) not in committed:
        return classify_miss(src, committed_kinds)
    if move_srcs[src] > 1:
        return classified(VFSErrorKind.invalid, f"Duplicate move source in batch: {src}", src, target=src)
    ancestor = _covering_ancestor(src, move_srcs)
    message = f"Cannot move {src}: inside {ancestor}, which this batch also moves"
    return classified(VFSErrorKind.invalid, message, src, target=src)


async def _point_row(session: AsyncSession, entry: Table, path: str) -> RowMapping | None:
    columns = [entry.c[name] for name in _SNAPSHOT_COLUMNS]
    return (await session.execute(select(*columns).where(entry.c.path == path))).mappings().first()


async def _dest_parent_id(session: AsyncSession, entry: Table, dest: Path, membership_budget: int) -> str | ResultError:
    """The destination's parent id after the live POSIX parent gate.

    A missing ancestor is ``not_found`` at that component, a
    non-directory is ``wrong_kind`` there — the shared descent ladder,
    read live so a parent minted by an earlier pair in the batch counts.
    """
    chain = ancestor_chain(dest)
    paths = [*(str(ancestor) for ancestor in chain), "/"]
    found: dict[str, RowMapping] = {}
    for chunk in chunked(paths, membership_budget):
        stmt = select(entry.c.entry_id, entry.c.path, entry.c.kind).where(entry.c.path.in_(chunk))
        found.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    for ancestor in chain:
        row = found.get(str(ancestor))
        if row is None:
            return classified(VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=dest)
        if row["kind"] != "directory":
            return classified(VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=dest)
    return found[str(dest.parent_dir)]["entry_id"]


async def _fetch_subtree(session: AsyncSession, entry: Table, src: str) -> list[RowMapping]:
    """The source row and every descendant, with the columns a copy reproduces."""
    columns = [entry.c[name] for name in _SUBTREE_COLUMNS]
    subtree = or_(
        entry.c.path == src,
        entry.c.path.like(escape_like(src) + "/%", escape=LIKE_ESCAPE),
    )
    return list((await session.execute(select(*columns).where(subtree))).mappings())


async def _execute_move(
    session: AsyncSession,
    tables: VFSTables,
    membership_budget: int,
    src_row: RowMapping,
    dest: Path,
    dest_parent_id: str,
    occupant: RowMapping | None,
    now: datetime,
) -> None:
    """Reparent the root, rewrite descendants, bump both parents.

    An occupant — an empty directory or a file, everything else was
    refused — is hard-deleted first: POSIX rename unlinks the target,
    no trash hop. The root update is deliberately unguarded (the row
    cannot vanish under the serialization point) and clears the restore
    columns unconditionally: a move out of trash is the restore gesture,
    and a live row must not carry trash metadata.
    """
    entry = tables.entry
    if occupant is not None:
        await _purge_subtree(session, tables, membership_budget, str(dest))
    await session.execute(
        update(entry)
        .where(entry.c.entry_id == src_row["entry_id"])
        .values(
            parent_id=dest_parent_id,
            name=dest.name,
            path=str(dest),
            version=entry.c.version + 1,
            updated_at=now,
            original_parent_id=None,
            original_name=None,
            deleted_at=None,
        )
    )
    await _rewrite_descendants(session, entry, src_row["path"], str(dest))
    await _bump(session, entry, src_row["parent_id"])
    # Both parents bump even when identical — two increments, memory parity.
    await _bump(session, entry, dest_parent_id)


async def _execute_copy(
    session: AsyncSession,
    tables: VFSTables,
    parameter_budget: int,
    membership_budget: int,
    *,
    subtree: list[RowMapping],
    src_row: RowMapping,
    dest: Path,
    dest_parent_id: str,
    occupant: RowMapping | None,
    new_paths: dict[str, str],
    user_id: str | None,
    now: datetime,
) -> int:
    """Mint the copied tree; the returned version is the root's fallback value.

    Fresh rows take new ULIDs at version 1, ownership follows the
    writer, and neither ``external_id`` nor any edge row is copied. An
    overwritten occupant keeps its identity — a material update with an
    SQL-side increment — so rows referencing it stay wired.
    """
    entry = tables.entry
    root_id = src_row["entry_id"]
    # The point-read src_row lacks material columns; the subtree row has them.
    root = next(row for row in subtree if row["entry_id"] == root_id)
    id_map = {row["entry_id"]: str(ULID()) for row in subtree}
    if occupant is not None:
        id_map[root_id] = occupant["entry_id"]
        await session.execute(
            update(entry)
            .where(entry.c.entry_id == occupant["entry_id"])
            .values(
                kind=root["kind"],
                content_hash=root["content_hash"],
                mime_type=root["mime_type"],
                ext=root["ext"],
                lines=root["lines"],
                size_bytes=root["size_bytes"],
                owner_id=user_id,
                updated_at=now,
                version=entry.c.version + 1,
            )
        )
        await session.execute(delete(tables.content).where(tables.content.c.entry_id == occupant["entry_id"]))
    fresh = [row for row in subtree if occupant is None or row["entry_id"] != root_id]
    values = [
        {
            "entry_id": id_map[row["entry_id"]],
            "parent_id": dest_parent_id if row["entry_id"] == root_id else id_map[row["parent_id"]],
            "path": new_paths[row["entry_id"]],
            "name": dest.name if row["entry_id"] == root_id else row["name"],
            "kind": row["kind"],
            "version": 1,
            "content_hash": row["content_hash"],
            "mime_type": row["mime_type"],
            "ext": row["ext"],
            "lines": row["lines"],
            "size_bytes": row["size_bytes"],
            "owner_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        for row in fresh
    ]
    if values:
        for chunk in chunked(values, rows_per_statement(parameter_budget, values)):
            await session.execute(insert(entry), list(chunk))
    content = tables.content
    bodies: list[dict[str, object]] = []
    for chunk in chunked([row["entry_id"] for row in subtree], membership_budget):
        found = await session.execute(
            select(content.c.entry_id, content.c.content).where(content.c.entry_id.in_(chunk))
        )
        bodies.extend({"entry_id": id_map[body.entry_id], "content": body.content} for body in found)
    if bodies:
        await session.execute(insert(content), bodies)
    if occupant is None:
        await _bump(session, entry, dest_parent_id)
        return 1
    return occupant["version"] + 1


async def _final_rows(
    session: AsyncSession, entry: Table, membership_budget: int, dests: list[str]
) -> dict[str, RowMapping]:
    """One chunked re-read of every pending destination after the batch."""
    finals: dict[str, RowMapping] = {}
    for chunk in chunked(sorted(set(dests)), membership_budget):
        stmt = select(entry.c.path, entry.c.kind, entry.c.version, entry.c.size_bytes).where(entry.c.path.in_(chunk))
        finals.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return finals


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


def _observe_deleted(target: Path, row: RowMapping) -> Observation:
    return Observation(
        path=target,
        kind=row["kind"],
        size_bytes=row["size_bytes"],
        version=row["version"],
        status="deleted",
    )
