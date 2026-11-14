"""The lexical index's storage half: the epoch build, the statistics probe, and the reads the lexical leg ranks from.

The reads are the leg's two rounds over the posting blocks
(:func:`chunk_ranking`, :func:`tail_block_statements`), the narrow rung's
chunk ids for an allow-list (:func:`chunk_ids_for`), and the visible
lexicon, the statistics a partial caller's leg is scored under
(:func:`visible_lexicon`).

The build is one step of the gram epoch's build phase: one keyset pass
over the chunk table keeping the chunks of exactly the entries the gram
scan covered — the set the publish flips ``encoded`` for — fed to the active
engine's builder in byte-bounded batches, its doc rows written as each
batch completes; then the fixed statistics, the term summaries and the
block rows, drained in term order and written in row-bounded inserts
under the epoch being built. Publish and reclaim are the gram epoch's
own: the one pointer flip makes the lexical rows current, and the epoch
sweep drops them with the postings. The invariant extends to the
lexical rows — **``encoded=True`` on a content row implies the entry's
terms are in the current lexical epoch**; a directory, with no terms to
index, is always ``encoded``.

The build's CPU — tokenizing each batch, fixing the statistics, and
assembling every drained row — hops through the process's offload pool
so the loop keeps serving while it runs.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import and_, func, insert, or_, select, tuple_

from vfs.batching import ByteBatcher
from vfs.models.lexical import (
    BM25_B,
    BM25_K1,
    ScoreBlock,
    SummaryRow,
    decode_summary,
    idf,
    lexical_builder,
    score_blocks,
    select_blocks,
)
from vfs.native import extension
from vfs.offload import call_offloaded
from vfs.storage.backends.database.dialects import bulk_insert, chunked
from vfs.storage.backends.database.membership import live_chunks, membership
from vfs.storage.backends.database.ranges import derived_hint
from vfs.storage.backends.database.rights import RIGHTS_FIELDS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Container, Mapping, Sequence
    from concurrent.futures import Executor

    from sqlalchemy import Column, ColumnElement, Select, Table
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.lexical import LexicalBuilder
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.rights import Visibility

# One tokenize call's content payload (chars as the byte proxy): bounds a
# hop's copy and the batch's transient token lists.
_TOKENIZE_BATCH_BYTES: Final = 4 * 1024 * 1024

# Rows per lexical insert. A doc or summary row is bounded-width and a
# block row holds at most a block's postings, so a row budget bounds bytes.
_LEXICAL_INSERT_ROWS: Final = 20_000

# Chunk rows per keyset page of the build's scan (a page is one round trip).
_SCAN_PAGE_ROWS: Final = 256

HEAD_BLOCKS: Final = 8
"""Blocks per term fetched in round one — a term of ≤ 1,024 postings is complete there."""

ChunkId = int
Ranking = list[tuple[ChunkId, float]]


class TermStatistics(NamedTuple):
    """Corpus-wide BM25 inputs for a query's terms, from the live set: the base and its published deltas.

    ``slots`` holds each probed term's summary row in every live segment
    that has it, ``(epoch, row)`` in epoch order, each a term of its own to
    the scorer. ``terms`` maps each term present in any segment to its first
    slot's row with ``df`` summed over the live set; a term absent from the
    corpus is absent from both. ``n_docs`` sums every segment's count;
    ``avg_dl``, ``k1`` and ``b`` are the base's, which every slot was
    weighted under.
    """

    terms: dict[str, SummaryRow]
    n_docs: int
    avg_dl: float
    k1: float
    b: float
    slots: Mapping[str, Sequence[tuple[int, SummaryRow]]]


class Lexicon(NamedTuple):
    """A partial caller's lexical leg: visible-set statistics, every block rebounded, the visible chunks.

    ``blocks`` index their term by position in the visible statistics'
    term order, which is the query's order with invisible terms dropped;
    ``visible`` is sorted, the scorer's candidate set.
    """

    stats: TermStatistics
    blocks: list[ScoreBlock]
    idfs: list[float]
    visible: list[ChunkId]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


async def build_lexical_epoch(
    session: AsyncSession, tables: VFSTables, epoch: int, executor: Executor, covered: Container[str]
) -> None:
    """Stream every covered chunk once and write the epoch's four row sets.

    The chunk rows stream in ascending id order into the builder, which
    returns each document's length for ``lex_docs`` as it goes; the
    fixed statistics then write ``lex_stats``, and the two drains write
    ``lex_df`` and ``lex_postings`` in term order. A rival building the
    same epoch collides on a primary key here exactly as on the postings
    table, and the caller's stale-snapshot redrive owns that. The feed
    keeps the chunks of the *covered* entries alone.
    """
    builder = lexical_builder()
    await _fed(session, tables, epoch, executor, builder, _chunk_batches(session, tables, covered))
    n_docs, avg_dl = await call_offloaded(executor, builder.finish)
    stats = {"epoch": epoch, "n_docs": n_docs, "avg_dl": avg_dl, "k1": BM25_K1, "b": BM25_B}
    await session.execute(insert(tables.lex_stats), [stats])
    await _drained(session, tables, epoch, executor, builder)


async def build_lexical_delta(
    session: AsyncSession,
    tables: VFSTables,
    epoch: int,
    base: int,
    posted: Sequence[str],
    executor: Executor,
    profile: DialectProfile,
    membership_budget: int,
) -> None:
    """Write a delta's four row sets from the chunks of exactly the *posted* entries, weighted under *base*.

    The chunk ids are read by membership slices of the entry ids and sorted,
    then their content by slices of those ids in order, so the builder sees
    strictly increasing ids and no entry flag is read. Every block's bound is
    taken under the base's mean length and, per term, the base's idf where
    the base holds the term, else ``idf(df, base_n + delta_n)``: the scale
    the overlay already scores unindexed bodies on. The delta's own document
    count and mean length are its ``lex_stats`` row, under the base's ``k1``
    and ``b``.
    """
    chunks, df, stats = tables.chunks, tables.lex_df, tables.lex_stats
    ids: list[int] = []
    for entry_ids in chunked(list(posted), membership_budget):
        held = select(chunks.c.id).where(membership(chunks.c.entry_id, entry_ids, profile))
        ids.extend((await session.execute(held)).scalars())
    ids.sort()
    builder = lexical_builder()
    batches = _posted_batches(session, tables, ids, profile, membership_budget)
    fed = await _fed(session, tables, epoch, executor, builder, batches)
    base_row = select(stats.c.n_docs, stats.c.avg_dl, stats.c.k1, stats.c.b).where(stats.c.epoch == base)
    corpus = (await session.execute(base_row)).one()
    vocabulary = await call_offloaded(executor, builder.vocabulary)
    in_base: dict[str, float] = {}
    for probe in chunked([term for term, _count in vocabulary], membership_budget):
        lookup = select(df.c.term, df.c.idf).where(df.c.epoch == base, membership(df.c.term, probe, profile))
        in_base.update((row.term, row.idf) for row in await session.execute(lookup))
    idfs = [in_base[term] if term in in_base else idf(count, corpus.n_docs + fed) for term, count in vocabulary]
    n_docs, avg_dl = await call_offloaded(executor, partial(builder.finish_under, corpus.avg_dl, idfs))
    row = {"epoch": epoch, "n_docs": n_docs, "avg_dl": avg_dl, "k1": corpus.k1, "b": corpus.b}
    await session.execute(insert(stats), [row])
    await _drained(session, tables, epoch, executor, builder)


def lexical_scan_page(tables: VFSTables, *, after: int) -> Select[Any]:
    """The build scan's next keyset page past chunk id *after*: chunk rows alone, no entry row read."""
    chunks = tables.chunks
    page = select(chunks.c.id, chunks.c.entry_id, chunks.c.content).where(chunks.c.id > after)
    return page.order_by(chunks.c.id).limit(_SCAN_PAGE_ROWS)


