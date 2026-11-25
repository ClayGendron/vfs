"""Whose connections a record write should use on Postgres: the mount's pool, or a pool of the store's own.

The spec's choice 2 gives the store a pool of its own, subject to this measurement. ``--sessions`` sessions
each write one file through the kernel and then write one record in a second transaction, as decision
10's record-after form does. Four ways, each on a fresh schema:

- ``none``: no record; the verb alone.
- ``mount-pool``: the record on the mount's own engine and pool (5 kept, 10 more at a peak).
- ``own-15``: the record on a second engine with the same pool defaults, the spec's default.
- ``own-32``: the record on a second engine with a pool of 32.

For each it reports the write's median and 95th percentile (the verb and its record together, and the
verb alone), the record's own time, the connections the server had open at the peak
(``pg_stat_activity``, sampled every 20 ms), the most callers seen waiting on each pool at a sample, and
the record writes that found their pool with every connection out when they asked for one.

``--batches N`` runs N writes of ``--batch`` entries beside the sessions, with eight readers that put a
row behind for each read, to show what a record write and a flush do when the mount's pool is exhausted.
The sessions then write until the batches end or ``--window`` seconds pass, and batches still running
are cancelled.

Timings are sizes and never a pass or a fail. The script stops what it started at ``--deadline``.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_postgres_pool.py
    VFS_TEST_POSTGRES_URL=... uv run python .../probe_postgres_pool.py --batches 32 --window 90
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from standin import StandinStore, open_store, upsert_stamps

from vfs import AsyncVirtualFileSystem, Authority, Entry, PostgresStorage, Principal

WAYS = ("none", "mount-pool", "own-15", "own-32")
LINE = "the policy text of file {seed}, line {n}, with nothing to find in it at all\n"


def body(seed: str, lines: int = 52) -> str:
    return "".join(LINE.format(seed=seed, n=n) for n in range(lines))


def authority(n: int) -> Authority:
    return Authority.of(Principal(f"agent-{n:02d}"))


def summary(seconds: list[float]) -> dict[str, Any]:
    if not seconds:
        return {"n": 0}
    ordered = sorted(seconds)
    rank = max(0, min(len(ordered) - 1, round(0.95 * len(ordered) + 0.5) - 1))
    return {
        "n": len(ordered),
        "median_ms": round(statistics.median(ordered) * 1000, 1),
        "p95_ms": round(ordered[rank] * 1000, 1),
        "max_ms": round(ordered[-1] * 1000, 1),
    }


class PoolWatch:
    """What one pool was asked for: the most connections out, the most callers waiting, exhausted checkouts."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.pool = engine.sync_engine.pool
        self.most_out = 0
        self.most_waiting = 0
        self.checkouts = 0
        self.limit = self.pool.size() + getattr(self.pool, "_max_overflow", 0)
        event.listen(engine.sync_engine, "checkout", self._on_checkout)

    def _on_checkout(self, *_: Any) -> None:
        self.checkouts += 1
        self.most_out = max(self.most_out, self.pool.checkedout())

    def sample(self) -> None:
        self.most_out = max(self.most_out, self.pool.checkedout())
        queue = getattr(getattr(self.pool, "_pool", None), "_queue", None)
        waiting = len(getattr(queue, "_getters", ()))
        self.most_waiting = max(self.most_waiting, waiting)

    def facts(self) -> dict[str, Any]:
        return {"limit": self.limit, "most_out": self.most_out, "most_callers_waiting": self.most_waiting,
                "checkouts": self.checkouts}


