"""What the store costs on the root's own database while readers, one writer and a batch share it.

It repeats the waits run of the log cost study (``agents/2026-11-21-what-a-log-row-per-call-costs``) with
the store as the spec now designs it: in the mount's own SQLite file, four tries of five seconds, and a
flusher that flushes as soon as it is free. Each place is one fresh database with the study's corpus of
2,000 files:

- ``none``: no store; the verbs alone.
- ``same``: the store on a second engine in the mount's own database (decisions 4 and 5).
- ``own-file``: SQLite only; the store in a second file, the shape the study recommended.

Eight reader sessions call ``read`` back to back and put one row behind for each read. One more session
writes one file at a time and then records in a second transaction (``record_after``). The windows:

- ``quiet``: a few seconds with nothing else;
- ``batch``: while one more session writes ``--batch`` entries in one call;
- ``held``: SQLite only; while a connection outside the process's engines holds the file's writer for
  ``--hold`` seconds, which stands for a batch as long as the study's (28 s on its machine).
- ``sweep``: with ``--sweep-rows N``; while one pass removes N expired rows from the store, 5,000 to a
  commit, back to back, as decision 17's pass does.

Then ``--sessions`` sessions each write ``--calls`` files at once, with no reader and no batch, each
write followed by its record.

``--rows log`` puts one unkeyed fifteen-column row for each read, the action log's shape and the worst
case for the buffer. ``--rows stamp`` puts one keyed row for each session and path, over 2,000 paths.

Timings are sizes and never a pass or a fail. The script stops what it started at ``--deadline``.

    S=<a scratch directory outside the repository>
    PROBE_SCRATCH=$S uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_waits.py \
        --engine sqlite --deadline 900
    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs PROBE_SCRATCH=$S \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_waits.py --engine postgres
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import URL, delete, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from standin import PARAMETER_BUDGET, StandinStore, open_store, upsert_stamps

from vfs import AsyncVirtualFileSystem, Authority, Entry, PostgresStorage, Principal, SQLiteStorage

READERS = 8
CORPUS_DIRS = 100
CORPUS_FILES_PER_DIR = 20
LINE = "the policy text of file {seed}, line {n}, with nothing to find in it at all\n"


def body(seed: str, lines: int = 52) -> str:
    """About 4 KB of text, the reference deployment's median file."""
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


