"""R6 experiment 3: the rights predicate inside the recursive member (A) vs on the final result only (B).

Run: cd /Users/claygendron/Git/Repos/vfs && uv run python <scratch>/experiments/r6_cte_rights.py
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.dialects import mssql, oracle, postgresql

from r6_common import ANN, AUTHORED, DB, SYSTEM, Edge, Entry, Path, min_depth_select, open_storage, run, walk_cte
from vfs.storage.backends.database.dialects import MARIADB, MSSQL, ORACLE, POSTGRESQL, SQLITE, membership_budget
from vfs.storage.backends.database.ranges import visible_entries
from vfs.storage.backends.database.rights import RIGHTS_FIELDS, Visibility, resolve_authority

X, HIDDEN, Y, Z = "/src/a/r6_x.py", "/src/b/r6_hidden.py", "/src/a/r6_y.py", "/src/a/r6_z.py"


def mariadb_dialect():
    try:
        from sqlalchemy.dialects.mysql.mariadb import MariaDBDialect

        return MariaDBDialect()
    except Exception as exc:  # noqa: BLE001
        from sqlalchemy.dialects import mysql

        print(f"    (mariadb dialect class unavailable: {exc!r}; compiling with mysql.dialect())")
        return mysql.dialect()


async def main() -> None:
    storage = await open_storage(DB)
    host = storage._host
    tables, profile = host.tables, host.profile
    entry = tables.entry

    written = await storage.write(entries=[Entry(path=Path(p), content=f"# {p}\n") for p in (X, HIDDEN, Y, Z)])
    assert written.success, written.errors[:2]
    made = await storage.mkedge(
        edges=[
            Edge(source=Path(X), target=Path(HIDDEN), edge_type="references"),
            Edge(source=Path(HIDDEN), target=Path(Y), edge_type="references"),
            Edge(source=Path(X), target=Path(Z), edge_type="references"),
        ],
        provenance="user",
    )
    assert made.success, made.errors[:2]
    granted = await storage.grant(path=Path("/src/a"), principal="ann", level="read", authority=SYSTEM)
    assert granted.success, granted.errors[:2]
    print("mount posture: private (everyone holds nothing); ann granted read on /src/a")
    print(f"planted chain: {X} -> {HIDDEN} -> {Y}; control: {X} -> {Z}")

    async with host.session_factory() as session:
        resolution = await resolve_authority(session, tables, profile, host.membership_budget, ANN, None)
        rights = resolution.read
        view = Visibility(rights, tables, profile, host.membership_budget, host.parameter_budget)
        await view.prepare(session)
        print(f"ann's read rights: level={rights.level} spans={rights.spans} roots={rights.roots} "
              f"whole={rights.whole} empty={rights.empty} need={rights.need}")
        visible = view.entries()
        print(f"view.entries() -> {type(visible).__name__} named {visible.name!r} (profile range_source={profile.range_source}, "
              f"range_fence={profile.range_fence})")
        clauses = view.clauses()
        print(f"view.clauses() -> {len(clauses)} clause(s), binds={[c.binds for c in clauses]}")

        # Is the SQL pushdown exact, i.e. equal to Rights.admits over every row?
        judged = select(entry.c.entry_id, entry.c.path, *(entry.c[f] for f in sorted(RIGHTS_FIELDS - {"path"})))
        all_rows = (await session.execute(judged)).mappings().all()
        by_admits = {r["entry_id"] for r in all_rows if view.admits(r)}
        by_sql = {r[0] for r in (await session.execute(select(visible.c.entry_id))).all()}
        print(f"visible_entries rows={len(by_sql)} == rows Rights.admits passes={len(by_admits)}: {by_sql == by_admits}")

        ids = {r["path"]: r["entry_id"] for r in (await session.execute(select(entry.c.path, entry.c.entry_id))).mappings()}
        paths = {v: k for k, v in ids.items()}
        seeds = [ids[X]]

        print("\nPlacement A: predicate inside the recursive member (and the anchor) — the walk cannot pass a hidden node")
        walk_a = walk_cte(tables, profile, seeds, "out", 3, edge_types=AUTHORED, far_join=visible)
        got_a = {paths[n]: d for n, d in (await session.execute(min_depth_select(walk_a))).all()}
        print(f"    reached: {dict(sorted(got_a.items(), key=lambda kv: kv[1]))}")

        print("Placement B: no predicate in the walk; the final result joined to the visible set")
        walk_b = walk_cte(tables, profile, seeds, "out", 3, edge_types=AUTHORED)
        final_b = min_depth_select(walk_b).join(visible, visible.c.entry_id == walk_b.c.node)
        got_b = {paths[n]: d for n, d in (await session.execute(final_b)).all()}
        print(f"    reached: {dict(sorted(got_b.items(), key=lambda kv: kv[1]))}")
        only_b = set(got_b) - set(got_a)
        print(f"    visible nodes B reports that A does not: {sorted(only_b)}  <- reachable only THROUGH the hidden {HIDDEN}")
        print("    ADR 065 pin 1 ('a hidden row is absent ... edge traversals') and Clay's 'rights enforced through the "
              "traversal' require A: nothing is reached through a hidden node.")

        print("\nPlacement A with the literal-OR form (visibility_clauses on the far alias), one statement, all clauses OR-ed")
        walk_c = walk_cte(
            tables, profile, seeds, "out", 3, edge_types=AUTHORED,
            far_terms=lambda far: [or_(*(c.predicate for c in view.clauses(far)))],
        )
        got_c = {paths[n]: d for n, d in (await session.execute(min_depth_select(walk_c))).all()}
        print(f"    reached: {dict(sorted(got_c.items(), key=lambda kv: kv[1]))}  == A: {got_c == got_a}")

        print("\nSQLite executes the three-seek join (json_each, MATERIALIZED CTE) inside the recursive member: yes, above.")
        print("Rendered SQL, placement A, sqlite:")
        print(str(min_depth_select(walk_a).compile(dialect=host.engine.dialect)))

    print("\nCompile-only for the other dialects (placement A, out, depth 3):")
    targets = [
        ("postgresql", postgresql.dialect(), POSTGRESQL),
        ("mariadb", mariadb_dialect(), MARIADB),
        ("mssql", mssql.dialect(), MSSQL),
        ("oracle", oracle.dialect(), ORACLE),
    ]
    for name, dialect, prof in targets:
        pb = dialect.insertmanyvalues_max_parameters
        vis = visible_entries(entry, rights.ranges(), rights.need, prof)
        walk = walk_cte(tables, prof, seeds, "out", 3, edge_types=AUTHORED, far_join=vis)
        stmt = min_depth_select(walk)
        try:
            sql = str(stmt.compile(dialect=dialect))
        except Exception as exc:  # noqa: BLE001
            print(f"--- {name}: COMPILE REFUSED: {exc!r}")
            continue
        head = sql.split("\n", 1)[0]
        print(f"--- {name}: parameter_budget={pb} membership_budget={membership_budget(prof, pb)} "
              f"visible={type(vis).__name__} first line: {head!r}")
        print(sql)
        print()
    _ = SQLITE
    await storage.close()


if __name__ == "__main__":
    run(main)
