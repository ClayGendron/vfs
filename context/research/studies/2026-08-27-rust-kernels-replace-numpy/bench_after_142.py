"""After spec 142: the shipped lexical kernels on the full linux store.

The three-arm scripts reached into numpy internals spec 142 deleted;
this one measures the product as it ships — ``decode_summary``,
``competing_blocks`` and ``score_blocks`` from ``vfs.models.lexical`` —
on the same query draw (``draw_queries``, seed 7, plus the all-common
``struct if`` shape) and the same two-round search as
``bench_e2e_lexical.py``. Compare against ``results/lexical_sites.json``
and ``results/e2e_lexical.json`` (their numpy rows) for the before.

    VFS_BENCH_DB=/path/to/landing_full.sqlite uv run python bench_after_142.py
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
import statistics
import time
from array import array

from benchlib import DB, dump, machine, timed_ms
from sqlalchemy import and_, or_, select

from vfs import _native
from vfs.models.lexical import ScoreBlock, competing_blocks, decode_summary, score_blocks
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.lexical import lexical_stats

HEAD_BLOCKS = 8
PER_ARITY = 10
RUNS = 5


def draw_queries(con: sqlite3.Connection, seed: int = 7) -> dict[str, list[list[str]]]:
    n = con.execute("SELECT n_docs FROM vfs_lex_stats").fetchone()[0]
    rows = con.execute("SELECT term, df FROM vfs_lex_df").fetchall()
    mid = [t for t, df in rows if 0.002 * n <= df <= 0.02 * n]
    common = [t for t, df in rows if df > 0.2 * n]
    rare = [t for t, df in rows if 2 <= df < 0.002 * n]
    rng = random.Random(seed)
    out: dict[str, list[list[str]]] = {"1": [], "3": [], "6": []}
    for _ in range(PER_ARITY):
        out["1"].append([rng.choice(mid)])
        out["3"].append(rng.sample(mid, 2) + [rng.choice(common)])
        out["6"].append([rng.choice(rare)] + rng.sample(mid, 4) + [rng.choice(common)])
    return out


async def search(storage, epoch, terms, k):
    """The ADR 055 two-round search, SQL and compute bucketed apart."""
    tables = storage._host.tables
    postings = tables.lex_postings
    sql = compute = 0.0
    async with storage._host.session_factory() as session:
        t = time.perf_counter()
        stats = await lexical_stats(session, tables, epoch, terms, 500)
        present = [x for x in terms if x in stats.terms]
        heads_stmt = select(
            postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls
        ).where(postings.c.epoch == epoch, postings.c.term.in_(present), postings.c.block_no < HEAD_BLOCKS)
        head_rows = (await session.execute(heads_stmt)).all()
        sql += time.perf_counter() - t
        t = time.perf_counter()
        summaries = {x: decode_summary(stats.terms[x].blocks) for x in present}
        idfs = [stats.terms[x].idf for x in present]
        index = {x: i for i, x in enumerate(present)}
        blocks = [
            ScoreBlock(index[r.term], summaries[r.term].max_weights[r.block_no], bytes(r.doc_ids), bytes(r.tfs), bytes(r.dls))
            for r in head_rows
        ]
        everything = score_blocks(blocks, idfs, stats.avg_dl, 10**9)
        theta = everything[k - 1][1] if len(everything) >= k else 0.0
        scores_of = dict(everything)
        cands = array("q", sorted(scores_of))
        tail = array("d", [scores_of[c] for c in cands])
        overflowing = sorted(
            (x for x in present if len(summaries[x].first_ids) > HEAD_BLOCKS), key=lambda x: -max(summaries[x].max_weights)
        )
        wanted = []
        for i, term in enumerate(overflowing):
            rest = sum(max(summaries[o].max_weights) for o in overflowing[i + 1 :])
            competing = [no for no in competing_blocks(summaries[term], cands, tail, theta, rest) if no >= HEAD_BLOCKS]
            if competing:
                wanted.append((term, competing))
        compute += time.perf_counter() - t
        if wanted:
            t = time.perf_counter()
            arms = [
                and_(postings.c.epoch == epoch, postings.c.term == term, postings.c.block_no.in_(nos)) for term, nos in wanted
            ]
            stmt = select(postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls).where(
                or_(*arms)
            )
            more = (await session.execute(stmt)).all()
            sql += time.perf_counter() - t
            t = time.perf_counter()
            blocks += [
                ScoreBlock(index[r.term], summaries[r.term].max_weights[r.block_no], bytes(r.doc_ids), bytes(r.tfs), bytes(r.dls))
                for r in more
            ]
            compute += time.perf_counter() - t
        t = time.perf_counter()
        top = score_blocks(blocks, idfs, stats.avg_dl, k)
        compute += time.perf_counter() - t
    return top, sql, compute, len(blocks), sum(len(n) for _, n in wanted), summaries, cands, tail, theta


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    queries = draw_queries(con)
    queries["all_common"] = [[t for t, _ in con.execute("SELECT term, df FROM vfs_lex_df ORDER BY df DESC LIMIT 2")]]
    async with storage._host.session_factory() as session:
        epoch = await current_epoch(session, storage._host.tables)
        # Site 3 and 4 micro-shapes: the all-common summaries and a 6-term selection.
        common_terms = queries["all_common"][0]
        stats = await lexical_stats(session, storage._host.tables, epoch, common_terms, 500)
        sblobs = [stats.terms[t].blocks for t in common_terms if t in stats.terms]
    total_blocks = sum(len(decode_summary(b).first_ids) for b in sblobs)
    sites = {
        "summary_blocks": total_blocks,
        "summary_decode_ms": timed_ms(lambda: [decode_summary(b) for b in sblobs]),
    }
    six = queries["6"][0]
    _top, _sql, _compute, _n, _r2, summaries, cands, tail, theta = await search(storage, epoch, six, 1000)
    cands = array("q", cands[:5000])
    tail = array("d", tail[:5000])
    sites["selection_terms"] = len(summaries)
    sites["selection_candidates"] = len(cands)
    sites["selection_ms"] = timed_ms(
        lambda: [competing_blocks(summary, cands, tail, theta, 0.0) for summary in summaries.values()]
    )
    print(f"site3 summary decode, {total_blocks:,} blocks: {sites['summary_decode_ms']:.3f} ms")
    print(f"site4 selection, {len(summaries)} terms x {len(cands):,} cands: {sites['selection_ms']:.3f} ms")

    rows = []
    for arity, qs in queries.items():
        for terms in qs:
            for k in (10, 1000):
                await search(storage, epoch, terms, k)  # warm
                samples = [await search(storage, epoch, terms, k) for _ in range(RUNS)]
                rows.append(
                    {
                        "arity": arity,
                        "terms": terms,
                        "k": k,
                        "total_ms": round(statistics.median(s[1] + s[2] for s in samples) * 1000, 3),
                        "sql_ms": round(statistics.median(s[1] for s in samples) * 1000, 3),
                        "compute_ms": round(statistics.median(s[2] for s in samples) * 1000, 3),
                        "blocks_scored": samples[0][3],
                        "round2_blocks": samples[0][4],
                    }
                )
    summary = {}
    for arity in queries:
        for k in (10, 1000):
            sub = [r for r in rows if r["arity"] == arity and r["k"] == k]
            summary[f"{arity}@{k}"] = {
                "total_ms": round(statistics.median(r["total_ms"] for r in sub), 3),
                "compute_ms": round(statistics.median(r["compute_ms"] for r in sub), 3),
                "sql_ms": round(statistics.median(r["sql_ms"] for r in sub), 3),
            }
            print(f"e2e {arity:>10}@{k:<5} total={summary[f'{arity}@{k}']['total_ms']:.2f} ms  compute={summary[f'{arity}@{k}']['compute_ms']:.2f}  sql={summary[f'{arity}@{k}']['sql_ms']:.2f}")
    await storage.close()
    dump(
        "after-142.json",
        {"machine": machine(), "protocol": _native.PROTOCOL_VERSION, "sites": sites, "summary": summary, "rows": rows},
    )


if __name__ == "__main__":
    asyncio.run(main())
