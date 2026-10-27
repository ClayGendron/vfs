"""Probe: can posture and grant rows sit at a /.vfs/tools path that holds no stored row?

Run: uv run python context/research/studies/2026-10-15-agent-shell/experiments/r170/posture_at_view_paths.py
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem


def show(label, r):
    errs = [(e.kind, e.message) for e in r.errors] if r.errors else []
    rows = [(o.path, getattr(o, "kind", None)) for o in (r.observations or [])][:5]
    print(f"{label}: success={r.success} rows={rows} errors={errs}")


async def main() -> None:
    fs = VirtualFileSystem()
    sys = Authority.system()
    alice = Authority.of(Principal("alice"))
    bob = Authority.of(Principal("bob"))

    show("A posture / none", await fs.posture("/", "none", authority=sys))
    show("B posture /.vfs/tools read", await fs.posture("/.vfs/tools", "read", authority=sys))
    show("C grant alice read /.vfs/tools/search (no row)", await fs.grant("/.vfs/tools/search", "alice", "read", authority=sys))
    show("D grants /.vfs/tools/search", await fs.grants("/.vfs/tools/search", authority=sys))
    rd = await fs.grants("/.vfs/tools/search", authority=sys)
    print("   D extras:", {k: v for k, v in (rd.model_dump().items()) if k not in ("observations","errors")})
    show("E alice stat /.vfs/tools/search (no row)", await fs.stat("/.vfs/tools/search", authority=alice))
    show("F system write /.vfs/tools/search (today: lawful?)", await fs.write(path="/.vfs/tools/search", content="manifest", parents=True, authority=sys))
    show("G alice read /.vfs/tools/search", await fs.read("/.vfs/tools/search", authority=alice))
    show("H bob read /.vfs/tools/search", await fs.read("/.vfs/tools/search", authority=bob))
    show("I bob ls /.vfs/tools", await fs.ls("/.vfs/tools", authority=bob))
    show("J alice ls /.vfs (unscoped meta?)", await fs.ls("/.vfs", authority=alice))


asyncio.run(main())
