"""The posture gate of an anonymous call that carries a scope channel.

An anonymous caller is judged by the posture rows alone, at every path
its call names. A ``glob``, ``grep`` or ``search`` with scope roots names
the paths composition would have judged: the entry-wide patterns' beside
each root's literal directory joined with each arm's. They are a product
of the caller's inputs, so the gate's pure work runs on the offload pool
under the verb's wall, and only the posture read touches the database.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, NamedTuple

from vfs.deadline import Deadline
from vfs.offload import call_offloaded, offload_pool
from vfs.paths import address_of
from vfs.storage.backends.database.addressing import scope_judged
from vfs.storage.backends.database.labels import posture_rows_for_chunks
from vfs.storage.backends.database.rights import posture_chain, posture_refusals, posture_wall_refusal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.ops import Rung
    from vfs.pattern_matching import ScopeChannel
    from vfs.results import ResultError
    from vfs.storage.backends.database.engine import EngineHost

# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class ScopedGate(NamedTuple):
    """An anonymous scoped call's posture gate: what composition would have judged, and the verb's wall.

    ``patterns`` is the entry-wide channel, ``scope`` the admitted scope
    (roots in entry coordinates, arms expanded), ``piped`` the paths of
    rows piped into the call, judged after the patterns' paths.
    """

    patterns: tuple[str, ...]
    scope: ScopeChannel
    piped: tuple[str, ...]
    wall_seconds: float


async def scoped_refusals(
    session: AsyncSession, host: EngineHost, who: Authority, gate: ScopedGate, rung: Rung
) -> list[ResultError]:
    """An anonymous scoped call's refusals, judged where composition judges, under the verb's wall.

    The judged paths are :func:`scope_judged`'s: the entry-wide patterns'
    beside each root's literal directory joined with each arm's. The pure
    work runs on the offload pool in two hops around the one chunked
    posture read: the judged paths and their sorted, chunked ancestor
    chain first, each path's refusal after. Each hop and the read check
    the wall, read when the gate starts; a gate that reaches it refuses
    the whole call as ``unauthenticated``, because a rights check never
    serves part of a call. The direction is judging each root once from
    the posture in force at it and the posture rows beneath it, linear in
    the roots.
    """
    deadline = Deadline.after(gate.wall_seconds)
    budget = host.membership_budget

    def chained() -> tuple[list[str], list[list[str]]] | None:
        addressed = scope_judged(gate.patterns, gate.scope, deadline=deadline)
        if addressed is None:
            return None
        judged = list(dict.fromkeys(address_of(path).stored for path in (*addressed, *gate.piped)))
        chunks = posture_chain(judged, budget, deadline=deadline)
        return None if chunks is None else (judged, chunks)

    planned = await call_offloaded(offload_pool(), chained)
    if planned is None:
        return [posture_wall_refusal()]
    judged, chunks = planned
    postures = await posture_rows_for_chunks(session, host.tables, host.profile, chunks, deadline=deadline)
    if postures is None:
        return [posture_wall_refusal()]
    judge = partial(posture_refusals, who, postures, judged, rung, deadline=deadline)
    refusals = await call_offloaded(offload_pool(), judge)
    return [posture_wall_refusal()] if refusals is None else refusals
