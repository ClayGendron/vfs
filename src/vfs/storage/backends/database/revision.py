"""The grant revisions — the admin lock every grants write takes first, and the stamps that key the rights cache.

One row holds the mount-wide revision (``meta.grant_revision``).
Advancing it is the first statement of every grant, posture or
membership write, so rival admin writes serialize behind the row's write
lock and each one decides on settled state; the value stamps version
rows and every grant row written under it. A relabel chunk takes the
same lock without advancing the value: it changes no right, only labels.

The value also stamps the principals a write names, one row each in
``principal_revisions``: a grant or revoke stamps its grantee, a
membership write stamps the member whose closure it changes, a posture
write stamps the everyone principal. A caller's compile is keyed on the
greatest stamp over its subjects and their groups, so a write retires
exactly the compiles of the callers it reaches and no other.

    revision = await bump_revision(session, tables)             # the lock, then the new value
    await stamp_principals(session, tables, ["ann"], revision)  # ann's compile is retired
    stamp = await principal_revision(session, tables, profile, budget, ["ann", "group:eng"])
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import func, insert, select, update

from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile


# ---------------------------------------------------------------------------
# The mount-wide revision — the admin lock
# ---------------------------------------------------------------------------


async def read_revision(session: AsyncSession, tables: VFSTables) -> int:
    """The grant spine's current revision — one single-row read."""
    meta = tables.meta
    value = (await session.execute(select(meta.c.grant_revision).where(meta.c.id == 1))).scalar_one_or_none()
    return int(value or 0)


async def bump_revision(session: AsyncSession, tables: VFSTables) -> int:
    """Advance the grant revision — the first statement of every grant or membership write."""
    meta = tables.meta
    await session.execute(update(meta).where(meta.c.id == 1).values(grant_revision=meta.c.grant_revision + 1))
    return await read_revision(session, tables)


async def hold_revision(session: AsyncSession, tables: VFSTables) -> int:
    """Take the admin lock without advancing the revision; the value in force under it.

    An ``UPDATE`` that writes the row's own value back: every engine
    locks the row for it as it does for a bump, and rights change by
    nothing, so no cached compile is retired. The read follows the lock,
    so an engine that pins its snapshot at the first plain read sees the
    state the lock serialized behind.
    """
    meta = tables.meta
    await session.execute(update(meta).where(meta.c.id == 1).values(grant_revision=meta.c.grant_revision))
    return await read_revision(session, tables)


# ---------------------------------------------------------------------------
# The per-principal stamps — what keys a caller's compile
# ---------------------------------------------------------------------------


async def principal_revision(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, ids: Iterable[str]
) -> int:
    """The greatest stamp over *ids* — ``0`` when no write has ever named any of them.

    One chunked read, bounded by the number of ids: a caller's subjects
    and their closure groups, which are dozens.
    """
    revisions = tables.principal_revisions
    stamp = 0
    for chunk in chunked(sorted(set(ids)), membership_budget):
        stmt = select(func.max(revisions.c.revision)).where(membership(revisions.c.principal_id, chunk, profile))
        found = (await session.execute(stmt)).scalar_one_or_none()
        stamp = max(stamp, int(found or 0))
    return stamp


async def stamp_principals(session: AsyncSession, tables: VFSTables, ids: Iterable[str], revision: int) -> None:
    """Stamp each of *ids* with *revision*, the admin lock's value this write bumped to.

    Under the lock no rival stamps the same row, so an update that finds
    no row is followed by the insert. *revision* is greater than every
    stamp before it, so any compile keyed on one of *ids* is retired.
    """
    revisions = tables.principal_revisions
    for principal in dict.fromkeys(ids):
        stamp = update(revisions).where(revisions.c.principal_id == principal).values(revision=revision)
        if cast("CursorResult[Any]", await session.execute(stamp)).rowcount == 0:
            await session.execute(insert(revisions).values(principal_id=principal, revision=revision))
