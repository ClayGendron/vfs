"""Probe 4: the error kinds a read-first `path_open` would classify from (spec 169 review)."""

from __future__ import annotations

import asyncio

from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

COLS = frozenset({"content", "data", "kind", "size_bytes", "mime_type", "version"})


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/data/in.txt", content="x", parents=True)
    await fs.mkdir("/data/sub")
    for p in ["/data/in.txt", "/data/sub", "/data/nope.txt", "/data/in.txt/child", "/nodir/x.txt"]:
        r = await fs.read(p, columns=COLS)
        e = r.errors[0] if r.errors else None
        print(f"read {p:22} success={r.success} kind={e.kind if e else None} err.path={e.path if e else None} data={e.data if e else None}")
    r = await fs.read("/data/sub/../in.txt", columns=COLS)
    print(f"read with '..': success={r.success} rows={[str(o.path) for o in r.observations]}")
    await fs.close()


asyncio.run(main())
