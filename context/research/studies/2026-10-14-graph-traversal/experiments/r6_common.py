"""Shared helpers for the R6 executed experiments. Never imported by vfs.

Seams borrowed from the live tree (read-only use):
  - DatabaseStorage(url=..., posture=...)      src/vfs/storage/backends/database/backend.py:177-218
  - storage._host.tables / .session_factory()  tests/storage/database/test_edges.py:56-60
  - storage._host.engine.sync_engine (events)  tests/storage/database/test_edges.py:335-337
  - storage._host.profile / .parameter_budget  src/vfs/storage/backends/database/engine.py:204-223
  - liveness_filters(entry, profile, ...)      src/vfs/storage/backends/database/descent.py:223-234
"""

from __future__ import annotations

import asyncio
import collections
import json
import math
import pathlib
import random
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from sqlalchemy import Integer, event, func, literal, select, union_all
from sqlalchemy.sql import ColumnElement, FromClause

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.descent import liveness_filters
from vfs.storage.backends.database.ranges import _RangeJoin

HERE = pathlib.Path(__file__).resolve().parent
DB = HERE / "r6_graph.sqlite"
DB_10K = HERE / "r6_graph_10k.sqlite"
DB_CYCLE = HERE / "r6_cycle.sqlite"
META = HERE / "r6_graph_meta.json"

AUTHORED = ("imports", "references", "calls")
SYSTEM = Authority.system()
ANN = Authority.of(Principal("ann"))

Direction = str  # "out" | "in" | "both"


