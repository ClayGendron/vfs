"""The statements the spec quotes, run under two connections on SQLite and on Postgres.

Each check builds its own small tables in a fresh SQLite file or a fresh Postgres schema and reports
counts. Nothing here reads a clock except to stage an order between two transactions.

- ``counter``: decision 11's ``UPDATE … SET n = n + :count … RETURNING n`` from two engines at once,
  each number used in the transaction that took it; a block of five; a number taken and rolled back;
  and, on Postgres, the same under a server default of REPEATABLE READ, since decision 5 pins nothing.
- ``bounded_delete``: decision 12's ``DELETE … WHERE key IN (SELECT key … ORDER BY expires LIMIT :n)``,
  its binds, its counts over 12,000 expired rows, the three-column key of decision 25, and two passes
  at once that each stop when a call removes no row, as decision 17's pass does.
- ``upsert``: the ``WHERE`` on the update that keeps the newest, its row counts, the row count of an
  insert that does nothing, and one statement that names a key twice.
- ``first_touch``: eight connections making the tables at once, under the serialization point of
  decision 8 and without it.
- ``deadlock``: Postgres only. Two flushes that write two keys in opposite orders, the same in one
  order, and a flush against a sweep's delete; with what today's classifier says of the error.
- ``bulk_insert``: today's ``bulk_insert`` called with a session that is no storage's, 10,000 rows.

    PROBE_SCRATCH=<a scratch directory outside the repository> \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_statements.py --engine sqlite
    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_statements.py --engine postgres
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import (
    URL,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    select,
    text,
    tuple_,
    update,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from standin import _sqlite_transaction_control

from vfs.storage.backends.database.dialects import bulk_insert, is_retryable, profile_for
from vfs.storage.backends.database.engine import advisory_key


class Bed:
    """One fresh database and a way to make engines on it."""

    def __init__(self, engine: str) -> None:
        self.kind = engine
        self.dialect = "sqlite" if engine == "sqlite" else "postgresql"
        self.schema: str | None = None
        self.directory: FsPath | None = None
        self.engines: list[AsyncEngine] = []
        if engine == "sqlite":
            self.directory = FsPath(os.environ["PROBE_SCRATCH"]) / f"statements-{uuid.uuid4().hex[:8]}"
            self.directory.mkdir(parents=True)
            self.url: Any = URL.create("sqlite+aiosqlite", database=str(self.directory / "probe.db"))
        else:
            self.url = os.environ["VFS_TEST_POSTGRES_URL"]
            self.schema = f"probe_{uuid.uuid4().hex[:12]}"
        self.metadata = MetaData()
        s = self.schema
        self.counters = Table("c_counters", self.metadata, Column("id", String(40), primary_key=True),
                              Column("n", Integer, nullable=False), schema=s)
        self.used = Table("c_used", self.metadata, Column("n", Integer, primary_key=True),
                          Column("who", String(8)), schema=s)
        self.expiring = Table("d_expiring", self.metadata, Column("key", Integer, primary_key=True),
                              Column("expires", DateTime(timezone=True), nullable=True, index=True), schema=s)
        self.triple = Table("d_triple", self.metadata, Column("a", Integer, primary_key=True),
                            Column("b", Integer, primary_key=True), Column("c", Integer, primary_key=True),
                            Column("dead", Integer, nullable=False), schema=s)
        self.stamps = Table("u_stamps", self.metadata, Column("session", String(40), primary_key=True),
                            Column("path", String(200), primary_key=True), Column("vid", String(40)),
                            Column("turn", Integer, nullable=False), schema=s)

    def engine(self, **arguments: Any) -> AsyncEngine:
        made = create_async_engine(self.url, **arguments)
        if self.kind == "sqlite":
            _sqlite_transaction_control(made)
        self.engines.append(made)
        return made

    async def open(self) -> AsyncEngine:
        first = self.engine()
        if self.schema is not None:
            async with first.begin() as conn:
                await conn.execute(text(f"CREATE SCHEMA {self.schema}"))
        else:
            async with first.connect() as conn:
                conn = await conn.execution_options(no_begin=True)
                await conn.exec_driver_sql("PRAGMA journal_mode = WAL")
        async with self.writer(first) as conn:
            await conn.run_sync(self.metadata.create_all)
        return first

    def writer(self, engine: AsyncEngine) -> Any:
        return _Writer(engine)

    def insert(self, table: Table) -> Any:
        return postgresql.insert(table) if self.dialect == "postgresql" else sqlite.insert(table)

    async def close(self) -> None:
        if self.schema is not None:
            async with self.engines[0].begin() as conn:
                await conn.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        for engine in self.engines:
            await engine.dispose()
        if self.directory is not None:
            shutil.rmtree(self.directory, ignore_errors=True)


class _Writer:
    """One writer transaction on a connection of its own: ``BEGIN IMMEDIATE`` on SQLite."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def __aenter__(self) -> Any:
        self._conn = await self._engine.connect()
        await self._conn.execution_options(writer=True)
        self._tx = await self._conn.begin()
        return self._conn

    async def __aexit__(self, kind: Any, exc: Any, tb: Any) -> None:
        try:
            if kind is None:
                await self._tx.commit()
            else:
                await self._tx.rollback()
        finally:
            await self._conn.close()