# ---------------------------------------------------------------------------
# Term statistics
# ---------------------------------------------------------------------------


async def lexical_stats(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    live: Sequence[int],
    terms: Sequence[str],
    membership_budget: int,
) -> TermStatistics:
    """Summary rows for *terms* in every segment of *live*, the base first: chunked membership probes on
    ``lex_df`` and the live set's ``lex_stats`` rows, each statement spending one budget on both lists.

    A live set whose base has no statistics row (none, or never built)
    answers zero documents; the caller decides what an empty corpus means.
    """
    df, stats = tables.lex_df, tables.lex_stats
    slots: dict[str, list[tuple[int, SummaryRow]]] = {}
    for epochs, probe in live_chunks(live, list(dict.fromkeys(terms)), membership_budget):
        columns = (df.c.epoch, df.c.term, df.c.df, df.c.idf, df.c.max_weight, df.c.blocks)
        lookup = select(*columns).where(membership(df.c.epoch, epochs, profile), membership(df.c.term, probe, profile))
        for row in await session.execute(lookup):
            summary = SummaryRow(row.term, row.df, row.idf, row.max_weight, bytes(row.blocks))
            slots.setdefault(row.term, []).append((row.epoch, summary))
    corpus: dict[int, Any] = {}
    for epochs in chunked(list(live), membership_budget):
        stmt = select(stats.c.epoch, stats.c.n_docs, stats.c.avg_dl, stats.c.k1, stats.c.b)
        rows = await session.execute(stmt.where(membership(stats.c.epoch, epochs, profile)))
        corpus.update((row.epoch, row) for row in rows)
    for held in slots.values():
        held.sort(key=lambda slot: slot[0])
    found = {term: held[0][1]._replace(df=sum(row.df for _, row in held)) for term, held in slots.items()}
    base = corpus.get(live[0]) if live else None
    if base is None:
        return TermStatistics(found, 0, 0.0, BM25_K1, BM25_B, slots)
    return TermStatistics(found, sum(row.n_docs for row in corpus.values()), base.avg_dl, base.k1, base.b, slots)


