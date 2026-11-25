"""The smallest stand-in for the kernel store the spec designs, for the probes in this directory.

Nothing of the spec is built, so each probe measures this stand-in beside today's ``src/vfs``. It holds what
the spec's decisions 4, 5, 9, 10 and 13 to 15 describe and nothing more:

- a second SQLAlchemy engine on the root storage's own database (the same SQLite file, or the same Postgres
  schema), or on a second SQLite file, or the mount's own engine borrowed, according to ``place``;
- ``commit``: one writer transaction under four tries, ``BEGIN IMMEDIATE`` on SQLite with ``busy_timeout``
  5,000 ms, a wait between tries drawn between half the step and the step, the step doubling from 0.05 s;
- ``record_after``: a ``commit`` that returns its failure as text and never raises;
- ``put_behind``: a bounded buffer of 16,384 rows that drops its oldest, where a keyed row replaces the
  waiting row of its key in that row's position;
- one flusher task, started in a context of its own, that takes up to 1,024 rows from the head and writes
  them in one ``commit`` as soon as it is free; a failed flush puts its rows back at the head and waits
  for the next ``put_behind``.

Two tables stand for the records: ``standin_log`` is the fifteen-column row the log cost study wrote, one
row for each call and no key, and ``standin_stamps`` is a keyed row, one for each session and path. It is
not run by itself:

    uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_waits.py --engine sqlite
"""

from __future__ import annotations

import asyncio
import contextvars
import random
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    event,
    insert,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from vfs.storage.backends.database.dialects import is_retryable, profile_for

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable, Sequence

Place = Literal["same", "own-file", "mount-engine"]

BEHIND_CAPACITY: Final = 16_384
FLUSH_ROWS: Final = 1_024
RETRY_ATTEMPTS: Final = 4
RETRY_BASE_DELAY: Final = 0.05
PARAMETER_BUDGET: Final = 32_700
SQLITE_SETTINGS: Final = ("PRAGMA busy_timeout = 5000", "PRAGMA synchronous = FULL")
SQLITE_FILE_SETTINGS: Final = ("PRAGMA page_size = 16384", "PRAGMA journal_mode = WAL")


class StoreUnavailable(Exception):
    """A store transaction whose tries ran out, or whose failure no retry clears."""


# ---------------------------------------------------------------------------
# The tables
# ---------------------------------------------------------------------------


def build_tables(schema: str | None) -> tuple[MetaData, Table, Table, Table]:
    """The meta table, the unkeyed log row and the keyed stamp row, on one ``MetaData``."""
    metadata = MetaData()
    meta = Table(
        "standin_kernel_meta",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("format_version", Integer, nullable=False),
        schema=schema,
    )
    log = Table(
        "standin_log",
        metadata,
        Column("call_id", String(40), primary_key=True),
        Column("run_id", String(26), nullable=True),
        Column("parent_call_id", String(26), nullable=True),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("elapsed_ns", BigInteger, nullable=True),
        Column("actor", String(255), nullable=False),
        Column("verb", String(32), nullable=False),
        Column("paths", Text, nullable=False),
        Column("path_count", Integer, nullable=False),
        Column("rows", Integer, nullable=True),
        Column("statements", Integer, nullable=True),
        Column("bytes", BigInteger, nullable=True),
        Column("outcome", String(64), nullable=True),
        Column("mount", String(255), nullable=False),
        Column("status", String(16), nullable=False),
        schema=schema,
    )
    Index("standin_log_started_at", log.c.started_at)
    Index("standin_log_run_id", log.c.run_id)
    stamps = Table(
        "standin_stamps",
        metadata,
        Column("session", String(64), primary_key=True),
        Column("path", String(1024), primary_key=True),
        Column("vid", String(64), nullable=False),
        Column("turn", Integer, nullable=False),
        schema=schema,
    )
    return metadata, meta, log, stamps


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


@dataclass
class CommitRecord:
    """One store transaction: who asked for it, how long its last try waited to begin, and how it ended."""

    what: str
    started: float
    begin_wait: float
    seconds: float
    attempts: int
    rows: int = 0
    error: str | None = None


