"""R3 executed check: the visibility predicate's shape, and whether it rides inside a recursive walk.

Builds a DatabaseStorage over a SQLite file, posture private, one grant for
``bob`` on ``/priv/deep`` only, a few authored ``cites`` edges, then prints:

  (a) what ``tree("/")`` returns for bob (visible rows plus the road);
  (b) the compiled visibility SQL for bob: the three-seek UNION ALL join on
      every dialect profile that declares a range source, and the literal
      OR clauses the generic floor spells;
  (c) three placements of the predicate inside a WITH RECURSIVE walk over
      vfs_edges on SQLite — materialised CTE, inline derived table, literal
      clauses — and the post-filter-only variant, to show which ones cut
      the walk at a hidden node.

Run from the vfs repo root:
    uv run python <this file> <scratch dir>
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from dataclasses import replace

from sqlalchemy import and_, literal, or_, select
from sqlalchemy.dialects import mssql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import GENERIC, MARIADB, MSSQL, ORACLE, POSTGRESQL
from vfs.storage.backends.database.ranges import visible_entries
from vfs.storage.backends.database.rights import Visibility, resolve_authority, visibility_clauses

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))
FILES = ["/pub/a.md", "/pub/b.md", "/priv/c.md", "/priv/deep/d.md", "/priv/deep/e.md"]
# d -> c -> e is a chain through a hidden node; d -> b leads to a hidden leaf.
CITES = [("/priv/deep/d.md", "/priv/c.md"), ("/priv/c.md", "/priv/deep/e.md"), ("/priv/deep/d.md", "/pub/b.md")]
DIALECTS = {
    "postgresql": (POSTGRESQL, postgresql.dialect()),
    "mssql": (MSSQL, mssql.dialect()),
    "mariadb": (MARIADB, mariadb.MariaDBDialect()),
    "oracle": (ORACLE, oracle.dialect()),
}


def compiled(stmt, dialect) -> str:
    try:
        return str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    except Exception as exc:  # noqa: BLE001 — a bound ARRAY has no literal form; show the parametrised text
        c = stmt.compile(dialect=dialect)
        return f"{c}\n-- params: {c.params}  (literal_binds refused: {type(exc).__name__})"


async def main(scratch: pathlib.Path) -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{scratch}/r3.sqlite")
    assert (await storage.first_touch()).success
    entries = [Entry(path=Path(p), content=f"body of {p}") for p in FILES]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success
    assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
    assert (await storage.grant(path=Path("/priv/deep"), principal="bob", level="read", authority=SYSTEM)).success
    edges = [Edge(source=Path(s), target=Path(t), edge_type="cites") for s, t in CITES]
    assert (await storage.mkedge(edges=edges, authority=SYSTEM)).success

    print("=== (a) tree('/') for bob ===")
    seen = await storage.tree(path=Path("/"), authority=BOB)
    for o in seen.observations:
        bare = o.version is None and o.size_bytes is None
        print(f"  {o.path!s:22} kind={o.kind:10} {'BARE (road)' if bare else 'visible row'}")

    host = storage._host  # noqa: SLF001
    entry, edges_t = host.tables.entry, host.tables.edges
    async with host.session_factory() as session:
        res = await resolve_authority(session, host.tables, host.profile, host.membership_budget, BOB, None)
        rights = res.read
        print("\n=== bob's compiled read rights ===")
        print(f"  level={rights.level} need={rights.need} whole={rights.whole} empty={rights.empty}")
        print(f"  spans={rights.spans} roots={rights.roots} holes={rights.holes}")
        print(f"  owner_arms={rights.owner_arms}")
        print(f"  ranges={rights.ranges()}")

        view = Visibility(rights, host.tables, host.profile, host.membership_budget, host.parameter_budget)
        await view.prepare(session)

        print("\n=== (b1) three-seek UNION ALL join, SQLite (range_source=json_each, fence MATERIALIZED) ===")
        visible = view.entries()
        probe = select(entry.c.path).join(visible, visible.c.entry_id == entry.c.entry_id)
        print(compiled(probe, sqlite.dialect()))
        got = sorted((await session.execute(probe)).scalars())
        print(f"  -> rows the join admits: {got}")

        for name, (profile, dialect) in DIALECTS.items():
            print(f"\n=== (b1) three-seek join as {name} would receive it (range_source={profile.range_source}) ===")
            vis = visible_entries(entry, rights.ranges(), rights.need, profile)
            stmt = select(entry.c.path).join(vis, vis.c.entry_id == entry.c.entry_id)
            print(compiled(stmt, dialect))

        print("\n=== (b2) literal OR clauses — the generic floor (no range source) ===")
        clauses = visibility_clauses(entry, rights, GENERIC, host.parameter_budget)
        for i, clause in enumerate(clauses):
            print(f"  clause {i} ({clause.binds} binds): {compiled(clause.predicate, sqlite.dialect())}")

        # ---- (c) the predicate inside a recursive walk over vfs_edges -------
        ids = dict((await session.execute(select(entry.c.path, entry.c.entry_id))).all())
        names = {v: k for k, v in ids.items()}
        seed = ids["/priv/deep/d.md"]

        def walk_from(seed_id: str, admit, *, visible_from=None, untyped_seed: bool = False):
            """successors of *seed_id* over ``cites`` edges to depth 3, *admit*(target) riding each hop.

            The seed is bound through the ULID type (binary-16 on disk);
            *untyped_seed* renders it as text for EXPLAIN only.
            """
            seed_lit = literal(seed_id) if untyped_seed else literal(seed_id, type_=entry.c.entry_id.type)
            anchor = select(seed_lit.label("entry_id"), literal(0).label("depth"))
            walk = anchor.cte("walk", recursive=True)
            target = entry.alias("t")
            step = (
                select(target.c.entry_id, (walk.c.depth + 1).label("depth"))
                .select_from(walk)
                .join(edges_t, and_(edges_t.c.source_id == walk.c.entry_id, edges_t.c.edge_type == "cites"))
                .join(target, and_(target.c.entry_id == edges_t.c.target_id, target.c.deleted_at.is_(None)))
                .where(walk.c.depth < 3)
            )
            if visible_from is not None:
                step = step.join(visible_from, visible_from.c.entry_id == target.c.entry_id)
            if admit is not None:
                step = step.where(admit(target))
            walk = walk.union_all(step)
            return select(walk.c.entry_id, walk.c.depth).where(walk.c.depth > 0)

        async def run(label: str, stmt) -> set[str]:
            rows = (await session.execute(stmt)).all()
            reached = sorted({(names[r.entry_id], r.depth) for r in rows})
            print(f"  {label:48} reached={reached}")
            return {p for p, _ in reached}

        stored_edges = (await session.execute(select(edges_t.c.source_id, edges_t.c.target_id, edges_t.c.edge_type))).all()
        print("\n=== stored edges (path form) ===")
        for s, t, k in stored_edges:
            print(f"  {names.get(s, s)} -[{k}]-> {names.get(t, t)}")
        print("\n=== (c) WITH RECURSIVE successors(/priv/deep/d.md, depth 3) over cites edges, on SQLite ===")
        print("  bob may see only /priv/deep/*. Chain d -> c(hidden) -> e; d -> b(hidden).")
        unguarded = walk_from(seed, None)
        await run("no rights at all", unguarded)

        # Post-filter only: the walk runs blind, then Python drops hidden rows.
        rows = (await session.execute(unguarded)).all()
        post = sorted({names[r.entry_id] for r in rows if view.admits(_mapping_of(await _row(session, entry, r.entry_id)))})
        print(f"  {'post-filter only (Python admits after the walk)':48} reached={post}  <- e leaks through hidden c")

        # Placement 1: materialised visible-set CTE, joined in the recursive member.
        c1 = walk_from(seed, None, visible_from=view.entries())
        print("\n  -- placement 1: MATERIALIZED visible CTE joined inside the recursive member")
        print("  " + compiled(c1, sqlite.dialect()).replace("\n", "\n  "))
        p1 = await run("placement 1 (materialised CTE)", c1)

        # Placement 2: the union inline as a derived table (no fence), joined inside the recursive member.
        inline = visible_entries(entry, rights.ranges(), rights.need, replace(host.profile, range_fence=None))
        p2 = await run("placement 2 (inline UNION ALL derived table)", walk_from(seed, None, visible_from=inline))

        # Placement 3: the literal OR clauses as WHERE terms on the target row.
        floor = visibility_clauses(entry, rights, GENERIC, host.parameter_budget)
        p3 = await run(
            "placement 3 (literal clauses on the target)",
            walk_from(seed, lambda t: or_(*(_rebase(c.predicate, entry, t) for c in floor))),
        )
        print(f"\n  placements agree: {p1 == p2 == p3} ; the walk is cut at c, so e is NOT reached: {'/priv/deep/e.md' not in p1}")

        print("\n=== EXPLAIN QUERY PLAN, placement 1 ===")
        c1x = walk_from(seed, None, visible_from=view.entries(), untyped_seed=True)
        plan = await session.execute(__import__("sqlalchemy").text("EXPLAIN QUERY PLAN " + compiled(c1x, sqlite.dialect())))
        for r in plan.all():
            print("  " + "  " * 0 + str(r[-1]))
    await storage.close()


async def _row(session, entry, entry_id):
    return (await session.execute(select(entry).where(entry.c.entry_id == entry_id))).mappings().one()


def _mapping_of(m):
    return {"path": m["path"], "owner_id": m["owner_id"], "everyone_level": m["everyone_level"]}


def _rebase(predicate, entry, alias):
    """*predicate* compiled on the entries table, re-pointed at *alias* (the recursive member's target row)."""
    from sqlalchemy.sql import visitors

    def repl(elem):
        if getattr(elem, "table", None) is entry:
            return alias.c[elem.name]
        return None

    return visitors.replacement_traverse(predicate, {}, repl)


if __name__ == "__main__":
    asyncio.run(main(pathlib.Path(sys.argv[1])))