def binds(statement: Any, dialect: str) -> int:
    compiled = statement.compile(dialect=postgresql.dialect() if dialect == "postgresql" else sqlite.dialect())
    return len(compiled.params)


def describe(exc: BaseException, dialect: str) -> dict[str, Any]:
    origin = getattr(exc, "orig", None)
    return {
        "error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:150]}",
        "sqlstate": getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None),
        "todays_classifier_says_retryable": is_retryable(profile_for(dialect), exc),
    }


# ---------------------------------------------------------------------------
# The counter
# ---------------------------------------------------------------------------


async def counter(bed: Bed) -> dict[str, Any]:
    first, second = bed.engines[0], bed.engine()
    c, used = bed.counters, bed.used
    async with bed.writer(first) as conn:
        await conn.execute(bed.insert(c).values(id="s1", n=0).on_conflict_do_nothing(index_elements=["id"]))
    take = update(c).where(c.c.id == "s1").values(n=c.c.n + 1).returning(c.c.n)
    out: dict[str, Any] = {"binds": binds(take, bed.dialect)}

    async def taker(engine: AsyncEngine, who: str, times: int) -> tuple[list[int], list[dict[str, Any]]]:
        numbers: list[int] = []
        errors: list[dict[str, Any]] = []
        for _ in range(times):
            for _attempt in range(8):
                try:
                    async with bed.writer(engine) as conn:
                        n = (await conn.execute(take)).scalar_one()
                        await conn.execute(used.insert().values(n=n, who=who))
                    numbers.append(n)
                    break
                except DBAPIError as exc:
                    errors.append(describe(exc, bed.dialect))
        return numbers, errors

    (a, ea), (b, eb) = await asyncio.gather(taker(first, "a", 50), taker(second, "b", 50))
    handed = sorted(a + b)
    out["two_engines_50_each"] = {
        "handed_out": len(handed),
        "exactly_1_to_100": handed == list(range(1, 101)),
        "repeats": len(handed) - len(set(handed)),
        "errors": len(ea) + len(eb),
        "error_kinds": sorted({e["error"][:90] for e in ea + eb}),
        "interleaved": sum(1 for x, y in zip(a, a[1:], strict=False) if y != x + 1) > 0,
    }
    async with bed.writer(first) as conn:
        block = update(c).where(c.c.id == "s1").values(n=c.c.n + 5).returning(c.c.n)
        out["block_of_five_after_100_returns"] = (await conn.execute(block)).scalar_one()
    try:
        async with bed.writer(first) as conn:
            taken = (await conn.execute(take)).scalar_one()
            raise RuntimeError("rolled back on purpose")
    except RuntimeError:
        pass
    async with bed.writer(first) as conn:
        again = (await conn.execute(take)).scalar_one()
    out["a_number_taken_and_rolled_back"] = {"taken": taken, "next_taken": again, "returned_to_the_counter": again == taken}
    async with bed.writer(first) as conn:
        missing = update(c).where(c.c.id == "nobody").values(n=c.c.n + 1).returning(c.c.n)
        out["no_row_matches_returns"] = (await conn.execute(missing)).scalar_one_or_none()
    if bed.dialect == "postgresql":
        settings = {"server_settings": {"default_transaction_isolation": "repeatable read"}}
        third, fourth = bed.engine(connect_args=settings), bed.engine(connect_args=settings)
        async with bed.writer(first) as conn:
            await conn.execute(bed.insert(c).values(id="s2", n=0))
            await conn.execute(delete(used))
        take2 = update(c).where(c.c.id == "s2").values(n=c.c.n + 1).returning(c.c.n)

        async def taker2(engine: AsyncEngine, who: str) -> tuple[list[int], list[dict[str, Any]]]:
            numbers: list[int] = []
            errors: list[dict[str, Any]] = []
            for _ in range(50):
                for _attempt in range(20):
                    try:
                        async with bed.writer(engine) as conn:
                            n = (await conn.execute(take2)).scalar_one()
                            await conn.execute(used.insert().values(n=n, who=who))
                            await asyncio.sleep(0)
                        numbers.append(n)
                        break
                    except DBAPIError as exc:
                        errors.append(describe(exc, bed.dialect))
            return numbers, errors

        (a, ea), (b, eb) = await asyncio.gather(taker2(third, "a"), taker2(fourth, "b"))
        handed = sorted(a + b)
        out["under_a_server_default_of_repeatable_read"] = {
            "handed_out": len(handed),
            "exactly_1_to_100": handed == list(range(1, 101)),
            "statements_refused": len(ea) + len(eb),
            "refusals": sorted({(e["sqlstate"], e["error"][:110], e["todays_classifier_says_retryable"]) for e in ea + eb}),
        }
    return out