@dataclass
class StandinStore:
    """One store: an engine, a buffer, one flusher."""

    engine: AsyncEngine
    dialect: str
    log: Table
    stamps: Table
    meta: Table
    metadata: MetaData
    owns_engine: bool = True
    capacity: int = BEHIND_CAPACITY
    flush_rows: int = FLUSH_ROWS
    commits: list[CommitRecord] = field(default_factory=list)
    buffer: OrderedDict[Hashable, tuple[str, dict[str, Any]]] = field(default_factory=OrderedDict)
    high_water: int = 0
    dropped: int = 0
    flushing: bool = False
    _sequence: int = 0
    _wake: asyncio.Event = field(default_factory=asyncio.Event)
    _flusher: asyncio.Task[None] | None = None
    _closing: bool = False

    # Transactions.

    async def first_touch(self) -> None:
        """The file settings, then one writer transaction that makes the tables and the meta row."""
        if self.dialect == "sqlite":
            async with self.engine.connect() as conn:
                conn = await conn.execution_options(no_begin=True)
                for statement in SQLITE_FILE_SETTINGS:
                    await conn.exec_driver_sql(statement)

        async def make(conn: AsyncConnection) -> None:
            await conn.run_sync(self.metadata.create_all, checkfirst=True)
            statement = _insert_for(self.dialect, self.meta).values(id=1, format_version=1)
            await conn.execute(statement.on_conflict_do_nothing(index_elements=["id"]))

        await self.commit(make, what="first-touch")

    async def commit(self, fn: Callable[[AsyncConnection], Awaitable[Any]], *, what: str, rows: int = 0) -> Any:
        """Run ``fn`` in one writer transaction, under four tries; raise ``StoreUnavailable`` when they run out."""
        step = RETRY_BASE_DELAY
        started = time.perf_counter()
        profile = profile_for(self.dialect)
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            tried = time.perf_counter()
            began = tried
            try:
                async with self.engine.connect() as conn:
                    conn = await conn.execution_options(writer=True)
                    async with conn.begin():
                        began = time.perf_counter()
                        result = await fn(conn)
                self.commits.append(
                    CommitRecord(what, started, began - tried, time.perf_counter() - started, attempt, rows)
                )
                return result
            except (DBAPIError, SQLAlchemyError) as exc:
                error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:140]}"
                retryable = isinstance(exc, DBAPIError) and is_retryable(profile, exc)
                if retryable and attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(random.uniform(step / 2, step))
                    step *= 2
                    continue
                self.commits.append(
                    CommitRecord(what, started, began - tried, time.perf_counter() - started, attempt, rows, error)
                )
                raise StoreUnavailable(error) from exc
        raise AssertionError("unreachable")

    async def record_after(self, fn: Callable[[AsyncConnection], Awaitable[Any]], *, rows: int = 0) -> str | None:
        """A ``commit`` that returns its failure as text."""
        try:
            await self.commit(fn, what="record", rows=rows)
        except StoreUnavailable as exc:
            return str(exc)
        return None

    # Written behind.

    def put_behind(self, kind: str, row: dict[str, Any], key: Hashable | None = None) -> None:
        """Add one row to the buffer and wake the flusher; a keyed row replaces the waiting row of its key."""
        if self._closing:
            self.dropped += 1
            return
        if key is None:
            self._sequence += 1
            key = self._sequence
        else:
            key = (kind, key)
        self.buffer[key] = (kind, row)
        while len(self.buffer) > self.capacity:
            self.buffer.popitem(last=False)
            self.dropped += 1
        self.high_water = max(self.high_water, len(self.buffer))
        if self._flusher is None:
            loop = asyncio.get_running_loop()
            self._flusher = loop.create_task(self._flush_loop(), context=contextvars.Context())
        self._wake.set()

    async def _flush_loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self.buffer:
                if not await self._flush_once():
                    break
            if self._closing:
                return

    async def settle(self, seconds: float = 60.0) -> bool:
        """Wait until nothing is buffered and no flush is in flight; False when ``seconds`` pass first."""
        deadline = time.perf_counter() + seconds
        while self.buffer or self.flushing:
            if time.perf_counter() > deadline:
                return False
            await asyncio.sleep(0.02)
        return True

    async def _flush_once(self) -> bool:
        self.flushing = True
        try:
            return await self._flush_batch()
        finally:
            self.flushing = False

    async def _flush_batch(self) -> bool:
        batch = [self.buffer.popitem(last=False) for _ in range(min(self.flush_rows, len(self.buffer)))]
        logs = [row for _, (kind, row) in batch if kind == "log"]
        stamps = sorted((row for _, (kind, row) in batch if kind == "stamp"), key=lambda r: (r["session"], r["path"]))

        async def write(conn: AsyncConnection) -> None:
            for chunk in _chunks(logs, PARAMETER_BUDGET // len(self.log.c)):
                await conn.execute(insert(self.log).values(chunk))
            for chunk in _chunks(stamps, PARAMETER_BUDGET // len(self.stamps.c)):
                await conn.execute(upsert_stamps(self.dialect, self.stamps, chunk))

        try:
            await self.commit(write, what="flush", rows=len(batch))
        except StoreUnavailable:
            # The rows go back to the head; a row a later put replaced meanwhile is left as the later one.
            for key, value in reversed(batch):
                if key not in self.buffer:
                    self.buffer[key] = value
                    self.buffer.move_to_end(key, last=False)
            while len(self.buffer) > self.capacity:
                self.buffer.popitem(last=False)
                self.dropped += 1
            self.high_water = max(self.high_water, len(self.buffer))
            return False
        return True

    async def close(self) -> int:
        """Flush what waits, end the task, dispose the engine; return the rows a failed last flush dropped."""
        self._closing = True
        if self._flusher is not None:
            self._wake.set()
            await self._flusher
            self._flusher = None
        left = len(self.buffer)
        self.buffer.clear()
        if self.owns_engine:
            await self.engine.dispose()
        return left


def upsert_stamps(dialect: str, stamps: Table, rows: Sequence[dict[str, Any]]) -> Any:
    """The keyed upsert: a row replaces the stored row of its key when its turn is not older."""
    statement = _insert_for(dialect, stamps).values(list(rows))
    return statement.on_conflict_do_update(
        index_elements=["session", "path"],
        set_={"vid": statement.excluded.vid, "turn": statement.excluded.turn},
        where=statement.excluded.turn >= stamps.c.turn,
    )


def open_store(
    dialect: str,
    url: Any,
    *,
    schema: str | None = None,
    engine_arguments: dict[str, Any] | None = None,
    borrowed: AsyncEngine | None = None,
    capacity: int = BEHIND_CAPACITY,
) -> StandinStore:
    """A store on ``url``, or on ``borrowed``, the mount's own engine, when one is given. No I/O."""
    metadata, meta, log, stamps = build_tables(schema)
    if borrowed is not None:
        return StandinStore(borrowed, dialect, log, stamps, meta, metadata, owns_engine=False, capacity=capacity)
    engine = create_async_engine(url, **(engine_arguments or {}))
    if dialect == "sqlite":
        _sqlite_transaction_control(engine)
    return StandinStore(engine, dialect, log, stamps, meta, metadata, capacity=capacity)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sqlite_transaction_control(engine: AsyncEngine) -> None:
    """The driver begins nothing; a writer begins with ``BEGIN IMMEDIATE``; the settings ride every checkout."""

    @event.listens_for(engine.sync_engine, "checkout")
    def _on_checkout(dbapi_connection, _record, _proxy) -> None:  # noqa: ANN001
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        for statement in SQLITE_SETTINGS:
            cursor.execute(statement)
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn) -> None:  # noqa: ANN001
        options = conn.get_execution_options()
        if options.get("no_begin"):
            return
        conn.exec_driver_sql("BEGIN IMMEDIATE" if options.get("writer") else "BEGIN")


def _insert_for(dialect: str, table: Table) -> Any:
    return postgresql.insert(table) if dialect == "postgresql" else sqlite.insert(table)


def _chunks(rows: Sequence[dict[str, Any]], size: int) -> list[Sequence[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), max(1, size))]
