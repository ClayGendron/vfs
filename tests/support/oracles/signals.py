"""The centrality prior's oracle.

Plain loops over lists, the same arithmetic in the same order as the
engine — edge order for the sums, node index within a depth for the tree
passes — so its values are bit-comparable with the engine's.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

NO_PARENT = -1


def centrality_prior(
    node_count: int,
    sources: Sequence[int],
    targets: Sequence[int],
    parents: Sequence[int],
    files: Sequence[bool],
    measure: str,
    gamma: float,
    *,
    damping: float = 0.85,
    alpha: float = 0.1,
    iterations: int = 20,
) -> list[float]:
    """One prior per node, files in ``[0, 1]`` and directories ``0.0``."""
    edges = list(zip(sources, targets, strict=True))
    if measure == "in_degree":
        raw = [0.0] * node_count
        for _, target in edges:
            raw[target] += 1.0
    elif measure == "pagerank":
        raw = _pagerank(node_count, edges, damping, iterations)
    elif measure == "katz":
        raw = _katz(node_count, edges, alpha, iterations)
    else:
        msg = f"unknown measure {measure!r}"
        raise ValueError(msg)
    measured = [math.log1p(value) for value in raw]
    depth = _depths(parents)
    order = sorted(range(node_count), key=lambda node: depth[node])
    total = [0.0] * node_count
    count = [0] * node_count
    own = [0.0] * node_count
    for node in reversed(order):
        if files[node]:
            value, counted = measured[node], True
        elif count[node]:
            value, counted = total[node] / count[node], True
        else:
            value, counted = 0.0, False
        own[node] = value
        if counted and parents[node] != NO_PARENT:
            total[parents[node]] += value
            count[parents[node]] += 1
    prior = [0.0] * node_count
    for node in order:
        parent = parents[node]
        prior[node] = own[node] if parent == NO_PARENT else (1.0 - gamma) * own[node] + gamma * prior[parent]
    scored = [prior[node] for node in range(node_count) if files[node]]
    low, high = (min(scored), max(scored)) if scored else (0.0, 0.0)
    span = high - low
    return [(prior[n] - low) / span if files[n] and span > 0.0 else 0.0 for n in range(node_count)]


def _pagerank(node_count: int, edges: list[tuple[int, int]], damping: float, iterations: int) -> list[float]:
    out_degree = [0.0] * node_count
    for source, _ in edges:
        out_degree[source] += 1.0
    rank = [1.0 / node_count] * node_count
    for _ in range(iterations):
        dangling = 0.0
        for node in range(node_count):
            if out_degree[node] == 0.0:
                dangling += rank[node]
        base = ((1.0 - damping) + damping * dangling) / node_count
        nxt = [base] * node_count
        for source, target in edges:
            nxt[target] += damping * rank[source] / out_degree[source]
        rank = nxt
    return [value * node_count for value in rank]


def _katz(node_count: int, edges: list[tuple[int, int]], alpha: float, iterations: int) -> list[float]:
    score = [0.0] * node_count
    for _ in range(iterations):
        nxt = [1.0] * node_count
        for source, target in edges:
            nxt[target] += alpha * score[source]
        score = nxt
    return [value - 1.0 for value in score]


def _depths(parents: Sequence[int]) -> list[int]:
    depth = [-1] * len(parents)
    for start in range(len(parents)):
        path = []
        node = start
        while depth[node] < 0 and node not in path:
            path.append(node)
            if parents[node] == NO_PARENT:
                break
            node = parents[node]
        if depth[node] < 0 and node in path and parents[node] != NO_PARENT:
            msg = f"the parent chain from node {start} is a cycle"
            raise ValueError(msg)
        base = 0 if parents[path[-1]] == NO_PARENT and depth[path[-1]] < 0 else depth[node] + 1
        for steps, walked in enumerate(reversed(path)):
            if depth[walked] < 0:
                depth[walked] = base + steps
    return depth
