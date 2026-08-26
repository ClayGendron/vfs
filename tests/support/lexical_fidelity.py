"""The lexical index's fidelity referee, shared by the sqlite and engine legs.

Scores a fixture corpus two ways — summing the stored weights in SQL
the way the glean leg will, and a pure-Python BM25 written here from
the tokens alone — and requires the same top-10 and a Kendall τ of 1.0
over every scored chunk. The pure scorer is deliberately independent
of the builder: it recomputes tf, dl, df, N, and avg_dl from
:func:`~vfs.models.lexical.tokenize` and spells the formula out, so a
build-side slip (a wrong dl, a stale df) fails here.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from vfs.models import Entry
from vfs.models.lexical import BM25_B, BM25_K1, tokenize
from vfs.paths import Path

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


async def assert_lexical_fidelity(storage: DatabaseStorage) -> None:
    """Write the corpus, reindex, and referee the stored weights against pure BM25."""
    entries = [Entry(path=Path(path), content=text) for path, text in CORPUS.items()]
    assert (await storage.write(entries=entries, parents=True)).success is True
    assert (await storage.reindex()).success is True
    tables = storage._host.tables
    entry, chunks, terms, meta = tables.entry, tables.chunks, tables.lex_terms, tables.meta
    async with storage._host.engine.connect() as conn:
        epoch = (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()
        located = select(chunks.c.id, entry.c.path).select_from(
            chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
        )
        path_of: dict[int, str] = {row.id: row.path for row in await conn.execute(located)}
        assert len(path_of) == len(CORPUS)  # one chunk per fixture body
        for query in QUERIES:
            probe = list(dict.fromkeys(tokenize(query)))
            scored = (
                select(terms.c.chunk_id, func.sum(terms.c.weight).label("score"))
                .where(terms.c.epoch == epoch, terms.c.term.in_(probe))
                .group_by(terms.c.chunk_id)
            )
            in_sql = {path_of[chunk_id]: float(score) for chunk_id, score in await conn.execute(scored)}
            in_python = pure_bm25(CORPUS, query)
            assert set(in_sql) == set(in_python), query
            for path, score in in_sql.items():
                assert math.isclose(score, in_python[path], rel_tol=1e-9), (query, path)
            # Rounding before ordering: the engines' float sums may differ in the last ulp.
            sql_order = sorted(in_sql, key=lambda p: (-round(in_sql[p], 9), p))
            python_order = sorted(in_python, key=lambda p: (-round(in_python[p], 9), p))
            assert sql_order[:10] == python_order[:10], query
            assert kendall_tau(sql_order, python_order) == 1.0, query
