"""Membership predicates — one owner, spelled in the dialect's form.

Every chunked ``column IN (...)`` in the backend is built here, so a
per-engine finding about how a long key list plans lands in one place
instead of forty. The profile declares the form: the expanding bind
list every compiler renders, or a ``VALUES`` derived table of the keys
(SQL Server, where a long ``IN`` list plans as a clustered scan on small
tables and every ``nvarchar`` bind is converted against the ``varchar``
key — one non-Latin path makes the seek range swallow the table). The
derived table's keys are cast once, server-side, into the column's own
type and collation, so non-Latin keys survive the trip the driver's
own ``varchar`` typing would lose them on.

    for chunk in chunked(ids, membership_budget):
        stmt = select(entry.c.path).where(membership(entry.c.entry_id, chunk, profile))

A guard read — rows that must stay locked to commit — takes the
whole-statement form, because the locking read must *seek*: under the
derived table the optimizer will still scan a small table, and a scan
under ``UPDLOCK`` locks every row and escalates to a table lock. The
join lets the profile's lock hint force the seek; the ``IN`` shapes
refuse it.

    guard = locked_lookup(entry, entry.c.entry_id, chunk, [entry.c.entry_id, entry.c.path], profile)

One key list is built outside this module: a refresh's refusal probe
(``embed.pass_unembedded``) spells its hashes as casts to the column's
type, because SQL Server merge-joins the derived table against a scan
of the refusal table's key there, and it chunks them by the membership
budget like every list here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import String, cast, collate, column, func, select, values
from sqlalchemy.dialects import mssql

from vfs.models.rows import BytewiseString
from vfs.storage.backends.database.dialects import chunked, lock_rows

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy import Column, ColumnElement, Select, Table
    from sqlalchemy.sql.selectable import Values

    from vfs.storage.backends.database.dialects import DialectProfile

# The derived table's one column and its alias in the rendered SQL.
_KEY_COLUMN = "v"
_KEYS_ALIAS = "keys"
# The one engine the derived-table form serves, whose column types say which collation a key is cast through.
_MSSQL = mssql.dialect()


# ---------------------------------------------------------------------------
# Membership predicates and guard reads
# ---------------------------------------------------------------------------


def membership(target: Column[Any], keys: Sequence[Any], profile: DialectProfile) -> ColumnElement[bool]:
    """``target IN keys``, in the profile's form; *keys* is one chunk under the budget."""
    if profile.membership == "in_list":
        return target.in_(list(keys))
    rows = _key_rows(target, keys)
    return target.in_(select(_typed(rows, target)))


def rare(profile: DialectProfile, term: ColumnElement[bool]) -> ColumnElement[bool]:
    """*term* said to the planner as one few rows meet, where the profile names a hint; *term* itself elsewhere."""
    return term if profile.rarity_hint is None else getattr(func, profile.rarity_hint)(term)


def live_chunks(epochs: Sequence[int], keys: Sequence[Any], budget: int) -> Iterator[tuple[Sequence[int], Sequence]]:
    """One *budget* split between a live set and a key list: each ``(epoch slice, key slice)`` pair, in order.

    An epoch slice holds at most half the budget, so half always fits the
    keys beside it, and its key slices take what remains; nothing for an
    empty set or no keys. A statement spends its ``epoch IN`` and its key
    ``IN`` from the one budget, whatever the number of live segments.
    """
    for epoch_slice in chunked(epochs, max(1, budget // 2)):
        for key_slice in chunked(keys, budget - len(epoch_slice)):
            yield epoch_slice, key_slice


def locked_lookup(
    table: Table, key: Column[Any], keys: Sequence[Any], columns: Sequence[Column[Any]], profile: DialectProfile
) -> Select[Any]:
    """``SELECT columns FROM table WHERE key IN keys``, rows locked to the transaction's end.

    The guard shape every liveness proof rests on: the rows come back
    locked, so the caller's decision stands on what it read. Chunk
    *keys* under the budget and sort them, so rival guards lock in one
    order.
    """
    if profile.membership == "in_list":
        return lock_rows(select(*columns).where(key.in_(list(keys))), table, profile)
    rows = _key_rows(key, keys)
    return lock_rows(select(*columns).select_from(rows.join(table, key == _typed(rows, key))), table, profile)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _key_rows(target: Column[Any], keys: Sequence[Any]) -> Values:
    """The keys as a ``VALUES`` derived table, bound through the target's own type."""
    return values(column(_KEY_COLUMN, target.type), name=_KEYS_ALIAS).data([(key,) for key in keys])


def _typed(rows: Values, target: Column[Any]) -> ColumnElement[Any]:
    """The key column cast to the target's type where the bind's type differs from it.

    String keys arrive as ``nvarchar``; each is cast to the column's own
    ``varchar`` length through the collation the column carries on SQL
    Server, the UTF-8 one that keeps non-Latin keys intact, or through
    none where the column takes the database's default, as a hash does,
    so the key's index is sought either way. Binary and integer keys
    already bind as the column's type. A column on the database's default
    collation holds vfs-minted, single-case values only (hashes, ULIDs); a
    caller-cased key column must carry ``_string`` or ``BytewiseString``.
    """
    if isinstance(target.type, (BytewiseString, String)):
        collation = getattr(target.type.dialect_impl(_MSSQL), "collation", None)
        key = rows.c[_KEY_COLUMN] if collation is None else collate(rows.c[_KEY_COLUMN], collation)
        return cast(key, String(target.type.length))
    return rows.c[_KEY_COLUMN]
