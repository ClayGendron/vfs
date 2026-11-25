"""Why a vfs grep scoped to one file costs more than the file: three ways to grep one file, timed.

    uv run python agents/2026-11-21-linux-grep-benchmark/scoped_grep.py linux.db
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

from vfs import AsyncVirtualFileSystem, DatabaseStorage

CASES = (
    ("^struct dentry \\{", "/include/linux/dcache.h"),
    ("^struct mount \\{", "/fs/mount.h"),
    ("i_count", "/include/linux/fs.h"),
    ("^struct dentry \\*simple_lookup", "/fs/libfs.c"),
)
REPS = 7


async def timed(call) -> tuple[float, int]:
    times = []
    hits = 0
    for repetition in range(REPS + 1):
        started = time.perf_counter()
        result = await call()
        elapsed = time.perf_counter() - started
        hits = sum(len(row.matches or []) for row in result.observations)
        if repetition:
            times.append(elapsed)
    return statistics.median(times) * 1000, hits


async def main(db: str) -> None:
    kernel = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{db}"))
    try:
        await kernel.stat("/fs")
        print("| pattern | file | grep(paths=file) ms | read+grep(observations) ms | read ms | grep whole tree ms |")
        print("|---|---|---|---|---|---|")
        for pattern, path in CASES:
            scoped, hits = await timed(lambda p=pattern, f=path: kernel.grep(p, paths=(f,)))
            read, _ = await timed(lambda f=path: kernel.read(f))

            async def in_hand(p: str = pattern, f: str = path):
                return await kernel.grep(p, observations=(await kernel.read(f)).observations)

            held, held_hits = await timed(in_hand)
            whole, _ = await timed(lambda p=pattern: kernel.grep(p))
            assert held_hits == hits
            print(f"| `{pattern}` | {path} | {scoped:.1f} | {held:.1f} | {read:.1f} | {whole:.1f} |")
    finally:
        await kernel.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
