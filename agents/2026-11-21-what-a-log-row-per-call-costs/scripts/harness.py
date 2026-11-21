"""The shared harness of the study: the engines, the log table, the three ways of writing a row, and the corpus.

The log is built outside ``src/``. A ``CallLog`` wraps the public verbs of one ``AsyncVirtualFileSystem`` and
writes each call's row to ``l0_call_log``, a table of its own in the same database as the mount, through an
engine of its own on the same URL. The storage's engine is touched only to put a ``before_cursor_execute``
listener on it, which its docstring allows.

Three modes:

- ``none``: the verb is called and nothing is written.
- ``sync``: every call, read or effect, inserts one complete row, synchronously, after the verb returns.
- ``leaned``: a read appends its row to a bounded buffer that one flusher task writes, 256 rows to one
  insert, on a connection of its own; an effect inserts a ``running`` row before the verb is entered and
  updates it to its outcome after, two synchronous statements.

Statements are counted per call with a context variable the listeners on both engines read, so a count is
the call's own under any concurrency. The flusher's task is created with no counter set, so its statements
are counted as the flusher's and never as a call's.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import platform
import shutil
import sqlite3
import statistics
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path as FsPath
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
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from ulid import ULID

from vfs import (
    AsyncVirtualFileSystem,
    Authority,
    Entry,
    PostgresStorage,
    Principal,
    Result,
    ResultError,
    SQLiteStorage,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from sqlalchemy.sql.expression import Executable

    from vfs import AsyncSession, DatabaseStorage

Engine = Literal["sqlite", "postgres"]
Mode = Literal["none", "sync", "leaned"]

MODES: Final[tuple[Mode, ...]] = ("none", "sync", "leaned")
ENGINES: Final[tuple[Engine, ...]] = ("sqlite", "postgres")
EFFECT_VERBS: Final = frozenset({"write", "edit", "delete", "mkdir", "move", "copy", "mkedge", "run"})

LOG_PATHS: Final = 16
LOG_FLUSH_ROWS: Final = 256
LOG_BUFFER_CAPACITY: Final = 16 * LOG_FLUSH_ROWS
LOG_TABLE: Final = "l0_call_log"

STUDY_DIR: Final = FsPath(__file__).resolve().parent.parent
RESULTS_DIR: Final = STUDY_DIR / "results"
SCRATCH_ENV: Final = "L0_SCRATCH"
POSTGRES_ENV: Final = "VFS_TEST_POSTGRES_URL"

# The corpus every agent-sized call runs against: 100 directories of 20 files of about 4 KB, the median.
CORPUS_DIRS: Final = 100
CORPUS_FILES_PER_DIR: Final = 20
CORPUS_LINE: Final = "the policy text of file {f} in directory {d}, line {n}, with nothing to find\n"
CORPUS_NEEDLE: Final = "every login requires a second factor, MFA, before the session opens\n"
READ_PATH: Final = "/corpus/d07/f003.md"
GREP_ROOT: Final = "/corpus/d07"
GREP_PATTERN: Final = "MFA"
BATCH_SIZE: Final = 10_000
BODY_LINES: Final = 52


# ---------------------------------------------------------------------------
# Statement counting
# ---------------------------------------------------------------------------


@dataclass
class Counter:
    """The statements one call issued, split by the engine they went to."""

    storage: int = 0
    log: int = 0


CURRENT: contextvars.ContextVar[Counter | None] = contextvars.ContextVar("l0_counter", default=None)
"""The counter of the call running in this context; None outside every call."""


@dataclass
class EngineTally:
    """Every statement an engine saw, including those no call owns (first touch, statistics, the flusher)."""

    statements: int = 0
    unowned: int = 0
    max_parameters: int = 0


def count_statements(engine: AsyncEngine, side: Literal["storage", "log"], tally: EngineTally) -> None:
    """Put the counting listener on ``engine``."""

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        tally.statements += 1
        tally.max_parameters = max(tally.max_parameters, _parameter_count(parameters))
        counter = CURRENT.get()
        if counter is None:
            tally.unowned += 1
        elif side == "storage":
            counter.storage += 1
        else:
            counter.log += 1


# ---------------------------------------------------------------------------
# The log table
# ---------------------------------------------------------------------------


def log_table(metadata: MetaData, schema: str | None) -> Table:
    """The row story H0 names, as wide as the real one, with the two indexes retention and resume read."""
    table = Table(
        LOG_TABLE,
        metadata,
        Column("call_id", String(26), primary_key=True),
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
    Index(f"{LOG_TABLE}_started_at", table.c.started_at)
    Index(f"{LOG_TABLE}_run_id", table.c.run_id)
    return table


@dataclass
class Row:
    """One call's row before it is written."""

    call_id: str
    started_at: datetime
    actor: str
    verb: str
    mount: str
    paths: list[str] = field(default_factory=list)
    path_count: int = 0
    run_id: str | None = None
    parent_call_id: str | None = None
    elapsed_ns: int | None = None
    rows: int | None = None
    statements: int | None = None
    bytes: int | None = None
    outcome: str | None = None
    status: str = "running"

    def values(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "run_id": self.run_id,
            "parent_call_id": self.parent_call_id,
            "started_at": self.started_at,
            "elapsed_ns": self.elapsed_ns,
            "actor": self.actor,
            "verb": self.verb,
            "paths": json.dumps(self.paths[:LOG_PATHS]),
            "path_count": self.path_count,
            "rows": self.rows,
            "statements": self.statements,
            "bytes": self.bytes,
            "outcome": self.outcome,
            "mount": self.mount,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# The bench: one storage, one log engine, one router
# ---------------------------------------------------------------------------


@dataclass
class FlushRecord:
    """One flush of the read buffer: its rows, its bind parameters, its wait, and the depth it found."""

    started: float
    rows: int
    parameters: int
    seconds: float
    depth_before: int
    error: str | None = None


@dataclass
class Bench:
    """One fresh database with a mount at ``/``, its log table, and the tallies of both engines."""

    engine_kind: Engine
    mode: Mode
    fs: AsyncVirtualFileSystem
    storage: DatabaseStorage
    log_engine: AsyncEngine
    table: Table
    storage_tally: EngineTally
    log_tally: EngineTally
    cleanup: Callable[[], Awaitable[None]]
    buffer: deque[Row] = field(default_factory=deque)
    flushes: list[FlushRecord] = field(default_factory=list)
    high_water: int = 0
    overflowed: int = 0
    log_failures: list[dict[str, Any]] = field(default_factory=list)
    _wake: asyncio.Event = field(default_factory=asyncio.Event)
    _flusher: asyncio.Task[None] | None = None
    _closing: bool = False

    # The verbs, wrapped. Each returns the verb's Result and the call's statement counter.

    async def call(
        self,
        session: AsyncSession,
        verb: str,
        thunk: Callable[[], Awaitable[Result]],
        *,
        paths: Sequence[str],
        sent_bytes: int = 0,
    ) -> tuple[Result, Counter]:
        counter = Counter()
        token = CURRENT.set(counter)
        try:
            result = await self._logged(session, verb, thunk, paths, sent_bytes)
        finally:
            CURRENT.reset(token)
        return result, counter

    async def _logged(
        self,
        session: AsyncSession,
        verb: str,
        thunk: Callable[[], Awaitable[Result]],
        paths: Sequence[str],
        sent_bytes: int,
    ) -> Result:
        if self.mode == "none":
            return await thunk()
        row = Row(
            call_id=str(ULID()),
            started_at=datetime.now(UTC),
            actor=session.authority.actor.sub,
            verb=verb,
            mount="/",
            paths=list(paths[:LOG_PATHS]),
            path_count=len(paths),
        )
        effect = verb in EFFECT_VERBS
        if self.mode == "leaned" and effect:
            # Claim first: an effect whose claim cannot be written is not entered.
            if not await self._log_write(verb, "claim", insert(self.table).values(row.values())):
                return Result(ops=(verb,), errors=[ResultError(kind="log_unavailable", message="claim failed")])
        counter = CURRENT.get()
        start = time.perf_counter_ns()
        result = await thunk()
        row.elapsed_ns = time.perf_counter_ns() - start
        row.rows = len(result.observations)
        row.statements = counter.storage if counter is not None else None
        row.bytes = sent_bytes or sum(len(o.content or "") for o in result.observations)
        row.outcome = "ok" if result.success else str(result.errors[0].kind)
        row.status = "done"
        if self.mode == "sync":
            await self._log_write(verb, "row", insert(self.table).values(row.values()))
        elif effect:
            done = {k: v for k, v in row.values().items() if k in _COMPLETION_COLUMNS}
            statement = update(self.table).where(self.table.c.call_id == row.call_id).values(done)
            await self._log_write(verb, "complete", statement)
        else:
            self._buffer(row)
        return result

    async def _log_write(self, verb: str, phase: str, statement: Executable) -> bool:
        """One synchronous log statement in a transaction of its own; a failure is recorded, never raised."""
        started = time.perf_counter()
        try:
            async with self.log_engine.begin() as conn:
                await conn.execute(statement)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
            self.log_failures.append(
                {"verb": verb, "phase": phase, "seconds": time.perf_counter() - started, "error": error}
            )
            return False
        return True

    # The read buffer and its one flusher.

    def _buffer(self, row: Row) -> None:
        if len(self.buffer) >= LOG_BUFFER_CAPACITY:
            self.overflowed += 1
        self.buffer.append(row)
        self.high_water = max(self.high_water, len(self.buffer))
        if len(self.buffer) >= LOG_FLUSH_ROWS:
            self._wake.set()

    def start_flusher(self) -> None:
        """Start the flusher in a context with no call counter, so its statements are the flusher's own."""
        if self.mode == "leaned":
            empty = contextvars.Context()
            self._flusher = asyncio.get_running_loop().create_task(self._flush_loop(), context=empty)

    async def _flush_loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while len(self.buffer) >= LOG_FLUSH_ROWS or (self._closing and self.buffer):
                await self._flush_once()
            if self._closing:
                return

    async def _flush_once(self) -> None:
        depth = len(self.buffer)
        rows = [self.buffer.popleft() for _ in range(min(LOG_FLUSH_ROWS, depth))]
        values = [r.values() for r in rows]
        started = time.perf_counter()
        error = None
        try:
            async with self.log_engine.begin() as conn:
                await conn.execute(insert(self.table).values(values))
        except Exception as exc:  # noqa: BLE001
            # A failed flush puts its rows back at the head, as a real flusher that keeps them would.
            error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
            self.buffer.extendleft(reversed(rows))
            await asyncio.sleep(0.05)
        record = FlushRecord(
            started=started,
            rows=len(rows),
            parameters=len(rows) * len(self.table.c),
            seconds=time.perf_counter() - started,
            depth_before=depth,
            error=error,
        )
        self.flushes.append(record)

    async def drain(self) -> None:
        """Flush what the buffer holds and stop the flusher, as ``close()`` would."""
        if self._flusher is None:
            return
        self._closing = True
        self._wake.set()
        await self._flusher
        self._flusher = None

    async def close(self) -> None:
        await self.drain()
        await self.fs.close()
        await self.log_engine.dispose()
        await self.cleanup()


_COMPLETION_COLUMNS: Final = frozenset({"elapsed_ns", "rows", "statements", "bytes", "outcome", "status"})


async def open_bench(
    engine_kind: Engine,
    mode: Mode,
    *,
    label: str,
    storage_arguments: dict[str, Any] | None = None,
    own_log_file: bool = False,
) -> Bench:
    """A fresh database: a new SQLite file, or a new Postgres schema, with the log table beside the mount.

    ``own_log_file`` puts the SQLite log in a second file beside the mount's, so it has a writer of its own.
    """
    if engine_kind == "sqlite":
        directory = scratch_dir() / f"{label}-{uuid.uuid4().hex[:8]}"
        directory.mkdir(parents=True)
        database = directory / "vfs.db"
        storage: DatabaseStorage = SQLiteStorage(path=database, engine_arguments=storage_arguments)
        log_database = directory / "log.db" if own_log_file else database
        log_engine = create_async_engine(f"sqlite+aiosqlite:///{log_database}")
        _stamp_sqlite_log_engine(log_engine)
        schema = None

        async def cleanup() -> None:
            shutil.rmtree(directory, ignore_errors=True)

    else:
        if own_log_file:
            raise ValueError("own_log_file is a SQLite variant; Postgres locks rows, not the database")
        url = postgres_url()
        schema = f"l0_{uuid.uuid4().hex[:12]}"
        admin = create_async_engine(url)
        async with admin.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema}"))
        await admin.dispose()
        storage = PostgresStorage(url=url, schema=schema, engine_arguments=storage_arguments)
        log_engine = create_async_engine(url)

        async def cleanup() -> None:
            dropper = create_async_engine(url)
            async with dropper.begin() as conn:
                await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            await dropper.dispose()

    storage_tally, log_tally = EngineTally(), EngineTally()
    count_statements(storage.engine, "storage", storage_tally)
    count_statements(log_engine, "log", log_tally)
    fs = AsyncVirtualFileSystem(storage=storage)
    metadata = MetaData()
    table = log_table(metadata, schema)
    # First touch of the mount, before the log table, so the database file and its settings are vfs's own.
    first = await fs.stat("/")
    if not first.success:
        raise RuntimeError(f"first touch failed: {first.errors}")
    async with log_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    bench = Bench(
        engine_kind=engine_kind,
        mode=mode,
        fs=fs,
        storage=storage,
        log_engine=log_engine,
        table=table,
        storage_tally=storage_tally,
        log_tally=log_tally,
        cleanup=cleanup,
    )
    bench.start_flusher()
    return bench


