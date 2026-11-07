"""Researcher 02: how vfs's async router and sync facade behave as LangChain tools.

Run from /home/user/vfs: uv run python <this file>. Uses langchain_core from the vfs venv.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time

from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.runnables.config import get_executor_for_config, var_child_runnable_config
from langchain_core.tools import StructuredTool, tool

from vfs import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import SyncVirtualFileSystem

USER_VAR: contextvars.ContextVar[str] = contextvars.ContextVar("user_var", default="unset")
SEEN: list[tuple[str, str, str, str]] = []


def note(where: str) -> None:
    cfg = var_child_runnable_config.get()
    tags = ",".join((cfg or {}).get("tags", [])) if cfg else "none"
    SEEN.append((where, threading.current_thread().name, USER_VAR.get(), tags))


sync_fs = SyncVirtualFileSystem(storage=InMemoryStorage())
sync_fs.write(path="/notes/a.txt", content="alpha beta\n", parents=True)


async def build_async_fs() -> VirtualFileSystem:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/notes/a.txt", content="alpha beta\n", parents=True)
    return fs


@tool
def read_sync(path: str) -> str:
    """Read a file through the sync facade."""
    note("sync tool body")
    return str(sync_fs.read(path))


def section(title: str) -> None:
    print(f"\n== {title}")


def report() -> None:
    for row in SEEN:
        print("   seen:", row)
    SEEN.clear()


# 1. A sync tool over the facade, called sync and from an async agent.
section("1 sync @tool over SyncVirtualFileSystem: invoke")
USER_VAR.set("caller-sync")
print("  ->", read_sync.invoke({"path": "/notes/a.txt"}, config={"tags": ["t-sync"]}).strip())
report()


async def case1_async() -> None:
    USER_VAR.set("caller-async")
    out = await read_sync.ainvoke({"path": "/notes/a.txt"}, config={"tags": ["t-async"]})
    print("  ->", out.strip())


section("1c inside the verb's own task on the facade loop thread")


async def probe() -> None:
    note("facade loop task")


@tool
def probe_tool(path: str) -> str:
    """Probe what context reaches the facade's loop thread."""
    note("probe tool body")
    sync_fs._submit(probe())  # private hop, used here only to observe the verb's context
    return "ok"


USER_VAR.set("caller-probe")
probe_tool.invoke({"path": "/x"}, config={"tags": ["t-probe"]})
report()


async def case1c_async() -> None:
    USER_VAR.set("caller-probe-async")
    await probe_tool.ainvoke({"path": "/x"}, config={"tags": ["t-probe-async"]})


asyncio.run(case1c_async())
report()

section("1b same sync tool: ainvoke from a running loop (executor round trip)")
asyncio.run(case1_async())
report()

# 2. An async tool over the async router, called both ways.
section("2 async @tool over VirtualFileSystem: ainvoke, then invoke")


async def case2() -> None:
    afs = await build_async_fs()

    @tool
    async def read_async(path: str) -> str:
        """Read a file through the async router."""
        note("async tool body")
        return str(await afs.read(path))

    out = await read_async.ainvoke({"path": "/notes/a.txt"}, config={"tags": ["t-a"]})
    print("  ainvoke ->", out.strip())
    report()
    try:
        await asyncio.to_thread(read_async.invoke, {"path": "/notes/a.txt"})
    except Exception as exc:  # noqa: BLE001
        print("  invoke  ->", type(exc).__name__, ":", exc)
    await afs.close()


asyncio.run(case2())

# 3. Both implementations on one tool: each path native.
section("3 StructuredTool.from_function(func=sync facade, coroutine=async router)")


async def case3() -> None:
    afs = await build_async_fs()

    def r(path: str) -> str:
        note("func")
        return str(sync_fs.read(path))

    async def ar(path: str) -> str:
        note("coroutine")
        return str(await afs.read(path))

    both = StructuredTool.from_function(func=r, coroutine=ar, name="read", description="Read a file.")
    await both.ainvoke({"path": "/notes/a.txt"})
    await asyncio.to_thread(both.invoke, {"path": "/notes/a.txt"})
    report()
    await afs.close()


asyncio.run(case3())

# 4. The naive bridge an AI engineer writes: asyncio.run inside a sync tool.
section("4 sync tool that calls asyncio.run(async_fs.read(...))")


@tool
def read_naive(path: str) -> str:
    """Read via asyncio.run over a fresh router each call."""

    async def go() -> str:
        fs = await build_async_fs()
        try:
            return str(await fs.read(path))
        finally:
            await fs.close()

    return asyncio.run(go())


print("  invoke (no loop) ->", read_naive.invoke({"path": "/notes/a.txt"}).strip())


async def case4() -> None:
    out = await read_naive.ainvoke({"path": "/notes/a.txt"})
    print("  ainvoke (executor thread) ->", out.strip())
    try:
        read_naive.invoke({"path": "/notes/a.txt"})
    except Exception as exc:  # noqa: BLE001
        print("  invoke on the loop thread ->", type(exc).__name__, ":", exc)


asyncio.run(case4())

# 5. A sync callable run on the loop thread (LangGraph's RunnableCallable.ainvoke with no afunc does this).
section("5 sync facade call made on the event-loop thread: loop starvation count")


