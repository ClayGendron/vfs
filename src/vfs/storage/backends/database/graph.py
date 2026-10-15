"""The graph walk — a frontier walk over ``vfs_edges``, one chunked statement per hop, every row judged.

The application holds the frontier, the visited set and the stop
condition; each hop is one statement per chunk of the frontier that
selects the frontier's edges in the walk's direction from ``vfs_edges``,
joined to the entries table on the far endpoint in the dialect's pinned
join, carrying the liveness term and the type filter, narrowed by the
caller's view at the rung a walk passes a node on (``list``) and judged
row by row before the far node joins the frontier. A node the caller may
read comes back whole; one it may only name comes back bare, and an
edge touching it carries its type and no measure. Under a partial named
view each frontier chunk also issues one un-narrowed probe for the
directories the narrowing cannot return, so a directory on the road to
a nameable row is passed as the listing verbs show it — one statement
per chunk, the price of that rule.

``inbound``, ``outbound`` and ``neighborhood`` are the same loop in
different directions. ``meet`` is the multi-source form: every node is
owned by the seed that reached it first (ties by seed input order), an
edge between differently owned nodes is a meeting, union-find joins the
components as meetings are accepted, and the walk stops when every seed
shares one component; the kept set is the bridge paths traced back to
their seeds, stripped of undirected leaves and, with ``minimal``, of
every non-articulation node.

Round trips grow with the depth reached: a walk of depth *d* issues the
seed fetch, at most *d* hops of one statement per frontier chunk (two
for either-direction walks, one more per chunk for the road probe under
a partial named view, one per clause on the generic floor), and one
induced-edge fetch over the returned nodes the walk never expanded. The
recursive statement that would fold the hops into one is exponential on
the engines that refuse ``UNION`` in a recursive member and cannot stop
early; it is the recorded acceleration for the others, not the shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

from sqlalchemy import select

from vfs.models import Observation
from vfs.models.edge import RESERVED_EDGE_TYPE
from vfs.paths import Path, is_meta_path
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.descent import liveness_filters, rows_by_path
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.ranges import pinned_join
from vfs.storage.backends.database.reads import BODY_FIELDS, LIST_FIELDS
from vfs.storage.backends.database.rights import RIGHTS_FIELDS

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy import Column
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement, Select

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.rights import Visibility

# ---------------------------------------------------------------------------
# Module constants and shared types
# ---------------------------------------------------------------------------

Direction = Literal["outbound", "inbound"]

# The directions each method follows: the arrow, the arrow reversed, or both.
DIRECTIONS: Final[dict[str, tuple[Direction, ...]]] = {
    "outbound": ("outbound",),
    "inbound": ("inbound",),
    "neighborhood": ("outbound", "inbound"),
    "meet": ("outbound", "inbound"),
}

# What a bare node carries: the ``list`` projection plus the walk's own field.
BARE_FIELDS: Final[frozenset[str]] = LIST_FIELDS | {"depth"}

GRAPH_OPS: Final = ("graph",)


class Site(NamedTuple):
    """The mount facts a walk reads: its tables, its dialect, its membership budget."""

    tables: VFSTables
    profile: DialectProfile
    membership_budget: int


class GraphRequest(NamedTuple):
    """One call's parameters, gated and normalized by the backend."""

    method: str
    depth: int | None
    edge_types: tuple[str, ...]
    edge_types_not: tuple[str, ...]
    minimal: bool
    limit: int | None
    fetched: frozenset[str]

    @property
    def directions(self) -> tuple[Direction, ...]:
        return DIRECTIONS[self.method]


class EdgeRow(NamedTuple):
    """One stored edge as the walk saw it."""

    source_id: str
    target_id: str
    edge_type: str
    weight: float | None
    distance: float | None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_id, self.target_id, self.edge_type)


class Node(NamedTuple):
    """One reached node: its identity, its depth from the nearest seed, and whether the caller reads it whole."""

    entry_id: str
    path: str
    kind: str
    depth: int
    whole: bool
    mapping: RowMapping | None


