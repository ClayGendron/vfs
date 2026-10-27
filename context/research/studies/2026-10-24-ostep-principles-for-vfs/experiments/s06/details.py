"""Study 06: the error detail and severity of the non-idempotent replays."""

from __future__ import annotations

import asyncio

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

S = Authority.system()


async def main():
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/e.md", content="hello world", authority=S)
    await fs.write(path="/x.md", content="x", authority=S)
    await fs.edit("/e.md", "world", "there", authority=S)
    for label, r in [
        ("edit replay", await fs.edit("/e.md", "world", "there", authority=S)),
        ("delete", await fs.delete("/x.md", authority=S)),
        ("delete replay", await fs.delete("/x.md", authority=S)),
        ("rmedge absent", await fs.rmedge(source="/e.md", target="/e.md", edge_type="cites", authority=S)),
    ]:
        for e in r.errors:
            print(f"{label:<14} success={r.success} kind={e.kind} severity={e.severity} message={e.message!r} data={e.data}")
    await fs.close()


asyncio.run(main())
