"""Follow-up probes: cost per sync call, reentrant deadlock, lazy handle forced in a worker, loop-bound state.

Run with the scratch venv: .venv/bin/python extra.py <probe>
"""

from __future__ import annotations

import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import mechanisms
from mechanisms import MECHANISMS, _Portal


def cost() -> None:
    """Sync spelling 200 times from a plain script: distinct threads and loops that ran the work."""
    mechanisms.SLEEP = 0
    made = [0]
    real = asyncio.events.new_event_loop

    def counting():
        made[0] += 1
        return real()

    asyncio.events.new_event_loop = counting
    asyncio.new_event_loop = counting
    for name in ["detect", "twins", "prefect_sync_compatible", "prefect_async_dispatch", "fsspec_sync_flag",
                 "sqla_await_only", "greenback", "asgiref_plain", "lazy_portal", "handle_result"]:
        fs = MECHANISMS[name]()
        made[0] = 0
        before = {t.ident for t in threading.enumerate()}
        threads, loops = set(), set()
        for _ in range(200):
            r = fs.read("a")
            r = r.result() if name == "handle_result" else r
            threads.add(r.thread)
            loops.add(r.loop_id)
        created = {t.name for t in threading.enumerate() if t.ident not in before}
        print(f"{name}: threads_that_ran_work={len(threads)} loops_created={made[0]} "
              f"threads_left_alive={sorted(created)}")


def reentrant() -> None:
    """Sync spelling called from code already running on the mechanism's own private loop."""
    name = sys.argv[2]
    fs = MECHANISMS[name]()

    async def inner() -> str:
        r = fs.read("a")
        r = r.result() if name == "handle_result" else r
        return type(r).__name__

    if name in ("twins", "prefect_async_dispatch", "handle_result", "lazy_portal"):
        loop = fs._portal.loop
    elif name == "fsspec_sync_flag":
        loop = fs.fs.loop
    elif name == "prefect_sync_compatible":
        from prefect.utilities.asyncutils import get_run_sync_loop  # type: ignore[attr-defined]

        runner = get_run_sync_loop()
        runner.submit  # noqa: B018
        loop = runner._loop
    else:
        raise ValueError(name)
    fut = asyncio.run_coroutine_threadsafe(inner(), loop)
    try:
        print(f"{name}: {fut.result(timeout=5)}")
    except TimeoutError:
        print(f"{name}: HANG (no result in 5 s; the private loop waits on itself)")
    except BaseException as exc:  # noqa: BLE001
        print(f"{name}: RAISED {type(exc).__name__}: {str(exc)[:140]}")


def lazy_worker() -> None:
    """Lazy handle forced inside the worker thread rather than after it escapes to the loop thread."""
    for name in ["lazy_portal", "lazy_greenback"]:
        fs = MECHANISMS[name]()

        async def main() -> str:
            with ThreadPoolExecutor(1) as pool:
                r = await asyncio.get_running_loop().run_in_executor(pool, lambda: (lambda h: (h.thread, h))(fs.read("a")))
            return f"forced in worker on {r[0]}"

        try:
            print(f"{name}: {asyncio.run(main())}")
        except BaseException as exc:  # noqa: BLE001
            print(f"{name}: RAISED {type(exc).__name__}: {str(exc)[:140]}")


def loop_bound() -> None:
    """A loop-bound primitive created by work on loop A, then used by a sync call bridged to loop B."""
    ev: list[asyncio.Event] = []

    async def use() -> str:
        if not ev:
            ev.append(asyncio.Event())
        e = ev[0]
        e.clear()
        asyncio.get_running_loop().call_later(0.01, e.set)
        await e.wait()
        return "ok"

    print("loop A (asyncio.run):", asyncio.run(use()))
    portal = _Portal()
    try:
        print("loop B (private thread):", asyncio.run_coroutine_threadsafe(use(), portal.loop).result(5))
    except BaseException as exc:  # noqa: BLE001
        print(f"loop B (private thread): RAISED {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    {"cost": cost, "reentrant": reentrant, "lazy_worker": lazy_worker, "loop_bound": loop_bound}[sys.argv[1]]()
    import os

    os._exit(0)
