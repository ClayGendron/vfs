"""What a database that lives in one connection needs.

An in-memory SQLite database exists only while its one connection is
open. Two rules follow from that, and this module holds both.

Calls take turns. One connection cannot run two transactions at once, so
each session holds a lock from the moment it is entered until it is left.

A cancellation does not reach the connection. SQLAlchemy closes a
connection whose user was cancelled in the middle of using it, and here
that would close the database. So each attempt runs in a task of its own,
and a caller that is cancelled waits for its attempt to end before the
cancellation is raised.

An attempt whose caller was cancelled is marked, and a marked attempt
does not commit. It stops when it next releases a savepoint or reaches
its commit, and its transaction is rolled back. An attempt that is marked
while it still waits for its turn sends nothing. An attempt that is
marked after its commit has begun has landed. A cancelled write therefore
means here what it means on a database in a file.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar, cast

from sqlalchemy import event
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

T = TypeVar("T")

CANCELLED_ATTEMPT = "the caller of this attempt was cancelled, so the attempt is not committed"
"""What a marked attempt is refused with, at its turn and at its commit."""


class _Mark:
    """Whether the caller of one attempt has been cancelled."""

    cancelled = False


# The mark of the attempt that the running task belongs to, or None outside any attempt.
_MARK: ContextVar[_Mark | None] = ContextVar("vfs_attempt_mark", default=None)


# ---------------------------------------------------------------------------
# Calls take turns
# ---------------------------------------------------------------------------


class SerializedSession:
    """One session that holds the host lock from the moment it is entered until it is left.

    A session that is never entered takes no lock. Every other attribute is
    the attribute of the session it wraps. If the attempt is already marked
    when its turn comes, entering raises ``InvalidRequestError`` and gives
    the lock back, and nothing is sent to the database.
    """

    def __init__(self, session: AsyncSession, lock: asyncio.Lock) -> None:
        self._session = session
        self._lock = lock

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def __aenter__(self) -> AsyncSession:
        await self._lock.acquire()
        try:
            _refuse_a_marked_attempt()
            return await self._session.__aenter__()
        except BaseException:
            self._lock.release()
            raise

    async def __aexit__(self, *exc_info: object) -> None:
        try:
            await self._session.__aexit__(*exc_info)
        finally:
            self._lock.release()


class SerializedSessions:
    """A session factory for a pool of one connection, where one session runs at a time.

    Two tasks that share one connection would start a transaction inside
    a transaction. Every session this factory makes shares one lock, so the
    second task waits for the first to leave.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._lock = asyncio.Lock()

    def __call__(self) -> AsyncSession:
        return cast("AsyncSession", SerializedSession(self._factory(), self._lock))


def rearm_on_fresh_connection(sync_engine: Engine, rearm: Callable[[], None]) -> None:
    """Call ``rearm`` each time the pool of ``sync_engine`` opens a connection after its first.

    A second connection to an in-memory database is a new and empty
    database. The host passes a ``rearm`` that makes its next call provision
    the schema again.
    """
    fresh = False

    @event.listens_for(sync_engine, "connect")
    def _on_connect(_dbapi_connection, _record) -> None:  # noqa: ANN001
        nonlocal fresh
        if fresh:
            rearm()
        fresh = True


# ---------------------------------------------------------------------------
# A cancellation does not reach the connection
# ---------------------------------------------------------------------------


class OneConnectionSession(Session):
    """A session whose commit is refused once the attempt it belongs to is marked.

    The refusal is an ``InvalidRequestError``, raised before anything is sent
    to the database. SQLAlchemy asks before a commit and before the release
    of a savepoint, so a marked attempt stops at whichever comes first.
    """


@event.listens_for(OneConnectionSession, "before_commit")
def _before_commit(_session: Session) -> None:
    _refuse_a_marked_attempt()


async def run_out_of_reach(attempt: Callable[[], Awaitable[T]]) -> T:
    """Run ``attempt`` in a task that a cancellation of the caller does not enter.

    Return what ``attempt`` returns, and raise what it raises. If the caller
    is cancelled while ``attempt`` runs, ``attempt`` is marked and runs on
    to its end. The caller goes on waiting, however many times it is
    cancelled, and raises one ``CancelledError`` once ``attempt`` has ended.
    What ``attempt`` returned or raised is then dropped.
    """
    mark = _Mark()

    async def marked() -> T:
        # Set here, in the attempt's own task: a task cannot set a variable in another's context.
        _MARK.set(mark)
        return await attempt()

    task = asyncio.ensure_future(marked())
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            mark.cancelled = True
    if not mark.cancelled:
        return task.result()
    with suppress(asyncio.CancelledError, Exception):
        task.result()
    raise asyncio.CancelledError


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _refuse_a_marked_attempt() -> None:
    """Raise ``InvalidRequestError`` if the running task belongs to a marked attempt."""
    mark = _MARK.get()
    if mark is not None and mark.cancelled:
        raise InvalidRequestError(CANCELLED_ATTEMPT)
