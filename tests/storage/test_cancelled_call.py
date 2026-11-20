"""A call that its caller cancels leaves its storage whole.

An in-memory SQLite database lives in its one connection. A call that
is cancelled while it uses that connection must not cost the storage
its rows, and the next call must work. On a database in a file the
connection must not be thrown away with a cursor open, which locks the
next writer out.

No test here reads a clock. One chosen driver round trip is held on the
driver's worker thread until the test lets it go, and the call is
cancelled while it is held. The unit tests of the task, the mark and
the refused commit are in ``tests/storage/database/test_attempts.py``.
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from typing import TYPE_CHECKING, Any

import aiosqlite.core
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.support.cancelled_callers import collect_what_was_dropped, reports_of_the_loop, turns_of_the_loop
from vfs import AsyncVirtualFileSystem, Authority, DatabaseStorage, InMemoryStorage
from vfs.storage.backends.database.drivers import engine_arguments

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine

IN_MEMORY = "sqlite+aiosqlite://"


class HeldRoundTrip:
    """Holds the first driver round trip that *chosen* picks, on the worker thread.

    A round trip is named by the driver function and the statement it carries, as
    ``execute SELECT ...`` or ``commit``. ``seen`` lists every round trip in order.
    """

    def __init__(self) -> None:
        self.chosen: Callable[[str], bool] | None = None
        self.reached = asyncio.Event()
        self.seen: list[str] = []
        self._let_go = threading.Event()

    def hold(self, chosen: Callable[[str], bool]) -> None:
        self.chosen = chosen

    def let_go(self) -> None:
        self.chosen = None
        self._let_go.set()

    def again(self) -> None:
        """Make ready to hold one more round trip, of a call that has not started."""
        self.reached, self._let_go = asyncio.Event(), threading.Event()
        self.seen.clear()

    def since(self, prefix: str) -> list[str]:
        """The round trips from the last one that starts with *prefix*, or none when there is no such one."""
        starts = [index for index, name in enumerate(self.seen) if name.startswith(prefix)]
        return self.seen[starts[-1] :] if starts else []

    def wrap(self, function: Callable[..., Any]) -> Callable[..., Any]:
        loop = asyncio.get_running_loop()
        self.chosen = None

        def held(*args: Any, **kwargs: Any) -> Any:
            loop.call_soon_threadsafe(self.reached.set)
            self._let_go.wait()
            return function(*args, **kwargs)

        return held


@pytest.fixture
def round_trip(monkeypatch: pytest.MonkeyPatch) -> Iterator[HeldRoundTrip]:
    held = HeldRoundTrip()
    queue_it = aiosqlite.core.Connection._execute

    async def _execute(self: Any, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        statement = next((" ".join(arg.split()) for arg in args if isinstance(arg, str)), "")
        name = f"{getattr(function, '__name__', '')} {statement}".strip()
        held.seen.append(name)
        if held.chosen is not None and held.chosen(name):
            function = held.wrap(function)
        return await queue_it(self, function, *args, **kwargs)

    monkeypatch.setattr(aiosqlite.core.Connection, "_execute", _execute)
    yield held
    held.let_go()


@pytest.fixture
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> DatabaseStorage:
    """A storage on SQLite: in memory, or where the test's parameter says it is kept."""
    return sqlite_storage(getattr(request, "param", "in memory"), tmp_path / "one")


@pytest.fixture
async def fs(storage: DatabaseStorage, round_trip: HeldRoundTrip) -> AsyncIterator[AsyncVirtualFileSystem]:
    """A kernel that holds ``/a.txt``, closed whatever the test did so no driver thread is left running.

    The statistics pass of that write is over, so the round trip a test holds is one of its own call.
    """
    kernel = await kernel_holding_a_file(storage)
    round_trip.seen.clear()
    yield kernel
    round_trip.let_go()
    await kernel.close()