class HopRow(NamedTuple):
    """One row a hop returned: the frontier node it left, the node it reached, the edge between them."""

    near_id: str
    far: Node
    edge: EdgeRow


@dataclass
class Walk:
    """The state a walk accumulates: the nodes reached, every edge seen, the nodes whose hop ran."""

    nodes: dict[str, Node]
    expanded: set[str] = field(default_factory=set)
    edges: dict[tuple[str, str, str], EdgeRow] = field(default_factory=dict)
    depth_reached: int = 0
    more: bool = False
    bridges: list[EdgeRow] = field(default_factory=list)
    parent: dict[str, tuple[str, EdgeRow]] = field(default_factory=dict)
    components: int = 1
    radius_spent: bool = False

    def see(self, edge: EdgeRow) -> None:
        self.edges.setdefault(edge.key, edge)


# ---------------------------------------------------------------------------
# The verb
# ---------------------------------------------------------------------------


async def graph_rows(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    seeds: Sequence[Path],
    view: Visibility | None,
) -> Result:
    """The ``graph`` answer for *seeds* under *view*: node rows nearest first, then every edge among them."""
    invalid = [
        classified(ErrorKind.invalid, seed, detail="graph seeds must be live paths outside /.vfs")
        for seed in seeds
        if is_meta_path(seed)
    ]
    if invalid:
        return Result(ops=GRAPH_OPS, errors=invalid)
    roots = await resolve_seeds(session, site, request, seeds, view)
    if not roots:
        return Result(ops=GRAPH_OPS)
    if request.method == "meet":
        walk = await meet_walk(session, site, request, roots, view)
        kept = prune(walk, roots, minimal=request.minimal)
        walk.edges = {
            key: edge for key, edge in walk.edges.items() if edge.source_id in kept and edge.target_id in kept
        }
        walk.nodes = {entry_id: node for entry_id, node in walk.nodes.items() if entry_id in kept}
    else:
        walk = await frontier_walk(session, site, request, roots, view)
    return await observe(session, site, request, walk, roots)


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


async def resolve_seeds(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    seeds: Sequence[Path],
    view: Visibility | None,
) -> list[Node]:
    """The seeds that resolve to live rows the caller may name, at depth 0, in input order.

    A hidden directory is offered to the view's road, as ``read`` and
    ``tree`` offer theirs; one on the road is a bare node. Unknown,
    tombstoned and hidden seeds yield nothing and are indistinguishable.
    """
    entry = site.tables.entry
    fields = sorted((request.fetched - BODY_FIELDS) | RIGHTS_FIELDS | {"deleted_at"})
    columns: list[ColumnElement[object]] = [entry.c.entry_id, *(entry.c[name] for name in fields)]
    wanted = list(dict.fromkeys(str(seed) for seed in seeds))
    found = await rows_by_path(session, entry, wanted, columns, site.profile, site.membership_budget)
    resolved: dict[str, Node] = {}
    doors: list[RowMapping] = []
    for path in wanted:
        mapping = found.get(path)
        if mapping is None or mapping["deleted_at"] is not None:
            continue
        if view is None or view.holds(mapping, "list"):
            resolved[path] = _node_of(mapping, view, 0)
        elif mapping["kind"] == "directory" and view.derives_road:
            doors.append(mapping)
    if doors and view is not None:
        road = await view.road(session, [mapping["path"] for mapping in doors])
        for mapping in doors:
            if mapping["path"] in road:
                resolved[mapping["path"]] = _bare_node(mapping, 0)
    return [resolved[path] for path in wanted if path in resolved]


# ---------------------------------------------------------------------------
# The hop
# ---------------------------------------------------------------------------


def frontier_budget(site: Site, request: GraphRequest) -> int:
    """Frontier ids per hop statement: the membership budget net of the type lists bound beside them."""
    return max(1, site.membership_budget - len(request.edge_types) - len(request.edge_types_not))


