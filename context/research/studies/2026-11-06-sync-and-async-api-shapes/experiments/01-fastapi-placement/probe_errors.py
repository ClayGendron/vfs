"""The bodies and tracebacks behind placements d, e and f of placement.py."""

from __future__ import annotations

import asyncio
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor

from placement import afs, app

import httpx


def threaded_asyncio_run(i: int) -> str:
    try:
        return str(asyncio.run(afs.read("/a.txt")))
    except Exception as exc:  # noqa: BLE001
        return "".join(traceback.format_exception_only(exc)).strip()[:200]


async def main() -> None:
    await afs.write(path="/a.txt", content="hello")
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = await client.get("/e-async-forgot-await")
        print("e body:", r.status_code, r.text[:120])
    with ThreadPoolExecutor(8) as pool:
        outcomes = list(pool.map(threaded_asyncio_run, range(40)))
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o] = counts.get(o, 0) + 1
    print("d, asyncio.run per call from 8 worker threads over one shared async router:")
    for k, v in counts.items():
        print(f"  {v:2}x {k}")
    try:
        async def inside() -> None:
            asyncio.run(afs.read("/a.txt"))
        await inside()
    except RuntimeError as exc:
        print("f:", exc)


asyncio.run(main())
