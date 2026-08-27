"""End-to-end lexical search (the ADR 055 two-round protocol) under three arms.

No lexical verb exists yet (spec 132 is pending), so this drives the
storage the way spec 132 will: the ``lex_df`` probe + head fetch
(``block_no < 8``), score, ``competing_blocks`` per overflowing term,
the keyed round-two fetch, the final score. Per arm the three compute
sites swap — summary decode (site 3), block selection (site 4), the
scorer (site 5) — and SQL time is bucketed apart from compute time.
Final top-k lists are asserted identical across arms.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import vfs_kernels_rs as rs
from sqlalchemy import and_, or_, select

import kernels_py as kp
from bench_lexical_sites import HEAD_BLOCKS, draw_queries
from benchlib import DB, dump, machine
from vfs import _native
from vfs.models.lexical import ScoreBlock, competing_blocks, decode_summary, pure_score_blocks
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.lexical import lexical_stats

import sqlite3

RUNS = 5


class Arm:
    def __init__(self, name: str) -> None:
        self.name = name

    def summary(self, blob: bytes):
        if self.name == "numpy":
            s = decode_summary(blob)
            return s.first_ids, s.max_weights
        if self.name == "stdlib":
            return kp.decode_summary(blob)
        f, m = rs.decode_summary(blob)
        fa, ma = array("q"), array("d")
        fa.frombytes(f)
        ma.frombytes(m)
        return fa, ma

    def score(self, blocks, idfs, avg_dl, k):
        if self.name == "numpy":
            return pure_score_blocks(blocks, idfs, avg_dl, k)
        if self.name == "stdlib":
            return kp.score_blocks_skip(blocks, idfs, avg_dl, k)
        return _native.lexical_score(blocks, idfs, avg_dl, k)

    def select(self, summary, cands, tail, theta, rest):
        firsts, maxes = summary
        if self.name == "numpy":
            from vfs.models.lexical import BlockSummary

            return competing_blocks(
                BlockSummary(firsts, maxes), np.asarray(cands, dtype=np.int64), np.asarray(tail), theta, rest
            ).tolist()
        if self.name == "stdlib":
            return kp.competing_blocks(firsts, maxes, cands, tail, theta, rest)
        return kp.from_q(rs.competing_blocks(firsts.tobytes(), maxes.tobytes(), kp.to_q(cands), kp.to_d(tail), theta, rest))


async def search(storage, epoch, terms, k, arm: Arm):
    tables = storage._host.tables
    postings = tables.lex_postings
    sql = compute = 0.0
    async with storage._host.session_factory() as session:
        t = time.perf_counter()
        stats = await lexical_stats(session, tables, epoch, terms, 500)
        present = [x for x in terms if x in stats.terms]
        heads_stmt = (
            select(postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)
            .where(postings.c.epoch == epoch, postings.c.term.in_(present), postings.c.block_no < HEAD_BLOCKS)
        )
        head_rows = (await session.execute(heads_stmt)).all()
        sql += time.perf_counter() - t
        t = time.perf_counter()
        summaries = {x: arm.summary(stats.terms[x].blocks) for x in present}
        idfs = [stats.terms[x].idf for x in present]
        index = {x: i for i, x in enumerate(present)}
        blocks = [
            ScoreBlock(index[r.term], float(summaries[r.term][1][r.block_no]), bytes(r.doc_ids), bytes(r.tfs), bytes(r.dls))
            for r in head_rows
        ]
        everything = arm.score(blocks, idfs, stats.avg_dl, 10**9)
        theta = everything[k - 1][1] if len(everything) >= k else 0.0
        scores_of = dict(everything)
        cands = sorted(scores_of)
        tail = [scores_of[c] for c in cands]
        overflowing = sorted((x for x in present if len(summaries[x][0]) > HEAD_BLOCKS), key=lambda x: -max(summaries[x][1]))
        wanted = []
        for i, term in enumerate(overflowing):
            rest = sum(max(summaries[o][1]) for o in overflowing[i + 1 :])
            competing = [no for no in arm.select(summaries[term], cands, tail, theta, rest) if no >= HEAD_BLOCKS]
            if competing:
                wanted.append((term, competing))
        compute += time.perf_counter() - t
        if wanted:
            t = time.perf_counter()
            arms = [and_(postings.c.epoch == epoch, postings.c.term == term, postings.c.block_no.in_(nos)) for term, nos in wanted]
            stmt = select(postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls).where(or_(*arms))
            more = (await session.execute(stmt)).all()
            sql += time.perf_counter() - t
            t = time.perf_counter()
            blocks += [
                ScoreBlock(index[r.term], float(summaries[r.term][1][r.block_no]), bytes(r.doc_ids), bytes(r.tfs), bytes(r.dls))
                for r in more
            ]
            compute += time.perf_counter() - t
        t = time.perf_counter()
        top = arm.score(blocks, idfs, stats.avg_dl, k)
        compute += time.perf_counter() - t
    return top, sql, compute, len(blocks), sum(len(n) for _, n in wanted)


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    queries = draw_queries(con)
    queries["all_common"] = [[t for t, _ in con.execute("SELECT term, df FROM vfs_lex_df ORDER BY df DESC LIMIT 2")]]
    async with storage._host.session_factory() as session:
        epoch = await current_epoch(session, storage._host.tables)
    arms = [Arm("numpy"), Arm("stdlib"), Arm("rust")]
    rows = []
    for arity, qs in queries.items():
        for terms in qs:
            for k in (10, 1000):
                tops = {}
                per_arm = {}
                for arm in arms:
                    await search(storage, epoch, terms, k, arm)  # warm
                    samples = [await search(storage, epoch, terms, k, arm) for _ in range(RUNS)]
                    tops[arm.name] = samples[0][0]
                    per_arm[arm.name] = {
                        "total_ms": round(statistics.median(s[1] + s[2] for s in samples) * 1000, 3),
                        "sql_ms": round(statistics.median(s[1] for s in samples) * 1000, 3),
                        "compute_ms": round(statistics.median(s[2] for s in samples) * 1000, 3),
                        "blocks_scored": samples[0][3],
                        "round2_blocks": samples[0][4],
                    }
                assert tops["numpy"] == tops["stdlib"] == tops["rust"], (terms, k)
                rows.append({"arity": arity, "terms": terms, "k": k, "arms": per_arm})
    summary = {}
    for arity in queries:
        for k in (10, 1000):
            sub = [r for r in rows if r["arity"] == arity and r["k"] == k]
            summary[f"{arity}@k{k}"] = {
                arm: {key: round(statistics.median(r["arms"][arm][key] for r in sub), 3) for key in sub[0]["arms"][arm]}
                for arm in ("numpy", "stdlib", "rust")
            }
            s = summary[f"{arity}@k{k}"]
            print(
                f"{arity:<10} k={k:<5} blocks={s['numpy']['blocks_scored']:>6.0f} r2={s['numpy']['round2_blocks']:>5.0f} | "
                f"np total={s['numpy']['total_ms']:.1f} (sql {s['numpy']['sql_ms']:.1f}, compute {s['numpy']['compute_ms']:.1f}) | "
                f"py total={s['stdlib']['total_ms']:.1f} (compute {s['stdlib']['compute_ms']:.1f}) | "
                f"rs total={s['rust']['total_ms']:.1f} (compute {s['rust']['compute_ms']:.1f}) ms",
                flush=True,
            )
    await storage.close()
    dump("e2e_lexical.json", {"machine": machine(), "runs": RUNS, "summary": summary, "rows": rows})


asyncio.run(main())
