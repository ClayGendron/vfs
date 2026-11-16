"""Probe 05: move of a file and of a tree; whether the id stays; occupants live and tombstoned; statements for big trees."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from probe_common import ALICE, BOB, SYSTEM, StatementCounter, edges, entries, make, show, versions
from vfs.models import Entry


async def build_tree(fs, root: str, rows: int) -> None:  # noqa: ANN001
    """A tree of exactly *rows* entries under and including *root*: the root, 10 directories, the rest files."""
    batch = [Entry(path=f"{root}/d{i:02d}/f{j:04d}.txt", content=f"body {i} {j}\n") for i in range(10) for j in range((rows - 11) // 10)]
    spare = rows - 11 - len(batch)
    batch += [Entry(path=f"{root}/d00/extra{j:04d}.txt", content="x\n") for j in range(spare)]
    result = await fs.write(batch, parents=True, authority=ALICE)
    assert not result.errors, result.errors


async def count_under(storage, prefix: str) -> tuple[int, int]:  # noqa: ANN001
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        where = (entry.c.path == prefix) | entry.c.path.like(prefix + "/%")
        total = (await session.execute(select(func.count()).where(where))).scalar_one()
        dead = (await session.execute(select(func.count()).where(where, entry.c.deleted_at.is_not(None)))).scalar_one()
    return total, dead


async def main() -> None:
    fs, storage = make()
    await fs.mkdir("/d", authority=SYSTEM)
    await fs.mkdir("/e", authority=SYSTEM)
    await fs.write(path="/d/a.txt", content="alpha v1\n", authority=ALICE)
    await fs.write(path="/d/a.txt", content="alpha v2\n", authority=ALICE)
    await fs.write(path="/d/other.txt", content="other\n", authority=BOB)
    await fs.mkedge(source="/d/a.txt", target="/d/other.txt", edge_type="cites", authority=ALICE)
    await fs.mkedge(source="/d/other.txt", target="/d/a.txt", edge_type="cites", authority=ALICE)

    print("== 1. move a file")
    await entries(storage, "/d")
    show("move /d/a.txt -> /e/b.md as bob (not the owner)", await fs.move("/d/a.txt", "/e/b.md", authority=BOB))
    await entries(storage, "/d")
    await entries(storage, "/e")
    await versions(storage)
    await edges(storage)
    show("read old path", await fs.read("/d/a.txt", authority=ALICE))
    show("read new path", await fs.read("/e/b.md", authority=ALICE))
    show("ls /.vfs/trash (does a move leave anything behind)", await fs.ls("/.vfs/trash", authority=SYSTEM))

    print("\n== 2. move onto an occupant")
    await fs.write(path="/d/live.txt", content="live occupant\n", authority=ALICE)
    await fs.write(path="/d/dead.txt", content="dead occupant\n", authority=ALICE)
    await fs.delete("/d/dead.txt", authority=ALICE)
    await fs.mkdir("/d/emptydir", authority=ALICE)
    await fs.mkdir("/d/srcdir", authority=ALICE)
    show("move file onto a live file", await fs.move("/e/b.md", "/d/live.txt", authority=ALICE))
    show("move file onto a tombstoned file", await fs.move("/e/b.md", "/d/dead.txt", authority=ALICE))
    show("move directory onto an empty live directory", await fs.move("/d/srcdir", "/d/emptydir", authority=ALICE))
    show("move file onto itself", await fs.move("/e/b.md", "/e/b.md", authority=ALICE))
    show("move a tombstoned source", await fs.move("/d/dead.txt", "/e/dead.txt", authority=ALICE))
    print(" -- the caller's own displacement: delete the occupant, then move")
    show("delete /d/live.txt", await fs.delete("/d/live.txt", authority=ALICE))
    show("move file onto the path just deleted", await fs.move("/e/b.md", "/d/live.txt", authority=ALICE))
    print(" -- and with sweep: destroy the occupant, then move")
    show("sweep /d/live.txt", await fs.sweep("/d/live.txt", authority=SYSTEM))
    show("move file onto the swept path", await fs.move("/e/b.md", "/d/live.txt", authority=ALICE))
    await entries(storage, "/d")

    print("\n== 3. move a tree that holds a tombstone")
    await fs.mkdir("/t/sub", parents=True, authority=SYSTEM)
    await fs.write(path="/t/x.txt", content="treex\n", authority=ALICE)
    await fs.write(path="/t/sub/y.txt", content="treey\n", authority=BOB)
    await fs.write(path="/t/sub/z.txt", content="treez\n", authority=ALICE)
    show("delete /t/sub/z.txt", await fs.delete("/t/sub/z.txt", authority=ALICE))
    await entries(storage, "/t")
    show("move /t -> /u", await fs.move("/t", "/u", authority=ALICE))
    await entries(storage, "/u")
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=SYSTEM))
    show("restore at the path the delete reported (/t/sub/z.txt)", await fs.restore("/t/sub/z.txt", authority=ALICE))
    show("restore at the moved path (/u/sub/z.txt)", await fs.restore("/u/sub/z.txt", authority=ALICE))
    print(" -- a fresh tree at the old name, then the old tombstone's path is free for an unrelated file")
    show("delete /u/sub/z.txt again", await fs.delete("/u/sub/z.txt", authority=ALICE))
    show("mkdir /t/sub parents", await fs.mkdir("/t/sub", parents=True, authority=ALICE))
    show("write /t/sub/z.txt (old path of a row now tombstoned at /u/sub/z.txt)", await fs.write(path="/t/sub/z.txt", content="unrelated\n", authority=BOB))
    await entries(storage, "/t")
    await entries(storage, "/u")

    print("\n== 4. statements issued by a move, a delete, a restore and a sweep of big trees")
    for rows in (100, 1000, 2000):
        fsn, storagen = make()
        await build_tree(fsn, "/big", rows)
        total, _ = await count_under(storagen, "/big")
        print(f" -- tree of {total} rows")
        with StatementCounter(storagen) as counter:
            result = await fsn.move("/big", "/moved", authority=ALICE)
        assert not result.errors, result.errors
        counter.report(f"move /big -> /moved ({total} rows)", samples=rows == 1000)
        with StatementCounter(storagen) as counter:
            result = await fsn.delete("/moved", authority=ALICE)
        assert not result.errors, result.errors
        counter.report(f"delete /moved ({total} rows)")
        print(f"    rows, tombstoned after delete: {await count_under(storagen, '/moved')}")
        with StatementCounter(storagen) as counter:
            result = await fsn.restore("/moved", authority=ALICE)
        assert not result.errors, result.errors
        counter.report(f"restore /moved ({total} rows)")
        with StatementCounter(storagen) as counter:
            result = await fsn.sweep("/moved", authority=SYSTEM)
        assert not result.errors, result.errors
        counter.report(f"sweep /moved, live ({total} rows)")
        print(f"    rows left after sweep: {await count_under(storagen, '/moved')}")
        await fsn.close()
    await fs.close()


asyncio.run(main())
