"""Shared fixtures and hooks for the live suite.

Engines come from a fixture that disposes them. In-memory SQLite makes an
abandoned connection cheap, but the suite also runs against real servers
(the engine legs selected by ``VFS_TEST_<ENGINE>_URL`` below), where every
undisposed engine holds a socket and a server-side session for the length
of the run.

A test whose plain SQLite transaction reads and then writes fails: SQLite
refuses that write at once whenever another connection committed after
the read, so the test passes or fails by the timing of whatever else runs.

A test that outlives its deadline fails alone, and every thread's stack
goes to a file under ``test-hangs/``, which CI uploads: pytest-xdist
drops a worker's stderr, so a stack written there is lost.
"""

from __future__ import annotations

import asyncio
import dataclasses
import faulthandler
import io
import math
import os
import re
import signal
import sysconfig
import threading
import traceback
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Final, NamedTuple

import aiosqlite
import greenlet
import pytest
from sqlalchemy import Engine, create_engine, event

from vfs import base as base_module
from vfs import chain as chain_module
from vfs import fanout as fanout_module
from vfs import listing as listing_module
from vfs.base import AsyncVirtualFileSystem
from vfs.rendering import RenderLimits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.backends.postgres import PostgresStorage
from vfs.storage.backends.sqlite import SQLiteStorage
from vfs.sync import VirtualFileSystem

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from types import FrameType

    from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext

# The shared contracts and pins assert outside a test module: rewritten, a failed comparison prints both sides.
HELPER_PACKAGES: Final = ("tests.lint", "tests.ranking", "tests.support")
pytest.register_assert_rewrite(*HELPER_PACKAGES)

HANG_DIR_VAR: Final = "VFS_TEST_HANG_DIR"
"""Where each worker's file of hung tests goes; ``test-hangs/`` under the root when unset."""
HANG_DIR_DEFAULT: Final = "test-hangs"

UNBOUNDED_ARGUMENTS: Final = frozenset(
    {"grep_wall_seconds", "search_wall_seconds", "glob_wall_seconds", "embed_timeout_seconds", "close_timeout"}
)
"""The time budgets a storage or a router takes, each given ``math.inf`` by default in a test."""
# Read before any fixture wraps a constructor, so the defaults patched are the ones each call reads.
_BUDGETED_INITS: Final = tuple(
    vars(kind)["__init__"]
    for kind in (
        DatabaseStorage,
        SQLiteStorage,
        PostgresStorage,
        InMemoryStorage,
        AsyncVirtualFileSystem,
        VirtualFileSystem,
    )
)
_STAGE_MODULES: Final = (base_module, chain_module, fanout_module, listing_module)
"""The router's modules whose matching stages read ``WALL_TIME_BUDGET`` at each call."""


