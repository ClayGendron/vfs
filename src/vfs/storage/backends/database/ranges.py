"""The three-seek predicate — a partial caller's visible entries in one statement, for any number of grants.

Visibility has three sources, each one index seek: the everyone level
on the row (``everyone_level >= :r`` through the ``(everyone_level,
path)`` index), the caller's own grants as sorted path pieces joined to
the ``path`` index (:meth:`~vfs.storage.grants.Rights.ranges`: exact
paths and open ranges, each kind one bound value unpacked by the
dialect's table function), and per member the rows it owns under its
owner pieces, through ``owner_id``. The branches are disjoint by
construction — the range and owner branches carry ``everyone_level <
:r``, and the owner pieces exclude the caller's own — so they merge by
``UNION ALL`` and no engine plans a deduplication. The statement text
never changes with the caller's grants.

While a posture row's relabel is in flight, the labels inside the
region it rewrites cannot be trusted, and the caller's rights carry it
as a hole (:attr:`~vfs.storage.grants.Ranges.holes`): the everyone leg
excludes the hole through the same unpacked pieces, and the parts of
the caller's own pieces and owner pieces that lie in it ride as two
more branches, admitted whatever the label says. The branches stay
disjoint, and the hole is one bound value like every other piece set.

A trashed row is judged by its origin, so every piece branch comes in
two forms: the live form joins the pieces to ``path`` and keeps only
rows with no origin (``origin_path IS NULL``, no bind); the trashed
form joins the same pieces to ``origin_path`` through its own index,
which holds the trashed rows alone. The two are disjoint by that
column, so the union stays ``UNION ALL``. A read scoped outside the
trash chain can hold no trashed row and sends the live forms only.

Each engine's planner misreads the extra term in its own way, so the
join keyword between the unpacked ranges and the entry table, the
index pin, and the optimizer hints are dialect facts
(:class:`~vfs.storage.backends.database.dialects.DialectProfile`); the
spellings here follow the five-engine measurement. Statements that read
chunk-side tables join the result as a derived table on ``entry_id``.
``entry_id IN (...)`` over the same union plans badly on some engines
(seconds on MariaDB), so it is not offered.

    visible = visible_entries(entry, rights.ranges(), rights.need, profile)
    stmt = select(func.count()).select_from(docs.join(visible, visible.c.entry_id == docs.c.entry_id))
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    CLOB,
    LargeBinary,
    String,
    Text,
    and_,
    bindparam,
    cast,
    collate,
    func,
    literal,
    not_,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import Join
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.sql.visitors import InternalTraversal

from vfs.models.rows import MSSQL_UTF8_COLLATION
from vfs.paths import MAX_PATH_LENGTH, ROOT, on_trash_chain

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import CTE, Column, ColumnElement, FromClause, Select, Subquery, Table
    from sqlalchemy.sql.compiler import SQLCompiler

    from vfs.storage.backends.database.dialects import DialectProfile, RangeSource
    from vfs.storage.grants import Pieces, Ranges

VISIBLE_ALIAS = "visible"
"""The derived table's name in rendered SQL; its one column is ``entry_id``."""

# Bound rows are typed this wide: no lawful path is longer in bytes, nor in characters.
_BOUND = f"({MAX_PATH_LENGTH})"

# The unpacked pieces' aliases: fixed, so a hint can name them.
_POINTS_ALIAS = "pts"
_OPENS_ALIAS = "rng"


# ---------------------------------------------------------------------------
# The visible entries
# ---------------------------------------------------------------------------


