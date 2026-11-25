"""A call that its caller cancels leaves its storage whole, and sends nothing after the statement in flight.

An in-memory SQLite database lives in its one connection. A call that
is cancelled while it uses that connection must not cost the storage
its rows, and the next call must work. On a database in a file the
connection must not be thrown away with a cursor open, which locks the
next writer out.

The same holds on both SQLite hosts: a storage whose database is in
memory, behind one connection, and one whose database is in a file,
behind a pool.

No test here reads a clock. One chosen driver round trip is held on the
driver's worker thread until the test lets it go, and the call is
cancelled while it is held. The unit tests of the task, the mark and
the refusals are in ``tests/storage/database/test_attempts.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

import aiosqlite.core
import anyio
import pytest
from sqlalchemy import event

from tests.support.cancelled_callers import (
    CONNECTING,
    FINGERPRINT,
    HOSTS,
    STAMP,
    Connections,
    HeldRoundTrip,
    Host,
    cancel_if_held,
    cancel_while_held,
    collect_what_was_dropped,
    first_of_kind,
    first_statement_of_a_transaction,
    kinds,
    left_of_a_checkout,
    number,
    reads_entries,
    reports_of_the_loop,
    starts_with,
    turns_of_the_loop,
)
from vfs import AsyncVirtualFileSystem, Authority
from vfs.models import Entry
from vfs.paths import Path

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

    from vfs import DatabaseStorage

SYSTEM = Authority.system()

IN_A_FILE = pytest.mark.parametrize("host", ["in a file"], indirect=True)
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
    """One of the two SQLite hosts: in memory, or the one the test's parameter names."""
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


class FreshWrites:
    """Writes ``/a.txt`` with a body no earlier call sent, so no write of a sweep is ``unchanged``."""

    def __init__(self) -> None:
        self.sent = 0

    @property
    def body(self) -> str:
        """The body of the latest call."""
        return f"new {self.sent}"

    def __call__(self, kernel: AsyncVirtualFileSystem) -> Awaitable[Any]:
        self.sent += 1
        return kernel.write(path="/a.txt", content=self.body)


WRITE = FreshWrites()

CALLS: dict[str, Callable[[AsyncVirtualFileSystem], Awaitable[Any]]] = {
    "stat": lambda kernel: kernel.stat("/"),
    "read": lambda kernel: kernel.read("/a.txt"),
    "write": WRITE,
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
    "grant": lambda kernel: kernel.grant("/dir", "ann", "read"),
    "revoke": lambda kernel: kernel.revoke("/dir", "bob"),
}


async def _while_an_error_is_handled(kernel: AsyncVirtualFileSystem) -> None:
    try:
        raise LookupError("an earlier step failed")
    except LookupError:
        await kernel.stat("/a.txt")


async def _in_a_finally_during_an_error(kernel: AsyncVirtualFileSystem) -> None:
    with contextlib.suppress(LookupError):
        try:
            raise LookupError("an earlier step failed")
        finally:
            await kernel.stat("/a.txt")


# Where a caller makes its call: a block that is handling an error replaces what is behind the error raised in it.
CALLED: dict[str, Callable[[AsyncVirtualFileSystem], Awaitable[Any]]] = {
    "plainly": lambda kernel: kernel.stat("/a.txt"),
    "while an error is handled": _while_an_error_is_handled,
    "in a finally during an error": _in_a_finally_during_an_error,
}


async def a_directory(kernel: AsyncVirtualFileSystem, storage: DatabaseStorage) -> None:
    """Add ``/dir`` with two files and a grant to *kernel*, and wait for the statistics pass of those writes."""
    for path in ("/dir/x.txt", "/dir/y.txt"):
        assert (await kernel.write(path=path, content="old", parents=True)).success
    assert (await kernel.grant("/dir", "bob", "read")).success
    await storage._host.settle_statistics()


async def everything(kernel: AsyncVirtualFileSystem) -> list[tuple[str, str | None, int | None]]:
    """Every entry under the root as its path, content and version, and every grant on ``/dir``, in order."""
    granted = await kernel.grants("/dir")
    assert granted.success, granted.errors
    found: list[tuple[str, str | None, int | None]] = [
        (f"{grant['path_prefix']} to {grant['principal_id']}", grant["level"], None)
        for grant in (granted.model_extra or {})["grants"]
    ]
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


