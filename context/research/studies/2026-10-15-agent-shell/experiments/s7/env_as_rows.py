"""S7 experiment 2: can session env/cwd/history live as ROWS in the namespace?

Probes the live tree: which candidate homes accept a write, and whether
rows written there are visible to glob/grep (the Plan 9 /env question),
to another principal, and to the trash view after delete.

Run from the vfs repo root:
    uv run python context/research/studies/2026-10-15-agent-shell/experiments/s7/env_as_rows.py
"""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))

CANDIDATES = [
    "/.vfs/sessions/s1/env/X",  # reserved meta tree
    "/.agents/sessions/s1/env/X",  # reserved capability tree, unknown family
    "/.agents/tools/s1/env/X",  # reserved capability tree, known family
    "/sessions/s1/env/X",  # plain user directory
    "/home/alice/.session/env/X",  # a per-principal home
]


def show(label: str, result) -> None:
    if result.success:
        print(f"  {label}: ok rows={[str(o.path) for o in result.observations]}")
    else:
        print(f"  {label}: {'; '.join(f'{e.kind}: {e.message}' for e in result.errors)}")


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    assert (await fs.posture("/", "none", authority=SYSTEM)).success
    assert (await fs.grant("/", "alice", "read_write", authority=SYSTEM)).success
    assert (await fs.grant("/", "bob", "read", authority=SYSTEM)).success
    a, b = fs.session(ALICE), fs.session(BOB)

    print("1. which homes accept an env row (alice, read_write at /)")
    for path in CANDIDATES:
        show(path, await a.write(path=path, content="1", parents=True))

    print("2. visibility of env rows to the search verbs (alice)")
    show("glob **/X", await a.glob("**/X"))
    show("glob /.vfs/**", await a.glob("/.vfs/**"))
    show("grep '^1$'", await a.grep("^1$", allow_scan=True))
    show("tree /", await a.tree("/"))

    print("3. visibility of alice's env rows to bob (read at /)")
    show("bob read /sessions/s1/env/X", await b.read("/sessions/s1/env/X"))
    show("bob glob **/X", await b.glob("**/X"))

    print("4. an env row changed is a version; deleted is a tombstone in the trash view")
    show("alice write X=2", await a.write(path="/sessions/s1/env/X", content="2"))
    show("alice stat X", await a.stat("/sessions/s1/env/X", columns=frozenset({"path", "version"})))
    show("alice delete X", await a.delete("/sessions/s1/env/X"))
    show("alice ls /.vfs/trash/sessions/s1/env", await a.ls("/.vfs/trash/sessions/s1/env"))
    show("alice restore X", await a.restore("/sessions/s1/env/X"))

    print("5. mount table is NOT rows: ls /.vfs/mounts")
    show("ls /.vfs", await a.ls("/.vfs"))
    show("ls /.vfs/mounts", await a.ls("/.vfs/mounts"))
    print("  fs.mounts() ->", [(m.path, m.storage_type) for m in fs.mounts()])
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
