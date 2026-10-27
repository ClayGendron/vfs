"""Spec 177 probe: how far does stdlib zlib shrink a 10,000-row write Result's stored payload? Bytes only, no clocks."""

from __future__ import annotations

import asyncio
import zlib

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage

S = Authority.system()


async def main():
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.mkdir("/d", authority=S)
    r = await fs.write([Entry(path=f"/d/file-{i:05}.md", content=f"body {i}") for i in range(10_000)], authority=S)
    raw = r.model_dump_json(exclude_none=True).encode()
    for level in (1, 6):
        packed = zlib.compress(raw, level)
        print(f"zlib level {level}: raw={len(raw)} packed={len(packed)} ratio={len(raw) / len(packed):.1f}x")
    print("one row:", r.observations[0].model_dump_json(exclude_none=True))
    await fs.close()


asyncio.run(main())
