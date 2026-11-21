"""An attempt out of reach of its caller's cancellation: the task, the mark and the refusals.

Each test runs ``run_out_of_reach`` over an attempt that waits where the
test tells it to, so the cancellation lands at a known point and no test
reads a clock. The sessions are real ones over an in-memory SQLite
database, and what the database was sent is counted, statement by
statement. The same laws on a whole storage are in
``tests/storage/test_cancelled_call.py``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.support.cancelled_callers import (
    IN_MEMORY,
    collect_what_was_dropped,
    reports_of_the_loop,
    turns_of_the_loop,
)
from vfs.storage.backends.database.attempts import (
    ATTEMPT,
    CANCELLED_ATTEMPT,
    AttemptSessions,
    attempt_begins,
    run_out_of_reach,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

ADD_TWO = "INSERT INTO kept VALUES (2)"
ADD_THREE = "INSERT INTO kept VALUES (3)"


class Waiting:
    """An attempt that waits until the test lets it go, and then does *then*."""

    def __init__(self, then: Callable[[], Any] = lambda: "done") -> None:
        self.started = asyncio.Event()
        self.ended = False
        self._then = then
        self._let_go = asyncio.Event()

    def let_go(self) -> None:
        self._let_go.set()

    async def __call__(self) -> Any:
        self.started.set()
        await self._let_go.wait()
        try:
            return self._then()
        finally:
            self.ended = True


async def cancelled_while_it_waits(attempt: Waiting, message: str = "the caller gave up") -> asyncio.CancelledError:
    """Cancel the caller of *attempt* while it waits, let it go, and return what the caller raised."""
    caller = asyncio.ensure_future(run_out_of_reach(attempt))
    await attempt.started.wait()
    caller.cancel(message)
    await turns_of_the_loop()
    attempt.let_go()
    with pytest.raises(asyncio.CancelledError) as raised:
        await caller
    return raised.value


def failing(error: BaseException) -> Callable[[], Any]:
    def fail() -> Any:
        raise error

    return fail


async def cancelled_at(gate: Waiting, attempt: Callable[[], Awaitable[Any]]) -> BaseException | None:
    """Cancel the caller of *attempt* while it waits at *gate*, let it go, and return what the attempt raised."""
    raised: list[BaseException] = []

    async def recorded() -> Any:
        try:
            return await attempt()
        except Exception as error:
            raised.append(error)
            raise

    caller = asyncio.ensure_future(run_out_of_reach(recorded))
    await gate.started.wait()
    caller.cancel()
    await turns_of_the_loop()
    gate.let_go()
    with pytest.raises(asyncio.CancelledError):
        await caller
    return raised[0] if raised else None


def listeners(target: Any, name: str) -> int:
    """How many listeners the event *name* has on *target*, those of its class and its engine among them."""
    return len(list(getattr(target.dispatch, name)))


class Kept:
    """An in-memory database of one table with one row, and every statement and checkout it saw since it was made.

    ``taken`` makes the sessions a host takes for its attempts. ``own``
    makes the sessions an application makes for itself on the same engine.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.own = async_sessionmaker(engine)
        self.taken = AttemptSessions(self.own)
        self.sent: list[str] = []
        self.checkouts: list[object] = []
        event.listen(engine.sync_engine, "before_cursor_execute", lambda *sent: self.sent.append(sent[2]))
        event.listen(engine.sync_engine, "checkout", lambda *checkout: self.checkouts.append(checkout[0]))

    async def rows(self) -> list[int]:
        async with self.own() as session:
            return list((await session.execute(text("SELECT n FROM kept ORDER BY n"))).scalars())


@pytest.fixture
async def kept() -> AsyncIterator[Kept]:
    engine = create_async_engine(IN_MEMORY)
    # A host's transaction control tells each transaction of its engine to the attempt, as this does.
    event.listen(engine.sync_engine, "begin", attempt_begins)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE kept (n INTEGER)"))
        await connection.execute(text("INSERT INTO kept VALUES (1)"))
    yield Kept(engine)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Running an attempt
# ---------------------------------------------------------------------------


class TestAnAttemptNobodyCancels:
    async def test_the_caller_gets_what_the_attempt_returns(self) -> None:
        async def attempt() -> str:
            return "the answer"

        assert await run_out_of_reach(attempt) == "the answer"

    async def test_the_caller_is_raised_what_the_attempt_raises(self) -> None:
        async def attempt() -> None:
            raise LookupError("no such row")

        with pytest.raises(LookupError, match="no such row"):
            await run_out_of_reach(attempt)


