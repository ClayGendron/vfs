"""Membership predicates — the profile's form, rendered per dialect.

The ``IN`` list is every compiler's default; SQL Server takes a
``VALUES`` derived table with the keys cast once, server-side, into the
column's collation, and its guard reads join that table under the
seek-forcing lock hint. These pins hold the rendered SQL, not the
engine's plan — the plan and lock profile are pinned on the mssql leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.dialects import mssql as mssql_dialect
from sqlalchemy.dialects import postgresql as postgresql_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect

from vfs.models.rows import MSSQL_UTF8_COLLATION, BytewiseString, ULIDKey
from vfs.storage.backends.database.dialects import MSSQL, POSTGRESQL, SQLITE, DialectProfile
from vfs.storage.backends.database.membership import locked_lookup, membership

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect
    from sqlalchemy.sql import ClauseElement

_ENTRY = Table(
    "entry",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("entry_id", ULIDKey()),
    Column("path", BytewiseString(1024)),
    Column("kind", String(16)),
)
_KEYS = ["/a", "/b"]


def _sql(clause: ClauseElement, dialect: Dialect) -> str:
    return " ".join(str(clause.compile(dialect=dialect)).split())


class TestMembership:
    @pytest.mark.parametrize(
        ("profile", "dialect"),
        [(SQLITE, sqlite_dialect.dialect()), (POSTGRESQL, postgresql_dialect.dialect())],
        ids=["sqlite", "postgresql"],
    )
    def test_the_in_list_is_the_default_form(self, profile: DialectProfile, dialect: Dialect) -> None:
        sql = _sql(select(_ENTRY.c.id).where(membership(_ENTRY.c.path, _KEYS, profile)), dialect)
        assert sql.endswith("WHERE entry.path IN (__[POSTCOMPILE_path_1])")
        assert "VALUES" not in sql

    def test_mssql_string_keys_join_a_values_table_cast_through_the_utf8_collation(self) -> None:
        sql = _sql(select(_ENTRY.c.id).where(membership(_ENTRY.c.path, _KEYS, MSSQL)), mssql_dialect.dialect())
        assert f"entry.path IN (SELECT CAST(keys.v COLLATE {MSSQL_UTF8_COLLATION} AS VARCHAR(1024))" in sql
        assert "FROM (VALUES (:param_1), (:param_2)) AS keys (v)" in sql

    def test_mssql_plain_string_columns_take_the_same_cast_at_their_own_length(self) -> None:
        sql = _sql(select(_ENTRY.c.id).where(membership(_ENTRY.c.kind, ["file"], MSSQL)), mssql_dialect.dialect())
        assert f"CAST(keys.v COLLATE {MSSQL_UTF8_COLLATION} AS VARCHAR(16))" in sql

    @pytest.mark.parametrize("target", [_ENTRY.c.entry_id, _ENTRY.c.id], ids=["ulid", "integer"])
    def test_mssql_binary_and_integer_keys_join_uncast(self, target: Column[object]) -> None:
        keys = ["01ARZ3NDEKTSV4RRFFQ69G5FAV"] if target is _ENTRY.c.entry_id else [1]
        sql = _sql(select(_ENTRY.c.path).where(membership(target, keys, MSSQL)), mssql_dialect.dialect())
        assert "IN (SELECT keys.v FROM (VALUES (:param_1)) AS keys (v))" in sql
        assert "CAST" not in sql

    def test_the_predicate_composes_with_other_where_terms(self) -> None:
        stmt = select(_ENTRY.c.id).where(membership(_ENTRY.c.path, _KEYS, MSSQL), _ENTRY.c.kind == "file")
        sql = _sql(stmt, mssql_dialect.dialect())
        assert "AS keys (v)) AND entry.kind = :kind_1" in sql


class TestLockedLookup:
    def test_postgresql_locks_the_in_list_read_for_update(self) -> None:
        stmt = locked_lookup(_ENTRY, _ENTRY.c.path, _KEYS, [_ENTRY.c.path, _ENTRY.c.id], POSTGRESQL)
        sql = _sql(stmt, postgresql_dialect.dialect())
        assert sql == "SELECT entry.path, entry.id FROM entry WHERE entry.path IN (__[POSTCOMPILE_path_1]) FOR UPDATE"

    def test_sqlite_renders_the_plain_read_the_writer_transaction_is_the_lock(self) -> None:
        stmt = locked_lookup(_ENTRY, _ENTRY.c.path, _KEYS, [_ENTRY.c.path], SQLITE)
        assert (
            _sql(stmt, sqlite_dialect.dialect())
            == "SELECT entry.path FROM entry WHERE entry.path IN (__[POSTCOMPILE_path_1])"
        )

    def test_mssql_joins_the_values_table_under_the_seek_forcing_lock_hint(self) -> None:
        # The IN shapes refuse FORCESEEK; only the join lets the locking
        # read seek, which is what keeps the lock at key granularity.
        stmt = locked_lookup(_ENTRY, _ENTRY.c.path, _KEYS, [_ENTRY.c.path, _ENTRY.c.entry_id], MSSQL)
        sql = _sql(stmt, mssql_dialect.dialect())
        assert sql == (
            "SELECT entry.path, entry.entry_id FROM (VALUES (:param_1), (:param_2)) AS keys (v) "
            "JOIN entry WITH (UPDLOCK, FORCESEEK) "
            f"ON entry.path = CAST(keys.v COLLATE {MSSQL_UTF8_COLLATION} AS VARCHAR(1024))"
        )

    def test_mssql_binary_keys_join_on_the_bare_column(self) -> None:
        stmt = locked_lookup(_ENTRY, _ENTRY.c.entry_id, ["01ARZ3NDEKTSV4RRFFQ69G5FAV"], [_ENTRY.c.path], MSSQL)
        assert "JOIN entry WITH (UPDLOCK, FORCESEEK) ON entry.entry_id = keys.v" in _sql(stmt, mssql_dialect.dialect())
