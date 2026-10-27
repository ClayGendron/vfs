"""Probe: what is vfs's atomic unit of write? (study 01, OSTEP principles)."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage

COMMITS = {"n": 0}
_orig_commit = AsyncSession.commit


async def counting_commit(self):
    COMMITS["n"] += 1
    return await _orig_commit(self)


AsyncSession.commit = counting_commit


async def exists(fs, path):
    r = await fs.stat(path)
    return r.success


async def main():
    # 1. One mount, one batch, one bad entry (missing parent, parents=False).
    fs = VirtualFileSystem(storage=InMemoryStorage())
    r = await fs.write([Entry(path="/a.txt", content="a"), Entry(path="/missing/b.txt", content="b")])
    print("1 single-mount batch with one bad entry: success=", r.success,
          "errors=", [(e.kind, str(e.path)) for e in r.errors],
          "| /a.txt landed?", await exists(fs, "/a.txt"))

    # 2. Two mounts, one batch: good entry on mount A, bad entry on mount B.
    fs2 = VirtualFileSystem(storage=InMemoryStorage())
    await fs2.add_mount(InMemoryStorage(name="b"), "/b")
    r = await fs2.write([Entry(path="/a.txt", content="a"), Entry(path="/b/missing/x.txt", content="x")])
    print("2 cross-mount batch, bad entry on /b only: success=", r.success,
          "errors=", [(e.kind, str(e.path)) for e in r.errors],
          "| /a.txt landed?", await exists(fs2, "/a.txt"))

    # 3. 10,000-entry batch on one mount: how many commits?
    fs3 = VirtualFileSystem(storage=InMemoryStorage())
    await fs3.mkdir("/etl")
    COMMITS["n"] = 0
    r = await fs3.write([Entry(path=f"/etl/f{i:05d}.txt", content=f"row {i}\n") for i in range(10_000)])
    print("3 10,000-entry batch: success=", r.success, "rows=", len(r.observations), "commits=", COMMITS["n"])

    # 4. Same 10,000 plus one bad entry at the end: does anything land?
    fs4 = VirtualFileSystem(storage=InMemoryStorage())
    await fs4.mkdir("/etl")
    COMMITS["n"] = 0
    batch = [Entry(path=f"/etl/f{i:05d}.txt", content=f"row {i}\n") for i in range(10_000)]
    batch.append(Entry(path="/nope/z.txt", content="z"))
    r = await fs4.write(batch)
    ls = await fs4.ls("/etl")
    print("4 10,000 good + 1 bad: success=", r.success, "errors=", len(r.errors),
          "commits=", COMMITS["n"], "| rows now under /etl:", len(ls.observations))
    for f in (fs, fs2, fs3, fs4):
        await f.close()


asyncio.run(main())