# ---------------------------------------------------------------------------
# The bounded delete
# ---------------------------------------------------------------------------


def delete_expired(table: Table, now: datetime, limit: int) -> Any:
    inner = select(table.c.key).where(table.c.expires <= now).order_by(table.c.expires).limit(limit)
    return delete(table).where(table.c.key.in_(inner))


async def bounded_delete(bed: Bed) -> dict[str, Any]:
    first, second = bed.engines[0], bed.engine()
    t = bed.expiring
    now = datetime(2026, 11, 23, tzinfo=UTC)
    out: dict[str, Any] = {}

    async def fill(expired: int, live: int, never: int) -> None:
        rows = [{"key": i, "expires": now - timedelta(seconds=expired - i)} for i in range(expired)]
        rows += [{"key": expired + i, "expires": now + timedelta(days=1)} for i in range(live)]
        rows += [{"key": expired + live + i, "expires": None} for i in range(never)]
        async with bed.writer(first) as conn:
            await conn.execute(delete(t))
            for start in range(0, len(rows), 5000):
                await conn.execute(t.insert(), rows[start : start + 5000])

    await fill(12_000, 100, 3)
    statement = delete_expired(t, now, 5000)
    out["binds"] = binds(statement, bed.dialect)
    counts = []
    while True:
        async with bed.writer(first) as conn:
            removed = (await conn.execute(statement)).rowcount
        counts.append(removed)
        if removed == 0:
            break
    async with first.connect() as conn:
        left = (await conn.execute(select(func.count()).select_from(t))).scalar_one()
    out["one_pass_over_12000_expired_100_live_3_with_no_expiry"] = {"removed_by_each_call": counts, "rows_left": left}

    # Two passes at once, each ending when a call of its own removes no row.
    await fill(40_000, 100, 0)

    async def a_pass(engine: AsyncEngine) -> list[int]:
        mine = []
        while True:
            async with bed.writer(engine) as conn:
                removed = (await conn.execute(statement)).rowcount
            mine.append(removed)
            if removed == 0:
                return mine

    one, two = await asyncio.gather(a_pass(first), a_pass(second))
    async with first.connect() as conn:
        left = (await conn.execute(select(func.count()).select_from(t))).scalar_one()
    out["two_passes_at_once_over_40000_expired"] = {
        "first_pass_calls": one,
        "second_pass_calls": two,
        "removed_in_all": sum(one) + sum(two),
        "rows_left": left,
        "a_pass_ended_before_the_other_was_done": len(one) != len(two),
    }

    # The three-column key of decision 25.
    tr = bed.triple
    rows = [{"a": i // 4, "b": i % 4, "c": 7, "dead": 1} for i in range(8)]
    async with bed.writer(first) as conn:
        await conn.execute(tr.insert(), rows)
    inner = select(tr.c.a, tr.c.b, tr.c.c).where(tr.c.dead == 1).limit(5)
    by_row_value = delete(tr).where(tuple_(tr.c.a, tr.c.b, tr.c.c).in_(inner))
    async with bed.writer(first) as conn:
        removed = (await conn.execute(by_row_value)).rowcount
    out["three_column_key_limit_5_of_8"] = {"removed": removed, "binds": binds(by_row_value, bed.dialect)}
    return out


# ---------------------------------------------------------------------------
# The upsert
# ---------------------------------------------------------------------------


async def upsert(bed: Bed) -> dict[str, Any]:
    first = bed.engines[0]
    s = bed.stamps
    out: dict[str, Any] = {}

    def newest(rows: list[dict[str, Any]]) -> Any:
        statement = bed.insert(s).values(rows)
        return statement.on_conflict_do_update(
            index_elements=["session", "path"],
            set_={"vid": statement.excluded.vid, "turn": statement.excluded.turn},
            where=statement.excluded.turn >= s.c.turn,
        )

    def rows(turn: int, vid: str, n: int = 4, start: int = 0) -> list[dict[str, Any]]:
        return [{"session": "s", "path": f"/p{i}", "vid": vid, "turn": turn} for i in range(start, start + n)]

    async def run(statement: Any) -> int:
        async with bed.writer(first) as conn:
            return (await conn.execute(statement)).rowcount

    out["insert_4_new"] = await run(newest(rows(5, "five")))
    out["upsert_4_older"] = await run(newest(rows(3, "three")))
    out["upsert_4_same_turn"] = await run(newest(rows(5, "five-again")))
    out["upsert_4_newer"] = await run(newest(rows(9, "nine")))
    async with first.connect() as conn:
        out["stored_vids"] = sorted({r[0] for r in (await conn.execute(select(s.c.vid))).all()})
    nothing = lambda r: bed.insert(s).values(r).on_conflict_do_nothing(index_elements=["session", "path"])  # noqa: E731
    out["do_nothing_8_new"] = await run(nothing(rows(1, "x", n=8, start=100)))
    out["do_nothing_4_of_which_3_exist"] = await run(nothing(rows(1, "x", n=4, start=105)))
    twice = rows(11, "eleven", n=1) + rows(12, "twelve", n=1)
    try:
        out["one_statement_names_a_key_twice"] = {"rowcount": await run(newest(twice))}
        async with first.connect() as conn:
            kept = (await conn.execute(select(s.c.vid).where(s.c.path == "/p0"))).scalar_one()
        out["one_statement_names_a_key_twice"]["stored"] = kept
    except DBAPIError as exc:
        out["one_statement_names_a_key_twice"] = describe(exc, bed.dialect)
    return out


# ---------------------------------------------------------------------------
# First touch
# ---------------------------------------------------------------------------


async def first_touch(bed: Bed) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for guarded in (True, False):
        metadata = MetaData()
        name = f"ft_meta_{'guarded' if guarded else 'bare'}"
        meta = Table(name, metadata, Column("id", Integer, primary_key=True),
                     Column("format_version", Integer, nullable=False), schema=bed.schema)
        Table(f"{name}_more", metadata, Column("id", Integer, primary_key=True),
              Column("payload", String(40), index=True), schema=bed.schema)
        key = advisory_key(meta.fullname)
        engines = [bed.engine() for _ in range(8)]

        async def touch(engine: AsyncEngine, guarded: bool = guarded, metadata: MetaData = metadata,
                        meta: Table = meta, key: int = key) -> str:
            try:
                if bed.dialect == "sqlite" and not guarded:
                    conn = await engine.connect()
                    try:
                        async with conn.begin():
                            await conn.run_sync(metadata.create_all, checkfirst=True)
                            await conn.execute(bed.insert(meta).values(id=1, format_version=1)
                                               .on_conflict_do_nothing(index_elements=["id"]))
                    finally:
                        await conn.close()
                    return "ok"
                async with bed.writer(engine) as conn:
                    if guarded and bed.dialect == "postgresql":
                        await conn.execute(select(func.pg_advisory_xact_lock(key)))
                    await conn.run_sync(metadata.create_all, checkfirst=True)
                    await conn.execute(bed.insert(meta).values(id=1, format_version=1)
                                       .on_conflict_do_nothing(index_elements=["id"]))
                return "ok"
            except DBAPIError as exc:
                return describe(exc, bed.dialect)["error"][:130]

        results = await asyncio.gather(*(touch(e) for e in engines))
        async with bed.engines[0].connect() as conn:
            try:
                meta_rows = (await conn.execute(select(func.count()).select_from(meta))).scalar_one()
            except DBAPIError as exc:
                meta_rows = describe(exc, bed.dialect)["error"][:80]
        label = "under_the_serialization_point" if guarded else "without_it"
        out[label] = {
            "ok": sum(1 for r in results if r == "ok"),
            "refused": sum(1 for r in results if r != "ok"),
            "refusals": sorted({r for r in results if r != "ok"}),
            "meta_rows": meta_rows,
        }
    out["advisory_key_of_the_mount_and_of_the_store_differ"] = advisory_key("s.vfs_entries") != advisory_key("s.vfs_kernel_meta")
    return out


# ---------------------------------------------------------------------------
# A deadlock between two flushes, and between a flush and a sweep
# ---------------------------------------------------------------------------


async def deadlock(bed: Bed) -> dict[str, Any]:
    first, second = bed.engines[0], bed.engine()
    s = bed.stamps
    out: dict[str, Any] = {}

    def one(path: str, turn: int) -> Any:
        statement = bed.insert(s).values(session="d", path=path, vid="v", turn=turn)
        return statement.on_conflict_do_update(index_elements=["session", "path"], set_={"turn": statement.excluded.turn})

    async with bed.writer(first) as conn:
        await conn.execute(one("/a", 0))
        await conn.execute(one("/b", 0))

    async def flush(engine: AsyncEngine, order: tuple[str, str], gate: asyncio.Event, ready: asyncio.Event) -> Any:
        try:
            async with bed.writer(engine) as conn:
                await conn.execute(one(order[0], 1))
                ready.set()
                await gate.wait()
                await conn.execute(one(order[1], 1))
            return "committed"
        except DBAPIError as exc:
            return describe(exc, bed.dialect)

    for label, orders in (("opposite_orders", (("/a", "/b"), ("/b", "/a"))), ("one_order", (("/a", "/b"), ("/a", "/b")))):
        gate = asyncio.Event()
        r1, r2 = asyncio.Event(), asyncio.Event()
        t1 = asyncio.create_task(flush(first, orders[0], gate, r1))
        t2 = asyncio.create_task(flush(second, orders[1], gate, r2))
        await r1.wait()
        if label == "opposite_orders":
            await r2.wait()
        gate.set()
        out[f"two_flushes_{label}"] = list(await asyncio.wait_for(asyncio.gather(t1, t2), timeout=30))

    # A flush that writes /a then /b, against one bounded delete that meets /b first.
    e = bed.expiring
    now = datetime(2026, 11, 23, tzinfo=UTC)
    async with bed.writer(first) as conn:
        await conn.execute(delete(e))
        await conn.execute(e.insert(), [{"key": 2, "expires": now - timedelta(days=2)}, {"key": 1, "expires": now - timedelta(days=1)}])

    def touch(key: int) -> Any:
        return update(e).where(e.c.key == key).values(expires=now + timedelta(days=30))

    async def toucher(gate: asyncio.Event, ready: asyncio.Event) -> Any:
        try:
            async with bed.writer(first) as conn:
                await conn.execute(touch(1))
                ready.set()
                await gate.wait()
                await conn.execute(touch(2))
            return "committed"
        except DBAPIError as exc:
            return describe(exc, bed.dialect)

    async def sweeper() -> Any:
        try:
            async with bed.writer(second) as conn:
                removed = (await conn.execute(delete_expired(e, now, 5000))).rowcount
            return {"committed_removed": removed}
        except DBAPIError as exc:
            return describe(exc, bed.dialect)

    gate, ready = asyncio.Event(), asyncio.Event()
    t1 = asyncio.create_task(toucher(gate, ready))
    await ready.wait()
    t2 = asyncio.create_task(sweeper())
    await asyncio.sleep(0.5)
    gate.set()
    out["a_flush_that_touches_two_rows_against_a_sweep_chunk"] = list(
        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=30)
    )
    return out


# ---------------------------------------------------------------------------
# Today's bulk insert, called from outside a storage
# ---------------------------------------------------------------------------


async def bulk(bed: Bed) -> dict[str, Any]:
    first = bed.engines[0]
    rows = [{"session": "bulk", "path": f"/b{i}", "vid": "v", "turn": i} for i in range(10_000)]
    try:
        async with AsyncSession(first) as session:
            await session.connection(execution_options={"writer": True})
            await bulk_insert(session, bed.stamps, rows)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"}
    async with first.connect() as conn:
        count = (await conn.execute(select(func.count()).select_from(bed.stamps).where(bed.stamps.c.session == "bulk"))).scalar_one()
    return {"rows_sent": len(rows), "rows_stored": count, "mode": profile_for(bed.dialect).bulk_insert}


async def run(engine: str) -> dict[str, Any]:
    bed = Bed(engine)
    await bed.open()
    out: dict[str, Any] = {"engine": engine}
    try:
        if engine == "postgres":
            async with bed.engines[0].connect() as conn:
                out["server"] = (await conn.execute(text("SHOW server_version"))).scalar_one()
                out["default_isolation"] = (await conn.execute(text("SHOW default_transaction_isolation"))).scalar_one()
        else:
            out["server"] = sqlite3.sqlite_version
        out["counter"] = await counter(bed)
        out["bounded_delete"] = await bounded_delete(bed)
        out["upsert"] = await upsert(bed)
        out["first_touch"] = await first_touch(bed)
        if engine == "postgres":
            out["deadlock"] = await deadlock(bed)
        out["bulk_insert"] = await bulk(bed)
    finally:
        await bed.close()
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--deadline", type=float, default=240.0)
    args = parser.parse_args()
    try:
        payload = await asyncio.wait_for(run(args.engine), timeout=args.deadline)
    except TimeoutError:
        raise SystemExit(f"deadline of {args.deadline:.0f} s passed") from None
    print(json.dumps({"script": "probe_statements.py", **payload}, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(main())
