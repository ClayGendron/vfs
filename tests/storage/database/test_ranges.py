"""The range join's SQL, rendered per dialect without a server.

The engine legs run each spelling for real (the grants contract); these
pin the rendered shape on every leg's run, so a spelling that drifts —
a bound cast lost, a collation dropped — fails here too. Row-exact
parity on a live engine is ``test_rights.py``'s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mssql, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb

from vfs.models.rows import MSSQL_UTF8_COLLATION, build_vfs_tables
from vfs.storage.backends.database.ranges import VISIBLE_ALIAS, visible_entries
from vfs.storage.grants import Pieces, Ranges

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

    from vfs.storage.backends.database.dialects import RangeSource

ENTRY = build_vfs_tables(table_name="vfs").entry
BOTH = Pieces(("/a",), (("/a/", "/a0"),))

# Each source, its dialect, and fragments its rendering must hold.
SPELLINGS: list[tuple[RangeSource, Dialect, tuple[str, ...]]] = [
    ("json_each", sqlite.dialect(), ("json_each(", "json_extract(")),
    ("unnest", postgresql.dialect(), ("unnest(", "::TEXT[]", 'COLLATE "C"')),
    ("openjson", mssql.dialect(), ("openjson(", "OPENJSON(", "WITH (lo nvarchar(max)", MSSQL_UTF8_COLLATION)),
    ("json_table", mariadb.MariaDBDialect(), ("JSON_TABLE(", "COLUMNS (value VARCHAR", "AS BINARY")),
]


def _render(ranges: Ranges, source: RangeSource, dialect: Dialect) -> str:
    return str(select(visible_entries(ENTRY, ranges, source)).compile(dialect=dialect))


@pytest.mark.parametrize(("source", "dialect", "fragments"), SPELLINGS, ids=[s[0] for s in SPELLINGS])
def test_each_source_renders_its_spelling(source: RangeSource, dialect: Dialect, fragments: tuple[str, ...]) -> None:
    sql = _render(Ranges(BOTH, (("ann", BOTH),)), source, dialect)
    for fragment in fragments:
        assert fragment in sql
    # Two piece kinds, for the arms and for ann's owner arm: four branches.
    assert sql.count("UNION") == 3
    assert "vfs.path = " in sql and "vfs.path > " in sql and "vfs.path < " in sql
    assert "vfs.owner_id = " in sql


def test_one_piece_kind_is_one_branch_and_no_union() -> None:
    sql = _render(Ranges(Pieces(("/a",), ()), ()), "json_each", sqlite.dialect())
    assert "UNION" not in sql
    assert f"AS {VISIBLE_ALIAS}" in sql


def test_no_pieces_admit_no_row() -> None:
    sql = _render(Ranges(Pieces((), ()), ()), "json_each", sqlite.dialect())
    assert "json_each" not in sql
    assert "0 = 1" in sql or "false" in sql.lower()
