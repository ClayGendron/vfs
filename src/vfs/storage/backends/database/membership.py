"""Membership predicates — one owner for every chunked key list.

Every chunked ``column IN (...)`` in the backend is built here, so a
per-engine finding about how a long key list plans lands in one place
instead of forty. Each is the expanding bind list every compiler
renders; the profile travels with every call, as the slot an engine's
own form would take.

    for chunk in chunked(ids, membership_budget):
        stmt = select(entry.c.path).where(membership(entry.c.entry_id, chunk, profile))

A guard read — rows that must stay locked to commit — takes the same
list under ``FOR UPDATE``:

    guard = locked_lookup(entry.c.entry_id, chunk, [entry.c.entry_id, entry.c.path], profile)

One key list is built outside this module: a refresh's refusal probe
(``embed.pass_unembedded``) spells its hashes as casts to the column's
type, and it chunks them by the membership budget like every list here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from vfs.storage.backends.database.dialects import chunked, lock_rows

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy import Column, ColumnElement, Select

    from vfs.storage.backends.database.dialects import DialectProfile


# ---------------------------------------------------------------------------
# Membership predicates and guard reads
# ---------------------------------------------------------------------------


def membership(target: Column[Any], keys: Sequence[Any], profile: DialectProfile) -> ColumnElement[bool]:
    """``target IN keys``; *keys* is one chunk under the budget, and *profile* is the slot for an engine's own form."""
    del profile
    return target.in_(list(keys))


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
    key: Column[Any], keys: Sequence[Any], columns: Sequence[Column[Any]], profile: DialectProfile
) -> Select[Any]:
    """``SELECT columns FROM key's table WHERE key IN keys``, rows locked to the transaction's end.

    The guard shape every liveness proof rests on: the rows come back
    locked, so the caller's decision stands on what it read. Chunk
    *keys* under the budget and sort them, so rival guards lock in one
    order. *profile* is the slot for an engine's own form, as in
    :func:`membership`.
    """
    return lock_rows(select(*columns).where(membership(key, keys, profile)))
