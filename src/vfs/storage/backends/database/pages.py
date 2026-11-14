"""Keyset pages over the chunk table under an entry filter, in the shape each planner serves.

One scan reads the chunk table a page at a time under an entry filter,
the embed step's: ``id > last ORDER BY id LIMIT n``, each page fetched
whole before the caller acts on it. Pages, never a streaming cursor: the
caller writes between pages on the same connection, and a driver without
multiple active result sets (SQL Server over ODBC) refuses a write while
a cursor is open. Each page keeps only the chunks whose entry is covered
— chunked and live — and the terms that say so live on the entry row.
The index build's scan pages the chunk table alone and reads no entry.

The natural spelling of that filter is a join to the entry table, and on
SQLite it is a trap. Once the store has planner statistics and holds
more than about four or five chunks per entry, the planner puts a Bloom
filter on the join's entry side: its estimate of the outer range ignores
the ``LIMIT``, so it expects the filter to cull, and the filter is built
once per execution over every entry row. Every chunk's entry qualifies,
so the filter excludes nothing, and a scan that re-executes the page
pays a build that grows with the entry count on every page: the scan is
quadratic in the corpus. The statistics are not the thing to drop;
without them the page plans the entries first and sorts every page.

So the profile decides the shape. Where it declares
``probe_entry_filter``, the filter is a correlated scalar subquery on
the entry table compared to a constant, one unique-index probe per chunk
row; SQLite's planner flattens a correlated ``EXISTS`` into the join and
rewrites no other subquery, so this one stays in place and builds
nothing. Every other profile, the generic floor included, keeps the join,
which a cost-based planner optimizes and some punish the probe for.

    page = covered_chunk_page(tables, profile, [chunks.c.id], [entry.c.chunked], after=last, limit=256)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import literal_column, select

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Select

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile


# ---------------------------------------------------------------------------
# The covered chunk page
# ---------------------------------------------------------------------------


def covered_chunk_page(
    tables: VFSTables,
    profile: DialectProfile,
    columns: Sequence[ColumnElement[Any]],
    entry_terms: Sequence[ColumnElement[bool]],
    *,
    after: int,
    limit: int,
    chunk_terms: Sequence[ColumnElement[bool]] = (),
) -> Select[Any]:
    """*columns* of the next *limit* chunk rows past id *after*, ascending, whose entry meets *entry_terms*.

    *chunk_terms* filter the chunk row itself and ride in both shapes
    unchanged. A chunk with no entry, or one whose entry misses a term,
    is dropped by either shape: the probe yields ``NULL = 1``, never true.
    """
    chunks, entry = tables.chunks, tables.entry
    if profile.probe_entry_filter:
        # literal_column renders the constant bare: no bind, no label in the subquery.
        probe = select(literal_column("1")).where(entry.c.entry_id == chunks.c.entry_id, *entry_terms)
        page = select(*columns).where(chunks.c.id > after, *chunk_terms, probe.correlate(chunks).scalar_subquery() == 1)
    else:
        page = (
            select(*columns)
            .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
            .where(chunks.c.id > after, *chunk_terms, *entry_terms)
        )
    return page.order_by(chunks.c.id).limit(limit)