# ---------------------------------------------------------------------------
# Block reads
# ---------------------------------------------------------------------------


async def chunk_ranking(
    session: AsyncSession,
    tables: VFSTables,
    live: Sequence[int],
    stats: TermStatistics,
    present: Sequence[str],
    k: int,
    candidates: Sequence[ChunkId] | None,
    profile: DialectProfile,
    membership_budget: int,
) -> Ranking:
    """Top-``k`` ``(chunk_id, score)`` from the head fetch plus the selected blocks, every slot a term.

    A chunk's postings live in one live segment, so each (term, segment)
    slot scores under its own stored idf and summary and the blocks concatenate;
    a slot's bound lifted by the others' maxima loosens block selection, never tightens it.
    """
    postings = tables.lex_postings
    columns = posting_columns(postings)
    slots = [(epoch, term) for term in present for epoch, _row in stats.slots[term]]
    rows = {(epoch, term): row for term in present for epoch, row in stats.slots[term]}
    summaries = {slot: decode_summary(rows[slot].blocks) for slot in slots}
    idfs = [rows[slot].idf for slot in slots]
    index = {slot: position for position, slot in enumerate(slots)}

    def as_blocks(fetched: Sequence[Any]) -> list[ScoreBlock]:
        return [
            ScoreBlock(
                index[(r.epoch, r.term)],
                summaries[(r.epoch, r.term)].max_weights[r.block_no],
                bytes(r.doc_ids),
                bytes(r.tfs),
                bytes(r.dls),
            )
            for r in fetched
        ]

    blocks: list[ScoreBlock] = []
    for epochs, probe in live_chunks(live, list(present), membership_budget):
        in_slots = (membership(postings.c.epoch, epochs, profile), postings.c.term.in_(list(probe)))
        head = select(*columns).where(*in_slots, postings.c.block_no < HEAD_BLOCKS)
        blocks += as_blocks((await session.execute(head)).all())
    scored = score_blocks(blocks, idfs, stats.avg_dl, 10**9, candidates=candidates)
    theta = scored[k - 1][1] if len(scored) >= k else 0.0
    score_of = dict(scored)
    sorted_candidates = sorted(score_of)
    tail = [score_of[chunk] for chunk in sorted_candidates]
    overflowing = [slot for slot in slots if len(summaries[slot].first_ids) > HEAD_BLOCKS]
    selected = select_blocks([summaries[slot] for slot in overflowing], sorted_candidates, tail, theta)
    wanted = {
        slot: [no for no in competing if no >= HEAD_BLOCKS]
        for slot, competing in zip(overflowing, selected, strict=True)
    }
    for statement in tail_block_statements(postings, wanted, profile, membership_budget):
        blocks += as_blocks((await session.execute(statement)).all())
    return score_blocks(blocks, idfs, stats.avg_dl, k, candidates=candidates)


