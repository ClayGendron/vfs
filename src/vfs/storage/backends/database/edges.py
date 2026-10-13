"""Edge-row maintenance for ``DatabaseStorage`` — the fs mirror and
reindex re-convergence.

One reserved-type ``"fs"`` edge row per non-root entry, ``(parent →
entry)``, minted and maintained inside the same transactions that mutate
the namespace: creates insert beside their segment postings, a move
repoints the one moved root's row by id, a copy mints rows for its fresh
ids, and the purge arm already deletes every edge touching a destroyed
id. The mirror follows ``parent_id`` everywhere, so the invariant is
uniform: every entry with a parent has exactly one fs in-edge naming it.
``parent_id`` is authoritative; on any disagreement the fs rows are
wrong.

A delete moves nothing — the row stays at its path with a tombstone —
so the fs mirror needs no repoint and authored edges need no cascade:
an edge whose endpoint is tombstoned is hidden with it by the liveness
term every edge reader carries, and it returns with ``restore`` or a
revive. Authored edges (every non-``fs`` row) die in exactly two ways:
``rmedge`` removes them by triple, or the purge destroys an endpoint.
``mkedge`` resolves its endpoints among the live rows under row locks,
so a rival delete serializes behind the insert and no verb lands an
edge on a tombstoned entry.

The reindex verb re-converges the fs rows to ``parent_id`` — the
segment-postings discipline: :func:`collect_edge_drift` diffs from a
plain read, :func:`repair_edge_drift` applies each entry's delta only
while the row still holds the parent the delta was computed from (the
row is locked for the check), and every applied repair surfaces as a
warning — drift means a namespace verb failed its maintenance, and that
bug must surface. Edge rows naming an endpoint with no entry row at all
are reclaimed the same pass. The collect pass holds the corpus's ids in
memory — the same whole-corpus profile as the segment pass, acknowledged
rather than capped; streamed merge passes are the future direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sqlalchemy import bindparam, cast, column, delete, insert, select, update, values
from sqlalchemy.exc import IntegrityError

from vfs.models import Observation
from vfs.models.edge import RESERVED_EDGE_TYPE
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.descent import classify_misses
from vfs.storage.backends.database.dialects import bulk_insert, chunked, statement_budget
from vfs.storage.backends.database.membership import locked_lookup, membership
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.dml import Update

    from vfs.authority import Authority
    from vfs.models import Edge
    from vfs.models.rows import VFSTables
    from vfs.paths import Path
    from vfs.storage.backends.database.dialects import DialectProfile

# One edge's stored identity: resolved endpoint ids plus the type segment.
_Triple = tuple[str, str, str]

# The identity probe binds three lists per statement; a chunk shares the budget.
_PROBE_LISTS = 3

# The executemany touch's bind names, in the touch row's column order.
_TOUCH_BINDS = ("b_id", "b_weight", "b_distance", "b_prov")

# Rows the collect pass streams per fetch — bounds driver buffering, not memory.
_SCAN_YIELD_ROWS = 1024


# ---------------------------------------------------------------------------
# Write-path maintenance — the fs mirror
# ---------------------------------------------------------------------------


def fs_row(parent_id: str, entry_id: str) -> dict[str, str]:
    """The one fs mirror row for *entry_id* under *parent_id*."""
    return {"source_id": parent_id, "target_id": entry_id, "edge_type": RESERVED_EDGE_TYPE, "provenance": "system"}


async def insert_fs_rows(session: AsyncSession, edges: Table, pairs: Iterable[tuple[str, str]]) -> None:
    """Insert the fs mirror rows for freshly created ``(parent_id, entry_id)`` rows.

    ``bulk_insert`` pages it under the dialect's parameter budget, like
    the segment postings beside it.
    """
    rows = [fs_row(parent_id, entry_id) for parent_id, entry_id in pairs]
    if rows:
        await bulk_insert(session, edges, rows)


async def repoint_fs_row(session: AsyncSession, edges: Table, entry_id: str, new_parent_id: str) -> None:
    """Re-source the one moved entry's fs in-edge — id-keyed, descendants untouched.

    Unguarded like the descendant path rewrites: the caller's claim on
    the entry row is the serialization proof, and nothing observable on
    the edge changed but its source.
    """
    stmt = (
        update(edges)
        .where(edges.c.target_id == entry_id, edges.c.edge_type == RESERVED_EDGE_TYPE)
        .values(source_id=new_parent_id)
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# The caller pair — mkedge touch/upsert, rmedge removal by triple
# ---------------------------------------------------------------------------


async def mkedge_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    *,
    edges: list[Edge],
    provenance: str,
    authority: Authority | None,
) -> Result:
    """Adjudicate and apply a batch of edge touches as a set.

    Endpoints resolve by path under row locks — the resolve is the
    liveness proof: a rival delete serializes behind this commit, and
    its cascade then sweeps whatever landed here. A missing endpoint
    classifies ``not_found`` and fails the batch whole — the write
    family's doctrine, and no statement runs. Existing identities are
    probed the same way, so every row's status (``created`` or
    ``updated``, the touch refreshing ``weight``/``distance``/
    ``provenance`` by row id — one ``VALUES`` join where the engine
    takes it, executemany elsewhere) is known without RETURNING; a duplicate racing in
    from a row-layer writer (verb batches serialize on the endpoint
    locks) surfaces as a unique violation on the insert, redrives
    row-by-row under savepoints, and lands as the touch it raced.
    *authority* is not yet used; edges carry no ownership today.
    """
    table = tables.edges
    ids = await _endpoint_ids(session, tables, profile, membership_budget, edges, lock=True)
    if missing := _missing_endpoints(edges, ids):
        errors = await classify_misses(session, tables.entry, missing, profile, membership_budget)
        return Result(ops=("mkedge",), errors=errors)
    existing = await _existing_triples(session, table, profile, membership_budget, _wanted_triples(edges, ids))
    creates: list[dict[str, object]] = []
    touches: list[tuple[int, dict[str, object]]] = []
    status: dict[_Triple, Literal["created", "updated", "deleted"]] = {}
    for edge in edges:
        triple = (ids[str(edge.source)], ids[str(edge.target)], edge.edge_type)
        values: dict[str, object] = {
            "source_id": triple[0],
            "target_id": triple[1],
            "edge_type": triple[2],
            "weight": edge.weight,
            "distance": edge.distance,
            "provenance": provenance,
        }
        row_id = existing.get(triple)
        if row_id is not None:
            status[triple] = "updated"
            touches.append((row_id, values))
        else:
            status[triple] = "created"
            creates.append(values)
    await seam("mkedge:before-insert")
    conflicted = await insert_arbitrated(session, table, creates)
    if conflicted:
        # The rival's rows are re-probed for their ids; one it has since
        # deleted lands nowhere, the same end state the touch would leave.
        raced = {_triple_of(values): values for values in conflicted}
        status.update(dict.fromkeys(raced, "updated"))
        found = await _existing_triples(session, table, profile, membership_budget, set(raced))
        touches.extend((row_id, raced[triple]) for triple, row_id in found.items())
    if touches:
        await _touch_rows(session, table, profile, parameter_budget, membership_budget, touches)
    rows = [
        _observe_edge(edge, status=status[(ids[str(edge.source)], ids[str(edge.target)], edge.edge_type)])
        for edge in edges
    ]
    return Result(ops=("mkedge",), observations=rows)


async def rmedge_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    *,
    edges: list[Edge],
    authority: Authority | None,
) -> Result:
    """Remove edges by exact triple; what is absent is a per-row warning.

    A missing endpoint or identity is a warning-severity ``not_found``
    record, never a batch error — removing what is already gone leaves
    the same end state, so the batch commits what it found. Statuses
    come from the probe that bounds the delete; a rival removing the
    same triple inside the window yields the identical end state.
    *authority* is not yet used.
    """
    table = tables.edges
    ids = await _endpoint_ids(session, tables, profile, membership_budget, edges)
    existing = await _existing_triples(session, table, profile, membership_budget, _wanted_triples(edges, ids))
    rows: list[Observation] = []
    warnings: list[ResultError] = []
    doomed: set[int] = set()
    for edge in edges:
        source_id, target_id = ids.get(str(edge.source)), ids.get(str(edge.target))
        row_id = existing.get((source_id, target_id, edge.edge_type)) if source_id and target_id else None
        if row_id is None:
            warnings.append(
                classified(
                    ErrorKind.not_found,
                    edge.source,
                    target=edge.target,
                    severity=Severity.warning,
                    detail=f"no {edge.edge_type} edge to the target",
                    data={"edge_type": edge.edge_type},
                )
            )
            continue
        doomed.add(row_id)
        rows.append(_observe_edge(edge, status="deleted"))
    for chunk in chunked(sorted(doomed), membership_budget):
        await session.execute(delete(table).where(membership(table.c.id, chunk, profile)))
    return Result(ops=("rmedge",), observations=rows, errors=warnings)


# ---------------------------------------------------------------------------
# Reindex re-convergence — collect drift, repair it under parent guards
# ---------------------------------------------------------------------------


@dataclass
class FsDelta:
    """One entry's fs-mirror drift, pinned to the parent it was computed from."""

    entry_id: str
    parent_id: str | None
    wrong_row_ids: list[int]
    missing: bool


