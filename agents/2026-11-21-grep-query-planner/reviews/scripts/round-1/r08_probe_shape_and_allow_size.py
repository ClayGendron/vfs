"""Decisions 2, 3 and 4: what the range probe and the range allow-list return, by counts, on the sandbox.

a) R2's probe predicate (the one e1 measures) against a root that is a file, beside vfs's own answer.
b) Overlapping roots: rows the per-root probe returns against distinct rows.
c) The range allow-list decision 4's third bullet builds for a wide multi-root scope: one statement, rows returned.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
import tracemalloc

from vfs import AsyncVirtualFileSystem, DatabaseStorage

DB = sys.argv[1]
RANGE = "kind = 'file' AND path > ? AND path < ?"


async def main() -> None:
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    try:
        root = "/include/linux/dcache.h"
        probe = raw.execute(f"SELECT id FROM vfs_entries WHERE {RANGE} LIMIT 1025", (root + "/", root + "0")).fetchall()
        r = await fs.grep("d_inode", paths=(root,), output_mode="files")
        print(f"a) R2 probe rows for file root {root}: {len(probe)}; vfs grep rows: {len(r.observations)}")
        roots = ("/drivers", "/drivers/md", "/drivers/md/bcache")
        per = [raw.execute(f"SELECT id FROM vfs_entries WHERE {RANGE}", (x + "/", x + "0")).fetchall() for x in roots]
        print(f"b) overlapping roots {roots}: per-root rows {[len(p) for p in per]} sum={sum(map(len, per))} "
              f"distinct={len({i for p in per for i in p})}")
        wide = ("/drivers", "/arch", "/fs", "/include", "/sound", "/tools", "/net")
        where = " OR ".join("(path > ? AND path < ?)" for _ in wide)
        params = [v for x in wide for v in (x + "/", x + "0")]
        tracemalloc.start()
        ids = sorted(i for (i,) in raw.execute(f"SELECT id FROM vfs_entries WHERE kind='file' AND ({where})", params))
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        total = raw.execute("select count(*) from vfs_entries where kind='file'").fetchone()[0]
        print(f"c) range allow-list for {len(wide)} roots: 1 statement, {len(ids)} ids "
              f"({len(ids) / total:.0%} of {total} files), traced peak {peak / 1e6:.1f} MB; "
              f"declared budgets: SCAN_TIER_BUDGET 25000, SQLite membership 32766")
        print(f"   at the reference deployment the same share is {len(ids) / total * 10_000_000:,.0f} ids")
    finally:
        raw.close()
        await fs.close()


asyncio.run(main())
