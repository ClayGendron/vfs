"""What the tests of a cancelled caller share: a held driver round trip, the two SQLite hosts, turns of the loop.

A test that cancels a caller never waits on a clock. It holds one chosen
round trip on the driver's worker thread, cancels the call while the
round trip is held, lets it go, and then looks at what was sent.

A statement of a call is an ``execute`` round trip that is not a
rollback. The driver's ``commit`` and ``rollback`` and the rollback to a
savepoint are round trips and not statements of the call. A statement
takes up to four round trips: the driver makes its ``cursor`` as the
statement is sent, then come its ``execute``, a ``fetchall`` and a
``close``. So a call that is held at a ``cursor`` has the statement of
the ``execute`` that follows in flight.
"""

from __future__ import annotations

import asyncio
import gc
import itertools
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import aiosqlite.core
import pytest
from sqlalchemy import event
from sqlalchemy.exc import DisconnectionError

from vfs import DatabaseStorage, InMemoryStorage
from vfs.storage.backends.database.dialects import SQLITE, SQLITE_VEC_PROBE
from vfs.storage.backends.database.engine import STATISTICS_FINGERPRINT

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator, Mapping
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine

IN_MEMORY = "sqlite+aiosqlite://"

HOSTS = ("in memory", "in a file")
"""Where a SQLite storage keeps its database: in its one connection, or in a file behind a pool."""

# More turns than any chain of tasks these tests start needs to settle.
TURNS = 10

STATEMENT = "execute "
UNDOING = "execute ROLLBACK"

STAMP = [f"{STATEMENT}{SQLITE_VEC_PROBE}", *(f"{STATEMENT}{setting}" for setting in SQLITE.session_settings)]
"""What a pool checkout sends before it hands a connection out: the probe for the vector function, then the settings."""
FINGERPRINT = STATEMENT + STATISTICS_FINGERPRINT.format(schema='"main"')
"""What the checkout of a database in a file sends after them: the read of the planner statistics it holds."""

CONNECTING = ("create_function", f"{STATEMENT}PRAGMA read_uncommitted", "enable_load_extension", "load_extension")
"""How the round trips begin that only the making of a connection sends: its functions, its probe, the extension."""


# ---------------------------------------------------------------------------
# A held round trip
# ---------------------------------------------------------------------------


class HeldRoundTrip:
    """Holds the first driver round trip that *chosen* picks, on the worker thread.

    A round trip is named by the driver function and the statement it carries, as
    ``execute SELECT ...`` or ``commit``. ``seen`` lists every round trip in order,
    and ``held_at`` is the place in it of the one that was held.
    """

    def __init__(self) -> None:
        self.chosen: Callable[[str], bool] | None = None
        self.reached = asyncio.Event()
        self.seen: list[str] = []
        self.held_at: int | None = None
        self._let_go = threading.Event()

    def hold(self, chosen: Callable[[str], bool]) -> None:
        self.chosen = chosen

    def let_go(self) -> None:
        self.chosen = None
        self._let_go.set()

    def again(self) -> None:
        """Make ready to hold one more round trip, of a call that has not started."""
        self.reached, self._let_go = asyncio.Event(), threading.Event()
        self.held_at = None
        self.seen.clear()

    def since(self, prefix: str) -> list[str]:
        """The round trips from the last one that starts with *prefix*, or none when there is no such one."""
        starts = [index for index, name in enumerate(self.seen) if name.startswith(prefix)]
        return self.seen[starts[-1] :] if starts else []

    def statements_after_the_cut(self) -> list[str]:
        """Every statement that was sent after the one in flight at the round trip that was held."""
        assert self.held_at is not None, "no round trip was held"
        after = self.seen[in_flight(self.seen, self.held_at) + 1 :]
        return [name for name in after if name.startswith(STATEMENT) and not name.startswith(UNDOING)]

    def sees(self, name: str, function: Callable[..., Any]) -> Callable[..., Any]:
        """Record one round trip, and return *function* wrapped to wait on the worker thread if it is the chosen one."""
        self.seen.append(name)
        if self.chosen is None or not self.chosen(name):
            return function
        loop = asyncio.get_running_loop()
        self.chosen, self.held_at = None, len(self.seen) - 1
        reached, let_go = self.reached, self._let_go

        def held(*args: Any, **kwargs: Any) -> Any:
            loop.call_soon_threadsafe(reached.set)
            let_go.wait()
            return function(*args, **kwargs)

        return held