async def cancel_while_held(
    call: Awaitable[Any], round_trip: HeldRoundTrip, message: str | None = None
) -> tuple[Any, ...]:
    """Cancel *call* with *message* while its chosen round trip is held, then let the round trip go.

    Returns the arguments of the ``CancelledError`` the call raised.
    """
    task = asyncio.ensure_future(call)
    reached = asyncio.ensure_future(round_trip.reached.wait())
    await asyncio.wait({task, reached}, return_when=asyncio.FIRST_COMPLETED)
    assert round_trip.reached.is_set(), "the call ended before it reached the chosen round trip"
    task.cancel(message)
    round_trip.let_go()
    with pytest.raises(asyncio.CancelledError) as raised:
        await task
    return raised.value.args


def reads_entries(round_trip: str) -> bool:
    return round_trip.startswith("execute SELECT") and "vfs_entries" in round_trip


def starts_with(prefix: str) -> Callable[[str], bool]:
    return lambda round_trip: round_trip.startswith(prefix)


def number(index: int) -> Callable[[str], bool]:
    """Pick the round trip that is *index* places after the first one asked about."""
    asked = itertools.count()
    return lambda _round_trip: next(asked) == index


SYSTEM = Authority.system()

IN_A_FILE = pytest.mark.parametrize("storage", ["in a file"], indirect=True)
IN_MEMORY_AND_IN_A_FILE = pytest.mark.parametrize("storage", ["in memory", "in a file"], indirect=True)

# The first call is some 600 round trips, so its sweep is cut into this many tests that run side by side.
FIRST_CALL_PARTS = 8


def sqlite_storage(kept: str, file: Path) -> DatabaseStorage:
    """A storage on SQLite, ``in memory`` or ``in a file`` at *file*."""
    return InMemoryStorage() if kept == "in memory" else DatabaseStorage(url=f"sqlite+aiosqlite:///{file}.sqlite")


async def kernel_holding_a_file(storage: DatabaseStorage) -> AsyncVirtualFileSystem:
    """A kernel that holds ``/a.txt``, with the statistics pass of that write over, so a call runs alone."""
    kernel = AsyncVirtualFileSystem(storage=storage, default_authority=Authority.system())
    assert (await kernel.write(path="/a.txt", content="old")).success
    await storage._host.settle_statistics()
    return kernel


