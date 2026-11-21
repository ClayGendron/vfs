"""Two checks on the sandbox, reads only.

1. Decision 4 names three plans and none for a pattern with no indexable literal: today the database path refuses
   it without allow_scan, and the in-hand path (grep with observations) answers it. Which does a small scope get?
2. Decision 7 keeps c_stmt as a weighted mean of observed statement latencies: what do one call's statements span?
"""
from __future__ import annotations

import asyncio
import sqlite3
import statistics
import sys
import time

from sqlalchemy import event

from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import Observation

DB = sys.argv[1]


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    lat: list[float] = []
    started: dict = {}
    eng = storage.engine.sync_engine
    event.listen(eng, "before_cursor_execute", lambda c, cur, s, p, ctx, m: started.__setitem__(id(cur), time.perf_counter()))
    event.listen(eng, "after_cursor_execute",
                 lambda c, cur, s, p, ctx, m: lat.append((time.perf_counter() - started.pop(id(cur))) * 1000))
    try:
        root = "/mm/tests"
        paths = [p for (p,) in raw.execute("select path from vfs_entries where kind='file' and path > ? and path < ?",
                                           (root + "/", root + "0"))]
        for pattern in ("a", ".", "^$", "x*"):
            db = await fs.grep(pattern, paths=(root,), output_mode="files")
            hand = await fs.grep(pattern, observations=[Observation(path=p, kind="file") for p in paths], output_mode="files")
            print(f"{pattern!r}: database plan -> {len(db.observations)} rows {[e.kind for e in db.errors]}; "
                  f"in-hand plan -> {len(hand.observations)} rows {[e.kind for e in hand.errors]}")
        for root, pattern in (("/drivers/atm", "-EINVAL"), ("/drivers/gpu", "i_count"), (None, "i_count")):
            lat.clear()
            await fs.grep(pattern, **({"paths": (root,)} if root else {}), output_mode="files")
            lat.sort()
            print(f"{root or 'corpus'} {pattern}: {len(lat)} statements, latency ms min={lat[0]:.3f} "
                  f"median={statistics.median(lat):.3f} max={lat[-1]:.1f}; max/min={lat[-1] / lat[0]:.0f}x")
    finally:
        raw.close()
        await fs.close()


asyncio.run(main())
