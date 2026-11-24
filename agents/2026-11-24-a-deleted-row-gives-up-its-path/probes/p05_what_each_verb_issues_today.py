"""Probe 05: the statements of today's verbs at the storage, and the rows a move rewrites, on the in-memory store.

The statement counts leave out ``BEGIN``, ``COMMIT``, ``PRAGMA``, ``SAVEPOINT``, ``RELEASE``, ``ROLLBACK``
and the statistics statements. A move's rows are counted by reading the entry and posting tables before
and after it. The counts size what the design keeps, adds and removes; nothing is timed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path as FsPath

from sqlalchemy import select

sys.path.insert(0, str(FsPath(__file__).parent))

from harness import ALICE, SYSTEM, Statements, make

from vfs import Entry


async def counted(storage, label: str, call, *, refusal: bool = False) -> None:
    with Statements(storage) as seen:
        result = await call()
    assert bool(result.errors) is refusal, result.errors
    seen.report(label)


async def tables(storage) -> tuple[dict[str, tuple[str, bool]], set[tuple]]:
    """Each entry's path and whether it is deleted, and the posting rows, as the tables hold them now."""
    entry, segments = storage._host.tables.entry, storage._host.tables.segments
    async with storage._host.session_factory() as conn:
        found = (await conn.execute(select(entry.c.entry_id, entry.c.path, entry.c.deleted_at))).all()
        postings = {tuple(row) for row in await conn.execute(select(segments))}
    return {entry_id: (path, deleted_at is not None) for entry_id, path, deleted_at in found}, postings


async def main() -> None:
    fs, storage = make()
    await fs.mkdir("/proj", authority=SYSTEM)
    await fs.write(path="/proj/warm.txt", content="warm\n", authority=ALICE)

    print("== a file: create, delete, a write at the deleted path, delete, restore")
    fresh = lambda: fs.write(path="/proj/a.txt", content="one\n", authority=ALICE)  # noqa: E731
    again = lambda: fs.write(path="/proj/a.txt", content="two\n", authority=ALICE)  # noqa: E731
    await counted(storage, "write, a fresh name", fresh)
    await counted(storage, "delete", lambda: fs.delete("/proj/a.txt", authority=ALICE))
    await counted(storage, "write at the deleted path (the revive)", again)
    await counted(storage, "delete again", lambda: fs.delete("/proj/a.txt", authority=ALICE))
    await counted(storage, "stat of the deleted path, a miss with the hint", lambda: fs.stat("/proj/a.txt", authority=ALICE), refusal=True)
    await counted(storage, "restore", lambda: fs.restore("/proj/a.txt", authority=ALICE))
    await counted(storage, "stat of a path that holds nothing", lambda: fs.stat("/proj/none.txt", authority=ALICE), refusal=True)

    print("== a directory: mkdir at a fresh name")
    await counted(storage, "mkdir", lambda: fs.mkdir("/proj/dir", authority=ALICE))

    for live, gone in ((100, 0), (100, 100), (100, 1000)):
        root = f"/m{gone}"
        await fs.mkdir(root, authority=SYSTEM)
        names = [f"{root}/f{i:04d}.txt" for i in range(live + gone)]
        made = await fs.write([Entry(path=name, content="x\n") for name in names], authority=ALICE)
        assert not made.errors, made.errors
        for name in names[live:]:
            await fs.delete(name, authority=ALICE)
        print(f"== a move of a directory holding {live} live files and {gone} deleted ones")
        before = await tables(storage)
        await counted(storage, "move", lambda root=root: fs.move(root, root + "-moved", authority=SYSTEM))
        after = await tables(storage)
        live_moved = sum(1 for key, (path, deleted) in after[0].items() if not deleted and before[0][key][0] != path)
        gone_moved = sum(1 for key, (path, deleted) in after[0].items() if deleted and before[0][key][0] != path)
        print(
            f"  entry rows whose path changed: {live_moved} live, {gone_moved} deleted;"
            f" posting rows removed and added: {len(before[1] - after[1])} and {len(after[1] - before[1])}"
        )
    await fs.close()


asyncio.run(main())
