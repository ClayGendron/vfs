"""The lexical index's storage half: the epoch build and the statistics probe.

The build is one step of the gram epoch's build phase: one stream over
the chunk rows of every ``chunked ∧ indexable ∧ live`` entry — the same
coverage set the gram scan flips ``encoded`` for — fed to the active
engine's builder in byte-bounded batches, its doc rows written as each
batch completes; then the fixed statistics, the term summaries and the
block rows, drained in term order and written in row-bounded inserts
under the epoch being built. Publish and reclaim are the gram epoch's
own: the one pointer flip makes the lexical rows current, and the epoch
sweep drops them with the postings. The invariant extends verbatim —
**``encoded=True`` implies the entry's terms are in the current lexical
epoch.**

The build's CPU — tokenizing each batch, fixing the statistics, and
assembling every drained row — hops through the backend's offload pool
so the loop keeps serving while it runs.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Final, NamedTuple

from sqlalchemy import insert, select

from vfs.models.lexical import BM25_B, BM25_K1, SummaryRow, lexical_builder
from vfs.storage.backends.database.dialects import ByteBatcher, bulk_insert, chunked
from vfs.storage.backends.database.offload import call_offloaded

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from concurrent.futures import Executor

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.lexical import LexicalBuilder
    from vfs.models.rows import VFSTables

# One tokenize call's content payload (chars as the byte proxy): bounds a
# hop's copy and the batch's transient token lists.
_TOKENIZE_BATCH_BYTES: Final = 4 * 1024 * 1024

# Rows per lexical insert. A doc or summary row is bounded-width and a
# block row holds at most a block's postings, so a row budget bounds bytes.
_LEXICAL_INSERT_ROWS: Final = 20_000

# Chunk rows per keyset page of the build's scan (a page is one round trip).
_SCAN_PAGE_ROWS: Final = 256


class TermStatistics(NamedTuple):
    """Corpus-wide BM25 inputs for a query's terms, from one epoch.

    ``terms`` maps each probed term present in the epoch to its summary
    row; a term absent from the corpus is absent here. ``k1`` and ``b``
    are the constants the epoch was weighted under.
    """

    terms: dict[str, SummaryRow]
    n_docs: int
    avg_dl: float
    k1: float
    b: float


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


async def build_lexical_epoch(session: AsyncSession, tables: VFSTables, epoch: int, executor: Executor) -> None:
    """Stream every covered chunk once and write the epoch's four row sets.

    The chunk rows stream in ascending id order into the builder, which
    returns each document's length for ``lex_docs`` as it goes; the
    fixed statistics then write ``lex_stats``, and the two drains write
    ``lex_df`` and ``lex_postings`` in term order. A rival building the
    same epoch collides on a primary key here exactly as on the postings
    table, and the caller's stale-snapshot redrive owns that.
    """
    builder = lexical_builder()
    async for batch in _chunk_batches(session, tables):
        docs = [(chunk_id, content) for chunk_id, _entry_id, content in batch]
        lengths = await call_offloaded(executor, partial(builder.add_docs, docs))
        rows = [
            {"epoch": epoch, "chunk_id": chunk_id, "entry_id": entry_id, "dl": dl}
            for (chunk_id, entry_id, _content), dl in zip(batch, lengths, strict=True)
        ]
        for page in chunked(rows, _LEXICAL_INSERT_ROWS):
            await bulk_insert(session, tables.lex_docs, list(page))
    n_docs, avg_dl = await call_offloaded(executor, builder.finish)
    stats = {"epoch": epoch, "n_docs": n_docs, "avg_dl": avg_dl, "k1": BM25_K1, "b": BM25_B}
    await session.execute(insert(tables.lex_stats), [stats])
    while (summaries := await call_offloaded(executor, partial(_df_rows, builder, epoch))) is not None:
        await bulk_insert(session, tables.lex_df, summaries)
    while (blocks := await call_offloaded(executor, partial(_block_rows, builder, epoch))) is not None:
        await bulk_insert(session, tables.lex_postings, blocks)


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
    """Summary rows for *terms* from *epoch*: one chunked ``IN``-list probe
    on ``lex_df`` plus the epoch's ``lex_stats`` row.

    An epoch with no statistics row (never built) answers zero
    documents; the caller decides what an empty corpus means.
    """
    df, stats = tables.lex_df, tables.lex_stats
    found: dict[str, SummaryRow] = {}
    for probe in chunked(list(dict.fromkeys(terms)), membership_budget):
        lookup = select(df.c.term, df.c.df, df.c.idf, df.c.max_weight, df.c.blocks).where(
            df.c.epoch == epoch, df.c.term.in_(probe)
        )
        for row in await session.execute(lookup):
            found[row.term] = SummaryRow(row.term, row.df, row.idf, row.max_weight, bytes(row.blocks))
    corpus = (
        await session.execute(
            select(stats.c.n_docs, stats.c.avg_dl, stats.c.k1, stats.c.b).where(stats.c.epoch == epoch)
        )
    ).one_or_none()
    if corpus is None:
        return TermStatistics(found, 0, 0.0, BM25_K1, BM25_B)
    return TermStatistics(found, corpus.n_docs, corpus.avg_dl, corpus.k1, corpus.b)


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


def _df_rows(builder: LexicalBuilder, epoch: int) -> list[dict[str, object]] | None:
    """The next batch of summary rows as insert rows — a drain's CPU, off the loop."""
    batch = builder.next_df_batch(_LEXICAL_INSERT_ROWS)
    if batch is None:
        return None
    return [
        {"epoch": epoch, "term": term, "df": df, "idf": idf, "max_weight": max_weight, "blocks": blocks}
        for term, df, idf, max_weight, blocks in batch
    ]


def _block_rows(builder: LexicalBuilder, epoch: int) -> list[dict[str, object]] | None:
    """The next batch of block rows as insert rows — a drain's CPU, off the loop."""
    batch = builder.next_batch(_LEXICAL_INSERT_ROWS)
    if batch is None:
        return None
    return [
        {
            "epoch": epoch,
            "term": term,
            "block_no": block_no,
            "doc_count": doc_count,
            "doc_ids": doc_ids,
            "tfs": tfs,
            "dls": dls,
        }
        for term, block_no, doc_count, doc_ids, tfs, dls in batch
    ]
