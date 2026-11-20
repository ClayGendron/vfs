"""An attempt out of reach of its caller's cancellation: the task, the mark and the refused commit.

Each test runs ``run_out_of_reach`` over an attempt that waits where the
test tells it to, so the cancellation lands at a known point and no test
reads a clock. The sessions are real ones over an in-memory SQLite
database. The same laws on a whole storage are in
``tests/storage/test_cancelled_call.py``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from tests.support.cancelled_callers import collect_what_was_dropped, reports_of_the_loop, turns_of_the_loop
from vfs.storage.backends.database.attempts import CANCELLED_ATTEMPT, AttemptSession, run_out_of_reach

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Engine


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


def rows_of(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT n FROM kept ORDER BY n")).scalars())


@pytest.fixture
def kept(engine: Engine) -> Engine:
    """The shared in-memory engine, holding one table with one row."""
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE kept (n INTEGER)"))
        connection.execute(text("INSERT INTO kept VALUES (1)"))
    return engine


def adding_a_row(session: Session) -> Callable[[], Any]:
    def add() -> None:
        session.execute(text("INSERT INTO kept VALUES (2)"))
        session.commit()

    return add


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


class TestTheMark:
    async def test_a_commit_outside_any_attempt_is_not_refused(self, kept: Engine) -> None:
        with AttemptSession(kept) as session:
            adding_a_row(session)()
        assert rows_of(kept) == [1, 2]

    async def test_a_commit_inside_an_attempt_nobody_cancelled_is_not_refused(self, kept: Engine) -> None:
        with AttemptSession(kept) as session:
            attempt = Waiting(adding_a_row(session))
            attempt.let_go()
            await run_out_of_reach(attempt)
        assert rows_of(kept) == [1, 2]

    async def test_a_marked_attempt_is_refused_at_its_commit(self, kept: Engine) -> None:
        """Guards the mark and the listener: with either gone, the cancelled attempt's row is committed."""
        refusals: list[BaseException] = []
        with AttemptSession(kept) as session:

            def commit() -> None:
                try:
                    adding_a_row(session)()
                except InvalidRequestError as refusal:
                    refusals.append(refusal)
                    raise

            await cancelled_while_it_waits(Waiting(commit))
        assert [str(refusal) for refusal in refusals] == [CANCELLED_ATTEMPT]
        assert rows_of(kept) == [1]

    async def test_a_marked_attempt_is_refused_at_the_release_of_a_savepoint(self, kept: Engine) -> None:
        """A marked attempt stops at the first savepoint it releases and sends nothing after it."""
        refusals: list[BaseException] = []
        with AttemptSession(kept) as session:

            def release() -> None:
                savepoint = session.begin_nested()
                session.execute(text("INSERT INTO kept VALUES (2)"))
                try:
                    savepoint.commit()
                except InvalidRequestError as refusal:
                    refusals.append(refusal)
                    raise

            await cancelled_while_it_waits(Waiting(release))
        assert [str(refusal) for refusal in refusals] == [CANCELLED_ATTEMPT]

    async def test_a_plain_session_commits_inside_a_marked_attempt(self, kept: Engine) -> None:
        """Guards where the listener is registered: on ``Session`` itself it would refuse every session there is."""
        with Session(kept) as session:
            await cancelled_while_it_waits(Waiting(adding_a_row(session)))
        assert rows_of(kept) == [1, 2]

    async def test_the_mark_of_one_attempt_is_not_seen_by_the_next(self, kept: Engine) -> None:
        await cancelled_while_it_waits(Waiting())
        with AttemptSession(kept) as session:
            attempt = Waiting(adding_a_row(session))
            attempt.let_go()
            await run_out_of_reach(attempt)
        assert rows_of(kept) == [1, 2]

    async def test_a_task_started_inside_an_attempt_carries_its_mark(self, kept: Engine) -> None:
        """A task copies the context it is started in, and the mark with it, so its commit is refused too."""
        refusals: list[BaseException] = []
        with AttemptSession(kept) as session:
            started = Waiting()

            async def child() -> None:
                await started()
                try:
                    adding_a_row(session)()
                except InvalidRequestError as refusal:
                    refusals.append(refusal)

            async def attempt() -> None:
                await asyncio.ensure_future(child())

            caller = asyncio.ensure_future(run_out_of_reach(attempt))
            await started.started.wait()
            caller.cancel()
            await turns_of_the_loop()
            started.let_go()
            with pytest.raises(asyncio.CancelledError):
                await caller
        assert [str(refusal) for refusal in refusals] == [CANCELLED_ATTEMPT]