@pytest.mark.timeout(60)
async def test_a_cut_a_call_ends_before_holds_no_round_trip_of_the_next_call(
    fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
) -> None:
    """Guards the withdrawn hold: a cut left armed counts on into the next call and holds its round trip for good.

    The sweep's statistics pass between two cuts was held that way, and the sweep hung where a write ended early.
    """
    round_trip.again()
    await fs.stat("/a.txt")
    sent = len(round_trip.seen)
    round_trip.again()
    round_trip.hold(number(sent))
    assert await cancel_if_held(fs.stat("/a.txt"), round_trip) is None
    assert (await fs.stat("/a.txt")).success
    assert round_trip.held_at is None


@pytest.mark.slow
class TestACallCancelledAtOneRoundTripAfterAnother:
    """One storage takes every cut of a sweep, so each cut also proves that the cut before it left the storage whole.

    The in-memory host is cut at every round trip of each call. The host in
    a file is cut at the first round trip of each kind: the driver function
    and the first two words of the statement it carries.
    """

    @ON_EVERY_HOST
    @pytest.mark.parametrize("call", CALLS)
    async def test_a_storage_keeps_its_rows_and_its_connections_and_is_sent_nothing_more(
        self, fs: AsyncVirtualFileSystem, host: Host, round_trip: HeldRoundTrip, call: str
    ) -> None:
        cuts = await every_cut_of(CALLS[call], fs, host, round_trip)
        expected = await content_and_version(fs)
        connections = Connections(host.engine)
        landed = 0
        for cut in cuts:
            await host.storage._host.settle_statistics()
            round_trip.again()
            round_trip.hold(cut)
            if await cancel_if_held(CALLS[call](fs), round_trip) is None:
                # A write sends fewer round trips once the host knows which of its tables have an index,
                # so a cut of the traced write may not come: the write then ran to its end, and landed.
                assert call == "write"
                expected = (WRITE.body, (expected[1] or 0) + 1)
                continue
            seen, held_at = list(round_trip.seen), round_trip.held_at
            assert held_at is not None
            where = f"{call} cancelled at round trip {held_at}, {seen[held_at]!r}"
            assert round_trip.statements_after_the_cut() == left_of_a_checkout(seen, held_at), where
            assert connections.lost_to_a_cancellation() == (0, 0), where
            # Nothing before the commit and all of it from the commit on, on every host alike.
            if "commit" in seen[: held_at + 1]:
                landed += 1
                expected = (WRITE.body, (expected[1] or 0) + 1)
            else:
                assert "commit" not in seen, where
            assert await content_and_version(fs) == expected, where
            assert (await fs.write(path="/b.txt", content=where)).success, where
        # A write is cut on both sides of its commit: at the commit, and at the rollback that returns the connection.
        assert landed == (2 if call == "write" else 0)

    @ON_EVERY_HOST
    @pytest.mark.parametrize("sent", CONNECTING)
    async def test_a_first_call_cancelled_while_its_connection_is_made_leaves_the_storage_whole(
        self, host: Host, round_trip: HeldRoundTrip, sent: str
    ) -> None:
        """The first call of all makes the connection. Its round trips come once, so each cut has its own storage."""
        kernel = AsyncVirtualFileSystem(storage=host.storage, default_authority=SYSTEM)
        connections = Connections(host.engine)
        round_trip.again()
        round_trip.hold(starts_with(sent))
        await cancel_while_held(kernel.write(path="/a.txt", content="one"), round_trip)
        seen, held_at = list(round_trip.seen), round_trip.held_at
        assert held_at is not None
        assert round_trip.statements_after_the_cut() == left_of_a_checkout(seen, held_at)
        assert (len(connections.opened), connections.invalidated, "commit" in seen) == (1, [], False)
        assert (await kernel.write(path="/b.txt", content="more")).success
        await host.storage._host.settle_statistics()
        assert [str(row.path) for row in (await kernel.ls("/")).observations] == ["/b.txt"]

    @ON_EVERY_HOST
    async def test_the_first_touch_of_a_fresh_storage_is_sent_nothing_more_and_runs_again(
        self, host: Host, round_trip: HeldRoundTrip, tmp_path: pathlib.Path
    ) -> None:
        """A cancelled first touch is rolled back whole, so the storage is as fresh for the next cut as before."""
        traced = Host(host.name, tmp_path / "traced")
        try:
            names = await first_call_after_one_was_cancelled(traced, round_trip)
        finally:
            await traced.close()
        # The first commit is the first touch's, and the second is the write's.
        assert names.count("commit") == 2
        assert not [name for name in names if name.startswith(CONNECTING)], "the traced call made its connection"
        kernel = AsyncVirtualFileSystem(storage=host.storage, default_authority=SYSTEM)
        connections = Connections(host.engine)
        for wanted in ["execute BEGIN IMMEDIATE", *kinds(names[: names.index("commit") + 1])]:
            assert host.storage._host._ready is False
            round_trip.again()
            round_trip.hold(first_of_kind(wanted))
            await cancel_while_held(kernel.write(path="/a.txt", content="one"), round_trip)
            seen, held_at = list(round_trip.seen), round_trip.held_at
            assert held_at is not None
            where = f"the first call cancelled at round trip {held_at}, {seen[held_at]!r}"
            assert round_trip.statements_after_the_cut() == left_of_a_checkout(seen, held_at), where
            assert (len(connections.opened) <= 1, connections.invalidated) == (True, []), where
            assert ("commit" in seen) == (wanted == "commit"), where
        # The last cut was at the commit of the first touch, which landed; the write after it never began.
        assert (await kernel.write(path="/b.txt", content="more")).success
        await host.storage._host.settle_statistics()
        assert [str(row.path) for row in (await kernel.ls("/")).observations] == ["/b.txt"]


