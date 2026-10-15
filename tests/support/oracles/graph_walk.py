"""The frontier walk's oracle: a readable breadth-first search over an edge list.

The graph is a list of ``(source, target, edge_type)`` triples. ``walk``
answers what the backend's ``inbound``, ``outbound`` and ``neighborhood``
answer — every node within *depth* hops of a seed with its distance from
the nearest seed, seeds at 0 — and ``induced`` the selected edges among a
node set in the walk's direction(s). Only live, visible nodes are ever
handed in: the oracle knows nothing of tombstones or rights, so a test
that plants one filters the edge list first.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

Edge = tuple[str, str, str]

DIRECTIONS = {
    "outbound": ("outbound",),
    "inbound": ("inbound",),
    "neighborhood": ("outbound", "inbound"),
}


def neighbours(edges: Iterable[Edge], node: str, method: str, types: frozenset[str] | None) -> list[str]:
    """The nodes one hop from *node* in *method*'s direction(s), over the selected *types* (``None``: every type)."""
    found: list[str] = []
    for source, target, edge_type in edges:
        if types is not None and edge_type not in types:
            continue
        if "outbound" in DIRECTIONS[method] and source == node:
            found.append(target)
        if "inbound" in DIRECTIONS[method] and target == node:
            found.append(source)
    return found


def walk(
    edges: Sequence[Edge], seeds: Sequence[str], method: str, depth: int | None, types: frozenset[str] | None = None
) -> dict[str, int]:
    """``node → distance from the nearest seed`` for every node within *depth* hops (``None``: unbounded)."""
    found = dict.fromkeys(seeds, 0)
    queue = deque(seeds)
    while queue:
        node = queue.popleft()
        if depth is not None and found[node] >= depth:
            continue
        for far in neighbours(edges, node, method, types):
            if far not in found:
                found[far] = found[node] + 1
                queue.append(far)
    return found


def induced(edges: Iterable[Edge], nodes: Iterable[str], types: frozenset[str] | None = None) -> set[Edge]:
    """Every selected edge whose both endpoints are in *nodes*."""
    kept = set(nodes)
    return {
        (source, target, edge_type)
        for source, target, edge_type in edges
        if source in kept and target in kept and (types is None or edge_type in types)
    }
