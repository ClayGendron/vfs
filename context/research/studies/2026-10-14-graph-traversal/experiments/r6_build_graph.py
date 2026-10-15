"""R6 experiment 1: build the cyclic test graph through the public API.

Run: cd /Users/claygendron/Git/Repos/vfs && uv run python <scratch>/experiments/r6_build_graph.py
"""

from __future__ import annotations

import random

from sqlalchemy import func, select

from r6_common import AUTHORED, DB, META, Edge, Entry, Path, edge_list, open_storage, run, timed

DIRS = ("/src/a", "/src/b", "/lib", "/docs")
FILES_PER_DIR = 500
TARGET_EDGES = 8_000
TYPE_WEIGHTS = {"imports": 0.6, "references": 0.3, "calls": 0.1}


def sccs(nodes: list[str], adj: dict[str, set[str]]) -> list[int]:
    """Sizes of the strongly connected components (iterative Tarjan). A component > 1 is a cycle."""
    index = {}
    low = {}
    on_stack = set()
    stack: list[str] = []
    sizes: list[int] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(adj.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(adj.get(w, ()))))
                    advanced = True
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                size = 0
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    size += 1
                    if w == v:
                        break
                sizes.append(size)
    return sizes


async def main() -> None:
    if DB.exists():
        DB.unlink()
    storage = await open_storage(DB, posture="private")
    print(f"profile={storage._host.profile.name} parameter_budget={storage._host.parameter_budget} "
          f"membership_budget={storage._host.membership_budget}")

    paths = [f"{d}/f{i:04}.py" for d in DIRS for i in range(FILES_PER_DIR)]
    entries = [Entry(path=Path(p), content=f"# {p}\n") for p in paths]
    with timed(f"write {len(entries)} files in one call"):
        written = await storage.write(entries=entries, parents=True)
    assert written.success, written.errors[:3]
    print(f"write: success={written.success} observations={len(written.observations)}")

    rng = random.Random(6)
    types = list(TYPE_WEIGHTS)
    weights = list(TYPE_WEIGHTS.values())
    triples: set[tuple[str, str, str]] = set()
    # Explicit rings guarantee cycles of known length; the random graph adds many more.
    for ring in range(10):
        members = rng.sample(paths, 3 + ring % 5)
        for a, b in zip(members, members[1:] + members[:1]):
            triples.add((a, b, "references"))
    while len(triples) < TARGET_EDGES:
        s, t = rng.sample(paths, 2)
        triples.add((s, t, rng.choices(types, weights)[0]))
    edges = [Edge(source=Path(s), target=Path(t), edge_type=k) for s, t, k in sorted(triples)]
    with timed(f"mkedge {len(edges)} authored edges in one call"):
        made = await storage.mkedge(edges=edges, provenance="user")
    assert made.success, made.errors[:3]
    statuses = {}
    for o in made.observations:
        statuses[o.status] = statuses.get(o.status, 0) + 1
    print(f"mkedge: success={made.success} statuses={statuses}")

    tables = storage._host.tables
    by_type = await storage._host.session_factory().__aenter__()
    try:
        res = await by_type.execute(
            select(tables.edges.c.edge_type, func.count()).group_by(tables.edges.c.edge_type).order_by(tables.edges.c.edge_type)
        )
        print("vfs_edges rows by edge_type:")
        total = 0
        for t, n in res.all():
            print(f"    {t:<12} {n}")
            total += n
        print(f"    {'TOTAL':<12} {total}")
        kinds = await by_type.execute(select(tables.entry.c.kind, func.count()).group_by(tables.entry.c.kind))
        print("vfs_entries rows by kind:", dict(kinds.all()))
    finally:
        await by_type.__aexit__(None, None, None)

    authored = await edge_list(storage, AUTHORED)
    adj: dict[str, set[str]] = {}
    for s, t, _ in authored:
        adj.setdefault(s, set()).add(t)
    nodes = sorted({n for e in authored for n in e[:2]})
    sizes = sccs(nodes, adj)
    big = sorted((s for s in sizes if s > 1), reverse=True)
    print(f"cycles: {len(authored)} authored edges over {len(nodes)} nodes; SCCs of size>1: {len(big)}, "
          f"largest SCC = {big[0] if big else 0} nodes (every node in it lies on a cycle)")
    META.write_text(__import__("json").dumps({"files": len(paths), "authored_edges": len(edges), "dirs": DIRS}))
    await storage.close()
    print(f"kept: {DB}")


if __name__ == "__main__":
    run(main)
