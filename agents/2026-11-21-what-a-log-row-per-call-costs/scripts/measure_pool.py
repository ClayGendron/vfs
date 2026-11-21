"""Whether 32 concurrent sessions need a connection pool larger than SQLAlchemy's default, with no log.

Two fresh databases per engine: one with the default pool (5 connections and 10 overflow), one with 32 and no
overflow. Each runs 32 sessions of five ``read`` calls, then of five ``grep`` calls, three times, and records
each call's wall time and the calls per second of the whole window.

    L0_SCRATCH=... uv run python scripts/measure_pool.py --engine sqlite
    VFS_TEST_POSTGRES_URL=... L0_SCRATCH=... uv run python scripts/measure_pool.py --engine postgres

The script writes ``results/pool-<engine>.json`` and stops everything it started when ``--deadline`` passes.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from typing import Any

from harness import agent as authority_of
from harness import do_grep, do_read, environment, open_bench, postgres_version, seed_corpus, summary_ms, write_results

SESSIONS = 32
CALLS_EACH = 5


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    cells = []
    for pool in ("default", "32"):
        arguments = {"pool_size": 32, "max_overflow": 0} if pool == "32" else None
        bench = await open_bench(args.engine, "none", label=f"pool-{pool}", storage_arguments=arguments)
        await seed_corpus(bench.fs)
        for name, verb in (("read", do_read), ("grep", do_grep)):
            for repeat in range(args.repeats):
                seconds: list[float] = []

                async def one(sid: int, verb=verb, seconds=seconds, bench=bench) -> None:  # noqa: ANN001
                    async with bench.fs.open_session(authority_of(sid)) as session:
                        for _ in range(CALLS_EACH):
                            start = time.perf_counter()
                            await verb(bench, session)
                            seconds.append(time.perf_counter() - start)

                start = time.perf_counter()
                await asyncio.gather(*(one(sid) for sid in range(SESSIONS)))
                wall = time.perf_counter() - start
                cells.append(
                    {
                        "pool": pool,
                        "verb": name,
                        "repeat": repeat,
                        **summary_ms(seconds),
                        "calls_per_second": round(len(seconds) / wall, 1),
                    }
                )
        await bench.close()
        print(f"pool {pool} done", file=sys.stderr, flush=True)
    return cells


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--deadline", type=float, default=600.0, help="seconds before the run is stopped")
    args = parser.parse_args()
    started = time.perf_counter()
    env = environment()
    if args.engine == "postgres":
        env["postgres"] = await postgres_version()
    try:
        cells = await asyncio.wait_for(run(args), timeout=args.deadline)
    except TimeoutError:
        raise SystemExit(f"deadline of {args.deadline:.0f} s passed; nothing written") from None
    medians = {
        f"{p}|{v}": statistics.median(c["median_ms"] for c in cells if c["pool"] == p and c["verb"] == v)
        for p in ("default", "32")
        for v in ("read", "grep")
    }
    payload = {
        "script": "scripts/measure_pool.py",
        "arguments": vars(args),
        "environment": env,
        "seconds": round(time.perf_counter() - started, 1),
        "median_of_medians_ms": medians,
        "cells": cells,
    }
    out = write_results(f"pool-{args.engine}.json", payload)
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
