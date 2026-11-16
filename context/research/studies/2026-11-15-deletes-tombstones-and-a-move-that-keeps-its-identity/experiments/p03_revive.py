"""Probe 03: delete a file, then write a new one at the same path, as the same caller and as a different one."""

from __future__ import annotations

import asyncio

from sqlalchemy import select, update

from probe_common import ALIAS, ALICE, ANON, BOB, CAROL, SYSTEM, edges, entries, grants, make, show, versions


async def external_ids(storage, prefix: str) -> None:  # noqa: ANN001
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as conn:
        stmt = select(entry.c.entry_id, entry.c.path, entry.c.external_id, entry.c.created_at, entry.c.updated_at)
        for row in (await conn.execute(stmt.where(entry.c.path.like(prefix + "%")))).mappings():
            print(
                f"    id={ALIAS.of(row['entry_id'])} path={row['path']} external_id={row['external_id']} "
                f"created_at==updated_at: {row['created_at'] == row['updated_at']}"
            )


async def main() -> None:
    fs, storage = make()
    await fs.mkdir("/d", authority=SYSTEM)
    print("== setup: alice writes /d/a.txt twice, links it both ways, and holds a grant on its exact path")
    await fs.write(path="/d/a.txt", content="alice private draft v1\n", authority=ALICE)
    await fs.write(path="/d/a.txt", content="alice private draft v2\n", authority=ALICE)
    await fs.write(path="/d/other.txt", content="other\n", authority=ALICE)
    await fs.mkedge(source="/d/a.txt", target="/d/other.txt", edge_type="cites", authority=ALICE)
    await fs.mkedge(source="/d/other.txt", target="/d/a.txt", edge_type="cites", authority=ALICE)
    show("grant carol read at /d/a.txt", await fs.grant("/d/a.txt", "carol", "read", authority=SYSTEM))
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        await session.execute(update(entry).where(entry.c.path == "/d/a.txt").values(external_id="ext-alice-001"))
        await session.commit()
    await entries(storage, "/d")
    await versions(storage)
    await edges(storage)
    await grants(storage)
    await external_ids(storage, "/d/a")

    print("\n== 1. same caller: alice deletes, alice writes a new file at the path")
    show("delete", await fs.delete("/d/a.txt", authority=ALICE))
    show("write (same caller)", await fs.write(path="/d/a.txt", content="alice new file\n", authority=ALICE))
    await entries(storage, "/d")
    await versions(storage)
    await edges(storage)
    show("restore after the revive", await fs.restore("/d/a.txt", authority=ALICE))
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=ALICE))

    print("\n== 2. different caller, open region: alice deletes, bob writes a new file at the path")
    show("delete as alice", await fs.delete("/d/a.txt", authority=ALICE))
    show("write as bob, overwrite=False", await fs.write(path="/d/a.txt", content="bob brand new file\n", overwrite=False, authority=BOB))
    await entries(storage, "/d")
    await versions(storage)
    await edges(storage)
    await grants(storage)
    await external_ids(storage, "/d/a")
    show("traverse inbound /d/a.txt as bob", await fs.traverse("inbound", "/d/a.txt", authority=BOB))
    show("traverse outbound /d/a.txt as bob", await fs.traverse("outbound", "/d/a.txt", authority=BOB))
    show("restore as alice (her deleted file)", await fs.restore("/d/a.txt", authority=ALICE))
    show("read as alice", await fs.read("/d/a.txt", authority=ALICE))
    print(" -- now the region closes: everyone none at /d, bob granted read_write, alice granted nothing")
    show("posture /d none", await fs.posture("/d", "none", authority=SYSTEM))
    show("grant bob read_write /d", await fs.grant("/d", "bob", "read_write", authority=SYSTEM))
    show("read /d/a.txt as alice (owner of the row bob believes he created)", await fs.read("/d/a.txt", authority=ALICE))
    show("read /d/other.txt as alice (her own, for comparison)", await fs.read("/d/other.txt", authority=ALICE))
    show("write /d/bob-own.txt as bob", await fs.write(path="/d/bob-own.txt", content="bob own\n", authority=BOB))
    show("read /d/bob-own.txt as alice (a row bob really created)", await fs.read("/d/bob-own.txt", authority=ALICE))
    show("edit /d/a.txt as alice", await fs.edit("/d/a.txt", old="bob", new="ALICE WAS HERE", authority=ALICE))
    show("delete /d/a.txt as alice", await fs.delete("/d/a.txt", authority=ALICE))
    show("read /d/a.txt as carol (grant on the exact path survived)", await fs.read("/.vfs/trash/d/a.txt", authority=CAROL))
    await entries(storage, "/d")

    print("\n== 3. different caller, closed region: can bob come to hold or read alice's deleted file")
    fs2, storage2 = make()
    await fs2.mkdir("/p", authority=SYSTEM)
    await fs2.posture("/p", "none", authority=SYSTEM)
    await fs2.grant("/p", "alice", "read_write", authority=SYSTEM)
    await fs2.write(path="/p/secret.txt", content="alice secret body\n", authority=ALICE)
    await fs2.delete("/p/secret.txt", authority=ALICE)
    print(" -- bob holds nothing at /p")
    show("write /p/secret.txt as bob", await fs2.write(path="/p/secret.txt", content="bob\n", authority=BOB))
    show("write /p/secret.txt as anonymous", await fs2.write(path="/p/secret.txt", content="anon\n", authority=ANON))
    show("write /p/fresh.txt as bob (a name nobody used)", await fs2.write(path="/p/fresh.txt", content="bob\n", authority=BOB))
    for level in ("list", "read", "add", "contribute", "read_write"):
        await fs2.grant("/p", "bob", level, authority=SYSTEM)
        print(f" -- bob holds {level} at /p")
        show("  read live path", await fs2.read("/p/secret.txt", authority=BOB))
        show("  read trash view", await fs2.read("/.vfs/trash/p/secret.txt", authority=BOB))
        show("  stat trash view", await fs2.stat("/.vfs/trash/p/secret.txt", authority=BOB))
        show("  write at the deleted path", await fs2.write(path="/p/secret.txt", content=f"bob at {level}\n", authority=BOB))
        show("  write at a fresh name", await fs2.write(path=f"/p/fresh-{level}.txt", content="bob\n", authority=BOB))
        await entries(storage2, "/p/secret.txt")
        if level != "read_write":
            # put the tombstone back when a revive landed, so every level starts from the same state
            async with storage2._host.session_factory() as conn:
                e2 = storage2._host.tables.entry
                live = (await conn.execute(select(e2.c.deleted_at).where(e2.c.path == "/p/secret.txt"))).scalar()
            if live is None:
                await fs2.delete("/p/secret.txt", authority=ALICE)
    await versions(storage2)
    await entries(storage2, "/p")
    await fs.close()
    await fs2.close()


asyncio.run(main())
