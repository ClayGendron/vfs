"""Probe 01: delete a file and a directory tree; what every read verb then returns, by caller; the trash view."""

from __future__ import annotations

import asyncio

from probe_common import ALICE, ANON, BOB, CALLERS, SYSTEM, edges, entries, make, show, versions


async def reads_at(fs, label: str, path: str, parent: str, needle: str, who) -> None:  # noqa: ANN001
    print(f" -- {label}")
    show(f"read {path}", await fs.read(path, authority=who))
    show(f"stat {path}", await fs.stat(path, authority=who))
    show(f"ls {parent}", await fs.ls(parent, authority=who))
    show(f"tree {parent}", await fs.tree(parent, authority=who))
    show(f"glob {parent}/**", await fs.glob(f"{parent}/**", authority=who))
    show(f"grep {needle}", await fs.grep(needle, authority=who))
    show(f"search {needle}", await fs.search(needle, authority=who))


async def trash_reads(fs, label: str, path: str, needle: str, who) -> None:  # noqa: ANN001
    print(f" -- trash view, {label}")
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=who))
    show("tree /.vfs/trash", await fs.tree("/.vfs/trash", authority=who))
    show(f"stat /.vfs/trash{path}", await fs.stat(f"/.vfs/trash{path}", authority=who))
    show(f"read /.vfs/trash{path}", await fs.read(f"/.vfs/trash{path}", authority=who))
    show("glob /.vfs/trash/**", await fs.glob("/.vfs/trash/**", authority=who))
    show(f"grep {needle} paths=trash", await fs.grep(needle, paths=("/.vfs/trash",), authority=who))
    show(f"search {needle} paths=trash", await fs.search(needle, paths=("/.vfs/trash",), authority=who))


async def main() -> None:
    fs, storage = make()
    print("== setup: an open region /d and /t (everyone read_write), a closed region /p (everyone none, alice read_write)")
    await fs.mkdir("/d", authority=SYSTEM)
    await fs.write(path="/d/a.txt", content="alpha needle one\n", authority=ALICE)
    await fs.write(path="/d/keep.txt", content="keeper needle\n", authority=ALICE)
    await fs.mkdir("/t/sub", parents=True, authority=SYSTEM)
    await fs.write(path="/t/x.txt", content="treex needle\n", authority=ALICE)
    await fs.write(path="/t/sub/y.txt", content="treey needle\n", authority=BOB)
    await fs.write(path="/t/sub/z.txt", content="treez needle\n", authority=ALICE)
    await fs.mkdir("/p", authority=SYSTEM)
    show("posture /p none", await fs.posture("/p", "none", authority=SYSTEM))
    show("grant alice read_write /p", await fs.grant("/p", "alice", "read_write", authority=SYSTEM))
    show("write /p/secret.txt as alice", await fs.write(path="/p/secret.txt", content="secret needle\n", authority=ALICE))
    show("mkedge a.txt -> keep.txt", await fs.mkedge(source="/d/a.txt", target="/d/keep.txt", edge_type="cites", authority=ALICE))
    show("mkedge keep.txt -> a.txt", await fs.mkedge(source="/d/keep.txt", target="/d/a.txt", edge_type="cites", authority=ALICE))
    await entries(storage)

    print("\n== 1. delete a file: /d/a.txt as alice")
    show("delete /d/a.txt", await fs.delete("/d/a.txt", authority=ALICE))
    await entries(storage, "/d")
    await edges(storage)
    await versions(storage)
    for name, who in CALLERS.items():
        await reads_at(fs, f"after delete, caller={name}", "/d/a.txt", "/d", "needle", who)
    for name, who in CALLERS.items():
        await trash_reads(fs, f"caller={name}", "/d/a.txt", "needle", who)
    show("traverse outbound from /d/keep.txt (edge to the deleted file)", await fs.traverse("outbound", "/d/keep.txt", authority=ALICE))
    show("traverse outbound from /d/a.txt (deleted seed)", await fs.traverse("outbound", "/d/a.txt", authority=ALICE))
    show("delete /d/a.txt again", await fs.delete("/d/a.txt", authority=ALICE))
    show("edit the deleted file", await fs.edit("/d/a.txt", old="alpha", new="beta", authority=ALICE))

    print("\n== 2. delete a directory tree: /t")
    show("delete /t cascade=False", await fs.delete("/t", cascade=False, authority=SYSTEM))
    show("delete /t/sub/z.txt first (its own root)", await fs.delete("/t/sub/z.txt", authority=ALICE))
    show("delete /t (cascade) as system", await fs.delete("/t", authority=SYSTEM))
    await entries(storage, "/t")
    for name, who in (("system", SYSTEM), ("alice", ALICE), ("anonymous", ANON)):
        print(f" -- after tree delete, caller={name}")
        show("read /t/x.txt", await fs.read("/t/x.txt", authority=who))
        show("stat /t", await fs.stat("/t", authority=who))
        show("ls /t", await fs.ls("/t", authority=who))
        show("ls /", await fs.ls("/", authority=who))
        show("tree /t", await fs.tree("/t", authority=who))
        show("glob /t/**", await fs.glob("/t/**", authority=who))
        show("grep treex", await fs.grep("treex", authority=who))
        show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=who))
        show("ls /.vfs/trash/t", await fs.ls("/.vfs/trash/t", authority=who))
        show("tree /.vfs/trash", await fs.tree("/.vfs/trash", authority=who))
        show("read /.vfs/trash/t/sub/y.txt", await fs.read("/.vfs/trash/t/sub/y.txt", authority=who))

    print("\n== 3. delete in the closed region: /p/secret.txt as alice; what bob and anonymous then learn")
    show("delete /p/secret.txt as bob (no rights)", await fs.delete("/p/secret.txt", authority=BOB))
    show("delete /p/secret.txt as alice", await fs.delete("/p/secret.txt", authority=ALICE))
    await entries(storage, "/p")
    for name, who in CALLERS.items():
        print(f" -- caller={name}")
        show("read /p/secret.txt", await fs.read("/p/secret.txt", authority=who))
        show("stat /p/secret.txt", await fs.stat("/p/secret.txt", authority=who))
        show("read /.vfs/trash/p/secret.txt", await fs.read("/.vfs/trash/p/secret.txt", authority=who))
        show("ls /.vfs/trash/p", await fs.ls("/.vfs/trash/p", authority=who))
        show("grep secret paths=trash", await fs.grep("secret", paths=("/.vfs/trash",), authority=who))
        show("restore /p/secret.txt (dry look: expect refusal for non-holders)", await fs.stat("/.vfs/trash/p/secret.txt", authority=who))
    await fs.close()


asyncio.run(main())
