"""A call that its caller cancels leaves its storage whole.

An in-memory SQLite database lives in its one connection. A call that
is cancelled while it uses that connection must not cost the storage
its rows, and the next call must work.

No test here reads a clock. One chosen driver round trip is held on the
driver's worker thread until the test lets it go, and the call is
cancelled while it is held.
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from typing import TYPE_CHECKING, Any

import aiosqlite.core
import pytest
from sqlalchemy import event

from vfs import AsyncVirtualFileSystem, Authority, DatabaseStorage, InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
    from pathlib import Path


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
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
async def fs(storage: InMemoryStorage, round_trip: HeldRoundTrip) -> AsyncIterator[AsyncVirtualFileSystem]:
    """A kernel that holds ``/a.txt``, closed whatever the test did so no driver thread is left running."""
    kernel = AsyncVirtualFileSystem(storage=storage, default_authority=Authority.system())
    assert (await kernel.write(path="/a.txt", content="old")).success
    round_trip.seen.clear()
    yield kernel
    round_trip.let_go()
    await kernel.close()


async def cancel_while_held(call: Awaitable[Any], round_trip: HeldRoundTrip) -> None:
    """Cancel *call* while its chosen round trip is held, then let the round trip go."""
    task = asyncio.ensure_future(call)
    reached = asyncio.ensure_future(round_trip.reached.wait())
    await asyncio.wait({task, reached}, return_when=asyncio.FIRST_COMPLETED)
    assert round_trip.reached.is_set(), "the call ended before it reached the chosen round trip"
    task.cancel()
    round_trip.let_go()
    with pytest.raises(asyncio.CancelledError):
        await task


async def turns_of_the_loop() -> None:
    """Let every task that can run do so, while the held round trip keeps the call where it is."""
    for _ in range(10):
        await asyncio.sleep(0)


def reads_entries(round_trip: str) -> bool:
    return round_trip.startswith("execute SELECT") and "vfs_entries" in round_trip


def starts_with(prefix: str) -> Callable[[str], bool]:
    return lambda round_trip: round_trip.startswith(prefix)


def number(index: int) -> Callable[[str], bool]:
    """Pick the round trip that is *index* places after the first one asked about."""
    asked = itertools.count()
    return lambda _round_trip: next(asked) == index


async def kernel_holding_a_file(storage: DatabaseStorage) -> AsyncVirtualFileSystem:
    """A kernel that holds ``/a.txt``, with the statistics pass of that write over, so a call runs alone."""
    kernel = AsyncVirtualFileSystem(storage=storage, default_authority=Authority.system())
    assert (await kernel.write(path="/a.txt", content="old")).success
    await storage._host.settle_statistics()
    return kernel


class Connections:
    """The connections a storage's pool opened and threw away, from the moment this is made."""

    def __init__(self, storage: DatabaseStorage) -> None:
        self.opened: list[object] = []
        self.invalidated: list[object] = []
        engine = storage._host.engine.sync_engine
        event.listen(engine, "connect", lambda connection, _record: self.opened.append(connection))
        event.listen(engine, "invalidate", lambda connection, _record, _exception: self.invalidated.append(connection))


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
        self, fs: AsyncVirtualFileSystem, storage: InMemoryStorage, round_trip: HeldRoundTrip
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
    async def test_an_in_memory_storage_keeps_its_rows_and_its_one_connection(
        self, round_trip: HeldRoundTrip, call: str
    ) -> None:
        names = await round_trips_of(call, InMemoryStorage(), round_trip)
        commit = names.index("commit") if call == "write" else len(names)
        assert names.count("commit") == (1 if call == "write" else 0)
        for cut in range(len(names)):
            storage = InMemoryStorage()
            kernel = await kernel_holding_a_file(storage)
            try:
                connections = Connections(storage)
                round_trip.again()
                round_trip.hold(number(cut))
                await cancel_while_held(CALLS[call](kernel), round_trip)
                where = f"{call} cancelled at round trip {cut}, {names[cut]!r}"
                assert (connections.opened, connections.invalidated) == ([], []), where
                assert await content_and_version(kernel) == (("old", 1) if cut < commit else ("new", 2)), where
                await another_file_can_be_written(kernel)
            finally:
                round_trip.let_go()
                await kernel.close()

    async def test_a_write_on_a_database_in_a_file_gives_the_same_two_answers(
        self, round_trip: HeldRoundTrip, tmp_path: Path
    ) -> None:
        def a_file(name: str) -> DatabaseStorage:
            return DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path / name}.sqlite")

        names = await round_trips_of("write", a_file("traced"), round_trip)
        commit = names.index("commit")
        assert names.count("commit") == 1
        for cut in range(len(names)):
            storage = a_file(f"cut{cut}")
            kernel = await kernel_holding_a_file(storage)
            try:
                connections = Connections(storage)
                round_trip.again()
                round_trip.hold(number(cut))
                await cancel_while_held(CALLS["write"](kernel), round_trip)
                where = f"write cancelled at round trip {cut}, {names[cut]!r}"
                assert await content_and_version(kernel) == (("old", 1) if cut < commit else ("new", 2)), where
                # A file outlives its connections, so a cancelled call may cost the one it was using.
                assert len(connections.invalidated) <= 1, where
            finally:
                round_trip.let_go()
                await kernel.close()


class TestACallerThatDoesNotWait:
    async def test_a_storage_lists_every_file_after_a_time_limit_around_a_call_ran_out(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        round_trip.hold(reads_entries)
        # The round trip is held until the second timer, so the limit always runs out first.
        asyncio.get_running_loop().call_later(0.05, round_trip.let_go)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(fs.stat("/"), timeout=0.01)
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