async def every_cut_of(
    call: Callable[[AsyncVirtualFileSystem], Awaitable[Any]],
    kernel: AsyncVirtualFileSystem,
    host: Host,
    round_trip: HeldRoundTrip,
) -> list[Callable[[str], bool]]:
    """The cuts of one sweep of *call*, from a trace nothing cancels: all on the first host, the kinds elsewhere."""
    await host.storage._host.settle_statistics()
    round_trip.again()
    await call(kernel)
    names = list(round_trip.seen)
    assert names, "the call was traced as no round trip at all"
    await host.storage._host.settle_statistics()
    if host.name == HOSTS[0]:
        return [number(cut) for cut in range(len(names))]
    return [first_of_kind(wanted) for wanted in kinds(names)]


async def first_call_after_one_was_cancelled(host: Host, round_trip: HeldRoundTrip) -> list[str]:
    """The round trips of the first call on *host* once an earlier first call was cancelled at its first change.

    A cancelled first touch leaves no table, but it leaves the connection
    open with its extension loaded, so the next first call is the one a
    sweep on one storage repeats.
    """
    kernel = AsyncVirtualFileSystem(storage=host.storage, default_authority=SYSTEM)
    round_trip.again()
    round_trip.hold(first_of_kind("execute BEGIN IMMEDIATE"))
    await cancel_while_held(kernel.write(path="/a.txt", content="one"), round_trip)
    round_trip.again()
    assert (await kernel.write(path="/a.txt", content="one")).success
    return list(round_trip.seen)


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