@dataclass
class EdgeRebuildState:
    """Carry-over between the reindex edge phases' separate transactions."""

    deltas: list[FsDelta] = field(default_factory=list)
    dangling: list[int] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.deltas and not self.dangling


async def collect_edge_drift(session: AsyncSession, tables: VFSTables, state: EdgeRebuildState) -> Result:
    """Diff the fs rows against ``parent_id`` and find dangling endpoints.

    A plain read — no writer is blocked. Each drifted entry's delta is
    recorded with the parent it was computed from, which becomes the
    repair pass's guard; edge rows of any type naming an endpoint with
    no entry row are recorded as dangling (their guard is that absence,
    permanent — an entry id never returns). A tombstoned endpoint is an
    entry like any other here: its edges wait with it for the restore.
    """
    entry, edges = tables.entry, tables.edges
    parents: dict[str, str | None] = {}
    entry_scan = select(entry.c.entry_id, entry.c.parent_id).execution_options(yield_per=_SCAN_YIELD_ROWS)
    async for row in await session.stream(entry_scan):
        parents[row.entry_id] = row.parent_id
    held: dict[str, list[tuple[int, str]]] = {}
    edge_scan = select(edges.c.id, edges.c.source_id, edges.c.target_id, edges.c.edge_type).execution_options(
        yield_per=_SCAN_YIELD_ROWS
    )
    async for row in await session.stream(edge_scan):
        if row.source_id not in parents or row.target_id not in parents:
            state.dangling.append(row.id)
        elif row.edge_type == RESERVED_EDGE_TYPE:
            held.setdefault(row.target_id, []).append((row.id, row.source_id))
    for entry_id, parent_id in parents.items():
        rows = held.get(entry_id, [])
        wrong = [row_id for row_id, source_id in rows if parent_id is None or source_id != parent_id]
        missing = parent_id is not None and not any(source_id == parent_id for _, source_id in rows)
        if wrong or missing:
            state.deltas.append(FsDelta(entry_id, parent_id, wrong, missing))
    return Result(ops=("reindex",))


