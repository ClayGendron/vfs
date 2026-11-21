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

A deleted row stays at its path with a tombstone, so it is judged
exactly as a live one: one form per piece branch, on ``path``. The
statement that joins the visible set carries the liveness term itself.

Each engine's planner misreads the extra term in its own way, so the
join keyword between the unpacked ranges and the entry table is a
dialect fact
(:class:`~vfs.storage.backends.database.dialects.DialectProfile`).
Statements that read chunk-side tables join the result as a derived
table on ``entry_id``; ``entry_id IN (...)`` over the same union was
measured to plan badly, so it is not offered.

    visible = visible_entries(entry, rights.ranges(), rights.need, profile)
    stmt = select(func.count()).select_from(docs.join(visible, visible.c.entry_id == docs.c.entry_id))
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    Text,
    and_,
    bindparam,
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
from sqlalchemy.sql.visitors import InternalTraversal

from vfs.paths import ROOT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import CTE, Column, ColumnElement, FromClause, Select, Subquery, Table
    from sqlalchemy.sql.compiler import SQLCompiler

    from vfs.storage.backends.database.dialects import DialectProfile, RangeSource
    from vfs.storage.grants import Open, Pieces, Ranges, Rank

VISIBLE_ALIAS = "visible"
"""The derived table's name in rendered SQL; its one column is ``entry_id``."""

# The unpacked pieces' aliases: fixed, so the statement text never changes with the grants.
_POINTS_ALIAS = "pts"
_OPENS_ALIAS = "rng"


# ---------------------------------------------------------------------------
# The visible entries
# ---------------------------------------------------------------------------


def visible_entries(
    entry: Table, ranges: Ranges, need: Rank, profile: DialectProfile, scope: str | None = None
) -> Subquery | CTE:
    """The ``entry_id`` of every row the caller may see at level *need*, as a derived table.

    Branch one is the everyone leg; then one branch per piece kind of
    the caller's own pieces, and the same per owner arm under
    ``owner_id = owner`` — every branch disjoint, merged by ``UNION ALL``.
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
    unholed = hole_free(entry.c.path, ranges.holes, profile)
    everyone = select(entry.c.entry_id).where(entry.c.everyone_level >= need, unholed, *within)
    column = entry.c.path
    below = [entry.c.everyone_level < need, *within]
    holed = [entry.c.everyone_level >= need, *within]
    branches = [everyone]
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


def range_counts(entry: Table, opens: Sequence[Open], profile: DialectProfile) -> Select[Any]:
    """``(lo, hi, rows)`` for every open range of *opens* — the ranges drive, one seek each.

    A relabel sizes its chunks from this before it writes.
    """
    source = profile.range_source
    assert source is not None, "the generic floor counts one range at a time"
    rows, lo, hi = open_rows(opens, source)
    on = and_(entry.c.path > lo, entry.c.path < hi)
    stmt = _range_select(entry, rows, on, profile, lo, hi, func.count())
    return stmt.group_by(lo, hi)


# ---------------------------------------------------------------------------
# Table functions and the join keyword the compilers do not spell
# ---------------------------------------------------------------------------


class _RangeJoin(Join):
    """A join whose keyword the profile declares — ``CROSS JOIN`` on SQLite, ``JOIN`` elsewhere."""

    # The keyword joins the cache key: two profiles on one dialect never share a compiled statement.
    _traverse_internals = [*Join._traverse_internals, ("keyword", InternalTraversal.dp_string)]  # noqa: RUF012

    def __init__(self, left: FromClause, right: FromClause, onclause: ColumnElement[bool], keyword: str) -> None:
        super().__init__(left, right, onclause)
        self.keyword = keyword


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
    rows = func.json_each(json.dumps(list(points))).table_valued("value", name=_POINTS_ALIAS)
    return rows, rows.c.value


def open_rows(opens: Sequence[Open], source: RangeSource) -> tuple[FromClause, ColumnElement[Any], ColumnElement[Any]]:
    """*opens* as rows from one bind (two on Postgres), and the columns holding each bound."""
    if source == "unnest":
        lows = bindparam(None, [lo for lo, _ in opens], type_=ARRAY(Text))
        highs = bindparam(None, [hi for _, hi in opens], type_=ARRAY(Text))
        rows = func.unnest(lows, highs).table_valued("lo", "hi", name=_OPENS_ALIAS).render_derived()
        return rows, collate(rows.c.lo, "C"), collate(rows.c.hi, "C")
    rows = func.json_each(json.dumps([list(pair) for pair in opens])).table_valued("value", name=_OPENS_ALIAS)
    return rows, func.json_extract(rows.c.value, "$[0]"), func.json_extract(rows.c.value, "$[1]")


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
    kinds: list[tuple[FromClause, ColumnElement[bool]]] = []
    if found.points:
        rows, value = point_rows(found.points, source)
        kinds.append((rows, column == value))
    if found.opens:
        rows, lo, hi = open_rows(found.opens, source)
        kinds.append((rows, and_(column > lo, column < hi)))
    return [_range_select(entry, rows, and_(on, *extra), profile, entry.c.entry_id) for rows, on in kinds]


def pinned_join(left: FromClause, right: FromClause, on: ColumnElement[bool], profile: DialectProfile) -> Join:
    """*left* joined to *right* on *on* in the profile's declared keyword — the plan pin every seek join carries.

    The ranges join and the graph walk's hop share it: both drive a seek
    of an index from a small left side, and a plain ``JOIN`` let SQLite
    plan the probe from the wrong table. No hint rides it; the callers
    that need one add it to the statement.
    """
    return _RangeJoin(left, right, on, profile.range_join)


def _range_select(
    entry: Table, rows: FromClause, on: ColumnElement[bool], profile: DialectProfile, *columns: ColumnElement[Any]
) -> Select[Any]:
    """``SELECT columns`` from the unpacked *rows* joined to *entry* on *on*, in the profile's keyword."""
    return select(*columns).select_from(pinned_join(rows, entry, on, profile))


def _scoped(entry: Table, scope: str | None) -> list[ColumnElement[bool]]:
    """The strict descendants of *scope* as a path range, or nothing."""
    if scope is None:
        return []
    lo, hi = (ROOT, "0") if scope == ROOT else (scope + "/", scope + "0")
    return [entry.c.path > lo, entry.c.path < hi]
