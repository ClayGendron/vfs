"""The two questions a caller asks of the rights tables without writing.

One lists the grants the caller may see. The other says whether the
caller holds a level at a path. Each resolves the caller's gate on the
read session it is given, and ``rights`` does the judging.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vfs.ops import VERB_RUNGS, Needs
from vfs.results import Result, ResultError
from vfs.storage.backends.database.rights import grant_refusal, list_grants
from vfs.storage.protocol import HOLDS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.ops import Rung
    from vfs.paths import Path
    from vfs.storage.backends.database.engine import EngineHost
    from vfs.storage.backends.database.rights import WriteGate

    GateFor = Callable[[AsyncSession, Authority, Needs], Awaitable[WriteGate | ResultError]]

# ---------------------------------------------------------------------------
# The questions
# ---------------------------------------------------------------------------


async def listed_grants(
    session: AsyncSession, host: EngineHost, gate_for: GateFor, who: Authority, path: Path
) -> Result:
    """The grant rows on *path* and its ancestors that *who* may see."""
    gate = await gate_for(session, who, VERB_RUNGS["grants"])
    if isinstance(gate, ResultError):
        return Result(ops=("grants",), errors=[gate])
    return await list_grants(session, host.tables, host.profile, host.membership_budget, gate, path=path, authority=who)


async def held(
    session: AsyncSession, host: EngineHost, gate_for: GateFor, who: Authority, path: Path, level: Rung
) -> Result:
    """Whether *who* holds *level* at *path*. A failed result carries the reason, as a verb's refusal would."""
    gate = await gate_for(session, who, Needs(level))
    if isinstance(gate, ResultError):
        return Result(ops=(HOLDS,), errors=[gate])
    refusal = await grant_refusal(
        session, host.tables, host.profile, host.membership_budget, HOLDS, gate, path, None, level, subtree=False
    )
    return Result(ops=(HOLDS,), errors=[] if refusal is None else [refusal])
