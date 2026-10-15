"""R6 experiment 2: one recursive CTE per direction, UNION vs UNION ALL, validated against a Python BFS.

Run: cd /Users/claygendron/Git/Repos/vfs && uv run python <scratch>/experiments/r6_cte_walk.py
"""

from __future__ import annotations

import random

from sqlalchemy import Integer, case, func, literal, or_, select, text

from r6_common import (
    AUTHORED,
    DB,
    adjacency_dict,
    bfs,
    count_select,
    edge_list,
    literal_sql,
    live_entries,
    min_depth_select,
    min_depths,
    open_storage,
    per_depth_select,
    rows,
    run,
    walk_cte,
)
from vfs.storage.backends.database.descent import liveness_filters


def walk_both_or(tables, profile, seeds, max_depth, edge_types):
    """`both` as an OR-join on the edges table (one CTE reference, no derived adjacency)."""
    entry, edges = tables.entry, tables.edges
    seed = entry.alias("seed")
    anchor = select(seed.c.entry_id.label("node"), literal(0, Integer).label("depth")).where(
        seed.c.entry_id.in_(list(seeds)), *liveness_filters(seed, profile, include_meta=False)
    )
    walk = anchor.cte("walk_or", recursive=True)
    w = walk.alias("w")
    far_id = case((edges.c.source_id == w.c.node, edges.c.target_id), else_=edges.c.source_id)
    far = entry.alias("far")
    member = (
        select(far_id.label("node"), (w.c.depth + 1).label("depth"))
        .select_from(
            w.join(edges, or_(edges.c.source_id == w.c.node, edges.c.target_id == w.c.node)).join(
                far, far.c.entry_id == far_id
            )
        )
        .where(w.c.depth < max_depth, edges.c.edge_type.in_(list(edge_types)), *liveness_filters(far, profile, include_meta=False))
    )
    return walk.union(member)


async def explain(storage, stmt) -> list[str]:
    sql = literal_sql(stmt, storage._host.engine.dialect)
    plan = await rows(storage, text("EXPLAIN QUERY PLAN " + sql))
    return [f"{'  ' * 0}{r[3]}" for r in plan]


