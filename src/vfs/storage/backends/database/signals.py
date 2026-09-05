"""Ranking signals — stored priors: the reindex phase that computes them, the probe glean reads.

A signal is a query-independent importance prior, one float per entry
in ``[0, 1]``, declared on the mount's :class:`~vfs.storage.ranking.Ranker`
and stored in the ``signals`` table under a generation. It is computed
whole-corpus as a phase of ``reindex`` — :func:`collect_graph` reads the
live entries, their tree, and the reference edges (never the ``fs``
mirror) in keyset pages; :func:`compute_signal` runs the measure, the
hierarchy smoothing, and the scaling off the event loop through the
engine; :func:`publish_signal` writes the new generation beside the old,
flips the signal's pointer row, and sweeps the old generation in one
transaction. ``signals`` is read, never computed, on the query path:
:func:`signal_factors` looks up each declared signal's pointer, drops
one that is missing, computed under other options, or empty (each with
a warning record), probes the stored values for the candidate entries,
and hands back one multiplier per entry, ``∏ (1 + β·t(v))``. A missing
row is factor one.

The collect pass holds the corpus's node and edge arrays in memory —
the same whole-corpus profile as the segment pass, acknowledged rather
than capped; iterative SQL is the out-of-core direction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast

from sqlalchemy import delete, insert, select, update

from vfs.models import CONTENT_KINDS
from vfs.models.edge import RESERVED_EDGE_TYPE
from vfs.models.signals import NO_PARENT, centrality_prior
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database.dialects import bulk_insert, chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.offload import call_offloaded
from vfs.storage.ranking import PathShape

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

    from sqlalchemy import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import EntryId, VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.ranking import Ranker, Signal

SCAN_PAGE_ROWS: Final = 5_000
"""Rows per keyset page of the collect pass — no statement grows with the corpus."""


class GraphInputs(NamedTuple):
    """The live corpus as dense arrays: nodes in ``entry_ids`` order, edges as node indices."""

    entry_ids: list[EntryId]
    parents: list[int]
    files: list[bool]
    depths: list[int]
    sources: list[int]
    targets: list[int]


# ---------------------------------------------------------------------------
# The reindex phase — collect, compute, publish
# ---------------------------------------------------------------------------


async def collect_graph(session: AsyncSession, tables: VFSTables) -> GraphInputs:
    """Every live entry with its parent, kind and depth, and every reference edge between live entries."""
    entry, edges = tables.entry, tables.edges
    index: dict[EntryId, int] = {}
    entry_ids: list[EntryId] = []
    parent_ids: list[EntryId | None] = []
    files: list[bool] = []
    depths: list[int] = []
    last = 0
    while True:
        page = (
            select(entry.c.id, entry.c.entry_id, entry.c.parent_id, entry.c.kind, entry.c.path)
            .where(entry.c.deleted_at.is_(None), entry.c.id > last)
            .order_by(entry.c.id)
            .limit(SCAN_PAGE_ROWS)
        )
        rows = (await session.execute(page)).all()
        if not rows:
            break
        for row in rows:
            index[row.entry_id] = len(entry_ids)
            entry_ids.append(row.entry_id)
            parent_ids.append(row.parent_id)
            files.append(row.kind in CONTENT_KINDS)
            depths.append(row.path.count("/"))
        last = rows[-1].id
    parents = [NO_PARENT if parent_id is None else index.get(parent_id, NO_PARENT) for parent_id in parent_ids]
    sources: list[int] = []
    targets: list[int] = []
    last = 0
    while True:
        page = (
            select(edges.c.id, edges.c.source_id, edges.c.target_id)
            .where(edges.c.edge_type != RESERVED_EDGE_TYPE, edges.c.id > last)
            .order_by(edges.c.id)
            .limit(SCAN_PAGE_ROWS)
        )
        rows = (await session.execute(page)).all()
        if not rows:
            break
        for row in rows:
            source, target = index.get(row.source_id), index.get(row.target_id)
            if source is not None and target is not None:
                sources.append(source)
                targets.append(target)
        last = rows[-1].id
    return GraphInputs(entry_ids, parents, files, depths, sources, targets)


async def compute_signal(executor: Executor, graph: GraphInputs, signal: Signal) -> dict[EntryId, float]:
    """The signal's value per entry that earns one — computed off the event loop."""
    return await call_offloaded(executor, partial(signal_values, graph, signal))


def signal_values(graph: GraphInputs, signal: Signal) -> dict[EntryId, float]:
    """``entry_id → value`` for every file whose prior is above zero — the sparse rows."""
    measure = signal.measure
    if isinstance(measure, PathShape):
        values = _path_shape(graph, measure.sign)
    else:
        values = centrality_prior(
            len(graph.entry_ids), graph.sources, graph.targets, graph.parents, graph.files, measure, signal.smoothing
        )
    return {entry_id: value for entry_id, value in zip(graph.entry_ids, values, strict=True) if value > 0.0}


