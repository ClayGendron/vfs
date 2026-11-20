"""An attempt that a cancellation of its caller does not reach.

An attempt is one try of one call's transaction. On SQLite, a caller
that is cancelled must not be cut off in the middle of using its
connection. SQLAlchemy throws such a connection away. In memory the
connection is the database, so the database goes with it. In a file the
connection can be thrown away with a cursor still open, and it then
keeps its write lock until the collector runs, which locks the next
writer out.

So each attempt runs in a task of its own, and a caller that is
cancelled waits for its attempt to end before the cancellation is raised.

An attempt whose caller was cancelled is marked, and a marked attempt
does not commit. It stops when it next releases a savepoint or reaches
its commit, and its transaction is rolled back. An attempt that is
marked after its commit has begun has landed. A caller that is cancelled
during a write therefore cannot know whether the write landed, and that
is so on every engine.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import event
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")

CANCELLED_ATTEMPT = "the caller of this attempt was cancelled, so the attempt is not committed"
"""What a marked attempt is refused with."""


class _Mark:
    """Whether the caller of one attempt has been cancelled."""

    cancelled = False


# The mark of the attempt that the running task belongs to, or None outside any attempt.
_MARK: ContextVar[_Mark | None] = ContextVar("vfs_attempt_mark", default=None)


# ---------------------------------------------------------------------------
# Running an attempt
# ---------------------------------------------------------------------------


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
# Refusing a marked attempt
# ---------------------------------------------------------------------------


def refuse_a_marked_attempt() -> None:
    """Raise ``InvalidRequestError`` if the running task belongs to a marked attempt."""
    mark = _MARK.get()
    if mark is not None and mark.cancelled:
        raise InvalidRequestError(CANCELLED_ATTEMPT)


class AttemptSession(Session):
    """A session whose commit is refused once the attempt it belongs to is marked.

    The refusal is an ``InvalidRequestError``, raised before anything is sent
    to the database. SQLAlchemy asks before a commit and before the release
    of a savepoint, so a marked attempt stops at whichever comes first.
    """


@event.listens_for(AttemptSession, "before_commit")
def _before_commit(_session: Session) -> None:
    refuse_a_marked_attempt()
