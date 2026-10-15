"""R2 experiment: recursive CTE vs client-side frontier loop on a vfs-shaped edge table.

Counts statements, bind parameters and rows produced; never wall-clock.
Graph: entries(id, path, deleted_at, visible) and edges(source_id, target_id, edge_type).
Node 'hidden' is not visible to the caller; node 'dead' is tombstoned. Nothing may be
reached through either. The graph has cycles so UNION ALL without a bound would not end.
"""

import sqlite3
import sys

con = sqlite3.connect(":memory:")
con.executescript(
    """
    CREATE TABLE entries(id TEXT PRIMARY KEY, path TEXT NOT NULL, deleted_at TEXT, visible INT NOT NULL);
    CREATE TABLE edges(id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                       edge_type TEXT NOT NULL);
    CREATE INDEX ix_fwd ON edges(source_id, edge_type);
    CREATE INDEX ix_rev ON edges(target_id, edge_type);
    """
)

# a -> b -> c -> d -> a (4-cycle), b -> hidden -> e, c -> dead -> f, d -> g -> h,
# plus a dense cluster k1..k6 fully connected (cycle-rich).
nodes = ["a", "b", "c", "d", "e", "f", "g", "h", "hidden", "dead"] + [f"k{i}" for i in range(6)]
for n in nodes:
    con.execute(
        "INSERT INTO entries VALUES (?,?,?,?)",
        (n, f"/{n}", "2026-01-01" if n == "dead" else None, 0 if n == "hidden" else 1),
    )
edges = [
    ("a", "b"), ("b", "c"), ("c", "d"), ("d", "a"),
    ("b", "hidden"), ("hidden", "e"),
    ("c", "dead"), ("dead", "f"),
    ("d", "g"), ("g", "h"),
]
ks = [f"k{i}" for i in range(6)]
edges += [(x, y) for x in ks for y in ks if x != y]
edges += [("h", "k0")]
con.executemany("INSERT INTO edges(source_id, target_id, edge_type) VALUES (?,?,'ref')", edges)

VISIBLE = "e.deleted_at IS NULL AND e.visible = 1"

# --- Shape A: one recursive CTE, dedupe on node id via UNION, depth bound, per-hop join ---
def recursive_cte(seeds, depth, dedupe):
    marks = ",".join("?" * len(seeds))
    op = "UNION" if dedupe else "UNION ALL"
    sql = f"""
    WITH RECURSIVE walk(node, depth) AS (
        SELECT e.id, 0 FROM entries e WHERE e.id IN ({marks}) AND {VISIBLE}
        {op}
        SELECT e.id, w.depth + 1
        FROM walk w
        JOIN edges g ON g.source_id = w.node
        JOIN entries e ON e.id = g.target_id AND {VISIBLE}
        WHERE w.depth < ?
    )
    SELECT node, MIN(depth) AS depth, COUNT(*) AS rows_produced FROM walk GROUP BY node ORDER BY node
    """
    rows = con.execute(sql, [*seeds, depth]).fetchall()
    return rows, 1, len(seeds) + 1


# --- Shape B: client-side frontier loop, one statement per hop ---
def frontier_loop(seeds, depth):
    stmts = 0
    binds = 0
    marks = ",".join("?" * len(seeds))
    frontier = [r[0] for r in con.execute(
        f"SELECT e.id FROM entries e WHERE e.id IN ({marks}) AND {VISIBLE}", seeds)]
    stmts += 1
    binds += len(seeds)
    seen = {n: 0 for n in frontier}
    for d in range(1, depth + 1):
        if not frontier:
            break
        marks = ",".join("?" * len(frontier))
        nxt = con.execute(
            f"SELECT DISTINCT e.id FROM edges g JOIN entries e ON e.id = g.target_id AND {VISIBLE} "
            f"WHERE g.source_id IN ({marks})",
            frontier,
        ).fetchall()
        stmts += 1
        binds += len(frontier)
        frontier = [n for (n,) in nxt if n not in seen]
        for n in frontier:
            seen[n] = d
    return sorted(seen.items()), stmts, binds


print("== depth 3 from seed a, UNION (node,depth) dedupe ==")
rows, s, b = recursive_cte(["a"], 3, dedupe=True)
for r in rows:
    print("  ", r)
print("  statements:", s, "binds:", b)

print("== depth 3 from seed a, UNION ALL (walk semantics) ==")
rows, s, b = recursive_cte(["a"], 3, dedupe=False)
for r in rows:
    print("  ", r)

print("== frontier loop depth 3 from seed a ==")
rows, s, b = frontier_loop(["a"], 3)
print("  ", rows)
print("  statements:", s, "binds:", b)

print("== cycle-rich cluster k0, depth 6: rows produced per shape ==")
for dedupe in (True, False):
    rows, _, _ = recursive_cte(["k0"], 6, dedupe)
    print("  dedupe" if dedupe else "  walk  ", "nodes:", len(rows), "rows produced:", sum(r[2] for r in rows))

print("== (node,depth) UNION does NOT converge on a cycle: rows grow with the bound ==")
for bound in (8, 16, 32):
    rows, _, _ = recursive_cte(["a"], bound, dedupe=True)
    print("  bound", bound, "rows produced:", sum(r[2] for r in rows), "nodes:", len(rows))


def node_only_cte(seeds):
    """Unbounded reachability: UNION on the node column alone, no depth column."""
    marks = ",".join("?" * len(seeds))
    sql = f"""
    WITH RECURSIVE walk(node) AS (
        SELECT e.id FROM entries e WHERE e.id IN ({marks}) AND {VISIBLE}
        UNION
        SELECT e.id FROM walk w
        JOIN edges g ON g.source_id = w.node
        JOIN entries e ON e.id = g.target_id AND {VISIBLE}
    )
    SELECT node FROM walk ORDER BY node
    """
    return [r[0] for r in con.execute(sql, seeds).fetchall()]


print("== unbounded reachability with node-only UNION converges on the cyclic graph ==")
print("  nodes:", node_only_cte(["a"]))

print("== multi-seed: union of per-seed results equals one call with both seeds ==")
r_ab, _, _ = recursive_cte(["a", "k1"], 2, True)
r_a, _, _ = recursive_cte(["a"], 2, True)
r_k, _, _ = recursive_cte(["k1"], 2, True)
merged = {}
for node, d, _ in r_a + r_k:
    merged[node] = min(d, merged.get(node, d))
print("  same node set:", sorted(merged) == [r[0] for r in r_ab],
      "same min depth:", all(merged[r[0]] == r[1] for r in r_ab))

print("== hidden/tombstoned never reached and nothing through them ==")
names = set(node_only_cte(["a"]))
print("  hidden in result:", "hidden" in names, "e (only via hidden):", "e" in names,
      "dead:", "dead" in names, "f (only via dead):", "f" in names)

print("== seed 10,000 ids: SQLite bind cap ==")
print("  SQLITE_MAX_VARIABLE_NUMBER:", con.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER))
big = [f"s{i}" for i in range(10_000)]
try:
    recursive_cte(big, 1, True)
    print("  10,000 binds in one IN list: accepted")
except sqlite3.OperationalError as exc:
    print("  10,000 binds in one IN list: refused ->", exc)
print("python", sys.version.split()[0], "sqlite", sqlite3.sqlite_version)
