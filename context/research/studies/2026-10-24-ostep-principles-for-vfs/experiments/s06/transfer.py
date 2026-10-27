"""Study 06: what a replayed move or copy tells the caller, and a stale whole-body write vs a stale edit."""

from __future__ import annotations

import asyncio

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

S = Authority.system()


def show(label, r):
    print(label, r.success, [(str(e.kind), str(e.severity), e.message, e.data) for e in r.errors])


async def main():
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/y.md", content="y", authority=S)
    await fs.move("/y.md", "/z.md", authority=S)
    show("move replay:", await fs.move("/y.md", "/z.md", authority=S))
    await fs.copy("/z.md", "/w.md", authority=S)
    show("copy replay:", await fs.copy("/z.md", "/w.md", authority=S))

    # Two agents hold the same cached body (their context windows).
    await fs.write(path="/n.md", content="alpha\nbeta\n", authority=S)
    cached = (await fs.read("/n.md", authority=S)).observations[0].content
    await fs.edit("/n.md", "beta", "BETA", authority=S)  # agent B lands first
    show("agent A stale edit alpha->ALPHA:", await fs.edit("/n.md", "alpha", "ALPHA", authority=S))
    show("agent A stale edit beta->gamma:", await fs.edit("/n.md", "beta", "gamma", authority=S))
    await fs.write(path="/n.md", content=cached.replace("alpha", "ALPHA2"), authority=S)  # whole-body from stale cache
    print("after stale whole-body write:", repr((await fs.read("/n.md", authority=S)).observations[0].content))
    await fs.close()


asyncio.run(main())
