"""Where does offloading a sha256 start to pay? Measures (a) the cost of one hand-off
through vfs's offload seam, (b) loop stall per hash on the loop, (c) wall time for 32
concurrent reads-with-hash, hashed inline on the loop versus offloaded."""

from __future__ import annotations

import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

from vfs.storage.backends.database.offload import call_offloaded

SIZES = [10_000, 100_000, 256_000, 1_000_000, 4_000_000, 16_000_000]
CONCURRENT = 32


async def main() -> None:
    pool = ThreadPoolExecutor(max_workers=8)
    t0 = time.perf_counter()
    for _ in range(200):
        await call_offloaded(pool, lambda: None)
    handoff_us = (time.perf_counter() - t0) / 200 * 1e6
    print(f"offload hand-off (empty work): {handoff_us:,.0f} µs")
    print(f"{'bytes':>12} {'inline µs':>10} {'offload µs':>11} | {'32 inline ms':>12} {'32 offload ms':>13} {'loop stall ms':>13}")
    for n in SIZES:
        data = (b"x" * 99 + b"\n") * (n // 100)
        h = lambda: hashlib.sha256(data).hexdigest()
        h()
        t0 = time.perf_counter(); [h() for _ in range(10)]; inline = (time.perf_counter() - t0) / 10 * 1e6
        t0 = time.perf_counter()
        for _ in range(10):
            await call_offloaded(pool, h)
        off = (time.perf_counter() - t0) / 10 * 1e6
        # 32 concurrent "requests", inline: each hashes on the loop
        async def inline_req():
            await asyncio.sleep(0)
            h()
        async def off_req():
            await call_offloaded(pool, h)
        # loop stall: longest gap a 1 ms ticker sees while inline work runs
        stall = 0.0
        async def ticker(stop):
            nonlocal stall
            last = time.perf_counter()
            while not stop.is_set():
                await asyncio.sleep(0.001)
                now = time.perf_counter(); stall = max(stall, now - last - 0.001); last = now
        stop = asyncio.Event(); tk = asyncio.create_task(ticker(stop))
        t0 = time.perf_counter(); await asyncio.gather(*(inline_req() for _ in range(CONCURRENT))); w_in = (time.perf_counter() - t0) * 1e3
        stop.set(); await tk
        t0 = time.perf_counter(); await asyncio.gather(*(off_req() for _ in range(CONCURRENT))); w_off = (time.perf_counter() - t0) * 1e3
        print(f"{len(data):>12,} {inline:>10,.0f} {off:>11,.0f} | {w_in:>12,.1f} {w_off:>13,.1f} {stall*1e3:>13,.1f}")
    pool.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
