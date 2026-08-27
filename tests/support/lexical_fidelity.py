"""The lexical index's fidelity referee, shared by the sqlite and engine legs.

Scores a fixture corpus two ways — through the stored blocks and the
active engine's scorer, the way the glean leg will, and a pure-Python
BM25 written here from the tokens alone — and requires the same top-10
and a Kendall τ of 1.0 over every scored chunk. The pure scorer is
deliberately independent of the builder: it recomputes tf, dl, df, N,
and avg_dl from :func:`~vfs.models.lexical.tokenize` and spells the
formula out, so a build-side slip (a wrong dl, a stale df) fails here.

The second referee proves the two-round fetch on a corpus whose common
terms span blocks: the head blocks plus the blocks
:func:`~vfs.models.lexical.competing_blocks` selects must rank exactly
as the whole fetch, at k = 10 and at a fusion-sized K.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import select

from vfs.models import Entry
from vfs.models.lexical import (
    BM25_B,
    BM25_K1,
    BlockSummary,
    ScoreBlock,
    competing_blocks,
    decode_summary,
    pure_score_blocks,
    score_blocks,
    tokenize,
)
from vfs.paths import Path
from vfs.storage.backends.database.lexical import lexical_stats

if TYPE_CHECKING:
    from vfs.storage.backends.database import DatabaseStorage

# Fixture corpus: overlapping vocabulary across code and prose so every
# query scores several chunks with distinct, length-normalised weights.
_SUBJECTS = ("parser", "lexer", "scheduler", "allocator", "cache", "router")
_VERBS = ("build", "flush", "resolve", "encode", "publish")

CORPUS: dict[str, str] = {}
for i, subject in enumerate(_SUBJECTS):
    for j, verb in enumerate(_VERBS):
        body = [f"def {verb}_{subject}(self, budget):"]
        body += [f"    {subject}_state = self.{subject}.{verb}(budget)"] * (1 + (i + j) % 3)
        body += [f"    # {verb} the {subject} under the budget; retries on conflict"] * (1 + j % 2)
        if (i + j) % 4 == 0:
            body.append("    raise ConflictError('rival publish')")
        CORPUS[f"/src/{subject}/{verb}.py"] = "\n".join(body) + "\n"
CORPUS["/docs/README.md"] = "The scheduler publishes and the allocator flushes; the cache is a cache.\n"
CORPUS["/docs/design.md"] = "Parser and lexer resolve tokens; the router encodes routes.\n"

QUERIES = ("flush cache", "publish scheduler budget", "ConflictError rival", "resolve", "the cache", "PublishRouter")

# The two-round corpus: `page` and `body` in every document (several
# blocks each), a rotating mid term, and a rare term in eleven documents
# of the first two blocks — so a top-10 anchored by it leaves the common
# terms' later blocks unfetched, while a K past the corpus fetches all.
SPANNING_QUERIES = ("rare_marker page body", "term3 page", "page body")
HEAD_BLOCKS = 2  # the referee's head, small enough that the corpus overflows it


def spanning_corpus(count: int) -> dict[str, str]:
    return {
        f"/p/{i:04}.txt": f"page body {i} term{i % 7}{' rare_marker' if i % 23 == 5 and i < 250 else ''}"
        + " word" * (i % 9)
        + "\n"
        for i in range(count)
    }


def pure_bm25(corpus: dict[str, str], query: str) -> dict[str, float]:
    """Score every document of *corpus* for *query* with a from-scratch BM25."""
    tokens = {path: tokenize(text) for path, text in corpus.items()}
    n_docs = len(tokens)
    avg_dl = sum(len(t) for t in tokens.values()) / n_docs
    terms = list(dict.fromkeys(tokenize(query)))
    scores: dict[str, float] = {}
    for term in terms:
        df = sum(1 for t in tokens.values() if term in t)
        if df == 0:
            continue
        term_idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        for path, doc_tokens in tokens.items():
            tf = doc_tokens.count(term)
            if tf:
                dl = len(doc_tokens)
                scores[path] = scores.get(path, 0.0) + term_idf * tf * (BM25_K1 + 1) / (
                    tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avg_dl)
                )
    return scores


def kendall_tau(left: list[str], right: list[str]) -> float:
    """Kendall's τ between two orderings of the same items (1.0 = identical)."""
    assert sorted(left) == sorted(right)
    position = {item: index for index, item in enumerate(right)}
    concordant = discordant = 0
    for i in range(len(left)):
        for j in range(i + 1, len(left)):
            if position[left[i]] < position[left[j]]:
                concordant += 1
            else:
                discordant += 1
    pairs = concordant + discordant
    return 1.0 if pairs == 0 else (concordant - discordant) / pairs


async def fetch_query(
    storage: DatabaseStorage, epoch: int, query: str
) -> tuple[list[ScoreBlock], list[float], float, dict]:
    """Every block of the query's terms as scorer input, plus idfs, avg_dl
    and each term's ``(index, summary)`` — the whole fetch, no rounds."""
    tables = storage._host.tables
    postings = tables.lex_postings
    probe = list(dict.fromkeys(tokenize(query)))
    async with storage._host.session_factory() as session:
        stats = await lexical_stats(session, tables, epoch, probe, 100)
        terms = [t for t in probe if t in stats.terms]
        summaries = {t: decode_summary(stats.terms[t].blocks) for t in terms}
        fetched = (
            select(postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)
            .where(postings.c.epoch == epoch, postings.c.term.in_(terms))
            .order_by(postings.c.term, postings.c.block_no)
        )
        blocks: list[ScoreBlock] = []
        for row in await session.execute(fetched):
            index = terms.index(row.term)
            bound = float(summaries[row.term].max_weights[row.block_no])
            blocks.append(ScoreBlock(index, bound, bytes(row.doc_ids), bytes(row.tfs), bytes(row.dls)))
    blocks.sort(key=lambda b: b.term)  # term order as indexed; block order kept within a term
    idfs = [stats.terms[t].idf for t in terms]
    return blocks, idfs, stats.avg_dl, {t: (i, summaries[t]) for i, t in enumerate(terms)}


