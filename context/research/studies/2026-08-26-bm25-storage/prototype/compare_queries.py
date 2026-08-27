"""Lexical two-round query (real SQL, both rounds) vs the grep verb on the same store.

    uv run --no-sync python compare_queries.py <store.sqlite>
"""

from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import statistics
import sys
import time

import numpy as np
from sqlalchemy import and_, or_, select

from vfs.models.lexical import ScoreBlock, competing_blocks, decode_summary, score_blocks
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.lexical import lexical_stats

HEAD_BLOCKS = 8
DB = sys.argv[1]


def draw_queries(con: sqlite3.Connection, seed: int = 7, per_arity: int = 15) -> dict[int, list[list[str]]]:
    n = con.execute("SELECT n_docs FROM vfs_lex_stats").fetchone()[0]
    rows = con.execute("SELECT term, df FROM vfs_lex_df").fetchall()
    mid = [t for t, df in rows if 0.002 * n <= df <= 0.02 * n]
    common = [t for t, df in rows if df > 0.2 * n]
    rare = [t for t, df in rows if 2 <= df < 0.002 * n]
    rng = random.Random(seed)
    out: dict[int, list[list[str]]] = {1: [], 3: [], 6: []}
    for _ in range(per_arity):
        out[1].append([rng.choice(mid)])
        out[3].append(rng.sample(mid, 2) + [rng.choice(common)])
        out[6].append([rng.choice(rare)] + rng.sample(mid, 4) + [rng.choice(common)])
    return out


def to_blocks(rows, present, summaries) -> list[ScoreBlock]:
    return [
        ScoreBlock(
            present.index(r.term),
            float(summaries[r.term].max_weights[r.block_no]),
            bytes(r.doc_ids),
            bytes(r.tfs),
            bytes(r.dls),
        )
        for r in rows
    ]


async def lexical_query(storage: DatabaseStorage, epoch: int, terms: list[str], k: int) -> dict:
    """Round one: summary probe + head fetch. Round two: competing blocks per overflowing term."""
    tables = storage._host.tables
    p = tables.lex_postings
    cols = (p.c.term, p.c.block_no, p.c.doc_ids, p.c.tfs, p.c.dls)
    t0 = time.perf_counter()
    async with storage._host.session_factory() as session:
        stats = await lexical_stats(session, tables, epoch, terms, 500)
        present = [t for t in terms if t in stats.terms]
        if not present:
            return {"ms": (time.perf_counter() - t0) * 1000, "rounds": 1, "blocks": 0, "bytes": 0}
        summaries = {t: decode_summary(stats.terms[t].blocks) for t in present}
        idfs = [stats.terms[t].idf for t in present]
        head = select(*cols).where(p.c.epoch == epoch, p.c.term.in_(present), p.c.block_no < HEAD_BLOCKS)
        fetched = to_blocks((await session.execute(head)).all(), present, summaries)
        t_round1 = time.perf_counter()
        overflowing = sorted(
            (t for t in present if len(summaries[t].max_weights) > HEAD_BLOCKS),
            key=lambda t: -float(summaries[t].max_weights.max()),
        )
        wanted: list = []
        for position, term in enumerate(overflowing):
            everything = score_blocks(fetched, idfs, stats.avg_dl, 10**9)
            ranked = everything[:k]
            theta = ranked[-1][1] if len(ranked) == k else 0.0
            candidates = np.array(sorted(c for c, _ in everything), dtype=np.int64)
            scores_of = dict(everything)
            tail = np.array([scores_of[c] for c in candidates.tolist()], dtype=np.float64)
            rest = sum(float(summaries[o].max_weights.max()) for o in overflowing[position + 1 :])
            competing = [n for n in competing_blocks(summaries[term], candidates, tail, theta, rest).tolist() if n >= HEAD_BLOCKS]
            if competing:
                wanted.append(and_(p.c.epoch == epoch, p.c.term == term, p.c.block_no.in_(competing)))
        rounds = 1
        if wanted:
            rounds = 2
            second = select(*cols).where(or_(*wanted))
            fetched += to_blocks((await session.execute(second)).all(), present, summaries)
        top = score_blocks(fetched, idfs, stats.avg_dl, k)
    ms = (time.perf_counter() - t0) * 1000
    return {
        "ms": ms,
        "round1_ms": (t_round1 - t0) * 1000,
        "rounds": rounds,
        "blocks": len(fetched),
        "bytes": sum(len(b.doc_ids) + len(b.tfs) + len(b.dls) for b in fetched),
        "hits": len(top),
    }


async def grep_query(storage: DatabaseStorage, pattern: str, mode: str) -> dict:
    t0 = time.perf_counter()
    result = await storage.grep(pattern=pattern, fixed_strings=True, output_mode=mode)
    ms = (time.perf_counter() - t0) * 1000
    assert result.success, (pattern, result.errors)
    return {"ms": ms, "observations": len(result.observations), "warnings": len(result.errors)}


def med(rows: list[dict], key: str) -> float:
    return round(statistics.median(r[key] for r in rows), 2)


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    con = sqlite3.connect(DB)
    epoch = con.execute("SELECT current_gram_epoch FROM vfs_meta").fetchone()[0]
    queries = draw_queries(con)
    con.close()
    out: dict = {}
    for arity, qs in queries.items():
        for k in (10, 1000):
            rows = []
            for terms in qs:
                await lexical_query(storage, epoch, terms, k)  # warm
                rows.append(await lexical_query(storage, epoch, terms, k))
            out[f"lexical_{arity}terms_k{k}"] = {
                "ms_median": med(rows, "ms"),
                "ms_max": round(max(r["ms"] for r in rows), 2),
                "round1_ms_median": med(rows, "round1_ms"),
                "two_rounds_pct": round(100 * sum(r["rounds"] == 2 for r in rows) / len(rows)),
                "blocks_median": med(rows, "blocks"),
                "kb_median": round(med(rows, "bytes") / 1024, 1),
            }
            print(f"lexical {arity} terms k={k}: {out[f'lexical_{arity}terms_k{k}']}", flush=True)
    # grep: the same single mid-frequency terms as fixed strings, and the 3-term
    # query's rarest term — what a grep user would type for the same intent.
    singles = [q[0] for q in queries[1]]
    for mode in (() if "--no-grep" in sys.argv else ("files", "lines")):
        rows = []
        for term in singles:
            await grep_query(storage, term, mode)
            rows.append(await grep_query(storage, term, mode))
        out[f"grep_1term_{mode}"] = {
            "ms_median": med(rows, "ms"),
            "ms_max": round(max(r["ms"] for r in rows), 2),
            "observations_median": med(rows, "observations"),
            "truncated": sum(r["warnings"] > 0 for r in rows),
        }
        print(f"grep 1 term {mode}: {out[f'grep_1term_{mode}']}", flush=True)
    print(json.dumps(out, indent=1))
    await storage.close()


asyncio.run(main())