def visible_entries(
    entry: Table, ranges: Ranges, need: int, profile: DialectProfile, scope: str | None = None
) -> Subquery | CTE:
    """The ``entry_id`` of every row the caller may see at level *need*, as a derived table.

    Branch one is the everyone leg; then one branch per piece kind of
    the caller's own pieces, and the same per owner arm under
    ``owner_id = owner`` — each in its live form on ``path`` and, where
    a trashed row may lie in the scope, its trashed form on
    ``origin_path``; every branch disjoint, merged by ``UNION ALL``.
    *scope* narrows every branch to the strict descendants of that path,
    so a subtree read seeks the composite index once instead of walking
    every row everyone may see. Where the profile declares a fence, the
    union is a common table expression under that prefix, so the
    statement joining it computes it once instead of pushing its own
    table into every branch.
    """
    source = profile.range_source
    assert source is not None, "the clause fan serves a dialect without a range source"
    within = _scoped(entry, scope)
    unholed = judged_hole_free(entry, ranges.holes, profile)
    everyone = select(entry.c.entry_id).where(entry.c.everyone_level >= need, unholed, *within)
    hint = profile.range_hints.everyone
    if hint:
        everyone = everyone.prefix_with(
            hint.format(entry=entry.name, index=_index_name(entry, "everyone_level", "path")), dialect=profile.name
        )
    columns = [entry.c.path] if scope is not None and not on_trash_chain(scope) else [entry.c.path, entry.c.origin_path]
    branches = [everyone]
    for column in columns:
        live = [entry.c.origin_path.is_(None)] if column is entry.c.path else []
        below = [*live, entry.c.everyone_level < need, *within]
        holed = [*live, entry.c.everyone_level >= need, *within]
        branches += _branches(entry, column, ranges.arms, profile, below)
        branches += _branches(entry, column, ranges.holed_arms, profile, holed)
        for owner, found in ranges.owners:
            branches += _branches(entry, column, found, profile, [entry.c.owner_id == owner, *below])
        for owner, found in ranges.holed_owners:
            branches += _branches(entry, column, found, profile, [entry.c.owner_id == owner, *holed])
    visible = union_all(*branches)
    if profile.range_fence is None:
        return visible.subquery(VISIBLE_ALIAS)
    return visible.cte(VISIBLE_ALIAS).prefix_with(profile.range_fence, dialect=profile.name)


def judged_hole_free(entry: FromClause, holes: Pieces, profile: DialectProfile) -> ColumnElement[bool]:
    """The row's judged path lies in none of *holes* — ``path`` for a live row, ``origin_path`` for a trashed one.

    True outright when there are no holes, so the no-hole statement is
    the measured one.
    """
    if not holes.points and not holes.opens:
        return true()
    live = and_(entry.c.origin_path.is_(None), hole_free(entry.c.path, holes, profile))
    trashed = and_(entry.c.origin_path.is_not(None), hole_free(entry.c.origin_path, holes, profile))
    return or_(live, trashed)


def hole_free(path: ColumnElement[Any], holes: Pieces, profile: DialectProfile) -> ColumnElement[bool]:
    """``path`` lies in none of *holes* — true outright when there are none.

    Through a range source the hole is one bound value and the test is a
    ``NOT EXISTS`` over its unpacked pieces; the generic floor spells the
    literal negation, which the number of pieces bounds.
    """
    if not holes.points and not holes.opens:
        return true()
    source = profile.range_source
    if source is None:
        points = [path == point for point in holes.points]
        opens = [and_(path > lo, path < hi) for lo, hi in holes.opens]
        return not_(or_(*points, *opens))
    terms: list[ColumnElement[bool]] = []
    if holes.points:
        rows, value = point_rows(holes.points, source)
        terms.append(not_(select(literal(1)).select_from(rows).where(path == value).exists()))
    if holes.opens:
        rows, lo, hi = open_rows(holes.opens, source)
        terms.append(not_(select(literal(1)).select_from(rows).where(path > lo, path < hi).exists()))
    return and_(*terms)


def range_counts(entry: Table, opens: Sequence[tuple[str, str]], profile: DialectProfile) -> Select[Any]:
    """``(lo, hi, rows)`` for every open range of *opens* — the ranges drive, one seek each.

    A relabel sizes its chunks from this before it writes. The bounds
    come back in the range source's own form, so a mysql-family caller
    reads bytes.
    """
    source = profile.range_source
    assert source is not None, "the generic floor counts one range at a time"
    rows, lo, hi = open_rows(opens, source)
    on = and_(entry.c.path > lo, entry.c.path < hi)
    stmt = _range_select(entry, rows, on, profile, _OPENS_ALIAS, len(opens), lo, hi, func.count())
    return stmt.group_by(lo, hi)


