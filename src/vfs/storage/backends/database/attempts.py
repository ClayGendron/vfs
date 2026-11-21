"""An attempt that a cancellation of its caller does not reach, and that stops once its caller is cancelled.

An attempt is one try of one call's transaction. On SQLite, a caller
that is cancelled must not be cut off in the middle of using its
connection. SQLAlchemy throws such a connection away. In memory the
connection is the database, so the database goes with it. In a file the
connection can be thrown away with a cursor still open, and it then
keeps its write lock until the collector runs, which locks the next
writer out.

So on every SQLite storage each attempt runs in a task of its own, and a
caller that is cancelled waits for its attempt to end before its
cancellation is raised. The storage may have built its engine or been
handed its sessions, and its database may be in memory or in a file.

An attempt whose caller was cancelled is marked, and a marked attempt
stops. The statement in flight ends, and no other is sent: the next one
is refused before it reaches the database, the ``BEGIN`` of a
transaction among them, as is the entry of a session, and the commit.
The transaction is then rolled back. So a write that is cancelled before its
commit has begun changes nothing, and one that is cancelled later has
landed whole. A caller cannot know which, and that is so on every engine.

Two things are still sent after a mark. A connection that the pool is
checking out has its settings stamped in the pool's own listener, and a
refusal raised there would cost the connection, so a checkout that has
begun sends all its statements. And every rollback is sent, to a
savepoint or of the whole transaction, because the rollbacks are what
unwind the attempt and leave the connection clean.

The refusals belong to the sessions a host takes for its attempts, and
nothing is left on what outlives them. Such a session is bound to a view
of its engine that carries an option, and the host's own listener at the
begin of a transaction tells this module of each connection that carries
it. The engine, its pool and a session the application makes for itself
are given no listener, and that session is refused nothing, even inside
a marked attempt.

A task copies the context it is started in, so one started inside an
attempt carries that attempt's mark for as long as it runs: a task that
is to outlive its attempt is started outside it, as the statistics pass
is, or sets the mark to ``None`` first.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar, cast

from sqlalchemy import Engine, event
from sqlalchemy.exc import InvalidRequestError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

T = TypeVar("T")

CANCELLED_ATTEMPT = "the caller of this attempt was cancelled, so the attempt sends nothing more"
"""What a marked attempt is refused with."""

ATTEMPT = "vfs_attempt"
"""The execution option on every connection of a session that a host took for an attempt."""


class _Mark:
    """Whether the caller of one attempt has been cancelled."""

    cancelled = False


# The mark of the attempt that the running task belongs to, or None outside any attempt.
_MARK: ContextVar[_Mark | None] = ContextVar("vfs_attempt_mark", default=None)

# How every statement that undoes work begins: the rollback to a savepoint is the one SQLAlchemy sends as a statement.
_ROLLBACK = "ROLLBACK"


# ---------------------------------------------------------------------------
# Running an attempt
# ---------------------------------------------------------------------------


async def run_out_of_reach(attempt: Callable[[], Awaitable[T]]) -> T:
    """Run ``attempt`` in a task that a cancellation of the caller does not enter.

    Return what ``attempt`` returns, and raise what it raises. If the caller
    is cancelled while ``attempt`` runs, ``attempt`` is marked and runs on
    until its next refusal. The caller goes on waiting, however many times
    it is cancelled. Once ``attempt`` has ended it raises the first of those
    cancellations, the same ``CancelledError`` and not a new one, so a
    canceller that knows its own cancellation by its message still does.
    What ``attempt`` returned or raised is then dropped.
    """
    mark = _Mark()
    cancellation: asyncio.CancelledError | None = None

    async def marked() -> T:
        # Set here, in the attempt's own task: a task cannot set a variable in another's context.
        _MARK.set(mark)
        return await attempt()

    task = asyncio.ensure_future(marked())
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError as raised:
            mark.cancelled = True
            cancellation = cancellation or raised
    if cancellation is None:
        return task.result()
    # Read what the dropped attempt raised, or the loop reports it as never retrieved.
    with suppress(asyncio.CancelledError, Exception):
        task.result()
    raise cancellation


# ---------------------------------------------------------------------------
# Refusing a marked attempt
# ---------------------------------------------------------------------------


def refuse_a_marked_attempt() -> None:
    """Raise ``InvalidRequestError`` if the running task belongs to a marked attempt."""
    mark = _MARK.get()
    if mark is not None and mark.cancelled:
        raise InvalidRequestError(CANCELLED_ATTEMPT)


def attempt_begins(connection: Connection) -> None:
    """Refuse each statement that *connection* is asked to send once its attempt is marked.

    The host calls this from its own listener at the begin of every
    transaction on its engine, before it sends the ``BEGIN``, so the
    ``BEGIN`` of a marked attempt is refused as well. Only a connection
    of a session the host took carries ``ATTEMPT``, and only inside an
    attempt is there a mark to watch, so any other connection is left as
    it is. The watch is a listener on the connection alone, which ends
    with its transaction.
    """
    mark = _MARK.get()
    if mark is None or not connection.get_execution_options().get(ATTEMPT):
        return

    def before_each_statement(_connection: Connection, _cursor: object, statement: str, *_sent: object) -> None:
        # A rollback is let through: it is what unwinds the refused attempt and leaves the connection clean.
        if mark.cancelled and not statement.startswith(_ROLLBACK):
            raise InvalidRequestError(CANCELLED_ATTEMPT)

    event.listen(connection, "before_cursor_execute", before_each_statement)


class AttemptSession:
    """One session that a host took for an attempt.

    Entering it refuses a marked attempt before a connection is checked
    out, binds the session to the host's view of its engine, so that each
    of its transactions is told to ``attempt_begins``, and has its commit
    refused once the attempt is marked. Every other attribute is the
    attribute of the session it wraps.
    """

    def __init__(self, session: AsyncSession, views: dict[Engine, Engine]) -> None:
        self._session = session
        self._views = views

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def __aenter__(self) -> AsyncSession:
        refuse_a_marked_attempt()
        session = self._session.sync_session
        bind = session.bind
        if isinstance(bind, Engine):
            # One view for each engine, made once: the same pool, and the option on each connection.
            view = self._views.get(bind)
            if view is None:
                view = self._views[bind] = bind.execution_options(**{ATTEMPT: True})
            session.bind = view
        event.listen(session, "before_commit", _before_commit)
        return await self._session.__aenter__()

    async def __aexit__(self, *exc_info: object) -> None:
        await self._session.__aexit__(*exc_info)


class AttemptSessions:
    """A session factory whose sessions are ``AttemptSession``, over the factory a host built or was handed."""

    def __init__(self, factory: Callable[[], AsyncSession]) -> None:
        self._factory = factory
        self._views: dict[Engine, Engine] = {}

    def __call__(self) -> AsyncSession:
        return cast("AsyncSession", AttemptSession(self._factory(), self._views))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _before_commit(_session: Session) -> None:
    refuse_a_marked_attempt()
