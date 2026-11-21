"""Statements and wall time per call: four calls, three modes, 1 and 32 sessions, on one engine.

Each repeat opens one fresh database per mode, seeds the 2,000-file corpus, and runs ``read``, ``grep`` and a
one-file ``write`` under 1 session and then under 32. The 10,000-entry ``write`` gets a fresh database of its
own per repeat, because 32 of them leave 320,000 files behind. The modes rotate their order each repeat, so
no mode always runs first on a cold machine.

    L0_SCRATCH=/path/outside/the/repo uv run python scripts/measure_calls.py --engine sqlite
    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs L0_SCRATCH=... \
        uv run python scripts/measure_calls.py --engine postgres

The script writes ``results/calls-<engine>.json`` and stops everything it started when ``--deadline`` passes.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from harness import (
    MODES,
    Bench,
    do_batch,
    do_grep,
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
from sqlalchemy import func, select

if TYPE_CHECKING:
    from vfs import AsyncSession

AGENT_VERBS = ("read", "grep", "write")
WARMUP_CALLS = 3


async def agent_calls(bench: Bench, verb: str, sessions: int, calls_each: int, tag: str) -> list[dict[str, Any]]:
    """``sessions`` concurrent sessions, each issuing ``calls_each`` calls of ``verb`` back to back."""
    records: list[dict[str, Any]] = []

    async def one_session(sid: int) -> None:
        async with bench.fs.open_session(authority_of(sid)) as session:
            for n in range(WARMUP_CALLS + calls_each):
                start = time.perf_counter()
                result, counter = await _one(bench, session, verb, f"/agents/{tag}/s{sid:02d}/w{n:03d}.md")
                seconds = time.perf_counter() - start
                if n >= WARMUP_CALLS:
                    records.append(
                        {
                            "seconds": seconds,
                            "storage": counter.storage,
                            "log": counter.log,
                            "ok": result.success,
                            "error": None if result.success else str(result.errors[0].kind),
                        }
                    )

    await asyncio.gather(*(one_session(sid) for sid in range(sessions)))
    return records


async def _one(bench: Bench, session: AsyncSession, verb: str, path: str):  # noqa: ANN202
    if verb == "read":
        return await do_read(bench, session)
    if verb == "grep":
        return await do_grep(bench, session)
    return await do_write(bench, session, path)


async def batch_calls(bench: Bench, sessions: int, tag: str) -> list[dict[str, Any]]:
    """``sessions`` concurrent sessions, each issuing one 10,000-entry write."""
    records: list[dict[str, Any]] = []

    async def one_session(sid: int) -> None:
        async with bench.fs.open_session(authority_of(sid)) as session:
            start = time.perf_counter()
            result, counter = await do_batch(bench, session, f"/batch/{tag}/s{sid:02d}")
            records.append(
                {
                    "seconds": time.perf_counter() - start,
                    "storage": counter.storage,
                    "log": counter.log,
                    "ok": result.success,
                    "error": None if result.success else f"{result.errors[0].kind}: {result.errors[0].message[:160]}",
                }
            )

    await asyncio.gather(*(one_session(sid) for sid in range(sessions)))
    return records


async def finish(bench: Bench, expected_rows: int) -> dict[str, Any]:
    """Drain the buffer, check one row per call landed, and close the database."""
    await bench.drain()
    logged = None
    if bench.mode != "none":
        async with bench.log_engine.connect() as conn:
            logged = (await conn.execute(select(func.count()).select_from(bench.table))).scalar_one()
    facts = {
        "expected_rows": expected_rows,
        "logged_rows": logged,
        "flushes": len(bench.flushes),
        "flush_errors": sum(1 for f in bench.flushes if f.error),
        "flush_max_parameters": max((f.parameters for f in bench.flushes), default=0),
        "flush_max_seconds": round(max((f.seconds for f in bench.flushes), default=0.0), 4),
        "buffer_high_water": bench.high_water,
        "buffer_overflowed": bench.overflowed,
        "log_failures": len(bench.log_failures),
        "log_failure_errors": sorted({f["error"] for f in bench.log_failures}),
        "log_failure_max_seconds": round(max((f["seconds"] for f in bench.log_failures), default=0.0), 3),
        "log_engine_statements": bench.log_tally.statements,
        "log_engine_unowned": bench.log_tally.unowned,
        "log_engine_max_parameters": bench.log_tally.max_parameters,
    }
    await bench.close()
    return facts


async def run(args: argparse.Namespace) -> dict[str, Any]:
    raw: dict[str, list[dict[str, Any]]] = defaultdict(list)
    closing: list[dict[str, Any]] = []
    for repeat in range(args.repeats):
        order = MODES[repeat % 3 :] + MODES[: repeat % 3]
        for mode in order:
            bench = await open_bench(args.engine, mode, label=f"calls-{mode}-{repeat}")
            await seed_corpus(bench.fs)
            calls = 0
            for verb in AGENT_VERBS:
                for sessions, each in ((1, args.single_calls), (32, args.concurrent_calls)):
                    records = await agent_calls(bench, verb, sessions, each, f"r{repeat}-{verb}-{sessions}")
                    calls += sessions * (WARMUP_CALLS + each)
                    for rec in records:
                        rec["repeat"] = repeat
                    raw[f"{verb}|{sessions}|{mode}"].extend(records)
            closing.append({"mode": mode, "repeat": repeat, "kind": "agent", **await finish(bench, calls)})
            print(f"repeat {repeat} {mode}: agent calls done", file=sys.stderr, flush=True)
        for sessions, repeats in ((1, args.repeats), (32, args.batch32_repeats)):
            if repeat >= repeats:
                continue
            for mode in order:
                bench = await open_bench(args.engine, mode, label=f"batch-{mode}-{repeat}")
                records = await batch_calls(bench, sessions, f"r{repeat}")
                for rec in records:
                    rec["repeat"] = repeat
                raw[f"batch|{sessions}|{mode}"].extend(records)
                closing.append(
                    {"mode": mode, "repeat": repeat, "kind": f"batch{sessions}", **await finish(bench, sessions)}
                )
                print(f"repeat {repeat} {mode}: batch x{sessions} done", file=sys.stderr, flush=True)
    return {"cells": summarize(raw), "closing": closing}


def summarize(raw: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    cells = []
    for key, records in sorted(raw.items()):
        verb, sessions, mode = key.split("|")
        by_repeat: dict[int, list[float]] = defaultdict(list)
        for rec in records:
            by_repeat[rec["repeat"]].append(rec["seconds"])
        medians = [statistics.median(v) for v in by_repeat.values()]
        p95s = [summary_ms(v)["p95_ms"] for v in by_repeat.values()]
        cells.append(
            {
                "verb": verb,
                "sessions": int(sessions),
                "mode": mode,
                "calls": len(records),
                "failures": sum(1 for r in records if not r["ok"]),
                "failure_kinds": sorted({r["error"] for r in records if r["error"]}),
                "storage_statements": _distribution(r["storage"] for r in records),
                "log_statements": _distribution(r["log"] for r in records),
                "median_ms": round(statistics.median(medians) * 1000, 3),
                "median_spread_ms": round((max(medians) - min(medians)) * 1000, 3),
                "repeat_medians_ms": [round(m * 1000, 3) for m in medians],
                "p95_ms": round(statistics.median(p95s), 3),
                "repeat_p95s_ms": p95s,
                "pooled": summary_ms([r["seconds"] for r in records]),
            }
        )
    return cells


def _distribution(values: Any) -> dict[str, int]:
    counts: dict[int, int] = defaultdict(int)
    for v in values:
        counts[v] += 1
    return {str(k): counts[k] for k in sorted(counts)}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--batch32-repeats", type=int, default=2)
    parser.add_argument("--single-calls", type=int, default=60)
    parser.add_argument("--concurrent-calls", type=int, default=15)
    parser.add_argument("--deadline", type=float, default=1800.0, help="seconds before the run is stopped")
    args = parser.parse_args()
    started = time.perf_counter()
    env = environment()
    if args.engine == "postgres":
        env["postgres"] = await postgres_version()
    try:
        body = await asyncio.wait_for(run(args), timeout=args.deadline)
    except TimeoutError:
        raise SystemExit(f"deadline of {args.deadline:.0f} s passed; nothing written") from None
    payload = {
        "script": "scripts/measure_calls.py",
        "arguments": vars(args),
        "environment": env,
        "seconds": round(time.perf_counter() - started, 1),
        **body,
    }
    out = write_results(f"calls-{args.engine}.json", payload)
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