async def case5() -> None:
    ticks = 0
    stop = False

    async def heartbeat() -> None:
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0)

    hb = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    before = ticks
    for _ in range(200):
        sync_fs.read("/notes/a.txt")
    during = ticks - before
    before = ticks
    for _ in range(200):
        await asyncio.to_thread(sync_fs.read, "/notes/a.txt")
    offloaded = ticks - before
    stop = True
    await hb
    print(f"  heartbeat ticks during 200 blocking facade reads on the loop: {during}")
    print(f"  heartbeat ticks during 200 offloaded facade reads:            {offloaded}")


asyncio.run(case5())

# 6. ToolNode-shaped fan-out: N parallel tool calls, sync path and async path.
section("6 ToolNode-shaped fan-out of 8 calls")


async def case6() -> None:
    afs = await build_async_fs()

    def r(path: str) -> str:
        note("fanout-sync")
        return str(sync_fs.read(path))

    async def ar(path: str) -> str:
        note("fanout-async")
        return str(await afs.read(path))

    sync_only = StructuredTool.from_function(func=r, name="r", description="r")
    both = StructuredTool.from_function(func=r, coroutine=ar, name="rb", description="rb")
    calls = [{"path": "/notes/a.txt"}] * 8
    await asyncio.gather(*(sync_only.ainvoke(c) for c in calls))
    threads = {row[1] for row in SEEN}
    print(f"  async agent, sync-only tool: {len(SEEN)} calls on {len(threads)} distinct worker threads")
    SEEN.clear()
    await asyncio.gather(*(both.ainvoke(c) for c in calls))
    threads = {row[1] for row in SEEN}
    print(f"  async agent, tool with coroutine: {len(SEEN)} calls on {len(threads)} distinct threads {threads}")
    SEEN.clear()

    def sync_agent() -> None:
        with get_executor_for_config(RunnableConfig(max_concurrency=4)) as ex:
            list(ex.map(lambda c: sync_only.invoke(c), calls))

    await asyncio.to_thread(sync_agent)
    threads = {row[1] for row in SEEN}
    print(f"  sync agent (ToolNode executor, max_concurrency=4): {len(SEEN)} calls on {len(threads)} threads")
    SEEN.clear()
    await afs.close()


asyncio.run(case6())

# 7. Per-call overhead of each path (research timing, not a test).
section("7 per-call cost, 2000 reads each, microseconds per call")


async def case7() -> None:
    afs = await build_async_fs()
    n = 2000

    def r(path: str) -> str:
        return str(sync_fs.read(path))

    async def ar(path: str) -> str:
        return str(await afs.read(path))

    sync_tool = StructuredTool.from_function(func=r, name="r", description="r")
    async_tool = StructuredTool.from_function(coroutine=ar, name="a", description="a")
    t = time.perf_counter()
    for _ in range(n):
        await afs.read("/notes/a.txt")
    print(f"  await router.read           {1e6 * (time.perf_counter() - t) / n:8.1f}")
    t = time.perf_counter()
    for _ in range(n):
        await asyncio.to_thread(sync_fs.read, "/notes/a.txt")
    print(f"  to_thread(facade.read)      {1e6 * (time.perf_counter() - t) / n:8.1f}")
    t = time.perf_counter()
    for _ in range(n):
        await async_tool.ainvoke({"path": "/notes/a.txt"})
    print(f"  async tool .ainvoke         {1e6 * (time.perf_counter() - t) / n:8.1f}")
    t = time.perf_counter()
    for _ in range(n):
        await sync_tool.ainvoke({"path": "/notes/a.txt"})
    print(f"  sync tool .ainvoke          {1e6 * (time.perf_counter() - t) / n:8.1f}")
    await afs.close()


def case7_sync() -> None:
    n = 2000

    def r(path: str) -> str:
        return str(sync_fs.read(path))

    sync_tool = StructuredTool.from_function(func=r, name="r", description="r")
    t = time.perf_counter()
    for _ in range(n):
        sync_fs.read("/notes/a.txt")
    print(f"  facade.read (no loop)       {1e6 * (time.perf_counter() - t) / n:8.1f}")
    t = time.perf_counter()
    for _ in range(n):
        sync_tool.invoke({"path": "/notes/a.txt"})
    print(f"  sync tool .invoke           {1e6 * (time.perf_counter() - t) / n:8.1f}")


asyncio.run(case7())
case7_sync()

# 8. A 10,000-entry write through the facade from a sync tool and from abatch.
section("8 10,000-entry write via the facade")
entries = [Entry(path=f"/bulk/{i:05d}.txt", content=f"row {i}\n") for i in range(10_000)]
sync_fs.mkdir("/bulk")
res = sync_fs.write(entries)
print("  success:", res.success, "rows:", len(res))
lam = RunnableLambda(lambda p: sync_fs.read(p).success)
print("  RunnableLambda.abatch over 50 facade reads ->", all(asyncio.run(lam.abatch([f"/bulk/{i:05d}.txt" for i in range(50)]))))
print("  threads alive named vfs-sync-loop:", sum(t.name == "vfs-sync-loop" for t in threading.enumerate()))
sync_fs.close()
