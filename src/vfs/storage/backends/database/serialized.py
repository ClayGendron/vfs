"""The serialized-verb kit — what delete, restore, sweep, move and copy share.

A serialized verb rewrites or hides part of the namespace that other
rows depend on — a subtree's path caches, the tombstone over a whole
tree, the rows a purge destroys — so it cannot interleave with another
such verb. Each one's first statement takes the per-mount serialization
point (:func:`serialize`: a locking read of the one-row lock table,
which nothing else reads, so a verb never holds up a write, a read or a
rights compile), and every read runs after it inside the same
transaction, so refusal checks judge post-rival state and later targets
see earlier targets' effects.

Writes are deliberately *not* serialized with these verbs, so every
claim a verb makes on a row is guarded on the version it read at the
probe that judged it (:func:`claim`): a rival write committing inside
the window bumps the row and flips the guard, and the verb redrives
whole from a fresh snapshot — re-collection is correctness by
construction. The same discipline covers a destination-address claim
lost to an unserialized rival: the unique violation redrives, and the
fresh ladder returns the honest per-pair refusal with the caller's own
attribution — never a classification off mid-race state, never raw
driver text. Every guard proves it matched through what the dialect
verifiably reports (rowcount where sane, RETURNING where modeled) or
refuses ``unsupported``.

A verb that claims many rows at once uses :func:`claim_rows`: one
guarded update over the whole claim set, set-based where the dialect
runs a VALUES join, verified executemany elsewhere, so the claim costs
one statement per chunk whatever the batch size. :func:`bump_many` is
the set form of the bump.

The rest of the kit is the shared shape of such a verb: one bounded
pre-batch snapshot of the targets and their ancestors
(:func:`fetch_snapshot`), a point read on either side of the tombstone
(:func:`point_row`), the live parent gate a destination must pass
(:func:`dest_parent_id`), the unguarded bump a namespace change owes
its holder (:func:`bump`), and the observation of each executed target
re-read after the batch (:class:`PendingRow`, :func:`final_rows`,
:func:`observe_final`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from sqlalchemy import Update, bindparam, column, select, update, values

from vfs.models import Observation
from vfs.results import ErrorKind, ResultError, classified
from vfs.storage.backends.database.descent import ancestor_chain, classify_miss, rows_by_path, targets_with_ancestors
from vfs.storage.backends.database.dialects import (
    StaleSnapshot,
    chunked,
    lock_rows,
    statement_budget,
    supports_values_update,
)
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from typing import Any

    from sqlalchemy import Column, ColumnElement, Delete, Table
    from sqlalchemy.engine import CursorResult, RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.paths import ObjectKind, Path
    from vfs.storage.backends.database.dialects import DialectProfile

# The pre-batch committed snapshot: classification and observation state.
SNAPSHOT_COLUMNS: Final[tuple[str, ...]] = (
    "entry_id",
    "parent_id",
    "path",
    "name",
    "kind",
    "version",
    "size_bytes",
    "deleted_at",
)


class Claim(NamedTuple):
    """One row a verb claims: its id and the version the verb judged it at."""

    entry_id: str
    version: int


class PendingRow(NamedTuple):
    """One executed target's observation, captured at execution time.

    The captured values are the fallback: after the loop every pending
    path is re-read in one chunked pass and the final values win — a
    later target may have bumped an earlier one — but a path a later
    target moved away falls back to these.
    """

    path: Path
    status: Literal["created", "unchanged"]
    kind: ObjectKind
    version: int
    size_bytes: int


# ---------------------------------------------------------------------------
# The serialization point and the guarded claim
# ---------------------------------------------------------------------------


async def serialize(session: AsyncSession, profile: DialectProfile, lock: Table) -> None:
    """Take the serialization point — always the verb's first statement.

    One locking read of the mount's single lock row, held to the end of
    the transaction: rival serialized verbs queue on it, and nothing
    else ever reads that row, so no write, read or rights compile waits
    behind a verb on any engine. Spelled as the kit's locking read —
    ``FOR UPDATE`` wherever the compiler renders it, the profile's hint
    on T-SQL; on SQLite, whose writer transaction is the lock, the read
    is inert.
    """
    await session.execute(lock_rows(select(lock.c.id).where(lock.c.id == 1), lock, profile))


async def claim(
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


async def claim_rows(
    session: AsyncSession,
    entry: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    claims: Sequence[Claim],
    *,
    side: ColumnElement[bool],
    assign: Mapping[str, Any],
    miss: str,
) -> ResultError | None:
    """One guarded update over every claim, proving each matched.

    The statement sets *assign* on each claimed row where its id, its
    judged version and the tombstone *side* all hold. It runs set-based
    over a VALUES join with RETURNING where the dialect runs one,
    executemany verified by the aggregate rowcount where that is sane,
    the per-row floor where only single rowcounts are, else a
    classified ``unsupported`` — an unverifiable guarded claim never
    proceeds. Any shortfall raises :class:`StaleSnapshot` with *miss*
    as its context: the verb redrives whole.
    """
    if not claims:
        return None
    dialect = session.get_bind().dialect
    if supports_values_update(profile, dialect):

        def build(rows: Sequence[Claim]) -> Update:
            return _claim_values_stmt(entry, rows, side, assign)

        per_statement = statement_budget(
            build,
            claims[0],
            dialect,
            parameter_budget=parameter_budget,
            row_width=len(claims[0]),
            row_cap=membership_budget,
        )
        for chunk in chunked(claims, per_statement):
            matched = len((await session.execute(build(chunk))).all())
            _prove(matched, len(chunk), miss)
        return None
    if not dialect.supports_sane_rowcount:
        detail = f"guarded claims cannot be verified on {profile.name}: no RETURNING, no sane rowcount"
        return classified(ErrorKind.unsupported, detail=detail)
    stmt = (
        update(entry)
        .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_ver"), side)
        .values(**assign)
    )
    for chunk in chunked(claims, membership_budget):
        params = [{"b_id": claim_.entry_id, "b_ver": claim_.version} for claim_ in chunk]
        if dialect.supports_sane_multi_rowcount:
            matched = cast("CursorResult[Any]", await session.execute(stmt, params)).rowcount
        else:
            matched = 0
            for row_params in params:
                matched += cast("CursorResult[Any]", await session.execute(stmt, row_params)).rowcount
        _prove(matched, len(params), miss)
    return None


async def bump(session: AsyncSession, entry: Table, entry_id: str) -> None:
    """One unguarded SQL-side increment — a namespace change bumps its holder."""
    await session.execute(update(entry).where(entry.c.entry_id == entry_id).values(version=entry.c.version + 1))


async def bump_many(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, entry_ids: Iterable[str]
) -> None:
    """The set form of :func:`bump`: each distinct holder once, one statement per chunk."""
    for chunk in chunked(sorted(set(entry_ids)), membership_budget):
        stmt = update(entry).where(membership(entry.c.entry_id, chunk, profile)).values(version=entry.c.version + 1)
        await session.execute(stmt)


# ---------------------------------------------------------------------------
# Reads a serialized verb judges by
# ---------------------------------------------------------------------------


async def fetch_snapshot(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, targets: list[Path]
) -> dict[str, RowMapping]:
    """One bounded fetch: targets, their ancestors, the root — tombstones included, for the caller to judge."""
    columns = snapshot_columns(entry)
    return await rows_by_path(session, entry, targets_with_ancestors(targets), columns, profile, membership_budget)


async def point_row(session: AsyncSession, entry: Table, path: str) -> RowMapping | None:
    """The row at *path* on either side of the tombstone — the caller judges ``deleted_at``."""
    stmt = select(*snapshot_columns(entry)).where(entry.c.path == path)
    return (await session.execute(stmt)).mappings().first()


def snapshot_columns(entry: Table, names: Sequence[str] = SNAPSHOT_COLUMNS) -> list[Column[Any]]:
    """The entry columns *names* select — the snapshot's by default."""
    return [entry.c[name] for name in names]


