"""Concurrency seams — named points where tests stage rival writers.

The race windows the concurrency pins must reach — after a verb's
committed-state snapshot, before its mutation statements — are not
addressable through the public surface: nothing observable separates
them. Each such window declares a named seam, and a test installs an
async handler on it to commit a rival mid-window, then drives the real
public verb — retry, classification, and orchestration are exercised,
never mirrored. With no handler installed a seam is a no-op await, the
production behavior.

    with seams.installed("write:before-apply", rival):
        result = await storage.write(entries=[mine])

The same shape as the prior art this design was ratified against:
Postgres ``INJECTION_POINT`` markers, SQLite ``sqlite3FaultSim`` —
inert markers owned by the code under test, behavior supplied by the
harness at runtime.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

Handler = Callable[[], Awaitable[None]]

_handlers: dict[str, Handler] = {}


# ---------------------------------------------------------------------------
# Seam points and handler installation
# ---------------------------------------------------------------------------


async def seam(name: str) -> None:
    """Run the handler installed on *name*, if any — a no-op in production.

    A handler sees the calling verb frozen mid-window; it runs on the
    same loop, so anything it awaits (a rival verb on its own session)
    completes before the caller resumes. Handlers that drive a rival
    through the same seam's verb must uninstall themselves first —
    the seam itself takes no reentrancy position.
    """
    handler = _handlers.get(name)
    if handler is not None:
        await handler()


def install(name: str, handler: Handler) -> None:
    """Install *handler* on seam *name*, replacing any current one."""
    _handlers[name] = handler


def clear(name: str) -> None:
    """Remove the handler on seam *name*; absent is fine."""
    _handlers.pop(name, None)


@contextmanager
def installed(name: str, handler: Handler) -> Iterator[None]:
    """Install *handler* on *name* for the block, clearing on exit."""
    install(name, handler)
    try:
        yield
    finally:
        clear(name)
