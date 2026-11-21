"""How big the log grows, and what reclaiming one day of it costs, on one engine.

One fresh database with the corpus and the log table. The table is filled with ``--days`` days of 150,000
rows each, the reference deployment's verb calls, and measured after the first day and after the last: the
heap, the indexes, and bytes per row. Then the oldest day is deleted in chunks of ``--chunk-rows`` by one
statement shape whose size never grows (a ``LIMIT`` subquery, one bind parameter for the cutoff and one for
the chunk). While it runs, eight readers, one one-file writer and one probe that inserts a single log row
every 50 ms measure whether anything waits. Last, one more day is inserted, to see whether the space the
delete freed is reused.

The fill uses the leaned design's own flush shape for its first day (256 rows to one insert) and a bulk load
after, because the fill is setup, not the thing measured: ``executemany`` on SQLite, and on Postgres the
driver's ``COPY``, because ``executemany`` took about a minute a day there.

    L0_SCRATCH=... uv run python scripts/measure_growth.py --engine sqlite
    VFS_TEST_POSTGRES_URL=... L0_SCRATCH=... uv run python scripts/measure_growth.py --engine postgres

The script writes ``results/growth-<engine>.json`` and stops everything it started when ``--deadline`` passes.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from harness import (
    CURRENT,
    LOG_FLUSH_ROWS,
    LOG_TABLE,
    Bench,
    Counter,
    Row,
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
from sqlalchemy import delete, func, insert, select, text
from ulid import ULID

ROWS_PER_DAY = 150_000
BULK_ROWS = 10_000
READERS = 8
PROBE_INTERVAL = 0.05
BASELINE_SECONDS = 2.0

# The mix of a day's calls: three reads, lists, globs and greps per write or edit, search under a tenth.
VERB_MIX = (("read", 40), ("ls", 12), ("glob", 8), ("grep", 15), ("stat", 0), ("write", 15), ("edit", 6), ("search", 4))
MANY_PATH_VERBS = frozenset({"ls", "glob", "grep", "search"})


def day_rows(rng: random.Random, day_start: datetime) -> list[dict[str, Any]]:
    """150,000 rows spread over one day, with paths shaped like the reference deployment's (depth 6)."""
    verbs = [v for v, weight in VERB_MIX for _ in range(weight)]
    rows = []
    for n in range(ROWS_PER_DAY):
        verb = rng.choice(verbs)
        count = rng.randint(1, 40) if verb in MANY_PATH_VERBS else 1
        paths = [_path(rng) for _ in range(min(count, 16))]
        in_run = rng.random() < 0.3
        row = Row(
            call_id=str(ULID()),
            run_id=str(ULID()) if in_run else None,
            parent_call_id=str(ULID()) if in_run and rng.random() < 0.3 else None,
            started_at=day_start + timedelta(seconds=n * 86_400 / ROWS_PER_DAY),
            actor=f"user-{rng.randint(0, 999):04d}",
            verb=verb,
            mount="/enterprise",
            paths=paths,
            path_count=count,
            elapsed_ns=rng.randint(2_000_000, 80_000_000),
            rows=count,
            statements=rng.randint(4, 30),
            bytes=rng.randint(0, 64_000),
            outcome="ok" if rng.random() < 0.97 else "vfs.not_found",
            status="done",
        )
        rows.append(row.values())
    return rows


def _path(rng: random.Random) -> str:
    return (
        f"/enterprise/dept-{rng.randint(0, 40):02d}/team-{rng.randint(0, 9)}/projects/"
        f"p-{rng.randint(0, 9999):04d}/doc-{rng.randint(0, 99999):05d}.md"
    )


