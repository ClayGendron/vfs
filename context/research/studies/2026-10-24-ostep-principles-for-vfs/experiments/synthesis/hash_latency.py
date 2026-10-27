"""How much latency would a sha256 check add to read? Compares the time to read a body
through vfs (InMemoryStorage, system actor) with the time hashlib takes to hash it."""

from __future__ import annotations

import asyncio
import hashlib
import time

from vfs import Authority, VirtualFileSystem
from vfs.storage.backends import InMemoryStorage

SIZES = [1_000, 10_000, 100_000, 1_000_000, 4_000_000, 16_000_000]
REPS = 20


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    admin = Authority.system()
    print(f"{'bytes':>10} {'read µs':>10} {'sha256 µs':>10} {'added %':>8}")
    for n in SIZES:
        body = ("x" * 99 + "\n") * (n // 100)
        path = f"/f{n}.txt"
        await fs.write(path=path, content=body, authority=admin)
        await fs.read(path, authority=admin)
        t0 = time.perf_counter()
        for _ in range(REPS):
            r = await fs.read(path, authority=admin)
        read_us = (time.perf_counter() - t0) / REPS * 1e6
        data = r.first().content.encode()
        t0 = time.perf_counter()
        for _ in range(REPS):
            hashlib.sha256(data).hexdigest()
        hash_us = (time.perf_counter() - t0) / REPS * 1e6
        print(f"{len(data):>10,} {read_us:>10,.0f} {hash_us:>10,.0f} {hash_us / read_us * 100:>7.1f}%")
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