def url_for(path: pathlib.Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


async def open_storage(path: pathlib.Path, posture: str = "private") -> DatabaseStorage:
    storage = DatabaseStorage(url=url_for(path), posture=posture)  # type: ignore[arg-type]
    touched = await storage.first_touch()
    assert touched.success, touched
    return storage


class StatementCounter:
    """Counts cursor executions on the storage's own engine (the test suite's own pattern)."""

    def __init__(self, storage: DatabaseStorage) -> None:
        self.statements: list[str] = []
        self._engine = storage._host.engine.sync_engine

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            self.statements.append(statement)

        self._record = record
        event.listen(self._engine, "before_cursor_execute", record)

    @property
    def count(self) -> int:
        """Query statements only: the session's own BEGIN/COMMIT/ROLLBACK are not counted."""
        return len([s for s in self.statements if s.strip().split(" ", 1)[0].upper() not in ("BEGIN", "COMMIT", "ROLLBACK")])

    def clear(self) -> None:
        self.statements.clear()

    def detach(self) -> None:
        event.remove(self._engine, "before_cursor_execute", self._record)


async def rows(storage: DatabaseStorage, stmt: Any) -> list[Any]:
    async with storage._host.session_factory() as session:
        return list((await session.execute(stmt)).all())


async def scalar(storage: DatabaseStorage, stmt: Any) -> Any:
    async with storage._host.session_factory() as session:
        return (await session.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# Graph material read back from the database
# ---------------------------------------------------------------------------


async def live_entries(storage: DatabaseStorage) -> dict[str, dict[str, Any]]:
    """entry_id -> {path, kind} over live, non-meta rows (the same liveness term the readers carry)."""
    tables, profile = storage._host.tables, storage._host.profile
    entry = tables.entry
    stmt = select(entry.c.entry_id, entry.c.path, entry.c.kind).where(
        *liveness_filters(entry, profile, include_meta=False)
    )
    return {r.entry_id: {"path": r.path, "kind": r.kind} for r in await rows(storage, stmt)}


async def edge_list(storage: DatabaseStorage, edge_types: Sequence[str] | None = None) -> list[tuple[str, str, str]]:
    """(source_id, target_id, edge_type) for every edge whose both endpoints are live."""
    tables, profile = storage._host.tables, storage._host.profile
    entry, edges = tables.entry, tables.edges
    src = entry.alias("src")
    tgt = entry.alias("tgt")
    stmt = (
        select(edges.c.source_id, edges.c.target_id, edges.c.edge_type)
        .select_from(
            edges.join(src, src.c.entry_id == edges.c.source_id).join(tgt, tgt.c.entry_id == edges.c.target_id)
        )
        .where(*liveness_filters(src, profile, include_meta=False), *liveness_filters(tgt, profile, include_meta=False))
    )
    if edge_types is not None:
        stmt = stmt.where(edges.c.edge_type.in_(list(edge_types)))
    return [(r.source_id, r.target_id, r.edge_type) for r in await rows(storage, stmt)]


def adjacency_dict(edges: Iterable[tuple[str, str, str]], direction: Direction) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = collections.defaultdict(set)
    for s, t, _ in edges:
        if direction in ("out", "both"):
            adj[s].add(t)
        if direction in ("in", "both"):
            adj[t].add(s)
    return adj


def bfs(adj: dict[str, set[str]], seeds: Iterable[str], max_depth: int) -> dict[str, int]:
    """Pure-Python BFS: node -> min depth, seeds at 0, bounded at max_depth."""
    dist = {s: 0 for s in seeds}
    frontier = list(dist)
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        nxt = []
        for u in frontier:
            for v in adj.get(u, ()):
                if v not in dist:
                    dist[v] = depth
                    nxt.append(v)
        frontier = nxt
    return dist


# ---------------------------------------------------------------------------
# The recursive-CTE walk, built with SQLAlchemy Core on the backend's own tables
# ---------------------------------------------------------------------------


def adjacency(tables: Any, direction: Direction, edge_types: Sequence[str] | None) -> FromClause:
    """A derived table (frm, to, edge_type) in the requested direction. `both` is a UNION ALL of the two."""
    edges = tables.edges
    base = select(edges.c.source_id.label("frm"), edges.c.target_id.label("to"), edges.c.edge_type.label("edge_type"))
    flipped = select(edges.c.target_id.label("frm"), edges.c.source_id.label("to"), edges.c.edge_type.label("edge_type"))
    if edge_types is not None:
        base = base.where(edges.c.edge_type.in_(list(edge_types)))
        flipped = flipped.where(edges.c.edge_type.in_(list(edge_types)))
    if direction == "out":
        return base.subquery("adj")
    if direction == "in":
        return flipped.subquery("adj")
    if direction == "both":
        return union_all(base, flipped).subquery("adj")
    raise ValueError(direction)


def walk_cte(
    tables: Any,
    profile: Any,
    seeds: Sequence[str] | None,
    direction: Direction,
    max_depth: int,
    *,
    edge_types: Sequence[str] | None = None,
    dedup: bool = True,
    far_join: FromClause | None = None,
    far_terms: Callable[[Any], list[ColumnElement[bool]]] | None = None,
    anchor_rows: FromClause | None = None,
    name: str = "walk",
):
    """One recursive CTE: anchor = live seeds at depth 0; member = one hop in *direction* with the liveness term.

    *far_join* (a derived table of visible entry_id) and/or *far_terms* (literal predicate on the far entry
    alias) are the rights predicate riding every hop AND the anchor. *anchor_rows* replaces the IN-list anchor
    with a derived table whose one column is ``node`` (the temp-table experiment).
    """
    entry = tables.entry
    seed = entry.alias("seed")
    anchor = select(seed.c.entry_id.label("node"), literal(0, Integer).label("depth")).where(
        *liveness_filters(seed, profile, include_meta=False)
    )
    if anchor_rows is not None:
        anchor = anchor.select_from(seed.join(anchor_rows, anchor_rows.c.node == seed.c.entry_id))
    else:
        assert seeds is not None
        anchor = anchor.where(seed.c.entry_id.in_(list(seeds)))
    if far_join is not None:
        anchor = anchor.where(seed.c.entry_id.in_(select(far_join.c.entry_id)))
    if far_terms is not None:
        anchor = anchor.where(*far_terms(seed))

    walk = anchor.cte(name, recursive=True)
    w = walk.alias("w")
    adj = adjacency(tables, direction, edge_types)
    far = entry.alias("far")
    joined = w.join(adj, adj.c.frm == w.c.node).join(far, far.c.entry_id == adj.c.to)
    if far_join is not None:
        joined = joined.join(far_join, far_join.c.entry_id == far.c.entry_id)
    member = (
        select(adj.c.to.label("node"), (w.c.depth + 1).label("depth"))
        .select_from(joined)
        .where(w.c.depth < max_depth, *liveness_filters(far, profile, include_meta=False))
    )
    if far_terms is not None:
        member = member.where(*far_terms(far))
    return walk.union(member) if dedup else walk.union_all(member)


def min_depth_select(walk: Any):
    return select(walk.c.node, func.min(walk.c.depth).label("depth")).group_by(walk.c.node)


def count_select(walk: Any):
    return select(func.count()).select_from(walk)


def per_depth_select(walk: Any):
    return select(walk.c.depth, func.count()).group_by(walk.c.depth).order_by(walk.c.depth)


async def min_depths(storage: DatabaseStorage, walk: Any) -> dict[str, int]:
    return {r.node: r.depth for r in await rows(storage, min_depth_select(walk))}


def literal_sql(stmt: Any, dialect: Any) -> str:
    """Rendered SQL with the binds substituted (positional dialects only; values are str/int)."""
    compiled = stmt.compile(dialect=dialect, compile_kwargs={"render_postcompile": True})
    text = str(compiled)
    if compiled.positiontup is None:
        return text
    out = []
    names = iter(compiled.positiontup)
    for ch in text:
        if ch == "?":
            value = compiled.params[next(names)]
            out.append(str(value) if isinstance(value, (int, float)) else "'" + str(value).replace("'", "''") + "'")
        else:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# The app-side frontier loop (one non-recursive statement per hop per chunk)
# ---------------------------------------------------------------------------


async def frontier_walk(
    storage: DatabaseStorage,
    seeds: Sequence[str],
    direction: Direction,
    max_depth: int,
    budget: int,
    *,
    edge_types: Sequence[str] | None = None,
    far_join: FromClause | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    """node -> min depth, plus work counters: statements, rows_returned, hops."""
    tables, profile = storage._host.tables, storage._host.profile
    entry = tables.entry
    adj = adjacency(tables, direction, edge_types)
    far = entry.alias("far")
    dist = {s: 0 for s in seeds}
    frontier = list(dist)
    work = {"statements": 0, "rows_returned": 0, "hops": 0}
    async with storage._host.session_factory() as session:
        for depth in range(1, max_depth + 1):
            if not frontier:
                break
            work["hops"] += 1
            nxt: list[str] = []
            for i in range(0, len(frontier), budget):
                chunk = frontier[i : i + budget]
                # The profile's range-join keyword (CROSS JOIN on SQLite): without it the stat-less planner
                # drives from ix_vfs_entries_deleted_at and probes the edge index once per (entry x seed).
                joined = _RangeJoin(adj, far, far.c.entry_id == adj.c.to, profile.range_join)
                if far_join is not None:
                    joined = joined.join(far_join, far_join.c.entry_id == far.c.entry_id)
                stmt = (
                    select(adj.c.to)
                    .select_from(joined)
                    .where(adj.c.frm.in_(chunk), *liveness_filters(far, profile, include_meta=False))
                    .distinct()
                )
                found = (await session.execute(stmt)).scalars().all()
                work["statements"] += 1
                work["rows_returned"] += len(found)
                for v in found:
                    if v not in dist:
                        dist[v] = depth
                        nxt.append(v)
            frontier = nxt
    return dist, work


def chunks_for(n: int, budget: int) -> int:
    return math.ceil(n / budget)


def timed(label: str):
    class _T:
        def __enter__(self):
            self.t0 = time.perf_counter()
            return self

        def __exit__(self, *a):
            self.seconds = time.perf_counter() - self.t0
            print(f"    [wall-clock side note] {label}: {self.seconds:.2f}s")

    return _T()


def run(main: Callable[[], Any]) -> None:
    asyncio.run(main())


__all__ = [
    "ANN",
    "AUTHORED",
    "DB",
    "DB_10K",
    "DB_CYCLE",
    "META",
    "SYSTEM",
    "Edge",
    "Entry",
    "Path",
    "StatementCounter",
    "adjacency",
    "adjacency_dict",
    "bfs",
    "chunks_for",
    "count_select",
    "edge_list",
    "frontier_walk",
    "json",
    "literal_sql",
    "live_entries",
    "min_depth_select",
    "min_depths",
    "open_storage",
    "per_depth_select",
    "random",
    "rows",
    "run",
    "scalar",
    "timed",
    "walk_cte",
]
