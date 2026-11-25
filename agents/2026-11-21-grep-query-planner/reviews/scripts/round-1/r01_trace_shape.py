"""What grep_rows receives for each scope shape: globs, scope roots/arms, composed plan, allow-list arms and size."""
from __future__ import annotations

import asyncio
import sys

import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, DatabaseStorage

DB = sys.argv[1]
seen: dict = {}
real_rows = g.grep_rows
real_allow = g.allow_list_ids


async def rows(*a, **k):
    seen["globs"] = k["globs"]
    sc = k.get("scope")
    seen["scope"] = None if sc is None else (sc.live, sc.trashed, sc.channel.arms)
    seen["composed"] = None if sc is None else sc.composed(trashed=False)
    return await real_rows(*a, **k)


async def allow(session, tables, profile, mb, channel, **k):
    ids = await real_allow(session, tables, profile, mb, channel, **k)
    seen["arms"] = [(a.pattern, sorted(a.segments), a.name) for a in channel.arms]
    seen["allow"] = None if ids is None else len(ids)
    return ids


g.grep_rows = rows
g.allow_list_ids = allow
import vfs.storage.backends.database.backend as b  # noqa: E402
b.grep_rows = rows

CASES = [
    dict(paths=("/drivers/atm",)),
    dict(paths=("/include/linux/dcache.h",)),
    dict(paths=("/fs/open.c", "/fs/read_write.c")),
    dict(paths=("/drivers/atm", "/mm/tests")),
    dict(paths=("/drivers/atm",), globs=("*.c",)),
    dict(globs=("/drivers/atm/**",)),
    dict(paths=("/drivers",), globs=("**/atm/*.h",)),
]


async def main() -> None:
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    try:
        for case in CASES:
            seen.clear()
            r = await fs.grep("atm_dev", output_mode="files", **case)
            print(case)
            print("   rows", len(r.observations), "errors", [e.message[:60] for e in r.errors])
            for key in ("globs", "scope", "composed", "arms", "allow"):
                print("  ", key, seen.get(key))
    finally:
        await fs.close()


asyncio.run(main())
