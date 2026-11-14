import asyncio, time, json, os
from vfs.base import AsyncVirtualFileSystem
from vfs import InMemoryStorage
from vfs.models import Observation
from vfs.paths import Path

async def ticker(gaps, stop):
    last = time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(0.001)
        now = time.perf_counter(); gaps.append(now - last); last = now

async def measure(fn):
    gaps, stop = [], asyncio.Event()
    t = asyncio.create_task(ticker(gaps, stop)); await asyncio.sleep(0.01); gaps.clear()
    t0 = time.perf_counter(); r = await fn(); el = time.perf_counter() - t0
    stop.set(); await t
    return r, el, max(gaps)

async def main():
    out = {"cpu_count": os.cpu_count()}
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    body = ("line of ordinary text without the word\n" * 25_000)
    await fs.write(path="/data/big.txt", content=body, parents=True)
    out["stored_body_bytes"] = len(body)
    p = r"(\w|\s){60}Q"
    out["pattern"] = p
    for n in (10, 20, 40):
        rows = [Observation(path=Path("/data/big.txt"), kind="file") for _ in range(n)]
        r, el, gap = await measure(lambda: fs.grep(p, observations=rows, output_mode="files"))
        out[f"chained_same_path_x{n}"] = {"success": r.success, "hits": len(r.observations), "elapsed_s": round(el, 3), "max_loop_gap_s": round(gap, 3)}
    r, el, gap = await measure(lambda: fs.grep(p, allow_scan=True, output_mode="files"))
    out["storage_scan_tier_x1"] = {"success": r.success, "elapsed_s": round(el, 3), "max_loop_gap_s": round(gap, 3)}
    print(json.dumps(out, indent=1))
asyncio.run(main())
