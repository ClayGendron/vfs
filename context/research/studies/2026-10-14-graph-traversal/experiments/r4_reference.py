"""Readable pure-Python reference of the meeting subgraph and its minimal variant.

Graph: adjacency as ``edges: set[tuple[int, int]]`` of directed edges.
Seeds: a list (input order is the priority order for first-claim ownership).

meeting_subgraph(edges, seeds, depth=None):
  1. multi-source BFS over the undirected view, one global FIFO queue seeded in
     input order; a node is owned by the first seed wavefront that reaches it
     (ties within one frontier: lower node id first, because each node's
     neighbours are scanned in sorted order).
  2. when a scan from node u hits an already-owned v whose owner-component
     differs from u's, (u, v) is a bridge and the two components are unioned.
  3. stop when all seeds share one component or the queue empties
     (or the depth bound is hit).
  4. keep = seeds + both backtracks of every bridge along BFS parents.
  5. directed leaf stripping of non-seed nodes with in-degree 0 or
     out-degree 0 in the induced kept subgraph, to a fixed point.
  returns (kept_nodes, kept_edges, bridges)

min_meeting_subgraph: additionally removes non-seed nodes that are not
articulation points of the undirected kept subgraph, one at a time
(recomputing after each removal, lowest id first), then re-runs leaf stripping.
"""

from __future__ import annotations

from collections import deque


class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}
        self.components = len(self.parent)

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # deterministic: smaller root wins
        if rb < ra:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.components -= 1
        return True


def undirected_adjacency(edges):
    adj: dict[int, set[int]] = {}
    for s, t in edges:
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)
    return adj


def multi_source_bfs(edges, seeds, depth=None):
    """Return (origin, parent, depth_of, bridges, uf) after the wavefronts meet."""
    adj = undirected_adjacency(edges)
    seeds = list(dict.fromkeys(seeds))
    origin: dict[int, int] = {}
    parent: dict[int, int] = {}
    dist: dict[int, int] = {}
    uf = UnionFind(seeds)
    queue: deque[int] = deque()
    for s in seeds:
        origin[s] = s
        parent[s] = s
        dist[s] = 0
        queue.append(s)
    bridges: list[tuple[int, int]] = []
    while queue and uf.components > 1:
        u = queue.popleft()
        if depth is not None and dist[u] >= depth:
            # we may still *detect* meetings at the boundary, but not expand past it
            for v in sorted(adj.get(u, ())):
                if v in origin and uf.find(origin[v]) != uf.find(origin[u]):
                    bridges.append((u, v))
                    uf.union(origin[v], origin[u])
            continue
        for v in sorted(adj.get(u, ())):
            if v not in origin:
                origin[v] = origin[u]
                parent[v] = u
                dist[v] = dist[u] + 1
                queue.append(v)
            elif uf.find(origin[v]) != uf.find(origin[u]):
                bridges.append((u, v))
                uf.union(origin[v], origin[u])
    return origin, parent, dist, bridges, uf


def backtrack(parent, bridges, seeds):
    kept = set(seeds)
    for a, b in bridges:
        for start in (a, b):
            n = start
            while parent[n] != n:
                kept.add(n)
                n = parent[n]
            kept.add(n)
    return kept


def induced_edges(edges, nodes):
    return {(s, t) for s, t in edges if s in nodes and t in nodes}


def strip_leaves(edges, kept, protected):
    """Directed leaf stripping: drop non-protected nodes with in==0 or out==0, to fixpoint."""
    kept = set(kept)
    while True:
        sub = induced_edges(edges, kept)
        outd = {n: 0 for n in kept}
        ind = {n: 0 for n in kept}
        for s, t in sub:
            outd[s] += 1
            ind[t] += 1
        removable = {n for n in kept if n not in protected and (outd[n] == 0 or ind[n] == 0)}
        if not removable:
            return kept, sub
        kept -= removable


def articulation_points(nodes, und_adj):
    """Hopcroft-Tarjan on an undirected graph given as adjacency dict (iterative)."""
    disc: dict[int, int] = {}
    low: dict[int, int] = {}
    aps: set[int] = set()
    timer = 0
    for root in sorted(nodes):
        if root in disc:
            continue
        disc[root] = low[root] = timer
        timer += 1
        root_children = 0
        stack = [(root, None, iter(sorted(und_adj.get(root, ()))))]
        while stack:
            u, p, it = stack[-1]
            advanced = False
            for v in it:
                if v == p:
                    continue
                if v not in disc:
                    disc[v] = low[v] = timer
                    timer += 1
                    if u == root:
                        root_children += 1
                    stack.append((v, u, iter(sorted(und_adj.get(v, ())))))
                    advanced = True
                    break
                low[u] = min(low[u], disc[v])
            if advanced:
                continue
            stack.pop()
            if stack:
                pu = stack[-1][0]
                low[pu] = min(low[pu], low[u])
                if pu != root and low[u] >= disc[pu]:
                    aps.add(pu)
        if root_children > 1:
            aps.add(root)
    return aps


def meeting_subgraph(edges, seeds, depth=None):
    seeds = list(dict.fromkeys(seeds))
    if len(seeds) <= 1:
        return set(seeds), set(), []
    origin, parent, dist, bridges, uf = multi_source_bfs(edges, seeds, depth)
    kept = backtrack(parent, bridges, seeds)
    kept, sub = strip_leaves(edges, kept, set(seeds))
    return kept, sub, bridges


def min_meeting_subgraph(edges, seeds, depth=None):
    kept, sub, bridges = meeting_subgraph(edges, seeds, depth)
    seed_set = set(seeds)
    while True:
        und = {}
        for s, t in sub:
            und.setdefault(s, set()).add(t)
            und.setdefault(t, set()).add(s)
        aps = articulation_points(kept, und)
        removable = sorted(n for n in kept if n not in seed_set and n not in aps)
        if not removable:
            break
        kept.discard(removable[0])
        kept, sub = strip_leaves(edges, kept, seed_set)
    return kept, sub, bridges


if __name__ == "__main__":
    # Hand-built graph: two seeds joined through a cycle, a spur, and a
    # third seed in a disconnected component.
    #   1 -> 2 -> 3 -> 4      (seed 1, seed 4)
    #   2 -> 5 -> 3            (parallel route: cycle 2-3-5 undirected)
    #   3 -> 6                 (spur off 3, dead end)
    #   7 -> 8                 (seed 8 disconnected from the rest)
    #   9 -> 1                 (spur into seed 1)
    edges = {(1, 2), (2, 3), (3, 4), (2, 5), (5, 3), (3, 6), (7, 8), (9, 1)}
    seeds = [1, 4, 8]
    kept, sub, bridges = meeting_subgraph(edges, seeds)
    print("meeting_subgraph")
    print("  bridges     :", bridges)
    print("  kept nodes  :", sorted(kept))
    print("  kept edges  :", sorted(sub))
    kept2, sub2, _ = min_meeting_subgraph(edges, seeds)
    print("min_meeting_subgraph")
    print("  kept nodes  :", sorted(kept2))
    print("  kept edges  :", sorted(sub2))
    print("single seed  :", meeting_subgraph(edges, [1]))
    print("no seed      :", meeting_subgraph(edges, []))
    print("depth=1      :", sorted(meeting_subgraph(edges, [1, 4], depth=1)[0]))
    print("depth=2      :", sorted(meeting_subgraph(edges, [1, 4], depth=2)[0]))