async def fill_day(bench: Bench, rows: list[dict[str, Any]], *, flush_shape: bool) -> dict[str, Any]:
    started = time.perf_counter()
    before = bench.log_tally.statements
    async with bench.log_engine.begin() as conn:
        if flush_shape:
            for i in range(0, len(rows), LOG_FLUSH_ROWS):
                await conn.execute(insert(bench.table).values(rows[i : i + LOG_FLUSH_ROWS]))
        elif bench.engine_kind == "postgres":
            # asyncpg's COPY: SQLAlchemy's executemany ran about a minute a day here, too slow for 30 days.
            raw = await conn.get_raw_connection()
            columns = [c.name for c in bench.table.c]
            records = [tuple(r[c] for c in columns) for r in rows]
            await raw.driver_connection.copy_records_to_table(  # ty: ignore[unresolved-attribute]
                LOG_TABLE, records=records, columns=columns, schema_name=bench.table.schema
            )
        else:
            for i in range(0, len(rows), BULK_ROWS):
                await conn.execute(insert(bench.table), rows[i : i + BULK_ROWS])
    return {"seconds": round(time.perf_counter() - started, 2), "statements": bench.log_tally.statements - before}


async def table_bytes(bench: Bench) -> dict[str, Any]:
    """The log's heap and index bytes, read from the engine's own catalog of page use."""
    async with bench.log_engine.connect() as conn:
        rows = (await conn.execute(select(func.count()).select_from(bench.table))).scalar_one()
        if bench.engine_kind == "sqlite":
            used = (
                await conn.execute(
                    text(
                        "SELECT name, SUM(pgsize) FROM dbstat WHERE name IN "
                        "(SELECT name FROM sqlite_master WHERE tbl_name = :t) GROUP BY name"
                    ),
                    {"t": LOG_TABLE},
                )
            ).all()
            by_name = {name: int(size) for name, size in used}
            heap = by_name.pop(LOG_TABLE, 0)
            indexes = sum(by_name.values())
            page = (await conn.execute(text("PRAGMA page_size"))).scalar_one()
            free = (await conn.execute(text("PRAGMA freelist_count"))).scalar_one()
            pages = (await conn.execute(text("PRAGMA page_count"))).scalar_one()
            extra = {"file_bytes": page * pages, "freelist_bytes": page * free, "index_bytes_by_name": by_name}
        else:
            qualified = f"{bench.table.schema}.{LOG_TABLE}"
            heap, indexes, total = (
                await conn.execute(
                    text("SELECT pg_relation_size(:t), pg_indexes_size(:t), pg_total_relation_size(:t)"),
                    {"t": qualified},
                )
            ).one()
            extra = {"total_relation_bytes": int(total)}
    total_bytes = int(heap) + int(indexes)
    return {
        "rows": rows,
        "heap_bytes": int(heap),
        "index_bytes": int(indexes),
        "bytes": total_bytes,
        "bytes_per_row": round(total_bytes / rows, 1) if rows else None,
        **extra,
    }


async def reclaim(bench: Bench, cutoff: datetime, chunk_rows: int) -> dict[str, Any]:
    """Delete every row older than ``cutoff`` in chunks, one bounded statement each, with probes running."""
    stop = asyncio.Event()
    probes: dict[str, list[tuple[float, float, bool]]] = {"read": [], "write": [], "log_row": []}
    chunks: list[dict[str, Any]] = []

    async def reader(sid: int) -> None:
        async with bench.fs.open_session(authority_of(sid)) as session:
            while not stop.is_set():
                start = time.perf_counter()
                result, _ = await do_read(bench, session)
                probes["read"].append((start, time.perf_counter(), result.success))

    async def writer() -> None:
        async with bench.fs.open_session(authority_of(40)) as session:
            n = 0
            while not stop.is_set():
                start = time.perf_counter()
                result, _ = await do_write(bench, session, f"/agents/growth/w{n:05d}.md")
                probes["write"].append((start, time.perf_counter(), result.success))
                n += 1

    async def log_row_probe() -> None:
        while not stop.is_set():
            start = time.perf_counter()
            ok = await bench._log_write("probe", "probe", insert(bench.table).values(_probe_row()))
            probes["log_row"].append((start, time.perf_counter(), ok))
            await asyncio.sleep(PROBE_INTERVAL)

    tasks = [asyncio.create_task(reader(i)) for i in range(READERS)]
    tasks += [asyncio.create_task(writer()), asyncio.create_task(log_row_probe())]
    base_start = time.perf_counter()
    await asyncio.sleep(BASELINE_SECONDS)
    base_end = time.perf_counter()
    # The delete's statements are counted in this task's context alone, never the probes' or the flusher's.
    own = Counter()
    token = CURRENT.set(own)
    oldest = select(bench.table.c.call_id).where(bench.table.c.started_at < cutoff)
    oldest = oldest.order_by(bench.table.c.started_at).limit(chunk_rows)
    del_start = time.perf_counter()
    while True:
        started = time.perf_counter()
        async with bench.log_engine.begin() as conn:
            deleted = (await conn.execute(delete(bench.table).where(bench.table.c.call_id.in_(oldest)))).rowcount
        chunks.append({"rows": deleted, "seconds": round(time.perf_counter() - started, 4)})
        if deleted == 0:
            break
    del_end = time.perf_counter()
    CURRENT.reset(token)
    stop.set()
    await asyncio.gather(*tasks)
    return {
        "chunk_rows": chunk_rows,
        "chunks": len(chunks),
        "rows_deleted": sum(c["rows"] for c in chunks),
        "statements": own.log,
        "seconds": round(del_end - del_start, 2),
        "chunk_seconds": summary_ms([c["seconds"] for c in chunks]),
        "probes_baseline": {k: _window(v, base_start, base_end) for k, v in probes.items()},
        "probes_during_delete": {k: _window(v, del_start, del_end) for k, v in probes.items()},
    }


