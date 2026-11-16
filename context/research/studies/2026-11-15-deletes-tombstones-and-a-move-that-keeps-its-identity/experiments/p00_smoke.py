"""Smoke probe: learn the result shapes before the real probes are written."""

from __future__ import annotations

import asyncio

from probe_common import ALICE, SYSTEM, edges, entries, grants, make, show, versions


async def main() -> None:
    fs, storage = make()
    show("mkdir /d", await fs.mkdir("/d", authority=SYSTEM))
    show("write /d/a.txt", await fs.write(path="/d/a.txt", content="alpha one\n", authority=ALICE))
    show("read", await fs.read("/d/a.txt", authority=ALICE))
    show("stat", await fs.stat("/d/a.txt", authority=ALICE))
    show("ls /d", await fs.ls("/d", authority=ALICE))
    show("tree /", await fs.tree("/", authority=ALICE))
    show("glob", await fs.glob("**/*.txt", authority=ALICE))
    show("grep", await fs.grep("alpha", authority=ALICE))
    r = await fs.search("alpha", authority=ALICE)
    show("search", r)
    show("grants /", await fs.grants("/", authority=SYSTEM))
    print(repr(await fs.grants("/", authority=SYSTEM))[:600])
    await entries(storage)
    await versions(storage)
    await edges(storage, include_fs=True)
    await grants(storage)
    print(type(storage).__mro__[1].__name__, [n for n in dir(storage) if "rebuild" in n or "index" in n])
    await fs.close()


asyncio.run(main())