class TestACancelledCaller:
    async def test_the_caller_is_raised_its_own_cancellation(self) -> None:
        """The error raised is the one the caller was cancelled with, so its message is the canceller's.

        Guards ``run_out_of_reach``: with a new ``CancelledError()`` raised
        in its place, the message is gone, and a cancel scope that knows its
        own cancellation by that message lets the error escape.
        """
        raised = await cancelled_while_it_waits(Waiting(), "the scope ran out")
        assert raised.args == ("the scope ran out",)

    async def test_a_caller_cancelled_twice_is_raised_the_first_cancellation(self) -> None:
        """Guards which cancellation is kept: the last one would hide the canceller that came first."""
        attempt = Waiting()
        caller = asyncio.ensure_future(run_out_of_reach(attempt))
        await attempt.started.wait()
        caller.cancel("first")
        await turns_of_the_loop()
        caller.cancel("second")
        await turns_of_the_loop()
        attempt.let_go()
        with pytest.raises(asyncio.CancelledError) as raised:
            await caller
        assert raised.value.args == ("first",)

    async def test_the_attempt_runs_on_to_its_end(self) -> None:
        """Guards ``run_out_of_reach``: an attempt that is cancelled with its caller never reaches its end."""
        attempt = Waiting()
        await cancelled_while_it_waits(attempt)
        assert attempt.ended is True

    async def test_the_caller_is_still_waiting_after_each_cancellation(self) -> None:
        """Guards the wait: one that is not taken up again after a cancellation ends before the attempt has."""
        attempt = Waiting()
        caller = asyncio.ensure_future(run_out_of_reach(attempt))
        await attempt.started.wait()
        waiting: list[bool] = []
        for _ in range(3):
            caller.cancel()
            await turns_of_the_loop()
            waiting.append(not caller.done())
        attempt.let_go()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert waiting == [True, True, True]
        assert attempt.ended is True

    async def test_the_answer_of_an_attempt_that_succeeded_is_dropped(self) -> None:
        """Guards the last lines of ``run_out_of_reach``: a cancelled caller is never handed the result."""
        caller = asyncio.ensure_future(run_out_of_reach(attempt := Waiting()))
        await attempt.started.wait()
        caller.cancel()
        attempt.let_go()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert caller.cancelled() is True

    async def test_the_caller_is_raised_its_cancellation_and_not_what_the_attempt_raised(self) -> None:
        """Guards the drop: a dropped attempt's error raised in place of the cancellation reads as a failed call."""
        raised = await cancelled_while_it_waits(Waiting(failing(LookupError("no such row"))), "gave up")
        assert raised.args == ("gave up",)

    async def test_what_the_dropped_attempt_raised_is_never_reported_as_unretrieved(self) -> None:
        """Guards the read of the dropped task's result: without it the loop logs an exception nobody retrieved."""
        with reports_of_the_loop() as reports:
            await cancelled_while_it_waits(Waiting(failing(LookupError("no such row"))))
            await collect_what_was_dropped()
        assert reports == []


# ---------------------------------------------------------------------------
# Refusing a marked attempt
# ---------------------------------------------------------------------------


class TestAnAttemptNobodyCancelled:
    async def test_a_session_outside_any_attempt_sends_and_commits(self, kept: Kept) -> None:
        async with kept.taken() as session:
            await session.execute(text(ADD_TWO))
            await session.commit()
        assert kept.sent == [ADD_TWO]
        assert await kept.rows() == [1, 2]

    async def test_a_session_inside_an_attempt_sends_and_commits(self, kept: Kept) -> None:
        async def attempt() -> None:
            async with kept.taken() as session:
                await session.execute(text(ADD_TWO))
                await session.commit()

        await run_out_of_reach(attempt)
        assert kept.sent == [ADD_TWO]
        assert await kept.rows() == [1, 2]

    async def test_the_mark_of_one_attempt_is_not_seen_by_the_next(self, kept: Kept) -> None:
        await cancelled_while_it_waits(Waiting())

        async def attempt() -> None:
            async with kept.taken() as session:
                await session.execute(text(ADD_TWO))
                await session.commit()

        await run_out_of_reach(attempt)
        assert await kept.rows() == [1, 2]


