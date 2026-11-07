"""Where a FastAPI developer can call vfs from, and what each placement costs.

Run from /home/user/vfs:
    uv run --with fastapi==0.162.0 --with httpx python \
        context/research/studies/2026-11-06-sync-and-async-api-shapes/experiments/01-fastapi-placement/placement.py

Each verb read is slowed by an awaited sleep of DELAY seconds so that blocking and
offload become visible. The heartbeat task ticks every 5 ms on the server loop; a
placement that blocks the loop starves it. Peak counts how many reads overlapped.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
import warnings

import anyio.to_thread
import fastapi
import httpx
import starlette
from fastapi import BackgroundTasks, Depends, FastAPI
from starlette._utils import is_async_callable

from vfs import VirtualFileSystem
from vfs.sync import SyncVirtualFileSystem

DELAY = 0.05
N = 100


class Slow(VirtualFileSystem):
    """The router with a counted, slowed read: stands in for a network-backed storage."""

    inflight = 0
    peak = 0
    lock = threading.Lock()

    async def read(self, *args, **kwargs):  # type: ignore[override]
        with Slow.lock:
            Slow.inflight += 1
            Slow.peak = max(Slow.peak, Slow.inflight)
        try:
            await asyncio.sleep(DELAY)
            return await super().read(*args, **kwargs)
        finally:
            with Slow.lock:
                Slow.inflight -= 1


afs = Slow()
sfs = SyncVirtualFileSystem.wrap(Slow())


def dual_read(path: str):
    """A dual-mode stand-in: a plain def that returns a coroutine under a running loop, else the value."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return sfs.read(path)
    return afs.read(path)


app = FastAPI()


@app.get("/a-async-await")
async def a(path: str = "/a.txt"):
    return {"text": str(await afs.read(path))}


@app.get("/b-def-syncfacade")
def b(path: str = "/a.txt"):
    return {"text": str(sfs.read(path)), "thread": threading.current_thread().name}


@app.get("/c-async-syncfacade")
async def c(path: str = "/a.txt"):
    return {"text": str(sfs.read(path))}


@app.get("/d-def-asynciorun")
def d(path: str = "/a.txt"):
    return {"text": str(asyncio.run(afs.read(path)))}


@app.get("/e-async-forgot-await")
async def e(path: str = "/a.txt"):
    return {"text": str(afs.read(path))}


@app.get("/f-async-asynciorun")
async def f(path: str = "/a.txt"):
    return {"text": str(asyncio.run(afs.read(path)))}


@app.get("/g-async-dual")
async def g(path: str = "/a.txt"):
    return {"text": str(await dual_read(path))}


@app.get("/h-def-dual")
def h(path: str = "/a.txt"):
    return {"text": str(dual_read(path))}


async def get_afs() -> VirtualFileSystem:
    return afs


def get_sfs() -> SyncVirtualFileSystem:
    return sfs


@app.get("/i-dep-async")
async def i(fs: VirtualFileSystem = Depends(get_afs)):
    return {"text": str(await fs.read("/a.txt"))}


done: list[str] = []


def bg_sync() -> None:
    sfs.write(path="/bg-sync.txt", content="s")
    done.append("bg_sync:" + threading.current_thread().name)


async def bg_async() -> None:
    await afs.write(path="/bg-async.txt", content="a")
    done.append("bg_async:" + threading.current_thread().name)


def bg_dual() -> None:
    done.append("bg_dual:" + threading.current_thread().name + ":" + type(dual_read("/a.txt")).__name__)


@app.post("/j-background")
async def j(tasks: BackgroundTasks):
    tasks.add_task(bg_sync)
    tasks.add_task(bg_async)
    tasks.add_task(bg_dual)
    tasks.add_task(afs.write, path="/bg-bound.txt", content="m")
    tasks.add_task(sfs.write, path="/bg-bound-sync.txt", content="m")
    return {"queued": 5}


async def heartbeat(stop: asyncio.Event, ticks: list[float]) -> None:
    while not stop.is_set():
        t0 = time.perf_counter()
        await asyncio.sleep(0.005)
        ticks.append(time.perf_counter() - t0)


async def run(client: httpx.AsyncClient, route: str, n: int) -> None:
    Slow.peak = 0
    stop, ticks = asyncio.Event(), []
    hb = asyncio.create_task(heartbeat(stop, ticks))
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            rs = await asyncio.gather(*(client.get(route) for _ in range(n)), return_exceptions=True)
        finally:
            stop.set()
            await hb
    wall = time.perf_counter() - t0
    statuses: dict[str, int] = {}
    for r in rs:
        key = str(r.status_code) if isinstance(r, httpx.Response) else type(r).__name__ + ": " + str(r)[:90]
        statuses[key] = statuses.get(key, 0) + 1
    worst = max(ticks) * 1000 if ticks else float("nan")
    warn = sorted({str(w.message)[:70] for w in caught})
    print(f"{route:24} n={n:3} wall={wall:5.2f}s peak_inflight={Slow.peak:3} heartbeat_ticks={len(ticks):3} worst_gap={worst:6.1f}ms statuses={statuses} warnings={warn}")


async def main() -> None:
    print("fastapi", fastapi.__version__, "starlette", starlette.__version__, "anyio thread tokens", anyio.to_thread.current_default_thread_limiter().total_tokens)
    await afs.write(path="/a.txt", content="hello")
    sfs.write(path="/a.txt", content="hello")
    print("is_async_callable: afs.read", is_async_callable(afs.read), "sfs.read", is_async_callable(sfs.read), "dual_read", is_async_callable(dual_read))
    print("inspect.iscoroutinefunction(afs.read)", inspect.iscoroutinefunction(afs.read))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        for route in ("/a-async-await", "/b-def-syncfacade", "/c-async-syncfacade", "/d-def-asynciorun", "/g-async-dual", "/h-def-dual", "/i-dep-async"):
            await run(client, route, N)
        for route in ("/e-async-forgot-await", "/f-async-asynciorun"):
            await run(client, route, 2)
        r = await client.get("/b-def-syncfacade")
        print("b served on thread:", r.json()["thread"])
        r = await client.post("/j-background")
        print("background status", r.status_code, r.json())
        for entry in done:
            print("  ran", entry)
        for p in ("/bg-sync.txt", "/bg-bound-sync.txt"):
            print("  sync facade wrote", p, sfs.read(p).paths if hasattr(sfs.read(p), "paths") else "")
        for p in ("/bg-async.txt", "/bg-bound.txt"):
            print("  async router wrote", p, (await afs.read(p)).paths)
    print("live threads named vfs-sync-loop:", sum(t.name == "vfs-sync-loop" for t in threading.enumerate()))
    sfs.close()


if __name__ == "__main__":
    asyncio.run(main())
