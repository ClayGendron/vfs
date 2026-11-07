"""The bodies and outcomes behind placements d, e and f of placement.py.

d is reproduced without FastAPI: 40 daemon threads, 8 at a time, each calling
asyncio.run(router.read(...)) on one shared router, each joined with a 5 s cap so a
hang is counted rather than waited on. Run as placement.py says.
"""

from __future__ import annotations

import asyncio
import threading
import traceback
import warnings

import httpx
from placement import Slow, afs, app


def outcome_of(router: Slow, sink: list[str]) -> None:
    try:
        sink.append("ok: " + str(asyncio.run(router.read("/a.txt"))))
    except Exception as exc:  # noqa: BLE001
        sink.append("".join(traceback.format_exception_only(exc)).strip()[:160])


def wave(router: Slow, width: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _ in range(40 // width):
        sinks = [[] for _ in range(width)]
        threads = [threading.Thread(target=outcome_of, args=(router, s), daemon=True) for s in sinks]
        for t in threads:
            t.start()
        for t, s in zip(threads, sinks, strict=True):
            t.join(5)
            key = s[0] if s else "hung (no answer within 5 s)"
            counts[key] = counts.get(key, 0) + 1
    return counts


async def main() -> None:
    await afs.write(path="/a.txt", content="hello")
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = await client.get("/e-async-forgot-await")
        print("e body:", r.status_code, r.text[:120])
    try:
        asyncio.run(afs.read("/a.txt"))
    except RuntimeError as exc:
        print("f:", exc)


asyncio.run(main())
for width in (1, 8):
    fresh = Slow()
    asyncio.run(fresh.write(path="/a.txt", content="hello"))
    print(f"d, asyncio.run per call, {width} thread(s) at a time over one shared router:")
    for k, v in wave(fresh, width).items():
        print(f"  {v:2}x {k}")
