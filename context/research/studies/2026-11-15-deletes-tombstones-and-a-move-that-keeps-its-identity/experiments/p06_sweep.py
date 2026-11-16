"""Probe 06: sweep at the trash view and at a live path; what a sweep of a live directory destroys; who may sweep."""

from __future__ import annotations

import asyncio

from probe_common import ALICE, ANON, BOB, SYSTEM, entries, make, show, table_counts
from vfs import AsyncVirtualFileSystem, InMemoryStorage


async def seed(fs) -> None:  # noqa: ANN001
    await fs.mkdir("/work/sub", parents=True, authority=SYSTEM)
    await fs.write(path="/work/a.txt", content="alpha v1\n", authority=ALICE)
    await fs.write(path="/work/a.txt", content="alpha v2\n", authority=ALICE)
    await fs.write(path="/work/sub/b.txt", content="bravo\n", authority=BOB)
    await fs.write(path="/keep.txt", content="keeper\n", authority=ALICE)
    await fs.mkedge(source="/keep.txt", target="/work/a.txt", edge_type="cites", authority=ALICE)
    await fs.mkedge(source="/work/a.txt", target="/work/sub/b.txt", edge_type="cites", authority=ALICE)


async def main() -> None:
    print("== 1. sweep at the trash view, retention 90 days (the default)")
    fs, storage = make()
    await seed(fs)
    await fs.delete("/work/a.txt", authority=ALICE)
    print(f"  table rows before: {await table_counts(storage)}")
    show("sweep() default address", await fs.sweep(authority=SYSTEM))
    show("sweep /.vfs/trash", await fs.sweep("/.vfs/trash", authority=SYSTEM))
    print(f"  table rows after:  {await table_counts(storage)}")
    show("sweep /.vfs/trash/work/a.txt (one row through the view)", await fs.sweep("/.vfs/trash/work/a.txt", authority=SYSTEM))
    show("sweep /work/a.txt (the tombstoned row by its own path)", await fs.sweep("/work/a.txt", authority=SYSTEM))
    print(f"  table rows after:  {await table_counts(storage)}")
    show("restore /work/a.txt after that sweep", await fs.restore("/work/a.txt", authority=ALICE))
    await fs.close()

    print("\n== 2. sweep at the trash view, retention 0 days")
    storage = InMemoryStorage(trash_days=0)
    fs = AsyncVirtualFileSystem(storage=storage)
    await seed(fs)
    await fs.delete("/work/a.txt", authority=ALICE)
    await fs.delete("/work/sub", authority=ALICE)
    print(f"  table rows before: {await table_counts(storage)}")
    show("sweep /.vfs/trash as alice (everyone holds read_write here)", await fs.sweep("/.vfs/trash", authority=ALICE))
    print(f"  table rows after:  {await table_counts(storage)}")
    await entries(storage)
    await fs.close()

    print("\n== 3. sweep at a live path: what it destroys, and whether anything warns first")
    fs, storage = make()
    await seed(fs)
    print(f"  table rows before: {await table_counts(storage)}")
    await entries(storage)
    result = show("sweep /work (a live directory holding live files) as system", await fs.sweep("/work", authority=SYSTEM))
    print(f"  full result: ops={result.ops} observations={len(result.observations)} errors={result.errors}")
    print(f"  table rows after:  {await table_counts(storage)}")
    await entries(storage)
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=SYSTEM))
    show("restore /work", await fs.restore("/work", authority=SYSTEM))
    show("read /work/a.txt", await fs.read("/work/a.txt", authority=SYSTEM))
    show("traverse outbound /keep.txt (its edge pointed into /work)", await fs.traverse("outbound", "/keep.txt", authority=ALICE))
    show("sweep /", await fs.sweep("/", authority=SYSTEM))
    show("sweep a path that does not exist", await fs.sweep("/nothing", authority=SYSTEM))
    await fs.close()

    print("\n== 4. who may sweep a live file")
    fs, storage = make()
    await seed(fs)
    show("sweep /keep.txt as anonymous (everyone read_write)", await fs.sweep("/keep.txt", authority=ANON))
    show("read /keep.txt", await fs.read("/keep.txt", authority=ALICE))
    show("sweep /work/a.txt as bob (not the owner; everyone read_write)", await fs.sweep("/work/a.txt", authority=BOB))
    show("read /work/a.txt", await fs.read("/work/a.txt", authority=ALICE))
    await fs.mkdir("/p", authority=SYSTEM)
    await fs.posture("/p", "none", authority=SYSTEM)
    for level in ("add", "contribute", "read_write"):
        await fs.grant("/p", "alice", level, authority=SYSTEM)
        await fs.grant("/p", "bob", level, authority=SYSTEM)
        await fs.write(path=f"/p/{level}.txt", content="x\n", authority=ALICE)
        show(f"alice (owner) holds {level}: delete", await fs.delete(f"/p/{level}.txt", authority=ALICE))
        show(f"alice (owner) holds {level}: restore", await fs.restore(f"/p/{level}.txt", authority=ALICE))
        show(f"bob (not owner) holds {level}: delete", await fs.delete(f"/p/{level}.txt", authority=BOB))
        show(f"bob (not owner) holds {level}: restore", await fs.restore(f"/p/{level}.txt", authority=BOB))
        show(f"bob (not owner) holds {level}: sweep", await fs.sweep(f"/p/{level}.txt", authority=BOB))
        show(f"alice (owner) holds {level}: sweep", await fs.sweep(f"/p/{level}.txt", authority=ALICE))
        show(f"alice holds {level}: sweep /.vfs/trash", await fs.sweep("/.vfs/trash", authority=ALICE))
    await fs.close()


asyncio.run(main())
