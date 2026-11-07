"""Confirming run over the real vfs.VirtualFileSystem on InMemoryStorage (aiosqlite).

Question: does the real kernel survive the two bridging strategies the dual mechanisms use?
(a) a fresh asyncio.run per sync call (plain detection, Prefect's no-loop path in 2.x, greenback's
and SQLAlchemy's no-loop fallbacks), (b) one private loop thread per object (vfs.sync, fsspec,
Prefect's RunSyncEventLoopThread), and (c) the detect-style coroutine handed back inside a loop.
Run with: cd /home/user/vfs && uv run python <this file>
"""

from __future__ import annotations

import asyncio
import threading
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor

from vfs import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import SyncVirtualFileSystem


def report(label: str, fn) -> None:
    try:
        print(f"{label}: {fn()}")
    except BaseException as exc:  # noqa: BLE001
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        print(f"{label}: RAISED {type(exc).__name__}: {str(exc)[:160]} (at {frame.filename.split('/')[-1]}:{frame.lineno})")


def per_call_asyncio_run() -> str:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    w = asyncio.run(fs.write(path="/a.txt", content="x"))
    r = asyncio.run(fs.read("/a.txt"))
    return f"write.success={w.success} read.success={r.success}"


def portal_thread() -> str:
    with SyncVirtualFileSystem(storage=InMemoryStorage()) as fs:
        w = fs.write(path="/a.txt", content="x")
        r = fs.read("/a.txt")
    return f"write.success={w.success} read.success={r.success}"


def cross_loop() -> str:
    fs = VirtualFileSystem(storage=InMemoryStorage())

    async def first() -> bool:
        return (await fs.write(path="/a.txt", content="x")).success

    ok = asyncio.run(first())
    pool = ThreadPoolExecutor(1)
    second = pool.submit(lambda: asyncio.run(fs.read("/a.txt"))).result()
    return f"write on loop A={ok}, read on loop B in another thread success={second.success}"


def sync_spelling_inside_loop() -> str:
    async def main() -> str:
        fs = VirtualFileSystem(storage=InMemoryStorage())
        r = fs.read("/a.txt")  # the forgotten await a detect-style dual API turns into
        return f"returned {type(r).__name__}, has .success: {hasattr(r, 'success')}"

    return asyncio.run(main())


if __name__ == "__main__":
    warnings.simplefilter("always")
    report("(a) fresh asyncio.run per call", per_call_asyncio_run)
    report("(b) private loop thread (vfs.sync)", portal_thread)
    report("(a') loop A then loop B on another thread", cross_loop)
    report("(c) sync spelling inside a running loop", sync_spelling_inside_loop)
    print("threads:", sorted(t.name for t in threading.enumerate()))
