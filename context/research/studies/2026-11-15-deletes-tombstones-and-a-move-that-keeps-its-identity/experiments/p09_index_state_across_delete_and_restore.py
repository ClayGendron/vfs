"""Probe 09: what a delete and a restore do to the index state of a tree, counted in rows awaiting the index pass."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from probe_common import ALICE, SYSTEM, make, show
from vfs.models import Entry


async def flags(storage, prefix: str) -> str:  # noqa: ANN001
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        stmt = (
            select(entry.c.kind, entry.c.chunked, entry.c.encoded, func.count())
            .where(entry.c.path.like(prefix + "/%"))
            .group_by(entry.c.kind, entry.c.chunked, entry.c.encoded)
            .order_by(entry.c.kind, entry.c.chunked, entry.c.encoded)
        )
        found = (await session.execute(stmt)).all()
    return ", ".join(f"{kind} chunked={chunked} encoded={encoded}: {count}" for kind, chunked, encoded, count in found)


async def main() -> None:
    fs, storage = make()
    batch = [Entry(path=f"/tree/d{i}/f{j:03d}.txt", content=f"needle body {i} {j}\nsecond line\n") for i in range(5) for j in range(40)]
    assert not (await fs.write(batch, parents=True, authority=ALICE)).errors
    print(f"  after write:    {await flags(storage, '/tree')}")
    result = await storage.rebuild()
    print(f"  rebuild errors: {result.errors}")
    print(f"  after rebuild:  {await flags(storage, '/tree')}")
    show("grep needle (count)", await fs.grep("needle body 3 7", authority=ALICE))
    assert not (await fs.delete("/tree", authority=SYSTEM)).errors
    print(f"  after delete:   {await flags(storage, '/tree')}")
    assert not (await fs.restore("/tree", authority=SYSTEM)).errors
    print(f"  after restore:  {await flags(storage, '/tree')}")
    show("grep needle after restore", await fs.grep("needle body 3 7", authority=ALICE))
    result = await storage.rebuild()
    print(f"  after 2nd rebuild: {await flags(storage, '/tree')}")
    print("  -- a move of the same tree, for comparison")
    assert not (await fs.move("/tree", "/tree2", authority=ALICE)).errors
    print(f"  after move:     {await flags(storage, '/tree2')}")
    await fs.close()


asyncio.run(main())