def type_filter(site: Site, request: GraphRequest) -> list[ColumnElement[bool]]:
    """The edge-type terms: the named types, else every authored type (never ``fs``), minus the excluded."""
    edge_type = site.tables.edges.c.edge_type
    terms: list[ColumnElement[bool]] = []
    if request.edge_types:
        terms.append(membership(edge_type, sorted(set(request.edge_types)), site.profile))
    else:
        terms.append(edge_type != RESERVED_EDGE_TYPE)
    if request.edge_types_not:
        terms.append(~membership(edge_type, sorted(set(request.edge_types_not)), site.profile))
    return terms


def hop_statement(
    site: Site,
    request: GraphRequest,
    direction: Direction,
    chunk: Sequence[str],
    columns: Iterable[ColumnElement[object]],
) -> Select[Any]:
    """The edges leaving one frontier *chunk* in *direction*, joined to their live far endpoint in the pinned join."""
    edges, entry = site.tables.edges, site.tables.entry
    near, far = _endpoints(site, direction)
    return (
        select(edges.c.source_id, edges.c.target_id, edges.c.edge_type, edges.c.weight, edges.c.distance, *columns)
        .select_from(pinned_join(edges, entry, entry.c.entry_id == far, site.profile))
        .where(
            membership(near, chunk, site.profile),
            *liveness_filters(entry, site.profile, include_meta=False),
            *type_filter(site, request),
        )
    )


async def hop(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    frontier: Sequence[str],
    view: Visibility | None,
) -> list[HopRow]:
    """Every selected edge leaving *frontier* whose far endpoint the caller may name, with that node.

    The statement is narrowed by the view (one statement, or one per
    clause, merged) and every row passes ``holds`` at ``list``. Under a
    partial named view the directories the narrowing cannot return are
    probed un-narrowed and offered to the road.
    """
    entry = site.tables.entry
    fields = sorted((request.fetched - BODY_FIELDS) | RIGHTS_FIELDS)
    columns: list[ColumnElement[object]] = [entry.c.entry_id, *(entry.c[name] for name in fields)]
    rows: list[HopRow] = []
    for direction in request.directions:
        for chunk in chunked(frontier, frontier_budget(site, request)):
            stmt = hop_statement(site, request, direction, chunk, columns)
            for statement in view.narrow(stmt) if view is not None else [stmt]:
                judged = (await session.execute(statement)).mappings()
                rows.extend(
                    _hop_row(mapping, direction, _node_of(mapping, view, 0))
                    for mapping in judged
                    if view is None or view.holds(mapping, "list")
                )
            if view is not None and view.derives_road:
                rows.extend(await _road_rows(session, site, request, direction, chunk, view))
    return rows


# ---------------------------------------------------------------------------
# The walks
# ---------------------------------------------------------------------------


async def frontier_walk(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    roots: Sequence[Node],
    view: Visibility | None,
) -> Walk:
    """The directed loop: one hop per level until the depth is spent, nothing new is reached, or ``limit`` is.

    A node's discovering edge is the first, by ``(far path, edge type,
    near path)``, that reached it at its depth. The early stop at ``limit``
    is exact: a hop adds only nodes one level deeper than every node found,
    and the cut order is ``(depth, path)``.
    """
    walk = Walk({root.entry_id: root for root in roots})
    frontier = [root.entry_id for root in roots]
    level = 0
    while frontier and (request.depth is None or level < request.depth):
        rows = await hop(session, site, request, frontier, view)
        walk.expanded.update(frontier)
        new: list[str] = []
        for row in sorted(rows, key=lambda r: (r.far.path, r.edge.edge_type, walk.nodes[r.near_id].path)):
            walk.see(row.edge)
            if row.far.entry_id not in walk.nodes:
                walk.nodes[row.far.entry_id] = row.far._replace(depth=level + 1)
                new.append(row.far.entry_id)
        frontier = new
        level += 1
        if new:
            walk.depth_reached = level
        if request.limit is not None and len(walk.nodes) >= request.limit:
            walk.more = bool(new) and (request.depth is None or level < request.depth)
            break
    return walk