async def one_way(way: str, args: argparse.Namespace, repeat: int) -> dict[str, Any]:
    url = os.environ["VFS_TEST_POSTGRES_URL"]
    schema = f"probe_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(url, pool_size=2, max_overflow=0)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
    storage = PostgresStorage(url=url, schema=schema)
    fs = AsyncVirtualFileSystem(storage=storage)
    first = await fs.stat("/")
    if not first.success:
        raise RuntimeError(f"first touch failed: {first.errors}")
    store: StandinStore | None = None
    if way == "mount-pool":
        store = open_store("postgresql", url, schema=schema, borrowed=storage.engine)
    elif way == "own-15":
        store = open_store("postgresql", url, schema=schema)
    elif way == "own-32":
        store = open_store("postgresql", url, schema=schema, engine_arguments={"pool_size": 32, "max_overflow": 0})
    if store is not None:
        await store.first_touch()
    mount_watch = PoolWatch(storage.engine)
    store_watch = PoolWatch(store.engine) if store is not None and store.owns_engine else None
    seeded = await fs.write(
        [Entry(path=f"/corpus/d{d:02d}/f{f:03d}.md", content=body(f"{d}-{f}")) for d in range(20) for f in range(20)],
        parents=True,
    )
    if not seeded.success:
        raise RuntimeError(f"seeding failed: {seeded.errors[:2]}")

    stop = asyncio.Event()
    peak = {"connections": 0}

    async def monitor() -> None:
        count = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()")
        while not stop.is_set():
            mount_watch.sample()
            if store_watch is not None:
                store_watch.sample()
            async with admin.connect() as conn:
                peak["connections"] = max(peak["connections"], (await conn.execute(count)).scalar_one())
            await asyncio.sleep(0.02)

    verb: list[float] = []
    whole: list[float] = []
    record_whole: list[float] = []
    refused: list[str] = []
    record_failures: list[str] = []
    exhausted_checkouts = 0

    async def write(session: Any, sid: int, path: str, counted: bool) -> None:
        nonlocal exhausted_checkouts
        start = time.perf_counter()
        result = await session.write(path=path, content=body(path), parents=True)
        verb_end = time.perf_counter()
        if result.success and store is not None:
            stamp = {"session": f"w{sid}", "path": path, "vid": "v1", "turn": 1}
            pool = store.engine.sync_engine.pool
            limit = pool.size() + getattr(pool, "_max_overflow", 0)
            if pool.checkedout() >= limit:
                exhausted_checkouts += 1
            before = len(store.commits)

            async def record(conn: Any) -> None:
                await conn.execute(upsert_stamps("postgresql", store.stamps, [stamp]))

            failure = await store.record_after(record, rows=1)
            if failure is not None:
                record_failures.append(failure)
            elif counted:
                mine = store.commits[before:]
                done = [c for c in mine if c.what == "record"]
                if done:
                    record_whole.append(done[-1].seconds)
        if counted:
            verb.append(verb_end - start)
            whole.append(time.perf_counter() - start)
            if not result.success:
                refused.append(str(result.errors[0].kind))

    async def writer(sid: int) -> None:
        async with fs.open_session(authority(sid)) as session:
            n = 0
            while not stop.is_set() and (args.batches or n < args.calls):
                await write(session, sid, f"/w/r{repeat}/s{sid:02d}/f{n:04d}.md", counted=n >= args.warm)
                n += 1

    reads: list[float] = []

    async def reader(sid: int) -> None:
        async with fs.open_session(authority(100 + sid)) as session:
            n = 0
            while not stop.is_set():
                start = time.perf_counter()
                path = f"/corpus/d{n % 20:02d}/f{(n // 20) % 20:03d}.md"
                await session.read(path)
                reads.append(time.perf_counter() - start)
                if store is not None:
                    row = {"session": f"r{sid}", "path": path, "vid": "v", "turn": n}
                    store.put_behind("stamp", row, key=(row["session"], path))
                n += 1

    batches_done: list[Any] = []

    async def batch(b: int) -> None:
        entries = [Entry(path=f"/batch/r{repeat}/b{b:02d}/{i // 100:03d}/f{i:05d}.md", content=body(str(i)))
                   for i in range(args.batch)]
        async with fs.open_session(authority(200 + b)) as session:
            start = time.perf_counter()
            result = await session.write(entries, parents=True)
            batches_done.append((result.success, None if result.success else str(result.errors[0].kind),
                                 time.perf_counter() - start))

    watch = asyncio.create_task(monitor())
    started = time.perf_counter()
    if args.batches:
        readers = [asyncio.create_task(reader(i)) for i in range(8)]
        writers = [asyncio.create_task(writer(i)) for i in range(args.sessions)]
        batch_tasks = [asyncio.create_task(batch(b)) for b in range(args.batches)]
        _, pending = await asyncio.wait(batch_tasks, timeout=args.window)
        stop.set()
        for task in pending:
            task.cancel()
        await asyncio.gather(*batch_tasks, *writers, *readers, return_exceptions=True)
    else:
        await asyncio.gather(*(writer(i) for i in range(args.sessions)))
        stop.set()
    elapsed = time.perf_counter() - started
    await watch
    facts: dict[str, Any] = {
        "way": way,
        "repeat": repeat,
        "seconds": round(elapsed, 2),
        "write_verb_and_record": summary(whole),
        "write_verb_alone": summary(verb),
        "writes_refused": len(refused),
        "refusal_kinds": sorted(set(refused)),
        "connections_open_at_the_peak": peak["connections"],
        "mount_pool": mount_watch.facts(),
    }
    if store is not None:
        records = [c for c in store.commits if c.what == "record"]
        flushes = [c for c in store.commits if c.what == "flush"]
        facts["record"] = summary(record_whole) | {
            "failed": len(record_failures),
            "errors": sorted({f[:110] for f in record_failures}),
            "all_records": len(records),
        }
        facts["record_checkouts_that_found_the_pool_exhausted"] = exhausted_checkouts
        if store_watch is not None:
            facts["store_pool"] = store_watch.facts()
        if flushes:
            facts["flushes"] = {
                "count": len(flushes),
                "failed": sum(1 for c in flushes if c.error),
                "errors": sorted({(c.error or "")[:110] for c in flushes if c.error}),
                "whole": summary([c.seconds for c in flushes]),
                "buffer_high_water": store.high_water,
                "rows_dropped": store.dropped,
            }
    if args.batches:
        facts["reads"] = summary(reads)
        facts["batches"] = {
            "started": args.batches,
            "served": sum(1 for b in batches_done if b[0]),
            "refused": sum(1 for b in batches_done if not b[0]),
            "refusal_kinds": sorted({b[1] for b in batches_done if b[1]}),
            "cancelled_at_the_window": args.batches - len(batches_done),
            "seconds": summary([b[2] for b in batches_done]),
        }
    if store is not None:
        await store.close()
    await fs.close()
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    await admin.dispose()
    return facts


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    cells = []
    ways = args.ways.split(",") if args.ways else list(WAYS)
    for repeat in range(args.repeats):
        order = ways[repeat % len(ways) :] + ways[: repeat % len(ways)]
        for way in order:
            cell = await one_way(way, args, repeat)
            cells.append(cell)
            print(f"{way} r{repeat}: {cell['seconds']} s, median {cell['write_verb_and_record'].get('median_ms')} ms",
                  file=sys.stderr, flush=True)
    return cells


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sessions", type=int, default=32)
    parser.add_argument("--calls", type=int, default=23)
    parser.add_argument("--warm", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--batches", type=int, default=0)
    parser.add_argument("--batch", type=int, default=10_000)
    parser.add_argument("--window", type=float, default=90.0)
    parser.add_argument("--ways", default="")
    parser.add_argument("--deadline", type=float, default=900.0)
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        cells = await asyncio.wait_for(run(args), timeout=args.deadline)
    except TimeoutError:
        raise SystemExit(f"deadline of {args.deadline:.0f} s passed; nothing reported") from None
    payload = {"script": "probe_postgres_pool.py", "arguments": vars(args),
               "seconds": round(time.perf_counter() - started, 1), "cells": cells}
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
