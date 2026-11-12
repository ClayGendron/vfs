"""Study 03 driver: glean's lifted-budget curve with the overlay's tokenize-and-count in the Rust kernel.

Imports study 02's driver and harness (copies beside this file, unedited) and
replaces ``glean._overlay_blocks`` with a switch that routes to either the
Python original or the pyo3 prototype ``overlay_counts.overlay_postings``.
The switch is installed before the harness wrappers, so the phase timer
``glean.tokenize`` wraps whichever implementation the switch selects. Per
level on the SQLite 100,000-file store: fresh copy, the same dirty set study
02 drew, one pass of the five lifted-budget queries through the Python
overlay, three passes through the kernel overlay, a hit-for-hit parity check
of the two, and the sentinel recall probe through the kernel.

Usage, from the vfs repo: uv run --with <wheel> python study_kernel.py --files 100000 --levels 10000,25000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import overlay_counts  # noqa: E402  (the pyo3 prototype wheel)
from vfs.storage.backends.database import glean as glean_module  # noqa: E402

import study  # noqa: E402  (study 02's driver, a copy)
from corpus import SENTINEL_PATH, SENTINEL_WORD  # noqa: E402
from harness import checkpoint_and_copy, install_wrappers, open_store, sqlite_url, table_counts  # noqa: E402
from study import GLEAN_QUERIES, LIFTED_OVERLAY, LIFTED_WALL, REPS, SCRATCH, dirty, glean_call, glean_suite, log  # noqa: E402

PYTHON_OVERLAY_BLOCKS = glean_module._overlay_blocks
IMPL = ["kernel"]


def _overlay_blocks_kernel(docs, terms, stats):
    """``_overlay_blocks`` with the per-body tokenize-and-count in the kernel; the block assembly is unchanged."""
    per_term, total_dl = overlay_counts.overlay_postings(docs, list(terms))
    n_docs = stats.n_docs + len(docs)
    avg_dl = stats.avg_dl if stats.n_docs else (total_dl / len(docs) if docs else 0.0)
    idfs = [
        stats.terms[term].idf if term in stats.terms else glean_module.idf(len(per_term[position]), n_docs)
        for position, term in enumerate(terms)
    ]
    blocks = []
    for position, postings in enumerate(per_term):
        for page in glean_module.chunked(postings, glean_module.BLOCK_SIZE):
            ids, tfs, dls = zip(*page, strict=True)
            bound = max(
                glean_module.term_weight(tf, dl, avg_dl, idfs[position]) for tf, dl in zip(tfs, dls, strict=True)
            )
            blocks.append(glean_module.ScoreBlock(position, bound, *glean_module.encode_block(ids, tfs, dls)))
    return blocks, idfs, avg_dl


def _overlay_blocks_switch(docs, terms, stats):
    if IMPL[0] == "python":
        return PYTHON_OVERLAY_BLOCKS(docs, terms, stats)
    return _overlay_blocks_kernel(docs, terms, stats)


glean_module._overlay_blocks = _overlay_blocks_switch


async def parity(storage) -> list[dict]:
    """Every lifted-budget query once through each implementation: the hit lists must agree path for path and score for score."""
    rows = []
    for name, query in GLEAN_QUERIES:
        glean_module.OVERLAY_BUDGET = LIFTED_OVERLAY
        try:
            IMPL[0] = "python"
            a = await storage.glean(query=query, limit=10)
            IMPL[0] = "kernel"
            b = await storage.glean(query=query, limit=10)
        finally:
            glean_module.OVERLAY_BUDGET = study.DEFAULT_OVERLAY
        hits_a = [(str(o.path), o.score) for o in a.observations]
        hits_b = [(str(o.path), o.score) for o in b.observations]
        same_paths = [p for p, _ in hits_a] == [p for p, _ in hits_b]
        max_delta = max((abs(x - y) for (_, x), (_, y) in zip(hits_a, hits_b, strict=True)), default=0.0) if same_paths else None
        rows.append({"name": name, "same_paths": same_paths, "max_score_delta": max_delta, "python": hits_a, "kernel": hits_b})
        log(f"  parity {name}: same paths={same_paths} max score delta={max_delta}")
    return rows


async def run_level(files: int, n: int, base_db: str) -> dict:
    out: dict = {"n": n}
    level_db = os.path.join(SCRATCH, f"kernel_level_{files}_{n}.db")
    out["copy_s"] = checkpoint_and_copy(base_db, level_db)
    storage, counter = await open_store(sqlite_url(level_db), wall=LIFTED_WALL)
    log(f"level N={n}: fresh store ready in {out['copy_s']}s")
    out["dirty"] = await dirty(storage, files, n)
    log(f"  dirtied {n} (+ sentinel) in {out['dirty']['wall_s']}s; not_encoded={out['dirty']['not_encoded_after']}")
    IMPL[0] = "python"
    log("  overlay implementation: python (study 02's), one pass")
    out["glean_lifted_python"] = await glean_suite(storage, counter, 1, LIFTED_OVERLAY)
    IMPL[0] = "kernel"
    log(f"  overlay implementation: kernel, {REPS} passes")
    out["glean_lifted_kernel"] = await glean_suite(storage, counter, REPS, LIFTED_OVERLAY)
    out["parity"] = await parity(storage)
    IMPL[0] = "kernel"
    out["recall_kernel"] = await glean_call(storage, counter, "sentinel glean", SENTINEL_WORD, 0, LIFTED_OVERLAY)
    log(f"  recall (kernel, budget {LIFTED_OVERLAY}): sentinel found={out['recall_kernel']['sentinel_found']}")
    out["rss_mb"] = study.rss_mb()
    await storage.close()
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(level_db + suffix):
            os.remove(level_db + suffix)
    return out


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=100_000)
    parser.add_argument("--levels", default="10000,25000")
    parser.add_argument("--out", default=os.path.join(HERE, "results_kernel_sqlite_100000.json"))
    args = parser.parse_args()
    install_wrappers()
    base_db = os.path.join(SCRATCH, f"base_{args.files}.db")
    assert os.path.exists(base_db), base_db
    levels = [int(x) for x in args.levels.split(",") if int(x) <= args.files]
    storage, _ = await open_store(sqlite_url(base_db), wall=LIFTED_WALL)
    counts = await table_counts(storage)
    await storage.close()
    log(f"reusing base: {counts}")
    out: dict = {
        "engine": "sqlite",
        "files": args.files,
        "levels": levels,
        "machine": "Apple M1 Pro, 10 cores, 32 GB",
        "python": sys.version.split()[0],
        "kernel": "overlay_counts.overlay_postings (pyo3 prototype, kernel.rs)",
        "lifted_overlay_budget": LIFTED_OVERLAY,
        "lifted_wall_s": LIFTED_WALL,
        "glean_queries": [{"name": n, "query": q} for n, q in GLEAN_QUERIES],
        "sentinel": SENTINEL_PATH,
        "base_counts": counts,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [],
    }
    for n in levels:
        t0 = time.perf_counter()
        level = await run_level(args.files, n, base_db)
        level["level_total_s"] = round(time.perf_counter() - t0, 1)
        out["results"].append(level)
        with open(args.out, "w") as f:
            json.dump(out, f, indent=1, default=str)
        log(f"level N={n} done in {level['level_total_s']}s; results written")
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, default=str)
    log("done")


if __name__ == "__main__":
    asyncio.run(main())
