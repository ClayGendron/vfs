"""A proof that blocking work left the event loop, counted in loop turns.

A ticker task counts turns of the loop. A double standing in for the
blocking work calls :meth:`LoopTicker.hop` from the worker thread, which
returns only once the count has advanced: if the work had run inline on
the loop, the loop could not turn, the count would never move, and the
hop would time out. The test then asserts how many hops ran. No sleep
and no elapsed-time assertion anywhere; the timeout is a liveness bound.
"""

from __future__ import annotations

import asyncio
import time


class LoopTicker:
    """Counts event-loop turns while blocking hops wait for the count to move."""

    def __init__(self) -> None:
        self.ticks = 0
        self.hops = 0
        self._task: asyncio.Task[None] | None = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(0.001)
            self.ticks += 1

    def start(self) -> LoopTicker:
        self._task = asyncio.ensure_future(self._run())
        return self

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def hop(self, timeout: float = 5.0) -> None:
        """From a worker thread: block until the loop has turned at least once more."""
        seen = self.ticks
        deadline = time.monotonic() + timeout
        while self.ticks == seen:
            if time.monotonic() > deadline:
                msg = "the loop never turned during a blocking hop: the work ran inline"
                raise AssertionError(msg)
            time.sleep(0.0005)
        self.hops += 1
