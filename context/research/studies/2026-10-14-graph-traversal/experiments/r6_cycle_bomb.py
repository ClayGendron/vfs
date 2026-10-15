"""R6 experiment 5: a dense cyclic cluster — UNION ALL row explosion vs UNION vs the frontier loop.

Run: cd /Users/claygendron/Git/Repos/vfs && uv run python <scratch>/experiments/r6_cycle_bomb.py
"""

from __future__ import annotations

from sqlalchemy import func, select

from r6_common import (
    DB_CYCLE,
    Edge,
    Entry,
    Path,
    StatementCounter,
    adjacency,
    count_select,
    frontier_walk,
    live_entries,
    open_storage,
    rows,
    run,
    timed,
    walk_cte,
)

CLUSTERS = {"k": 200, "s": 50}
TYPES = ("links",)
ROW_CAP = 10_000_000


def union_all_rows(n: int, depth: int) -> int:
    """One seed in an n-clique (both ways): paths of length 0..depth = sum (n-1)^d."""
    return sum((n - 1) ** d for d in range(depth + 1))


async def main() -> None:
    if DB_CYCLE.exists():
        DB_CYCLE.unlink()
    storage = await open_storage(DB_CYCLE)
    host = storage._host
    tables, profile = host.tables, host.profile
    paths = {c: [f"/{c}/n{i:03}.py" for i in range(n)] for c, n in CLUSTERS.items()}
    entries = [Entry(path=Path(p), content="# n\n") for ps in paths.values() for p in ps]
    assert (await storage.write(entries=entries, parents=True)).success
    edges = [
        Edge(source=Path(a), target=Path(b), edge_type="links")
        for ps in paths.values()
        for a in ps
        for b in ps
        if a != b
    ]
    with timed(f"mkedge {len(edges)} clique edges in one call"):
        made = await storage.mkedge(edges=edges, provenance="user")
    assert made.success, made.errors[:2]
    live = await live_entries(storage)
    ids = {m["path"]: i for i, m in live.items()}
    counter = StatementCounter(storage)

    for cluster, n in CLUSTERS.items():
        seed = [ids[paths[cluster][0]]]
        print(f"\n{n}-node cluster, fully connected both ways ({n * (n - 1)} edges), one seed, direction out:")
        print(f"    {'depth':>5} {'UNION ALL rows':>15} {'(predicted)':>12} {'UNION rows':>10} {'UNION join work':>15} "
              f"{'frontier rows':>13} {'frontier stmts':>14}")
        for depth in range(1, 5):
            predicted = union_all_rows(n, depth)
            if predicted <= ROW_CAP:
                with timed(f"UNION ALL depth {depth}"):
                    ua = (await rows(storage, count_select(walk_cte(tables, profile, seed, "out", depth, edge_types=TYPES, dedup=False))))[0][0]
            else:
                ua = "not run"
            with timed(f"UNION depth {depth}"):
                u = (await rows(storage, count_select(walk_cte(tables, profile, seed, "out", depth, edge_types=TYPES, dedup=True))))[0][0]
            # Join work under UNION: every distinct (node, depth-1) row is expanded once -> rows of the member's join.
            work = 0
            for level in range(1, depth + 1):
                prev = walk_cte(tables, profile, seed, "out", level - 1, edge_types=TYPES, dedup=True)
                adj = adjacency(tables, "out", TYPES)
                stmt = select(func.count()).select_from(prev.join(adj, adj.c.frm == prev.c.node)).where(prev.c.depth == level - 1)
                work += (await rows(storage, stmt))[0][0]
            counter.clear()
            got, fw = await frontier_walk(storage, seed, "out", depth, 1_000, edge_types=TYPES)
            print(f"    {depth:>5} {ua!s:>15} {predicted:>12} {u:>10} {work:>15} {fw['rows_returned']:>13} {fw['statements']:>14}")
        print(f"    distinct nodes reachable: {len(got)} (the whole cluster from depth 1 on)")
    counter.detach()
    await storage.close()


if __name__ == "__main__":
    run(main)
