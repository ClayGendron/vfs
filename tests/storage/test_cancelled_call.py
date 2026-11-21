"""A call that its caller cancels leaves its storage whole, and sends nothing after the statement in flight.

An in-memory SQLite database lives in its one connection. A call that
is cancelled while it uses that connection must not cost the storage
its rows, and the next call must work. On a database in a file the
connection must not be thrown away with a cursor open, which locks the
next writer out.

The same holds on each of the four SQLite hosts: a storage that built
its engine from a URL and one that was handed a session factory, over a
database in memory and over one in a file.

No test here reads a clock. One chosen driver round trip is held on the
driver's worker thread until the test lets it go, and the call is
cancelled while it is held. The unit tests of the task, the mark and
the refusals are in ``tests/storage/database/test_attempts.py``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import aiosqlite.core
import pytest
from sqlalchemy import event, text

from tests.support.cancelled_callers import (
    HOSTS,
    Connections,
    HeldRoundTrip,
    Host,
    cancel_while_held,
    collect_what_was_dropped,
    first_statement_of_a_transaction,
    left_of_a_checkout,
    reads_entries,
    reports_of_the_loop,
    starts_with,
    turns_of_the_loop,
)
from vfs import AsyncVirtualFileSystem, Authority
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database.attempts import ATTEMPT, run_out_of_reach

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.orm import Session

    from vfs import DatabaseStorage

SYSTEM = Authority.system()

# The events of an engine, of its pool and of a session that a listener can be put on.
ENGINE_EVENTS = (
    *("before_execute", "after_execute", "before_cursor_execute", "after_cursor_execute", "engine_connect"),
    *("begin", "commit", "rollback", "savepoint", "release_savepoint", "rollback_savepoint"),
)
POOL_EVENTS = (
    *("connect", "first_connect", "checkout", "checkin", "reset"),
    *("invalidate", "soft_invalidate", "close", "detach", "close_detached"),
)
SESSION_EVENTS = (
    *("before_commit", "after_commit", "after_begin", "after_rollback", "after_soft_rollback"),
    *("after_transaction_create", "after_transaction_end", "do_orm_execute", "before_flush", "after_flush"),
)

BUILT = pytest.mark.parametrize("host", HOSTS[:2], indirect=True)
IN_A_FILE = pytest.mark.parametrize("host", ["built in a file"], indirect=True)
ON_EVERY_HOST = pytest.mark.parametrize("host", HOSTS, indirect=True)


@pytest.fixture
def round_trip(monkeypatch: pytest.MonkeyPatch) -> Iterator[HeldRoundTrip]:
    held = HeldRoundTrip()
    queue_it = aiosqlite.core.Connection._execute

    async def _execute(self: Any, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        statement = next((" ".join(arg.split()) for arg in args if isinstance(arg, str)), "")
        name = f"{getattr(function, '__name__', '')} {statement}".strip()
        return await queue_it(self, held.sees(name, function), *args, **kwargs)

    monkeypatch.setattr(aiosqlite.core.Connection, "_execute", _execute)
    yield held
    held.let_go()


@pytest.fixture
async def host(request: pytest.FixtureRequest, tmp_path: pathlib.Path) -> AsyncIterator[Host]:
    """One of the four SQLite hosts: built in memory, or the one the test's parameter names."""
    made = Host(getattr(request, "param", HOSTS[0]), tmp_path / "one")
    yield made
    await made.close()


@pytest.fixture
def storage(host: Host) -> DatabaseStorage:
    return host.storage


@pytest.fixture
async def fs(host: Host, round_trip: HeldRoundTrip) -> AsyncIterator[AsyncVirtualFileSystem]:
    """A kernel that holds ``/a.txt``, closed whatever the test did so no driver thread is left running.

    The statistics pass of that write is over, so the round trip a test holds is one of its own call.
    """
    kernel = await kernel_holding_a_file(host.storage)
    round_trip.seen.clear()
    yield kernel
    round_trip.let_go()
    await kernel.close()


async def kernel_holding_a_file(storage: DatabaseStorage) -> AsyncVirtualFileSystem:
    """A kernel that holds ``/a.txt``, with the statistics pass of that write over, so a call runs alone."""
    kernel = AsyncVirtualFileSystem(storage=storage, default_authority=SYSTEM)
    assert (await kernel.write(path="/a.txt", content="old")).success
    await storage._host.settle_statistics()
    return kernel


CALLS: dict[str, Callable[[AsyncVirtualFileSystem], Awaitable[Any]]] = {
    "stat": lambda kernel: kernel.stat("/"),
    "read": lambda kernel: kernel.read("/a.txt"),
    "write": lambda kernel: kernel.write(path="/a.txt", content="new"),
}

