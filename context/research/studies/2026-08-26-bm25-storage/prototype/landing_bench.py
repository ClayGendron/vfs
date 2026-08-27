"""Spec 130 landing measurements on the linux checkout, through the live tree.

Loads a seeded sample (or the whole checkout with ``--all``) into a
sqlite ``DatabaseStorage``, then measures the shipped implementation:

- build: reindex wall with and without the lexical build, the tokenizer's
  share (the active engine's tokenizer over every chunk), peak RSS;
- size: index bytes per table (sqlite ``dbstat``), bytes per posting and
  per chunk, the ratio to content bytes;
- query: Rust vs numpy scorer time at 1/3/6 terms on the benchmark's
  drawn queries, and the two-round fetch's round-two blocks and bytes at
  k = 10 and K = 1000 — plus an adversarial all-common query.

    uv run --no-sync python landing_bench.py --files 4000 --seed 7
    uv run --no-sync python landing_bench.py --all --db /tmp/linux_full.sqlite
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import resource
import sqlite3
import statistics
import time
from pathlib import Path as FsPath

import numpy as np
from sqlalchemy import select

import vfs.native as native
from vfs import _native
from vfs.models import Entry
from vfs.models import lexical as lexical_model
from vfs.models.lexical import (
    ScoreBlock,
    competing_blocks,
    decode_summary,
    pure_score_blocks,
    pure_tokenize,
    score_blocks,
    tokenize,
)
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database.lexical import lexical_stats

LINUX = FsPath.home() / "Git/Repos/linux"
EXTS = {".c", ".h", ".py", ".rst", ".txt", ".md", ".S", ".sh", ".yaml", ".json"}
HEAD_BLOCKS = 8
RESULTS = FsPath(__file__).resolve().parent / "results"


def sample_files(n: int | None, seed: int) -> list[FsPath]:
    files = sorted(p for p in LINUX.rglob("*") if p.is_file() and p.suffix in EXTS and ".git" not in p.parts)
    if n is None:
        return files
    return random.Random(seed).sample(files, min(n, len(files)))


async def load(storage: DatabaseStorage, files: list[FsPath]) -> int:
    total = 0
    batch: list[Entry] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text or not text:
            continue
        total += len(text.encode())
        batch.append(Entry(path=Path("/" + path.relative_to(LINUX).as_posix()), content=text))
        if len(batch) == 1000:
            assert (await storage.write(entries=batch, parents=True)).success
            batch = []
    if batch:
        assert (await storage.write(entries=batch, parents=True)).success
    return total


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20


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


def timed(fn, reps: int = 7) -> float:
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(times)


async def fetch_all(storage: DatabaseStorage, epoch: int, terms: list[str]):
    """Whole fetch: every block of every term, plus summaries and idfs."""
    tables = storage._host.tables
    postings = tables.lex_postings
    async with storage._host.session_factory() as session:
        stats = await lexical_stats(session, tables, epoch, terms, 500)
        present = [t for t in terms if t in stats.terms]
        summaries = {t: decode_summary(stats.terms[t].blocks) for t in present}
        fetched = (
            select(postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)
            .where(postings.c.epoch == epoch, postings.c.term.in_(present))
            .order_by(postings.c.term, postings.c.block_no)
        )
        by_term: dict[str, list[ScoreBlock]] = {t: [] for t in present}
        for row in await session.execute(fetched):
            bound = float(summaries[row.term].max_weights[row.block_no])
            by_term[row.term].append(
                ScoreBlock(present.index(row.term), bound, bytes(row.doc_ids), bytes(row.tfs), bytes(row.dls))
            )
    idfs = [stats.terms[t].idf for t in present]
    return present, by_term, summaries, idfs, stats.avg_dl


def two_round(present, by_term, summaries, idfs, avg_dl, k) -> tuple[int, int, int, int]:
    """Round one = heads; round two = competing blocks per overflowing term.
    Returns (blocks fetched, blocks total, bytes fetched, bytes total)."""
    size = lambda b: len(b.doc_ids) + len(b.tfs) + len(b.dls)  # noqa: E731
    fetched = [b for t in present for b in by_term[t][:HEAD_BLOCKS]]
    overflowing = sorted(
        (t for t in present if len(by_term[t]) > HEAD_BLOCKS), key=lambda t: -float(summaries[t].max_weights.max())
    )
    for position, term in enumerate(overflowing):
        everything = score_blocks(fetched, idfs, avg_dl, 10**9)
        ranked = everything[:k]
        theta = ranked[-1][1] if len(ranked) == k else 0.0
        candidates = np.array(sorted(c for c, _ in everything), dtype=np.int64)
        scores_of = dict(everything)
        tail = np.array([scores_of[c] for c in candidates.tolist()], dtype=np.float64)
        rest = sum(float(summaries[o].max_weights.max()) for o in overflowing[position + 1 :])
        competing = competing_blocks(summaries[term], candidates, tail, theta, rest)
        fetched += [by_term[term][no] for no in competing.tolist() if no >= HEAD_BLOCKS]
    total = [b for t in present for b in by_term[t]]
    return len(fetched), len(total), sum(map(size, fetched)), sum(map(size, total))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=4000)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--db", default="/tmp/landing_lexical.sqlite")
    ap.add_argument("--reuse", action="store_true", help="skip the load; the store at --db is already loaded")
    args = ap.parse_args()
    db = FsPath(args.db)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}")
    if args.reuse:
        con = sqlite3.connect(db)
        files = list(range(con.execute("SELECT COUNT(*) FROM vfs WHERE kind = 'file'").fetchone()[0]))
        content_bytes = con.execute("SELECT SUM(LENGTH(content)) FROM vfs_chunks").fetchone()[0]
        con.close()
        print(f"engine {native.active_core()}; reusing {len(files)} files, {content_bytes / 1e6:.1f} MB of chunk text")
    else:
        if db.exists():
            db.unlink()
        files = sample_files(None if args.all else args.files, args.seed)
        t0 = time.perf_counter()
        content_bytes = await load(storage, files)
        load_s = time.perf_counter() - t0
        print(f"engine {native.active_core()}; loaded {len(files)} files, {content_bytes / 1e6:.1f} MB in {load_s:.1f}s")
    rss_after_load = rss_mb()

    real_build = indexing.build_lexical_epoch

    async def no_lexical(session, tables, epoch, executor) -> None:
        return None

    indexing.build_lexical_epoch = no_lexical  # type: ignore[assignment]
    t0 = time.perf_counter()
    result = await storage.reindex()
    assert result.success, result.errors
    baseline = time.perf_counter() - t0
    lexical_model.TOKENIZER_VERSION = 99  # type: ignore[misc]  # force a rebuild through the options hash
    indexing.build_lexical_epoch = real_build  # type: ignore[assignment]
    t0 = time.perf_counter()
    result = await storage.reindex()
    assert result.success, result.errors
    full = time.perf_counter() - t0
    rss_after_build = rss_mb()
    print(f"reindex without lexical {baseline:.1f}s; with {full:.1f}s (lexical delta {full - baseline:.1f}s)")

    tables = storage._host.tables
    async with storage._host.engine.connect() as conn:
        texts = (await conn.execute(select(tables.chunks.c.content))).scalars().all()
        epoch = (await conn.execute(select(tables.meta.c.current_gram_epoch))).scalar_one()
    t0 = time.perf_counter()
    tokens = sum(len(tokenize(text)) for text in texts)
    tokenize_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    for text in texts[:2000]:
        pure_tokenize(text)
    pure_tokenize_s = (time.perf_counter() - t0) * len(texts) / max(1, min(2000, len(texts)))
    print(f"chunks {len(texts)}, tokens {tokens}; tokenizer {tokenize_s:.2f}s (pure est. {pure_tokenize_s:.1f}s)")

    con = sqlite3.connect(db)
    sizes = dict(con.execute("SELECT name, SUM(pgsize) FROM dbstat WHERE name LIKE 'vfs_lex%' OR name = 'vfs_chunks' GROUP BY name"))
    lex_bytes = sum(v for k, v in sizes.items() if "lex" in k)
    postings = con.execute("SELECT SUM(doc_count), SUM(LENGTH(doc_ids)+LENGTH(tfs)+LENGTH(dls)), COUNT(*) FROM vfs_lex_postings").fetchone()
    vocab, summary_bytes = con.execute("SELECT COUNT(*), SUM(LENGTH(blocks)) FROM vfs_lex_df").fetchone()
    build = {
        "files": len(files),
        "content_mb": round(content_bytes / 2**20, 1),
        "chunks": len(texts),
        "tokens": tokens,
        "vocab": vocab,
        "postings": postings[0],
        "block_rows": postings[2],
        "reindex_without_lexical_s": round(baseline, 2),
        "reindex_with_lexical_s": round(full, 2),
        "lexical_delta_s": round(full - baseline, 2),
        "tokenizer_s": round(tokenize_s, 2),
        "tokenizer_share_pct": round(100 * tokenize_s / max(1e-9, full - baseline), 1),
        "pure_tokenizer_est_s": round(pure_tokenize_s, 1),
        "blob_bytes": postings[1],
        "blob_bytes_per_posting": round(postings[1] / postings[0], 3),
        "summary_bytes": summary_bytes,
        "summary_bytes_per_block": round(summary_bytes / postings[2], 2),
        "table_bytes": {k: v for k, v in sizes.items()},
        "lex_bytes_mb": round(lex_bytes / 2**20, 1),
        "lex_bytes_per_posting": round(lex_bytes / postings[0], 2),
        "lex_bytes_per_chunk": round(lex_bytes / len(texts)),
        "lex_over_content": round(lex_bytes / content_bytes, 2),
        "rss_mb_after_load": round(rss_after_load, 1),
        "rss_mb_after_build": round(rss_after_build, 1),
    }
    print(json.dumps(build, indent=1))

    # --- query -----------------------------------------------------------
    queries = draw_queries(con)
    n_docs = con.execute("SELECT n_docs FROM vfs_lex_stats").fetchone()[0]
    commonest = [t for t, _df in con.execute("SELECT term, df FROM vfs_lex_df ORDER BY df DESC LIMIT 2")]
    query_results: dict[str, dict] = {}
    for arity, qs in queries.items():
        rust_ms, numpy_ms, blocks_n, fetched = [], [], [], {10: [], 1000: []}
        for terms in qs:
            present, by_term, summaries, idfs, avg_dl = await fetch_all(storage, epoch, terms)
            blocks = [b for t in present for b in by_term[t]]
            blocks_n.append(len(blocks))
            rust_ms.append(timed(lambda: _native.lexical_score(blocks, idfs, avg_dl, 10)))
            numpy_ms.append(timed(lambda: pure_score_blocks(blocks, idfs, avg_dl, 10)))
            assert _native.lexical_score(blocks, idfs, avg_dl, 10) == pure_score_blocks(blocks, idfs, avg_dl, 10)
            for k in (10, 1000):
                fetched[k].append(two_round(present, by_term, summaries, idfs, avg_dl, k))
        query_results[str(arity)] = {
            "blocks_median": statistics.median(blocks_n),
            "rust_score_ms": round(statistics.median(rust_ms), 3),
            "numpy_score_ms": round(statistics.median(numpy_ms), 3),
            **{
                f"k{k}_round2_blocks_pct": round(100 * sum(f[0] for f in fetched[k]) / sum(f[1] for f in fetched[k]), 1)
                for k in (10, 1000)
            },
            **{
                f"k{k}_bytes_fetched_pct": round(100 * sum(f[2] for f in fetched[k]) / sum(f[3] for f in fetched[k]), 1)
                for k in (10, 1000)
            },
        }
    present, by_term, summaries, idfs, avg_dl = await fetch_all(storage, epoch, commonest)
    blocks = [b for t in present for b in by_term[t]]
    all_common = {
        "terms": commonest,
        "df_share_pct": [round(100 * df / n_docs, 1) for _t, df in con.execute("SELECT term, df FROM vfs_lex_df ORDER BY df DESC LIMIT 2")],
        "blocks": len(blocks),
        "blob_bytes": sum(len(b.doc_ids) + len(b.tfs) + len(b.dls) for b in blocks),
        "rust_score_ms": round(timed(lambda: _native.lexical_score(blocks, idfs, avg_dl, 10)), 3),
        "numpy_score_ms": round(timed(lambda: pure_score_blocks(blocks, idfs, avg_dl, 10)), 3),
        **{f"k{k}_round2_blocks_pct": round(100 * two_round(present, by_term, summaries, idfs, avg_dl, k)[0] / len(blocks), 1) for k in (10, 1000)},
    }
    payload = {"engine": native.active_core(), "build": build, "queries": query_results, "all_common": all_common}
    print(json.dumps({"queries": query_results, "all_common": all_common}, indent=1))
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"landing_{'full' if args.all else args.files}.json"
    out.write_text(json.dumps(payload, indent=1))
    print(f"-> {out}")
    await storage.close()


asyncio.run(main())
