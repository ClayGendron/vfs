"""An attempt that a cancellation of its caller does not reach, and that stops once its caller is cancelled.

An attempt is one try of one call's transaction. On SQLite, a caller
that is cancelled must not be cut off in the middle of using its
connection. SQLAlchemy throws such a connection away. In memory the
connection is the database, so the database goes with it. In a file the
connection can be thrown away with a cursor still open, and it then
keeps its write lock until the collector runs, which locks the next
writer out.

So on SQLite each attempt runs in a task of its own, and a caller that
is cancelled waits for its attempt to end before its cancellation is
raised. A caller with more than one canceller is raised the first
cancellation that carries a message, with the others behind it as its
``__context__``. The first canceller that gave a message, as a cancel
scope does, then finds its cancellation on the error raised. A later
one finds its own only behind that error, where it does not always
arrive, and ``run_out_of_reach`` says which cancellers are not served.

An attempt whose caller was cancelled is marked, and a marked attempt
stops. The statement in flight ends, and no other is sent: the next one
is refused before it reaches the database, the ``BEGIN`` of a
transaction among them, as is the first use of a session, before a
connection is checked out, and the commit. The transaction is then
rolled back. So a write that is cancelled before its commit has begun
changes nothing, and one that is cancelled later has landed whole. A
caller cannot know which, and that is so on every engine.

Two things are still sent after a mark. A connection that the pool is
making or checking out has its settings stamped in the pool's own
listener, and a refusal raised there would cost the connection, so a
checkout that has begun sends all its statements. And every rollback is
sent, to a savepoint or of the whole transaction, because the rollbacks
are what unwind the attempt and leave the connection clean.

A mark does not end a wait. An attempt that is waiting for a connection
from its pool, or for its turn on a database that lives in one
connection, is refused when it gets one, and its caller is back then and
not before. On a pool that is the pool's timeout at the latest. An
attempt that waits on a worker thread, as a grep does, ends when the
thread has.

The refusals are two listeners, each put in place once. One is on the
storage's own engine and reads the mark before each statement. The other
is on the class of the storage's sessions and reads it at a session's
first use and at its commit. Outside an attempt there is no mark, so the
statistics pass, which runs in a task of the storage, is refused nothing.

A task copies the context it is started in, so one started inside an
attempt carries that attempt's mark for as long as it runs: a task that
is to outlive its attempt is started outside it, as the statistics pass
is, or sets the mark to ``None`` first.
"""

from __future__ import annotations

import asyncio
import itertools
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import event
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy import Engine
    from sqlalchemy.engine import Connection

T = TypeVar("T")

CANCELLED_ATTEMPT = "the caller of this attempt was cancelled, so the attempt sends nothing more"
"""What a marked attempt is refused with."""


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
    it is cancelled. Once ``attempt`` has ended it raises one of those
    cancellations, the same ``CancelledError`` and not a new one. What
    ``attempt`` returned or raised is then dropped.

    A caller can have two cancellers, such as a time limit and a cancel
    scope. The cancellation raised is the first that carries a message,
    or the first of all when none does. A canceller that knows its
    cancellation by its message, as a cancel scope does, must see it on
    the error itself, and asyncio's own cancellers, a time limit and a
    task group, do not read the message. One cancellation is kept for
    each message, and the others are behind the one raised as its
    ``__context__``, in the order they came.

    Two cancellers are not always both served. A cancel scope takes any
    error that has its message on it or behind it, whatever else is
    pending on the task, and this function cannot know which of two
    cancellers is the outer one. So when a task is cancelled from
    outside, or by a time limit around the scope, and a scope inside it
    is cancelled in the same wait, the scope takes the error and the
    outer canceller gets nothing. The task runs on to its end with
    ``Task.cancelling()`` still 1, and no ``TimeoutError`` is raised,
    where a plain await would have ended the task cancelled.

    What is behind the error raised does not always arrive either.
    Python replaces it when the caller awaits inside a block that is
    handling another error. There only the first cancellation with a
    message is found: a scope that is cancelled after a canceller that
    gave a message of its own does not find its cancellation, and the
    task ends cancelled.
    """
    mark = _Mark()
    cancellations: list[asyncio.CancelledError] = []

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
            # A scope cancels again at every turn of the loop, so one cancellation is kept for each message.
            if all(raised.args != kept.args for kept in cancellations):
                cancellations.append(raised)
    if not cancellations:
        return task.result()
    # Read what the dropped attempt raised, or the loop reports it as never retrieved.
    with suppress(asyncio.CancelledError, Exception):
        task.result()
    # A message is how a canceller knows its own cancellation, so the first that carries one is the one raised.
    first = next((kept for kept in cancellations if kept.args), cancellations[0])
    for kept, later in itertools.pairwise([first, *(kept for kept in cancellations if kept is not first)]):
        kept.__context__ = later
    raise first


# ---------------------------------------------------------------------------
# Refusing a marked attempt
# ---------------------------------------------------------------------------


def refuse_a_marked_attempt() -> None:
    """Raise ``InvalidRequestError`` if the running task belongs to a marked attempt."""
    mark = _MARK.get()
    if mark is not None and mark.cancelled:
        raise InvalidRequestError(CANCELLED_ATTEMPT)


def refuse_statements_of_marked_attempts(engine: Engine) -> None:
    """Have *engine* refuse each statement that a marked attempt asks one of its connections to send.

    The ``BEGIN`` that opens a transaction and the statements of a
    savepoint are refused with the rest. A rollback is let through. The
    statements a pool sends as it makes or checks out a connection do not
    pass this way, and are sent.
    """
    event.listen(engine, "before_cursor_execute", _before_statement)


class AttemptSession(Session):
    """A session that a marked attempt cannot begin to use, and cannot commit.

    The refusal at its first use comes before a connection is checked
    out, so an attempt that was marked before it used its session sends
    nothing. The refusal at the commit is its own because a commit is a
    call of the driver and not a statement. Both raise
    ``InvalidRequestError``.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _before_statement(_connection: Connection, _cursor: object, statement: str, *_sent: object) -> None:
    # A rollback is let through: it is what unwinds the refused attempt and leaves the connection clean.
    if not statement.startswith(_ROLLBACK):
        refuse_a_marked_attempt()


@event.listens_for(AttemptSession, "after_transaction_create")
def _at_first_use(_session: Session, _transaction: object) -> None:
    refuse_a_marked_attempt()


@event.listens_for(AttemptSession, "before_commit")
def _before_commit(_session: Session) -> None:
    refuse_a_marked_attempt()