async def _write_and_index(storage: DatabaseStorage, corpus: dict[str, str]) -> tuple[int, dict[int, str]]:
    entries = [Entry(path=Path(path), content=text) for path, text in corpus.items()]
    assert (await storage.write(entries=entries, parents=True)).success is True
    assert (await storage.reindex()).success is True
    tables = storage._host.tables
    entry, chunks, meta = tables.entry, tables.chunks, tables.meta
    async with storage._host.engine.connect() as conn:
        epoch = (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()
        located = select(chunks.c.id, entry.c.path).select_from(
            chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
        )
        path_of: dict[int, str] = {row.id: row.path for row in await conn.execute(located)}
    assert len(path_of) == len(corpus)  # one chunk per fixture body
    return epoch, path_of


async def assert_lexical_fidelity(storage: DatabaseStorage) -> None:
    """Write the corpus, reindex, and referee both scorers against pure BM25."""
    epoch, path_of = await _write_and_index(storage, CORPUS)
    for query in QUERIES:
        blocks, idfs, avg_dl, _summaries = await fetch_query(storage, epoch, query)
        in_python = pure_bm25(CORPUS, query)
        for scorer in (score_blocks, pure_score_blocks):
            ranked = scorer(blocks, idfs, avg_dl, len(path_of))
            scored = {path_of[chunk_id]: score for chunk_id, score in ranked}
            assert set(scored) == set(in_python), query
            for path, score in scored.items():
                assert math.isclose(score, in_python[path], rel_tol=1e-9), (query, path)
            # Rounding before ordering: the engines' float sums may differ in the last ulp.
            engine_order = sorted(scored, key=lambda p: (-round(scored[p], 9), p))
            python_order = sorted(in_python, key=lambda p: (-round(in_python[p], 9), p))
            assert engine_order[:10] == python_order[:10], query
            assert kendall_tau(engine_order, python_order) == 1.0, query


async def assert_two_round_fidelity(storage: DatabaseStorage, count: int = 300) -> None:
    """Write a block-spanning corpus, reindex, and prove the two-round fetch:
    head blocks plus the selected blocks rank exactly as the whole fetch."""
    epoch, path_of = await _write_and_index(storage, spanning_corpus(count))
    skipped: dict[str, int] = {}
    for query in SPANNING_QUERIES:
        blocks, idfs, avg_dl, summaries = await fetch_query(storage, epoch, query)
        assert any(summary.first_ids.size > HEAD_BLOCKS for _i, summary in summaries.values())
        for k in (10, 1000):
            whole = score_blocks(blocks, idfs, avg_dl, k)
            selected = _two_round(blocks, idfs, avg_dl, k, summaries)
            skipped[f"{query}@{k}"] = len(blocks) - len(selected)
            assert score_blocks(selected, idfs, avg_dl, k) == whole, (query, k)
        # The referee against pure BM25 holds on this corpus too.
        in_python = pure_bm25(spanning_corpus(count), query)
        ranked = {path_of[c]: s for c, s in score_blocks(blocks, idfs, avg_dl, len(path_of))}
        assert all(math.isclose(ranked[p], in_python[p], rel_tol=1e-9) for p in in_python)
    # The rare-anchored top-10 leaves the common terms' tail blocks in the
    # engine; a K past the corpus size (θ = 0) fetches everything.
    assert skipped["rare_marker page body@10"] > 0
    assert all(count == 0 for key, count in skipped.items() if key.endswith("@1000"))


def _two_round(blocks: list[ScoreBlock], idfs: list[float], avg_dl: float, k: int, summaries: dict) -> list[ScoreBlock]:
    """Round one: every term's head; round two: the competing blocks of
    each overflowing term, one term at a time in descending maximum."""
    by_term: dict[int, list[ScoreBlock]] = {}
    for block in blocks:
        by_term.setdefault(block.term, []).append(block)
    fetched = [b for term, bs in by_term.items() for b in bs[:HEAD_BLOCKS]]
    overflowing = sorted(
        (term for term, bs in by_term.items() if len(bs) > HEAD_BLOCKS),
        key=lambda term: -float(summaries_of(summaries, term).max_weights.max()),
    )
    for position, term in enumerate(overflowing):
        ranked = score_blocks(fetched, idfs, avg_dl, k)
        theta = ranked[-1][1] if len(ranked) == k else 0.0
        candidates = np.array(sorted(chunk for chunk, _ in score_blocks(fetched, idfs, avg_dl, 10**9)), dtype=np.int64)
        scores = dict(score_blocks(fetched, idfs, avg_dl, 10**9))
        rest = sum(float(summaries_of(summaries, other).max_weights.max()) for other in overflowing[position + 1 :])
        tail = np.array([scores[c] for c in candidates.tolist()], dtype=np.float64)
        competing = competing_blocks(summaries_of(summaries, term), candidates, tail, theta, rest)
        fetched += [by_term[term][no] for no in competing.tolist() if no >= HEAD_BLOCKS]
    return fetched


def summaries_of(summaries: dict, term: int) -> BlockSummary:
    return next(summary for index, summary in summaries.values() if index == term)
