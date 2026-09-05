"""Edge-row maintenance for ``DatabaseStorage`` — the fs mirror, the
authored-edge cascade, and reindex re-convergence.

One reserved-type ``"fs"`` edge row per non-root entry, ``(parent →
entry)``, minted and maintained inside the same transactions that mutate
the namespace: creates insert beside their segment postings, a move (and
delete's reparent into trash, which rides the same shape) repoints the
one moved root's row by id, a copy mints rows for its fresh ids, and the
purge arm already deletes every edge touching a destroyed id. The mirror
follows ``parent_id`` everywhere — trash included — so the invariant is
uniform: every entry with a parent has exactly one fs in-edge naming it.
``parent_id`` is authoritative; on any disagreement the fs rows are
wrong.

Authored edges (every non-``fs`` row) die in exactly two ways: ``rmedge``
removes them by triple, or an endpoint entry is deleted — soft delete
included. Delete's cascade removes the trashed subtree's authored rows
in both directions; restore brings entries back with authored edges
gone, by design. ``mkedge`` resolves its endpoints under row locks, so
a rival delete serializes behind the insert and no verb ever lands an
edge on a trashed entry; a stray minted at the row layer is reclaimed
by reindex, loudly.

The reindex verb re-converges the fs rows to ``parent_id`` — the
segment-postings discipline: :func:`collect_edge_drift` diffs from a
plain read, :func:`repair_edge_drift` applies each entry's delta only
while the row still holds the parent the delta was computed from (the
row is locked for the check), and every applied repair surfaces as a
warning — drift means a namespace verb failed its maintenance, and that
bug must surface. Edge rows naming an endpoint with no entry row at all
are reclaimed the same pass, as are authored rows touching a trashed
entry — each guarded so a racing restore wins. The collect pass holds the corpus's ids in
memory — the same whole-corpus profile as the segment pass, acknowledged
rather than capped; streamed merge passes are the future direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sqlalchemy import bindparam, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from vfs.models import Observation
from vfs.models.edge import RESERVED_EDGE_TYPE
from vfs.paths import TRASH_ROOT
from vfs.results import Result, ResultError, Severity, VFSErrorKind, classified
from vfs.storage.backends.database.dialects import bulk_insert, chunked
from vfs.storage.backends.database.membership import locked_lookup, membership
from vfs.storage.backends.database.seams import seam

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import Edge
    from vfs.models.rows import VFSTables
    from vfs.paths import Path
    from vfs.storage.backends.database.dialects import DialectProfile

# One edge's stored identity: resolved endpoint ids plus the type segment.
_Triple = tuple[str, str, str]

# Rows the collect pass streams per fetch — bounds driver buffering, not memory.
_SCAN_YIELD_ROWS = 1024

# A stored path inside the trash scope — the liveness fact the reclaim reads.
_TRASH_PREFIX = f"{TRASH_ROOT}/"


# ---------------------------------------------------------------------------
# Write-path maintenance — the fs mirror and the authored-edge cascade
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


async def delete_authored_edges(
    session: AsyncSession, edges: Table, profile: DialectProfile, membership_budget: int, ids: Iterable[str]
) -> None:
    """Remove every authored (non-fs) edge touching *ids*, both directions.

    Delete's cascade: a trashed entry keeps its fs mirror row (it still
    has a parent — the bucket) and loses every authored edge. Two
    single-list deletes per chunk, like the purge arm — one OR'd
    statement would carry the chunk's binds twice.
    """
    for chunk in chunked(sorted(set(ids)), membership_budget):
        await session.execute(
            delete(edges).where(membership(edges.c.source_id, chunk, profile), edges.c.edge_type != RESERVED_EDGE_TYPE)
        )
        await session.execute(
            delete(edges).where(membership(edges.c.target_id, chunk, profile), edges.c.edge_type != RESERVED_EDGE_TYPE)
        )


# ---------------------------------------------------------------------------
# The caller pair — mkedge touch/upsert, rmedge removal by triple
# ---------------------------------------------------------------------------


async def mkedge_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    *,
    edges: list[Edge],
    provenance: str,
    user_id: str | None,
) -> Result:
    """Adjudicate and apply a batch of edge touches as a set.

    Endpoints resolve by path under row locks — the resolve is the
    liveness proof: a rival delete serializes behind this commit, and
    its cascade then sweeps whatever landed here. A missing endpoint
    classifies ``not_found`` and fails the batch whole — the write
    family's doctrine, and no statement runs. Existing identities are
    probed the same way, so every row's status (``created`` or
    ``updated``, the touch refreshing ``weight``/``distance``/
    ``provenance``) is known without RETURNING; a duplicate racing in
    from a row-layer writer (verb batches serialize on the endpoint
    locks) surfaces as a unique violation on the insert, redrives
    row-by-row under savepoints, and lands as the touch it raced.
    *user_id* is not yet used; edges carry no ownership today.
    """
    table = tables.edges
    ids = await _endpoint_ids(session, tables, profile, membership_budget, edges, lock=True)
    errors = [
        classified(VFSErrorKind.not_found, f"Not found: {endpoint}", endpoint)
        for endpoint in _missing_endpoints(edges, ids)
    ]
    if errors:
        return Result(ops=("mkedge",), errors=errors)
    existing = await _existing_triples(session, table, profile, membership_budget, edges, ids)
    creates: list[dict[str, object]] = []
    touches: list[dict[str, object]] = []
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
        if triple in existing:
            status[triple] = "updated"
            touches.append(values)
        else:
            status[triple] = "created"
            creates.append(values)
    await seam("mkedge:before-insert")
    conflicted = await _insert_arbitrated(session, table, creates)
    for values in conflicted:
        status[(str(values["source_id"]), str(values["target_id"]), str(values["edge_type"]))] = "updated"
        touches.append(values)
    if touches:
        stmt = (
            update(table)
            .where(
                table.c.source_id == bindparam("b_source"),
                table.c.target_id == bindparam("b_target"),
                table.c.edge_type == bindparam("b_type"),
            )
            .values(weight=bindparam("b_weight"), distance=bindparam("b_distance"), provenance=bindparam("b_prov"))
        )
        await session.execute(stmt, [_touch_params(values) for values in touches])
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
    user_id: str | None,
) -> Result:
    """Remove edges by exact triple; what is absent is a per-row warning.

    A missing endpoint or identity is a warning-severity ``not_found``
    record, never a batch error — removing what is already gone leaves
    the same end state, so the batch commits what it found. Statuses
    come from the probe that bounds the delete; a rival removing the
    same triple inside the window yields the identical end state.
    *user_id* is not yet used.
    """
    table = tables.edges
    ids = await _endpoint_ids(session, tables, profile, membership_budget, edges)
    existing = await _existing_triples(session, table, profile, membership_budget, edges, ids)
    rows: list[Observation] = []
    warnings: list[ResultError] = []
    doomed: list[dict[str, str]] = []
    for edge in edges:
        source_id, target_id = ids.get(str(edge.source)), ids.get(str(edge.target))
        if source_id is None or target_id is None or (source_id, target_id, edge.edge_type) not in existing:
            message = f"No edge: {edge.source} -> {edge.target} ({edge.edge_type})"
            warnings.append(
                ResultError(kind=VFSErrorKind.not_found, message=message, path=edge.source, severity=Severity.warning)
            )
            continue
        doomed.append({"b_source": source_id, "b_target": target_id, "b_type": edge.edge_type})
        rows.append(_observe_edge(edge, status="deleted"))
    if doomed:
        stmt = delete(table).where(
            table.c.source_id == bindparam("b_source"),
            table.c.target_id == bindparam("b_target"),
            table.c.edge_type == bindparam("b_type"),
        )
        await session.execute(stmt, doomed)
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
    """Carry-over between the reindex edge phases' separate transactions.

    ``strays`` maps an authored edge row's id to the trashed endpoint
    ids it was recorded against — the repair pass's guard facts.
    """

    deltas: list[FsDelta] = field(default_factory=list)
    dangling: list[int] = field(default_factory=list)
    strays: dict[int, set[str]] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.deltas and not self.dangling and not self.strays


async def collect_edge_drift(session: AsyncSession, tables: VFSTables, state: EdgeRebuildState) -> Result:
    """Diff the fs rows against ``parent_id`` and find dangling endpoints.

    A plain read — no writer is blocked. Each drifted entry's delta is
    recorded with the parent it was computed from, which becomes the
    repair pass's guard; edge rows of any type naming an endpoint with
    no entry row are recorded as dangling (their guard is that absence,
    permanent — an entry id never returns); authored rows touching a
    trashed entry are recorded as strays with the trashed ids as their
    guard — the endpoint locks make a stray a mint-site bug.
    """
    entry, edges = tables.entry, tables.edges
    parents: dict[str, str | None] = {}
    trashed: set[str] = set()
    entry_scan = select(entry.c.entry_id, entry.c.parent_id, entry.c.path).execution_options(yield_per=_SCAN_YIELD_ROWS)
    async for row in await session.stream(entry_scan):
        parents[row.entry_id] = row.parent_id
        if _in_trash(row.path):
            trashed.add(row.entry_id)
    held: dict[str, list[tuple[int, str]]] = {}
    edge_scan = select(edges.c.id, edges.c.source_id, edges.c.target_id, edges.c.edge_type).execution_options(
        yield_per=_SCAN_YIELD_ROWS
    )
    async for row in await session.stream(edge_scan):
        if row.source_id not in parents or row.target_id not in parents:
            state.dangling.append(row.id)
        elif row.edge_type == RESERVED_EDGE_TYPE:
            held.setdefault(row.target_id, []).append((row.id, row.source_id))
        elif row.source_id in trashed or row.target_id in trashed:
            state.strays[row.id] = {eid for eid in (row.source_id, row.target_id) if eid in trashed}
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
    row is gone — is skipped, and a stray whose recorded endpoints were
    all restored is skipped too: the rival's synchronous maintenance is
    the truth. Every applied repair surfaces as a warning: drift is a
    maintenance bug being surfaced, never silently absorbed.
    """
    entry, edges = tables.entry, tables.edges
    current: dict[str, tuple[str | None, str]] = {}
    guarded = {delta.entry_id for delta in state.deltas} | {eid for ids in state.strays.values() for eid in ids}
    for chunk in chunked(sorted(guarded), membership_budget):
        guard = locked_lookup(
            entry, entry.c.entry_id, chunk, [entry.c.entry_id, entry.c.parent_id, entry.c.path], profile
        )
        current.update({row.entry_id: (row.parent_id, row.path) for row in await session.execute(guard)})
    confirmed = [
        delta for delta in state.deltas if delta.entry_id in current and current[delta.entry_id][0] == delta.parent_id
    ]
    # A recorded endpoint that vanished entirely reads as still-dead: the
    # purge that removed it removed the edge row too, and the id never returns.
    strays = [
        row_id
        for row_id, endpoints in state.strays.items()
        if any(eid not in current or _in_trash(current[eid][1]) for eid in endpoints)
    ]
    doomed = [row_id for delta in confirmed for row_id in delta.wrong_row_ids] + state.dangling + strays
    for chunk in chunked(doomed, membership_budget):
        await session.execute(delete(edges).where(membership(edges.c.id, chunk, profile)))
    additions = [fs_row(delta.parent_id, delta.entry_id) for delta in confirmed if delta.missing and delta.parent_id]
    if additions:
        await bulk_insert(session, edges, additions)
    warnings = [_drift_warning(delta) for delta in confirmed]
    if state.dangling:
        warnings.append(_dangling_warning(len(state.dangling)))
    if strays:
        warnings.append(_stray_warning(len(strays)))
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
    """``path → entry id`` for every distinct endpoint in the batch.

    Trashed rows are unaddressable through here by construction: their
    paths are rewritten under the reserved trash scope, which the
    ``Edge`` model already refuses as an endpoint. With *lock* the
    resolve is also the liveness proof: the rows stay locked until the
    caller's transaction commits, so a rival delete cannot trash an
    endpoint inside the window — it serializes behind the commit, and
    its cascade then sweeps whatever landed here.
    """
    entry = tables.entry
    paths = sorted({str(edge.source) for edge in edges} | {str(edge.target) for edge in edges})
    found: dict[str, str] = {}
    for chunk in chunked(paths, membership_budget):
        columns = [entry.c.path, entry.c.entry_id]
        if lock:
            # Sorted paths order the locks; a deadlock against a rival's
            # claim order classifies retryable and rides the retry channel.
            stmt = locked_lookup(entry, entry.c.path, chunk, columns, profile)
        else:
            stmt = select(*columns).where(membership(entry.c.path, chunk, profile))
        result = await session.execute(stmt)
        found.update({row.path: row.entry_id for row in result})
    return found


