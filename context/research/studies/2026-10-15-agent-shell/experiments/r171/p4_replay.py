"""Probe 4 for the spec 171 review: what a re-issued mutation reports today.

Run from the repo root:
    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r171/p4_replay.py
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority
from vfs.base import VirtualFileSystem


async def main() -> None:
    fs = VirtualFileSystem()
    s = Authority.system()
    await fs.write(path="/a.md", content="a", authority=s)
    await fs.write(path="/b.md", content="b", authority=s)
    steps = [
        ("write same", lambda: fs.write(path="/a.md", content="a", authority=s)),
        ("mkedge", lambda: fs.mkedge(source="/a.md", target="/b.md", edge_type="cites", authority=s)),
        ("mkedge again", lambda: fs.mkedge(source="/a.md", target="/b.md", edge_type="cites", authority=s)),
        ("move", lambda: fs.move("/b.md", "/c.md", authority=s)),
        ("move again", lambda: fs.move("/b.md", "/c.md", authority=s)),
        ("delete", lambda: fs.delete("/c.md", authority=s)),
        ("delete again", lambda: fs.delete("/c.md", authority=s)),
    ]
    for label, step in steps:
        r = await step()
        print(label, r.success, [str(e.kind) for e in r.errors], [o.status for o in r.observations])


asyncio.run(main())
