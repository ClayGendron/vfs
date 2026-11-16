"""Probe 02: restore of a file, of a tree, of one row inside a deleted tree, and onto a path occupied since."""

from __future__ import annotations

import asyncio

from probe_common import ALICE, ANON, BOB, SYSTEM, edges, entries, make, show, versions


async def main() -> None:
    fs, storage = make()
    await fs.mkdir("/d", authority=SYSTEM)
    await fs.write(path="/d/a.txt", content="alpha v1\n", authority=ALICE)
    await fs.write(path="/d/a.txt", content="alpha v2\n", authority=ALICE)
    await fs.write(path="/d/other.txt", content="other\n", authority=ALICE)
    await fs.mkedge(source="/d/a.txt", target="/d/other.txt", edge_type="cites", authority=ALICE)
    await fs.mkedge(source="/d/other.txt", target="/d/a.txt", edge_type="cites", authority=ALICE)
    await fs.mkdir("/t/sub", parents=True, authority=SYSTEM)
    await fs.write(path="/t/x.txt", content="treex\n", authority=ALICE)
    await fs.write(path="/t/sub/y.txt", content="treey\n", authority=BOB)
    await fs.write(path="/t/sub/z.txt", content="treez\n", authority=ALICE)

    print("== 1. restore a file")
    await entries(storage, "/d")
    await versions(storage)
    show("delete /d/a.txt", await fs.delete("/d/a.txt", authority=ALICE))
    await entries(storage, "/d")
    show("restore /d/a.txt as alice", await fs.restore("/d/a.txt", authority=ALICE))
    await entries(storage, "/d")
    await versions(storage)
    await edges(storage)
    show("read after restore", await fs.read("/d/a.txt", authority=ALICE))
    show("traverse outbound /d/other.txt", await fs.traverse("outbound", "/d/other.txt", authority=ALICE))
    show("restore again (live row)", await fs.restore("/d/a.txt", authority=ALICE))
    show("restore a path that never existed", await fs.restore("/d/never.txt", authority=ALICE))
    show("restore by the trash-view address", await fs.restore("/.vfs/trash/d/a.txt", authority=ALICE))

    print("\n== 2. restore a tree; one row deleted earlier keeps its own root")
    show("delete /t/sub/z.txt (own root)", await fs.delete("/t/sub/z.txt", authority=ALICE))
    show("delete /t", await fs.delete("/t", authority=SYSTEM))
    await entries(storage, "/t")
    print(" -- one row inside the deleted tree")
    show("restore /t/x.txt (member of /t's set)", await fs.restore("/t/x.txt", authority=ALICE))
    show("restore /t/sub (member directory)", await fs.restore("/t/sub", authority=SYSTEM))
    show("restore /t/sub/z.txt (own root, parent still deleted)", await fs.restore("/t/sub/z.txt", authority=ALICE))
    print(" -- the tree")
    show("restore /t as anonymous", await fs.restore("/t", authority=ANON))
    show("restore /t as alice (holds read_write through everyone; owns two of the files)", await fs.restore("/t", authority=ALICE))
    await entries(storage, "/t")
    show("ls /t/sub after tree restore", await fs.ls("/t/sub", authority=ALICE))
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=ALICE))
    show("restore /t/sub/z.txt now", await fs.restore("/t/sub/z.txt", authority=ALICE))
    await entries(storage, "/t")

    print("\n== 3. restore onto a path occupied since the delete")
    show("delete /d/a.txt", await fs.delete("/d/a.txt", authority=ALICE))
    show("move /d/other.txt -> /d/a.txt (try to occupy the deleted path with another row)", await fs.move("/d/other.txt", "/d/a.txt", authority=ALICE))
    show("copy /d/other.txt -> /d/a.txt", await fs.copy("/d/other.txt", "/d/a.txt", authority=ALICE))
    show("mkdir /d/a.txt", await fs.mkdir("/d/a.txt", authority=ALICE))
    show("write /d/a.txt overwrite=False (the only way to occupy: a revive)", await fs.write(path="/d/a.txt", content="fresh body\n", overwrite=False, authority=BOB))
    await entries(storage, "/d")
    show("restore /d/a.txt after the revive", await fs.restore("/d/a.txt", authority=ALICE))
    show("read /d/a.txt", await fs.read("/d/a.txt", authority=ALICE))
    await versions(storage)

    print("\n== 4. restore in a closed region: who may")
    await fs.mkdir("/p", authority=SYSTEM)
    await fs.posture("/p", "none", authority=SYSTEM)
    await fs.grant("/p", "alice", "add", authority=SYSTEM)
    await fs.grant("/p", "carol", "read_write", authority=SYSTEM)
    show("write /p/mine.txt as alice (add)", await fs.write(path="/p/mine.txt", content="mine\n", authority=ALICE))
    show("delete /p/mine.txt as alice (add, owner)", await fs.delete("/p/mine.txt", authority=ALICE))
    await entries(storage, "/p")
    show("restore /p/mine.txt as bob (nothing)", await fs.restore("/p/mine.txt", authority=BOB))
    show("restore /p/mine.txt as anonymous", await fs.restore("/p/mine.txt", authority=ANON))
    show("restore /p/mine.txt as alice (add, owner)", await fs.restore("/p/mine.txt", authority=ALICE))
    await entries(storage, "/p")
    await fs.close()


asyncio.run(main())