class Connections:
    """The connections the pool of *engine* opened and threw away, from the moment this is made."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.opened: list[object] = []
        self.invalidated: list[object] = []
        pool = engine.sync_engine
        event.listen(pool, "connect", lambda connection, _record: self.opened.append(connection))
        event.listen(pool, "invalidate", lambda connection, _record, _exception: self.invalidated.append(connection))


CALLS: dict[str, Callable[[AsyncVirtualFileSystem], Awaitable[Any]]] = {
    "stat": lambda kernel: kernel.stat("/"),
    "read": lambda kernel: kernel.read("/a.txt"),
    "write": lambda kernel: kernel.write(path="/a.txt", content="new"),
}


async def round_trips_of(call: str, storage: DatabaseStorage, round_trip: HeldRoundTrip) -> list[str]:
    """The driver round trips of one *call* that nothing cancels, in order."""
    kernel = await kernel_holding_a_file(storage)
    round_trip.again()
    await CALLS[call](kernel)
    names = list(round_trip.seen)
    await kernel.close()
    return names


async def content_and_version(kernel: AsyncVirtualFileSystem) -> tuple[str | None, int | None]:
    read = await kernel.read("/a.txt")
    assert read.success, read.errors
    return read.one().content, (await kernel.stat("/a.txt")).one().version


async def another_file_can_be_written(kernel: AsyncVirtualFileSystem) -> None:
    assert (await kernel.write(path="/b.txt", content="more")).success
    assert (await kernel.read("/b.txt")).one().content == "more"
    assert sorted(str(row.path) for row in (await kernel.ls("/")).observations) == ["/a.txt", "/b.txt"]


class TestACancelledRead:
    async def test_a_stat_cancelled_inside_a_statement_leaves_the_file_readable(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(reads_entries)
        await cancel_while_held(fs.stat("/"), round_trip)
        read = await fs.read("/a.txt")
        assert read.success, read.errors
        assert read.one().content == "old"

    async def test_after_a_cancelled_stat_a_write_lands_beside_the_earlier_file(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(reads_entries)
        await cancel_while_held(fs.stat("/"), round_trip)
        assert (await fs.write(path="/b.txt", content="new")).success
        listed = await fs.ls("/")
        assert sorted(str(row.path) for row in listed.observations) == ["/a.txt", "/b.txt"]

    async def test_a_cancelled_call_opens_no_second_connection(
        self, fs: AsyncVirtualFileSystem, storage: DatabaseStorage, round_trip: HeldRoundTrip
    ) -> None:
        opened: list[object] = []
        event.listen(storage._host.engine.sync_engine, "connect", lambda connection, _record: opened.append(connection))
        round_trip.hold(reads_entries)
        await cancel_while_held(fs.stat("/"), round_trip)
        await fs.stat("/")
        assert opened == []


class TestACancelledWrite:
    @pytest.mark.parametrize(
        "cut_at",
        ["execute UPDATE vfs_entries", "execute INSERT INTO vfs_content", "execute RELEASE vfs_statistics"],
        ids=["at its first change", "after a savepoint is released", "at the last statement before the commit"],
    )
    async def test_a_write_cancelled_before_its_commit_changes_nothing(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip, cut_at: str
    ) -> None:
        round_trip.hold(starts_with(cut_at))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert "commit" not in round_trip.since("execute UPDATE vfs_entries")
        assert (await fs.read("/a.txt")).one().content == "old"
        assert (await fs.stat("/a.txt")).one().version == 1

    async def test_a_cancelled_write_stops_at_the_next_savepoint_it_releases(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(starts_with("execute UPDATE vfs_entries"))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        sent = round_trip.since("execute UPDATE vfs_entries")
        # The write's next statements are the version row and the content. None of them is sent.
        assert [name for name in sent if name.startswith(("execute INSERT", "execute DELETE"))] == []

    @pytest.mark.parametrize("cut_at", ["commit", "rollback"], ids=["at its commit", "after its commit"])
    async def test_a_write_cancelled_at_its_commit_or_after_has_landed_whole(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip, cut_at: str
    ) -> None:
        round_trip.hold(lambda name: name == cut_at and bool(round_trip.since("execute INSERT INTO vfs_content")))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert (await fs.read("/a.txt")).one().content == "new"
        assert (await fs.stat("/a.txt")).one().version == 2

    async def test_a_write_cancelled_while_it_waits_its_turn_sends_nothing(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(reads_entries)
        ahead = asyncio.ensure_future(fs.stat("/a.txt"))
        await round_trip.reached.wait()
        behind = asyncio.ensure_future(fs.write(path="/a.txt", content="new"))
        await turns_of_the_loop()
        behind.cancel()
        round_trip.let_go()
        with pytest.raises(asyncio.CancelledError):
            await behind
        assert (await ahead).one().version == 1
        # A write opens with a bare BEGIN IMMEDIATE. The statistics pass of the first write tags its own.
        assert "execute BEGIN IMMEDIATE" not in round_trip.seen
        assert not round_trip.since("execute UPDATE vfs_entries")
        assert (await fs.read("/a.txt")).one().content == "old"


@pytest.mark.slow
class TestACallCancelledAtEveryRoundTrip:
    """Each call is traced once, and then cancelled at each round trip that was traced."""

    @pytest.mark.parametrize("call", ["stat", "read", "write"])
    @pytest.mark.parametrize("kept", ["in memory", "in a file"])
    async def test_a_sqlite_storage_keeps_its_rows_and_its_connections(
        self, round_trip: HeldRoundTrip, tmp_path: Path, kept: str, call: str
    ) -> None:
        names = await round_trips_of(call, sqlite_storage(kept, tmp_path / "traced"), round_trip)
        assert names, "the call was traced as no round trip at all"
        commit = names.index("commit") if call == "write" else len(names)
        assert names.count("commit") == (1 if call == "write" else 0)
        for cut in range(len(names)):
            storage = sqlite_storage(kept, tmp_path / f"cut{cut}")
            kernel = await kernel_holding_a_file(storage)
            try:
                connections = Connections(storage._host.engine)
                round_trip.again()
                round_trip.hold(number(cut))
                await cancel_while_held(CALLS[call](kernel), round_trip)
                where = f"{call} cancelled at round trip {cut}, {names[cut]!r}"
                assert (connections.opened, connections.invalidated) == ([], []), where
                # The same two answers in memory and in a file: nothing before the commit, all of it after.
                assert await content_and_version(kernel) == (("old", 1) if cut < commit else ("new", 2)), where
                await another_file_can_be_written(kernel)
            finally:
                round_trip.let_go()
                await kernel.close()

    @pytest.mark.parametrize("part", range(FIRST_CALL_PARTS))
    @pytest.mark.parametrize("kept", ["in memory", "in a file"])
    async def test_the_first_call_on_a_fresh_storage_leaves_it_whole(
        self, round_trip: HeldRoundTrip, tmp_path: Path, kept: str, part: int
    ) -> None:
        """The first call makes the first touch, which provisions the schema, and then writes its file."""
        traced = AsyncVirtualFileSystem(storage=sqlite_storage(kept, tmp_path / "traced"), default_authority=SYSTEM)
        round_trip.again()
        assert (await traced.write(path="/a.txt", content="one")).success
        names = list(round_trip.seen)
        await traced.close()
        # The first commit is the first touch's and the last is the write's.
        assert names.count("commit") == 2
        commit = len(names) - 1 - names[::-1].index("commit")
        cuts = range(part, len(names), FIRST_CALL_PARTS)
        assert cuts, "the call was traced as too few round trips for this part to cut one"
        for cut in cuts:
            storage = sqlite_storage(kept, tmp_path / f"cut{cut}")
            kernel = AsyncVirtualFileSystem(storage=storage, default_authority=SYSTEM)
            try:
                connections = Connections(storage._host.engine)
                round_trip.again()
                round_trip.hold(number(cut))
                await cancel_while_held(kernel.write(path="/a.txt", content="one"), round_trip)
                where = f"the first call cancelled at round trip {cut}, {names[cut]!r}"
                assert (len(connections.opened) <= 1, connections.invalidated) == (True, []), where
                assert (await kernel.write(path="/b.txt", content="more")).success, where
                listed = sorted(str(row.path) for row in (await kernel.ls("/")).observations)
                assert listed == (["/b.txt"] if cut < commit else ["/a.txt", "/b.txt"]), where
                if cut >= commit:
                    assert await content_and_version(kernel) == ("one", 1), where
            finally:
                round_trip.let_go()
                await kernel.close()


class TestACancelledWriteOnADatabaseInAFile:
    @IN_A_FILE
    async def test_a_write_cancelled_inside_one_of_its_reads_leaves_the_next_write_working(
        self, fs: AsyncVirtualFileSystem, storage: DatabaseStorage, round_trip: HeldRoundTrip
    ) -> None:
        """A connection thrown away with a cursor open keeps its write lock until the collector runs.

        Guards the host's choice of what runs out of reach: were it the
        in-memory database alone, this cancellation would cost a connection.
        """
        connections = Connections(storage._host.engine)
        round_trip.hold(starts_with("execute SELECT vfs_meta.grant_revision"))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await content_and_version(fs) == ("old", 1)
        await another_file_can_be_written(fs)


class TestACancelledInstallOfExtensions:
    @IN_MEMORY_AND_IN_A_FILE
    async def test_an_install_cancelled_inside_its_probe_costs_no_connection_and_no_row(
        self, fs: AsyncVirtualFileSystem, storage: DatabaseStorage, round_trip: HeldRoundTrip
    ) -> None:
        """Guards ``install_extensions``: run in its caller's task, a cancellation inside it reaches the connection."""
        connections = Connections(storage._host.engine)
        round_trip.hold(lambda name: "vec_version" in name)
        await cancel_while_held(storage.install_extensions(), round_trip)
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await content_and_version(fs) == ("old", 1)
        await another_file_can_be_written(fs)