async def main() -> None:
    storage = await open_storage(DB)
    tables, profile = storage._host.tables, storage._host.profile
    entries = await live_entries(storage)
    files = sorted(i for i, m in entries.items() if m["kind"] == "file")
    authored = await edge_list(storage, AUTHORED)
    every = await edge_list(storage, None)
    print(f"live entries={len(entries)} files={len(files)} authored edges={len(authored)} all edges={len(every)}")
    rng = random.Random(62)
    seeds = rng.sample(files, 5)
    print("seeds:", [entries[s]["path"] for s in seeds])

    print("\n(a) rows per depth, max_depth=4, authored types, 5 seeds, cyclic graph")
    print(f"    {'direction':<9} {'form':<9} {'d0':>5} {'d1':>6} {'d2':>7} {'d3':>8} {'d4':>8} {'CTE rows':>9} {'distinct nodes':>14}")
    for direction in ("out", "in", "both"):
        for dedup in (True, False):
            walk = walk_cte(tables, profile, seeds, direction, 4, edge_types=AUTHORED, dedup=dedup)
            per_depth = dict(await rows(storage, per_depth_select(walk)))
            total = await rows(storage, count_select(walk))
            distinct = len(await min_depths(storage, walk))
            form = "UNION" if dedup else "UNION ALL"
            cells = " ".join(f"{per_depth.get(d, 0):>{w}}" for d, w in zip(range(5), (5, 6, 7, 8, 8)))
            print(f"    {direction:<9} {form:<9} {cells} {total[0][0]:>9} {distinct:>14}")

    print("\n(b) UNION dedups (node, depth) pairs, not nodes: nodes appearing at more than one depth, out/4/UNION")
    walk = walk_cte(tables, profile, seeds, "out", 4, edge_types=AUTHORED, dedup=True)
    multi = (
        select(walk.c.node, func.count().label("n"), func.min(walk.c.depth), func.max(walk.c.depth))
        .group_by(walk.c.node)
        .having(func.count() > 1)
        .order_by(func.count().desc(), walk.c.node)
    )
    found = await rows(storage, multi)
    total_rows = (await rows(storage, count_select(walk)))[0][0]
    distinct = len(await min_depths(storage, walk))
    print(f"    CTE rows={total_rows} distinct nodes={distinct} nodes with >1 depth row={len(found)}")
    for node, n, lo, hi in found[:3]:
        depths = sorted(d for (d,) in await rows(storage, select(walk.c.depth).where(walk.c.node == node)))
        print(f"    e.g. {entries[node]['path']}: {n} rows at depths {depths} (min {lo}, max {hi})")
    walk_all = walk_cte(tables, profile, seeds, "out", 4, edge_types=AUTHORED, dedup=False)
    same_depth_dups = await rows(
        storage,
        select(func.count()).select_from(
            select(walk_all.c.node, walk_all.c.depth).group_by(walk_all.c.node, walk_all.c.depth).having(func.count() > 1).subquery()
        ),
    )
    print(f"    under UNION ALL, (node, depth) pairs that occur more than once: {same_depth_dups[0][0]} "
          f"(UNION removes exactly these and nothing else)")

    print("\n(c) BFS distance = GROUP BY node, MIN(depth) over the CTE; the CTE's materialised row count beside it")
    adj_out = adjacency_dict(authored, "out")
    truth = bfs(adj_out, seeds, 4)
    for dedup in (True, False):
        walk = walk_cte(tables, profile, seeds, "out", 4, edge_types=AUTHORED, dedup=dedup)
        got = await min_depths(storage, walk)
        total = (await rows(storage, count_select(walk)))[0][0]
        print(f"    {'UNION' if dedup else 'UNION ALL':<9} CTE rows={total:>6} min-depth rows={len(got):>5} "
              f"== python BFS: {got == truth}")

    print("\nValidation vs pure-Python BFS: 20 random seed sets x depths 1..4 x 3 directions x (authored, all types)")
    agree = disagree = 0
    agree_all = 0
    for trial in range(20):
        seed_set = rng.sample(files, rng.randint(1, 8))
        for types, edges in ((AUTHORED, authored), (None, every)):
            for direction in ("out", "in", "both"):
                adj = adjacency_dict(edges, direction)
                for depth in range(1, 5):
                    truth = bfs(adj, seed_set, depth)
                    walk = walk_cte(tables, profile, seed_set, direction, depth, edge_types=types, dedup=True)
                    got = await min_depths(storage, walk)
                    if got == truth:
                        agree += 1
                    else:
                        disagree += 1
                        print(f"    DISAGREE trial={trial} dir={direction} depth={depth} types={types}: "
                              f"sql={len(got)} bfs={len(truth)}")
                    if depth <= 3 and len(seed_set) <= 3:
                        walk = walk_cte(tables, profile, seed_set, direction, depth, edge_types=types, dedup=False)
                        if await min_depths(storage, walk) == truth:
                            agree_all += 1
                        else:
                            print(f"    DISAGREE(UNION ALL) trial={trial} dir={direction} depth={depth}")
    print(f"    UNION form: {agree} agree / {disagree} disagree; UNION ALL form (subset): {agree_all} agree")

    print("\n`both` as a UNION ALL adjacency derived table vs an OR-join on vfs_edges: same answer, SQLite plans")
    seed_set = rng.sample(files, 3)
    adj = adjacency_dict(authored, "both")
    truth = bfs(adj, seed_set, 3)
    w_union = walk_cte(tables, profile, seed_set, "both", 3, edge_types=AUTHORED)
    w_or = walk_both_or(tables, profile, seed_set, 3, AUTHORED)
    print(f"    adjacency form == BFS: {await min_depths(storage, w_union) == truth}; "
          f"OR-join form == BFS: {await min_depths(storage, w_or) == truth}")
    print("    plan, out direction (adjacency subquery flattened onto the fwd index):")
    for line in await explain(storage, min_depth_select(walk_cte(tables, profile, seed_set, "out", 3, edge_types=AUTHORED))):
        print("      ", line)
    print("    plan, both via UNION ALL adjacency:")
    for line in await explain(storage, min_depth_select(w_union)):
        print("      ", line)
    print("    plan, both via OR-join:")
    for line in await explain(storage, min_depth_select(w_or)):
        print("      ", line)

    print("\nRendered statement (out, depth 3, UNION, sqlite):")
    print(literal_sql(min_depth_select(walk_cte(tables, profile, seed_set[:2], "out", 3, edge_types=AUTHORED)), storage._host.engine.dialect))
    await storage.close()


if __name__ == "__main__":
    run(main)
