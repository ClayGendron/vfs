"""The meeting subgraph's oracle: a readable level-synchronous reference written to the declared rules.

The graph is a list of ``(source, target, edge_type)`` triples read
undirected. Seeds are a sequence whose order is the priority for
ownership. ``meet`` returns the kept node ids with their distance from
the owning seed, the bridges accepted, and how many components the seeds
end in.

The rules, as the spec declares them:

1. Level by level: every frontier node's edges are read at once; a
   newly reached node is claimed in ``(owner's seed index, edge type,
   near id, far id)`` order by the first row that names it, so it is
   owned by the nearest seed, ties by seed input order, and its parent
   is the least ``(edge type, near id)`` among its reachers.
2. A row whose endpoints have different owners is a meeting; after the
   claims of a level, meetings are accepted in ``(min owner index, max
   owner index, source id, target id)`` order by union-find, and an
   accepted one is a bridge.
3. The walk stops when every seed shares one component, the frontier
   empties, or *depth* levels have run; at a spent radius one more
   boundary level detects meetings without claiming.
4. Kept = seeds plus every bridge endpoint traced back to its seed
   through the parent map; then non-seed nodes with at most one kept
   neighbour are stripped to a fixed point (undirected).
5. ``minimal``: repeatedly drop the lowest-id non-seed node that is not
   an articulation point of the undirected kept subgraph, re-strip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence

Edge = tuple[str, str, str]


class Meeting(NamedTuple):
    depths: dict[str, int]
    bridges: list[Edge]
    components: int


def meet(edges: Sequence[Edge], seeds: Sequence[str], depth: int | None = None, *, minimal: bool = False) -> Meeting:
    """The meeting subgraph of *seeds* over *edges*, by the declared rules."""
    seeds = list(dict.fromkeys(seeds))
    owner = {seed: index for index, seed in enumerate(seeds)}
    parent: dict[str, str] = {}
    dist = dict.fromkeys(seeds, 0)
    roots = list(range(len(seeds)))
    components = len(seeds)
    bridges: list[Edge] = []

    def find(index: int) -> int:
        while roots[index] != index:
            roots[index] = roots[roots[index]]
            index = roots[index]
        return index

    frontier = list(seeds)
    level = 0
    while frontier and components > 1:
        boundary = depth is not None and level >= depth
        rows = [
            (near, far, edge)
            for edge in edges
            for near, far in ((edge[0], edge[1]), (edge[1], edge[0]))
            if near in frontier
        ]
        new: list[str] = []
        for near, far, _edge in sorted(rows, key=lambda r: (owner[r[0]], r[2][2], r[0], r[1])):
            if far in owner or boundary:
                continue
            owner[far] = owner[near]
            parent[far] = near
            dist[far] = level + 1
            new.append(far)
        meetings = [
            (near, far, edge) for near, far, edge in rows if far in owner and find(owner[near]) != find(owner[far])
        ]
        meetings.sort(key=lambda r: (min(owner[r[0]], owner[r[1]]), max(owner[r[0]], owner[r[1]]), r[2][0], r[2][1]))
        for near, far, edge in meetings:
            a, b = find(owner[near]), find(owner[far])
            if a != b:
                roots[max(a, b)] = min(a, b)
                components -= 1
                bridges.append(edge)
        level += 1
        if boundary:
            break
        frontier = new

    kept = set(seeds)
    for source, target, _type in bridges:
        for end in (source, target):
            node = end
            while node not in seeds:
                kept.add(node)
                node = parent[node]
    kept = _strip(edges, kept, set(seeds))
    while minimal:
        points = _articulation_points(kept, _adjacency(edges, kept))
        removable = sorted(node for node in kept if node not in seeds and node not in points)
        if not removable:
            break
        kept.discard(removable[0])
        kept = _strip(edges, kept, set(seeds))
    return Meeting({node: dist[node] for node in kept}, bridges, components)


def _adjacency(edges: Sequence[Edge], kept: set[str]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {node: set() for node in kept}
    for source, target, _type in edges:
        if source in kept and target in kept and source != target:
            adjacency[source].add(target)
            adjacency[target].add(source)
    return adjacency


def _strip(edges: Sequence[Edge], kept: set[str], seeds: set[str]) -> set[str]:
    kept = set(kept)
    while True:
        adjacency = _adjacency(edges, kept)
        leaves = {node for node in kept if node not in seeds and len(adjacency[node]) <= 1}
        if not leaves:
            return kept
        kept -= leaves


def _articulation_points(nodes: set[str], adjacency: dict[str, set[str]]) -> set[str]:
    """Recursive lowpoint search — the oracle may recurse; the kept sets it sees are small."""
    discovered: dict[str, int] = {}
    low: dict[str, int] = {}
    points: set[str] = set()
    clock = [0]

    def visit(node: str, parent: str | None) -> None:
        discovered[node] = low[node] = clock[0]
        clock[0] += 1
        children = 0
        for other in sorted(adjacency[node]):
            if other == parent:
                continue
            if other in discovered:
                low[node] = min(low[node], discovered[other])
                continue
            children += 1
            visit(other, node)
            low[node] = min(low[node], low[other])
            if parent is not None and low[other] >= discovered[node]:
                points.add(node)
        if parent is None and children > 1:
            points.add(node)

    for root in sorted(nodes):
        if root not in discovered:
            visit(root, None)
    return points
