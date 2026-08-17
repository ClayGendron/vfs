"""Probe-study harness: where do the overlay probe's milliseconds live?

Measures the real `_entries_for_scan(everything=False)` path (the scan-tier
overlay probe grep_rows pays on every call), decomposes it into Python vs
driver vs DB time, and measures the candidate mechanisms (partial index,
EXISTS fast-path, piggy-backed epoch read).

Run: uv run python bench_probe.py  (from the repo dir; outputs probe_results.json)
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import statistics
import sys
from pathlib import Path as FsPath
from time import monotonic, perf_counter

from sqlalchemy import exists, select, text

from vfs.models import CONTENT_KINDS
from vfs.pattern_matching import compile_filter
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.storage.backends.database.descent import liveness_filters
from vfs.storage.backends.database.dialects import op_execution_options
from vfs.storage.backends.database.grep import CANDIDATE_BUDGET, _entries_for_scan
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.reads import effective_columns, ext_membership

CLONES = FsPath(__file__).parent / "clones"
LIMIT = CANDIDATE_BUDGET  # remaining budget a typical gateless grep passes

RUNS_MS = 40  # ms-scale measurements
RUNS_US = 400  # µs-scale measurements


def stats(samples: list[float]) -> dict:
    return {
        "n": len(samples),
        "median_us": statistics.median(samples) * 1e6,
        "mean_us": statistics.fmean(samples) * 1e6,
        "min_us": min(samples) * 1e6,
        "p90_us": sorted(samples)[int(len(samples) * 0.9)] * 1e6,
    }


async def atime(fn, runs: int, warmup: int = 5) -> dict:
    for _ in range(warmup):
        await fn()
    samples = []
    for _ in range(runs):
        t0 = perf_counter()
        await fn()
        samples.append(perf_counter() - t0)
    return stats(samples)


def stime(fn, runs: int, warmup: int = 5) -> dict:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(runs):
        t0 = perf_counter()
        fn()
        samples.append(perf_counter() - t0)
    return stats(samples)


class CapturingSession:
    """Delegates execute() while recording the statement objects."""

    def __init__(self, session):
        self._session = session
        self.captured = []

    async def execute(self, stmt, *args, **kwargs):
        self.captured.append(stmt)
        return await self._session.execute(stmt, *args, **kwargs)


async def bench_db(db_path: FsPath, *, decompose: bool) -> dict:
    out: dict = {"db": db_path.name}
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db_path}")
    host = storage._host
    refusal = await host.ensure_ready()
    assert refusal is None, refusal
    tables, profile = host.tables, host.profile
    pb, mb = host.parameter_budget, host.membership_budget
    entry = tables.entry
    fetched = effective_columns(None, content=False)  # grep_rows with columns=None
    gates_gated = [compile_filter("drivers/**", ())]
    no_ext: frozenset[str] = frozenset()

    async with host.session_factory() as session:
        if options := op_execution_options(profile, writer=False):
            await session.connection(execution_options=options)

        async def probe(gates):
            nominated, _overflow = await _entries_for_scan(
                session,
                tables,
                profile,
                pb,
                mb,
                gates,
                no_ext,
                everything=False,
                fetched=fetched,
                limit=LIMIT,
                deadline=monotonic() + 10.0,
            )
            return nominated

        # -- 1. reproduce: the real probe, gateless and gated ------------
        rows = await probe([])
        out["probe_gateless_rows"] = len(rows)
        out["probe_gateless"] = await atime(lambda: probe([]), RUNS_MS)
        rows = await probe(gates_gated)
        out["probe_gated_rows"] = len(rows)
        out["probe_gated"] = await atime(lambda: probe(gates_gated), RUNS_MS)

        # capture the exact statements the probe executes
        capture = CapturingSession(session)
        await _entries_for_scan(
            capture, tables, profile, pb, mb, [], no_ext,
            everything=False, fetched=fetched, limit=LIMIT, deadline=monotonic() + 10.0,
        )
        stmt_gateless = capture.captured[0]
        capture2 = CapturingSession(session)
        await _entries_for_scan(
            capture2, tables, profile, pb, mb, gates_gated, no_ext,
            everything=False, fetched=fetched, limit=LIMIT, deadline=monotonic() + 10.0,
        )
        stmt_gated = capture2.captured[0]
        dialect = (await session.connection()).dialect

        sql_gateless = str(stmt_gateless.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        sql_gated = str(stmt_gated.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        out["sql_gateless"] = sql_gateless
        out["sql_gated"] = sql_gated

        if decompose:
            # -- 2a. building the select object --------------------------
            def build_stmt():
                base = [entry.c.kind.in_(sorted(CONTENT_KINDS)), ~entry.c.encoded]
                terms = [*base, entry.c.path != "/", *liveness_filters(entry, profile, include_meta=False)]
                ride = ext_membership(entry, no_ext, mb)
                if ride.predicate is not None:
                    terms.append(ride.predicate)
                ride_along = {"size_bytes", "ext", "name"}
                columns = [entry.c.entry_id, *(entry.c[f] for f in sorted((fetched | ride_along) - {"content"}))]
                return select(*columns).where(*terms).order_by(entry.c.path).limit(LIMIT + 1)

            rebuilt = str(build_stmt().compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
            out["rebuild_matches_captured"] = rebuilt == sql_gateless
            out["build_stmt"] = stime(build_stmt, RUNS_US)

            # -- 2b. cache key + cold compile ----------------------------
            stmt = build_stmt()
            out["cache_key"] = stime(lambda: stmt._generate_cache_key(), RUNS_US)
            out["compile_cold"] = stime(lambda: stmt.compile(dialect=dialect), RUNS_US)

            # -- 2c. execute: reused stmt, fresh-built stmt --------------
            async def exec_reused():
                return list((await session.execute(stmt)).mappings())

            async def exec_fresh():
                return list((await session.execute(build_stmt())).mappings())

            out["execute_reused_stmt"] = await atime(exec_reused, RUNS_MS)
            out["execute_fresh_stmt"] = await atime(exec_fresh, RUNS_MS)

            # compiled-cache check: does repeated execution hit the cache?
            eng_cache = host.engine.sync_engine._compiled_cache
            before = len(eng_cache)
            for _ in range(10):
                await exec_fresh()
            out["compiled_cache_growth_over_10_fresh_executes"] = len(eng_cache) - before

            # -- 2d. text() and raw-driver versions ----------------------
            async def exec_text():
                return (await session.execute(text(sql_gateless))).fetchall()

            out["execute_text"] = await atime(exec_text, RUNS_MS)

            conn = await session.connection()
            raw = await conn.get_raw_connection()
            driver = raw.driver_connection  # aiosqlite.Connection

            async def exec_raw_aiosqlite():
                cur = await driver.execute(sql_gateless)
                rows = await cur.fetchall()
                await cur.close()
                return rows

            out["execute_raw_aiosqlite"] = await atime(exec_raw_aiosqlite, RUNS_MS)

            # gated variants through the same ladder
            async def exec_gated_reused():
                return list((await session.execute(stmt_gated)).mappings())

            out["execute_gated_reused_stmt"] = await atime(exec_gated_reused, RUNS_MS)

        # -- 4/6. EXISTS fast-paths and the epoch read -------------------
        kinds = ", ".join(f"'{k}'" for k in sorted(CONTENT_KINDS))
        e1 = "SELECT EXISTS(SELECT 1 FROM vfs WHERE NOT encoded)"
        e2 = f"SELECT EXISTS(SELECT 1 FROM vfs WHERE NOT encoded AND kind IN ({kinds}))"
        out["exists_text_nokind"] = await atime(
            lambda: session.execute(text(e1)), RUNS_US // 2
        )
        out["exists_text_kind"] = await atime(
            lambda: session.execute(text(e2)), RUNS_US // 2
        )
        orm_exists = select(
            exists(select(entry.c.id).where(~entry.c.encoded, entry.c.kind.in_(sorted(CONTENT_KINDS))))
        )
        out["exists_orm_kind"] = await atime(
            lambda: session.execute(orm_exists), RUNS_US // 2
        )

        meta = tables.meta
        out["epoch_read"] = await atime(lambda: current_epoch(session, tables), RUNS_US // 2)
        wide = select(meta.c.current_gram_epoch, meta.c.reindex_holder, meta.c.reindex_heartbeat).where(
            meta.c.id == 1
        )
        out["epoch_read_wide"] = await atime(lambda: session.execute(wide), RUNS_US // 2)
        overlay_sub = (
            select(exists(select(entry.c.id).where(~entry.c.encoded, entry.c.kind.in_(sorted(CONTENT_KINDS)))))
            .scalar_subquery()
        )
        combined = select(meta.c.current_gram_epoch, overlay_sub.label("overlay")).where(meta.c.id == 1)
        out["epoch_read_plus_exists"] = await atime(lambda: session.execute(combined), RUNS_US // 2)

    # -- pure-DB floor: sync sqlite3 on the same file --------------------
    con = sqlite3.connect(db_path)
    try:
        out["sync_probe_gateless"] = stime(lambda: con.execute(sql_gateless).fetchall(), RUNS_MS)
        out["sync_probe_gated"] = stime(lambda: con.execute(sql_gated).fetchall(), RUNS_MS)
        out["sync_exists_nokind"] = stime(lambda: con.execute(e1).fetchall(), RUNS_US // 2)
        out["sync_exists_kind"] = stime(lambda: con.execute(e2).fetchall(), RUNS_US // 2)
        out["plan_gateless"] = [r[3] for r in con.execute(f"EXPLAIN QUERY PLAN {sql_gateless}")]
        out["plan_gated"] = [r[3] for r in con.execute(f"EXPLAIN QUERY PLAN {sql_gated}")]
        out["plan_exists_nokind"] = [r[3] for r in con.execute(f"EXPLAIN QUERY PLAN {e1}")]
        out["plan_exists_kind"] = [r[3] for r in con.execute(f"EXPLAIN QUERY PLAN {e2}")]
    finally:
        con.close()

    await storage.close()
    return out


async def main() -> None:
    results = []
    for name, decompose in (
        ("base.sqlite", False),
        ("empty.sqlite", True),
        ("empty_p1.sqlite", False),
        ("empty_p2.sqlite", False),
    ):
        print(f"== {name}", file=sys.stderr)
        results.append(await bench_db(CLONES / name, decompose=decompose))
    out_path = FsPath(__file__).parent / "probe_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