# One call of each shape a verb's transaction takes, over the files of ``a_directory``.
VERBS: dict[str, Callable[[AsyncVirtualFileSystem], Awaitable[Any]]] = {
    "stat": lambda kernel: kernel.stat("/a.txt"),
    "read": lambda kernel: kernel.read("/a.txt"),
    "grep": lambda kernel: kernel.grep("old"),
    "write of a batch": lambda kernel: kernel.write(
        entries=[Entry(path=Path("/a.txt"), content="new"), Entry(path=Path("/dir/z.txt"), content="new")]
    ),
    "edit": lambda kernel: kernel.edit(path="/a.txt", old="old", new="new"),
    "delete of a directory": lambda kernel: kernel.delete("/dir"),
    "move": lambda kernel: kernel.move("/dir/x.txt", "/dir/moved.txt"),
}


async def a_directory(kernel: AsyncVirtualFileSystem, storage: DatabaseStorage) -> None:
    """Add ``/dir`` with two files to *kernel*, and wait for the statistics pass of each write.

    A storage that was handed an in-memory session factory has one connection
    and no turns, so a pass that is still running would collide with the next call.
    """
    for path in ("/dir/x.txt", "/dir/y.txt"):
        assert (await kernel.write(path=path, content="old", parents=True)).success
        await storage._host.settle_statistics()


async def everything(kernel: AsyncVirtualFileSystem) -> list[tuple[str, str | None, int | None]]:
    """Every entry under the root as its path, content and version, in the order of the paths."""
    found: list[tuple[str, str | None, int | None]] = []
    waiting = ["/"]
    while waiting:
        listed = await kernel.ls(waiting.pop())
        assert listed.success, listed.errors
        for row in listed.observations:
            if row.kind == "directory":
                waiting.append(str(row.path))
                found.append((str(row.path), None, None))
            else:
                read = await kernel.read(str(row.path))
                assert read.success, read.errors
                found.append((str(row.path), read.one().content, (await kernel.stat(str(row.path))).one().version))
    return sorted(found)


def listeners_on(engine: AsyncEngine) -> dict[str, int]:
    """How many listeners each event of *engine* and of its pool has."""
    sync = engine.sync_engine
    counted = {name: len(list(getattr(sync.dispatch, name))) for name in ENGINE_EVENTS}
    return counted | {name: len(list(getattr(sync.pool.dispatch, name))) for name in POOL_EVENTS}


def listeners_of(session: Session) -> dict[str, int]:
    """How many listeners each event of *session* has, its class's among them."""
    return {name: len(list(getattr(session.dispatch, name))) for name in SESSION_EVENTS}


async def content_and_version(kernel: AsyncVirtualFileSystem) -> tuple[str | None, int | None]:
    read = await kernel.read("/a.txt")
    assert read.success, read.errors
    return read.one().content, read.one().version


async def another_file_can_be_written(kernel: AsyncVirtualFileSystem) -> None:
    assert (await kernel.write(path="/b.txt", content="more")).success
    assert (await kernel.read("/b.txt")).one().content == "more"
    assert sorted(str(row.path) for row in (await kernel.ls("/")).observations) == ["/a.txt", "/b.txt"]


class TestNothingIsSentAfterTheStatementInFlight:
    """A cancelled call ends the statement in flight, sends no other, and its transaction is rolled back."""

    @ON_EVERY_HOST
    @pytest.mark.parametrize("verb", VERBS)
    async def test_a_call_cancelled_inside_its_first_statement_sends_no_other(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip, verb: str
    ) -> None:
        """Guards the check before each statement: without it a read runs to its end and a delete sends every one."""
        await a_directory(fs, host.storage)
        before = await everything(fs)
        connections = Connections(host.engine)
        round_trip.again()
        round_trip.hold(first_statement_of_a_transaction())
        await cancel_while_held(VERBS[verb](fs), round_trip)
        assert round_trip.statements_after_the_cut() == []
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await everything(fs) == before
        assert (await fs.write(path="/next.txt", content="more")).success

    @ON_EVERY_HOST
    @pytest.mark.parametrize("call", ["stat", "write"])
    async def test_a_call_cancelled_while_its_connection_is_checked_out_begins_no_transaction(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip, call: str
    ) -> None:
        """A checkout that has begun stamps all its settings, and the attempt is refused before it begins.

        Guards the refusal at the begin: without it the transaction's ``BEGIN`` follows the settings.
        """
        connections = Connections(host.engine)
        round_trip.hold(starts_with("execute PRAGMA busy_timeout"))
        await cancel_while_held(CALLS[call](fs), round_trip)
        seen, held_at = list(round_trip.seen), round_trip.held_at
        assert held_at is not None
        left = left_of_a_checkout(seen, held_at)
        assert (round_trip.statements_after_the_cut(), len(left) > 0) == (left, True)
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await content_and_version(fs) == ("old", 1)


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
    @ON_EVERY_HOST
    @pytest.mark.parametrize(
        "cut_at",
        ["execute UPDATE vfs_entries", "execute INSERT INTO vfs_content", "execute RELEASE vfs_statistics"],
        ids=["at its first change", "after a savepoint is released", "at the last statement before the commit"],
    )
    async def test_a_write_cancelled_before_its_commit_changes_nothing(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip, cut_at: str
    ) -> None:
        """Guards the refused commit: the cut at the last statement leaves the commit alone to stop the write.

        And the rollback to a savepoint, which is let through: refused,
        the session's close fails at its first change and the connection never comes back.
        """
        connections = Connections(host.engine)
        round_trip.hold(starts_with(cut_at))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert "commit" not in round_trip.since("execute UPDATE vfs_entries")
        assert round_trip.statements_after_the_cut() == []
        assert await content_and_version(fs) == ("old", 1)
        assert (connections.opened, connections.invalidated) == ([], [])

    @ON_EVERY_HOST
    @pytest.mark.parametrize("cut_at", ["commit", "rollback"], ids=["at its commit", "after its commit"])
    async def test_a_write_cancelled_at_its_commit_or_after_has_landed_whole(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip, cut_at: str
    ) -> None:
        round_trip.hold(lambda name: name == cut_at and bool(round_trip.since("execute INSERT INTO vfs_content")))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert round_trip.statements_after_the_cut() == []
        assert await content_and_version(fs) == ("new", 2)

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
        # The round trip that was held is the last statement of the call ahead: the write behind sent none.
        assert round_trip.statements_after_the_cut() == []
        assert (await fs.read("/a.txt")).one().content == "old"