def _stamp_sqlite_log_engine(engine: AsyncEngine) -> None:
    """The log engine waits for the write lock as vfs's own connections do: 5 s, FULL sync, WAL."""

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, record) -> None:  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()


# ---------------------------------------------------------------------------
# The corpus and the calls
# ---------------------------------------------------------------------------


def body(seed: str, lines: int = BODY_LINES, needle_every: int = 0) -> str:
    """About 4 KB of text; every ``needle_every``-th line carries the pattern grep looks for."""
    out = []
    for n in range(lines):
        if needle_every and n % needle_every == 0:
            out.append(CORPUS_NEEDLE)
        else:
            out.append(CORPUS_LINE.format(f=seed, d=seed, n=n))
    return "".join(out)


async def seed_corpus(fs: AsyncVirtualFileSystem) -> None:
    """2,000 files of about 4 KB; in each directory, every fourth file carries the pattern three times."""
    entries = [
        Entry(
            path=f"/corpus/d{d:02d}/f{f:03d}.md",
            content=body(f"{d}-{f}", needle_every=17 if f % 4 == 0 else 0),
        )
        for d in range(CORPUS_DIRS)
        for f in range(CORPUS_FILES_PER_DIR)
    ]
    result = await fs.write(entries, parents=True)
    if not result.success:
        raise RuntimeError(f"seeding failed: {result.errors[:3]}")


