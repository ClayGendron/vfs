"""Spec 177 probe: how large is the stored payload of a 10,000-row mutation Result, and does an edit replay apply twice?"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Edge, Entry
from vfs.storage.backends.memory import InMemoryStorage

S = Authority.system()
N = 10_000


def size(label, r):
    body = r.model_dump_json(exclude_none=True)
    print(f"{label:<28} ok={r.success!s:<5} rows={len(r.observations):>6} errors={len(r.errors):>6} "
          f"payload_bytes={len(body.encode()):>9} bytes_per_row={len(body.encode()) // max(1, len(r.observations) or len(r.errors))}")


async def main():
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.mkdir("/d", authority=S)
    await fs.mkdir("/m", authority=S)
    await fs.mkdir("/c", authority=S)
    entries = [Entry(path=f"/d/file-{i:05}.md", content=f"body {i}") for i in range(N)]
    size("write 10k created", await fs.write(entries, authority=S))
    size("write 10k replay (updated)", await fs.write(entries, authority=S))
    size("copy 10k", await fs.copy(copies=[(f"/d/file-{i:05}.md", f"/c/file-{i:05}.md") for i in range(N)], authority=S))
    size("move 10k", await fs.move(moves=[(f"/c/file-{i:05}.md", f"/m/file-{i:05}.md") for i in range(N)], authority=S))
    size("move 10k replay (failure)", await fs.move(moves=[(f"/c/file-{i:05}.md", f"/m/file-{i:05}.md") for i in range(N)], authority=S))
    edges = [Edge(source=f"/d/file-{i:05}.md", target=f"/m/file-{i:05}.md", edge_type="cites") for i in range(N)]
    size("mkedge 10k", await fs.mkedge(edges, authority=S))
    obs = (await fs.ls("/m", authority=S)).observations
    size("delete 10k by rows", await fs.delete(observations=obs, authority=S))
    await fs.write(path="/g.md", content="foo", authority=S)
    await fs.edit("/g.md", "foo", "foo!", authority=S)
    await fs.edit("/g.md", "foo", "foo!", authority=S)
    print("edit foo->foo! twice leaves:", repr((await fs.read("/g.md", authority=S)).observations[0].content))
    await fs.close()


asyncio.run(main())