class Bench:
    """One fresh database, its mount, and the store in the place asked for."""

    def __init__(self, engine: str, place: str, rows: str) -> None:
        self.engine = engine
        self.place = place
        self.rows = rows
        self.store: StandinStore | None = None
        self.directory: FsPath | None = None
        self.schema: str | None = None
        self.url: Any = None
        self.fs: AsyncVirtualFileSystem
        self.record_failures: list[str] = []

    async def open(self) -> None:
        if self.engine == "sqlite":
            root = FsPath(os.environ["PROBE_SCRATCH"])
            self.directory = root / f"waits-{self.place}-{uuid.uuid4().hex[:8]}"
            self.directory.mkdir(parents=True)
            database = self.directory / "vfs.db"
            storage: Any = SQLiteStorage(path=database)
            self.url = URL.create("sqlite+aiosqlite", database=str(database))
            store_url = (
                URL.create("sqlite+aiosqlite", database=str(self.directory / "kernel.db"))
                if self.place == "own-file"
                else self.url
            )
            dialect = "sqlite"
        else:
            self.url = os.environ["VFS_TEST_POSTGRES_URL"]
            self.schema = f"probe_{uuid.uuid4().hex[:12]}"
            admin = create_async_engine(self.url)
            async with admin.begin() as conn:
                await conn.execute(text(f"CREATE SCHEMA {self.schema}"))
            await admin.dispose()
            storage = PostgresStorage(url=self.url, schema=self.schema)
            store_url = self.url
            dialect = "postgresql"
        self.fs = AsyncVirtualFileSystem(storage=storage)
        first = await self.fs.stat("/")
        if not first.success:
            raise RuntimeError(f"first touch failed: {first.errors}")
        if self.place != "none":
            self.store = open_store(dialect, store_url, schema=self.schema)
            await self.store.first_touch()
        entries = [
            Entry(path=f"/corpus/d{d:02d}/f{f:03d}.md", content=body(f"{d}-{f}"))
            for d in range(CORPUS_DIRS)
            for f in range(CORPUS_FILES_PER_DIR)
        ]
        seeded = await self.fs.write(entries, parents=True)
        if not seeded.success:
            raise RuntimeError(f"seeding failed: {seeded.errors[:2]}")

    async def close(self) -> dict[str, Any]:
        left = await self.store.close() if self.store is not None else 0
        await self.fs.close()
        files: list[str] = []
        if self.directory is not None:
            files = sorted(p.name for p in self.directory.iterdir())
            shutil.rmtree(self.directory, ignore_errors=True)
        if self.schema is not None:
            admin = create_async_engine(self.url)
            async with admin.begin() as conn:
                await conn.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
            await admin.dispose()
        return {"rows_dropped_at_close": left, "files_after_close": files}

    # One read and one write, each with its record.

    async def read(self, session: Any, sid: int, n: int) -> bool:
        path = "/corpus/d07/f003.md" if self.rows == "log" else f"/corpus/d{n % 100:02d}/f{(n // 100) % 20:03d}.md"
        result = await session.read(path)
        if self.store is not None:
            if self.rows == "log":
                self.store.put_behind("log", log_row(f"agent-{sid:02d}", "read", path))
            else:
                row = {"session": f"s{sid}", "path": path, "vid": f"v{n}", "turn": n}
                self.store.put_behind("stamp", row, key=(row["session"], path))
        return result.success

    async def write(self, session: Any, sid: int, path: str) -> tuple[bool, str | None, float]:
        """The verb, then its record; returns the verb's success, its error kind, and the verb's own seconds."""
        start = time.perf_counter()
        result = await session.write(path=path, content=body(path), parents=True)
        verb_seconds = time.perf_counter() - start
        if result.success and self.store is not None:
            store = self.store
            stamp = {"session": f"w{sid}", "path": path, "vid": "v1", "turn": 1}
            change = log_row(f"agent-{sid:02d}", "change", path)

            async def record(conn: Any) -> None:
                await conn.execute(upsert_stamps(store.dialect, store.stamps, [stamp]))
                await conn.execute(store.log.insert().values(change))

            failure = await store.record_after(record, rows=2)
            if failure is not None:
                self.record_failures.append(failure)
        kind = None if result.success else str(result.errors[0].kind)
        return result.success, kind, verb_seconds


def log_row(actor: str, verb: str, path: str) -> dict[str, Any]:
    return {
        "call_id": uuid.uuid4().hex,
        "run_id": None,
        "parent_call_id": None,
        "started_at": datetime.now(UTC),
        "elapsed_ns": 1,
        "actor": actor,
        "verb": verb,
        "paths": json.dumps([path]),
        "path_count": 1,
        "rows": 1,
        "statements": 4,
        "bytes": 4096,
        "outcome": "ok",
        "mount": "/",
        "status": "done",
    }


EXPIRED = datetime(2020, 1, 1, tzinfo=UTC)
CUTOFF = datetime(2021, 1, 1, tzinfo=UTC)
SWEEP_CHUNK = 5_000


async def fill_expired(store: StandinStore, rows: int) -> None:
    """Put ``rows`` log rows in the store whose time is before the sweep's cutoff."""
    for start in range(0, rows, 20_000):
        chunk = [log_row("old", "read", "/old") | {"started_at": EXPIRED} for _ in range(min(20_000, rows - start))]

        async def write(conn: Any, chunk: list[dict[str, Any]] = chunk) -> None:
            for i in range(0, len(chunk), 2_000):
                await conn.execute(store.log.insert().values(chunk[i : i + 2_000]))

        await store.commit(write, what="fill")


