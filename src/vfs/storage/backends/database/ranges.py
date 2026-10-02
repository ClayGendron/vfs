"""The range join — a partial caller's visible entries in one statement, for any number of grants.

:meth:`~vfs.storage.grants.Rights.ranges` turns a caller's rights into
sorted, disjoint pieces: exact paths and open ranges. Each kind travels
as one bound value, unpacked into rows by the dialect's table function
and joined to the ``path`` index — one index seek per piece, and
statement text that never changes with the caller's grants. Each owner
arm is its own ``UNION`` branch through ``owner_id``; inside the range
join's ``ON`` it would block the seeks.

Statements that read chunk-side tables join the result as a derived
table on ``entry_id``. ``entry_id IN (...)`` over the same ``UNION``
plans badly on some engines (seconds on MariaDB), so it is not offered.

    visible = visible_entries(entry, rights.ranges(), "json_each")
    stmt = select(func.count()).select_from(docs.join(visible, visible.c.entry_id == docs.c.entry_id))
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import ARRAY, LargeBinary, String, Text, and_, bindparam, cast, collate, false, func, select, union
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from vfs.models.rows import MSSQL_UTF8_COLLATION
from vfs.paths import MAX_PATH_LENGTH

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, FromClause, Select, Subquery, Table
    from sqlalchemy.sql.compiler import SQLCompiler

    from vfs.storage.backends.database.dialects import RangeSource
    from vfs.storage.grants import Pieces, Ranges

VISIBLE_ALIAS = "visible"
"""The derived table's name in rendered SQL; its one column is ``entry_id``."""

# Bound rows are typed this wide: no lawful path is longer in bytes, nor in characters.
_BOUND = f"({MAX_PATH_LENGTH})"


# ---------------------------------------------------------------------------
# The visible entries
# ---------------------------------------------------------------------------


def visible_entries(entry: Table, ranges: Ranges, source: RangeSource) -> Subquery:
    """The ``entry_id`` of every row *ranges* admit, as a derived table.

    One branch per piece kind, plus the same per owner arm under
    ``owner_id = owner``, merged by ``UNION`` — so an id appears once.
    No pieces at all is a derived table with no rows.
    """
    branches = _branches(entry, ranges.arms, source)
    for owner, found in ranges.owners:
        branches += [branch.where(entry.c.owner_id == owner) for branch in _branches(entry, found, source)]
    if not branches:
        return select(entry.c.entry_id).where(false()).subquery(VISIBLE_ALIAS)
    if len(branches) == 1:
        return branches[0].subquery(VISIBLE_ALIAS)
    return union(*branches).subquery(VISIBLE_ALIAS)


# ---------------------------------------------------------------------------
# Table functions the compilers do not spell
# ---------------------------------------------------------------------------


class _OpenJsonPairs(FunctionElement[Any]):
    """SQL Server: a JSON array of ``[lo, hi]`` pairs as rows of ``lo`` and ``hi``."""

    name = "openjson_pairs"
    inherit_cache = True


class _JsonTableValues(FunctionElement[Any]):
    """MariaDB: a JSON array of strings as rows of ``value``."""

    name = "json_table_values"
    inherit_cache = True


class _JsonTablePairs(FunctionElement[Any]):
    """MariaDB: a JSON array of ``[lo, hi]`` pairs as rows of ``lo`` and ``hi``."""

    name = "json_table_pairs"
    inherit_cache = True


@compiles(_OpenJsonPairs)
def _render_openjson_pairs(element: _OpenJsonPairs, compiler: SQLCompiler, **kw: Any) -> str:
    pairs = "lo nvarchar(max) '$[0]', hi nvarchar(max) '$[1]'"
    return f"OPENJSON({compiler.process(element.clauses, **kw)}) WITH ({pairs})"


@compiles(_JsonTableValues)
def _render_json_table_values(element: _JsonTableValues, compiler: SQLCompiler, **kw: Any) -> str:
    return f"JSON_TABLE({compiler.process(element.clauses, **kw)}, '$[*]' COLUMNS (value VARCHAR{_BOUND} PATH '$'))"


@compiles(_JsonTablePairs)
def _render_json_table_pairs(element: _JsonTablePairs, compiler: SQLCompiler, **kw: Any) -> str:
    pairs = f"lo VARCHAR{_BOUND} PATH '$[0]', hi VARCHAR{_BOUND} PATH '$[1]'"
    return f"JSON_TABLE({compiler.process(element.clauses, **kw)}, '$[*]' COLUMNS ({pairs}))"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _branches(entry: Table, found: Pieces, source: RangeSource) -> list[Select[Any]]:
    """One ``SELECT entry_id`` per non-empty piece kind, each joined to the ``path`` index."""
    out: list[Select[Any]] = []
    if found.points:
        rows, value = _point_rows(found.points, source)
        out.append(select(entry.c.entry_id).select_from(rows).join(entry, entry.c.path == value))
    if found.opens:
        rows, lo, hi = _open_rows(found.opens, source)
        out.append(select(entry.c.entry_id).select_from(rows).join(entry, and_(entry.c.path > lo, entry.c.path < hi)))
    return out


def _point_rows(points: Sequence[str], source: RangeSource) -> tuple[FromClause, ColumnElement[Any]]:
    """*points* as rows from one bind, and the column holding each path."""
    if source == "unnest":
        rows = func.unnest(bindparam(None, list(points), type_=ARRAY(Text))).table_valued("value").render_derived()
        return rows, collate(rows.c.value, "C")
    value = json.dumps(list(points))
    if source == "json_each":
        rows = func.json_each(value).table_valued("value")
        return rows, rows.c.value
    if source == "openjson":
        rows = func.openjson(value).table_valued("value")
        return rows, _utf8(rows.c.value)
    rows = _JsonTableValues(value).table_valued("value")
    return rows, cast(rows.c.value, LargeBinary)


def _open_rows(
    opens: Sequence[tuple[str, str]], source: RangeSource
) -> tuple[FromClause, ColumnElement[Any], ColumnElement[Any]]:
    """*opens* as rows from one bind (two on Postgres), and the columns holding each bound."""
    if source == "unnest":
        lows = bindparam(None, [lo for lo, _ in opens], type_=ARRAY(Text))
        highs = bindparam(None, [hi for _, hi in opens], type_=ARRAY(Text))
        rows = func.unnest(lows, highs).table_valued("lo", "hi").render_derived()
        return rows, collate(rows.c.lo, "C"), collate(rows.c.hi, "C")
    value = json.dumps([list(pair) for pair in opens])
    if source == "json_each":
        rows = func.json_each(value).table_valued("value")
        return rows, func.json_extract(rows.c.value, "$[0]"), func.json_extract(rows.c.value, "$[1]")
    if source == "openjson":
        rows = _OpenJsonPairs(value).table_valued("lo", "hi")
        return rows, _utf8(rows.c.lo), _utf8(rows.c.hi)
    rows = _JsonTablePairs(value).table_valued("lo", "hi")
    return rows, cast(rows.c.lo, LargeBinary), cast(rows.c.hi, LargeBinary)


def _utf8(column: ColumnElement[Any]) -> ColumnElement[Any]:
    """An ``nvarchar`` bound cast into the path column's type through its UTF-8 collation.

    Casting after the collation keeps non-Latin paths intact and lets
    the comparison seek the ``varchar`` path index.
    """
    return cast(collate(column, MSSQL_UTF8_COLLATION), String(MAX_PATH_LENGTH))
