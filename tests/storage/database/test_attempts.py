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
import gc
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.event import registry
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.support.cancelled_callers import (
    IN_MEMORY,
    collect_what_was_dropped,
    reports_of_the_loop,
    turns_of_the_loop,
)
from vfs.storage.backends.database.attempts import (
    CANCELLED_ATTEMPT,
    AttemptSession,
    refuse_statements_of_marked_attempts,
    run_out_of_reach,
    run_to_its_end,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine

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


async def cancelled_with(messages: list[str | None]) -> asyncio.CancelledError:
    """Cancel the caller of an attempt that waits once for each of *messages*, let it go, and return what it raised."""
    attempt = Waiting()
    caller = asyncio.ensure_future(run_out_of_reach(attempt))
    await attempt.started.wait()
    for message in messages:
        caller.cancel(message)
        await turns_of_the_loop()
    attempt.let_go()
    with pytest.raises(asyncio.CancelledError) as raised:
        await caller
    return raised.value


def chain_of(cancellation: BaseException) -> list[tuple[Any, ...]]:
    """The arguments of *cancellation* and of each error behind it, as a canceller that looks for its own reads them."""
    found: list[tuple[Any, ...]] = []
    error: BaseException | None = cancellation
    while error is not None:
        found.append(error.args)
        error = error.__context__
    return found


@pytest.fixture
def thrown(monkeypatch: pytest.MonkeyPatch) -> list[BaseException]:
    """Every cancellation that the wait of a caller is thrown, in order, as the very errors."""
    seen: list[BaseException] = []
    wait = asyncio.wait

    async def recording(tasks: Any) -> Any:
        try:
            return await wait(tasks)
        except asyncio.CancelledError as error:
            seen.append(error)
            raise

    monkeypatch.setattr(asyncio, "wait", recording)
    return seen


def failing(error: BaseException) -> Callable[[], Any]:
    def fail() -> Any:
        raise error

    return fail


def listeners(target: Any, name: str) -> int:
    """How many listeners the event *name* has on *target*, those of its class and its engine among them."""
    return len(list(getattr(target.dispatch, name)))


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


class Kept:
    """An in-memory database of one table with one row, as a storage on SQLite sets its engine up.

    ``sessions`` makes the sessions of the storage. ``sent`` and ``checkouts``
    hold every statement and every checkout the database saw since this was made.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        refuse_statements_of_marked_attempts(engine.sync_engine)
        self.sessions = async_sessionmaker(engine, sync_session_class=AttemptSession)
        self.sent: list[str] = []
        self.checkouts: list[object] = []
        event.listen(engine.sync_engine, "before_cursor_execute", lambda *sent: self.sent.append(sent[2]))
        event.listen(engine.sync_engine, "checkout", lambda *checkout: self.checkouts.append(checkout[0]))

    async def rows(self) -> list[int]:
        async with self.sessions() as session:
            return list((await session.execute(text("SELECT n FROM kept ORDER BY n"))).scalars())


@pytest.fixture
async def kept() -> AsyncIterator[Kept]:
    engine = create_async_engine(IN_MEMORY)
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

    async def test_the_error_raised_is_the_very_one_the_caller_was_cancelled_with(
        self, thrown: list[BaseException]
    ) -> None:
        """Guards the raise: a new error with the same message is not the one a canceller holds on to."""
        raised = await cancelled_with(["mine"])
        assert [raised] == thrown

    async def test_a_caller_cancelled_twice_is_raised_the_first_cancellation(self, thrown: list[BaseException]) -> None:
        """Guards which cancellation is kept: the last one would hide the canceller that came first."""
        raised = await cancelled_with(["first", "second"])
        assert raised is thrown[0]
        assert raised.args == ("first",)

    async def test_a_cancellation_with_a_message_is_raised_ahead_of_an_earlier_one_with_none(
        self, thrown: list[BaseException]
    ) -> None:
        """A canceller that knows its cancellation by its message finds it on the error raised.

        Guards which cancellation is raised: a time limit cancels with no message and a cancel
        scope with its own, and what is behind the error raised is lost when the caller is handling an error.
        """
        raised = await cancelled_with([None, "the scope's"])
        assert raised is thrown[1]
        assert raised.__context__ is thrown[0]
        assert chain_of(raised) == [("the scope's",), ()]

    async def test_a_caller_cancelled_with_no_message_at_all_is_raised_the_first(
        self, thrown: list[BaseException]
    ) -> None:
        raised = await cancelled_with([None, None])
        assert raised is thrown[0]
        assert chain_of(raised) == [()]

    async def test_three_cancellers_are_one_behind_another_in_the_order_they_came(
        self, thrown: list[BaseException]
    ) -> None:
        """Guards the whole chain: each later cancellation is behind the one before it, and none is left out."""
        raised = await cancelled_with(["first", "second", "third"])
        assert raised is thrown[0]
        assert raised.__context__ is thrown[1]
        assert chain_of(raised) == [("first",), ("second",), ("third",)]

    async def test_the_cancellations_behind_the_one_raised_keep_the_order_they_came_in(self) -> None:
        """Guards the order: only the first cancellation with a message moves, to the front."""
        assert chain_of(await cancelled_with([None, "first", "second"])) == [("first",), (), ("second",)]

    async def test_a_canceller_that_cancels_again_and_again_is_behind_the_first_once(self) -> None:
        """Guards the test for a message already kept: a scope cancels at every turn of the loop while it waits."""
        raised = await cancelled_with(["a scope's", "a scope's", "another's", "a scope's", "another's"])
        assert chain_of(raised) == [("a scope's",), ("another's",)]

    async def test_a_caller_cancelled_once_is_raised_a_cancellation_with_nothing_behind_it(self) -> None:
        assert chain_of(await cancelled_with(["mine"])) == [("mine",)]

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

    async def test_a_caller_whose_attempt_was_cancelled_too_is_raised_its_own_cancellation(self) -> None:
        """Guards the read of a dropped attempt that ended cancelled: its ``CancelledError`` is not the caller's."""
        with reports_of_the_loop() as reports:
            raised = await cancelled_while_it_waits(Waiting(failing(asyncio.CancelledError("the attempt's"))), "mine")
            await collect_what_was_dropped()
        assert (raised.args, reports) == (("mine",), [])

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
        """Guards the test for a mark: the statistics pass runs in no attempt, and is refused nothing."""
        async with kept.sessions() as session:
            await session.execute(text(ADD_TWO))
            await session.commit()
        assert kept.sent == [ADD_TWO]
        assert await kept.rows() == [1, 2]

    async def test_a_session_inside_an_attempt_sends_and_commits(self, kept: Kept) -> None:
        async def attempt() -> None:
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await session.commit()

        await run_out_of_reach(attempt)
        assert kept.sent == [ADD_TWO]
        assert await kept.rows() == [1, 2]

    async def test_a_caller_that_was_cancelled_carries_no_mark_of_its_own(self, kept: Kept) -> None:
        """Guards where the mark is set: in the caller's context it would refuse whatever the caller does next."""

        async def caller() -> None:
            with pytest.raises(asyncio.CancelledError):
                await run_out_of_reach(attempt)
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await session.commit()

        attempt = Waiting()
        task = asyncio.ensure_future(caller())
        await attempt.started.wait()
        task.cancel()
        await turns_of_the_loop()
        attempt.let_go()
        await task
        assert await kept.rows() == [1, 2]

    async def test_the_mark_of_one_attempt_is_not_seen_by_the_next(self, kept: Kept) -> None:
        await cancelled_while_it_waits(Waiting())

        async def attempt() -> None:
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await session.commit()

        await run_out_of_reach(attempt)
        assert await kept.rows() == [1, 2]


class TestAMarkedAttempt:
    async def test_it_is_refused_at_its_next_statement(self, kept: Kept) -> None:
        """Guards the listener on the engine: without it every statement of a marked attempt is sent."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.sessions() as session:
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
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.commit()

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [ADD_TWO])
        assert await kept.rows() == [1]

    async def test_it_stays_marked_when_its_caller_is_cancelled_again(self, kept: Kept) -> None:
        """Guards the mark under a second cancellation: taken off again, the write of a caller cancelled twice lands."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.commit()

        caller = asyncio.ensure_future(run_out_of_reach(attempt))
        await gate.started.wait()
        for message in ("first", "second"):
            caller.cancel(message)
            await turns_of_the_loop()
        gate.let_go()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert await kept.rows() == [1]

    async def test_it_is_refused_the_first_use_of_a_session_and_checks_no_connection_out(self, kept: Kept) -> None:
        """Guards the refusal at a session's first use: without it a checkout stamps its settings before the stop."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.sessions() as session:
                await gate()
                await session.execute(text(ADD_TWO))

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent, kept.checkouts) == (CANCELLED_ATTEMPT, [], [])

    async def test_it_is_refused_inside_a_savepoint_and_is_let_roll_back_to_it(self, kept: Kept) -> None:
        """Guards the rollback that is let through: refused, the attempt cannot unwind and its connection is lost."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.sessions() as session:
                connection = await session.connection()
                await connection.execute(text(ADD_TWO))
                async with connection.begin_nested():
                    await gate()
                    await connection.execute(text(ADD_THREE))

        refusal = await cancelled_at(gate, attempt)
        assert str(refusal) == CANCELLED_ATTEMPT
        assert kept.sent == [ADD_TWO, "SAVEPOINT sa_savepoint_1", "ROLLBACK TO SAVEPOINT sa_savepoint_1"]
        assert await kept.rows() == [1]

    async def test_a_task_it_started_carries_its_mark(self, kept: Kept) -> None:
        """A task copies the context it is started in, and the mark with it, so its statements are refused too."""
        gate = Waiting()

        async def child() -> None:
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.execute(text(ADD_THREE))

        async def attempt() -> None:
            await asyncio.ensure_future(child())

        refusal = await cancelled_at(gate, attempt)
        assert (str(refusal), kept.sent) == (CANCELLED_ATTEMPT, [ADD_TWO])


class TestWhatIsNotTheStoragesOwn:
    async def test_another_engine_and_its_sessions_are_refused_nothing_inside_a_marked_attempt(
        self, kept: Kept
    ) -> None:
        """Guards where the two listeners are put: on every engine or every session class, they would stop this one."""
        other = create_async_engine(IN_MEMORY)
        sessions = async_sessionmaker(other)
        gate = Waiting()

        async def attempt() -> list[int]:
            async with sessions() as session:
                await gate()
                await session.execute(text("CREATE TABLE kept (n INTEGER)"))
                await session.execute(text(ADD_TWO))
                await session.commit()
                return list((await session.execute(text("SELECT n FROM kept"))).scalars())

        assert await cancelled_at(gate, attempt) is None
        async with sessions() as session:
            assert list((await session.execute(text("SELECT n FROM kept"))).scalars()) == [2]
        await other.dispose()
        assert kept.sent == []


class TestWhatTheRefusalsCost:
    """Counted on calls that nobody cancels: the refusals are two listeners put in place once."""

    CALLS = 200

    async def test_a_session_and_its_connection_are_given_no_listener_of_their_own(self, kept: Kept) -> None:
        """Guards where the listeners are put: one more for each session or transaction is work on every call."""
        engine = kept.engine.sync_engine
        own: dict[str, int] = {}

        async def call() -> None:
            async with kept.sessions() as session:
                connection = (await session.connection()).sync_connection
                await session.execute(text("SELECT 1"))
                own["statement"] = listeners(connection, "before_cursor_execute") - on_the_engine
                own["commit"] = listeners(session.sync_session, "before_commit")
                own["first use"] = listeners(session.sync_session, "after_transaction_create")

        on_the_engine = listeners(engine, "before_cursor_execute")
        await run_out_of_reach(call)
        gc.collect()
        listened = len(registry._key_to_collection)
        for _ in range(self.CALLS):
            await run_out_of_reach(call)
        gc.collect()
        # The listener on the engine and the two on the class of the sessions are all there is.
        assert own == {"statement": 0, "commit": 1, "first use": 1}
        assert (listeners(engine, "before_cursor_execute"), len(registry._key_to_collection)) == (
            on_the_engine,
            listened,
        )
        assert len(kept.sent) == self.CALLS + 1


class TestAnAttemptRunToItsEnd:
    async def test_it_commits_whatever_its_caller_does(self, kept: Kept) -> None:
        """Guards ``run_to_its_end``: marked as ``run_out_of_reach`` marks, a record after its change is lost."""
        gate = Waiting()

        async def attempt() -> None:
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.commit()

        caller = asyncio.ensure_future(run_to_its_end(attempt))
        await gate.started.wait()
        for message in ("first", "second"):
            caller.cancel(message)
            await turns_of_the_loop()
        gate.let_go()
        with pytest.raises(asyncio.CancelledError) as raised:
            await caller
        assert (chain_of(raised.value), await kept.rows()) == ([("first",), ("second",)], [1, 2])

    async def test_inside_a_marked_attempt_it_still_runs_to_its_end(self, kept: Kept) -> None:
        """Guards the mark it clears: a task copies its starter's mark, and a marked starter's record is refused."""
        gate = Waiting()

        async def record() -> None:
            async with kept.sessions() as session:
                await session.execute(text(ADD_TWO))
                await gate()
                await session.commit()

        refusal = await cancelled_at(gate, lambda: run_to_its_end(record))
        assert (refusal, await kept.rows()) == (None, [1, 2])

    async def test_the_caller_gets_what_it_returns_and_what_it_raises(self) -> None:
        attempt = Waiting(then=lambda: "answered")
        attempt.let_go()
        assert await run_to_its_end(attempt) == "answered"
        failed = Waiting(then=failing(LookupError("no row")))
        failed.let_go()
        with pytest.raises(LookupError, match="no row"):
            await run_to_its_end(failed)
