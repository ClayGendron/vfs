"""The planner-statistics step on SQLite: detection in each write, one pass per host, every connection on the file.

A SQLite store with no statistics plans a scoped glob off the tombstone
index, one seek per arm, and the cost grows with the store. These pins
hold the fix: each write detects inside the lock it already holds, a
crossing write returns at once and one host-tracked pass lands the
statistics, pooled connections replace themselves when the statistics
move, in-memory and borrowed connections reload at their next write,
and ``close()`` interrupts a running pass rather than waiting on it.
Every assertion counts statements, events, rows or plan details.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from itertools import pairwise
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import aiosqlite
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import QueuePool

from tests.support.database_helpers import _fresh_url, _url
from tests.support.plan_store import (
    PLAN_ARMS,
    PLAN_EXTENSIONS,
    chunk_entries,
    chunk_page_plans,
    shipped_join_plan,
)
from tests.support.statements import is_statistics_statement
from vfs import sync as sync_module
from vfs.authority import Authority, Principal
from vfs.base import AsyncVirtualFileSystem
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.pattern_matching import composed_pattern
from vfs.results import ErrorKind, Severity
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import SQLITE
from vfs.storage.backends.database.engine import STATISTICS_NAME
from vfs.storage.backends.database.rights import Resolution, RightsCache, resolve_authority, visibility_clauses
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import VirtualFileSystem

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence

LARGE_ROOTS = 400
"""The large store: 400 roots of 25 files, 11,201 entry rows, the size the research measured."""

CROSSING_ROOTS = 115
"""The crossing store: 115 roots of 25 files, 2,875 files, enough for a fresh store's first crossing."""

ENTRIES_ANALYZE = 'ANALYZE "main"."vfs_entries"'
SCHEMA_RELOAD = 'ANALYZE "main".sqlite_schema'
PASS_BEGIN = "BEGIN IMMEDIATE /* vfs_statistics */"
LISTING = 'PRAGMA "main".optimize = 0x10003'
SYSTEM = Authority.system()


class Traced(NamedTuple):
    """One recorded event on an engine: a transaction bracket or a statement, with its connection."""

    kind: str
    text: str
    connection: int


# ---------------------------------------------------------------------------
# Stores and recorders
# ---------------------------------------------------------------------------


def _entries(roots: int, prefix: str = "/d") -> list[Entry]:
    """*roots* directories of 25 files over ``a/`` and ``b/`` in five extensions, the plan store's shape."""
    return [
        Entry(path=Path(f"{prefix}{root:05d}/{side}/f{index:02d}.{PLAN_EXTENSIONS[index % 5]}"), content="x")
        for root in range(roots)
        for index in range(25)
        for side in ("a" if index < 13 else "b",)
    ]


def _text_entries(roots: int) -> list[Entry]:
    """The crossing store with text bodies, so reindex fills the chunk and gram tables."""
    return [
        Entry(path=Path(f"/t{root:05d}/f{index:02d}.md"), content=f"alpha beta gamma {root} delta {index}")
        for root in range(roots)
        for index in range(25)
    ]


@pytest.fixture(scope="module")
def large_store(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """The 11,201-row store, written once per module through the backend, its statistics settled."""
    target = tmp_path_factory.mktemp("large") / "vfs.sqlite"

    async def build() -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{target}")
        assert (await storage.write(entries=_entries(LARGE_ROOTS), parents=True)).success is True
        await storage._host.settle_statistics()
        await storage.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, build()).result()
    return target


@pytest.fixture(scope="module")
def chunk_store(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """200 long text files of about ten chunks each, written once per module, reindexed, statistics settled.

    Ten chunks per entry, the reference ratio, is past the four to five
    at which SQLite's planner puts a filter on the chunk page's join.
    """
    target = tmp_path_factory.mktemp("chunks") / "vfs.sqlite"

    async def build() -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{target}")
        assert (await storage.write(entries=chunk_entries(), parents=True)).success is True
        assert (await storage.reindex()).success is True
        await storage._host.settle_statistics()
        await storage.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, build()).result()
    return target


def _copied(source: pathlib.Path, tmp_path: pathlib.Path) -> str:
    """A URL over a private copy of *source*."""
    target = tmp_path / "copy.sqlite"
    shutil.copy(source, target)
    return f"sqlite+aiosqlite:///{target}"