async def publish_signal(
    session: AsyncSession, tables: VFSTables, signal: Signal, generation: str, values: dict[EntryId, float]
) -> Result:
    """Write *values* under *generation*, point the signal at it, and sweep the generation before.

    One transaction: a reader sees the whole prior generation or the
    whole new one. The pointer row is updated in place, or created on
    the signal's first publish.
    """
    table, epochs = tables.signals, tables.signal_epochs
    rows = [
        {"entry_id": entry_id, "signal": signal.name, "generation": generation, "value": value}
        for entry_id, value in sorted(values.items())
    ]
    if rows:
        await bulk_insert(session, table, rows)
    stamp = {"generation": generation, "options_hash": signal.options_hash(), "row_count": len(rows)}
    flipped = cast(
        "CursorResult[Any]",
        await session.execute(
            update(epochs).where(epochs.c.signal == signal.name).values(created_at=datetime.now(UTC), **stamp)
        ),
    )
    if flipped.rowcount == 0:
        await session.execute(insert(epochs).values(signal=signal.name, created_at=datetime.now(UTC), **stamp))
    await session.execute(delete(table).where(table.c.signal == signal.name, table.c.generation != generation))
    return Result(ops=("reindex",))


async def sweep_undeclared_signals(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, declared: Sequence[str]
) -> Result:
    """Drop every signal the ranker no longer names — its rows and its pointer."""
    table, epochs = tables.signals, tables.signal_epochs
    if declared:
        await session.execute(delete(table).where(~membership(table.c.signal, sorted(declared), profile)))
        await session.execute(delete(epochs).where(~membership(epochs.c.signal, sorted(declared), profile)))
    else:
        await session.execute(delete(table))
        await session.execute(delete(epochs))
    return Result(ops=("reindex",))


# ---------------------------------------------------------------------------
# The query-time probe
# ---------------------------------------------------------------------------


class SignalFactors(NamedTuple):
    """What the probe answered: the multiplier per entry, the records, and the explain rows."""

    factors: dict[EntryId, float]
    records: list[ResultError]
    explain: dict[str, dict[str, Any]]


async def signal_factors(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    ranker: Ranker,
    entry_ids: Sequence[EntryId],
) -> SignalFactors:
    """The declared signals' multipliers over *entry_ids* — the candidates the legs produced.

    A signal with no pointer row, one computed under other options than
    the ranker now declares, or one with no rows at all is dropped with
    a warning record naming why; the rest are probed in one statement
    per candidate chunk, and each stored value becomes ``1 + β·t(v)``.
    """
    if not ranker.signals or not entry_ids:
        return SignalFactors({}, [], {})
    epochs = tables.signal_epochs
    names = sorted(signal.name for signal in ranker.signals)
    pointers = await session.execute(select(epochs).where(membership(epochs.c.signal, names, profile)))
    pointer = {row.signal: row for row in pointers}
    live: dict[str, tuple[Signal, str]] = {}
    records: list[ResultError] = []
    explain: dict[str, dict[str, Any]] = {}
    for signal in ranker.signals:
        row = pointer.get(signal.name)
        if row is None:
            reason = "not computed yet; run reindex"
        elif row.options_hash != signal.options_hash():
            reason = "computed under other options; run reindex"
        elif row.row_count == 0:
            reason = "no entry earned a value"
        else:
            live[signal.name] = (signal, row.generation)
            continue
        explain[signal.name] = {"applied": False, "reason": reason}
        records.append(
            ResultError(
                kind=VFSErrorKind.unavailable,
                severity=Severity.warning,
                message=f"signal {signal.name!r} not applied: {reason}",
                data={"leg": "signal", "signal": signal.name, "reason": reason},
            )
        )
    if not live:
        return SignalFactors({}, records, explain)
    table = tables.signals
    generations = sorted({generation for _, generation in live.values()})
    found: dict[str, dict[EntryId, float]] = {name: {} for name in live}
    per_chunk = max(1, membership_budget - len(live) - len(generations))
    for chunk in chunked(sorted(entry_ids), per_chunk):
        stmt = select(table.c.entry_id, table.c.signal, table.c.generation, table.c.value).where(
            membership(table.c.entry_id, chunk, profile),
            membership(table.c.signal, sorted(live), profile),
            membership(table.c.generation, generations, profile),
        )
        for row in await session.execute(stmt):
            if row.signal in live and row.generation == live[row.signal][1]:
                found[row.signal][row.entry_id] = row.value
    factors: dict[EntryId, float] = {}
    for name, (signal, generation) in live.items():
        explain[name] = {
            "applied": True,
            "generation": generation,
            "entries": len(found[name]),
            "weight": signal.weight,
            "transform": repr(signal.transform),
        }
        for entry_id, value in found[name].items():
            factors[entry_id] = factors.get(entry_id, 1.0) * signal.factor(value)
    return SignalFactors(factors, records, explain)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _path_shape(graph: GraphInputs, sign: int) -> list[float]:
    """Depth min-max scaled over the files; ``sign`` below zero favours the shallow."""
    scored = [depth for depth, file in zip(graph.depths, graph.files, strict=True) if file]
    if not scored:
        return [0.0] * len(graph.depths)
    low, span = min(scored), max(scored) - min(scored)
    if span == 0:
        return [0.0] * len(graph.depths)
    out = []
    for depth, file in zip(graph.depths, graph.files, strict=True):
        scaled = (depth - low) / span
        out.append(0.0 if not file else scaled if sign > 0 else 1.0 - scaled)
    return out