class TestAMarkedAttempt:
    async def test_it_is_refused_at_its_next_statement(self, kept: Kept) -> None:
        """Guards the watch on the session's connection: without it every statement of a marked attempt is sent."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.taken() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.execute(text(ADD_THREE))

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [ADD_TWO])
        assert await kept.rows() == [1]

    async def test_it_is_refused_at_its_commit(self, kept: Kept) -> None:
        """Guards the refused commit: a commit is no statement, so without it a marked write lands."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.taken() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.commit()

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [ADD_TWO])
        assert await kept.rows() == [1]

    async def test_it_is_refused_the_first_statement_of_a_session_it_had_entered(self, kept: Kept) -> None:
        gate = Waiting()

        async def attempt() -> None:
            async with kept.taken() as session:
                await gate()
                await session.execute(text(ADD_TWO))

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [])

    async def test_it_is_refused_at_a_savepoint(self, kept: Kept) -> None:
        gate = Waiting()

        async def attempt() -> None:
            async with kept.taken() as session:
                connection = await session.connection()
                await gate()
                async with connection.begin_nested():
                    await connection.execute(text(ADD_TWO))

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [])

    async def test_it_enters_no_session(self, kept: Kept) -> None:
        """Guards the refusal at the entry: without it a marked attempt checks a connection out before it stops."""
        gate = Waiting()
        entered: list[AsyncSession] = []

        async def attempt() -> None:
            await gate()
            async with kept.taken() as session:
                entered.append(session)

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), entered, kept.checkouts) == (CANCELLED_ATTEMPT, [], [])

    async def test_a_task_it_started_carries_its_mark(self, kept: Kept) -> None:
        """A task copies the context it is started in, and the mark with it, so its statements are refused too."""
        gate = Waiting()

        async def child() -> None:
            async with kept.taken() as session:
                await gate()
                await session.execute(text(ADD_TWO))

        async def attempt() -> None:
            await asyncio.ensure_future(child())

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [])


class TestASessionTheApplicationMakes:
    """The refusals belong to the sessions a host takes, and nothing of them is left on the engine."""

    async def test_it_sends_and_commits_inside_a_marked_attempt(self, kept: Kept) -> None:
        """Guards whose sessions are refused: a refusal told by the mark alone would stop this session too."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.own() as session:
                await gate()
                await session.execute(text(ADD_TWO))
                await session.commit()

        assert await cancelled_at(gate, attempt) is None
        assert kept.sent == [ADD_TWO]
        assert await kept.rows() == [1, 2]

    async def test_the_engine_is_not_told_of_the_attempts_that_use_it(self, kept: Kept) -> None:
        engine = kept.engine.sync_engine
        async with kept.taken() as session:
            await session.execute(text(ADD_TWO))
            bind = session.sync_session.get_bind()
        async with kept.taken() as session:
            # One view of an engine serves every session a host takes on it.
            assert session.sync_session.get_bind() is bind
        # A host's session is bound to a view of the engine that carries the option, over the same pool.
        assert isinstance(bind, Engine)
        assert (bind is engine, bind.pool is engine.pool) == (False, True)
        assert (bind.get_execution_options().get(ATTEMPT), engine.get_execution_options().get(ATTEMPT)) == (True, None)
        async with kept.own() as session:
            assert session.sync_session.get_bind() is engine


class TestWhatTheRefusalsCost:
    """Counted on a session nobody cancels: what a host's session carries that the application's does not."""

    async def test_an_attempt_puts_one_listener_on_its_session_and_one_on_its_connection(self, kept: Kept) -> None:
        own: dict[str, int] = {}
        taken: dict[str, int] = {}

        async def attempt() -> None:
            for sessions, counted in ((kept.own, own), (kept.taken, taken)):
                async with sessions() as session:
                    connection = (await session.connection()).sync_connection
                    counted["commit"] = listeners(session.sync_session, "before_commit")
                    counted["statement"] = listeners(connection, "before_cursor_execute")

        await run_out_of_reach(attempt)
        assert {name: taken[name] - own[name] for name in own} == {"commit": 1, "statement": 1}
        assert kept.sent == []

    async def test_outside_an_attempt_a_connection_is_not_watched(self, kept: Kept) -> None:
        """Guards the test for a mark: the statistics pass runs in no attempt, and has no caller to be cancelled."""
        async with kept.own() as own, kept.taken() as taken:
            watched = [
                listeners((await session.connection()).sync_connection, "before_cursor_execute")
                for session in (own, taken)
            ]
        assert watched[0] == watched[1]
