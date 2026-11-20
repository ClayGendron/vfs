"""What a database that lives in one connection needs: sessions that take turns, and a re-arm on a new connection.

The sessions are real ones over an in-memory SQLite database, which is
the database this module exists for.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.support.cancelled_callers import turns_of_the_loop
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.attempts import CANCELLED_ATTEMPT, run_out_of_reach
from vfs.storage.backends.database.oneconnection import (
    SerializedSession,
    SerializedSessions,
    rearm_on_fresh_connection,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine

IN_MEMORY = "sqlite+aiosqlite://"


@pytest.fixture
async def one_connection() -> AsyncIterator[AsyncEngine]:
    """An engine over an in-memory database, which SQLAlchemy serves through one connection."""
    engine = create_async_engine(IN_MEMORY)
    yield engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# Calls take turns
# ---------------------------------------------------------------------------


class TestCallsTakeTurns:
    async def test_failed_session_enter_releases_the_host_lock(self) -> None:
        # A session whose enter fails must not leave the host lock held —
        # that would deadlock every later op on the storage.
        class _ExplodingSession:
            async def __aenter__(self) -> AsyncSession:
                raise RuntimeError("enter failed")

            async def __aexit__(self, *exc_info: object) -> None: ...

        lock = asyncio.Lock()
        session = SerializedSession(cast("AsyncSession", _ExplodingSession()), lock)
        with pytest.raises(RuntimeError, match="enter failed"):
            async with session:
                pass
        assert lock.locked() is False

    async def test_a_session_that_is_never_entered_takes_no_lock(self, one_connection: AsyncEngine) -> None:
        lock = asyncio.Lock()
        session = SerializedSession(AsyncSession(one_connection), lock)
        # Every other attribute is the wrapped session's: the bind is read with no lock taken.
        assert session.get_bind() is one_connection.sync_engine
        assert lock.locked() is False

    async def test_the_lock_is_held_until_the_session_has_been_left(self, one_connection: AsyncEngine) -> None:
        """Guards ``__aexit__``: a lock given back before the session's own exit lets the next call in too soon."""
        lock = asyncio.Lock()
        held_as_the_exit_ended: list[bool] = []

        class _LeavingSession(AsyncSession):
            async def __aexit__(self, type_: Any, value: Any, traceback: Any) -> None:
                await super().__aexit__(type_, value, traceback)
                held_as_the_exit_ended.append(lock.locked())

        async with SerializedSession(_LeavingSession(one_connection), lock) as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
            assert lock.locked() is True
        assert held_as_the_exit_ended == [True]
        assert lock.locked() is False

    async def test_a_second_session_of_one_factory_waits_for_the_first_to_leave(
        self, one_connection: AsyncEngine
    ) -> None:
        """Guards the factory's one lock: with a lock for each session, the second enters beside the first."""
        sessions = SerializedSessions(async_sessionmaker(one_connection))
        order: list[str] = []

        async def behind() -> None:
            async with sessions():
                order.append("the second entered")

        async with sessions():
            waiting = asyncio.ensure_future(behind())
            await turns_of_the_loop()
            order.append("the first is leaving")
        await waiting
        assert order == ["the first is leaving", "the second entered"]

    async def test_an_attempt_marked_while_it_waits_its_turn_enters_no_session_and_gives_the_lock_back(
        self, one_connection: AsyncEngine
    ) -> None:
        """Guards ``__aenter__``: the refusal at the turn, and the lock it must give back when it refuses."""
        lock = asyncio.Lock()
        checked_out: list[object] = []
        event.listen(one_connection.sync_engine, "checkout", lambda *connection: checked_out.append(connection))
        entered: list[AsyncSession] = []
        refusals: list[str] = []

        async def attempt() -> None:
            try:
                async with SerializedSession(AsyncSession(one_connection), lock) as session:
                    entered.append(session)
                    await session.execute(text("SELECT 1"))
            except InvalidRequestError as refusal:
                refusals.append(str(refusal))
                raise

        await lock.acquire()
        behind = asyncio.ensure_future(run_out_of_reach(attempt))
        await turns_of_the_loop()
        behind.cancel()
        await turns_of_the_loop()
        lock.release()
        with pytest.raises(asyncio.CancelledError):
            await behind
        assert (entered, checked_out, refusals) == ([], [], [CANCELLED_ATTEMPT])
        assert lock.locked() is False


# ---------------------------------------------------------------------------
# A second connection is a new database
# ---------------------------------------------------------------------------


class TestASecondConnectionIsANewDatabase:
    def test_the_first_connection_does_not_re_arm_and_the_next_one_does(self, engine: Engine) -> None:
        """Guards the listener: one that never calls ``rearm`` leaves a host serving an empty database as ready."""
        calls: list[str] = []
        rearm_on_fresh_connection(engine, lambda: calls.append("re-armed"))
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            first = list(calls)
            connection.invalidate()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        assert (first, calls) == ([], ["re-armed"])

    async def test_replacement_connection_re_arms_first_touch(self) -> None:
        # A :memory: database lives inside its one connection: a re-minted
        # connection is empty, and serving off the stale latch is a lie.
        storage = DatabaseStorage(url="sqlite+aiosqlite:///:memory:")
        assert (await storage.first_touch()).success is True
        host = storage._host
        assert host._ready is True
        async with host.engine.connect() as conn:
            await conn.invalidate()
        async with host.engine.connect() as conn:  # checkout mints the replacement
            await conn.execute(text("SELECT 1"))
        assert host._ready is False
        result = await storage.stat(path=Path("/"))  # next op re-provisions
        assert result.success is True
        assert result.observations[0].kind == "directory"
        await storage.close()
