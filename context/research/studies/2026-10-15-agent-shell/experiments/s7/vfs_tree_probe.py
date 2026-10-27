"""S7 experiment 3: the /.vfs tree as a home for session rows -- what the
search verbs, another principal and the trash view do with rows there."""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))
ANON = Authority.anonymous()


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
    row = "/.vfs/sessions/s1/env/X"
    show("alice write /.vfs row", await a.write(path=row, content="1", parents=True))
    show("alice write /.vfs/sessions/s1/history", await a.write(path="/.vfs/sessions/s1/history", content="cd /a\nls\n", parents=True))

    print("A. search verbs vs the reserved tree")
    show("glob **/* (unscoped)", await a.glob("**/*"))
    show("glob X paths=/.vfs", await a.glob("X", paths=("/.vfs",)))
    show("grep ^1$ unscoped", await a.grep("^1$", allow_scan=True))
    show("grep ^1$ paths=/.vfs", await a.grep("^1$", paths=("/.vfs",), allow_scan=True))
    show("read row", await a.read(row))
    show("ls /.vfs/sessions/s1", await a.ls("/.vfs/sessions/s1"))

    print("B. the other principal and anonymous")
    show("bob read row", await b.read(row))
    show("bob ls /.vfs/sessions", await b.ls("/.vfs/sessions"))
    show("anon ls /.vfs/sessions", await fs.ls("/.vfs/sessions", authority=ANON))
    show("anon read row", await fs.read(row, authority=ANON))

    print("C. trash view after delete")
    show("alice delete row", await a.delete(row))
    show("ls /.vfs/trash", await a.ls("/.vfs/trash"))
    show("stat trash view of row", await a.stat("/.vfs/trash/.vfs/sessions/s1/env/X"))
    show("ls /.vfs/sessions/s1/env", await a.ls("/.vfs/sessions/s1/env"))

    print("D. a plain user-space row for comparison")
    show("alice write /sessions/s1/env/Y", await a.write(path="/sessions/s1/env/Y", content="y", parents=True))
    show("alice delete Y", await a.delete("/sessions/s1/env/Y"))
    show("ls /.vfs/trash", await a.ls("/.vfs/trash"))
    show("ls /.vfs/trash/sessions", await a.ls("/.vfs/trash/sessions"))
    show("stat /.vfs/trash/sessions/s1/env/Y", await a.stat("/.vfs/trash/sessions/s1/env/Y"))
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
