"""A proof that blocking work left the event loop, counted in loop turns.

A ticker task counts turns of the loop. A double standing in for the
blocking work calls :meth:`LoopTicker.hop` from the worker thread, which
returns only once the count has advanced. Work run inline on the loop
calls the hop from the loop's own thread, where the loop cannot turn,
and the hop says so at once. The test then asserts how many hops ran.
No sleep, no elapsed-time assertion and no timeout anywhere: the run's
deadline bounds a wait that never ends.
"""

from __future__ import annotations

import asyncio
import threading
import time


class LoopTicker:
    """Counts event-loop turns while blocking hops wait for the count to move."""

    def __init__(self) -> None:
        self.ticks = 0
        self.hops = 0
        self._task: asyncio.Task[None] | None = None
        self._loop_thread: int | None = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(0.001)
            self.ticks += 1

    def start(self) -> LoopTicker:
        self._loop_thread = threading.get_ident()
        self._task = asyncio.ensure_future(self._run())
        return self

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def hop(self) -> None:
        """From a worker thread: block until the loop has turned at least once more."""
        if threading.get_ident() == self._loop_thread:
            msg = "a blocking hop ran on the loop's own thread: the work ran inline"
            raise AssertionError(msg)
        seen = self.ticks
        while self.ticks == seen:
            time.sleep(0.0005)
        self.hops += 1
