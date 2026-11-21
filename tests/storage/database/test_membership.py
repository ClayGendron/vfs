"""Membership predicates — the expanding ``IN`` list, rendered per dialect.

The ``IN`` list is the one form on both engines and the generic floor,
and a guard read takes the same list under ``FOR UPDATE``. These pins
hold the rendered SQL, not the engine's plan.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.dialects import postgresql as postgresql_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect

from vfs.models.rows import BytewiseString, ULIDKey
from vfs.storage.backends.database.dialects import GENERIC, POSTGRESQL, SQLITE, DialectProfile
from vfs.storage.backends.database.membership import live_chunks, locked_lookup, membership

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
        [
            (SQLITE, sqlite_dialect.dialect()),
            (POSTGRESQL, postgresql_dialect.dialect()),
            (GENERIC, postgresql_dialect.dialect()),
        ],
        ids=["sqlite", "postgresql", "generic"],
    )
    def test_the_in_list_is_the_default_form(self, profile: DialectProfile, dialect: Dialect) -> None:
        sql = _sql(select(_ENTRY.c.id).where(membership(_ENTRY.c.path, _KEYS, profile)), dialect)
        assert sql.endswith("WHERE entry.path IN (__[POSTCOMPILE_path_1])")
        assert "VALUES" not in sql

    def test_the_predicate_composes_with_other_where_terms(self) -> None:
        stmt = select(_ENTRY.c.id).where(membership(_ENTRY.c.path, _KEYS, POSTGRESQL), _ENTRY.c.kind == "file")
        sql = _sql(stmt, postgresql_dialect.dialect())
        assert "IN (__[POSTCOMPILE_path_1]) AND entry.kind = %(kind_1)s" in sql


class TestLockedLookup:
    def test_postgresql_locks_the_in_list_read_for_update(self) -> None:
        stmt = locked_lookup(_ENTRY.c.path, _KEYS, [_ENTRY.c.path, _ENTRY.c.id], POSTGRESQL)
        sql = _sql(stmt, postgresql_dialect.dialect())
        assert sql == "SELECT entry.path, entry.id FROM entry WHERE entry.path IN (__[POSTCOMPILE_path_1]) FOR UPDATE"

    def test_sqlite_renders_the_plain_read_the_writer_transaction_is_the_lock(self) -> None:
        stmt = locked_lookup(_ENTRY.c.path, _KEYS, [_ENTRY.c.path], SQLITE)
        assert (
            _sql(stmt, sqlite_dialect.dialect())
            == "SELECT entry.path FROM entry WHERE entry.path IN (__[POSTCOMPILE_path_1])"
        )


def test_live_chunks_splits_the_budget_in_half() -> None:
    """Guards: the epoch slice put back at ``budget - 1``, so a long live set leaves one key a statement."""
    keys = list(range(5_000))
    pairs = list(live_chunks(range(1_440), keys, 1_000))
    assert len(pairs) == 29
    assert [len(epochs) for epochs, _keys in pairs[::10]] == [500, 500, 440]
    assert Counter(len(epochs) for epochs, _keys in pairs) == Counter({500: 20, 440: 9})
    assert all(len(epochs) <= 500 and len(epochs) + len(probe) <= 1_000 for epochs, probe in pairs)
    assert len(list(live_chunks(range(96), keys, 1_000))) == 6
