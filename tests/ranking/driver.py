"""The BM25 baseline driver: the lexical index read the way the glean leg reads it.

``load_corpus`` writes a corpus into a backend and reindexes it;
``entry_ranking`` runs one query as two rounds over the block tables —
the head fetch, the engine's scorer, block selection for the overflowing
terms, the round-two key fetch with the epoch equality inside every arm,
the scorer again — then MaxP to entries. Scores are rounded to
:data:`SCORE_DECIMALS` and ordered ``score DESC, path ASC`` so the
ordered list is identical on every engine and across rebuilds (entry
ids are minted per write; paths are not).
"""

from __future__ import annotations

from array import array
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import and_, or_, select

from vfs.models import Entry
from vfs.models.lexical import ScoreBlock, decode_summary, score_blocks, select_blocks, tokenize
from vfs.paths import Path
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.lexical import lexical_stats

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tests.ranking.corpora import Corpus
    from vfs.storage.backends.database import DatabaseStorage

HEAD_BLOCKS: Final = 8
"""Blocks per term fetched in round one — a term of ≤ 1,024 postings is complete there."""

FUSION_K: Final = 1000
"""Chunk-level depth scored per query, the fusion leg's K; entries come from these."""

SCORE_DECIMALS: Final = 9
"""Rounding applied before ordering — the last-ulp drift between engines never reorders."""

WRITE_BATCH: Final = 5000

Run = dict[str, dict[str, float]]
"""qid → doc id → score, the shape ranx reads."""


class Loaded(NamedTuple):
    """A corpus written and indexed in a backend: its epoch and chunk → path map."""

    storage: DatabaseStorage
    corpus: Corpus
    epoch: int
    path_of: dict[int, str]


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


async def load_corpus(storage: DatabaseStorage, corpus: Corpus) -> Loaded:
    """Write every document, reindex, and read the chunk → path map once."""
    entries = [Entry(path=Path(corpus.paths[doc]), content=text) for doc, text in corpus.docs.items()]
    for batch in chunked(entries, WRITE_BATCH):
        written = await storage.write(entries=list(batch), parents=True)
        assert written.success is True, written.errors
    indexed = await storage.reindex()
    assert indexed.success is True, indexed.errors
    tables = storage._host.tables
    entry, chunks, meta = tables.entry, tables.chunks, tables.meta
    async with storage._host.engine.connect() as conn:
        epoch = (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()
        located = select(chunks.c.id, entry.c.path).select_from(
            chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
        )
        path_of = {row.id: row.path for row in await conn.execute(located)}
    return Loaded(storage, corpus, epoch, path_of)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


async def bm25_run(loaded: Loaded, k: int = 50) -> Run:
    """Every query of the corpus ranked to ``k`` entries, keyed by doc id."""
    doc_of = loaded.corpus.doc_of
    run: Run = {}
    for qid, query in loaded.corpus.queries.items():
        ranked = await entry_ranking(loaded, query, k)
        run[qid] = {doc_of[path]: score for path, score in ranked}
    return run


async def entry_ranking(loaded: Loaded, query: str, k: int) -> list[tuple[str, float]]:
    """Top-``k`` entries as ``(path, score)``: MaxP over the chunk ranking, rounded, path-broken."""
    best: dict[str, float] = {}
    for chunk_id, score in await chunk_ranking(loaded, query, FUSION_K):
        path = loaded.path_of[chunk_id]
        best[path] = max(best.get(path, 0.0), round(score, SCORE_DECIMALS))
    ordered = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    return ordered[:k]


async def chunk_ranking(loaded: Loaded, query: str, k: int) -> list[tuple[int, float]]:
    """The two-round fetch and the engine's scorer: top-``k`` ``(chunk_id, score)``."""
    storage, epoch = loaded.storage, loaded.epoch
    tables, budget = storage._host.tables, storage._host.membership_budget
    postings = tables.lex_postings
    columns = (postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)
    terms = list(dict.fromkeys(tokenize(query)))
    async with storage._host.session_factory() as session:
        stats = await lexical_stats(session, tables, epoch, terms, budget)
        present = [term for term in terms if term in stats.terms]
        if not present:
            return []
        summaries = {term: decode_summary(stats.terms[term].blocks) for term in present}
        idfs = [stats.terms[term].idf for term in present]
        index = {term: position for position, term in enumerate(present)}

        def as_blocks(rows: Sequence[Any]) -> list[ScoreBlock]:
            return [
                ScoreBlock(
                    index[r.term],
                    summaries[r.term].max_weights[r.block_no],
                    bytes(r.doc_ids),
                    bytes(r.tfs),
                    bytes(r.dls),
                )
                for r in rows
            ]

        blocks: list[ScoreBlock] = []
        for probe in chunked(present, budget):
            head = select(*columns).where(
                postings.c.epoch == epoch, postings.c.term.in_(probe), postings.c.block_no < HEAD_BLOCKS
            )
            blocks += as_blocks((await session.execute(head)).all())
        everything = score_blocks(blocks, idfs, stats.avg_dl, 10**9)
        theta = everything[k - 1][1] if len(everything) >= k else 0.0
        score_of = dict(everything)
        candidates = array("q", sorted(score_of))
        tail = array("d", [score_of[chunk] for chunk in candidates])
        overflowing = [term for term in present if len(summaries[term].first_ids) > HEAD_BLOCKS]
        selected = select_blocks([summaries[term] for term in overflowing], candidates, tail, theta)
        arms = []
        for term, competing in zip(overflowing, selected, strict=True):
            wanted = [no for no in competing if no >= HEAD_BLOCKS]
            arms.extend(
                and_(postings.c.epoch == epoch, postings.c.term == term, postings.c.block_no.in_(list(nos)))
                for nos in chunked(wanted, budget)
            )
        if arms:
            blocks += as_blocks((await session.execute(select(*columns).where(or_(*arms)))).all())
        return score_blocks(blocks, idfs, stats.avg_dl, k)
