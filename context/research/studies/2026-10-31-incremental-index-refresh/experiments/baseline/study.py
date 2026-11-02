"""Measurements A-E for one corpus size: cold reindex, no-op reindex, dirty reindex, reader staleness, write latency.

Usage: uv run python study.py N  -> writes results_N.json beside this file and logs progress to stderr.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import resource
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corpus import IDENTS, VOCAB, _perm, generate, path_for  # noqa: E402
from harness import db_parts_mb, db_size_mb, open_store, table_counts, timed  # noqa: E402
from vfs.models import Entry  # noqa: E402
from vfs.paths import Path  # noqa: E402
from vfs.storage.backends.database import backend as backend_module  # noqa: E402
from vfs.storage.backends.database import indexing  # noqa: E402

PHASES: dict[str, float] = {}


def _timed_phase(module, name: str, key: str) -> None:
    original = getattr(module, name)

    async def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            PHASES[key] = PHASES.get(key, 0.0) + (time.perf_counter() - t0)

    setattr(module, name, wrapper)


for _name in ("chunk_dirty", "build_epoch", "publish_epoch", "reclaim_epochs"):
    _timed_phase(backend_module, _name, _name)
_timed_phase(indexing, "build_lexical_epoch", "build_lexical_epoch (inside build_epoch)")

HERE = os.path.dirname(os.path.abspath(__file__))
WRITE_BATCH = 2000
DIRTY_FRACTIONS = (0.001, 0.005, 0.01, 0.02, 0.05)

# Rank r in the Zipf permutation: low rank = frequent, high rank = rare.
def word_at_rank(r: int) -> str:
    return VOCAB[_perm[r]]


GREP_PATTERNS = [
    ("rare word (rank 4992)", word_at_rank(4992), {}),
    ("rare word (rank 4874)", word_at_rank(4874), {}),
    ("rare word (rank 4725)", word_at_rank(4725), {}),
    ("mid word (rank 1500)", word_at_rank(1500), {}),
    ("mid word (rank 400)", word_at_rank(400), {}),
    ("identifier literal", IDENTS[17], {"fixed_strings": True}),
    ("identifier literal 2", IDENTS[311], {"fixed_strings": True}),
    ("3-letter common word", "was", {}),
    ("regex, literal core", r"parse_entry_9\d\d", {}),
    ("regex, literal core 2", r"score(Query|Handle)[0-9]+", {}),
]
GLEAN_QUERIES = [
    f"{word_at_rank(3000)} {word_at_rank(3100)}",
    f"{word_at_rank(1200)} {word_at_rank(2200)} {word_at_rank(4000)}",
    f"{word_at_rank(50)} {word_at_rank(60)} {word_at_rank(4700)}",
    f"{word_at_rank(800)} {word_at_rank(900)} {word_at_rank(1000)} {word_at_rank(1100)}",
    f"{IDENTS[17]} {word_at_rank(2500)}",
]
UNIQUE_WORD = "qzxvunique"
LAST_PATH = "/zzz/zzz/last.md"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1_000_000, 1)


def errors_of(result) -> list[dict]:
    return [
        {"kind": str(e.kind), "severity": str(e.severity), "message": e.message, "data": e.data}
        for e in result.errors
    ]


async def write_all(storage, n: int) -> dict:
    t0 = time.perf_counter()
    batch: list[Entry] = []
    for path, content in generate(n):
        batch.append(Entry(path=Path(path), content=content))
        if len(batch) == WRITE_BATCH:
            r = await storage.write(entries=batch, parents=True)
            assert r.success, r.errors
            batch = []
    if batch:
        r = await storage.write(entries=batch, parents=True)
        assert r.success, r.errors
    return {"wall_s": round(time.perf_counter() - t0, 2), "entries": n}


async def dirty(storage, order: list[int], lo: int, hi: int, salt: int) -> float:
    """Rewrite docs order[lo:hi] with new content (salt); returns wall seconds."""
    t0 = time.perf_counter()
    idx = sorted(order[lo:hi])
    batch: list[Entry] = []
    for i in idx:
        rng = random.Random((20261031, i, salt).__hash__())
        from corpus import doc_text  # local to keep generate() the single generator

        words = rng.randint(200, 2000)
        batch.append(Entry(path=Path(path_for(i)), content=f"# Document {i} rev {salt}\n\n" + doc_text(rng, words)))
        if len(batch) == WRITE_BATCH:
            assert (await storage.write(entries=batch, parents=True)).success
            batch = []
    if batch:
        assert (await storage.write(entries=batch, parents=True)).success
    return round(time.perf_counter() - t0, 2)


async def reindex_measure(storage, counter, label: str) -> dict:
    db = storage._host.engine.url.database
    before = rss_mb()
    PHASES.clear()
    with counter.capture():
        result, wall = await timed(storage.reindex())
    counts = await table_counts(storage)
    out = {
        "label": label,
        "success": result.success,
        "wall_s": wall,
        "phases_s": {k: round(v, 3) for k, v in PHASES.items()},
        "statements": counter.count,
        "statement_kinds": counter.kinds,
        "executemany_rows": counter.rows_bound,
        "errors": errors_of(result),
        "extras": result.model_extra or {},
        "rss_before_mb": before,
        "rss_after_mb": rss_mb(),
        **db_parts_mb(db),
        **counts,
    }
    log(f"reindex[{label}] wall={wall}s stmts={counter.count} postings={counts['posting_list']} lex={counts['lex_postings']} epoch={counts['epoch']} phases={out['phases_s']} db={db_parts_mb(db)}")
    return out


async def grep_suite(storage, counter, label: str) -> list[dict]:
    rows = []
    for name, pattern, kw in GREP_PATTERNS:
        with counter.capture():
            result, wall = await timed(storage.grep(pattern=pattern, **kw))
        files = len(result.observations)
        lines = sum(len(o.matches or ()) for o in result.observations)
        rows.append(
            {
                "state": label,
                "name": name,
                "pattern": pattern,
                "wall_s": wall,
                "statements": counter.count,
                "files": files,
                "lines": lines,
                "errors": errors_of(result),
            }
        )
    log(f"grep[{label}] total wall={sum(r['wall_s'] for r in rows):.2f}s")
    return rows


async def glean_suite(storage, counter, label: str) -> list[dict]:
    rows = []
    for q in GLEAN_QUERIES:
        with counter.capture():
            result, wall = await timed(storage.glean(query=q, limit=10))
        rows.append(
            {
                "state": label,
                "query": q,
                "wall_s": wall,
                "statements": counter.count,
                "hits": len(result.observations),
                "errors": [e for e in errors_of(result) if "no embedding provider" not in e["message"]],
            }
        )
    log(f"glean[{label}] total wall={sum(r['wall_s'] for r in rows):.2f}s")
    return rows


async def freshness(storage, counter, label: str) -> dict:
    """Does a dirty, never-reindexed file whose path sorts last show up in grep and glean?"""
    body = f"# fresh\n\nthis body holds the {UNIQUE_WORD} word and little else of note\n"
    assert (await storage.write(entries=[Entry(path=Path(LAST_PATH), content=body)], parents=True)).success
    with counter.capture():
        g, gw = await timed(storage.grep(pattern=UNIQUE_WORD))
    g_stmts = counter.count
    with counter.capture():
        l, lw = await timed(storage.glean(query=UNIQUE_WORD, limit=10))
    out = {
        "state": label,
        "grep_found": LAST_PATH in [str(o.path) for o in g.observations],
        "grep_wall_s": gw,
        "grep_statements": g_stmts,
        "glean_found": LAST_PATH in [str(o.path) for o in l.observations],
        "glean_wall_s": lw,
        "glean_statements": counter.count,
        "glean_errors": [e for e in errors_of(l) if "no embedding provider" not in e["message"]],
        "not_encoded": (await table_counts(storage))["not_encoded"],
    }
    log(f"freshness[{label}] grep={out['grep_found']} glean={out['glean_found']} dirty={out['not_encoded']}")
    return out


async def write_latency(storage, counter, label: str, prefix: str, reps: int = 3) -> list[dict]:
    rows = []
    for rep in range(reps):
        entries = [
            Entry(path=Path(f"/new/{prefix}/r{rep}/f{i:04d}.md"), content=content)
            for i, (_, content) in enumerate(generate(500, salt=900 + rep))
        ]
        with counter.capture():
            result, wall = await timed(storage.write(entries=entries, parents=True))
        assert result.success
        rows.append({"state": label, "rep": rep, "entries": 500, "wall_s": wall, "statements": counter.count})
    log(f"write500[{label}] walls={[r['wall_s'] for r in rows]}")
    return rows


async def main(n: int) -> None:
    db = os.path.join(HERE, f"corpus_{n}.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db + suffix):
            os.remove(db + suffix)
    storage, counter = await open_store(db, grep_wall_seconds=600, glean_wall_seconds=600)
    out: dict = {"n": n, "machine": "Apple M1 Pro, 10 cores, 32 GB, SQLite via aiosqlite", "python": sys.version.split()[0]}
    order = list(range(n))
    random.Random(7).shuffle(order)

    log(f"writing {n} entries")
    out["write"] = await write_all(storage, n)
    out["write"]["db_mb_after_write"] = db_size_mb(db)
    log(f"write done in {out['write']['wall_s']}s, db={out['write']['db_mb_after_write']}MB")

    # A: cold build, then no-op.
    out["A_cold"] = await reindex_measure(storage, counter, "cold")
    out["A_cold"]["db_mb"] = db_size_mb(db)
    out["A_noop"] = await reindex_measure(storage, counter, "noop")

    # C/D baseline: clean readers.
    out["grep"] = await grep_suite(storage, counter, "clean")
    out["glean"] = await glean_suite(storage, counter, "clean")

    # E clean: 500 new entries while nothing is dirty; then reindex (a 1,500-entry dirty set, all new).
    await write_latency(storage, counter, "clean warm-up (untimed)", "warm", reps=1)
    out["E_clean"] = await write_latency(storage, counter, "clean", "clean")
    out["B_new2000"] = await reindex_measure(storage, counter, "2000 new entries dirty")

    # C/D at cumulative dirty fractions.
    out["freshness"] = []
    lo = 0
    for frac in DIRTY_FRACTIONS:
        hi = int(round(n * frac))
        if hi > lo:
            dw = await dirty(storage, order, lo, hi, salt=1)
            lo = hi
        label = f"dirty {frac:.1%} ({hi})"
        log(f"dirtied to {hi} ({frac:.1%}) in {dw}s")
        out["grep"] += await grep_suite(storage, counter, label)
        out["glean"] += await glean_suite(storage, counter, label)
        out["freshness"].append(await freshness(storage, counter, label))
    # E dirty: 500 new entries while ~5% is dirty.
    out["E_dirty"] = await write_latency(storage, counter, "5% dirty", "dirty")
    # B at 5% (+ the 1,501 fresh rows written above).
    out["B_5pct"] = await reindex_measure(storage, counter, "5% dirty")
    # B at 1%.
    out["B_1pct_dirty_wall_s"] = await dirty(storage, order, 0, int(round(n * 0.01)), salt=2)
    out["B_1pct"] = await reindex_measure(storage, counter, "1% dirty")
    out["B_noop_again"] = await reindex_measure(storage, counter, "noop again")
    out["db_mb_final"] = db_size_mb(db)
    await storage.close()
    with open(os.path.join(HERE, f"results_{n}.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    log("done")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
