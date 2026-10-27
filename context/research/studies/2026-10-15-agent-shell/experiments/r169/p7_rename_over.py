"""Probe 7: does `move` replace an existing destination, as POSIX rename must? (spec 169 review)"""

from __future__ import annotations

import asyncio

from vfs.base import VirtualFileSystem


async def main() -> None:
    fs = VirtualFileSystem()
    await fs.write(path="/d/out.txt", content="old", parents=True)
    await fs.write(path="/d/.out.txt.tmp", content="new")
    r = await fs.move("/d/.out.txt.tmp", "/d/out.txt")
    e = r.errors[0] if r.errors else None
    print(f"move tmp -> existing: success={r.success} kind={e.kind if e else None} msg={e.message if e else ''}")
    print("out.txt now:", (await fs.read("/d/out.txt")).first().content)
    await fs.close()


asyncio.run(main())