async def meet_walk(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    roots: Sequence[Node],
    view: Visibility | None,
) -> Walk:
    """The multi-source undirected loop: owners, parents, meetings and bridges, stopping when the seeds join.

    Rows are claimed in ``(owner's seed index, edge type, near path, far
    path)`` order; meetings are accepted in ``(owners' indexes, source
    path, target path)`` order by union-find. When the radius is spent
    and the seeds are not yet joined, one boundary hop detects meetings
    without claiming, so seeds ``2·depth + 1`` edges apart still meet.
    """
    walk = Walk({root.entry_id: root for root in roots})
    owner = {root.entry_id: index for index, root in enumerate(roots)}
    parent: dict[str, tuple[str, EdgeRow]] = {}
    union = _UnionFind(len(roots))
    frontier = [root.entry_id for root in roots]
    level = 0
    while frontier and union.components > 1:
        boundary = request.depth is not None and level >= request.depth
        rows = await hop(session, site, request, frontier, view)
        walk.expanded.update(frontier)
        new: list[str] = []
        claims = sorted(
            rows, key=lambda r: (owner[r.near_id], r.edge.edge_type, walk.nodes[r.near_id].path, r.far.path)
        )
        for row in claims:
            walk.see(row.edge)
            if row.far.entry_id in owner:
                continue
            if boundary:
                walk.radius_spent = True
                continue
            owner[row.far.entry_id] = owner[row.near_id]
            parent[row.far.entry_id] = (row.near_id, row.edge)
            walk.nodes[row.far.entry_id] = row.far._replace(depth=level + 1)
            new.append(row.far.entry_id)
        meetings = [
            row
            for row in rows
            if row.far.entry_id in owner and union.find(owner[row.near_id]) != union.find(owner[row.far.entry_id])
        ]
        meetings.sort(
            key=lambda r: (
                min(owner[r.near_id], owner[r.far.entry_id]),
                max(owner[r.near_id], owner[r.far.entry_id]),
                walk.nodes[r.edge.source_id].path,
                walk.nodes[r.edge.target_id].path,
            )
        )
        for row in meetings:
            if union.union(owner[row.near_id], owner[row.far.entry_id]):
                walk.bridges.append(row.edge)
        level += 1
        if new:
            walk.depth_reached = level
        if boundary:
            break
        frontier = new
    walk.components = union.components
    walk.parent = parent
    return walk


def prune(walk: Walk, roots: Sequence[Node], *, minimal: bool) -> set[str]:
    """The kept ids of a meeting: seeds plus bridge paths, leaves stripped; *minimal* drops non-articulation nodes."""
    seeds = {root.entry_id for root in roots}
    kept = set(seeds)
    for bridge in walk.bridges:
        for end in (bridge.source_id, bridge.target_id):
            node = end
            while node not in seeds:
                kept.add(node)
                node = walk.parent[node][0]
    kept = _strip_leaves(walk, kept, seeds)
    while minimal:
        adjacency = _adjacency(walk, kept)
        cut_points = _articulation_points(kept, adjacency)
        removable = sorted(
            (walk.nodes[node].path, node) for node in kept if node not in seeds and node not in cut_points
        )
        if not removable:
            break
        kept.discard(removable[0][1])
        kept = _strip_leaves(walk, kept, seeds)
    return kept


# ---------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------


async def induced_edges(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    unexpanded: Sequence[str],
    kept: set[str],
) -> list[EdgeRow]:
    """The selected edges of the kept nodes the walk never expanded, their far endpoint judged against *kept*.

    One membership list per statement, no join: both endpoints are kept
    nodes, already live and already admitted, so nothing else is needed.
    """
    edges = site.tables.edges
    found: list[EdgeRow] = []
    for direction in request.directions:
        near, _far = _endpoints(site, direction)
        for chunk in chunked(sorted(unexpanded), frontier_budget(site, request)):
            stmt = select(
                edges.c.source_id, edges.c.target_id, edges.c.edge_type, edges.c.weight, edges.c.distance
            ).where(membership(near, chunk, site.profile), *type_filter(site, request))
            for mapping in (await session.execute(stmt)).mappings():
                edge = _edge_of(mapping)
                if edge.source_id in kept and edge.target_id in kept:
                    found.append(edge)
    return found