class TestACallerThatDoesNotWait:
    async def test_a_storage_lists_every_file_after_a_time_limit_around_a_call_ran_out(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        """The limit runs out while a statement of the call is held on the driver, by no timer.

        Guards ``with_retry``: a call that runs in its caller's task is cut
        off inside that statement, and the in-memory database goes with it.
        """
        round_trip.hold(reads_entries)

        async def run_out_at_the_held_round_trip(limit: asyncio.Timeout) -> None:
            await round_trip.reached.wait()
            limit.reschedule(asyncio.get_running_loop().time())
            await turns_of_the_loop()
            ran_out.append(limit.expired())
            round_trip.let_go()

        ran_out: list[bool] = []
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(None) as limit:
                expiry = asyncio.ensure_future(run_out_at_the_held_round_trip(limit))
                await fs.stat("/")
        await expiry
        # The limit had run out while the round trip was still held.
        assert ran_out == [True]
        assert [str(row.path) for row in (await fs.ls("/")).observations] == ["/a.txt"]

    async def test_a_read_that_is_cancelled_and_not_awaited_leaves_the_next_write_working(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(reads_entries)
        abandoned = asyncio.ensure_future(fs.read("/a.txt"))
        await round_trip.reached.wait()
        abandoned.cancel()
        round_trip.let_go()
        assert (await fs.write(path="/b.txt", content="more")).success
        assert sorted(str(row.path) for row in (await fs.ls("/")).observations) == ["/a.txt", "/b.txt"]
        with pytest.raises(asyncio.CancelledError):
            await abandoned


class TestTheCallerWaitsForItsAttempt:
    async def test_a_caller_cancelled_twice_is_still_waiting_and_raises_once(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(reads_entries)
        task = asyncio.ensure_future(fs.stat("/"))
        await round_trip.reached.wait()
        task.cancel()
        await turns_of_the_loop()
        still_waiting_after_one = not task.done()
        task.cancel()
        await turns_of_the_loop()
        still_waiting_after_two = not task.done()
        round_trip.let_go()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (still_waiting_after_one, still_waiting_after_two) == (True, True)
        assert (await fs.read("/a.txt")).one().content == "old"

    @IN_MEMORY_AND_IN_A_FILE
    async def test_the_caller_is_raised_the_cancellation_it_was_cancelled_with(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        """A scope that cancels with a message knows its own cancellation by it, so the message must come back.

        Guards ``run_out_of_reach``: a new ``CancelledError()`` raised in
        place of the caller's own carries no message.
        """
        round_trip.hold(reads_entries)
        assert await cancel_while_held(fs.stat("/"), round_trip, "why") == ("why",)

    async def test_the_refusal_of_a_cancelled_write_is_never_reported_as_unretrieved(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        """Guards the read of the dropped attempt's result: without it the loop logs the refusal at collection."""
        round_trip.hold(starts_with("execute UPDATE vfs_entries"))
        with reports_of_the_loop() as reports:
            await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
            await collect_what_was_dropped()
        assert reports == []
        assert (await fs.read("/a.txt")).one().content == "old"


class TestAStorageHandedAnInMemorySessionFactory:
    """The host runs these attempts out of reach, and it did not make their sessions, so no commit is refused."""

    @pytest.fixture
    async def engine(self) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine(IN_MEMORY, **engine_arguments(IN_MEMORY))
        yield engine
        await engine.dispose()

    @pytest.fixture
    async def handed(self, engine: AsyncEngine, round_trip: HeldRoundTrip) -> AsyncIterator[AsyncVirtualFileSystem]:
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        kernel = await kernel_holding_a_file(storage)
        round_trip.seen.clear()
        yield kernel
        round_trip.let_go()
        await storage._host.settle_statistics()
        await kernel.close()

    async def test_a_cancelled_stat_costs_no_connection_and_no_row(
        self, handed: AsyncVirtualFileSystem, engine: AsyncEngine, round_trip: HeldRoundTrip
    ) -> None:
        """Guards first touch: a host that did not learn there that its database is in memory would lose it here."""
        connections = Connections(engine)
        round_trip.hold(reads_entries)
        await cancel_while_held(handed.stat("/"), round_trip)
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await content_and_version(handed) == ("old", 1)

    async def test_a_write_cancelled_before_its_commit_has_landed(
        self, handed: AsyncVirtualFileSystem, engine: AsyncEngine, round_trip: HeldRoundTrip
    ) -> None:
        """Guards where the refusal is registered: on every session, this write would be rolled back."""
        connections = Connections(engine)
        round_trip.hold(starts_with("execute UPDATE vfs_entries"))
        await cancel_while_held(handed.write(path="/a.txt", content="new"), round_trip)
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await content_and_version(handed) == ("new", 2)