async def repair_edge_drift(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, state: EdgeRebuildState
) -> Result:
    """Apply the collected deltas, each guarded by the parent it was computed from.

    The guard re-read locks the entry rows (:func:`~vfs.storage.backends.database.membership.locked_lookup`), so a rival
    topology verb serializes against this repair instead of interleaving
    with it. A delta whose row now names a different parent — or whose
    row is gone — is skipped: the rival's synchronous maintenance is the
    truth. Every applied repair surfaces as a warning: drift is a
    maintenance bug being surfaced, never silently absorbed.
    """
    entry, edges = tables.entry, tables.edges
    current: dict[str, str | None] = {}
    guarded = {delta.entry_id for delta in state.deltas}
    for chunk in chunked(sorted(guarded), membership_budget):
        guard = locked_lookup(entry, entry.c.entry_id, chunk, [entry.c.entry_id, entry.c.parent_id], profile)
        current.update({row.entry_id: row.parent_id for row in await session.execute(guard)})
    confirmed = [
        delta for delta in state.deltas if delta.entry_id in current and current[delta.entry_id] == delta.parent_id
    ]
    doomed = [row_id for delta in confirmed for row_id in delta.wrong_row_ids] + state.dangling
    for chunk in chunked(doomed, membership_budget):
        await session.execute(delete(edges).where(membership(edges.c.id, chunk, profile)))
    additions = [fs_row(delta.parent_id, delta.entry_id) for delta in confirmed if delta.missing and delta.parent_id]
    if additions:
        await bulk_insert(session, edges, additions)
    warnings = [_drift_warning(delta) for delta in confirmed]
    if state.dangling:
        warnings.append(_dangling_warning(len(state.dangling)))
    return Result(ops=("reindex",), errors=warnings)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _endpoint_ids(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    edges: list[Edge],
    *,
    lock: bool = False,
) -> dict[str, str]:
    """``path → entry id`` for every distinct live endpoint in the batch.

    A tombstoned row at an endpoint's path reads as absent: no verb
    lands an edge on it, and the one it has waits for the restore. With
    *lock* the resolve is also the liveness proof: the rows stay locked
    until the caller's transaction commits, so a rival delete cannot
    tombstone an endpoint inside the window — it serializes behind the
    commit.
    """
    entry = tables.entry
    paths = sorted({str(edge.source) for edge in edges} | {str(edge.target) for edge in edges})
    found: dict[str, str] = {}
    for chunk in chunked(paths, membership_budget):
        columns = [entry.c.path, entry.c.entry_id, entry.c.deleted_at]
        if lock:
            # Sorted paths order the locks; a deadlock against a rival's
            # claim order classifies retryable and rides the retry channel.
            stmt = locked_lookup(entry, entry.c.path, chunk, columns, profile)
        else:
            stmt = select(*columns).where(membership(entry.c.path, chunk, profile))
        result = await session.execute(stmt)
        found.update({row.path: row.entry_id for row in result if row.deleted_at is None})
    return found