def tail_block_statements(
    postings: Table,
    wanted: Mapping[tuple[int, str], Sequence[int]],
    profile: DialectProfile,
    membership_budget: int,
) -> list[Select[Any]]:
    """The tail fetch: the statements that read the ``wanted`` blocks ((epoch, term) → block numbers) by key.

    Two spellings, chosen by the profile. Where the engine accepts a
    row-value constructor inside ``IN`` (``tuple_in``), every statement
    is ``(epoch, term, block_no) IN (triples)``, the triples chunked
    at a third of the membership budget because each binds three values, and no
    statement carries an ``OR``. Elsewhere the arms are
    ``epoch = ? AND term = ? AND block_no IN (...)``, one per slot and
    chunk of block numbers, packed into ``OR`` statements under the
    membership budget, which nets the driver's reserve; an arm over the whole live set would fetch blocks
    no slot chose.

    The tuple form exists because SQLite's planner loses rows from the OR
    form: over the postings table's ``WITHOUT ROWID`` key, once the store
    has planner statistics, a ``MULTI-INDEX OR`` whose later arm lists
    more than one block and names a term that sorts before an earlier
    arm's returns none of that arm's rows. A statement with no ``OR``
    cannot take that plan. The ranking harness driver calls this builder
    too, so the referee and the leg cannot drift apart.
    """
    columns = posting_columns(postings)
    if profile.tuple_in:
        triples = [(epoch, term, no) for (epoch, term), nos in wanted.items() for no in nos]
        key = tuple_(postings.c.epoch, postings.c.term, postings.c.block_no)
        per_statement = max(1, membership_budget // 3)
        return [select(*columns).where(key.in_(list(chunk))) for chunk in chunked(triples, per_statement)]
    arms: list[tuple[int, ColumnElement[bool]]] = []
    for (epoch, term), nos in wanted.items():
        for chunk in chunked(list(nos), max(1, membership_budget - 2)):
            arm = and_(postings.c.epoch == epoch, postings.c.term == term, postings.c.block_no.in_(list(chunk)))
            arms.append((len(chunk) + 2, arm))
    return [select(*columns).where(or_(*statement)) for statement in _packed_arms(arms, membership_budget)]


def posting_columns(postings: Table) -> tuple[Column[Any], ...]:
    """The six posting columns every block fetch projects, its slot's epoch first, in the scorer's reader's order."""
    return (postings.c.epoch, postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)


async def chunk_ids_for(
    session: AsyncSession,
    tables: VFSTables,
    live: Sequence[int],
    doc_ids: Sequence[int],
    profile: DialectProfile,
    membership_budget: int,
) -> list[ChunkId]:
    """The live set's chunk ids of the entries with surrogate ids *doc_ids*, sorted."""
    entry, docs = tables.entry, tables.lex_docs
    found: list[ChunkId] = []
    for epochs, chunk in live_chunks(live, list(doc_ids), membership_budget):
        stmt = (
            select(docs.c.chunk_id)
            .select_from(docs.join(entry, entry.c.entry_id == docs.c.entry_id))
            .where(membership(docs.c.epoch, epochs, profile), membership(entry.c.id, chunk, profile))
        )
        found.extend((await session.execute(stmt)).scalars())
    found.sort()
    return found


# ---------------------------------------------------------------------------
# The visible lexicon — statistics over what a partial caller can see
# ---------------------------------------------------------------------------


async def visible_lexicon(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    live: Sequence[int],
    stats: TermStatistics,
    terms: Sequence[str],
    view: Visibility,
) -> Lexicon:
    """The query's BM25 inputs counted over the rows *view* admits, and the blocks to score them.

    ``N`` and the mean length come from the visible chunks of the live set,
    each counted once, since a live chunk has one doc row in it; each term's
    ``df`` from its postings in every slot met with the visible chunks
    among them, one idf a term. A term no visible row contains drops out, so
    it neither scores nor appears in the export. Every block's stored bound
    was taken under its slot's statistics, so it is rescaled —
    ``max_weight * idf_v / idf_slot * max(1, avg_dl_v / avg_dl_base)``,
    never below the true bound — before the scorer prunes on it; the union's
    cap is every slot's stored ``df`` summed, never below the union.

    Cost profile, stated plainly: this reads every block of every query
    term and resolves the visibility of every chunk those blocks name —
    work that grows with the terms' corpus-wide document frequency, not
    with what the caller sees. Numbering chunks in path order, so a
    folder is one id range, is the known way to make it flat.
    """
    n_docs, total_dl = await _visible_corpus(session, tables, profile, live, view, membership_budget)
    avg_dl = total_dl / n_docs if n_docs else 0.0
    probed = [term for term in terms if term in stats.terms]
    by_slot = await _all_blocks(session, tables, profile, live, probed, membership_budget)
    engine = extension()
    union: list[int] = []
    if probed:
        groups = [[bytes(block.doc_ids)] for fetched in by_slot.values() for block in fetched]
        cap = sum(row.df for term in probed for _epoch, row in stats.slots[term])
        union, _count = engine.candidate_ids(groups, None, cap)
    visible = sorted(await _visible_chunks(session, tables, profile, membership_budget, live, union, view))
    kept: dict[str, SummaryRow] = {}
    blocks: list[ScoreBlock] = []
    idfs: list[float] = []
    lift = max(1.0, avg_dl / stats.avg_dl) if stats.avg_dl else 1.0
    for term in probed:
        term_slots = [(row, by_slot.get((epoch, term), [])) for epoch, row in stats.slots[term]]
        held = [[bytes(b.doc_ids)] for _row, fetched in term_slots for b in fetched]
        df = engine.candidate_ids(held, visible, 0)[1] if visible else 0
        if not df:
            continue
        term_idf = idf(df, n_docs)
        first = stats.terms[term]
        kept[term] = SummaryRow(term, df, term_idf, first.max_weight * term_idf / first.idf * lift, first.blocks)
        position = len(idfs)
        idfs.append(term_idf)
        for row, fetched in term_slots:
            maxima, scale = decode_summary(row.blocks).max_weights, term_idf / row.idf * lift
            blocks += [
                ScoreBlock(position, maxima[b.block_no] * scale, bytes(b.doc_ids), bytes(b.tfs), bytes(b.dls))
                for b in fetched
            ]
    return Lexicon(TermStatistics(kept, n_docs, avg_dl, stats.k1, stats.b, {}), blocks, idfs, visible)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _chunk_batches(
    session: AsyncSession, tables: VFSTables, covered: Container[str]
) -> AsyncIterator[list[tuple[int, str, str]]]:
    """The covered chunk rows — every chunk of an entry in *covered*, ascending id — in byte-bounded batches.

    Read by keyset pages, never a streaming cursor, each fully fetched
    before the batch it completes is handed out (:mod:`.pages` says why);
    a row whose entry is not covered is dropped before the batcher.
    """
    batcher: ByteBatcher[tuple[int, str, str]] = ByteBatcher(_doc_size, _TOKENIZE_BATCH_BYTES)
    last = 0
    while page := (await session.execute(lexical_scan_page(tables, after=last))).all():
        for row in page:
            if row.entry_id not in covered:
                continue
            full = batcher.add((row.id, row.entry_id, row.content))
            if full is not None:
                yield full
        last = page[-1].id
    final = batcher.flush()
    if final is not None:
        yield final


async def _posted_batches(
    session: AsyncSession, tables: VFSTables, ids: Sequence[ChunkId], profile: DialectProfile, membership_budget: int
) -> AsyncIterator[list[tuple[int, str, str]]]:
    """The chunk rows *ids* name, ascending, read by membership slices of the sorted ids, in byte-bounded batches."""
    chunks = tables.chunks
    batcher: ByteBatcher[tuple[int, str, str]] = ByteBatcher(_doc_size, _TOKENIZE_BATCH_BYTES)
    for page in chunked(ids, membership_budget):
        stmt = select(chunks.c.id, chunks.c.entry_id, chunks.c.content).where(membership(chunks.c.id, page, profile))
        for row in (await session.execute(stmt.order_by(chunks.c.id))).all():
            full = batcher.add((row.id, row.entry_id, row.content))
            if full is not None:
                yield full
    final = batcher.flush()
    if final is not None:
        yield final


async def _fed(
    session: AsyncSession,
    tables: VFSTables,
    epoch: int,
    executor: Executor,
    builder: LexicalBuilder,
    batches: AsyncIterator[list[tuple[int, str, str]]],
) -> int:
    """Feed each batch to *builder* off the loop and write its doc rows under *epoch*; the documents fed."""
    fed = 0
    async for batch in batches:
        docs = [(chunk_id, content) for chunk_id, _entry_id, content in batch]
        lengths = await call_offloaded(executor, partial(builder.add_docs, docs))
        rows = [
            {"epoch": epoch, "chunk_id": chunk_id, "entry_id": entry_id, "dl": dl}
            for (chunk_id, entry_id, _content), dl in zip(batch, lengths, strict=True)
        ]
        for page in chunked(rows, _LEXICAL_INSERT_ROWS):
            await bulk_insert(session, tables.lex_docs, list(page))
        fed += len(batch)
    return fed


async def _drained(
    session: AsyncSession, tables: VFSTables, epoch: int, executor: Executor, builder: LexicalBuilder
) -> None:
    """The finished builder's summary rows, then its block rows, written under *epoch* in row-bounded inserts."""
    while (summaries := await call_offloaded(executor, partial(_df_rows, builder, epoch))) is not None:
        await bulk_insert(session, tables.lex_df, summaries)
    while (blocks := await call_offloaded(executor, partial(_block_rows, builder, epoch))) is not None:
        await bulk_insert(session, tables.lex_postings, blocks)


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


def _packed_arms(
    arms: Sequence[tuple[int, ColumnElement[bool]]], parameter_budget: int
) -> list[list[ColumnElement[bool]]]:
    """Round-two arms grouped into statements whose bind spend stays inside the budget."""
    statements: list[list[ColumnElement[bool]]] = []
    spend = 0
    for binds, arm in arms:
        if not statements or spend + binds > parameter_budget:
            statements.append([])
            spend = 0
        statements[-1].append(arm)
        spend += binds
    return statements


async def _visible_corpus(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    live: Sequence[int],
    view: Visibility,
    membership_budget: int,
) -> tuple[int, int]:
    """``(chunk count, total length)`` over the live set's chunks whose entry the view admits.

    One aggregate over the chunks joined to the visible entries where the
    dialect joins a range list, hinted where its planner would otherwise
    drive the join from the chunks; otherwise one aggregate when the
    predicate fits one statement, or each clause's rows read and
    deduplicated here, since clauses overlap and a per-clause count
    would double one. Each runs once per slice of the live set, summed.
    """
    docs, entry = tables.lex_docs, tables.entry
    aggregate = (func.count(), func.coalesce(func.sum(docs.c.dl), 0))
    visible = view.entries()
    joined = docs.join(entry, entry.c.entry_id == docs.c.entry_id)
    clauses = view.clauses() or []
    fields = (docs.c.chunk_id, docs.c.dl, entry.c.path, *(entry.c[field] for field in sorted(RIGHTS_FIELDS)))
    hint = derived_hint(profile, docs, "epoch", "entry_id")
    count, total, lengths = 0, 0, {}
    for epochs in chunked(list(live), membership_budget):
        in_live = membership(docs.c.epoch, epochs, profile)
        if visible is not None:
            on_visible = docs.join(visible, visible.c.entry_id == docs.c.entry_id)
            stmt = select(*aggregate).select_from(on_visible).where(in_live)
            stmt = stmt if hint is None else stmt.prefix_with(hint, dialect=profile.name)
        elif len(clauses) == 1:
            stmt = select(*aggregate).select_from(joined).where(in_live, clauses[0].predicate)
        else:
            for clause in clauses:
                rows = await session.execute(select(*fields).select_from(joined).where(in_live, clause.predicate))
                lengths.update((m["chunk_id"], m["dl"]) for m in rows.mappings() if view.holds(m, view.need))
            continue
        slice_count, slice_total = (await session.execute(stmt)).one()
        count, total = count + int(slice_count), total + int(slice_total)
    return count + len(lengths), total + sum(lengths.values())


async def _all_blocks(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    live: Sequence[int],
    terms: Sequence[str],
    membership_budget: int,
) -> dict[tuple[int, str], list[Any]]:
    """Every block of each of *terms* in every live segment, keyed by slot, in block order."""
    postings = tables.lex_postings
    out: dict[tuple[int, str], list[Any]] = {}
    for epochs, probe in live_chunks(live, list(terms), membership_budget):
        stmt = (
            select(*posting_columns(postings))
            .where(membership(postings.c.epoch, epochs, profile), postings.c.term.in_(list(probe)))
            .order_by(postings.c.epoch, postings.c.term, postings.c.block_no)
        )
        for row in await session.execute(stmt):
            out.setdefault((row.epoch, row.term), []).append(row)
    return out


async def _visible_chunks(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    live: Sequence[int],
    chunk_ids: Sequence[ChunkId],
    view: Visibility,
) -> set[ChunkId]:
    """The *chunk_ids* whose entry the view admits, resolved through the live set's doc rows."""
    docs, entry = tables.lex_docs, tables.entry
    visible: set[ChunkId] = set()
    for epochs, chunk in live_chunks(live, list(chunk_ids), membership_budget):
        stmt = (
            select(docs.c.chunk_id, entry.c.path, *(entry.c[field] for field in sorted(RIGHTS_FIELDS)))
            .select_from(docs.join(entry, entry.c.entry_id == docs.c.entry_id))
            .where(membership(docs.c.epoch, epochs, profile), membership(docs.c.chunk_id, chunk, profile))
        )
        visible.update(m["chunk_id"] for m in (await session.execute(stmt)).mappings() if view.holds(m, view.need))
    return visible
