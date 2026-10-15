"""Why do the SQL walk and the sequential reference disagree?  Split by cause.

For each of the 200 trials compare, in order:
  1. ownership: for every node the reference claimed, is the SQL owner the same?
  2. bridges: do both pick the same bridge edge set?
  3. pre-strip kept set (seeds + backtracks)
  4. post-strip kept set (directed leaf stripping)
  5. post-strip kept set if the strip were UNDIRECTED (degree-1 non-seed leaves)
"""

from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r4_reference import backtrack, induced_edges, multi_source_bfs, strip_leaves  # noqa: E402
from r4_sql_bfs import finish_in_python, load, random_graph, walk_rows  # noqa: E402


def undirected_strip(edges, kept, protected):
    kept = set(kept)
    while True:
        sub = induced_edges(edges, kept)
        deg = {n: 0 for n in kept}
        for s, t in sub:
            deg[s] += 1
            deg[t] += 1
        removable = {n for n in kept if n not in protected and deg[n] <= 1}
        if not removable:
            return kept, sub
        kept -= removable


def sql_parts(conn, seeds, edges, depth=12):
    rows = walk_rows(conn, [str(s) for s in seeds], depth)
    origin, parent = {}, {}
    for kind, a, b, d1, d2 in rows:
        if kind == "claim":
            origin[int(a)], parent[int(a)] = int(b), int(d2)
    kept, sub, bridges, _ = finish_in_python(rows, [str(s) for s in seeds], {(str(s), str(t)) for s, t in edges})
    bridges = [(int(a), int(b)) for a, b in bridges]
    pre = backtrack(parent, bridges, seeds)
    return origin, parent, bridges, pre, {int(x) for x in kept}


def main(trials=200):
    rng = random.Random(42)
    c = dict(own=0, bridge=0, pre=0, post=0, post_und=0, ref_stripped_to_seeds=0, sql_stripped_to_seeds=0)
    first_cause = {}
    for trial in range(trials):
        n = rng.randint(20, 60)
        m = rng.randint(n, 3 * n)
        edges = random_graph(rng, n, m)
        k = rng.randint(2, 6)
        seeds = rng.sample(range(n), k)
        r_origin, r_parent, _, r_bridges, _ = multi_source_bfs(edges, seeds)
        r_pre = backtrack(r_parent, r_bridges, seeds)
        r_post, _ = strip_leaves(edges, r_pre, set(seeds))
        r_post_u, _ = undirected_strip(edges, r_pre, set(seeds))
        conn = sqlite3.connect(":memory:")
        load(conn, n, edges)
        s_origin, s_parent, s_bridges, s_pre, s_post = sql_parts(conn, seeds, edges)
        s_post_u, _ = undirected_strip(edges, s_pre, set(seeds))
        own_same = all(s_origin.get(v) == o for v, o in r_origin.items())
        br_same = {frozenset(b) for b in r_bridges} == {frozenset(b) for b in s_bridges}
        c["own"] += not own_same
        c["bridge"] += not br_same
        c["pre"] += r_pre != s_pre
        c["post"] += r_post != s_post
        c["post_und"] += r_post_u != s_post_u
        c["ref_stripped_to_seeds"] += (r_post == set(seeds) and len(r_pre) > len(seeds))
        c["sql_stripped_to_seeds"] += (s_post == set(seeds) and len(s_pre) > len(seeds))
        if r_post != s_post:
            cause = "ownership" if not own_same else "bridge choice" if not br_same else "parent choice" if r_pre != s_pre else "strip only"
            first_cause[cause] = first_cause.get(cause, 0) + 1
    print("trials:", trials)
    print("ownership differs (over nodes the reference claimed):", c["own"])
    print("bridge edge set differs:", c["bridge"])
    print("pre-strip kept set differs:", c["pre"])
    print("post-strip (directed) kept set differs:", c["post"])
    print("post-strip (undirected) kept set differs:", c["post_und"])
    print("reference: directed strip collapsed a found path to seeds only:", c["ref_stripped_to_seeds"])
    print("sql:       directed strip collapsed a found path to seeds only:", c["sql_stripped_to_seeds"])
    print("first cause of each post-strip disagreement:", first_cause)


if __name__ == "__main__":
    main()
