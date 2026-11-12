"""The dirty-set cost curve: build and index a corpus once, then for each dirty level N measure grep and glean.

Usage:
  uv run python study.py --engine sqlite --files 10000 --levels 500,2000,5000,10000
  uv run python study.py --engine postgres --files 100000 --levels 10000,25000 --url postgresql+asyncpg://...

Each level starts from a fresh copy of the clean indexed store (a file copy
on SQLite, a schema clone on Postgres), rewrites N files chosen uniformly at
random (same size class, new words), writes the sentinel file last, and
runs: five grep patterns x 3 reps, five glean queries x 3 reps at the
default OVERLAY_BUDGET (500) and again at 25,000, the sentinel recall probe
under both budgets, and one pass of every pattern and query under the
default 10 s wall. Results land in results_<engine>_<files>.json beside
this file; progress goes to stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import resource
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corpus import (  # noqa: E402
    SENTINEL_PATH,
    SENTINEL_WORD,
    document,
    generate,
    path_for,
    sentinel,
    word_at_rank,
)
from harness import (  # noqa: E402
    PHASES,
    checkpoint_and_copy,
    clone_schema,
    db_size_mb,
    dirty_paths,
    drop_schema,
    install_wrappers,
    open_store,
    sqlite_url,
    table_counts,
    timed,
)
from vfs.models import Entry  # noqa: E402
from vfs.paths import Path  # noqa: E402
from vfs.storage.backends.database import glean as glean_module  # noqa: E402
from vfs.storage.backends.database.offload import WALL_TIME_BUDGET  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = (
    "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/19e5567a-293c-4698-ba37-caa374019bda/scratchpad/scanbudgets/curve"
)
WRITE_BATCH = 10_000
LIFTED_WALL = 600.0
DEFAULT_OVERLAY = glean_module.OVERLAY_BUDGET
LIFTED_OVERLAY = 25_000
REPS = 3

GREP_PATTERNS = [
    ("rare literal (rank 12000)", word_at_rank(12_000), {"fixed_strings": True}),
    ("common word (rank 40)", word_at_rank(40), {}),
    ("alternation regex (ranks 2000|2500)", f"{word_at_rank(2_000)}|{word_at_rank(2_500)}", {}),
    ("case-insensitive word (rank 800)", word_at_rank(800).upper(), {"case_mode": "insensitive"}),
    ("matches almost nothing", "neverappears", {}),
]
GLEAN_QUERIES = [
    ("2 words (ranks 300, 3000)", f"{word_at_rank(300)} {word_at_rank(3_000)}"),
    ("3 words (ranks 40, 1500, 9000)", f"{word_at_rank(40)} {word_at_rank(1_500)} {word_at_rank(9_000)}"),
    ("4 words (ranks 700, 2000, 5000, 15000)", " ".join(word_at_rank(r) for r in (700, 2_000, 5_000, 15_000))),
    ("2 very common (ranks 5, 12)", f"{word_at_rank(5)} {word_at_rank(12)}"),
    ("2 rare (ranks 8000, 20000)", f"{word_at_rank(8_000)} {word_at_rank(20_000)}"),
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1_000_000, 1)


def records_of(result) -> list[dict]:
    return [
        {"kind": str(e.kind), "severity": str(e.severity), "message": e.message, "data": e.data}
        for e in result.errors
        if "no embedding provider" not in e.message
    ]


def phases_snapshot() -> dict:
    return {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in PHASES.items()}


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


async def write_all(storage, n: int) -> dict:
    t0 = time.perf_counter()
    batch: list[Entry] = []
    written = 0
    for path, content in generate(n):
        batch.append(Entry(path=Path(path), content=content))
        if len(batch) == WRITE_BATCH:
            r = await storage.write(entries=batch, parents=True)
            assert r.success, r.errors
            written += len(batch)
            log(f"  wrote {written}/{n}")
            batch = []
    if batch:
        r = await storage.write(entries=batch, parents=True)
        assert r.success, r.errors
    return {"wall_s": round(time.perf_counter() - t0, 2), "entries": n}


async def reindex_until_clean(storage, counter) -> list[dict]:
    runs = []
    for attempt in range(4):
        with counter.capture():
            result, wall = await timed(storage.reindex())
        counts = await table_counts(storage)
        runs.append(
            {
                "attempt": attempt,
                "success": result.success,
                "wall_s": wall,
                "statements": counter.count,
                "errors": records_of(result),
                "extras": {k: str(v) for k, v in (result.model_extra or {}).items()},
                "rss_mb": rss_mb(),
                **counts,
            }
        )
        log(f"  reindex #{attempt} wall={wall}s stmts={counter.count} not_encoded={counts['not_encoded']} epoch={counts['epoch']}")
        if result.success and counts["not_encoded"] == 0:
            break
    return runs


async def build_base(engine: str, files: int, url: str, schema: str | None, db_path: str | None) -> dict:
    if engine == "sqlite":
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db_path + suffix):
                os.remove(db_path + suffix)
        storage, counter = await open_store(sqlite_url(db_path), wall=LIFTED_WALL)
    else:
        await drop_schema(url, schema)
        short, _ = await open_store(url, wall=LIFTED_WALL)
        async with short._host.engine.begin() as conn:
            from sqlalchemy import text

            await conn.execute(text(f"CREATE SCHEMA {schema}"))
        await short.close()
        storage, counter = await open_store(url, schema=schema, wall=LIFTED_WALL)
    log(f"building {files} files on {engine}")
    out = {"write": await write_all(storage, files)}
    log(f"write done in {out['write']['wall_s']}s")
    out["reindex"] = await reindex_until_clean(storage, counter)
    out["counts"] = await table_counts(storage)
    if engine == "sqlite":
        out["db_mb"] = db_size_mb(db_path)
    out["rss_mb"] = rss_mb()
    await storage.close()
    return out


# ---------------------------------------------------------------------------
# Dirtying
# ---------------------------------------------------------------------------


async def dirty(storage, files: int, n: int, *, compound: bool = False) -> dict:
    """Rewrite n files chosen uniformly at random; in compounding mode, top the store's live dirty set up to exactly n."""
    t0 = time.perf_counter()
    if compound:
        dirty_now = await dirty_paths(storage) - {SENTINEL_PATH}
        order = list(range(files))
        random.Random(7).shuffle(order)
        chosen = []
        need = n - len(dirty_now)
        for i in order:
            if need <= 0:
                break
            if path_for(i) not in dirty_now:
                chosen.append(i)
                need -= 1
        chosen.sort()
    else:
        chosen = sorted(random.Random(1_000 + n).sample(range(files), n))
    batch: list[Entry] = []
    for i in chosen:
        path, content = document(i, salt=1)
        batch.append(Entry(path=Path(path), content=content))
        if len(batch) == WRITE_BATCH:
            assert (await storage.write(entries=batch, parents=True)).success
            batch = []
    if batch:
        assert (await storage.write(entries=batch, parents=True)).success
    path, body = sentinel(n)
    assert (await storage.write(entries=[Entry(path=Path(path), content=body)], parents=True)).success
    counts = await table_counts(storage)
    return {"n": n, "wall_s": round(time.perf_counter() - t0, 2), "not_encoded_after": counts["not_encoded"]}


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------


