"""A call that its caller cancels leaves its storage whole.

An in-memory SQLite database lives in its one connection. A call that
is cancelled while it uses that connection must not cost the storage
its rows, and the next call must work.

No test here reads a clock. One chosen driver round trip is held on the
driver's worker thread until the test lets it go, and the call is
cancelled while it is held.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any

import aiosqlite.core
import pytest

from vfs import AsyncVirtualFileSystem, Authority, InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator


class HeldRoundTrip:
    """Holds the first driver round trip that *chosen* picks, on the worker thread."""

    def __init__(self) -> None:
        self.chosen: Callable[[str], bool] | None = None
        self.reached = asyncio.Event()
        self._let_go = threading.Event()

    def hold(self, chosen: Callable[[str], bool]) -> None:
        self.chosen = chosen

    def let_go(self) -> None:
        self.chosen = None
        self._let_go.set()

    def wrap(self, function: Callable[..., Any]) -> Callable[..., Any]:
        loop = asyncio.get_running_loop()
        self.chosen = None

        def held(*args: Any, **kwargs: Any) -> Any:
            loop.call_soon_threadsafe(self.reached.set)
            self._let_go.wait()
            return function(*args, **kwargs)

        return held


@pytest.fixture
def round_trip(monkeypatch: pytest.MonkeyPatch) -> Iterator[HeldRoundTrip]:
    held = HeldRoundTrip()
    queue_it = aiosqlite.core.Connection._execute

    async def _execute(self: Any, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        statement = next((arg for arg in args if isinstance(arg, str)), "")
        if held.chosen is not None and held.chosen(statement):
            function = held.wrap(function)
        return await queue_it(self, function, *args, **kwargs)

    monkeypatch.setattr(aiosqlite.core.Connection, "_execute", _execute)
    yield held
    held.let_go()


async def cancel_while_held(call: Awaitable[Any], round_trip: HeldRoundTrip) -> None:
    """Cancel *call* while its chosen round trip is held, then let the round trip go."""
    task = asyncio.ensure_future(call)
    reached = asyncio.ensure_future(round_trip.reached.wait())
    await asyncio.wait({task, reached}, return_when=asyncio.FIRST_COMPLETED)
    assert round_trip.reached.is_set(), "the call ended before it reached the chosen round trip"
    task.cancel()
    round_trip.let_go()
    with pytest.raises(asyncio.CancelledError):
        await task


def reads_entries(statement: str) -> bool:
    return statement.lstrip().upper().startswith("SELECT") and "vfs_entries" in statement


async def kernel_with_one_file() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage(), default_authority=Authority.system())
    assert (await fs.write(path="/a.txt", content="old")).success
    return fs


class TestACancelledRead:
    async def test_a_stat_cancelled_inside_a_statement_leaves_the_file_readable(
        self, round_trip: HeldRoundTrip
    ) -> None:
        fs = await kernel_with_one_file()
        round_trip.hold(reads_entries)
        await cancel_while_held(fs.stat("/"), round_trip)
        read = await fs.read("/a.txt")
        assert read.success, read.errors
        assert read.one().content == "old"
        await fs.close()

    async def test_after_a_cancelled_stat_a_write_lands_beside_the_earlier_file(
        self, round_trip: HeldRoundTrip
    ) -> None:
        fs = await kernel_with_one_file()
        round_trip.hold(reads_entries)
        await cancel_while_held(fs.stat("/"), round_trip)
        assert (await fs.write(path="/b.txt", content="new")).success
        listed = await fs.ls("/")
        assert sorted(str(row.path) for row in listed.observations) == ["/a.txt", "/b.txt"]
        await fs.close()