def _missing_endpoints(edges: list[Edge], ids: dict[str, str]) -> list[Path]:
    """The distinct endpoints with no stored row, in first-use order."""
    missing: list[Path] = []
    for edge in edges:
        for endpoint in (edge.source, edge.target):
            if str(endpoint) not in ids and endpoint not in missing:
                missing.append(endpoint)
    return missing


async def _existing_triples(
    session: AsyncSession,
    table: Table,
    profile: DialectProfile,
    membership_budget: int,
    edges: list[Edge],
    ids: dict[str, str],
) -> set[_Triple]:
    """The batch's identities that already have a row.

    Probed by ``source_id IN`` chunks and filtered to the batch's own
    triples client-side — a tuple-IN predicate varies by dialect. The
    filter result is bounded by the batch, but the fetch is bounded by
    the probed sources' out-degree: a high-degree hub makes a small
    batch read the hub's whole out-edge set. A tighter predicate
    (``edge_type``, or tuple-IN where the dialect has one) is the
    future direction, never a cap.
    """
    wanted: set[_Triple] = set()
    for edge in edges:
        source_id, target_id = ids.get(str(edge.source)), ids.get(str(edge.target))
        if source_id is not None and target_id is not None:
            wanted.add((source_id, target_id, edge.edge_type))
    found: set[_Triple] = set()
    for chunk in chunked(sorted({source_id for source_id, _, _ in wanted}), membership_budget):
        result = await session.execute(
            select(table.c.source_id, table.c.target_id, table.c.edge_type).where(
                membership(table.c.source_id, chunk, profile)
            )
        )
        found.update(
            (row.source_id, row.target_id, row.edge_type)
            for row in result
            if (row.source_id, row.target_id, row.edge_type) in wanted
        )
    return found