async def grep_call(storage, counter, name: str, pattern: str, kw: dict, rep: int) -> dict:
    with counter.capture():
        result, wall = await timed(storage.grep(pattern=pattern, **kw))
    return {
        "name": name,
        "pattern": pattern,
        "kw": kw,
        "rep": rep,
        "wall_s": wall,
        "statements": counter.count,
        "statement_kinds": dict(counter.kinds),
        "files": len(result.observations),
        "lines": sum(len(o.matches or ()) for o in result.observations),
        "phases": phases_snapshot(),
        "records": records_of(result),
        "sentinel_found": SENTINEL_PATH in [str(o.path) for o in result.observations],
    }


async def glean_call(storage, counter, name: str, query: str, rep: int, budget: int) -> dict:
    glean_module.OVERLAY_BUDGET = budget
    try:
        with counter.capture():
            result, wall = await timed(storage.glean(query=query, limit=10))
    finally:
        glean_module.OVERLAY_BUDGET = DEFAULT_OVERLAY
    extra = result.model_extra or {}
    legs = extra.get("legs") or {}
    return {
        "name": name,
        "query": query,
        "rep": rep,
        "overlay_budget": budget,
        "wall_s": wall,
        "statements": counter.count,
        "statement_kinds": dict(counter.kinds),
        "hits": len(result.observations),
        "lexical_hits": (legs.get("lexical") or {}).get("hits"),
        "vector_leg": legs.get("vector"),
        "terms_present": (legs.get("lexical") or {}).get("terms"),
        "phases": phases_snapshot(),
        "records": records_of(result),
        "no_provider_record": any("no embedding provider" in e.message for e in result.errors),
        "sentinel_found": SENTINEL_PATH in [str(o.path) for o in result.observations],
    }