def _probe_row() -> dict[str, Any]:
    now = datetime.now(UTC)
    return Row(call_id=str(ULID()), started_at=now, actor="probe", verb="probe", mount="/", status="done").values()


def _window(calls: list[tuple[float, float, bool]], start: float, end: float) -> dict[str, Any]:
    during = [c for c in calls if c[0] < end and c[1] > start]
    if not during:
        return {"n": 0}
    return {**summary_ms([c[1] - c[0] for c in during]), "failures": sum(1 for c in during if not c[2])}


async def run(args: argparse.Namespace) -> dict[str, Any]:
    rng = random.Random(20261121)
    bench = await open_bench(args.engine, "leaned", label="growth")
    await seed_corpus(bench.fs)
    first_day = datetime(2026, 10, 1, tzinfo=UTC)
    fills = []
    sizes: dict[str, Any] = {}
    for day in range(args.days):
        rows = day_rows(rng, first_day + timedelta(days=day))
        fills.append(await fill_day(bench, rows, flush_shape=day == 0))
        if day == 0:
            sizes["after_1_day"] = await table_bytes(bench)
        print(f"day {day + 1} filled", file=sys.stderr, flush=True)
    sizes[f"after_{args.days}_days"] = await table_bytes(bench)
    reclaimed = await reclaim(bench, first_day + timedelta(days=1), args.chunk_rows)
    sizes["after_reclaiming_1_day"] = await table_bytes(bench)
    if args.engine == "postgres":
        async with bench.log_engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text(f"VACUUM {bench.table.schema}.{LOG_TABLE}"))
        sizes["after_vacuum"] = await table_bytes(bench)
    rows = day_rows(rng, first_day + timedelta(days=args.days))
    fills.append(await fill_day(bench, rows, flush_shape=False))
    sizes["after_one_more_day"] = await table_bytes(bench)
    await bench.close()
    return {
        "rows_per_day": ROWS_PER_DAY,
        "first_day_fill": fills[0],
        "sizes": sizes,
        "reclaim": reclaimed,
        "row_shape": {
            "verb_mix": dict(VERB_MIX),
            "many_path_verbs": sorted(MANY_PATH_VERBS),
            "paths_for_many": "uniform 1 to 40, first 16 stored",
            "share_in_a_run": 0.3,
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--chunk-rows", type=int, default=5_000)
    parser.add_argument("--deadline", type=float, default=1200.0, help="seconds before the run is stopped")
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
        "script": "scripts/measure_growth.py",
        "arguments": vars(args),
        "environment": env,
        "seconds": round(time.perf_counter() - started, 1),
        **body,
    }
    out = write_results(f"growth-{args.engine}.json", payload)
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
