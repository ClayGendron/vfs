"""The sweep: expired records are removed in bounded chunks, and only when the public ``sweep`` is called.

Expiry does not depend on the sweep: every read of a table that expires
filters on its expiry against ``store.now()``, so a record past its
expiry reads as absent before it is swept. The sweep only gives the
space back. A table that expires registers a :data:`Sweeper`, and a pass
calls each sweeper in a ``commit`` of its own with ``SWEEP_CHUNK`` until a
call removes no row. Each chunk is a transaction of its own, so a lock is
held for a commit's length, and a pass that is cancelled or fails has
removed whole chunks and nothing else. Between two chunks the store's own
flush goes first, so rows written behind wait a chunk and not a pass.

    store.register_sweeper("jobs", expiry_sweeper(jobs, key=jobs.c.job_id,
                                                  expires=jobs.c.expires_at,
                                                  dependents=(pages.c.job_id,)))
    removed = await store.sweep()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final, TypeAlias

from sqlalchemy import and_, exists, select

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Sequence
    from datetime import datetime

    from sqlalchemy import Column, Table

    from vfs.kernel_store.store import KernelStore, Transaction

Sweeper: TypeAlias = "Callable[[KernelStore, Transaction, datetime, int], Awaitable[int]]"
"""A function that removes at most its limit of expired rows in the transaction it is handed, and says how many.

It is handed the store, a transaction, the pass's one reading of the
clock and a limit, and removes a parent only when its dependents are gone.
"""

SWEEP_CHUNK: Final = 5_000
"""The rows one call of a sweeper may remove: one transaction of a pass."""

_log: Final = logging.getLogger(__name__)

_FAILED: Final = (
    "a sweep of the kernel store at %s failed after %d records were removed (%s); the next sweep starts over"
)


# ---------------------------------------------------------------------------
# A table that expires with its dependents
# ---------------------------------------------------------------------------


def expiry_sweeper(
    table: Table,
    *,
    key: Column[Any],
    expires: Column[datetime],
    dependents: Sequence[Column[Any]] = (),
) -> Sweeper:
    """A sweeper for *table*, whose rows expire at *expires*, and for the rows of other tables that name them.

    Each of *dependents* is a column of another table that holds the
    parent's *key*; that table's primary key is what its rows are deleted
    by. One call first removes, for each dependent in order, its rows that
    name an expired parent, then the expired parents that have no
    dependent row left, oldest first, each up to what is left of the
    limit. A parent is never removed before its dependents, and every
    statement binds the same few values at any size.
    """

    async def sweep(store: KernelStore, transaction: Transaction, now: datetime, limit: int) -> int:
        removed = 0
        expired = select(key).where(expires <= now)
        for column in dependents:
            if removed >= limit:
                return removed
            dependent = column.table
            primary = list(dependent.primary_key.columns)
            removed += await store.delete_where(
                transaction, dependent, key=primary, where=column.in_(expired), limit=limit - removed
            )
        if removed >= limit:
            return removed
        orphaned = and_(expires <= now, *(~exists().where(column == key) for column in dependents))
        removed += await store.delete_where(
            transaction, table, key=key, where=orphaned, limit=limit - removed, order_by=expires
        )
        return removed

    return sweep


# ---------------------------------------------------------------------------
# A pass
# ---------------------------------------------------------------------------


async def sweep_pass(
    store: KernelStore,
    sweepers: Iterable[Sweeper],
    *,
    label: str,
    keeps_records: Callable[[], Awaitable[bool]],
    between: Callable[[], Awaitable[None]],
) -> int:
    """One pass: each sweeper in turn, a ``commit`` a chunk, until a call removes no row; the rows removed.

    *keeps_records* says whether the place holds the kernel's tables at
    all; a place that holds none is swept of nothing and given no table.
    *between* runs between two chunks, and lets the store's own flush go
    first. A pass that fails logs one ``WARNING`` and raises.
    """
    removed = 0
    try:
        if not await keeps_records():
            return 0
        now = store.now()
        for sweeper in sweepers:
            while True:
                found = await store.commit(_chunk(store, sweeper, now))
                removed += found
                if not found:
                    break
                await between()
    except Exception as failure:
        _log.warning(_FAILED, label, removed, failure)
        raise
    return removed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _chunk(store: KernelStore, sweeper: Sweeper, now: datetime) -> Callable[[Transaction], Awaitable[int]]:
    """The ``fn`` of one chunk's commit: one call of *sweeper*, with the pass's clock and the chunk's limit."""

    async def chunk(transaction: Transaction) -> int:
        return await sweeper(store, transaction, now, SWEEP_CHUNK)

    return chunk