# Where a cancellation reaches the connection, the driver leaves a task that never ends and the loop cannot close.
@pytest.mark.timeout(60)
class TestACallerCancelledByATimeLimitAndByACancelScope:
    """Two cancellers of one call: a time limit, which cancels with no message, and a scope, which knows its own by one.

    The time limit is made to run out by a time that has passed, so no test waits on a clock. The
    guard above is no measure: it fails the test whose loop cannot close, in a serial run and under
    workers alike, where the run would otherwise hang.
    """

    @ON_EVERY_HOST
    @pytest.mark.parametrize("where", ["plainly", "while an error is handled", "in a finally during an error"])
    @pytest.mark.parametrize("first", ["the time limit", "the scope"])
    async def test_the_scope_knows_its_cancellation_and_what_follows_it_runs(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip, first: str, where: str
    ) -> None:
        """Guards which cancellation is raised: the scope must find its message on the error itself.

        Python replaces what is behind an error as it leaves a block that is handling
        another, so a scope's cancellation kept behind the time limit's is lost there.
        """
        round_trip.hold(reads_entries)
        cancellers: list[Callable[[], Any]] = []

        async def handler() -> tuple[bool, str]:
            with anyio.CancelScope() as scope:
                async with asyncio.timeout(None) as limit:
                    cancellers.extend([lambda: limit.reschedule(0), scope.cancel])
                    await CALLED[where](fs)
            return scope.cancelled_caught, "ran on after the scope"

        handled = asyncio.ensure_future(handler())
        await round_trip.reached.wait()
        for cancel in cancellers if first == "the time limit" else reversed(cancellers):
            cancel()
            await turns_of_the_loop()
        still_waiting = not handled.done()
        round_trip.let_go()
        assert (still_waiting, await handled) == (True, (True, "ran on after the scope"))
        assert (await fs.read("/a.txt")).one().content == "old"

    @ON_EVERY_HOST
    async def test_a_cancellation_from_outside_is_lost_when_a_scope_inside_is_cancelled_in_the_same_wait(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        """Pins a loss as it is: the scope takes the error, and the canceller outside it gets nothing.

        A plain await ends the task cancelled when the outside cancellation lands first. If this fails,
        the outside canceller is being served, and the docstring of ``run_out_of_reach`` is to say so.
        """
        round_trip.hold(reads_entries)
        scopes: list[anyio.CancelScope] = []

        async def handler() -> tuple[bool, str, int]:
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await fs.stat("/a.txt")
            # The next await is not cancelled, though the outside request is still counted on the task.
            await asyncio.sleep(0)
            task = asyncio.current_task()
            assert task is not None
            return scope.cancelled_caught, "ran on to its end", task.cancelling()

        handled = asyncio.ensure_future(handler())
        await round_trip.reached.wait()
        handled.cancel()
        await turns_of_the_loop()
        scopes[0].cancel()
        await turns_of_the_loop()
        round_trip.let_go()
        assert await handled == (True, "ran on to its end", 1)

    @ON_EVERY_HOST
    async def test_a_scope_inside_the_time_limit_takes_the_cancellation_and_no_timeout_is_raised(
        self, fs: AsyncVirtualFileSystem, round_trip: HeldRoundTrip
    ) -> None:
        """Pins the other nesting as it is: what a plain await gives when the scope's cancellation lands first."""
        round_trip.hold(reads_entries)
        cancellers: list[Callable[[], Any]] = []

        async def handler() -> tuple[bool, bool, int]:
            async with asyncio.timeout(None) as limit:
                with anyio.CancelScope() as scope:
                    cancellers.extend([lambda: limit.reschedule(0), scope.cancel])
                    await fs.stat("/a.txt")
                ran_on = scope.cancelled_caught
            task = asyncio.current_task()
            assert task is not None
            return ran_on, limit.expired(), task.cancelling()

        handled = asyncio.ensure_future(handler())
        await round_trip.reached.wait()
        for cancel in cancellers:
            cancel()
            await turns_of_the_loop()
        round_trip.let_go()
        assert await handled == (True, True, 0)


class TestACallerCancelledWhileItsAttemptWaitsForAConnection:
    async def test_it_is_back_when_the_attempt_gets_a_connection_and_begins_no_transaction(
        self, round_trip: HeldRoundTrip, tmp_path: pathlib.Path
    ) -> None:
        """The wait for a connection is the pool's, and nothing ends it but a connection or the pool's own timeout.

        Pins the wait as it is: the caller is not back while the call ahead holds the one
        connection, and the attempt that then gets it is refused at its ``BEGIN``.
        """
        host = Host("in a file", tmp_path / "one", {"pool_size": 1, "max_overflow": 0})
        kernel = await kernel_holding_a_file(host.storage)
        try:
            round_trip.again()
            round_trip.hold(reads_entries)
            ahead = asyncio.ensure_future(kernel.stat("/a.txt"))
            await round_trip.reached.wait()
            waiting = asyncio.ensure_future(kernel.stat("/a.txt"))
            await turns_of_the_loop()
            waiting.cancel("mine")
            await turns_of_the_loop()
            still_waiting = not waiting.done()
            round_trip.let_go()
            with pytest.raises(asyncio.CancelledError) as raised:
                await waiting
            assert (still_waiting, raised.value.args, (await ahead).success) == (True, ("mine",), True)
            # The statement that was held is the last of the call ahead. The checkout stamps its settings after it.
            assert round_trip.statements_after_the_cut() == [*STAMP, FINGERPRINT]
        finally:
            round_trip.let_go()
            await kernel.close()
            await host.close()
