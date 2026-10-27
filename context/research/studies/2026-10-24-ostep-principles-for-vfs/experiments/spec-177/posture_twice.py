"""Spec 177 probe: what a replayed posture reports in its relabel extra."""

from __future__ import annotations

import asyncio

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

S = Authority.system()


async def main():
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.mkdir("/d", authority=S)
    for i in range(5):
        await fs.write(path=f"/d/{i}.md", content="x", authority=S)
    for n in (1, 2):
        r = await fs.posture("/d", "read", authority=S)
        print(f"posture #{n}: ok={r.success} relabel={(r.model_extra or {}).get('relabel')}")
    await fs.close()


asyncio.run(main())
