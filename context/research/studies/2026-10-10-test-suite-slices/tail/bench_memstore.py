import asyncio, time
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

async def main():
    N = 30
    init = touch = later = close = 0.0
    for _ in range(N):
        t0 = time.perf_counter(); s = InMemoryStorage(); fs = VirtualFileSystem(storage=s); t1 = time.perf_counter()
        await fs.write(path="/a.txt", content="a"); t2 = time.perf_counter()
        await fs.write(path="/b.txt", content="b"); t3 = time.perf_counter()
        await fs.close(); t4 = time.perf_counter()
        init += t1 - t0; touch += t2 - t1; later += t3 - t2; close += t4 - t3
    print(f"per storage: construct {init/N*1000:.1f}ms  first-touch write {touch/N*1000:.1f}ms  later write {later/N*1000:.1f}ms  close {close/N*1000:.1f}ms")
    # glob cost on a tiny world
    s = InMemoryStorage(); fs = VirtualFileSystem(storage=s)
    await fs.write(path="/data/deep/b.txt", content="b", parents=True)
    t0 = time.perf_counter()
    for _ in range(N): await fs.glob("**/*.txt")
    print(f"glob on a 3-row world: {(time.perf_counter()-t0)/N*1000:.1f}ms")
    await fs.close()
asyncio.run(main())
