"""Researcher 02: an async tool path that awaits the facade's own loop, so one engine only ever sees one loop.

Run from /home/user/vfs: uv run python <this file>.
"""

from __future__ import annotations

import asyncio
import threading
import time

from langchain_core.tools import StructuredTool

from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import SyncVirtualFileSystem

fs = SyncVirtualFileSystem(storage=InMemoryStorage())
fs.write(path="/notes/a.txt", content="alpha\n", parents=True)
router = fs._fs  # the facade's router, read here only to build the bridge under study
loop = fs._loop
seen: list[str] = []


async def on_owner_loop(path: str) -> str:
    seen.append(threading.current_thread().name)
    return str(await router.read(path))


def r(path: str) -> str:
    return str(fs.read(path))


async def ar(path: str) -> str:
    return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(on_owner_loop(path), loop))


tool = StructuredTool.from_function(func=r, coroutine=ar, name="read", description="Read a file.")


async def main() -> None:
    print("ainvoke ->", (await tool.ainvoke({"path": "/notes/a.txt"})).strip(), "| ran on", seen[-1])
    ticks = 0
    stop = False

    async def heartbeat() -> None:
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0)

    n = 500
    t = time.perf_counter()
    for _ in range(n):
        await tool.ainvoke({"path": "/notes/a.txt"})
    print(f"{n} sequential ainvoke via owner loop: {1e6 * (time.perf_counter() - t) / n:.1f} us/call")
    t = time.perf_counter()
    await asyncio.gather(*(tool.ainvoke({"path": "/notes/a.txt"}) for _ in range(n)))
    print(f"{n} gathered ainvoke via owner loop: {1e6 * (time.perf_counter() - t) / n:.1f} us/call amortised")
    hb = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    await asyncio.gather(*(tool.ainvoke({"path": "/notes/a.txt"}) for _ in range(50)))
    stop = True
    await hb
    print(f"caller-loop heartbeat ticks while 50 gathered calls ran: {ticks} (nonzero: the caller loop stayed free)")
    print("distinct threads that ran the verb:", set(seen))
    print("sync invoke from a worker thread ->", (await asyncio.to_thread(tool.invoke, {"path": "/notes/a.txt"})).strip())


asyncio.run(main())
fs.close()
