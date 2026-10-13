"""The serialized-verb kit — what delete, restore, sweep, move and copy share.

A serialized verb rewrites or hides part of the namespace that other
rows depend on — a subtree's path caches, the tombstone over a whole
tree, the rows a purge destroys — so it cannot interleave with another
such verb. Each one's first statement takes the per-mount serialization
point (:func:`serialize`: nothing on SQLite, whose writer transaction is
the lock; a transaction-scoped advisory lock on Postgres; an X-lock on
the single meta row everywhere else), and every read runs after it
inside the same transaction, so refusal checks judge post-rival state
and later targets see earlier targets' effects.

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

from sqlalchemy import Update, func, select, update

from vfs.models import Observation
from vfs.results import ErrorKind, ResultError, classified
from vfs.storage.backends.database.descent import ancestor_chain, classify_miss, rows_by_path, targets_with_ancestors
from vfs.storage.backends.database.dialects import StaleSnapshot

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy import Column, Delete, Table
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


async def serialize(session: AsyncSession, profile: DialectProfile, meta: Table, lock_key: int) -> None:
    """Take the serialization point — always the verb's first statement.

    SQLite needs nothing: the writer connection already opened
    ``BEGIN IMMEDIATE``. Postgres takes a transaction-scoped advisory
    lock on the mount's key. Everywhere else a self-assignment UPDATE
    X-locks the single meta row — portable, auto-released at commit,
    serializing rival verbs and first touch alike.
    """
    if profile.name == "sqlite":
        return
    if profile.name == "postgresql":
        await session.execute(select(func.pg_advisory_xact_lock(lock_key)))
        return
    await session.execute(update(meta).where(meta.c.id == 1).values(schema_format_version=meta.c.schema_format_version))


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


async def bump(session: AsyncSession, entry: Table, entry_id: str) -> None:
    """One unguarded SQL-side increment — a namespace change bumps its holder."""
    await session.execute(update(entry).where(entry.c.entry_id == entry_id).values(version=entry.c.version + 1))


# ---------------------------------------------------------------------------
# Reads a serialized verb judges by
# ---------------------------------------------------------------------------


async def fetch_snapshot(
    session: AsyncSession, entry: Table, profile: DialectProfile, membership_budget: int, targets: list[Path]
) -> dict[str, RowMapping]:
    """One bounded fetch: targets, their ancestors, the root — tombstones included, for the caller to judge."""
    columns = [entry.c[name] for name in SNAPSHOT_COLUMNS]
    return await rows_by_path(session, entry, targets_with_ancestors(targets), columns, profile, membership_budget)


async def point_row(session: AsyncSession, entry: Table, path: str) -> RowMapping | None:
    """The row at *path* on either side of the tombstone — the caller judges ``deleted_at``."""
    columns = [entry.c[name] for name in SNAPSHOT_COLUMNS]
    return (await session.execute(select(*columns).where(entry.c.path == path))).mappings().first()


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
