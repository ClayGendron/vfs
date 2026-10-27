"""Probe: can the router learn a caller's level at a path that holds no row, through public verbs?

Run: uv run python context/research/studies/2026-10-15-agent-shell/experiments/r170/grants_as_caller_at_view_path.py
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem


async def main() -> None:
    fs = VirtualFileSystem()
    sys = Authority.system()
    await fs.posture("/", "none", authority=sys)
    await fs.posture("/.vfs/tools", "list", authority=sys)
    await fs.grant("/.vfs/tools/search", "alice", "read", authority=sys)
    for who, auth in (("alice", Authority.of(Principal("alice"))), ("bob", Authority.of(Principal("bob"))), ("anonymous", Authority.anonymous())):
        r = await fs.grants("/.vfs/tools/search", authority=auth)
        rows = [(g["principal_id"], g["path_prefix"], g["level"]) for g in (r.model_dump().get("grants") or [])]
        print(f"{who}: success={r.success} errors={[e.kind.value for e in r.errors]} rows={rows}")
    fresh = VirtualFileSystem()
    r = await fresh.grants("/.vfs/tools/search", authority=Authority.anonymous())
    print("fresh node, anonymous:", r.success, [e.kind.value for e in r.errors], r.model_dump().get("grants"))
    r = await fresh.grants("/.vfs/tools/search", authority=Authority.of(Principal("bob")))
    print("fresh node, bob:", r.success, [e.kind.value for e in r.errors], r.model_dump().get("grants"))


asyncio.run(main())