def derived_hint(profile: DialectProfile, table: Table, *columns: str) -> str | None:
    """The hint a statement joining the visible set to *table* on its index over *columns* carries, if needed."""
    template = profile.range_hints.derived
    if not template:
        return None
    return template.format(visible=VISIBLE_ALIAS, table=table.name, index=_index_name(table, *columns))


# ---------------------------------------------------------------------------
# Table functions and the join keyword the compilers do not spell
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


class _JsonTableClobValues(FunctionElement[Any]):
    """Oracle: a JSON array of strings, bound as a CLOB, as rows of ``value``."""

    name = "json_table_clob_values"
    inherit_cache = True


class _JsonTableClobPairs(FunctionElement[Any]):
    """Oracle: a JSON array of ``[lo, hi]`` pairs, bound as a CLOB, as rows of ``lo`` and ``hi``."""

    name = "json_table_clob_pairs"
    inherit_cache = True


class _RangeJoin(Join):
    """A join whose keyword the profile declares — ``CROSS JOIN``, ``STRAIGHT_JOIN``, ``INNER LOOP JOIN``."""

    # The keyword joins the cache key: two profiles on one dialect never share a compiled statement.
    _traverse_internals = [*Join._traverse_internals, ("keyword", InternalTraversal.dp_string)]  # noqa: RUF012

    def __init__(self, left: FromClause, right: FromClause, onclause: ColumnElement[bool], keyword: str) -> None:
        super().__init__(left, right, onclause)
        self.keyword = keyword


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


@compiles(_JsonTableClobValues)
def _render_json_table_clob_values(element: _JsonTableClobValues, compiler: SQLCompiler, **kw: Any) -> str:
    columns = f"COLUMNS (value VARCHAR2{_BOUND} PATH '$')"
    return f"JSON_TABLE({compiler.process(element.clauses, **kw)}, '$[*]' {columns})"


@compiles(_JsonTableClobPairs)
def _render_json_table_clob_pairs(element: _JsonTableClobPairs, compiler: SQLCompiler, **kw: Any) -> str:
    pairs = f"lo VARCHAR2{_BOUND} PATH '$[0]', hi VARCHAR2{_BOUND} PATH '$[1]'"
    return f"JSON_TABLE({compiler.process(element.clauses, **kw)}, '$[*]' COLUMNS ({pairs}))"


@compiles(_RangeJoin)
def _render_range_join(element: _RangeJoin, compiler: SQLCompiler, **kw: Any) -> str:
    froms = {**kw, "asfrom": True}
    rest = {key: value for key, value in kw.items() if key != "asfrom"}
    left, right = compiler.process(element.left, **froms), compiler.process(element.right, **froms)
    assert element.onclause is not None
    return f"{left} {element.keyword} {right} ON {compiler.process(element.onclause, **rest)}"


# ---------------------------------------------------------------------------
# The range-source rows
# ---------------------------------------------------------------------------


def point_rows(points: Sequence[str], source: RangeSource) -> tuple[FromClause, ColumnElement[Any]]:
    """*points* as rows from one bind, and the column holding each path."""
    if source == "unnest":
        unpacked = func.unnest(bindparam(None, list(points), type_=ARRAY(Text)))
        rows = unpacked.table_valued("value", name=_POINTS_ALIAS).render_derived()
        return rows, collate(rows.c.value, "C")
    value = json.dumps(list(points))
    if source == "json_each":
        rows = func.json_each(value).table_valued("value", name=_POINTS_ALIAS)
        return rows, rows.c.value
    if source == "openjson":
        rows = func.openjson(value).table_valued("value", name=_POINTS_ALIAS)
        return rows, _utf8(rows.c.value)
    if source == "json_table_clob":
        rows = _JsonTableClobValues(bindparam(None, value, type_=CLOB)).table_valued("value", name=_POINTS_ALIAS)
        return rows, rows.c.value
    rows = _JsonTableValues(value).table_valued("value", name=_POINTS_ALIAS)
    return rows, cast(rows.c.value, LargeBinary)


