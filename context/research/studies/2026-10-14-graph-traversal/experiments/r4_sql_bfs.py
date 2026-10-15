"""Meeting subgraph: how much can live in SQL, validated against r4_reference.

Schema mirrors vfs: vfs_entries(id, path, deleted_at), vfs_edges(source_id, target_id, edge_type).

Phase 1 (SQL, one statement): a recursive CTE walks the undirected live view
from all seeds at once. The recursion carries only (node, origin, ord, depth)
under UNION (set) semantics and is bounded by :depth. A first attempt that
carried the parent under UNION ALL enumerated *walks*, not nodes, and did not
finish 200 small trials in two minutes -- cycles make the working table
exponential without a visited set, and a recursive CTE has no visited set.
Phase 2 (same statement): ``claim`` = one owner row per node by
(min depth, seed ord); ``parent`` recovered by joining the claim of a neighbour
one hop closer with the same origin (lowest id); ``meet`` = live edges whose
endpoints have different owners.
Phase 3 (Python, small): union-find over the meets in meeting order, backtrack
along parents, directed leaf stripping.
"""

from __future__ import annotations

import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r4_reference import UnionFind, meeting_subgraph, multi_source_bfs, strip_leaves  # noqa: E402

DDL = """
CREATE TABLE vfs_entries (id TEXT PRIMARY KEY, path TEXT NOT NULL, deleted_at TEXT);
CREATE TABLE vfs_edges (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL, target_id TEXT NOT NULL, edge_type TEXT NOT NULL,
    UNIQUE (source_id, target_id, edge_type)
);
CREATE INDEX ix_vfs_edges_fwd ON vfs_edges (source_id, edge_type);
CREATE INDEX ix_vfs_edges_rev ON vfs_edges (target_id, edge_type);
"""

WALK_SQL = """
WITH RECURSIVE
seeds(node, ord) AS (VALUES {seed_values}),
und(a, b) AS (
    SELECT e.source_id, e.target_id FROM vfs_edges e
      JOIN vfs_entries s ON s.id = e.source_id AND s.deleted_at IS NULL
      JOIN vfs_entries t ON t.id = e.target_id AND t.deleted_at IS NULL
    UNION ALL
    SELECT e.target_id, e.source_id FROM vfs_edges e
      JOIN vfs_entries s ON s.id = e.source_id AND s.deleted_at IS NULL
      JOIN vfs_entries t ON t.id = e.target_id AND t.deleted_at IS NULL
),
walk(node, origin, ord, depth) AS (
    SELECT node, node, ord, 0 FROM seeds
    UNION
    SELECT u.b, w.origin, w.ord, w.depth + 1
    FROM walk w JOIN und u ON u.a = w.node
    WHERE w.depth < :depth
),
claim AS (
    SELECT node, origin, ord, depth
    FROM (
        SELECT node, origin, ord, depth,
               ROW_NUMBER() OVER (PARTITION BY node ORDER BY depth, ord) AS rn
        FROM walk
    ) WHERE rn = 1
),
parent AS (
    SELECT c.node, MIN(p.node) AS parent
    FROM claim c
      JOIN und u ON u.a = c.node
      JOIN claim p ON p.node = u.b AND p.origin = c.origin AND p.depth = c.depth - 1
    GROUP BY c.node
)
SELECT 'claim' AS kind, c.node AS a, c.origin AS b, c.depth AS d1, COALESCE(p.parent, c.node) AS d2
FROM claim c LEFT JOIN parent p ON p.node = c.node
UNION ALL
SELECT 'meet', e.source_id, e.target_id, cs.depth, ct.depth
FROM vfs_edges e
  JOIN claim cs ON cs.node = e.source_id
  JOIN claim ct ON ct.node = e.target_id
WHERE cs.origin <> ct.origin
"""


def seed_values(seeds):
    return ", ".join(f"('{s}', {i})" for i, s in enumerate(seeds))


def walk_rows(conn, seeds, depth):
    return conn.execute(WALK_SQL.format(seed_values=seed_values(seeds)), {"depth": depth}).fetchall()


def finish_in_python(rows, seeds, edges):
    origin, parent, dist = {}, {}, {}
    meets = []
    for kind, a, b, d1, d2 in rows:
        if kind == "claim":
            origin[a], dist[a], parent[a] = b, d1, d2
        else:
            meets.append((a, b, d1, d2))
    ord_of = {s: i for i, s in enumerate(seeds)}
    meets.sort(key=lambda m: (min(m[2], m[3]), max(m[2], m[3]),
                              ord_of[origin[m[0]]], ord_of[origin[m[1]]], m[0], m[1]))
    uf = UnionFind(seeds)
    bridges = []
    for a, b, _, _ in meets:
        if uf.union(origin[a], origin[b]):
            bridges.append((a, b))
    kept = set(seeds)
    for a, b in bridges:
        for start in (a, b):
            n = start
            while parent[n] != n:
                kept.add(n)
                n = parent[n]
            kept.add(n)
    kept, sub = strip_leaves(edges, kept, set(seeds))
    return kept, sub, bridges, uf.components


