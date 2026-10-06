"""The three-seek statement's SQL, rendered per dialect without a server.

The engine legs run each spelling for real (the grants contract); these
pin the rendered shape on every leg's run, so a spelling that drifts —
a join keyword lost, a hint dropped, a collation missing — fails here
too. Row-exact parity on a live engine is ``test_rights.py``'s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mssql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb
from sqlalchemy.sql.elements import True_

from vfs.models.rows import MSSQL_UTF8_COLLATION, build_vfs_tables
from vfs.storage.backends.database.dialects import GENERIC, MARIADB, MSSQL, ORACLE, POSTGRESQL, SQLITE
from vfs.storage.backends.database.ranges import (
    VISIBLE_ALIAS,
    derived_hint,
    hole_free,
    range_counts,
    visible_entries,
)
from vfs.storage.grants import LEVEL_RANK, Pieces, Ranges

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

    from vfs.storage.backends.database.dialects import DialectProfile

TABLES = build_vfs_tables()
ENTRY = TABLES.entry
BOTH = Pieces(("/a",), (("/a/", "/a0"),))
NONE = Pieces((), ())

# Each profile, the dialect that renders it, and fragments its rendering must hold.
SPELLINGS: list[tuple[DialectProfile, Dialect, tuple[str, ...]]] = [
    (
        SQLITE,
        sqlite.dialect(),
        ("json_each(", "json_extract(", "AS pts CROSS JOIN vfs_entries ON", "AS rng CROSS JOIN vfs_entries ON"),
    ),
    (POSTGRESQL, postgresql.dialect(), ("unnest(", "::TEXT[]", 'COLLATE "C"', "(lo, hi) JOIN vfs_entries ON")),
    (
        MSSQL,
        mssql.dialect(),
        (
            "openjson(",
            "OPENJSON(",
            "WITH (lo nvarchar(max)",
            MSSQL_UTF8_COLLATION,
            "AS rng INNER LOOP JOIN vfs_entries ON",
        ),
    ),
    (
        MARIADB,
        mariadb.MariaDBDialect(),
        (
            "JSON_TABLE(",
            "COLUMNS (value VARCHAR",
            "AS BINARY",
            "AS rng STRAIGHT_JOIN vfs_entries FORCE INDEX (ix_vfs_entries_path) ON",
        ),
    ),
    (
        ORACLE,
        oracle.dialect(),
        (
            "JSON_TABLE(",
            "VARCHAR2(1024)",
            "/*+ INDEX(vfs_entries ix_vfs_entries_everyone_path) */",
            "/*+ CARDINALITY(pts 1) */",
            "/*+ CARDINALITY(rng 1) */",
            ") rng JOIN vfs_entries ON",
        ),
    ),
]


def _render(ranges: Ranges, profile: DialectProfile, dialect: Dialect, scope: str | None = None) -> str:
    return str(select(visible_entries(ENTRY, ranges, LEVEL_RANK["read"], profile, scope)).compile(dialect=dialect))


@pytest.mark.parametrize(("profile", "dialect", "fragments"), SPELLINGS, ids=[s[0].name for s in SPELLINGS])
def test_each_dialect_renders_its_measured_spelling(
    profile: DialectProfile, dialect: Dialect, fragments: tuple[str, ...]
) -> None:
    sql = _render(Ranges(BOTH, (("ann", BOTH),)), profile, dialect)
    for fragment in fragments:
        assert fragment in sql, sql
    # The everyone branch, then two piece kinds for the arms and two for
    # ann's owner arm, each in its live form on path and its trashed form
    # on origin_path: nine disjoint branches.
    assert sql.count("UNION ALL") == 8 and " UNION SELECT" not in sql
    assert sql.count("vfs_entries.everyone_level >= ") == 1 and sql.count("vfs_entries.everyone_level < ") == 8
    assert "vfs_entries.path = " in sql and "vfs_entries.path > " in sql and "vfs_entries.path < " in sql
    assert (
        "vfs_entries.origin_path = " in sql
        and "vfs_entries.origin_path > " in sql
        and "vfs_entries.origin_path < " in sql
    )
    assert sql.count("vfs_entries.origin_path IS NULL") == 4 and sql.count("vfs_entries.owner_id = ") == 4
    assert "LIKE" not in sql and "NOT EXISTS" not in sql


def test_sqlite_fences_the_visible_set_as_a_materialized_cte() -> None:
    # Joined as a plain subquery, SQLite pushes the outer table into every
    # branch and scans the ranges per row; the fence computes it once.
    sql = _render(Ranges(BOTH, ()), SQLITE, sqlite.dialect())
    assert sql.startswith(f"WITH {VISIBLE_ALIAS} AS MATERIALIZED \n(SELECT"), sql
    for profile, dialect, _ in SPELLINGS[1:]:
        other = _render(Ranges(BOTH, ()), profile, dialect)
        assert "MATERIALIZED" not in other and not other.startswith("WITH") and f"{VISIBLE_ALIAS}.entry_id" in other


def test_a_caller_without_pieces_is_the_everyone_branch_alone() -> None:
    sql = _render(Ranges(NONE, ()), POSTGRESQL, postgresql.dialect())
    assert "UNION" not in sql and "unnest" not in sql
    assert f"AS {VISIBLE_ALIAS}" in sql and "vfs_entries.everyone_level >= " in sql


def test_a_scope_narrows_every_branch_to_the_subtree() -> None:
    # Scoped away from the trash chain no trashed row can lie in the scope,
    # so only the live forms are sent: three branches, each in the range.
    sql = _render(Ranges(BOTH, (("ann", NONE),)), SQLITE, sqlite.dialect(), scope="/a")
    assert sql.count("vfs_entries.path > ? AND vfs_entries.path < ?") == 3 and "origin_path = " not in sql
    root = _render(Ranges(NONE, ()), SQLITE, sqlite.dialect(), scope="/")
    assert "vfs_entries.path > ? AND vfs_entries.path < ?" in root
    # The trash chain — the root, /.vfs, the trash root, anything beneath — carries both forms.
    for scope in ("/", "/.vfs", "/.vfs/trash", "/.vfs/trash/2026-10-03-12"):
        chained = _render(Ranges(BOTH, ()), SQLITE, sqlite.dialect(), scope=scope)
        assert chained.count("UNION ALL") == 4 and "vfs_entries.origin_path = " in chained, scope


def test_the_derived_hint_is_oracles_alone() -> None:
    hint = derived_hint(ORACLE, TABLES.lex_docs, "epoch", "entry_id")
    expected = (
        "/*+ NO_MERGE(visible) LEADING(visible) USE_NL(vfs_lex_docs) INDEX(vfs_lex_docs ix_vfs_lex_docs_entry) */"
    )
    assert hint == expected
    assert all(
        derived_hint(p, TABLES.lex_docs, "epoch", "entry_id") is None
        for p in (SQLITE, POSTGRESQL, MSSQL, MARIADB, GENERIC)
    )


# ---------------------------------------------------------------------------
# The in-flight holes
# ---------------------------------------------------------------------------


HOLE = Pieces(("/h",), (("/h/", "/h0"),))


@pytest.mark.parametrize(("profile", "dialect"), [(s[0], s[1]) for s in SPELLINGS], ids=[s[0].name for s in SPELLINGS])
def test_a_hole_excludes_the_everyone_leg_and_rides_the_spans_and_owner(
    profile: DialectProfile, dialect: Dialect
) -> None:
    # A posture row in flight: the everyone branch excludes the hole through
    # a NOT EXISTS over its unpacked pieces, and the spans' and owner arm's
    # parts inside it ride as branches admitted whatever the label says.
    ranges = Ranges(BOTH, (("ann", BOTH),), HOLE, Pieces(("/h/s",), ()), (("ann", Pieces((), (("/h/", "/h0"),))),))
    sql = _render(ranges, profile, dialect)
    assert "NOT EXISTS" in sql or "NOT (EXISTS" in sql
    # Everyone (minus the hole, judged on path or origin), then two arm
    # kinds, one holed-arm point, two owner kinds and one holed-owner range
    # in each of the two forms: thirteen branches joined disjoint.
    assert sql.count("UNION ALL") == 12 and " UNION SELECT" not in sql
    assert "vfs_entries.origin_path IS NOT NULL" in sql and sql.count("vfs_entries.origin_path IS NULL") == 7


def test_no_hole_keeps_the_predicate_simple_and_true() -> None:
    assert isinstance(hole_free(ENTRY.c.path, NONE, SQLITE), True_)
    sql = _render(Ranges(BOTH, ()), SQLITE, sqlite.dialect())
    assert "NOT EXISTS" not in sql


def test_the_generic_floor_spells_the_hole_as_a_literal_negation() -> None:
    clause = hole_free(ENTRY.c.path, HOLE, GENERIC)
    sql = str(clause.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "NOT (" in sql and "vfs_entries.path = '/h'" in sql and "'/h/'" in sql and "EXISTS" not in sql


def test_range_counts_groups_each_range_by_its_bounds() -> None:
    sql = str(range_counts(ENTRY, [("/a/", "/a0"), ("/b/", "/b0")], POSTGRESQL).compile(dialect=postgresql.dialect()))
    assert "count(" in sql and "GROUP BY" in sql and "unnest(" in sql
