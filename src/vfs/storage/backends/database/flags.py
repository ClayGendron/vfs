"""Flag repair — directories a store wrote before they were created encoded, re-converged by the rebuild.

A plain collect, then a guarded repair: the shape of the segment and edge passes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import select, update

from vfs.results import Result
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile

_SCAN_YIELD_ROWS: Final = 256


@dataclass
class FlagRebuildState:
    """Carry-over between the rebuild flag phases' separate transactions."""

    ids: list[str] = field(default_factory=list)
    repaired: int = 0

    @property
    def clean(self) -> bool:
        return not self.ids


async def collect_flag_drift(session: AsyncSession, tables: VFSTables, state: FlagRebuildState) -> Result:
    """Find the directory rows still flagged as awaiting the index.

    A plain read — no writer is blocked. On a store this rule wrote it
    is one seek on the (encoded, kind) index that returns nothing; on an
    earlier store it returns every directory once, the only time the
    result grows with the store.
    """
    entry = tables.entry
    scan = select(entry.c.entry_id).where(entry.c.kind == "directory", ~entry.c.encoded)
    async for row in await session.stream(scan.execution_options(yield_per=_SCAN_YIELD_ROWS)):
        state.ids.append(row.entry_id)
    return Result(ops=("rebuild",))


async def repair_flag_drift(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    state: FlagRebuildState,
) -> Result:
    """Flip the collected directories true, each guarded on still being an unencoded directory.

    Chunked by the membership budget, so no statement grows with the
    count. The guard keeps a row whose kind changed under its id from
    being stamped covered with no grams; the count of rows flipped is
    what the backend reports.
    """
    entry = tables.entry
    for chunk in chunked(sorted(state.ids), membership_budget):
        stmt = (
            update(entry)
            .where(membership(entry.c.entry_id, chunk, profile), entry.c.kind == "directory", ~entry.c.encoded)
            .values(encoded=True)
        )
        state.repaired += cast("CursorResult[Any]", await session.execute(stmt)).rowcount
    return Result(ops=("rebuild",))
