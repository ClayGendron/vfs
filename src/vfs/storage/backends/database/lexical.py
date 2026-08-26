"""The lexical index's storage half: the epoch build and the statistics probe.

The build is one step of the gram epoch's build phase: two streams
over the chunk rows of every ``chunked ∧ indexable ∧ live`` entry —
the same coverage set the gram scan flips ``encoded`` for — fed to the
pure builder in byte-bounded batches (statistics first, weighted rows
second) and written into the four ``lex_*`` tables under the epoch
being built as each batch completes. Publish and reclaim are
the gram epoch's own: the one pointer flip makes the lexical rows
current, and the epoch sweep drops them with the postings. The
invariant extends verbatim — **``encoded=True`` implies the entry's
terms are in the current lexical epoch.**

The build's CPU — tokenizing each batch, fixing the statistics, and
assembling every drained row — hops through the backend's offload
pool so the loop keeps serving while it runs.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Final, NamedTuple

from sqlalchemy import insert, select

from vfs.models.lexical import LexicalIndexBuilder
from vfs.storage.backends.database.dialects import ByteBatcher, chunked
from vfs.storage.backends.database.offload import call_offloaded

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from concurrent.futures import Executor

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.lexical import DfRow, DocRow, TermRow
    from vfs.models.rows import VFSTables

# One tokenize call's content payload (chars as the byte proxy): bounds
# a hop's copy and pass two's transient term rows (~100 per chunk).
_TOKENIZE_BATCH_BYTES: Final = 4 * 1024 * 1024

# Rows per lexical insert. Every ``lex_*`` row is bounded-width (a term
# is at most 64 bytes), so a row budget bounds the statement's bytes.
_LEXICAL_INSERT_ROWS: Final = 20_000

# Chunk rows per keyset page of the build's scan (a page is one round trip).
_SCAN_PAGE_ROWS: Final = 256


class TermStatistics(NamedTuple):
    """Corpus-wide BM25 inputs for a query's terms, from one epoch.

    ``terms`` maps each probed term present in the epoch to its
    ``(df, idf)``; a term absent from the corpus is absent here.
    """

    terms: dict[str, tuple[int, float]]
    n_docs: int
    avg_dl: float


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


async def build_lexical_epoch(session: AsyncSession, tables: VFSTables, epoch: int, executor: Executor) -> None:
    """Stream every covered chunk twice and write the epoch's four row sets.

    Pass one streams the chunk rows in ascending id order, counting
    document frequencies and lengths and writing ``lex_docs`` as it
    goes; the fixed statistics then write ``lex_stats`` and ``lex_df``;
    pass two streams the same rows again and writes each batch's
    weighted ``lex_terms`` rows. Nothing but the vocabulary is held
    across batches. A rival building the same epoch collides on a
    primary key here exactly as on the postings table, and the caller's
    stale-snapshot redrive owns that.
    """
    builder = LexicalIndexBuilder()
    async for batch in _chunk_batches(session, tables):
        docs = await call_offloaded(executor, partial(builder.observe, batch))
        for rows in chunked(docs, _LEXICAL_INSERT_ROWS):
            await session.execute(insert(tables.lex_docs), _doc_rows(epoch, rows))
    stats = await call_offloaded(executor, builder.finish)
    await session.execute(insert(tables.lex_stats), [{"epoch": epoch, "n_docs": stats.n_docs, "avg_dl": stats.avg_dl}])
    for dfs in chunked(builder.dfs, _LEXICAL_INSERT_ROWS):
        await session.execute(insert(tables.lex_df), _df_rows(epoch, dfs))
    async for batch in _chunk_batches(session, tables):
        terms = await call_offloaded(executor, partial(_weigh_rows, builder, epoch, batch))
        for rows in chunked(terms, _LEXICAL_INSERT_ROWS):
            await session.execute(insert(tables.lex_terms), list(rows))


# ---------------------------------------------------------------------------
# Term statistics
# ---------------------------------------------------------------------------


async def lexical_stats(
    session: AsyncSession,
    tables: VFSTables,
    epoch: int,
    terms: Sequence[str],
    membership_budget: int,
) -> TermStatistics:
    """Corpus-wide statistics for *terms* from *epoch*: one chunked
    ``IN``-list probe on ``lex_df`` plus the epoch's ``lex_stats`` row.

    An epoch with no statistics row (never built) answers zero
    documents; the caller decides what an empty corpus means.
    """
    df, stats = tables.lex_df, tables.lex_stats
    found: dict[str, tuple[int, float]] = {}
    for probe in chunked(list(dict.fromkeys(terms)), membership_budget):
        lookup = select(df.c.term, df.c.df, df.c.idf).where(df.c.epoch == epoch, df.c.term.in_(probe))
        for term, df_value, idf_value in await session.execute(lookup):
            found[term] = (df_value, idf_value)
    corpus = (await session.execute(select(stats.c.n_docs, stats.c.avg_dl).where(stats.c.epoch == epoch))).one_or_none()
    if corpus is None:
        return TermStatistics(found, 0, 0.0)
    return TermStatistics(found, corpus.n_docs, corpus.avg_dl)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _chunk_batches(session: AsyncSession, tables: VFSTables) -> AsyncIterator[list[tuple[int, str, str]]]:
    """The covered chunk rows — every chunk of a ``chunked ∧ indexable ∧ live``
    entry, ascending id — in byte-bounded batches.

    Read by keyset pages, never a streaming cursor: the caller writes
    between batches on the same connection, and a driver without
    multiple active result sets (SQL Server over ODBC) refuses a write
    while a cursor is open. Each page is fully fetched before the batch
    it completes is handed out.
    """
    chunks, entry = tables.chunks, tables.entry
    scan = (
        select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(entry.c.chunked, entry.c.indexable, entry.c.deleted_at.is_(None))
        .order_by(chunks.c.id)
        .limit(_SCAN_PAGE_ROWS)
    )
    batcher: ByteBatcher[tuple[int, str, str]] = ByteBatcher(_doc_size, _TOKENIZE_BATCH_BYTES)
    last = 0
    while page := (await session.execute(scan.where(chunks.c.id > last))).all():
        for row in page:
            full = batcher.add((row.id, row.entry_id, row.content))
            if full is not None:
                yield full
        last = page[-1].id
    final = batcher.flush()
    if final is not None:
        yield final


def _doc_size(doc: tuple[int, str, str]) -> int:
    """The tokenize batcher's metering: content length, chars as byte proxy."""
    _chunk_id, _entry_id, content = doc
    return len(content)


def _doc_rows(epoch: int, docs: Sequence[DocRow]) -> list[dict[str, object]]:
    return [{"epoch": epoch, "chunk_id": doc.chunk_id, "entry_id": doc.entry_id, "dl": doc.dl} for doc in docs]


def _df_rows(epoch: int, dfs: Sequence[DfRow]) -> list[dict[str, object]]:
    return [{"epoch": epoch, "term": row.term, "df": row.df, "idf": row.idf} for row in dfs]


def _weigh_rows(builder: LexicalIndexBuilder, epoch: int, batch: list[tuple[int, str, str]]) -> list[dict[str, object]]:
    """One batch's weighted term rows as insert rows — pass two's CPU, off the loop."""
    rows: list[TermRow] = builder.weigh(batch)
    return [{"epoch": epoch, "term": r.term, "chunk_id": r.chunk_id, "tf": r.tf, "weight": r.weight} for r in rows]