def agent(session_id: int) -> Authority:
    return Authority.of(Principal(f"agent-{session_id:02d}"))


async def do_read(bench: Bench, session: AsyncSession) -> tuple[Result, Counter]:
    return await bench.call(session, "read", lambda: session.read(READ_PATH), paths=(READ_PATH,))


async def do_grep(bench: Bench, session: AsyncSession) -> tuple[Result, Counter]:
    return await bench.call(session, "grep", lambda: session.grep(GREP_PATTERN, paths=(GREP_ROOT,)), paths=(GREP_ROOT,))


async def do_write(bench: Bench, session: AsyncSession, path: str) -> tuple[Result, Counter]:
    content = body(path)
    return await bench.call(
        session,
        "write",
        lambda: session.write(path=path, content=content, parents=True),
        paths=(path,),
        sent_bytes=len(content),
    )


async def do_batch(bench: Bench, session: AsyncSession, root: str) -> tuple[Result, Counter]:
    entries = [Entry(path=f"{root}/{i // 100:03d}/f{i:05d}.md", content=body(f"{root}-{i}")) for i in range(BATCH_SIZE)]
    paths = [e.path for e in entries]
    sent = sum(len(e.content or "") for e in entries)
    return await bench.call(
        session, "write", lambda: session.write(entries, parents=True), paths=paths, sent_bytes=sent
    )


