"""Researcher 02: two dual-mode stand-ins (context detection, dual-use handle) inside LangChain sync tools.

Run from /home/user/vfs: uv run python <this file>. Stand-ins only; no vfs code.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any

from langchain_core.tools import tool

_LOOP = asyncio.new_event_loop()
threading.Thread(target=_LOOP.run_forever, daemon=True).start()


async def _read(path: str) -> str:
    await asyncio.sleep(0)
    return f"contents of {path}"


def detecting_read(path: str) -> Any:
    """Prefect-style: a coroutine when a loop runs on this thread, else the value."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run_coroutine_threadsafe(_read(path), _LOOP).result()
    return _read(path)


class Handle:
    """Dual-use: awaitable, and .result() blocks."""

    def __init__(self, path: str) -> None:
        self._future: concurrent.futures.Future[str] = asyncio.run_coroutine_threadsafe(_read(path), _LOOP)

    def __await__(self):  # noqa: ANN204
        return asyncio.wrap_future(self._future).__await__()

    def result(self) -> str:
        return self._future.result()


def handle_read(path: str) -> Handle:
    return Handle(path)


@tool
def detect_tool(path: str) -> str:
    """Read via the detecting function, the way a sync tool author writes it."""
    return str(detecting_read(path))


@tool
def handle_tool(path: str) -> str:
    """Read via the dual-use handle, forgetting .result()."""
    return str(handle_read(path))


def show(label: str, value: str) -> None:
    print(f"  {label:<44} -> {value[:60]}")


print("== plain script, .invoke")
show("detect_tool.invoke", detect_tool.invoke({"path": "/a"}))
show("handle_tool.invoke (no .result())", handle_tool.invoke({"path": "/a"}))


async def main() -> None:
    print("== async agent, .ainvoke (LangChain runs the sync body in an executor thread)")
    show("detect_tool.ainvoke", await detect_tool.ainvoke({"path": "/a"}))
    print("== sync body run on the loop thread (a node or callback calling .invoke inside async code)")
    show("detect_tool.invoke on loop thread", detect_tool.invoke({"path": "/a"}))


asyncio.run(main())