async def observe(
    session: AsyncSession, site: Site, request: GraphRequest, walk: Walk, roots: Sequence[Node]
) -> Result:
    """Node rows in ``(depth, path)`` order cut at ``limit``, then every selected edge among them, with the records."""
    ordered = sorted(walk.nodes.values(), key=lambda node: (node.depth, node.path))
    cut = request.limit is not None and len(ordered) > request.limit
    shown = ordered[: request.limit] if cut else ordered
    kept = {node.entry_id for node in shown}
    unexpanded = [entry_id for entry_id in kept if entry_id not in walk.expanded]
    for edge in await induced_edges(session, site, request, unexpanded, kept):
        walk.see(edge)
    among = [edge for edge in walk.edges.values() if edge.source_id in kept and edge.target_id in kept]
    among.sort(key=lambda edge: (walk.nodes[edge.source_id].path, edge.edge_type, walk.nodes[edge.target_id].path))
    rows = [_observe_node(node, request.fetched) for node in shown]
    rows.extend(_observe_edge(edge, walk.nodes) for edge in among)
    errors: list[ResultError] = []
    if cut or walk.more:
        errors.append(
            classified(
                ErrorKind.truncated,
                severity=Severity.warning,
                detail=f"graph returned the nearest {len(shown)} of at least {len(walk.nodes)} nodes; raise limit",
                data={"limit": request.limit, "nodes_found": len(walk.nodes), "depth_reached": walk.depth_reached},
            )
        )
    if walk.components > 1:
        data: dict[str, object] = {"seeds": len(roots), "components": walk.components}
        if walk.radius_spent:
            data["depth"] = request.depth
        errors.append(
            classified(
                ErrorKind.not_found,
                severity=Severity.info,
                detail=f"no path joins every seed: {len(roots)} seeds in {walk.components} components",
                data=data,
            )
        )
    return Result(ops=GRAPH_OPS, observations=rows, errors=errors)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _endpoints(site: Site, direction: Direction) -> tuple[Column[object], Column[object]]:
    """The ``(near, far)`` edge columns for *direction*: the arrow as stored, or reversed."""
    edges = site.tables.edges
    if direction == "outbound":
        return edges.c.source_id, edges.c.target_id
    return edges.c.target_id, edges.c.source_id


def _hop_row(mapping: RowMapping, direction: Direction, far: Node) -> HopRow:
    near_id = mapping["source_id"] if direction == "outbound" else mapping["target_id"]
    return HopRow(near_id, far, _edge_of(mapping))


def _edge_of(mapping: RowMapping) -> EdgeRow:
    return EdgeRow(
        mapping["source_id"], mapping["target_id"], mapping["edge_type"], mapping["weight"], mapping["distance"]
    )


def _node_of(mapping: RowMapping, view: Visibility | None, depth: int) -> Node:
    """The node a judged row describes: whole where the caller reads it, bare where it only holds ``list``."""
    if view is None or view.reads(mapping):
        return Node(mapping["entry_id"], mapping["path"], mapping["kind"], depth, True, mapping)
    return _bare_node(mapping, depth)


def _bare_node(mapping: RowMapping, depth: int) -> Node:
    return Node(mapping["entry_id"], mapping["path"], mapping["kind"], depth, False, None)


async def _road_rows(
    session: AsyncSession,
    site: Site,
    request: GraphRequest,
    direction: Direction,
    chunk: Sequence[str],
    view: Visibility,
) -> list[HopRow]:
    """The road probe: the hidden directories one frontier chunk reaches, those on the road as bare nodes."""
    entry = site.tables.entry
    columns = [entry.c.entry_id, entry.c.path, entry.c.kind, *(entry.c[name] for name in sorted(RIGHTS_FIELDS))]
    stmt = hop_statement(site, request, direction, chunk, columns).where(entry.c.kind == "directory")
    hidden = [mapping for mapping in (await session.execute(stmt)).mappings() if not view.holds(mapping, "list")]
    if not hidden:
        return []
    road = await view.road(session, {mapping["path"] for mapping in hidden})
    return [_hop_row(mapping, direction, _bare_node(mapping, 0)) for mapping in hidden if mapping["path"] in road]


