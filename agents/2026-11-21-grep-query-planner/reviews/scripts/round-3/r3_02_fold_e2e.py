"""End to end: a Unicode 16 case pair the matcher unifies and the index fold does not.

A fresh SQLite store, rebuilt so every body is encoded. The same grep runs
two ways: the ladder (paths=) and in hand (observations=), the plan decision 6
routes a small scope to. Rows that differ are rows a plan choice changes.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys

from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import Observation

DB = sys.argv[1]
FILES = {
    "/u/rams_upper.txt": "Ɤabc marker\n",
    "/u/rams_lower.txt": "ɤabc marker\n",
    "/u/lambda_upper.txt": "Ƛqrs marker\n",
    "/u/garay_upper.txt": "\U00010d50\U00010d51\U00010d52 marker\n",
    "/u/plain.txt": "nothing here\n",
}
CASES = [
    ("ɤabc", "smart"),
    ("ƛqrs", "smart"),
    ("\U00010d70\U00010d71\U00010d72", "insensitive"),
    ("Ɤabc", "insensitive"),
]


async def main() -> None:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(DB + suffix):
            os.remove(DB + suffix)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    try:
        for path, body in FILES.items():
            r = await fs.write(path=path, content=body, parents=True)
            assert r.success, r.errors
        rb = await storage.rebuild()
        print("rebuild success", rb.success, [e.message[:80] for e in rb.errors])
        raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        print("encoded rows", raw.execute("select path, encoded from vfs_entries where kind='file' order by path").fetchall())
        observations = [Observation(path=p, kind="file") for p in FILES]
        for pattern, case_mode in CASES:
            ladder = await fs.grep(pattern, paths=("/u",), case_mode=case_mode, output_mode="files")
            hand = await fs.grep(pattern, observations=observations, case_mode=case_mode, output_mode="files")
            lrows = sorted(str(o.path) for o in ladder.observations)
            hrows = sorted(str(o.path) for o in hand.observations)
            print(f"{pattern!r} case={case_mode}")
            print(f"   ladder  {lrows} errors={[e.message[:60] for e in ladder.errors]}")
            print(f"   in hand {hrows} errors={[e.message[:60] for e in hand.errors]}")
            print(f"   LOST BY THE LADDER: {sorted(set(hrows) - set(lrows))}")
    finally:
        await fs.close()


asyncio.run(main())
