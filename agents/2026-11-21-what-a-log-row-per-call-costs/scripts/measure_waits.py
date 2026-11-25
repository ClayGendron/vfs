"""How long a read waits while a 10,000-entry write is in flight, and what the read buffer does meanwhile.

For each mode, one fresh database with the 2,000-file corpus. Eight reader sessions issue ``read`` back to
back, first for a quiet baseline window, then while one more session runs a 10,000-entry ``write``; this is
repeated ``--repeats`` times. A read counts as *during* the batch when its interval overlaps the batch's. The
flusher's records say how long each flush took, whether it failed, and how deep the buffer grew.

On SQLite a fourth variant runs the leaned design with the log in a file of its own beside the mount's,
so the flusher and the claims have a writer of their own.

A second probe runs in the same window: one session issuing one-file ``write`` calls back to back, the
effect path an agent takes while an ETL batch is running.

    L0_SCRATCH=... uv run python scripts/measure_waits.py --engine sqlite
    VFS_TEST_POSTGRES_URL=... L0_SCRATCH=... uv run python scripts/measure_waits.py --engine postgres

The script writes ``results/waits-<engine>.json`` and stops everything it started when ``--deadline`` passes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

from harness import (
    MODES,
    Bench,
    do_batch,
    do_read,
    do_write,
    environment,
    open_bench,
    postgres_version,
    seed_corpus,
    summary_ms,
    write_results,
)
from harness import agent as authority_of

READERS = 8
BASELINE_SECONDS = 2.0


async def window(bench: Bench, repeat: int, with_batch: bool) -> dict[str, Any]:
    """Readers and one writer run until the batch ends, or for the baseline window when there is none."""
    stop = asyncio.Event()
    reads: list[tuple[float, float, bool, str | None]] = []
    writes: list[tuple[float, float, bool, str | None]] = []
    flushes_before = len(bench.flushes)
    failures_before = len(bench.log_failures)
    high_water_before = bench.high_water
    bench.high_water = len(bench.buffer)

    async def reader(sid: int) -> None:
        async with bench.fs.open_session(authority_of(sid)) as session:
            while not stop.is_set():
                start = time.perf_counter()
                result, _ = await do_read(bench, session)
                kind = None if result.success else str(result.errors[0].kind)
                reads.append((start, time.perf_counter(), result.success, kind))

    async def writer() -> None:
        async with bench.fs.open_session(authority_of(40)) as session:
            n = 0
            while not stop.is_set():
                start = time.perf_counter()
                path = f"/agents/waits/r{repeat}-{int(with_batch)}/w{n:05d}.md"
                result, _ = await do_write(bench, session, path)
                kind = None if result.success else str(result.errors[0].kind)
                writes.append((start, time.perf_counter(), result.success, kind))
                n += 1

    tasks = [asyncio.create_task(reader(i)) for i in range(READERS)] + [asyncio.create_task(writer())]
    await asyncio.sleep(0.3)
    batch: dict[str, Any] = {}
    if with_batch:
        async with bench.fs.open_session(authority_of(50)) as session:
            b_start = time.perf_counter()
            result, counter = await do_batch(bench, session, f"/batch/waits-{repeat}")
            b_end = time.perf_counter()
        batch = {
            "seconds": round(b_end - b_start, 3),
            "ok": result.success,
            "error": None if result.success else f"{result.errors[0].kind}: {result.errors[0].message[:160]}",
            "storage_statements": counter.storage,
            "log_statements": counter.log,
        }
    else:
        b_start = time.perf_counter()
        await asyncio.sleep(BASELINE_SECONDS)
        b_end = time.perf_counter()
    stop.set()
    await asyncio.gather(*tasks)
    window_flushes = bench.flushes[flushes_before:]
    in_window = [f for f in window_flushes if f.started < b_end]
    facts = {
        "batch": batch,
        "reads": _overlapping(reads, b_start, b_end),
        "writes": _overlapping(writes, b_start, b_end),
        "flushes": {
            "count": len(in_window),
            "failed": sum(1 for f in in_window if f.error),
            "errors": sorted({f.error for f in in_window if f.error}),
            "max_seconds": round(max((f.seconds for f in in_window), default=0.0), 4),
            "seconds": [round(f.seconds, 4) for f in in_window],
            "max_depth_seen_by_a_flush": max((f.depth_before for f in in_window), default=0),
        },
        "buffer_high_water": bench.high_water,
        "log_failures": _failures(bench.log_failures[failures_before:]),
    }
    bench.high_water = max(high_water_before, bench.high_water)
    return facts


def _overlapping(calls: list[tuple[float, float, bool, str | None]], start: float, end: float) -> dict[str, Any]:
    during = [c for c in calls if c[0] < end and c[1] > start]
    if not during:
        return {"n": 0}
    return {
        **summary_ms([c[1] - c[0] for c in during]),
        "failures": sum(1 for c in during if not c[2]),
        "failure_kinds": sorted({c[3] for c in during if c[3]}),
    }


def _failures(failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(failures),
        "by_phase": {p: sum(1 for f in failures if f["phase"] == p) for p in sorted({f["phase"] for f in failures})},
        "errors": sorted({f["error"] for f in failures}),
        "max_seconds": round(max((f["seconds"] for f in failures), default=0.0), 3),
    }


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    cells = []
    variants = [(mode, False) for mode in MODES]
    if args.engine == "sqlite":
        variants.append(("leaned", True))
    for mode, own_log_file in variants:
        label = f"{mode}+own-log-file" if own_log_file else mode
        bench = await open_bench(args.engine, mode, label=f"waits-{mode}", own_log_file=own_log_file)
        await seed_corpus(bench.fs)
        for repeat in range(args.repeats):
            baseline = await window(bench, repeat, with_batch=False)
            during = await window(bench, repeat, with_batch=True)
            cells.append({"mode": label, "repeat": repeat, "baseline": baseline, "during_batch": during})
            print(f"{label} repeat {repeat}: batch {during['batch'].get('seconds')} s", file=sys.stderr, flush=True)
        await bench.close()
    return cells


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--deadline", type=float, default=900.0, help="seconds before the run is stopped")
    args = parser.parse_args()
    started = time.perf_counter()
    env = environment()
    if args.engine == "postgres":
        env["postgres"] = await postgres_version()
    try:
        cells = await asyncio.wait_for(run(args), timeout=args.deadline)
    except TimeoutError:
        raise SystemExit(f"deadline of {args.deadline:.0f} s passed; nothing written") from None
    payload = {
        "script": "scripts/measure_waits.py",
        "arguments": vars(args),
        "environment": env,
        "readers": READERS,
        "seconds": round(time.perf_counter() - started, 1),
        "cells": cells,
    }
    out = write_results(f"waits-{args.engine}.json", payload)
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