async def _insert_arbitrated(
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


def _touch_params(values: dict[str, object]) -> dict[str, object]:
    return {
        "b_source": values["source_id"],
        "b_target": values["target_id"],
        "b_type": values["edge_type"],
        "b_weight": values["weight"],
        "b_distance": values["distance"],
        "b_prov": values["provenance"],
    }


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
    message = (
        f"Reindex repaired the fs mirror for entry {delta.entry_id}: "
        f"{len(delta.wrong_row_ids)} wrong row(s), {'1' if delta.missing else '0'} missing"
    )
    return ResultError(
        kind=VFSErrorKind.internal,
        message=message,
        severity=Severity.warning,
        data={"entry_id": delta.entry_id, "wrong": len(delta.wrong_row_ids), "missing": delta.missing},
    )


def _dangling_warning(count: int) -> ResultError:
    message = f"Reindex reclaimed {count} edge row(s) naming an endpoint with no entry row"
    return ResultError(
        kind=VFSErrorKind.internal,
        message=message,
        severity=Severity.warning,
        data={"dangling": count},
    )


def _stray_warning(count: int) -> ResultError:
    message = f"Reindex reclaimed {count} authored edge row(s) touching trashed entries"
    return ResultError(
        kind=VFSErrorKind.internal,
        message=message,
        severity=Severity.warning,
        data={"strays": count},
    )


def _in_trash(path: str) -> bool:
    return path == TRASH_ROOT or path.startswith(_TRASH_PREFIX)
