"""What the tests of a cancelled caller share: turns of the loop, and what the loop was asked to report.

A test that cancels a caller never waits on a clock. It lets the loop
turn until every task that can run has run, and then looks at where the
caller is.
"""

from __future__ import annotations

import asyncio
import gc
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

# More turns than any chain of tasks these tests start needs to settle.
TURNS = 10


async def turns_of_the_loop() -> None:
    """Let every task that can run do so; a task that waits on something held stays where it is."""
    for _ in range(TURNS):
        await asyncio.sleep(0)


async def collect_what_was_dropped() -> None:
    """Collect every task that nothing holds any more.

    The loop turns first: until it has, the callback that woke the test
    still holds the task the test awaited last, and all that task holds.
    """
    await turns_of_the_loop()
    gc.collect()


@contextmanager
def reports_of_the_loop() -> Iterator[list[dict[str, Any]]]:
    """What the running loop is asked to report as unhandled while the block runs.

    A task that ended with an exception nobody read is reported when it is
    collected, so a test collects inside the block and reads the list after it.
    """
    reports: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: reports.append(context))
    try:
        yield reports
    finally:
        loop.set_exception_handler(handler)
