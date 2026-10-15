"""Two follow-ups.

A. Exact sequential parity from the SQL rows: assign each claimed node its
   FIFO queue position (seeds in input order; then level by level, ordered by
   parent position then node id) and replay bridge detection in that order
   (an edge (u, v) is a bridge when u is dequeued, v is already owned, and the
   owners' components differ). Compare the pre-strip kept set with the
   sequential reference over the same 200 trials.

B. The shared-dependency case: a -> x <- b with seeds [a, b]. Directed leaf
   stripping removes x (out-degree 0), returning the seeds alone; undirected
   stripping keeps it.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r4_reference import UnionFind, backtrack, meeting_subgraph, multi_source_bfs  # noqa: E402
from r4_diag import undirected_strip  # noqa: E402
from r4_sql_bfs import load, random_graph, walk_rows  # noqa: E402


def finish_sequential(rows, seeds, edges):
    origin, parent, dist = {}, {}, {}
    for kind, a, b, d1, d2 in rows:
        if kind == "claim":
            origin[a], dist[a], parent[a] = b, d1, d2
    # queue positions
    ord_of = {s: i for i, s in enumerate(seeds)}
    pos = {s: i for i, s in enumerate(seeds)}
    by_depth: dict[int, list[str]] = {}
    for n, d in dist.items():
        by_depth.setdefault(d, []).append(n)
    nxt = len(seeds)
    for d in sorted(by_depth):
        if d == 0:
            continue
        for n in sorted(by_depth[d], key=lambda n: (pos[parent[n]], int(n))):
            pos[n] = nxt
            nxt += 1
    # undirected adjacency over live edges
    adj: dict[str, set[str]] = {}
    for s, t in edges:
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)
    uf = UnionFind(seeds)
    bridges = []
    # replay: dequeue in position order; stop when connected
    for u in sorted(pos, key=pos.get):
        if uf.components <= 1:
            break
        for v in sorted(adj.get(u, ()), key=int):
            if v not in origin:
                continue  # beyond the depth bound: never claimed
            owned_before = dist[v] <= dist[u] or (parent[v] != u and pos[parent[v]] < pos[u])
            if owned_before and uf.find(origin[v]) != uf.find(origin[u]):
                bridges.append((u, v))
                uf.union(origin[v], origin[u])
    return backtrack(parent, bridges, seeds), bridges


def part_a(trials=200, depth=12):
    rng = random.Random(42)
    same_pre = same_bridges = 0
    for _ in range(trials):
        n = rng.randint(20, 60)
        m = rng.randint(n, 3 * n)
        edges = random_graph(rng, n, m)
        k = rng.randint(2, 6)
        seeds = rng.sample(range(n), k)
        _, r_parent, _, r_bridges, _ = multi_source_bfs(edges, seeds)
        r_pre = backtrack(r_parent, r_bridges, seeds)
        conn = sqlite3.connect(":memory:")
        load(conn, n, edges)
        rows = walk_rows(conn, [str(s) for s in seeds], depth)
        s_pre, s_bridges = finish_sequential(rows, [str(s) for s in seeds], {(str(s), str(t)) for s, t in edges})
        same_pre += {int(x) for x in s_pre} == r_pre
        same_bridges += [(int(a), int(b)) for a, b in s_bridges] == r_bridges
    print(f"A. sequential replay over SQL rows: pre-strip kept identical {same_pre}/{trials}, bridge lists identical {same_bridges}/{trials}")


def part_b():
    edges = {("a", "x"), ("b", "x")}
    seeds = ["a", "b"]
    kept, sub, bridges = meeting_subgraph(edges, seeds)
    print("B. a->x<-b, seeds [a,b]")
    print("   directed strip  :", sorted(kept), sorted(sub), "bridges", bridges)
    _, parent, _, bridges, _ = multi_source_bfs(edges, seeds)
    pre = backtrack(parent, bridges, seeds)
    kept_u, sub_u = undirected_strip(edges, pre, set(seeds))
    print("   undirected strip:", sorted(kept_u), sorted(sub_u))
    edges = {("a", "x"), ("x", "y"), ("b", "y")}  # a->x->y<-b : x has in and out, y has out 0
    kept, sub, _ = meeting_subgraph(edges, ["a", "b"])
    print("   a->x->y<-b directed strip:", sorted(kept), sorted(sub))


if __name__ == "__main__":
    part_b()
    part_a()
