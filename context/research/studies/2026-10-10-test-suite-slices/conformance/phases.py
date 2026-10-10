"""Time the lifecycle phases of a fresh storage: construct, first touch, one write, one read, close."""
import asyncio, sys, time, tempfile, pathlib, statistics
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage

N = int(sys.argv[2]) if len(sys.argv) > 2 else 20
mode = sys.argv[1] if len(sys.argv) > 1 else "memory"

async def one(tmp):
    t = {}
    t0 = time.process_time()
    if mode == "memory":
        s = InMemoryStorage()
    else:
        s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite", embedder=HashEmbeddingProvider())
    t["construct"] = time.process_time() - t0
    t0 = time.process_time()
    r = await s._host.ensure_ready()
    assert r is None, r
    t["first_touch"] = time.process_time() - t0
    t0 = time.process_time()
    r = await s.write(entries=[Entry(path=Path("/a/b/c.txt"), content="hi")], parents=True)
    assert r.success
    t["write1"] = time.process_time() - t0
    t0 = time.process_time()
    r = await s.write(entries=[Entry(path=Path("/a/b/d.txt"), content="hi")], parents=True)
    t["write2"] = time.process_time() - t0
    t0 = time.process_time()
    r = await s.stat(path=Path("/a/b"))
    t["stat"] = time.process_time() - t0
    t0 = time.process_time()
    r = await s.read(path=Path("/a/b/c.txt"))
    t["read"] = time.process_time() - t0
    t0 = time.process_time()
    await s.close()
    t["close"] = time.process_time() - t0
    return t

async def main():
    rows = []
    for i in range(N):
        with tempfile.TemporaryDirectory() as tmp:
            rows.append(await one(tmp))
    keys = rows[0].keys()
    print(f"{mode}: first iteration then median of the remaining {N-1}")
    for k in keys:
        vals = [r[k] for r in rows[1:]]
        print(f"  {k:12s} first={rows[0][k]*1000:8.1f}ms  median={statistics.median(vals)*1000:7.1f}ms")

asyncio.run(main())