# ---------------------------------------------------------------------------
# Figures and the record of the run
# ---------------------------------------------------------------------------


def summary_ms(seconds: Sequence[float]) -> dict[str, float]:
    """Median and 95th percentile in milliseconds."""
    ordered = sorted(seconds)
    return {
        "n": len(ordered),
        "median_ms": round(statistics.median(ordered) * 1000, 3),
        "p95_ms": round(percentile(ordered, 0.95) * 1000, 3),
        "max_ms": round(ordered[-1] * 1000, 3),
    }


def percentile(ordered: Sequence[float], q: float) -> float:
    """The nearest-rank percentile of an ordered sequence."""
    rank = max(0, min(len(ordered) - 1, int(round(q * len(ordered) + 0.5)) - 1))
    return ordered[rank]


def environment() -> dict[str, Any]:
    """The commit, the engine versions and the machine every figure was measured on."""
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False, cwd=STUDY_DIR
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "crates"],
            capture_output=True,
            text=True,
            check=False,
            cwd=STUDY_DIR,
        ).stdout.strip()
    )
    cpu = "unknown"
    with contextlib.suppress(OSError):
        for line in FsPath("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    memory_gb = None
    with contextlib.suppress(OSError, ValueError):
        pages = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        memory_gb = round(pages / 2**30, 1)
    return {
        "commit": commit,
        "src_dirty": dirty,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "cpu": cpu,
        "cores": os.cpu_count(),
        "memory_gb": memory_gb,
        "platform": platform.platform(),
    }


async def postgres_version() -> str:
    engine = create_async_engine(postgres_url())
    async with engine.connect() as conn:
        version = (await conn.execute(text("SELECT version()"))).scalar_one()
        vector = (
            await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        ).scalar_one_or_none()
    await engine.dispose()
    return f"{version}; pgvector {vector}"


def postgres_url() -> str:
    url = os.environ.get(POSTGRES_ENV)
    if not url:
        raise SystemExit(f"{POSTGRES_ENV} is unset; start the container as .claude/skills/db_test/SKILL.md says")
    return url


def scratch_dir() -> FsPath:
    """Where the SQLite files live: ``$L0_SCRATCH``, never inside the repository."""
    root = os.environ.get(SCRATCH_ENV)
    if not root:
        raise SystemExit(f"{SCRATCH_ENV} must name a scratch directory outside the repository")
    path = FsPath(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_results(name: str, payload: dict[str, Any]) -> FsPath:
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / name
    out.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return out


def _parameter_count(parameters: object) -> int:
    if isinstance(parameters, dict):
        return len(parameters)
    if isinstance(parameters, (list, tuple)):
        if parameters and isinstance(parameters[0], (list, tuple, dict)):
            return sum(len(p) for p in parameters)
        return len(parameters)
    return 0