class TestACancelledWriteOnADatabaseInAFile:
    @IN_A_FILE
    async def test_a_write_cancelled_inside_one_of_its_reads_leaves_the_next_write_working(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip
    ) -> None:
        """A connection thrown away with a cursor open keeps its write lock until the collector runs.

        Guards the host's choice of what runs out of reach: were it the
        in-memory database alone, this cancellation would cost a connection.
        """
        connections = Connections(host.engine)
        round_trip.hold(starts_with("execute SELECT vfs_meta.grant_revision"))
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert (connections.opened, connections.invalidated) == ([], [])
        assert await content_and_version(fs) == ("old", 1)
        await another_file_can_be_written(fs)


class TestACancelledInstallOfExtensions:
    @ON_EVERY_HOST
    async def test_an_install_cancelled_inside_its_probe_costs_no_connection_and_no_row(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip
    ) -> None:
        """Guards ``install_extensions``: run in its caller's task, a cancellation inside it reaches the connection."""
        connections = Connections(host.engine)
        round_trip.hold(lambda name: "vec_version" in name)
        await cancel_while_held(host.storage.install_extensions(), round_trip)
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

    @ON_EVERY_HOST
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


@pytest.mark.parametrize("host", HOSTS[2:], indirect=True)
class TestAHandedEngineIsNeverTouched:
    """A storage that was handed a session factory puts nothing on what outlives the sessions it takes."""

    async def test_cancelled_calls_leave_no_listener_on_the_engine_or_on_its_sessions(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip
    ) -> None:
        """Guards where the refusals are put: on the engine or on the session class, they would be found here."""
        assert host.sessions is not None
        engine = host.engine.sync_engine
        # The first call has put the transaction control on the engine: its begin and its checkout.
        before = listeners_on(host.engine)
        round_trip.hold(first_statement_of_a_transaction())
        await cancel_while_held(fs.write(path="/a.txt", content="new"), round_trip)
        assert (await fs.read("/a.txt")).one().content == "old"
        assert listeners_on(host.engine) == before
        assert [before[name] for name in ("before_cursor_execute", "before_execute", "commit")] == [0, 0, 0]
        assert engine.get_execution_options().get(ATTEMPT) is None
        async with host.sessions() as own:
            assert (own.sync_session.get_bind() is engine, set(listeners_of(own.sync_session).values())) == (True, {0})

    async def test_a_session_the_application_makes_inside_a_marked_attempt_is_not_refused(
        self, fs: AsyncVirtualFileSystem, host: Host
    ) -> None:
        """Guards whose transactions are refused: the mark alone would stop the application's own on this engine."""
        assert host.sessions is not None
        sessions = host.sessions
        started, let_go = asyncio.Event(), asyncio.Event()

        async def attempt() -> None:
            started.set()
            await let_go.wait()
            async with sessions() as own:
                await own.execute(text("CREATE TABLE own (n INTEGER)"))
                await own.execute(text("INSERT INTO own VALUES (1)"))
                await own.commit()

        caller = asyncio.ensure_future(run_out_of_reach(attempt))
        await started.wait()
        caller.cancel()
        await turns_of_the_loop()
        let_go.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        async with sessions() as own:
            assert list((await own.execute(text("SELECT n FROM own"))).scalars()) == [1]
        assert await content_and_version(fs) == ("old", 1)
