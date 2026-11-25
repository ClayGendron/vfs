"""What today's kernel keeps of a storage whose ``close`` outlives ``close_timeout``, and of one whose close is cancelled.

The spec's decision 19 says a close that is cut short, "by its timeout or by a cancellation, keeps the
store, as it keeps a storage (``base.py:559-565``)", so that a second ``close()`` finishes it. This runs
today's ``AsyncVirtualFileSystem.close`` over a storage whose ``close`` can be held, and counts how many
times the storage's ``close`` is entered by a first and a second ``close()`` of the kernel:

- ``timeout``: the storage's close outlives ``close_timeout``;
- ``cancelled``: the task that awaits the kernel's close is cancelled while the storage's close runs.

It then shows the arithmetic the spec's SQLite ruling brings: a flush that waits behind a held writer
for four tries of ``busy_timeout`` against the kernel's default ``close_timeout``.

    uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_close_timeout.py
"""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from vfs import AsyncVirtualFileSystem, InMemoryStorage


class SlowToClose(InMemoryStorage):
    """An in-memory storage whose close waits for ``release`` the first time it is entered."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = 0
        self.finished = 0
        self.release = asyncio.Event()

    async def close(self) -> None:
        self.entered += 1
        if self.entered == 1:
            await self.release.wait()
        await super().close()
        self.finished += 1


async def timeout_case() -> dict[str, Any]:
    storage = SlowToClose()
    fs = AsyncVirtualFileSystem(storage=storage, close_timeout=0.05)
    await fs.stat("/")
    first: str
    try:
        await fs.close()
        first = "returned"
    except BaseException as exc:  # noqa: BLE001
        first = type(exc).__name__
    entered_after_first = storage.entered
    storage.release.set()
    second: str
    try:
        await fs.close()
        second = "returned"
    except BaseException as exc:  # noqa: BLE001
        second = type(exc).__name__
    return {
        "case": "the storage's close outlives close_timeout",
        "first_close": first,
        "storage_close_entered_by_first": entered_after_first,
        "second_close": second,
        "storage_close_entered_in_all": storage.entered,
        "storage_close_finished": storage.finished,
    }


async def cancelled_case() -> dict[str, Any]:
    storage = SlowToClose()
    fs = AsyncVirtualFileSystem(storage=storage, close_timeout=30.0)
    await fs.stat("/")
    task = asyncio.create_task(fs.close())
    await asyncio.sleep(0.05)
    task.cancel()
    first: str
    try:
        await task
        first = "returned"
    except BaseException as exc:  # noqa: BLE001
        first = type(exc).__name__
    entered_after_first = storage.entered
    storage.release.set()
    await fs.close()
    return {
        "case": "the kernel's close is cancelled",
        "first_close": first,
        "storage_close_entered_by_first": entered_after_first,
        "second_close": "returned",
        "storage_close_entered_in_all": storage.entered,
        "storage_close_finished": storage.finished,
    }


async def main() -> None:
    default = inspect.signature(AsyncVirtualFileSystem.__init__).parameters["close_timeout"].default
    payload = {
        "script": "probe_close_timeout.py",
        "cases": [await timeout_case(), await cancelled_case()],
        "close_timeout_default_s": default,
        "a_flush_behind_a_held_sqlite_writer_waits_s": "4 tries x 5 s busy_timeout = 20, plus up to 0.35 s between tries",
    }
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