def sql_meeting_subgraph(conn, seeds, depth):
    seeds = list(dict.fromkeys(seeds))
    if len(seeds) <= 1:
        return set(seeds), set()
    rows = walk_rows(conn, seeds, depth)
    edges = {(s, t) for s, t in conn.execute("SELECT source_id, target_id FROM vfs_edges")}
    kept, sub, _, _ = finish_in_python(rows, seeds, edges)
    return kept, sub


def load(conn, n_nodes, edges, deleted=()):
    conn.executescript(DDL)
    conn.executemany("INSERT INTO vfs_entries VALUES (?, ?, ?)",
                     [(str(i), f"/n/{i}", ("x" if i in deleted else None)) for i in range(n_nodes)])
    conn.executemany("INSERT OR IGNORE INTO vfs_edges (source_id, target_id, edge_type) VALUES (?, ?, 'ref')",
                     [(str(s), str(t)) for s, t in edges])


def random_graph(rng, n, m):
    edges = set()
    while len(edges) < m:
        s, t = rng.randrange(n), rng.randrange(n)
        if s != t:
            edges.add((s, t))
    return edges


def seed_groups(sub, seeds):
    adj = {}
    for s, t in sub:
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)
    comp = {}
    for s in seeds:
        if s in comp:
            continue
        stack, comp[s] = [s], s
        while stack:
            u = stack.pop()
            for v in adj.get(u, ()):
                if v not in comp:
                    comp[v] = s
                    stack.append(v)
    return frozenset(frozenset(x for x in seeds if comp[x] == c) for c in {comp[x] for x in seeds})


def validate(trials=200, depth=12):
    rng = random.Random(42)
    agree = same_groups = 0
    size_equal = 0
    disagreements = []
    t0 = time.perf_counter()
    for trial in range(trials):
        n = rng.randint(20, 60)
        m = rng.randint(n, 3 * n)
        edges = random_graph(rng, n, m)
        k = rng.randint(2, 6)
        seeds = rng.sample(range(n), k)
        ref_kept, ref_sub, _ = meeting_subgraph(edges, seeds)
        conn = sqlite3.connect(":memory:")
        load(conn, n, edges)
        sql_kept, sql_sub = sql_meeting_subgraph(conn, [str(s) for s in seeds], depth)
        sql_kept = {int(x) for x in sql_kept}
        sql_sub = {(int(a), int(b)) for a, b in sql_sub}
        if sql_kept == ref_kept:
            agree += 1
            continue
        same = seed_groups(ref_sub, seeds) == seed_groups(sql_sub, seeds)
        same_groups += same
        size_equal += len(sql_kept) == len(ref_kept)
        disagreements.append((trial, n, m, seeds, len(ref_kept), len(sql_kept), same,
                              sorted(ref_kept - sql_kept), sorted(sql_kept - ref_kept)))
    el = time.perf_counter() - t0
    print(f"trials={trials} depth_bound={depth} elapsed={el:.1f}s")
    print(f"identical kept-set: {agree} ({agree / trials:.1%})")
    print(f"disagreements: {len(disagreements)}; same seed-connectivity: {same_groups}; same size: {size_equal}")
    for d in disagreements[:10]:
        trial, n, m, seeds, rk, sk, same, only_ref, only_sql = d
        print(f"  trial {trial}: n={n} m={m} seeds={seeds} |ref|={rk} |sql|={sk} same_groups={same} only_ref={only_ref} only_sql={only_sql}")
    return disagreements


def tombstone_check():
    """A tombstoned intermediary must be absent and nothing reached through it."""
    edges = {(1, 2), (2, 3), (1, 4), (4, 5), (5, 3)}
    conn = sqlite3.connect(":memory:")
    load(conn, 6, edges, deleted={2})
    kept, sub = sql_meeting_subgraph(conn, ["1", "3"], 8)
    print("tombstone 2 hidden ->", sorted(kept, key=int), sorted(sub))
    conn = sqlite3.connect(":memory:")
    load(conn, 6, edges)
    kept, sub = sql_meeting_subgraph(conn, ["1", "3"], 8)
    print("nothing hidden     ->", sorted(kept, key=int), sorted(sub))


def hand_graph_check():
    edges = {(1, 2), (2, 3), (3, 4), (2, 5), (5, 3), (3, 6), (7, 8), (9, 1)}
    conn = sqlite3.connect(":memory:")
    load(conn, 10, edges)
    kept, sub = sql_meeting_subgraph(conn, ["1", "4", "8"], 8)
    print("hand graph         ->", sorted(kept, key=int), sorted(sub))


if __name__ == "__main__":
    hand_graph_check()
    tombstone_check()
    validate()