def pytest_configure(config: pytest.Config) -> None:
    """Set no loop as the main thread's current one before any test asks for it.

    Up to Python 3.13, asking for the current loop when none was ever set
    makes one, and pytest-asyncio asks as it sets up each test; nobody
    closes that loop, so it is collected unclosed in whatever test runs then.
    """
    asyncio.set_event_loop(None)


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A disposable in-memory SQLite engine for DDL and Core round-trips."""
    engine = create_engine("sqlite://")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
async def _dispose_test_local_storages(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Close every ``DatabaseStorage`` a test made, on the test's own loop.

    Each instance owns an async engine whose driver thread reports back to
    the loop it was created on; an instance dropped without ``close()``
    would otherwise finalize at garbage-collection time against a closed
    loop, which under workers surfaces as an unhandled thread exception in
    whatever test runs next. ``close()`` is idempotent, so already-closed
    instances are fine. A storage a module-scoped fixture built is
    constructed before this fixture patches, so it is not tracked and must
    close in its fixture.

    A connection SQLAlchemy throws away is stopped and never awaited, so its
    driver thread can still be working when the test ends and then answer a
    closed loop. Each such stop is awaited here, while the loop is open.
    """
    created: list[DatabaseStorage] = []
    stopped: list[asyncio.Future[Any]] = []
    original = DatabaseStorage.__init__
    stop = aiosqlite.Connection.stop

    @wraps(original)
    def tracking(self: DatabaseStorage, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        created.append(self)

    def awaited_stop(self: aiosqlite.Connection) -> asyncio.Future[Any] | None:
        # Only a running connection's thread is there to answer; a second stop's future would never resolve.
        running = self._running
        future = stop(self)
        if running and future is not None:
            stopped.append(future)
        return future

    monkeypatch.setattr(DatabaseStorage, "__init__", tracking)
    monkeypatch.setattr(aiosqlite.Connection, "stop", awaited_stop)
    yield
    for storage in created:
        await storage.close()
    loop = asyncio.get_running_loop()
    await asyncio.gather(*(future for future in stopped if future.get_loop() is loop), return_exceptions=True)


@pytest.fixture(autouse=True)
def _unbounded_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave every budget a test does not name unbounded: each storage and router stage wall, a render, a close.

    A shipped budget of seconds fires on a machine slow enough, in a test
    that tests no budget, and fails it for the machine's speed. A test of a
    budget names its own, by argument or by patching the module's constant,
    and the run's deadline bounds every other wait.
    """
    for init in _BUDGETED_INITS:
        defaults = init.__kwdefaults__
        for name in UNBOUNDED_ARGUMENTS & defaults.keys():
            monkeypatch.setitem(defaults, name, math.inf)
    for module in _STAGE_MODULES:
        monkeypatch.setattr(module, "WALL_TIME_BUDGET", math.inf)
    render = RenderLimits.__init__
    shipped = render.__defaults__
    assert shipped is not None
    limits = {field.name: default for field, default in zip(dataclasses.fields(RenderLimits), shipped, strict=True)}
    monkeypatch.setattr(render, "__defaults__", tuple({**limits, "seconds": math.inf}.values()))


@pytest.fixture
def thread_gate() -> Iterator[Callable[[], threading.Event]]:
    """A maker of gates a test's threads wait on with no bound of their own, each opened at teardown.

    A test that fails or outlives its deadline before it opens a gate frees
    the thread waiting there as it tears down, so no pool shutdown or exit
    waits on it. Ask for it after any fixture that joins that thread.
    """
    made: list[threading.Event] = []

    def make() -> threading.Event:
        made.append(gate := threading.Event())
        return gate

    yield make
    for gate in made:
        gate.set()


# ---------------------------------------------------------------------------
# A plain SQLite transaction that reads and then writes
# ---------------------------------------------------------------------------

_LEADING_COMMENTS: Final = r"\s*(?:/\*.*?\*/\s*)*"
_READ: Final = re.compile(_LEADING_COMMENTS + r"(?:SELECT|WITH)\b", re.I | re.S)
_WRITE: Final = re.compile(
    _LEADING_COMMENTS + r"(?:INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|ANALYZE)\b", re.I | re.S
)
_WRITES_WITHIN: Final = re.compile(r"\b(?:INSERT|UPDATE|DELETE)\b", re.I)
_PLAIN: Final = "vfs_test_plain_transaction"
"""The pooled connection's record of its open plain transaction: ``begun``, ``read``, or absent."""
_LIBRARIES: Final = tuple({sysconfig.get_paths()[key] for key in ("stdlib", "platstdlib", "purelib", "platlib")})
_PLAIN_WRITES: list[str] = []
"""What the running test's plain transactions wrote after reading, with where; failed at its teardown."""


@pytest.fixture(autouse=True)
def _no_plain_transaction_reads_then_writes() -> Iterator[None]:
    """Fail a test whose plain SQLite transaction read and then wrote, naming each statement and its frames.

    A ``BEGIN`` takes the write lock only at the first write, and SQLite
    refuses that write with ``database is locked``, waiting for nothing, if
    another connection committed after the transaction's first read, such
    as the host's background statistics pass. ``begin_as_writer`` and
    ``writer_engine`` in ``tests/support/database_helpers.py`` begin as a
    verb's writer does, with the lock first.
    """
    _PLAIN_WRITES.clear()
    yield
    found, _PLAIN_WRITES[:] = list(_PLAIN_WRITES), []
    if found:
        pytest.fail("a plain SQLite transaction read and then wrote; begin it as a writer:\n" + "\n".join(found))


@event.listens_for(Engine, "do_execute")
def _watch_execute(cursor: DBAPICursor, statement: str, parameters: Any, context: ExecutionContext) -> None:
    _watch(statement, context)


@event.listens_for(Engine, "do_executemany")
def _watch_executemany(cursor: DBAPICursor, statement: str, parameters: Any, context: ExecutionContext) -> None:
    _watch(statement, context)


@event.listens_for(Engine, "do_execute_no_params")
def _watch_no_params(cursor: DBAPICursor, statement: str, context: ExecutionContext) -> None:
    _watch(statement, context)


# ---------------------------------------------------------------------------
# Selection: the real-engine legs
# ---------------------------------------------------------------------------

ENGINE_URLS: Final = {
    "postgres": ("VFS_TEST_POSTGRES_URL",),
}
"""Each engine marker and the URL variables that make its leg runnable."""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect every engine leg whose URL is unset.

    Deselection rather than a skip: a skipped engine item still pays its
    fixtures and lands in the summary line, and a local run has nothing to
    report about servers it was never pointed at. The fixture-time skip in
    ``server_storage`` stays as the backstop for a leg selected by hand.
    The ``slow`` marks stay plain markers: everything runs by default, and
    ``-m "not slow"`` is the opt-out.
    """
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if _engine_leg_without_url(item):
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def _engine_leg_without_url(item: pytest.Item) -> bool:
    legs = [name for name in ENGINE_URLS if item.get_closest_marker(name)]
    return bool(legs) and not any(os.environ.get(var) for name in legs for var in ENGINE_URLS[name])


# ---------------------------------------------------------------------------
# The hang guard: a deadline that ends the test, and a backstop that ends the worker
# ---------------------------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def pytest_timeout_set_timer(item: pytest.Item, settings: Any) -> bool | None:
    """Arm *item*'s deadline in place of pytest-timeout's own signal timer.

    At the deadline every thread's stack goes to this worker's file under
    the test's name, and the test fails, so the worker runs on. Should the
    test swallow that failure or never return to Python, the backstop at
    half the deadline again writes the stacks from C and ends the worker.
    The ``thread`` method, and a run off the main thread, keep pytest-timeout's.
    """
    if settings.method != "signal" or threading.current_thread() is not threading.main_thread():
        return None
    log = _HangLog.of(item.config)
    entry = log.begin(item.nodeid, settings.timeout)

    def expired(signum: int, frame: FrameType | None) -> None:
        __tracebackhide__ = True
        log.dump()
        pytest.fail(f"Timeout >{settings.timeout}s: every thread's stack is in {log.path}")

    def cancel() -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        faulthandler.cancel_dump_traceback_later()
        log.end(entry)

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, settings.timeout)
    faulthandler.dump_traceback_later(settings.timeout * 1.5, exit=True, file=log.file)
    item.stash[_ARMED] = cancel
    return True


@pytest.hookimpl(tryfirst=True)
def pytest_timeout_cancel_timer(item: pytest.Item) -> bool | None:
    """Keep an armed deadline when pytest-timeout would cancel it; the protocol's end cancels it.

    pytest-timeout cancels as a phase fails, so a failed test whose
    teardown then hung ran with no deadline and held its worker for good.
    Under ``--pdb``, pass ``--timeout=0``.
    """
    return True if _ARMED in item.stash else None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Any:
    """Cancel *item*'s armed deadline once its setup, call and teardown have all ended."""
    try:
        return (yield)
    finally:
        cancel = item.stash.get(_ARMED, None)
        if cancel is not None:
            del item.stash[_ARMED]
            cancel()


def pytest_unconfigure(config: pytest.Config) -> None:
    """Close this process's file of hung tests, and remove it when no test hung."""
    log = config.stash.get(_HANG_LOG, None)
    if log is not None:
        log.close()


class _HangLog:
    """One process's file of hung tests: a header per armed test, taken back when no stack follows it.

    A process ended from outside while a test runs leaves that test's header, with no stack after it.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file: BinaryIO = path.open("ab+", buffering=0)

    @classmethod
    def of(cls, config: pytest.Config) -> _HangLog:
        log = config.stash.get(_HANG_LOG, None)
        if log is None:
            folder = os.environ.get(HANG_DIR_VAR) or config.rootpath / HANG_DIR_DEFAULT
            worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
            log = config.stash[_HANG_LOG] = cls(Path(folder) / f"{worker}-{os.getpid()}.txt")
        return log

    def begin(self, nodeid: str, timeout: float) -> _Header:
        """Write *nodeid*'s header, and say where it starts and ends, so :meth:`end` can take it back."""
        start = self._size()
        self.file.write(f"\n=== {nodeid} (deadline {timeout}s)\n".encode())
        return _Header(start, self._size())

    def dump(self) -> None:
        """Every thread's stack, then the stack of each task on the loop this thread runs, if any.

        An async test's own frames are on no thread's stack while it awaits: its task holds them.
        """
        faulthandler.dump_traceback(self.file, all_threads=True)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        tasks = io.StringIO()
        for task in asyncio.all_tasks(loop):
            task.print_stack(file=tasks)
        self.file.write(f"\nTasks of the running loop:\n{tasks.getvalue()}".encode())

    def end(self, header: _Header) -> None:
        """Take back *header* unless a stack followed it."""
        if self._size() == header.end:
            self.file.truncate(header.start)

    def close(self) -> None:
        empty = self._size() == 0
        self.file.close()
        if empty:
            self.path.unlink()
            if not any(self.path.parent.iterdir()):
                self.path.parent.rmdir()

    def _size(self) -> int:
        return os.fstat(self.file.fileno()).st_size


class _Header(NamedTuple):
    """Where one test's header lies in a file of hung tests."""

    start: int
    end: int


_HANG_LOG: Final = pytest.StashKey[_HangLog]()
_ARMED: Final = pytest.StashKey[Callable[[], None]]()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _watch(statement: str, context: ExecutionContext) -> None:
    """Follow one SQLite connection's plain transaction from its ``BEGIN`` to a write after a read."""
    connection = getattr(context, "root_connection", None)
    if connection is None or connection.dialect.name != "sqlite":
        return
    info = connection.connection.info
    head = statement.lstrip()[:16].upper()
    if head.startswith("BEGIN"):
        info[_PLAIN] = None if head.startswith("BEGIN IMMEDIATE") else "begun"
        return
    state = info.get(_PLAIN)
    if state is None:
        return
    if not _in_transaction(connection.connection.dbapi_connection):
        info[_PLAIN] = None
    elif state == "begun" and _READ.match(statement) and not _WRITES_WITHIN.search(statement):
        info[_PLAIN] = "read"
    elif state == "read" and (_WRITE.match(statement) or (_READ.match(statement) and _WRITES_WITHIN.search(statement))):
        info[_PLAIN] = None
        _PLAIN_WRITES.append(f"  {' '.join(statement.split())[:100]!r}\n{_sent_from()}")


def _in_transaction(dbapi_connection: Any) -> bool:
    """Whether the driver connection holds an open transaction: aiosqlite's adapter, or ``sqlite3`` itself."""
    driver = getattr(dbapi_connection, "_connection", dbapi_connection)
    try:
        return bool(driver.in_transaction)
    except ValueError:
        return False


def _sent_from() -> str:
    """The frames outside the libraries that sent the statement, across the greenlet SQLAlchemy runs it in."""
    stack = traceback.extract_stack()
    parent = greenlet.getcurrent().parent
    if parent is not None and parent.gr_frame is not None:
        stack = traceback.extract_stack(parent.gr_frame) + stack
    frames = [frame for frame in stack if not frame.filename.startswith(_LIBRARIES) and frame.filename != __file__]
    return "".join(f"    {frame.filename}:{frame.lineno} in {frame.name}\n" for frame in frames[-4:])
