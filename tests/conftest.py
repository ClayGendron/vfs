"""Shared fixtures and hooks for the live suite.

Engines come from a fixture that disposes them. In-memory SQLite makes an
abandoned connection cheap, but the suite also runs against real servers
(the engine legs selected by ``VFS_TEST_<ENGINE>_URL`` below), where every
undisposed engine holds a socket and a server-side session for the length
of the run.

A test that outlives its deadline fails alone, and every thread's stack
goes to a file under ``test-hangs/``, which CI uploads: pytest-xdist
drops a worker's stderr, so a stack written there is lost.
"""

from __future__ import annotations

import asyncio
import faulthandler
import io
import os
import signal
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Final, NamedTuple

import aiosqlite
import pytest
from sqlalchemy import Engine, create_engine

from vfs.storage.backends.database import DatabaseStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from types import FrameType

# The shared contracts and pins assert outside a test module: rewritten, a failed comparison prints both sides.
HELPER_PACKAGES: Final = ("tests.lint", "tests.ranking", "tests.support")
pytest.register_assert_rewrite(*HELPER_PACKAGES)

HANG_DIR_VAR: Final = "VFS_TEST_HANG_DIR"
"""Where each worker's file of hung tests goes; ``test-hangs/`` under the root when unset."""
HANG_DIR_DEFAULT: Final = "test-hangs"


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
