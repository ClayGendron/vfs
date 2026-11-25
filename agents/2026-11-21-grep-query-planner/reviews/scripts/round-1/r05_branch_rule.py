"""Decision 4's branch rule: with U <= SCAN_TIER_BUDGET the range-scoped ladder is taken whatever the scope's size.

Two ladder plans, prototyped by replacing grep-module functions in this process:
  ranged   : no allow-list; the candidate fetch carries the roots' range as pushdown (decision 4, second bullet).
  allowed  : the allow-list built by range (decision 2's spelling), met by the kernel before the cap (third bullet).
For each, the ids the candidate entry fetch resolves, its statements, the rows it returns, and the body bytes fetched
are counted exactly; wall time is the median of 7 warm runs and is marked with the load average.
"""
from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time

from sqlalchemy import and_, event, or_, select

import vfs.storage.backends.database.backend as backend_module
import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, DatabaseStorage

DB = sys.argv[1]
MODE = ["ranged"]
ROOTS: list[str] = []
C: dict = {}
real_rows, real_push, real_entries, real_content = (backend_module.grep_rows, g.pushdown_terms,
                                                    g._entries_for_docs, g.content_for_entries)  # fmt: skip


async def grep_rows(*a, **k):
    ROOTS[:] = [str(r) for r in k["scope"].live]
    return await real_rows(*a, **k)


def rng(entry):
    return or_(*(or_(entry.c.path == r, and_(entry.c.path > r + "/", entry.c.path < r + "0")) for r in ROOTS))


async def allow(session, tables, profile, mb, channel, **k):
    if MODE[0] == "ranged":
        return None
    e = tables.entry
    stmt = select(e.c.id).where(e.c.kind == "file", rng(e))
    C["allow_stmts"] = C.get("allow_stmts", 0) + 1
    ids = sorted(row.id for row in await session.execute(stmt))
    C["allow_ids"] = len(ids)
    return ids


def push(entry, *a, **k):
    pd = real_push(entry, *a, **k)
    return g.Pushdown((*pd.terms, rng(entry)), pd.binds + 3 * len(ROOTS)) if MODE[0] == "ranged" else pd


async def entries(session, tables, profile, mb, doc_ids, fetched, pushdown):
    rows = await real_entries(session, tables, profile, mb, doc_ids, fetched, pushdown)
    C["fetch_ids"] = C.get("fetch_ids", 0) + len(doc_ids)
    C["fetch_rows"] = C.get("fetch_rows", 0) + len(rows)
    return rows


async def content(session, tables, profile, mb, ids):
    out = await real_content(session, tables, profile, mb, ids)
    C["body_bytes"] = C.get("body_bytes", 0) + sum(len(v) for v in out.values())
    return out


# Disable the existing defer so both plans run the ladder as decision 4 describes.
g._ladder_defers = lambda *a: False
backend_module.grep_rows, g.allow_list_ids, g.pushdown_terms = grep_rows, allow, push
g._entries_for_docs, g.content_for_entries = entries, content
SCOPES = ["/drivers/atm", "/drivers/md", "/drivers/gpu/drm/amd/display/dc", "/drivers/media", "/drivers/gpu"]
PATTERNS = ["xyzzy_no_such_symbol_42", "i_count", "kmalloc|kfree", "-EINVAL", "MODULE_LICENSE"]


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    n = [0]
    event.listen(storage.engine.sync_engine, "before_cursor_execute", lambda *_: n.__setitem__(0, n[0] + 1))
    try:
        await fs.stat("/fs")
        print("load at start", os.getloadavg())
        for root in SCOPES:
            for pattern in PATTERNS:
                out, rows = [], {}
                for mode in ("ranged", "allowed"):
                    MODE[0] = mode
                    times = []
                    for i in range(8):
                        C.clear()
                        before = n[0]
                        t0 = time.perf_counter()
                        r = await fs.grep(pattern, paths=(root,), output_mode="files")
                        if i:
                            times.append((time.perf_counter() - t0) * 1000)
                    rows[mode] = sorted(str(o.path) for o in r.observations)
                    out.append(f"{mode}: fetch_ids={C.get('fetch_ids', 0):6} allow_ids={C.get('allow_ids', '-'):>6} "
                               f"bytes={C.get('body_bytes', 0) // 1024:6}KB stmts={n[0] - before:2} "
                               f"{statistics.median(times):6.1f}ms")
                same = "same" if rows["ranged"] == rows["allowed"] else "DIFF"
                print(f"{root:32} {pattern:24} {same} {len(rows['ranged']):4}r | " + " | ".join(out),
                      f"load={os.getloadavg()[0]:.1f}", flush=True)
    finally:
        await fs.close()


asyncio.run(main())
