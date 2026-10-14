"""Topology-family statement builders for ``DatabaseStorage`` — move, copy.

Topology verbs rewrite the namespace's shape — parent pointers, path
caches, and the segment postings that mirror the path column inside the
same transaction. Each is a serialized verb (``serialized.py``): its
first statement takes the per-mount serialization point, its claims are
guarded on the version it judged, and a guard miss redrives the whole
verb from a fresh snapshot. The tombstone verbs that hide and reveal
rows without moving them live in ``trash.py``.

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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, cast

from sqlalchemy import bindparam, select, update
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from vfs.authority import owner_for
from vfs.paths import MAX_PATH_LENGTH, ROOT, Path, byte_length
from vfs.results import ErrorKind, Result, ResultError, already_exists, classified
from vfs.storage.backends.database.descent import (
    ancestor_chain,
    classify_miss,
    classify_misses,
    descendant_filter,
    subtree_filter,
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

    from sqlalchemy import Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.grants import PostureRows
    from vfs.storage.protocol import ResolvedPair

# A transfer subtree adds the material columns a copy reproduces.
_SUBTREE_COLUMNS: Final[tuple[str, ...]] = (
    *SNAPSHOT_COLUMNS,
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
_COPIED_COLUMNS: Final[tuple[str, ...]] = _SUBTREE_COLUMNS[len(SNAPSHOT_COLUMNS) :]

_PATH_BUDGET: Final = f"the path would exceed {MAX_PATH_LENGTH} bytes"


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
    await serialize(session, profile, tables.lock)
    if gate is not None and (refused := await gate(session)):
        return Result(ops=(op,), errors=refused)
    move_srcs = Counter(pair.src for pair in operations) if op == "move" else Counter[Path]()
    committed: dict[str, RowMapping] = {}
    if op == "move":
        committed = await fetch_snapshot(session, entry, profile, membership_budget, list(move_srcs))
    committed_kinds = {path: row["kind"] for path, row in committed.items() if row["deleted_at"] is None}
    tombstones = {path: row["deleted_at"] for path, row in committed.items() if row["deleted_at"] is not None}
    await seam("transfer:post-snapshot")
    now = datetime.now(UTC)
    pending: list[PendingRow] = []
    errors: list[ResultError] = []
    for pair in operations:
        src, dest = pair.src, pair.dest
        if src != ROOT and (move_srcs[src] > 1 or _covering_ancestor(src, move_srcs) is not None):
            errors.append(_overlap_error(src, move_srcs, committed_kinds, tombstones))
            continue
        src_row = await point_row(session, entry, str(src))
        if src_row is None or src_row["deleted_at"] is not None:
            errors.append((await classify_misses(session, entry, [src], profile, membership_budget))[0])
            continue
        if src == ROOT or dest == ROOT:
            detail = f"{op}: the root directory may be neither source nor destination"
            errors.append(classified(ErrorKind.invalid, src, target=dest, detail=detail))
            continue
        if dest == src:
            # POSIX rename-to-self: a successful no-op, never a refusal.
            pending.append(PendingRow(dest, "unchanged", src_row["kind"], src_row["version"], src_row["size_bytes"]))
            continue
        parent_id = await dest_parent_id(session, entry, dest, profile, membership_budget)
        if isinstance(parent_id, ResultError):
            errors.append(parent_id)
            continue
        # The rename ladder: exists first (an ancestor destination always
        # exists), then the into-itself cycle — no arm replaces an occupant.
        occupant = await point_row(session, entry, str(dest))
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
                session, tables, profile, membership_budget, src_row, dest, parent_id, postures, now, op=op
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
                dest_parent_id=parent_id,
                new_paths=new_paths,
                postures=postures,
                authority=authority,
                now=now,
            )
            version = 1
        pending.append(PendingRow(dest, "created", src_row["kind"], version, src_row["size_bytes"]))
    if errors:
        return Result(ops=(op,), errors=errors)
    finals = await final_rows(session, entry, profile, membership_budget, [str(p.path) for p in pending])
    rows = [observe_final(p, finals.get(str(p.path))) for p in pending]
    return Result(ops=(op,), observations=rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
            refused = await claim(
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
    await bump(session, entry, src_row["parent_id"])
    # Both parents bump even when identical — two increments, per the
    # conformance contract.
    await bump(session, entry, dest_parent_id)
    return None


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
    await bump(session, entry, dest_parent_id)


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