async def grep_suite(storage, counter, reps: int) -> list[dict]:
    rows = []
    for rep in range(reps):
        for name, pattern, kw in GREP_PATTERNS:
            rows.append(await grep_call(storage, counter, name, pattern, kw, rep))
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r["wall_s"])
    log("  grep medians: " + ", ".join(f"{k}={statistics.median(v):.2f}s" for k, v in by_name.items()))
    return rows


async def glean_suite(storage, counter, reps: int, budget: int) -> list[dict]:
    rows = []
    for rep in range(reps):
        for name, query in GLEAN_QUERIES:
            rows.append(await glean_call(storage, counter, name, query, rep, budget))
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(r["wall_s"])
    log(f"  glean[budget={budget}] medians: " + ", ".join(f"{k}={statistics.median(v):.2f}s" for k, v in by_name.items()))
    return rows


async def recall_probe(storage, counter) -> dict:
    g = await grep_call(storage, counter, "sentinel grep", SENTINEL_WORD, {}, 0)
    l_default = await glean_call(storage, counter, "sentinel glean", SENTINEL_WORD, 0, DEFAULT_OVERLAY)
    l_lifted = await glean_call(storage, counter, "sentinel glean", SENTINEL_WORD, 0, LIFTED_OVERLAY)
    log(
        f"  recall: grep={g['sentinel_found']} glean@{DEFAULT_OVERLAY}={l_default['sentinel_found']} "
        f"glean@{LIFTED_OVERLAY}={l_lifted['sentinel_found']}"
    )
    return {"grep": g, "glean_default": l_default, "glean_lifted": l_lifted}


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------