async def dest_parent_id(
    session: AsyncSession, entry: Table, dest: Path, profile: DialectProfile, membership_budget: int
) -> str | ResultError:
    """The destination's parent id after the live POSIX parent gate.

    A missing or tombstoned ancestor is ``not_found`` at that component
    (the tombstone carries its hint), a non-directory is ``wrong_kind``
    there — the shared descent ladder, read live so a parent minted by
    an earlier target in the batch counts.
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


# ---------------------------------------------------------------------------
# Observing the executed batch
# ---------------------------------------------------------------------------


async def final_rows(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, paths: list[str]
) -> dict[str, RowMapping]:
    """One bounded re-read of every pending path after the batch."""
    columns = [entry.c.path, entry.c.kind, entry.c.version, entry.c.size_bytes]
    return await rows_by_path(session, entry, paths, columns, profile, membership_budget)


def observe_final(pending: PendingRow, final: RowMapping | None) -> Observation:
    """The observation of one executed target: the re-read row where it still stands, else the captured values."""
    if final is None:
        return Observation(
            path=pending.path,
            kind=pending.kind,
            size_bytes=pending.size_bytes,
            version=pending.version,
            status=pending.status,
        )
    return Observation(
        path=pending.path,
        kind=final["kind"],
        size_bytes=final["size_bytes"],
        version=final["version"],
        status=pending.status,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _claim_values_stmt(
    entry: Table, rows: Sequence[Claim], side: ColumnElement[bool], assign: Mapping[str, Any]
) -> Update:
    """One guarded claim as a VALUES join over *rows*, RETURNING the ids it matched."""
    incoming = values(
        column("v_id", entry.c.entry_id.type),
        column("v_ver", entry.c.version.type),
        name="incoming",
    ).data(list(rows))
    return (
        update(entry)
        .where(entry.c.entry_id == incoming.c.v_id, entry.c.version == incoming.c.v_ver, side)
        .values(**assign)
        .returning(entry.c.entry_id)
    )


def _prove(matched: int, expected: int, miss: str) -> None:
    """A guarded claim set matched every row, or the snapshot it judged is stale."""
    if matched != expected:
        raise StaleSnapshot(miss)