async def sweep_pass(store: StandinStore) -> list[int]:
    """Decision 17's pass: one bounded delete to a commit, back to back, until a call removes no row."""
    log = store.log
    inner = select(log.c.call_id).where(log.c.started_at <= CUTOFF).order_by(log.c.started_at).limit(SWEEP_CHUNK)
    statement = delete(log).where(log.c.call_id.in_(inner))
    removed: list[int] = []
    while True:

        async def chunk(conn: Any) -> int:
            return (await conn.execute(statement)).rowcount

        count = await store.commit(chunk, what="sweep")
        removed.append(count)
        if count == 0:
            return removed


async def window(
    bench: Bench, label: str, kind: str, *, seconds: float, batch: int, hold: float, sweep_rows: int = 0
) -> dict[str, Any]:
    """Readers and one writer run until the window's own work ends."""
    stop = asyncio.Event()
    reads: list[tuple[float, float, bool]] = []
    writes: list[tuple[float, float, float, bool, str | None]] = []
    store = bench.store
    settled = await store.settle() if store else True
    opened = time.perf_counter()
    failures_before = len(bench.record_failures)
    dropped_before = store.dropped if store else 0
    if store:
        store.high_water = len(store.buffer)

    async def reader(sid: int) -> None:
        n = sid * 250
        async with bench.fs.open_session(authority(sid)) as session:
            while not stop.is_set():
                start = time.perf_counter()
                ok = await bench.read(session, sid, n)
                reads.append((start, time.perf_counter(), ok))
                n += 1

    async def writer() -> None:
        n = 0
        async with bench.fs.open_session(authority(40)) as session:
            while not stop.is_set():
                start = time.perf_counter()
                ok, error, verb_seconds = await bench.write(session, 40, f"/agents/{label}/w{n:05d}.md")
                writes.append((start, time.perf_counter(), verb_seconds, ok, error))
                n += 1

    if kind == "sweep":
        assert store is not None
        await fill_expired(store, sweep_rows)
        opened = time.perf_counter()
    tasks = [asyncio.create_task(reader(i)) for i in range(READERS)] + [asyncio.create_task(writer())]
    await asyncio.sleep(0.3)
    facts: dict[str, Any] = {"window": kind}
    w_start = time.perf_counter()
    if kind == "quiet":
        await asyncio.sleep(seconds)
    elif kind == "sweep":
        assert store is not None
        facts["sweep_chunks_removed"] = await sweep_pass(store)
    elif kind == "batch":
        entries = [Entry(path=f"/batch/{label}/{i // 100:03d}/f{i:05d}.md", content=body(str(i))) for i in range(batch)]
        w_start = time.perf_counter()
        async with bench.fs.open_session(authority(50)) as session:
            result = await session.write(entries, parents=True)
        facts["batch_ok"] = result.success
        facts["batch_error"] = None if result.success else str(result.errors[0].kind)
        facts["batch_seconds"] = round(time.perf_counter() - w_start, 2)
        if result.success and store is not None:
            # The record a batch through a session writes after it: one stamp and one change row an entry.
            stamps = [{"session": "batch", "path": e.path, "vid": "v1", "turn": 1} for e in entries]
            changes = [log_row("agent-50", "change", e.path) for e in entries]

            async def record(conn: Any) -> None:
                for i in range(0, len(stamps), PARAMETER_BUDGET // 4):
                    await conn.execute(upsert_stamps(store.dialect, store.stamps, stamps[i : i + PARAMETER_BUDGET // 4]))
                for i in range(0, len(changes), PARAMETER_BUDGET // 15):
                    await conn.execute(store.log.insert().values(changes[i : i + PARAMETER_BUDGET // 15]))

            before = time.perf_counter()
            failure = await store.record_after(record, rows=2 * len(entries))
            last = store.commits[-1]
            facts["batch_record"] = {
                "rows": 2 * len(entries),
                "failed": failure,
                "seconds": round(time.perf_counter() - before, 3),
                "waited_to_begin_s": round(last.begin_wait, 3),
                "held_the_writer_s": round(last.seconds - last.begin_wait, 3) if last.attempts == 1 else None,
            }
    else:
        assert bench.directory is not None
        await asyncio.to_thread(_hold_writer, str(bench.directory / "vfs.db"), hold)
    w_end = time.perf_counter()
    stop.set()
    await asyncio.gather(*tasks)
    facts["seconds"] = round(w_end - w_start, 2)
    during_reads = [r for r in reads if r[0] < w_end and r[1] > w_start]
    during_writes = [w for w in writes if w[0] < w_end and w[1] > w_start]
    facts["reads"] = summary([r[1] - r[0] for r in during_reads]) | {
        "failed": sum(1 for r in during_reads if not r[2])
    }
    facts["writes_verb"] = summary([w[2] for w in during_writes]) | {
        "refused": sum(1 for w in during_writes if not w[3]),
        "refusal_kinds": sorted({w[4] for w in during_writes if w[4]}),
    }
    facts["writes_verb_and_record"] = summary([w[1] - w[0] for w in during_writes])
    facts["reads_a_second"] = round(len(during_reads) / max(w_end - w_start, 0.001))
    if store:
        # A commit belongs to the window it was asked for in, so a backlog never counts twice.
        commits = [c for c in store.commits if opened <= c.started < w_end and c.started + c.seconds > w_start]
        flushes = [c for c in commits if c.what == "flush"]
        records = [c for c in commits if c.what == "record"]
        facts["settled_before"] = settled
        facts["flushes"] = {
            "count": len(flushes),
            "failed": sum(1 for c in flushes if c.error),
            "needed_more_than_one_try": sum(1 for c in flushes if c.attempts > 1),
            "errors": sorted({c.error for c in flushes if c.error}),
            "slowest_s": round(max((c.seconds for c in flushes), default=0.0), 3),
            "largest_rows": max((c.rows for c in flushes), default=0),
            "rows_written": sum(c.rows for c in flushes if not c.error),
        }
        facts["records"] = {
            "count": len(records),
            "failed": len(bench.record_failures) - failures_before,
            "needed_more_than_one_try": sum(1 for c in records if c.attempts > 1),
            "slowest_s": round(max((c.seconds for c in records), default=0.0), 3),
        }
        sweeps = [c for c in commits if c.what == "sweep"]
        if sweeps:
            facts["sweep"] = {
                "chunks": len(sweeps),
                "failed": sum(1 for c in sweeps if c.error),
                "whole": summary([c.seconds for c in sweeps]),
                "begin_wait": summary([c.begin_wait for c in sweeps]),
            }
        facts["store_commit_begin_wait"] = summary([c.begin_wait for c in flushes + records])
        facts["store_commit_whole"] = summary([c.seconds for c in flushes + records])
        facts["buffer_high_water"] = store.high_water
        facts["rows_dropped"] = store.dropped - dropped_before
    return facts


def _hold_writer(database: str, seconds: float) -> None:
    """Hold the file's one writer from a connection of no engine, as another process's batch would."""
    conn = sqlite3.connect(database, timeout=30.0, isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    time.sleep(seconds)
    conn.execute("COMMIT")
    conn.close()


async def many_writers(bench: Bench, repeat: int, sessions: int, calls: int, warm: int) -> dict[str, Any]:
    """``sessions`` sessions each write ``calls`` files at once, each write followed by its record."""
    store = bench.store
    commits_before = len(store.commits) if store else 0
    failures_before = len(bench.record_failures)
    verb: list[float] = []
    whole: list[float] = []
    refused: list[str] = []

    async def one(sid: int) -> None:
        async with bench.fs.open_session(authority(sid)) as session:
            for n in range(calls):
                start = time.perf_counter()
                ok, error, verb_seconds = await bench.write(session, sid, f"/many/r{repeat}/s{sid:02d}/w{n:03d}.md")
                if n >= warm:
                    verb.append(verb_seconds)
                    whole.append(time.perf_counter() - start)
                    if not ok:
                        refused.append(str(error))

    start = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(sessions)))
    facts: dict[str, Any] = {
        "seconds": round(time.perf_counter() - start, 2),
        "writes_verb": summary(verb),
        "writes_verb_and_record": summary(whole),
        "refused": len(refused),
        "refusal_kinds": sorted(set(refused)),
    }
    if store:
        records = [c for c in store.commits[commits_before:] if c.what == "record"]
        facts["records"] = {
            "count": len(records),
            "failed": len(bench.record_failures) - failures_before,
            "errors": sorted(set(bench.record_failures[failures_before:])),
            "needed_more_than_one_try": sum(1 for c in records if c.attempts > 1),
            "begin_wait": summary([c.begin_wait for c in records]),
            "whole": summary([c.seconds for c in records]),
        }
    return facts


async def run(args: argparse.Namespace) -> dict[str, Any]:
    places = ["none", "same"] + (["own-file"] if args.engine == "sqlite" else [])
    if args.places:
        places = args.places.split(",")
    cells: list[dict[str, Any]] = []
    for place in places:
        bench = Bench(args.engine, place, args.rows)
        await bench.open()
        cell: dict[str, Any] = {"place": place, "windows": [], "many_writers": []}
        for repeat in range(args.repeats):
            label = f"{place}-r{repeat}"
            kinds = ["quiet"] + (["batch"] if args.batch > 0 else [])
            kinds += ["held"] if args.engine == "sqlite" and args.hold > 0 else []
            kinds += ["sweep"] if args.sweep_rows > 0 and bench.store is not None else []
            for kind in kinds:
                facts = await window(
                    bench, f"{label}-{kind}", kind, seconds=args.quiet, batch=args.batch, hold=args.hold,
                    sweep_rows=args.sweep_rows,
                )
                facts["repeat"] = repeat
                cell["windows"].append(facts)
                print(f"{place} r{repeat} {kind}: {facts['seconds']} s", file=sys.stderr, flush=True)
        if bench.store is not None:
            await bench.store.settle()
        for repeat in range(args.many_repeats):
            facts = await many_writers(bench, repeat, args.sessions, args.calls, args.warm)
            facts["repeat"] = repeat
            cell["many_writers"].append(facts)
            print(f"{place} many r{repeat}: {facts['seconds']} s", file=sys.stderr, flush=True)
        cell["at_close"] = await bench.close()
        cells.append(cell)
    return {"cells": cells}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--rows", choices=("log", "stamp"), default="log")
    parser.add_argument("--places", default="")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--quiet", type=float, default=3.0)
    parser.add_argument("--batch", type=int, default=10_000)
    parser.add_argument("--hold", type=float, default=30.0)
    parser.add_argument("--sweep-rows", type=int, default=0)
    parser.add_argument("--sessions", type=int, default=32)
    parser.add_argument("--calls", type=int, default=6)
    parser.add_argument("--warm", type=int, default=3)
    parser.add_argument("--many-repeats", type=int, default=5)
    parser.add_argument("--deadline", type=float, default=900.0)
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        payload = await asyncio.wait_for(run(args), timeout=args.deadline)
    except TimeoutError:
        raise SystemExit(f"deadline of {args.deadline:.0f} s passed; nothing reported") from None
    payload = {
        "script": "probe_waits.py",
        "arguments": vars(args),
        "sqlite": sqlite3.sqlite_version,
        "seconds": round(time.perf_counter() - started, 1),
        **payload,
    }
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