def _observe_node(node: Node, fetched: frozenset[str]) -> Observation:
    if node.mapping is None:
        values: dict[str, object] = {"path": Path._brand(node.path), "kind": node.kind, "populated": BARE_FIELDS}
    else:
        values = {name: node.mapping[name] for name in fetched - BODY_FIELDS}
        values["path"] = Path._brand(node.path)
        values["populated"] = (fetched - BODY_FIELDS) | {"depth"}
    values["depth"] = node.depth
    return Observation.model_validate(values)


def _observe_edge(edge: EdgeRow, nodes: dict[str, Node]) -> Observation:
    """The ``mkedge`` shape; the measures ride only when the caller reads both endpoints."""
    source, target = nodes[edge.source_id], nodes[edge.target_id]
    measured = source.whole and target.whole
    return Observation(
        path=Path._brand(source.path),
        edge_target=Path._brand(target.path),
        edge_type=edge.edge_type,
        edge_weight=edge.weight if measured else None,
        edge_distance=edge.distance if measured else None,
    )


def _adjacency(walk: Walk, kept: set[str]) -> dict[str, set[str]]:
    """The undirected neighbours of every kept node, over the edges the walk saw among them."""
    adjacency: dict[str, set[str]] = {node: set() for node in kept}
    for edge in walk.edges.values():
        if edge.source_id in kept and edge.target_id in kept and edge.source_id != edge.target_id:
            adjacency[edge.source_id].add(edge.target_id)
            adjacency[edge.target_id].add(edge.source_id)
    return adjacency


def _strip_leaves(walk: Walk, kept: set[str], seeds: set[str]) -> set[str]:
    """Remove non-seed nodes with at most one kept neighbour, to a fixed point."""
    kept = set(kept)
    leaves = _leaves(walk, kept, seeds)
    while leaves:
        kept -= leaves
        leaves = _leaves(walk, kept, seeds)
    return kept


def _leaves(walk: Walk, kept: set[str], seeds: set[str]) -> set[str]:
    adjacency = _adjacency(walk, kept)
    return {node for node in kept if node not in seeds and len(adjacency[node]) <= 1}


def _articulation_points(nodes: set[str], adjacency: dict[str, set[str]]) -> set[str]:
    """The nodes whose removal disconnects the undirected graph — an iterative lowpoint search."""
    discovered: dict[str, int] = {}
    low: dict[str, int] = {}
    points: set[str] = set()
    clock = 0
    for root in sorted(nodes):
        if root in discovered:
            continue
        discovered[root] = low[root] = clock
        clock += 1
        root_children = 0
        stack: list[tuple[str, str | None, list[str]]] = [(root, None, sorted(adjacency[root]))]
        while stack:
            node, parent, pending = stack[-1]
            if pending:
                nxt = pending.pop()
                if nxt == parent:
                    continue
                if nxt in discovered:
                    low[node] = min(low[node], discovered[nxt])
                    continue
                discovered[nxt] = low[nxt] = clock
                clock += 1
                if node == root:
                    root_children += 1
                stack.append((nxt, node, sorted(adjacency[nxt])))
                continue
            stack.pop()
            if stack:
                above = stack[-1][0]
                low[above] = min(low[above], low[node])
                if above != root and low[node] >= discovered[above]:
                    points.add(above)
        if root_children > 1:
            points.add(root)
    return points


class _UnionFind:
    """Disjoint sets over the seed indexes; ``union`` reports whether it joined two components."""

    def __init__(self, count: int) -> None:
        self._parent = list(range(count))
        self.components = count

    def find(self, index: int) -> int:
        while self._parent[index] != index:
            self._parent[index] = self._parent[self._parent[index]]
            index = self._parent[index]
        return index

    def union(self, left: int, right: int) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        if b < a:
            a, b = b, a
        self._parent[b] = a
        self.components -= 1
        return True
