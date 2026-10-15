"""Compile-only experiment: a depth-bounded recursive CTE over vfs-shaped tables, per dialect.

No database is touched. Each statement is rendered by the dialect compiler
and printed. Any compiler refusal is caught and printed as REFUSED.
"""

from __future__ import annotations

import sqlalchemy
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    bindparam,
    literal,
    select,
    union_all,
)
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb

md = MetaData()
edges = Table(
    "vfs_edges", md,
    Column("source_id", Integer), Column("target_id", Integer), Column("edge_type", String),
)
entries = Table(
    "vfs_entries", md,
    Column("id", Integer), Column("path", String), Column("deleted_at", Integer),
    Column("everyone_level", Integer),
)

DIALECTS = {
    "postgresql": postgresql.dialect(),
    "sqlite": sqlite.dialect(),
    "mysql": mysql.dialect(),
    "mariadb": mariadb.MariaDBDialect(),
    "mssql": mssql.dialect(),
    "oracle": oracle.dialect(),
}


def walk(use_union_all: bool, derived_visibility: bool):
    seeds = bindparam("seeds", [1, 2, 3], expanding=True)
    anchor = (
        select(entries.c.id.label("id"), literal(0).label("depth"))
        .where(entries.c.id.in_(seeds), entries.c.deleted_at.is_(None))
    )
    cte = anchor.cte("walk", recursive=True)
    if derived_visibility:
        # The three-seek shape: a UNION ALL of seeks, as a derived table joined on id.
        visible = union_all(
            select(entries.c.id.label("entry_id")).where(entries.c.everyone_level >= bindparam("need", 1)),
            select(entries.c.id.label("entry_id")).where(entries.c.path == bindparam("point", "/a")),
        ).subquery("visible")
        step = (
            select(entries.c.id, (cte.c.depth + 1).label("depth"))
            .select_from(
                cte.join(edges, edges.c.source_id == cte.c.id)
                .join(entries, entries.c.id == edges.c.target_id)
                .join(visible, visible.c.entry_id == entries.c.id)
            )
            .where(edges.c.edge_type == bindparam("edge_type", "fs"), entries.c.deleted_at.is_(None),
                   cte.c.depth < bindparam("max_depth", 3))
        )
    else:
        step = (
            select(entries.c.id, (cte.c.depth + 1).label("depth"))
            .select_from(
                cte.join(edges, edges.c.source_id == cte.c.id)
                .join(entries, entries.c.id == edges.c.target_id)
            )
            .where(edges.c.edge_type == bindparam("edge_type", "fs"), entries.c.deleted_at.is_(None),
                   cte.c.depth < bindparam("max_depth", 3))
        )
    cte = cte.union_all(step) if use_union_all else cte.union(step)
    return select(cte.c.id, cte.c.depth)


print("SQLAlchemy", sqlalchemy.__version__)
for title, kw in (
    ("UNION ALL", dict(use_union_all=True, derived_visibility=False)),
    ("UNION", dict(use_union_all=False, derived_visibility=False)),
    ("UNION ALL + join to union_all(...).subquery() derived table", dict(use_union_all=True, derived_visibility=True)),
):
    print("=" * 78)
    print("SHAPE:", title)
    for name, dialect in DIALECTS.items():
        print("-" * 78)
        print(f"[{name}] (dialect.name={dialect.name!r})")
        try:
            compiled = walk(**kw).compile(dialect=dialect, compile_kwargs={"render_postcompile": True})
            print(str(compiled))
        except Exception as exc:  # noqa: BLE001
            print("REFUSED:", type(exc).__name__, exc)