async def run_level(
    engine: str, files: int, n: int, url: str, base_schema: str | None, base_db: str | None, compound_from: int | None = None
) -> dict:
    out: dict = {"n": n}
    if compound_from is not None:
        # No fresh copy: the level runs on the base store, extending the previous level's dirty set.
        out["compound_from"] = compound_from
        level_url = sqlite_url(base_db) if engine == "sqlite" else url
        level_schema, level_db = base_schema, base_db
        t0 = time.perf_counter()
        storage, counter = await open_store(level_url, schema=level_schema, wall=LIFTED_WALL)
        out["copy_s"] = round(time.perf_counter() - t0, 2)
    elif engine == "sqlite":
        level_db = os.path.join(SCRATCH, f"level_{files}_{n}.db")
        out["copy_s"] = checkpoint_and_copy(base_db, level_db)
        storage, counter = await open_store(sqlite_url(level_db), wall=LIFTED_WALL)
        level_url, level_schema = sqlite_url(level_db), None
    else:
        level_schema = f"curve_n{n}"
        storage, counter, out["copy_s"] = await clone_schema(url, base_schema, level_schema, LIFTED_WALL)
        level_url, level_db = url, None
    log(f"level N={n}: fresh store ready in {out['copy_s']}s")
    out["dirty"] = await dirty(storage, files, n, compound=compound_from is not None)
    log(f"  dirtied {n} (+ sentinel) in {out['dirty']['wall_s']}s; not_encoded={out['dirty']['not_encoded_after']}")
    out["grep"] = await grep_suite(storage, counter, REPS)
    out["glean_default"] = await glean_suite(storage, counter, REPS, DEFAULT_OVERLAY)
    out["glean_lifted"] = await glean_suite(storage, counter, REPS, LIFTED_OVERLAY)
    out["recall"] = await recall_probe(storage, counter)
    out["rss_mb"] = rss_mb()
    await storage.close()
    # One pass under the default 10 s wall: what a caller sees today.
    storage, counter = await open_store(level_url, schema=level_schema, wall=WALL_TIME_BUDGET)
    out["default_wall"] = {
        "grep": [await grep_call(storage, counter, name, pattern, kw, 0) for name, pattern, kw in GREP_PATTERNS],
        "glean_lifted": [await glean_call(storage, counter, name, q, 0, LIFTED_OVERLAY) for name, q in GLEAN_QUERIES],
    }
    log(
        "  default wall: grep "
        + ", ".join(f"{r['wall_s']:.2f}s" for r in out["default_wall"]["grep"])
        + " | glean "
        + ", ".join(f"{r['wall_s']:.2f}s" for r in out["default_wall"]["glean_lifted"])
    )
    await storage.close()
    if compound_from is not None:
        return out
    if engine == "sqlite":
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(level_db + suffix):
                os.remove(level_db + suffix)
    else:
        await drop_schema(url, level_schema)
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--files", type=int, required=True)
    parser.add_argument("--levels", default="500,2000,5000,10000,25000")
    parser.add_argument("--url", default="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs")
    parser.add_argument("--reuse-base", action="store_true", help="skip the build when the base store exists")
    parser.add_argument(
        "--compound",
        action="store_true",
        help="run every level on the base store itself, each extending the previous dirty set (no copy or clone)",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    install_wrappers()
    os.makedirs(SCRATCH, exist_ok=True)
    levels = [int(x) for x in args.levels.split(",") if int(x) <= args.files]
    base_db = os.path.join(SCRATCH, f"base_{args.files}.db") if args.engine == "sqlite" else None
    base_schema = f"curve_base_{args.files}" if args.engine == "postgres" else None
    out: dict = {
        "engine": args.engine,
        "files": args.files,
        "levels": levels,
        "machine": "Apple M1 Pro, 10 cores, 32 GB",
        "python": sys.version.split()[0],
        "default_overlay_budget": DEFAULT_OVERLAY,
        "lifted_overlay_budget": LIFTED_OVERLAY,
        "lifted_wall_s": LIFTED_WALL,
        "default_wall_s": WALL_TIME_BUDGET,
        "grep_patterns": [{"name": n, "pattern": p, "kw": kw} for n, p, kw in GREP_PATTERNS],
        "glean_queries": [{"name": n, "query": q} for n, q in GLEAN_QUERIES],
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    reuse = args.reuse_base and (
        (args.engine == "sqlite" and os.path.exists(base_db)) or args.engine == "postgres"
    )
    if reuse:
        storage, _ = await open_store(
            sqlite_url(base_db) if args.engine == "sqlite" else args.url, schema=base_schema, wall=LIFTED_WALL
        )
        out["base"] = {"reused": True, "counts": await table_counts(storage)}
        await storage.close()
        log(f"reusing base: {out['base']['counts']}")
    else:
        t0 = time.perf_counter()
        out["base"] = await build_base(args.engine, args.files, args.url, base_schema, base_db)
        out["base"]["total_s"] = round(time.perf_counter() - t0, 1)
        log(f"base built in {out['base']['total_s']}s: {out['base']['counts']}")
    out["results"] = []
    out["compound"] = args.compound
    previous = 0
    for n in levels:
        t0 = time.perf_counter()
        level = await run_level(
            args.engine, args.files, n, args.url, base_schema, base_db, compound_from=previous if args.compound else None
        )
        previous = n
        level["level_total_s"] = round(time.perf_counter() - t0, 1)
        out["results"].append(level)
        path = args.out or os.path.join(HERE, f"results_{args.engine}_{args.files}.json")
        with open(path, "w") as f:
            json.dump(out, f, indent=1, default=str)
        log(f"level N={n} done in {level['level_total_s']}s; results written")
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = args.out or os.path.join(HERE, f"results_{args.engine}_{args.files}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    log("done")


if __name__ == "__main__":
    asyncio.run(main())