def held_round_trips(monkeypatch: pytest.MonkeyPatch) -> HeldRoundTrip:
    """Send every round trip of every ``aiosqlite`` connection through one :class:`HeldRoundTrip`, for the test."""
    held = HeldRoundTrip()
    queue_it = aiosqlite.core.Connection._execute

    async def _execute(self: Any, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        statement = next((" ".join(arg.split()) for arg in args if isinstance(arg, str)), "")
        name = f"{getattr(function, '__name__', '')} {statement}".strip()
        return await queue_it(self, held.sees(name, function), *args, **kwargs)

    monkeypatch.setattr(aiosqlite.core.Connection, "_execute", _execute)
    return held


async def cancel_while_held(
    call: Awaitable[Any], round_trip: HeldRoundTrip, message: str | None = None
) -> tuple[Any, ...]:
    """Cancel *call* with *message* while its chosen round trip is held, then let the round trip go.

    Returns the arguments of the ``CancelledError`` the call raised.
    """
    cancelled = await cancel_if_held(call, round_trip, message)
    assert cancelled is not None, "the call ended before it reached the chosen round trip"
    return cancelled


async def cancel_if_held(
    call: Awaitable[Any], round_trip: HeldRoundTrip, message: str | None = None
) -> tuple[Any, ...] | None:
    """As ``cancel_while_held``, but ``None`` when *call* ended before it reached the chosen round trip.

    A call that ended first withdraws the hold, so no later round trip, of the next call or of a
    background pass, is held with nobody to let it go.
    """
    task = asyncio.ensure_future(call)
    reached = asyncio.ensure_future(round_trip.reached.wait())
    await asyncio.wait({task, reached}, return_when=asyncio.FIRST_COMPLETED)
    if not round_trip.reached.is_set():
        reached.cancel()
        await task
        round_trip.let_go()
        return None
    task.cancel(message)
    round_trip.let_go()
    with pytest.raises(asyncio.CancelledError) as raised:
        await task
    return raised.value.args


def reads_entries(round_trip: str) -> bool:
    return round_trip.startswith(f"{STATEMENT}SELECT") and "vfs_entries" in round_trip


def starts_with(prefix: str) -> Callable[[str], bool]:
    return lambda round_trip: round_trip.startswith(prefix)


def number(index: int) -> Callable[[str], bool]:
    """Pick the round trip that is *index* places after the first one asked about."""
    asked = itertools.count()
    return lambda _round_trip: next(asked) == index


def kind(round_trip: str) -> str:
    """The kind of a round trip: its driver function and the first two words of its statement, less their arguments."""
    return " ".join(word.split("(")[0] for word in round_trip.split()[:3])


def kinds(names: list[str]) -> list[str]:
    """Each kind of round trip in *names*, once, in the order they first come."""
    return list(dict.fromkeys(kind(name) for name in names))


def first_of_kind(wanted: str) -> Callable[[str], bool]:
    return lambda round_trip: kind(round_trip) == wanted


def first_statement_of_a_transaction() -> Callable[[str], bool]:
    """Pick the first statement that follows a ``BEGIN``: the first one a call sends in its own transaction."""
    begun = False

    def chosen(round_trip: str) -> bool:
        nonlocal begun
        if round_trip.startswith(f"{STATEMENT}BEGIN"):
            begun = True
            return False
        return begun and round_trip.startswith(STATEMENT)

    return chosen


def in_flight(names: list[str], cut: int) -> int:
    """The place of the statement in flight at round trip *cut* of *names*: the ``execute`` after a ``cursor``."""
    return cut + 1 if names[cut] == "cursor" else cut


def left_of_a_checkout(names: list[str], cut: int) -> list[str]:
    """The statements a pool checkout still sends after the one in flight at round trip *cut*, when it is one of them.

    A checkout stamps the connection's settings in the pool's own listener.
    A refusal raised there would cost the connection, so a checkout that has
    begun sends all its statements. A database in a file may find the
    connection's planner statistics stale and stamp a second one in its place.
    The first checkout of all makes the connection before it stamps it.
    Outside a checkout the answer is none.
    """
    cut = in_flight(names, cut)
    statements = [index for index, name in enumerate(names) if name.startswith(STATEMENT)]
    left: list[str] = []
    place = 0
    while place < len(statements):
        stamp = statements[place : place + len(STAMP)]
        if [names[index] for index in stamp] != STAMP:
            # A stamp that follows the one the cut is in belongs to the same checkout; anything else ends it.
            if left:
                break
            place += 1
            continue
        after = statements[place + len(STAMP) : place + len(STAMP) + 1]
        stamp += [index for index in after if names[index] == FINGERPRINT]
        making = names[cut].startswith(CONNECTING) and all(
            name.startswith(CONNECTING) for name in names[cut : stamp[0]] if name.startswith(STATEMENT)
        )
        if making:
            left += [names[index] for index in statements if cut < index < stamp[0]]
        if left or making or stamp[0] <= cut < stamp[-1]:
            left += [names[index] for index in stamp if index > cut]
        place += len(stamp)
    return left


# ---------------------------------------------------------------------------
# The two hosts
# ---------------------------------------------------------------------------


class Host:
    """One SQLite storage, kept in memory or in a file, and the engine it built.

    *engine_arguments* size the pool of a storage in a file, as ``pool_size=1`` does.
    """

    def __init__(self, name: str, file: Path, engine_arguments: Mapping[str, Any] | None = None) -> None:
        self.name = name
        if name == "in memory":
            self.storage: DatabaseStorage = InMemoryStorage()
        else:
            self.storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{file}.sqlite", engine_arguments=engine_arguments)
        self.engine: AsyncEngine = self.storage.engine

    async def close(self) -> None:
        await self.storage._host.settle_statistics()
        await self.storage.close()


class Connections:
    """The connections the pool of *engine* opened and threw away, from the moment this is made.

    ``replaced`` counts the ones the storage replaced itself because the planner
    statistics of their file had moved, which no cancellation causes.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self.opened: list[object] = []
        self.invalidated: list[object] = []
        self.replaced = 0
        pool = engine.sync_engine
        event.listen(pool, "connect", lambda connection, _record: self.opened.append(connection))
        event.listen(pool, "invalidate", self._thrown_away)

    def _thrown_away(self, connection: object, _record: object, reason: BaseException | None) -> None:
        if isinstance(reason, DisconnectionError):
            self.replaced += 1
        else:
            self.invalidated.append(connection)

    def lost_to_a_cancellation(self) -> tuple[int, int]:
        """How many connections were opened beyond the host's own replacements, and how many were thrown away."""
        return len(self.opened) - self.replaced, len(self.invalidated)


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


async def turns_of_the_loop() -> None:
    """Let every task that can run do so; a task that waits on something held stays where it is."""
    for _ in range(TURNS):
        await asyncio.sleep(0)


async def collect_what_was_dropped() -> None:
    """Collect every task that nothing holds any more.

    The loop turns first: until it has, the callback that woke the test
    still holds the task the test awaited last, and all that task holds.
    """
    await turns_of_the_loop()
    gc.collect()


@contextmanager
def reports_of_the_loop() -> Iterator[list[dict[str, Any]]]:
    """What the running loop is asked to report as unhandled while the block runs.

    A task that ended with an exception nobody read is reported when it is
    collected, so a test collects inside the block and reads the list after it.
    """
    reports: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: reports.append(context))
    try:
        yield reports
    finally:
        loop.set_exception_handler(handler)
