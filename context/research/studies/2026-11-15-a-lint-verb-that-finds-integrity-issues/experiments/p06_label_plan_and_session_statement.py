"""Probe 06: the plan of a label check that seeks only wrong rows, and the one statement every probe session adds."""

from __future__ import annotations

import asyncio

from sqlalchemy import text, update

from lint_common import SYSTEM, StatementCounter, make, plan, run_sql
from vfs.models import Entry

WRONG_IN_REGION = (
    "SELECT path, everyone_level FROM vfs_entries"
    " WHERE everyone_level = :other AND path > :lo AND path < :hi ORDER BY path LIMIT :n"
)


async def main() -> None:
    fs, storage = make()
    batch = [Entry(path=f"/data/d{i // 100:03d}/f{i:05d}.txt", content=f"file {i}\n") for i in range(5_000)]
    assert not (await fs.write(batch, parents=True, authority=SYSTEM)).errors
    await fs.posture("/data/d007", "none", authority=SYSTEM)
    e = storage._host.tables.entry
    await run_sql(
        storage,
        update(e).where(e.c.path == "/data/d007/f00712.txt").values(everyone_level=5),
        update(e).where(e.c.path == "/data/d020/f02001.txt").values(everyone_level=0),
    )
    # Two regions: under /data/d007 the posture gives 0; everywhere else it gives 5.
    regions = [("/data/d007/", "/data/d0070", 0), ("/", "/data/d007", 5), ("/data/d0070", "0", 5)]
    found, statements = [], 0
    with StatementCounter(storage) as counter:
        async with storage._host.session_factory() as session:
            for lo, hi, rank in regions:
                for other in range(6):
                    if other != rank:
                        rows = (await session.execute(text(WRONG_IN_REGION), {"other": other, "lo": lo, "hi": hi, "n": 1000})).all()
                        found.extend((row.path, row.everyone_level, rank) for row in rows)
    print(f"rows in the store: 5,051; statements={counter.statements}; wrong labels found (path, stored, posture gives): {found}")
    print("first statements of the session:", counter.samples[:2])
    for line in await plan(storage, WRONG_IN_REGION, {"other": 5, "lo": "/data/d007/", "hi": "/data/d0070", "n": 1000}):
        print(f"  plan: {line}")
    await fs.close()


asyncio.run(main())
