"""Scale probe: 100k nodes / 400k edges / 1,000 seeds in SQLite.

Two SQL shapes are measured:

A. one recursive CTE per call, bounded by depth 1..4 (the r4_sql_bfs shape):
   rows in the working table, rows after claim, meets, and elapsed time.

B. one statement per hop, app-side loop: a ``visited`` temp table holds
   (node, origin, ord, depth, parent); each hop inserts the unclaimed
   neighbours of the previous frontier (first claim by seed ord, then node id),
   then a second statement lists the edges whose endpoints are owned by
   different origins; Python runs union-find between hops and stops when every
   seed shares a component or the frontier empties.

Edges have locality: 80% of targets lie within +/-50 of the source id, 20% are
uniform. Seeds are 1,000 random ids.
"""

from __future__ import annotations

import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r4_reference import UnionFind  # noqa: E402
from r4_sql_bfs import DDL, WALK_SQL, seed_values  # noqa: E402

N, M, K = 100_000, 400_000, 1_000


def build(rng):
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    conn.executemany("INSERT INTO vfs_entries VALUES (?, ?, NULL)", [(str(i), f"/n/{i}") for i in range(N)])
    edges = set()
    while len(edges) < M:
        s = rng.randrange(N)
        if rng.random() < 0.8:
            t = (s + rng.randint(-50, 50)) % N
        else:
            t = rng.randrange(N)
        if s != t:
            edges.add((s, t))
    conn.executemany("INSERT OR IGNORE INTO vfs_edges (source_id, target_id, edge_type) VALUES (?, ?, 'ref')",
                     [(str(s), str(t)) for s, t in edges])
    conn.execute("ANALYZE")
    return conn


COUNT_WALK_SQL = """
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
)
SELECT COUNT(*), COUNT(DISTINCT node) FROM walk
"""


def probe_single_cte(conn, seeds):
    print("A. single recursive CTE (UNION over (node, origin, ord, depth)), 1,000 seeds")
    print("   depth | walk rows | distinct nodes | claim+meet rows | meets | seconds")
    for depth in (1, 2, 3, 4):
        t0 = time.perf_counter()
        walk_rows, distinct = conn.execute(COUNT_WALK_SQL.format(seed_values=seed_values(seeds)), {"depth": depth}).fetchone()
        t1 = time.perf_counter()
        rows = conn.execute(WALK_SQL.format(seed_values=seed_values(seeds)), {"depth": depth}).fetchall()
        t2 = time.perf_counter()
        meets = sum(1 for r in rows if r[0] == "meet")
        print(f"   {depth:5d} | {walk_rows:9d} | {distinct:14d} | {len(rows):15d} | {meets:5d} | count={t1 - t0:.2f} full={t2 - t1:.2f}")


HOP_DDL = """
CREATE TEMP TABLE visited (node TEXT PRIMARY KEY, origin TEXT NOT NULL, ord INTEGER NOT NULL,
                           depth INTEGER NOT NULL, parent TEXT NOT NULL);
CREATE INDEX visited_depth ON visited (depth);
"""

# One hop: the unclaimed neighbours of the frontier, first claim by (ord, node id).
HOP_SQL = """
INSERT INTO visited (node, origin, ord, depth, parent)
SELECT nb, origin, ord, :next_depth, parent FROM (
    SELECT u.b AS nb, f.origin, f.ord, f.node AS parent,
           ROW_NUMBER() OVER (PARTITION BY u.b ORDER BY f.ord, f.node) AS rn
    FROM visited f
      JOIN (
        SELECT e.source_id AS a, e.target_id AS b FROM vfs_edges e
          JOIN vfs_entries t ON t.id = e.target_id AND t.deleted_at IS NULL
        UNION ALL
        SELECT e.target_id, e.source_id FROM vfs_edges e
          JOIN vfs_entries s ON s.id = e.source_id AND s.deleted_at IS NULL
      ) u ON u.a = f.node
    WHERE f.depth = :depth
      AND NOT EXISTS (SELECT 1 FROM visited v WHERE v.node = u.b)
) WHERE rn = 1
"""

# Meets touching the new frontier: edges whose two endpoints have different owners.
MEET_SQL = """
SELECT e.source_id, e.target_id, a.depth, b.depth
FROM vfs_edges e
  JOIN visited a ON a.node = e.source_id
  JOIN visited b ON b.node = e.target_id
WHERE a.origin <> b.origin AND (a.depth = :depth OR b.depth = :depth)
"""


def probe_per_hop(conn, seeds, max_depth=8):
    print("B. one statement per hop, app-side union-find between hops")
    conn.executescript("DROP TABLE IF EXISTS visited;" + HOP_DDL)
    conn.executemany("INSERT INTO visited VALUES (?, ?, ?, 0, ?)", [(s, s, i, s) for i, s in enumerate(seeds)])
    uf = UnionFind(seeds)
    origin = {s: s for s in seeds}
    bridges = []
    t_all = time.perf_counter()
    print("   hop | new nodes | visited | meets this hop | seed components | seconds")
    for depth in range(0, max_depth):
        t0 = time.perf_counter()
        # meets at this depth (depth 0 = adjacent seeds)
        meets = conn.execute(MEET_SQL, {"depth": depth}).fetchall()
        for a, b, _, _ in meets:
            oa = conn.execute("SELECT origin FROM visited WHERE node = ?", (a,)).fetchone()[0] if a not in origin else origin[a]
            ob = conn.execute("SELECT origin FROM visited WHERE node = ?", (b,)).fetchone()[0] if b not in origin else origin[b]
            origin[a], origin[b] = oa, ob
            if uf.union(oa, ob):
                bridges.append((a, b))
        if uf.components <= 1:
            print(f"   {depth:3d} | {'-':>9} | {conn.execute('SELECT COUNT(*) FROM visited').fetchone()[0]:7d} | {len(meets):14d} | {uf.components:15d} | {time.perf_counter() - t0:.2f}  <- all seeds connected, stop")
            break
        cur = conn.execute(HOP_SQL, {"depth": depth, "next_depth": depth + 1})
        new = cur.rowcount
        visited = conn.execute("SELECT COUNT(*) FROM visited").fetchone()[0]
        print(f"   {depth:3d} | {new:9d} | {visited:7d} | {len(meets):14d} | {uf.components:15d} | {time.perf_counter() - t0:.2f}")
        if new == 0:
            print("   frontier empty, stop")
            break
    print(f"   bridges={len(bridges)} total={time.perf_counter() - t_all:.2f}s")


if __name__ == "__main__":
    rng = random.Random(7)
    t0 = time.perf_counter()
    conn = build(rng)
    print(f"built N={N} M={M} in {time.perf_counter() - t0:.1f}s")
    seeds = [str(x) for x in rng.sample(range(N), K)]
    probe_single_cte(conn, seeds)
    probe_per_hop(conn, seeds)