def _missing_endpoints(edges: list[Edge], ids: dict[str, str]) -> list[Path]:
    """The distinct endpoints with no stored row, in first-use order."""
    missing: list[Path] = []
    for edge in edges:
        for endpoint in (edge.source, edge.target):
            if str(endpoint) not in ids and endpoint not in missing:
                missing.append(endpoint)
    return missing


def _wanted_triples(edges: list[Edge], ids: dict[str, str]) -> set[_Triple]:
    """The batch's stored identities, for the endpoints that resolved."""
    wanted: set[_Triple] = set()
    for edge in edges:
        source_id, target_id = ids.get(str(edge.source)), ids.get(str(edge.target))
        if source_id is not None and target_id is not None:
            wanted.add((source_id, target_id, edge.edge_type))
    return wanted


def _triple_of(values: dict[str, object]) -> _Triple:
    return (str(values["source_id"]), str(values["target_id"]), str(values["edge_type"]))


async def _existing_triples(
    session: AsyncSession,
    table: Table,
    profile: DialectProfile,
    membership_budget: int,
    wanted: set[_Triple],
) -> dict[_Triple, int]:
    """``triple → row id`` for the wanted identities that already have a row.

    Each chunk probes its own sources, targets, and types as three
    membership lists — the portable stand-in for a tuple-IN — so the
    fetch is bounded by the chunk's cross product against the store,
    never by a hub's whole out-edge set; the client-side filter keeps
    exactly the wanted triples. The ids key every touch and delete, so
    those plan on the primary key whatever the optimizer makes of the
    triple's indexes.
    """
    found: dict[_Triple, int] = {}
    for chunk in chunked(sorted(wanted), max(1, membership_budget // _PROBE_LISTS)):
        sources = sorted({source_id for source_id, _, _ in chunk})
        targets = sorted({target_id for _, target_id, _ in chunk})
        types = sorted({edge_type for _, _, edge_type in chunk})
        stmt = select(table.c.id, table.c.source_id, table.c.target_id, table.c.edge_type).where(
            membership(table.c.source_id, sources, profile),
            membership(table.c.target_id, targets, profile),
            membership(table.c.edge_type, types, profile),
        )
        result = await session.execute(stmt)
        found.update(
            {
                (row.source_id, row.target_id, row.edge_type): row.id
                for row in result
                if (row.source_id, row.target_id, row.edge_type) in wanted
            }
        )
    return found


async def insert_arbitrated(
    session: AsyncSession, table: Table, creates: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Insert fresh identities; the unique key arbitrates a racing duplicate.

    The bulk insert runs under a savepoint; on a violation it redrives
    row-by-row, each row under its own savepoint, and the conflicted
    rows come back to land as touches — one portable catch-retry shape
    for every profile (native upsert buys nothing after the probe).
    """
    if not creates:
        return []
    try:
        async with session.begin_nested():
            await bulk_insert(session, table, creates)
    except IntegrityError:
        pass
    else:
        return []
    conflicted: list[dict[str, object]] = []
    for row in creates:
        try:
            async with session.begin_nested():
                await session.execute(insert(table).values(**row))
        except IntegrityError:
            conflicted.append(row)
    return conflicted


async def _touch_rows(
    session: AsyncSession,
    table: Table,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    touches: list[tuple[int, dict[str, object]]],
) -> None:
    """Refresh the touched rows' payloads by id.

    Where the profile takes a ``VALUES`` table as an UPDATE join source
    the touch is one statement per chunk; elsewhere it is executemany
    by id, which the array-binding drivers page and the others run row
    by row. Learns nothing back: the probe already proved the rows.
    """
    rows = [_touch_row(row_id, touched) for row_id, touched in touches]
    if not profile.values_join:
        stmt = (
            update(table)
            .where(table.c.id == bindparam("b_id"))
            .values(weight=bindparam("b_weight"), distance=bindparam("b_distance"), provenance=bindparam("b_prov"))
        )
        await session.execute(stmt, [dict(zip(_TOUCH_BINDS, row, strict=True)) for row in rows])
        return
    per_statement = statement_budget(
        lambda probe: _touch_values_stmt(table, probe),
        rows[0],
        session.get_bind().dialect,
        parameter_budget=parameter_budget,
        row_width=len(rows[0]),
        row_cap=membership_budget,
    )
    for chunk in chunked(rows, per_statement):
        await session.execute(_touch_values_stmt(table, chunk))


def _touch_row(row_id: int, touched: dict[str, object]) -> tuple[object, ...]:
    return (row_id, touched["weight"], touched["distance"], touched["provenance"])


def _touch_values_stmt(table: Table, rows: Sequence[tuple[object, ...]]) -> Update:
    """One payload-refresh VALUES join over *rows* of ``(id, weight, distance, provenance)``.

    Each assignment casts to its column's type: a payload column that is
    NULL in every row renders as bare NULLs, which the engine would
    otherwise type as text.
    """
    incoming = values(
        column("v_id", table.c.id.type),
        column("v_weight", table.c.weight.type),
        column("v_distance", table.c.distance.type),
        column("v_prov", table.c.provenance.type),
        name="incoming",
    ).data(list(rows))
    assignments = {
        name: cast(incoming.c[f"v_{alias}"], table.c[name].type)
        for name, alias in (("weight", "weight"), ("distance", "distance"), ("provenance", "prov"))
    }
    return update(table).where(table.c.id == incoming.c.v_id).values(**assignments)


def _observe_edge(edge: Edge, *, status: Literal["created", "updated", "deleted"]) -> Observation:
    return Observation(
        path=edge.source,
        edge_target=edge.target,
        edge_type=edge.edge_type,
        edge_weight=edge.weight,
        edge_distance=edge.distance,
        status=status,
    )


def _drift_warning(delta: FsDelta) -> ResultError:
    detail = (
        f"reindex repaired the fs mirror for entry {delta.entry_id}: "
        f"{len(delta.wrong_row_ids)} wrong row(s), {'1' if delta.missing else '0'} missing"
    )
    return classified(
        ErrorKind.internal,
        detail=detail,
        severity=Severity.warning,
        data={"entry_id": delta.entry_id, "wrong": len(delta.wrong_row_ids), "missing": delta.missing},
    )


def _dangling_warning(count: int) -> ResultError:
    detail = f"reindex reclaimed {count} edge row(s) naming an endpoint with no entry row"
    return classified(
        ErrorKind.internal,
        detail=detail,
        severity=Severity.warning,
        data={"dangling": count},
    )
