"""Probe 04: mkdir at a deleted directory's path, a write beneath a deleted directory, and kind changes at a tombstone."""

from __future__ import annotations

import asyncio

from probe_common import ALICE, SYSTEM, entries, make, show


async def main() -> None:
    fs, storage = make()
    await fs.mkdir("/proj/src", parents=True, authority=SYSTEM)
    await fs.write(path="/proj/src/main.py", content="print(1)\n", authority=ALICE)
    await fs.write(path="/proj/notes", content="a file named notes\n", authority=ALICE)
    show("delete /proj/src (directory tree)", await fs.delete("/proj/src", authority=ALICE))
    show("delete /proj/notes (file)", await fs.delete("/proj/notes", authority=ALICE))
    await entries(storage, "/proj")

    print("== mkdir at the deleted directory's path")
    show("mkdir /proj/src", await fs.mkdir("/proj/src", authority=ALICE))
    show("mkdir /proj/src exist_ok=True", await fs.mkdir("/proj/src", exist_ok=True, authority=ALICE))
    show("mkdir /proj/src parents=True", await fs.mkdir("/proj/src", parents=True, authority=ALICE))
    show("mkdir /proj/src as system", await fs.mkdir("/proj/src", authority=SYSTEM))

    print("== a write beneath the deleted directory")
    show("write /proj/src/new.py", await fs.write(path="/proj/src/new.py", content="x\n", authority=ALICE))
    show("write /proj/src/new.py parents=True", await fs.write(path="/proj/src/new.py", content="x\n", parents=True, authority=ALICE))
    show("write /proj/src/main.py (the deleted member's own path)", await fs.write(path="/proj/src/main.py", content="x\n", authority=ALICE))
    show("mkdir /proj/src/deeper parents=True", await fs.mkdir("/proj/src/deeper", parents=True, authority=ALICE))

    print("== a file write at the deleted directory's own path, and a mkdir at a deleted file's path")
    show("write /proj/src as a file", await fs.write(path="/proj/src", content="now a file\n", authority=ALICE))
    show("mkdir /proj/notes (a deleted file sits here)", await fs.mkdir("/proj/notes", authority=ALICE))
    show("write /proj/notes/child.txt parents=True", await fs.write(path="/proj/notes/child.txt", content="x\n", parents=True, authority=ALICE))

    print("== move and copy toward the tombstoned names")
    await fs.mkdir("/proj/other", authority=ALICE)
    show("move /proj/other -> /proj/src", await fs.move("/proj/other", "/proj/src", authority=ALICE))
    show("copy /proj/other -> /proj/src", await fs.copy("/proj/other", "/proj/src", authority=ALICE))
    show("move /proj/other -> /proj/src/inside", await fs.move("/proj/other", "/proj/src/inside", authority=ALICE))

    print("== the only two ways the name comes back")
    show("restore /proj/src", await fs.restore("/proj/src", authority=ALICE))
    show("delete /proj/src again", await fs.delete("/proj/src", authority=ALICE))
    show("sweep /proj/src (destroys the tombstoned tree)", await fs.sweep("/proj/src", authority=SYSTEM))
    show("mkdir /proj/src after the sweep", await fs.mkdir("/proj/src", authority=ALICE))
    await entries(storage, "/proj")
    await fs.close()


asyncio.run(main())