def _empty_statistics(url: str) -> None:
    """Drop every ``sqlite_stat1`` row of the file behind *url*, so every filled table is due again.

    The connection is closed here, not only committed: one left open
    holds the file's log and its index past the store's own close.
    """
    with closing(sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///"))) as connection, connection:
        connection.execute("DELETE FROM sqlite_stat1")


def _trace(engine: AsyncEngine) -> list[Traced]:
    """Every statement and transaction bracket *engine* issues from here on, in order."""
    traced: list[Traced] = []
    sync = engine.sync_engine

    @event.listens_for(sync, "before_cursor_execute")
    def statement(conn, cursor, statement, parameters, context, executemany) -> None:
        traced.append(Traced("statement", statement, id(conn.connection.dbapi_connection)))

    for bracket in ("begin", "commit", "rollback"):

        def mark(conn, bracket: str = bracket) -> None:
            traced.append(Traced(bracket, "", id(conn.connection.dbapi_connection)))

        event.listen(sync, bracket, mark)

    @event.listens_for(sync.pool, "invalidate")
    def invalidated(dbapi_connection, record, exception) -> None:
        traced.append(Traced("invalidate", "", id(dbapi_connection)))

    return traced


def _statements(traced: Sequence[Traced]) -> list[str]:
    return [item.text for item in traced if item.kind == "statement"]


def _statistics(traced: Sequence[Traced]) -> list[str]:
    return [text for text in _statements(traced) if is_statistics_statement(text)]


def _count(traced: Sequence[Traced], text: str) -> int:
    return sum(1 for statement in _statements(traced) if statement == text)


def _invalidations(engine: AsyncEngine) -> list[Any]:
    """Every pool ``invalidate`` event *engine* fires from here on."""
    events: list[Any] = []

    @event.listens_for(engine.sync_engine.pool, "invalidate")
    def invalidated(dbapi_connection, record, exception) -> None:
        events.append(exception)

    return events


async def _stat_rows(storage: DatabaseStorage, table: str | None = None) -> list[tuple[str, str | None, str]]:
    """The ``sqlite_stat1`` rows the store holds, for *table* or all; none when the table is absent."""
    query = "SELECT tbl, idx, stat FROM sqlite_stat1" + ("" if table is None else f" WHERE tbl = '{table}'")
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_no_begin": True})
        try:
            rows = (await conn.exec_driver_sql(query + " ORDER BY tbl, idx")).all()
        except Exception as exc:
            assert "sqlite_stat1" in str(exc), exc
            return []
    return [(str(row[0]), None if row[1] is None else str(row[1]), str(row[2])) for row in rows]


async def _deleted_at_stat(storage: DatabaseStorage) -> str:
    """The tombstone index's ``sqlite_stat1`` text: the row count, then the rows per distinct value."""
    [stat] = [
        stat for _tbl, idx, stat in await _stat_rows(storage, "vfs_entries") if idx == "ix_vfs_entries_deleted_at"
    ]
    return stat


async def _index_list(storage: DatabaseStorage, table: str) -> Sequence[Any]:
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_no_begin": True})
        return (await conn.exec_driver_sql(f'PRAGMA "main".index_list("{table}")')).all()


async def _own_tables_listed(storage: DatabaseStorage) -> list[str]:
    """The indexed own tables the growth listing names on the connection the store checks out now.

    The three index-less tables are named on every call and skipped by
    the step, so they are left out here too.
    """
    own = {f'ANALYZE "main"."{table.name}"': table.name for table in storage._host.tables.metadata.tables.values()}
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_writer": True})
        listed = [str(row[0]) for row in (await conn.exec_driver_sql(LISTING)).all()]
        indexed = [
            own[statement]
            for statement in listed
            if statement in own and (await conn.exec_driver_sql(f'PRAGMA "main".index_list("{own[statement]}")')).all()
        ]
        await session.rollback()
    return indexed


def _literal(statement: str, parameters: Sequence[Any]) -> str:
    literal = statement
    for value in parameters:
        literal = literal.replace("?", "'" + str(value).replace("'", "''") + "'", 1)
    return literal


async def _plan(storage: DatabaseStorage, statement: str, parameters: Sequence[Any]) -> list[str]:
    """``EXPLAIN QUERY PLAN`` details of *statement* on the connection the store checks out now."""
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_no_begin": True})
        rows = (await conn.exec_driver_sql("EXPLAIN QUERY PLAN " + _literal(statement, parameters))).all()
    return [str(row[-1]) for row in rows]


def _recorded_selects(engine: AsyncEngine) -> list[tuple[str, Any]]:
    """Every entry-table ``SELECT`` *engine* issues from here on, with its parameters."""
    recorded: list[tuple[str, Any]] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().startswith("SELECT") and "vfs_entries" in statement:
            recorded.append((statement, parameters))

    return recorded


def _fan_patterns(roots: int) -> tuple[str, ...]:
    return tuple(composed_pattern(Path(f"/d{index:05d}"), arm) for index in range(roots) for arm in PLAN_ARMS)


def _fail_analyze(engine: AsyncEngine, *, ordinal: int) -> dict[str, Any]:
    """Make the *ordinal*-th table ``ANALYZE`` the engine issues while ``armed`` fail at the driver.

    The statement is rewritten to analyze a table that does not exist,
    so the driver itself raises ``sqlite3.OperationalError`` and the
    failure takes the same wrapped road a busy or broken statement would.
    """
    state: dict[str, Any] = {"armed": True, "seen": 0}

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def failing(conn, cursor, statement, parameters, context, executemany) -> tuple[str, Any]:
        if state["armed"] and statement.startswith("ANALYZE ") and statement != SCHEMA_RELOAD:
            state["seen"] += 1
            if state["seen"] == ordinal:
                return 'ANALYZE "main"."vfs_no_such_table_for_this_pin"', parameters
        return statement, parameters

    return state


def _fail_statement(engine: AsyncEngine, text: str) -> dict[str, Any]:
    """Make the first statement equal to *text* the engine issues while ``armed`` fail at the driver.

    As :func:`_fail_analyze`, the statement is rewritten to read a table
    that does not exist, so the driver itself raises.
    """
    state: dict[str, Any] = {"armed": True, "seen": 0}

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def failing(conn, cursor, statement, parameters, context, executemany) -> tuple[str, Any]:
        if state["armed"] and statement == text:
            state["seen"] += 1
            return 'SELECT * FROM "main"."vfs_no_such_table_for_this_pin"', parameters
        return statement, parameters

    return state


def _pass_outcome(traced: Sequence[Traced]) -> str:
    """How the one pass in *traced* ended: its connection's first commit, rollback or invalidation after its begin.

    A pass stopped through its owning task rolls back and returns its
    connection; a pass whose inner task is cancelled, as the loop's
    shutdown does, has its connection invalidated by SQLAlchemy.
    """
    [pass_begin] = [index for index, item in enumerate(traced) if item.text == PASS_BEGIN]
    connection = traced[pass_begin].connection
    return next(
        item.kind
        for item in traced[pass_begin:]
        if item.kind in ("commit", "rollback", "invalidate") and item.connection == connection
    )


def _first_analyze(engine: AsyncEngine, flag: asyncio.Event | threading.Event) -> None:
    """Set *flag* when the engine hands its first table ``ANALYZE`` to the driver."""

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def seen(conn, cursor, statement, parameters, context, executemany) -> None:
        if statement.startswith("ANALYZE ") and statement != SCHEMA_RELOAD:
            flag.set()


def _statistics_errors(result: Any) -> list[Any]:
    return [error for error in result.errors if "planner-statistics" in error.message]


# ---------------------------------------------------------------------------
# The pins
# ---------------------------------------------------------------------------


class TestPlannerStatistics:
    async def test_a_fresh_store_has_no_statistics(self, tmp_path) -> None:
        """Guards: a statistics step at provisioning, which would plan every verb as a scan until the next tenfold."""
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        traced = _trace(storage._host.engine)
        assert (await storage.first_touch()).success is True
        statistics = _statistics(traced)
        assert await _stat_rows(storage, "vfs_entries") == []
        assert statistics == []
        await storage.close()

    @pytest.mark.slow
    async def test_a_written_store_has_full_statistics(self, tmp_path, large_store) -> None:
        """Guards: an uncapped pass that skips an index, or a cap that samples the tombstone column short."""
        storage = DatabaseStorage(url=_copied(large_store, tmp_path))
        rows = await _stat_rows(storage, "vfs_entries")
        indexes = await _index_list(storage, "vfs_entries")
        assert len(rows) == len(indexes) == 13
        assert await _deleted_at_stat(storage) == "11201 11201"
        await storage.close()

    @pytest.mark.slow
    async def test_the_glob_fan_and_the_kind_glob_seek_the_path_index(self, tmp_path, large_store) -> None:
        """Guards: the planner seeking the tombstone or kind index for every arm, the trap the step exists to close."""
        storage = DatabaseStorage(url=_copied(large_store, tmp_path))
        selects = _recorded_selects(storage._host.engine)
        roots = tuple(f"/d{index:05d}" for index in range(50))
        fan = await storage.glob(patterns=_fan_patterns(50))
        assert fan.success is True and len(fan.observations) > 0
        kind = await storage.glob(patterns=tuple(f"{root}/**" for root in roots), kind="file")
        assert kind.success is True and len(kind.observations) == 50 * 25
        assert len(selects) >= 2
        searches: list[str] = []
        for statement, parameters in selects:
            details = await _plan(storage, statement, parameters)
            searches += [detail for detail in details if detail.startswith("SEARCH vfs_entries")]
            assert not any("SCAN vfs_entries" in detail for detail in details), details
        assert searches and all("ix_vfs_entries_path" in detail for detail in searches), searches
        assert not any("ix_vfs_entries_deleted_at" in detail or "ix_vfs_entries_kind" in detail for detail in searches)
        await storage.close()

    @pytest.mark.slow
    async def test_an_unchanged_write_detects_inside_its_one_lock(self, tmp_path, large_store) -> None:
        """Guards: a listing or an ANALYZE taking the write lock of its own, or a pass started with nothing due."""
        storage = DatabaseStorage(url=_copied(large_store, tmp_path))
        # The host's first commit also reads which listed tables carry an index, once; the counted write follows it.
        assert (await storage.write(entries=[Entry(path=Path("/warm.txt"), content="x")])).success is True
        traced = _trace(storage._host.engine)
        invalidations = _invalidations(storage._host.engine)
        assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        assert _count(traced, "BEGIN IMMEDIATE") == 1
        statistics = _statistics(traced)
        assert statistics == ["SAVEPOINT vfs_statistics", LISTING, "RELEASE vfs_statistics"]
        indices = [index for index, item in enumerate(traced) if is_statistics_statement(item.text)]
        [begin] = [index for index, item in enumerate(traced) if item.kind == "begin"]
        [commit] = [index for index, item in enumerate(traced) if item.kind == "commit"]
        assert all(begin < index < commit for index in indices)
        assert storage._host._analysis is None
        for index in range(100):
            assert (await storage.stat(path=Path(f"/d{index:05d}/a/f00.py"))).success is True
        assert invalidations == []
        await storage.close()

    async def test_a_crossing_write_returns_then_one_pass_analyzes(self, tmp_path) -> None:
        """Guards: an analysis inside the caller's transaction, or a pass that analyzes the index-less tables."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        traced = _trace(storage._host.engine)
        written = await storage.write(entries=_entries(CROSSING_ROOTS), parents=True)
        assert written.success is True
        assert _count(traced, ENTRIES_ANALYZE) == 0
        assert storage._host._analysis is not None
        await storage._host.settle_statistics()
        assert _count(traced, "BEGIN IMMEDIATE") == 1
        assert _count(traced, PASS_BEGIN) == 1
        commit = next(index for index, item in enumerate(traced) if item.kind == "commit")
        [pass_begin] = [index for index, item in enumerate(traced) if item.text == PASS_BEGIN]
        assert commit < pass_begin
        assert _count(traced, ENTRIES_ANALYZE) == 1
        assert not any(
            name in statement
            for statement in _statements(traced)
            if statement.startswith("ANALYZE")
            for name in ("vfs_meta", "vfs_lock", "vfs_gram_epochs")
        )
        await storage.close()

    @pytest.mark.slow
    async def test_two_writers_crossing_together_analyze_once(self, tmp_path) -> None:
        """Guards: a second pass that analyzes again instead of reloading and re-listing under its own lock."""
        url = _url(tmp_path)
        x, y = DatabaseStorage(url=url), DatabaseStorage(url=url)
        traces = [_trace(x._host.engine), _trace(y._host.engine)]
        first = await asyncio.gather(
            x.write(entries=_entries(CROSSING_ROOTS, "/x"), parents=True),
            y.write(entries=_entries(CROSSING_ROOTS, "/y"), parents=True),
        )
        assert all(result.success for result in first)
        await x._host.settle_statistics()
        await y._host.settle_statistics()
        assert sum(_count(traced, ENTRIES_ANALYZE) for traced in traces) == 1
        assert (await x.glob(patterns=("/x00000/**",))).success is True
        assert (await y.glob(patterns=("/y00000/**",))).success is True
        for traced in traces:
            traced.clear()
        second = await asyncio.gather(
            x.write(entries=_entries(1_200, "/p"), parents=True),
            y.write(entries=_entries(1_200, "/q"), parents=True),
        )
        assert all(result.success for result in second)
        await x._host.settle_statistics()
        await y._host.settle_statistics()
        assert sum(_count(traced, ENTRIES_ANALYZE) for traced in traces) == 1
        await x.close()
        await y.close()

    @pytest.mark.slow
    async def test_another_pooled_connection_is_replaced_after_a_second_crossing(self, tmp_path) -> None:
        """Guards: a pooled connection planning from the statistics it loaded first after another host's analysis."""
        url = _url(tmp_path)
        x, y = DatabaseStorage(url=url), DatabaseStorage(url=url)
        assert (await x.write(entries=_entries(CROSSING_ROOTS), parents=True)).success is True
        await x._host.settle_statistics()
        assert (await y.glob(patterns=("/d00000/**",))).success is True
        assert (await x.write(entries=_entries(1_200, "/p"), parents=True)).success is True
        await x._host.settle_statistics()
        invalidations = _invalidations(y._host.engine)
        assert (await y.stat(path=Path("/d00000/a/f00.py"))).success is True
        assert len(invalidations) == 1
        assert await _own_tables_listed(y) == []
        selects = _recorded_selects(y._host.engine)
        assert (await y.glob(patterns=_fan_patterns(50))).success is True
        searches = [
            detail
            for statement, parameters in selects
            for detail in await _plan(y, statement, parameters)
            if detail.startswith("SEARCH")
        ]
        assert searches and all("ix_vfs_entries_path" in detail for detail in searches), searches
        for index in range(100):
            assert (await y.stat(path=Path(f"/d{index % CROSSING_ROOTS:05d}/a/f00.py"))).success is True
        assert len(invalidations) == 1
        await x.close()
        await y.close()

    async def test_a_shared_in_memory_store_is_never_replaced(self, tmp_path) -> None:
        """Guards: keying the exemption on the pool class, which lets a queue pool discard an in-memory database."""
        storage = DatabaseStorage(url="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")
        engine = storage._host.engine
        assert type(engine.sync_engine.pool).__name__ == "AsyncAdaptedQueuePool"
        assert (await storage.first_touch()).success is True
        assert storage._host.in_memory is True
        assert event.contains(engine.sync_engine, "checkout", storage._host._replace_stale) is False
        entries = _entries(CROSSING_ROOTS)
        assert (await storage.write(entries=entries, parents=True)).success is True
        await storage._host.settle_statistics()
        invalidations = _invalidations(engine)
        forced = {"pending": True}

        @event.listens_for(engine.sync_engine, "checkout")
        def force_stale(dbapi_connection, record, proxy) -> None:
            if forced["pending"]:
                forced["pending"] = False
                record.info[STATISTICS_NAME] = "forced"

        assert (await storage.stat(path=Path("/d00000/a/f00.py"))).success is True
        assert forced["pending"] is False and invalidations == []
        read = await storage.read(observations=[Observation(path=entry.path) for entry in entries])
        assert read.success is True and {o.content for o in read.observations} == {"x"}
        assert len(read.observations) == len(entries)
        traced = _trace(engine)
        assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        assert _count(traced, SCHEMA_RELOAD) == 1
        await storage._host.settle_statistics()
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.exec_driver_sql("DELETE FROM sqlite_stat1")
            await session.commit()
        failing = _fail_analyze(engine, ordinal=2)
        assert (await storage.write(entries=[Entry(path=Path("/two.txt"), content="x")])).success is True
        await storage._host.settle_statistics()
        failing["armed"] = False
        assert failing["seen"] == 2
        assert invalidations == []
        read = await storage.read(observations=[Observation(path=entry.path) for entry in entries])
        assert read.success is True and len(read.observations) == len(entries)
        await storage.close()

    async def test_a_borrowed_engine_gains_no_replacement_listener(self, tmp_path) -> None:
        """Guards: a replacement listener on a host application's pool, replacing connections vfs did not make."""
        url = _url(tmp_path)
        engine = create_async_engine(url)
        borrowed = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        assert (await borrowed.first_touch()).success is True
        assert len(list(cast("Any", engine.sync_engine.pool).dispatch.checkout)) == 1
        assert (await borrowed.stat(path=Path("/"))).success is True
        invalidations = _invalidations(engine)
        built = DatabaseStorage(url=url)
        assert (await built.write(entries=_entries(CROSSING_ROOTS), parents=True)).success is True
        await built._host.settle_statistics()
        for _ in range(100):
            assert (await borrowed.stat(path=Path("/"))).success is True
        assert invalidations == []
        traced = _trace(engine)
        selects = _recorded_selects(engine)
        assert (await borrowed.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        assert _count(traced, SCHEMA_RELOAD) == 1
        await borrowed._host.settle_statistics()
        assert (await borrowed.glob(patterns=_fan_patterns(50))).success is True
        searches = [
            detail
            for statement, parameters in selects
            for detail in await _plan(borrowed, statement, parameters)
            if detail.startswith("SEARCH")
        ]
        assert searches and all("ix_vfs_entries_path" in detail for detail in searches), searches
        await built.close()
        await borrowed.close()
        await engine.dispose()

    async def test_a_failed_fingerprint_read_keeps_the_checkout(self, tmp_path, monkeypatch) -> None:
        """Guards: a fingerprint read whose failure fails the caller's verb, or leaves the connection trusted."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=_entries(CROSSING_ROOTS), parents=True)).success is True
        await storage._host.settle_statistics()
        invalidations = _invalidations(storage._host.engine)
        fingerprint = engine_module.STATISTICS_FINGERPRINT
        monkeypatch.setattr(engine_module, "STATISTICS_FINGERPRINT", "SELECT no_such_function_for_this_pin()")
        assert (await storage.stat(path=Path("/d00000/a/f00.py"))).success is True
        assert invalidations == []
        monkeypatch.setattr(engine_module, "STATISTICS_FINGERPRINT", fingerprint)
        assert (await storage.stat(path=Path("/d00000/a/f00.py"))).success is True
        assert len(invalidations) == 1
        await storage.close()

    @pytest.mark.slow
    async def test_the_step_runs_uncapped(self, tmp_path, large_store) -> None:
        """Guards: the listing's cap bit, or a session limit, sampling the low-cardinality columns short."""
        assert SQLITE.statistics_listing is not None
        [mask] = [int(token, 16) for token in SQLITE.statistics_listing.split() if token.startswith("0x")]
        assert mask & 0x10 == 0
        storage = DatabaseStorage(url=_copied(large_store, tmp_path))
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_no_begin": True})
            assert (await conn.exec_driver_sql("PRAGMA analysis_limit")).scalar_one() == 0
        stat = await _deleted_at_stat(storage)
        first, second = stat.split()
        assert first == second and first.isdigit()
        await storage.close()

    async def test_a_borrowed_engine_analyzes_only_vfs_tables(self, tmp_path) -> None:
        """Guards: a pass acting on every statement the listing prints, a host application's tables included."""
        engine = create_async_engine(_url(tmp_path))
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE host_rows (id INTEGER PRIMARY KEY, label TEXT)")
            await conn.exec_driver_sql("CREATE INDEX ix_host_rows_label ON host_rows (label)")
            for index in range(1_000):
                await conn.exec_driver_sql(f"INSERT INTO host_rows (label) VALUES ('row{index}')")
        borrowed = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        assert (await borrowed.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        await borrowed._host.settle_statistics()
        assert await _stat_rows(borrowed, "host_rows") == []
        assert len(await _stat_rows(borrowed, "vfs_entries")) >= 1
        await borrowed.close()
        await engine.dispose()

    async def test_a_failed_pass_keeps_the_write_and_the_next_public_write_reports_it(self, tmp_path) -> None:
        """Guards: a pass failure failing the write, or going unreported, or reported more than once."""
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        before = await _stat_rows(storage)
        failing = _fail_analyze(engine, ordinal=2)
        entries = _entries(CROSSING_ROOTS)
        written = await storage.write(entries=entries, parents=True)
        assert written.success is True and len(written.observations) == len(entries) and written.errors == []
        await storage._host.settle_statistics()
        assert failing["seen"] == 2
        failing["armed"] = False
        invalidations = _invalidations(engine)
        traced = _trace(engine)
        next_write = await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])
        assert len(invalidations) == 1
        assert next_write.success is True
        [error] = next_write.errors
        assert error.kind == ErrorKind.unavailable and error.severity == Severity.warning
        assert error.retryable is False
        assert "background planner-statistics pass" in error.message and "an earlier write" in error.message
        await storage._host.settle_statistics()
        assert _count(traced, ENTRIES_ANALYZE) == 1
        assert await _stat_rows(storage) != before
        after = await storage.write(entries=[Entry(path=Path("/two.txt"), content="x")])
        assert after.success is True and after.errors == []
        await storage.close()

    @pytest.mark.slow
    async def test_a_pass_failure_during_reindex_skips_the_internal_commits(self, tmp_path, monkeypatch) -> None:
        """Guards: a held pass failure swallowed by an internal commit, or riding on reindex's own result."""
        monkeypatch.setattr(backend_module, "REINDEX_HEARTBEAT_SECONDS", 0.02)
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        assert (await storage.write(entries=_text_entries(CROSSING_ROOTS), parents=True)).success is True
        await storage._host.settle_statistics()
        internal: list[Any] = []
        original = storage._execute_maintenance

        async def spied(op: str, fn: Any) -> Any:
            result = await original(op, fn)
            if op == "reindex":
                internal.append(result)
            return result

        monkeypatch.setattr(storage, "_execute_maintenance", spied)
        failing = _fail_analyze(engine, ordinal=1)
        reindexed = await storage.reindex()
        await storage._host.settle_statistics()
        failing["armed"] = False
        assert reindexed.success is True
        assert failing["seen"] >= 1
        assert len(internal) >= 3
        assert [error for result in internal for error in result.errors] == []
        assert _statistics_errors(reindexed) == []
        next_write = await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])
        assert next_write.success is True and len(_statistics_errors(next_write)) == 1
        await storage._host.settle_statistics()
        after = await storage.write(entries=[Entry(path=Path("/two.txt"), content="x")])
        assert after.success is True and _statistics_errors(after) == []
        await storage.close()

    async def test_a_cancelled_caller_still_lands_the_statistics(self, tmp_path) -> None:
        """Guards: a pass that is a child of the caller, so a caller's cancellation or deadline loses the statistics."""
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        traced = _trace(engine)
        first = asyncio.Event()
        _first_analyze(engine, first)
        entries = _entries(CROSSING_ROOTS)

        async def caller() -> None:
            assert (await storage.write(entries=entries, parents=True)).success is True
            await asyncio.Event().wait()

        task = asyncio.create_task(caller())
        await first.wait()
        await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        read = await storage.read(observations=[Observation(path=entry.path) for entry in entries])
        assert read.success is True and len(read.observations) == len(entries)
        await storage._host.settle_statistics()
        rows = len(entries) + CROSSING_ROOTS * 3 + 1
        assert await _deleted_at_stat(storage) == f"{rows} {rows}"
        assert _count(traced, PASS_BEGIN) == 1
        assert _count(traced, ENTRIES_ANALYZE) == 1
        assert _pass_outcome(traced) == "commit"
        await storage.close()

    @pytest.mark.slow
    async def test_close_interrupts_a_running_pass_and_disposes(self, tmp_path, large_store, monkeypatch) -> None:
        """Guards: a close that waits on the pass past its bound, or skips the dispose when the bound fires.

        The bound is a second, not the millisecond the interrupt takes, so a
        saturated machine cannot fake a timeout; the rollback and the empty
        ``sqlite_stat1`` are what prove the pass was interrupted, not awaited.
        """
        url = _copied(large_store, tmp_path)
        _empty_statistics(url)
        storage = DatabaseStorage(url=url)
        engine = storage._host.engine
        disposed: list[int] = []
        dispose = AsyncEngine.dispose

        async def counted(self: AsyncEngine, close: bool = True) -> None:
            disposed.append(id(self))
            await dispose(self, close)

        monkeypatch.setattr(AsyncEngine, "dispose", counted)
        fs = AsyncVirtualFileSystem(storage=storage, close_timeout=1.0)
        traced = _trace(engine)
        first = asyncio.Event()
        _first_analyze(engine, first)
        assert (await fs.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        await first.wait()
        await fs.close()
        assert [path.name for path in tmp_path.iterdir() if path.name.endswith(("-wal", "-shm"))] == []
        pool = engine.sync_engine.pool
        assert isinstance(pool, QueuePool) and pool.checkedout() == 0
        assert disposed == [id(engine)]
        assert _pass_outcome(traced) == "rollback"
        with sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///")) as connection:
            assert connection.execute("SELECT count(*) FROM sqlite_stat1").fetchone()[0] == 0
        assert [task for task in asyncio.all_tasks() if task is not asyncio.current_task()] == []
        reopened = DatabaseStorage(url=url)
        traced = _trace(reopened._host.engine)
        assert (await reopened.write(entries=[Entry(path=Path("/two.txt"), content="x")])).success is True
        await reopened._host.settle_statistics()
        assert _count(traced, ENTRIES_ANALYZE) == 1
        await reopened.close()

    @pytest.mark.slow
    def test_the_sync_facade_close_disposes_with_no_pending_task(self, tmp_path, large_store, monkeypatch) -> None:
        """Guards: a facade close that cancels the pass inside its statement, leaving a stranded cursor, a task or an
        undisposed engine.
        """
        url = _copied(large_store, tmp_path)
        _empty_statistics(url)
        storage = DatabaseStorage(url=url)
        engine = storage._host.engine
        disposed: list[int] = []
        dispose = AsyncEngine.dispose

        async def counted(self: AsyncEngine, close: bool = True) -> None:
            disposed.append(id(self))
            await dispose(self, close)

        monkeypatch.setattr(AsyncEngine, "dispose", counted)
        interrupted: list[int] = []
        interrupt = aiosqlite.Connection.interrupt

        async def counted_interrupt(self: aiosqlite.Connection) -> None:
            interrupted.append(id(self))
            await interrupt(self)

        monkeypatch.setattr(aiosqlite.Connection, "interrupt", counted_interrupt)
        pending: list[int] = []
        all_tasks = asyncio.all_tasks

        def counted_tasks(loop: Any = None) -> set[Any]:
            tasks = all_tasks(loop)
            if loop is not None:
                pending.append(len(tasks))
            return tasks

        monkeypatch.setattr(sync_module.asyncio, "all_tasks", counted_tasks)
        traced = _trace(engine)
        first = threading.Event()
        _first_analyze(engine, first)
        facade = VirtualFileSystem(storage=storage)
        assert facade.write(entries=[Entry(path=Path("/one.txt"), content="x")]).success is True
        assert first.wait(timeout=10.0) is True
        facade.close()
        assert [path.name for path in tmp_path.iterdir() if path.name.endswith(("-wal", "-shm"))] == []
        assert facade._thread.is_alive() is False
        assert pending == [0]
        assert disposed == [id(engine)]
        with sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///")) as connection:
            assert connection.execute("SELECT count(*) FROM sqlite_stat1").fetchone()[0] == 0
        assert len(interrupted) >= 1
        assert _pass_outcome(traced) == "rollback"

    async def test_a_cancelled_pass_leaves_no_interrupt_pending(self, tmp_path, monkeypatch) -> None:
        """Guards: a cancelled pass that re-raises with its last interrupt pending, or leaves its clearing cursor open.

        The inner task is held open after its transaction has committed,
        so an interrupt is certain to find nothing running; SQLite's last
        close would honour it and leave the log and its index behind.
        """
        storage = DatabaseStorage(url=_url(tmp_path))
        committed, held, interrupted = asyncio.Event(), asyncio.Event(), asyncio.Event()
        transaction = engine_module.EngineHost._analysis_transaction

        async def held_open(self: engine_module.EngineHost, state: Any) -> None:
            await transaction(self, state)
            committed.set()
            await held.wait()

        monkeypatch.setattr(engine_module.EngineHost, "_analysis_transaction", held_open)
        driver: list[str] = []
        interrupt, execute = aiosqlite.Connection.interrupt, aiosqlite.Connection.execute

        async def recorded_interrupt(self: aiosqlite.Connection) -> None:
            driver.append("interrupt")
            interrupted.set()
            await interrupt(self)

        async def recorded_execute(self: aiosqlite.Connection, sql: str, parameters: Any = None) -> aiosqlite.Cursor:
            driver.append(sql)
            return await execute(self, sql, parameters)

        monkeypatch.setattr(aiosqlite.Connection, "interrupt", recorded_interrupt)
        monkeypatch.setattr(aiosqlite.Connection, "execute", recorded_execute)
        assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        await committed.wait()
        close = asyncio.create_task(storage.close())
        await interrupted.wait()
        held.set()
        await close
        assert sorted(path.name for path in tmp_path.iterdir() if path.name.startswith("vfs.sqlite")) == ["vfs.sqlite"]
        assert driver.count("interrupt") >= 1
        assert [entry for entry in driver if entry != "interrupt"] == [engine_module.STATISTICS_CLEAR]
        assert driver[-1] == engine_module.STATISTICS_CLEAR

    async def test_a_pass_cancelled_with_its_inner_task_ends_cancelled(self, tmp_path, monkeypatch) -> None:
        """Guards: a clearing statement with no suppression, so a driver already closed ends the pass in its error.

        Both of the pass's tasks are cancelled inside a statement, as a
        loop's shutdown does: SQLAlchemy closes the connection, the driver
        refuses the clearing statement, and the pass still ends cancelled.
        """
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        traced = _trace(engine)
        first = asyncio.Event()
        _first_analyze(engine, first)
        refused: list[BaseException] = []
        execute = aiosqlite.Connection.execute

        async def recorded_execute(self: aiosqlite.Connection, sql: str, parameters: Any = None) -> aiosqlite.Cursor:
            try:
                return await execute(self, sql, parameters)
            except (sqlite3.Error, ValueError) as exc:
                refused.append(exc)
                raise

        monkeypatch.setattr(aiosqlite.Connection, "execute", recorded_execute)
        assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        await first.wait()
        owning = storage._host._analysis
        assert owning is not None
        [inner] = [task for task in asyncio.all_tasks() if task.get_name() == f"{STATISTICS_NAME}-pass"]
        inner.cancel()
        owning.cancel()
        await asyncio.wait({owning})
        assert _pass_outcome(traced) == "invalidate"
        assert len(refused) == 1
        assert owning.cancelled() is True
        await storage.close()

    async def test_close_stops_a_pass_that_never_held_a_connection(self, tmp_path, monkeypatch) -> None:
        """Guards: a clearing statement run for a pass with no driver, which fails the close that is stopping it.

        The pass's transaction is replaced by one that takes no connection
        and ends only once the owning task has begun to stop it.
        """
        storage = DatabaseStorage(url=_url(tmp_path))
        started, stopping, ended = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class Watched(engine_module._AnalysisPass):
            def __setattr__(self, name: str, value: Any) -> None:
                super().__setattr__(name, value)
                if name == "interrupted" and value:
                    stopping.set()

        async def no_connection(self: engine_module.EngineHost, state: Any) -> None:
            started.set()
            await ended.wait()

        monkeypatch.setattr(engine_module, "_AnalysisPass", Watched)
        monkeypatch.setattr(engine_module.EngineHost, "_analysis_transaction", no_connection)
        assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        await started.wait()
        close = asyncio.create_task(storage.close())
        await stopping.wait()
        ended.set()
        await close
        owning = storage._host._analysis
        assert owning is not None and owning.cancelled() is True
        assert sorted(path.name for path in tmp_path.iterdir() if path.name.startswith("vfs.sqlite")) == ["vfs.sqlite"]

    async def test_below_sqlite_3_46_the_step_issues_nothing(self, tmp_path, monkeypatch) -> None:
        """Guards: the step running on a library whose listing depends on the connection's own query history."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        monkeypatch.setattr(storage._host._dialect, "server_version_info", (3, 45, 1))
        traced = _trace(storage._host.engine)
        invalidations = _invalidations(storage._host.engine)
        assert (await storage.write(entries=_entries(CROSSING_ROOTS), parents=True)).success is True
        assert _statistics(traced) == []
        assert storage._host._analysis is None
        assert (await storage.stat(path=Path("/d00000/a/f00.py"))).success is True
        assert invalidations == []
        assert await _stat_rows(storage, "vfs_entries") == []
        await storage.close()

    @pytest.mark.slow
    async def test_in_memory_statistics_live_with_the_store(self) -> None:
        """Guards: the in-memory store's one connection replaced, which drops the database with the statistics."""
        storage = InMemoryStorage()
        invalidations = _invalidations(storage._host.engine)
        assert (await storage.write(entries=_entries(LARGE_ROOTS), parents=True)).success is True
        await storage._host.settle_statistics()
        rows = await _stat_rows(storage, "vfs_entries")
        assert len(rows) == len(await _index_list(storage, "vfs_entries")) == 13
        assert invalidations == []
        await storage.close()
        assert (await storage.first_touch()).success is True
        assert await _stat_rows(storage) == []
        await storage.close()

    @pytest.mark.slow
    async def test_reindex_leaves_every_filled_table_analyzed(self, tmp_path) -> None:
        """Guards: a reindex phase whose commit detects nothing, leaving the tables it filled without statistics."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=_text_entries(CROSSING_ROOTS), parents=True)).success is True
        assert (await storage.reindex()).success is True
        await storage._host.settle_statistics()
        unanalyzed: list[str] = []
        for table in storage._host.tables.metadata.tables.values():
            if not await _index_list(storage, table.name):
                continue
            async with storage._host.session_factory() as session:
                conn = await session.connection(execution_options={"vfs_no_begin": True})
                count = (await conn.exec_driver_sql(f'SELECT count(*) FROM "{table.name}"')).scalar_one()
            if count >= 1 and not await _stat_rows(storage, table.name):
                unanalyzed.append(table.name)
        assert unanalyzed == []
        await storage.close()

    @pytest.mark.slow
    async def test_the_overlay_fetch_keeps_its_seek_under_statistics(self, tmp_path, large_store) -> None:
        """Guards: the planner walking the path index for the rows awaiting the index once statistics exist."""
        storage = DatabaseStorage(url=_copied(large_store, tmp_path))
        assert (await storage.reindex()).success is True
        await storage._host.settle_statistics()
        late = Entry(path=Path("/d00000/a/late.txt"), content="alpha beta gamma")
        assert (await storage.write(entries=[late])).success is True
        await storage._host.settle_statistics()
        selects = _recorded_selects(storage._host.engine)
        found = await storage.grep(pattern="alpha", globs=tuple(f"/d{index:05d}/**" for index in range(20)))
        assert found.success is True and len(found.observations) > 0
        overlay = [(statement, parameters) for statement, parameters in selects if "unlikely(" in statement]
        assert len(overlay) >= 1, [statement for statement, _ in selects]
        for statement, parameters in overlay:
            details = await _plan(storage, statement, parameters)
            entry_details = [detail for detail in details if "vfs_entries" in detail]
            assert entry_details, details
            assert all(detail.startswith("SEARCH vfs_entries") for detail in entry_details), details
            assert all("ix_vfs_entries_encoded_kind" in detail for detail in entry_details), details
        await storage.close()

    @pytest.mark.slow
    async def test_a_partial_callers_overlay_fetch_keeps_its_seek_under_statistics(self, tmp_path, large_store) -> None:
        """Guards: a partial caller's rights riding the overlay statement and moving the planner off the
        (encoded, kind) seek; the mutant is the packed group left out of the scan-tier statement."""
        storage = DatabaseStorage(url=_copied(large_store, tmp_path))
        roots = [f"/d{index:05d}" for index in range(20)]
        reader = Authority.of(Principal("reader"))
        assert (await storage.reindex()).success is True
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        for root in roots:
            granted = await storage.grant(path=Path(root), principal="reader", level="read", authority=SYSTEM)
            assert granted.success is True, granted.errors
        late = Entry(path=Path("/d00000/a/late.txt"), content="alpha beta gamma")
        assert (await storage.write(entries=[late], authority=SYSTEM)).success is True
        await storage._host.settle_statistics()
        host = storage._host
        async with host.session_factory() as session:
            resolved = await resolve_authority(
                session, host.tables, host.profile, host.membership_budget, reader, RightsCache()
            )
        assert isinstance(resolved, Resolution), resolved
        # Twenty roots compile to one clause, so the one packed group is that clause.
        [clause] = visibility_clauses(host.tables.entry, resolved.at("read"), host.profile, host.parameter_budget) or []
        group = str(clause.predicate.compile(dialect=host.engine.sync_engine.dialect))
        selects = _recorded_selects(host.engine)
        found = await storage.grep(pattern="alpha", globs=tuple(f"{root}/**" for root in roots), authority=reader)
        assert found.success is True and len(found.observations) > 0
        overlay = [(statement, parameters) for statement, parameters in selects if "unlikely(" in statement]
        assert len(overlay) >= 1, [statement for statement, _ in selects]
        for statement, parameters in overlay:
            assert statement.count(group) == 1, (group, statement)
            details = await _plan(storage, statement, parameters)
            entry_details = [detail for detail in details if "vfs_entries" in detail]
            assert entry_details, details
            assert all(detail.startswith("SEARCH vfs_entries") for detail in entry_details), details
            assert all("ix_vfs_entries_encoded_kind" in detail for detail in entry_details), details
        await storage.close()

    @pytest.mark.slow
    async def test_the_chunk_store_makes_the_shipped_join_build_a_filter(self, tmp_path, chunk_store) -> None:
        """Guards: a chunk store below the filter's trigger, on which the chunk-page pin could never go red."""
        storage = DatabaseStorage(url=_copied(chunk_store, tmp_path))
        plan = await shipped_join_plan(storage)
        assert sum("BLOOM FILTER" in line for line in plan.splitlines()) == 1, plan
        await storage.close()

    @pytest.mark.slow
    async def test_the_chunk_pages_build_no_filter_per_page(self, tmp_path, chunk_store) -> None:
        """Guards: the build's or the embed step's chunk page joining the entry table on SQLite, a Bloom filter
        over every entry row rebuilt on each page; the mutant is ``probe_entry_filter`` dropped from SQLITE.

        The embed page's refusal term plans as a correlated subquery of its
        own, so the count is of subqueries whose next step searches the entries.
        """
        storage = DatabaseStorage(url=_copied(chunk_store, tmp_path))
        plans = await chunk_page_plans(storage)
        assert set(plans) == {"build", "embed"}
        for page, plan in plans.items():
            lines = plan.splitlines()
            probes = [
                step
                for step, child in pairwise(lines)
                if "CORRELATED SCALAR SUBQUERY" in step and child.startswith("SEARCH vfs_entries")
            ]
            assert not any("BLOOM FILTER" in line for line in lines), (page, plan)
            assert len(probes) == 1, (page, plan)
        build = plans["build"].splitlines()
        assert sum("CORRELATED SCALAR SUBQUERY" in line for line in build) == 1, build
        await storage.close()

    @pytest.mark.slow
    async def test_a_timed_out_close_leaves_no_pass_running(self, tmp_path, large_store) -> None:
        """Guards: a close timing out while the pass waits for the lock, leaving it to commit on a disposed engine."""
        url = _copied(large_store, tmp_path)
        _empty_statistics(url)
        storage = DatabaseStorage(url=url)
        engine = storage._host.engine
        file = url.removeprefix("sqlite+aiosqlite:///")
        rival = sqlite3.connect(file, timeout=0, isolation_level=None)
        held = asyncio.Event()

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def hold(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement == PASS_BEGIN and not held.is_set():
                rival.execute("BEGIN IMMEDIATE")
                held.set()

        fs = AsyncVirtualFileSystem(storage=storage, close_timeout=0.01)
        traced = _trace(engine)
        assert (await fs.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        await held.wait()
        await asyncio.sleep(0.02)
        with pytest.raises(TimeoutError):
            await fs.close()
        rival.execute("COMMIT")
        rival.close()
        named = [task for task in asyncio.all_tasks() if task.get_name().startswith(STATISTICS_NAME)]
        if named:
            await asyncio.wait(named, timeout=10.0)
        assert [task.get_name() for task in asyncio.all_tasks() if task.get_name().startswith(STATISTICS_NAME)] == []
        [pass_begin] = [index for index, item in enumerate(traced) if item.text == PASS_BEGIN]
        connection = traced[pass_begin].connection
        assert [item for item in traced[pass_begin:] if item.kind == "commit" and item.connection == connection] == []
        with sqlite3.connect(file) as connection:
            assert connection.execute("SELECT count(*) FROM sqlite_stat1").fetchone()[0] == 0

    @pytest.mark.slow
    async def test_a_held_advisory_rides_on_a_topology_verb_and_on_posture(self, tmp_path) -> None:
        """Guards: an advisory drained by the write runner alone, unheard through delete or posture."""
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        first = _fail_analyze(engine, ordinal=2)
        assert (await storage.write(entries=_entries(CROSSING_ROOTS), parents=True)).success is True
        await storage._host.settle_statistics()
        assert first["seen"] == 2
        first["armed"] = False
        deleted = await storage.delete(path=Path("/d00000/a/f00.py"))
        assert deleted.success is True
        [error] = deleted.errors
        assert "background planner-statistics pass" in error.message
        after_delete = await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])
        assert after_delete.success is True and _statistics_errors(after_delete) == []
        await storage._host.settle_statistics()
        second = _fail_analyze(engine, ordinal=1)
        assert (await storage.write(entries=_entries(1_200, "/p"), parents=True)).success is True
        await storage._host.settle_statistics()
        assert second["seen"] >= 1
        second["armed"] = False
        postured = await storage.posture(path=Path("/p00000"), posture="read_write", authority=SYSTEM)
        assert postured.success is True and len(_statistics_errors(postured)) == 1
        after_posture = await storage.write(entries=[Entry(path=Path("/two.txt"), content="x")])
        assert after_posture.success is True and _statistics_errors(after_posture) == []
        await storage._host.settle_statistics()
        await storage.close()

    async def test_a_failed_detection_keeps_the_write_and_reports_once(self, tmp_path) -> None:
        """Guards: a listing failure failing the write, leaving the savepoint open, or going unreported."""
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        traced = _trace(engine)
        failing = _fail_statement(engine, LISTING)
        written = await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])
        assert written.success is True and len(written.observations) == 1
        [error] = written.errors
        assert error.kind == ErrorKind.unavailable and error.severity == Severity.warning and error.retryable is False
        assert "planner-statistics detection inside a write" in error.message
        assert "vfs_no_such_table_for_this_pin" in error.message
        assert failing["seen"] == 1
        assert _count(traced, f"ROLLBACK TO {STATISTICS_NAME}") == 1
        assert _count(traced, f"RELEASE {STATISTICS_NAME}") == 1
        assert _count(traced, PASS_BEGIN) == 0
        read = await storage.read(observations=[Observation(path=Path("/one.txt"))])
        assert read.success is True and read.observations[0].content == "x"
        failing["armed"] = False
        again = await storage.write(entries=[Entry(path=Path("/two.txt"), content="x")])
        assert again.success is True and again.errors == []
        await storage._host.settle_statistics()
        assert _count(traced, LISTING) == 3  # the failed detection, the next write's, and its pass's own
        assert await _stat_rows(storage, "vfs_entries") != []
        await storage.close()

    async def test_a_failed_fingerprint_read_in_the_pass_names_the_statement_that_failed(self, tmp_path) -> None:
        """Guards: a pass failing at its fingerprint read and the advisory naming a table's ANALYZE it never ran."""
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine
        failing = _fail_statement(engine, storage._host._fingerprint_statement())
        assert (await storage.write(entries=_entries(CROSSING_ROOTS), parents=True)).success is True
        await storage._host.settle_statistics()
        assert failing["seen"] == 1
        failing["armed"] = False
        next_write = await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])
        assert next_write.success is True
        [error] = _statistics_errors(next_write)
        assert "background planner-statistics pass" in error.message
        assert "vfs_no_such_table_for_this_pin" in error.message
        assert "ANALYZE" not in error.message
        await storage._host.settle_statistics()
        await storage.close()