def open_rows(
    opens: Sequence[tuple[str, str]], source: RangeSource
) -> tuple[FromClause, ColumnElement[Any], ColumnElement[Any]]:
    """*opens* as rows from one bind (two on Postgres), and the columns holding each bound."""
    if source == "unnest":
        lows = bindparam(None, [lo for lo, _ in opens], type_=ARRAY(Text))
        highs = bindparam(None, [hi for _, hi in opens], type_=ARRAY(Text))
        rows = func.unnest(lows, highs).table_valued("lo", "hi", name=_OPENS_ALIAS).render_derived()
        return rows, collate(rows.c.lo, "C"), collate(rows.c.hi, "C")
    value = json.dumps([list(pair) for pair in opens])
    if source == "json_each":
        rows = func.json_each(value).table_valued("value", name=_OPENS_ALIAS)
        return rows, func.json_extract(rows.c.value, "$[0]"), func.json_extract(rows.c.value, "$[1]")
    if source == "openjson":
        rows = _OpenJsonPairs(value).table_valued("lo", "hi", name=_OPENS_ALIAS)
        return rows, _utf8(rows.c.lo), _utf8(rows.c.hi)
    if source == "json_table_clob":
        rows = _JsonTableClobPairs(bindparam(None, value, type_=CLOB)).table_valued("lo", "hi", name=_OPENS_ALIAS)
        return rows, rows.c.lo, rows.c.hi
    rows = _JsonTablePairs(value).table_valued("lo", "hi", name=_OPENS_ALIAS)
    return rows, cast(rows.c.lo, LargeBinary), cast(rows.c.hi, LargeBinary)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _branches(
    entry: Table,
    column: Column[Any],
    found: Pieces,
    profile: DialectProfile,
    extra: Sequence[ColumnElement[bool]],
) -> list[Select[Any]]:
    """One ``SELECT entry_id`` per non-empty piece kind, the unpacked pieces driving a seek of *column*'s index."""
    source = profile.range_source
    assert source is not None
    kinds: list[tuple[FromClause, ColumnElement[bool], str, int]] = []
    if found.points:
        rows, value = point_rows(found.points, source)
        kinds.append((rows, column == value, _POINTS_ALIAS, len(found.points)))
    if found.opens:
        rows, lo, hi = open_rows(found.opens, source)
        kinds.append((rows, and_(column > lo, column < hi), _OPENS_ALIAS, len(found.opens)))
    return [
        _range_select(entry, rows, and_(on, *extra), profile, alias, count, entry.c.entry_id, index=column.name)
        for rows, on, alias, count in kinds
    ]


def _range_select(
    entry: Table,
    rows: FromClause,
    on: ColumnElement[bool],
    profile: DialectProfile,
    alias: str,
    count: int,
    *columns: ColumnElement[Any],
    index: str = "path",
) -> Select[Any]:
    """``SELECT columns`` from the unpacked *rows* joined to *entry* on *on*, in the profile's keyword and hints.

    *index* names the entry column whose index the join seeks, for the
    dialects told which one to use.
    """
    joined = _RangeJoin(rows, entry, on, profile.range_join)
    stmt = select(*columns).select_from(joined)
    if profile.range_entry_hint is not None:
        hint = profile.range_entry_hint.format(index=_index_name(entry, index))
        stmt = stmt.with_hint(entry, hint, dialect_name=profile.name)
    if profile.range_hints.ranges:
        hint = profile.range_hints.ranges.format(source=alias, count=count)
        stmt = stmt.prefix_with(hint, dialect=profile.name)
    return stmt


def _scoped(entry: Table, scope: str | None) -> list[ColumnElement[bool]]:
    """The strict descendants of *scope* as a path range, or nothing."""
    if scope is None:
        return []
    lo, hi = (ROOT, "0") if scope == ROOT else (scope + "/", scope + "0")
    return [entry.c.path > lo, entry.c.path < hi]


def _index_name(table: Table, *columns: str) -> str:
    """The name of *table*'s index on exactly *columns* — the schema declares one for every key asked for."""
    found = next((i.name for i in table.indexes if tuple(c.name for c in i.columns) == columns), None)
    assert isinstance(found, str)
    return found


def _utf8(column: ColumnElement[Any]) -> ColumnElement[Any]:
    """An ``nvarchar`` bound cast into the path column's type through its UTF-8 collation.

    Casting after the collation keeps non-Latin paths intact and lets
    the comparison seek the ``varchar`` path index.
    """
    return cast(collate(column, MSSQL_UTF8_COLLATION), String(MAX_PATH_LENGTH))
