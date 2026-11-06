"""Run one mechanism in one setting and print a JSON line describing what happened.

Settings: s1_sync (plain script), s2_sync (sync spelling inside asyncio.run on the loop thread,
as a notebook cell does), s2_async (await spelling on the loop thread), s3_worker (sync spelling
from a ThreadPoolExecutor worker while the main thread runs a loop), plus variants for the
greenlet mechanisms. A heartbeat task counts loop ticks during the call: zero ticks means the
call blocked the caller's event loop.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mechanisms import MECHANISMS, Result

ASYNC_NAME = {"twins": "aread", "fsspec_sync_flag": "aread", "fsspec_async_flag": "aread"}


def sync_spelling(name: str, fs: Any) -> Any:
    r = fs.read("a")
    if name == "handle_result":
        r = r.result()
    return r


def async_spelling(name: str, fs: Any) -> Any:
    return getattr(fs, ASYNC_NAME.get(name, "read"))("a")


def describe(r: Any, caller_loop: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {"returned": type(r).__name__}
    try:
        out["ran_on_thread"] = r.thread
        out["on_caller_loop"] = caller_loop is not None and r.loop_id == caller_loop
        out["value_ok"] = r.success is True and r.path == "a"
    except Exception as exc:  # noqa: BLE001
        out["attr_error"] = f"{type(exc).__name__}: {exc}"[:160]
    return out


async def heartbeat(counter: list[int]) -> None:
    while True:
        await asyncio.sleep(0.005)
        counter[0] += 1


async def in_loop(name: str, setting: str) -> dict[str, Any]:
    cls = MECHANISMS[name]
    loop = asyncio.get_running_loop()
    ticks = [0]
    hb = asyncio.create_task(heartbeat(ticks))
    await asyncio.sleep(0)
    fs = cls()
    before = ticks[0]
    if setting == "s2_sync":
        r = sync_spelling(name, fs)
        out = describe(r, id(loop))
        await asyncio.sleep(0)
    elif setting == "s2_sync_portal":
        import greenback

        await greenback.ensure_portal()
        r = sync_spelling(name, fs)
        out = describe(r, id(loop))
    elif setting == "s2_sync_spawned":
        from sqlalchemy.util import greenlet_spawn

        r = await greenlet_spawn(lambda: sync_spelling(name, fs))
        out = describe(r, id(loop))
    elif setting == "s2_async":
        r = await async_spelling(name, fs)
        out = describe(r, id(loop))
    elif setting == "s3_worker":
        with ThreadPoolExecutor(2) as pool:
            r = await loop.run_in_executor(pool, lambda: sync_spelling(name, fs))
        out = describe(r, id(loop))
    else:
        raise ValueError(setting)
    out["loop_ticks_during_call"] = ticks[0] - before
    hb.cancel()
    return out


def main() -> None:
    name, setting = sys.argv[1], sys.argv[2]
    warnings.simplefilter("always")
    caught: list[str] = []
    old = warnings.showwarning
    warnings.showwarning = lambda m, c, *a, **k: caught.append(f"{c.__name__}: {m}"[:140])
    out: dict[str, Any] = {"mechanism": name, "setting": setting}
    try:
        if setting == "s1_sync":
            r = sync_spelling(name, MECHANISMS[name]())
            out |= describe(r, None)
        else:
            out |= asyncio.run(in_loop(name, setting))
    except BaseException as exc:  # noqa: BLE001
        out["raised"] = f"{type(exc).__name__}: {exc}"[:200]
        out["raised_at"] = traceback.extract_tb(exc.__traceback__)[-1].filename.split("/")[-1]
    import gc

    gc.collect()
    warnings.showwarning = old
    out["warnings"] = sorted(set(caught))
    out["threads_alive"] = sorted({t.name.split("_")[0] for t in threading.enumerate()})
    print(json.dumps(out))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
    import os

    os._exit(0)
