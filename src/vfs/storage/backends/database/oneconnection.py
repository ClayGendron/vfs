"""What a database that lives in one connection needs.

An in-memory SQLite database exists only while its one connection is
open. Two rules follow from that, and this module holds both.

Calls take turns. One connection cannot run two transactions at once, so
each session holds a lock from the moment it is entered until it is left.
An attempt that was marked while it waited for its turn is refused at
the first use of its session, so it sends nothing and gives its turn up.

A second connection is a new database. When the pool opens one, the
host is told, so that its next call provisions the schema again.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import event

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Calls take turns
# ---------------------------------------------------------------------------


class SerializedSession:
    """One session that holds the host lock from the moment it is entered until it is left.

    A session that is never entered takes no lock. Every other attribute is
    the attribute of the session it wraps. The lock is given back if that
    session fails to enter, and when it has been left, whatever it raised.
    """

    def __init__(self, session: AsyncSession, lock: asyncio.Lock) -> None:
        self._session = session
        self._lock = lock

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def __aenter__(self) -> AsyncSession:
        await self._lock.acquire()
        try:
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

    def __init__(self, factory: Callable[[], AsyncSession]) -> None:
        self._factory = factory
        self._lock = asyncio.Lock()

    def __call__(self) -> AsyncSession:
        return cast("AsyncSession", SerializedSession(self._factory(), self._lock))


# ---------------------------------------------------------------------------
# A second connection is a new database
# ---------------------------------------------------------------------------


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
