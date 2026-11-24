"""What moves the entry id and the version of a file and of a directory, through the public verbs, on each engine.

It shows, for the facts the etag spec's decisions 3, 4, 10 and 17 rest on:

- the (entry id, version) of one file after each event the spec's table lists;
- a directory's version after each change to its children and to itself;
- the version the row of a ``delete`` reports, the version the trash view
  shows for the tombstone, and the path that view gives the row;
- whether a grant, a posture or a rebuild moves a version;
- that the four cases of "The problem" succeed with ``if_version`` today.

The entry id is read from ``vfs_entries`` directly, since no public row carries it.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p01_what_moves_an_id_and_a_version.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from harness import engines, run, storage_on
from vfs.authority import Authority
from vfs.base import AsyncVirtualFileSystem

if TYPE_CHECKING:
    from vfs.storage.backends.database import DatabaseStorage

SYSTEM = Authority.system()


async def stored(storage: DatabaseStorage, path: str) -> str:
    """The stored row at *path* as ``id-suffix,version,live|tombstone``, or ``none``."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        row = (
            await session.execute(select(entry.c.entry_id, entry.c.version, entry.c.deleted_at).where(entry.c.path == path))
        ).one_or_none()
    if row is None:
        return "none"
    return f"id=..{row.entry_id[-4:]} v={row.version} {'live' if row.deleted_at is None else 'tombstone'}"


async def the_file(fs: AsyncVirtualFileSystem, storage: DatabaseStorage) -> None:
    async def step(label: str, path: str = "/x/p") -> None:
        print(f"  {label:<44} {await stored(storage, path)}")

    await fs.mkdir("/x", authority=SYSTEM)
    await fs.write(path="/x/p", content="one", authority=SYSTEM)
    await step("created")
    await fs.write(path="/x/p", content="two", authority=SYSTEM)
    await step("rewritten")
    await fs.write(path="/x/p", content="two", authority=SYSTEM)
    await step("written with the same body")
    deleted = await fs.delete("/x/p", authority=SYSTEM)
    await step("deleted")
    print(f"    the delete's own row reports version {deleted.observations[0].version}")
    await fs.write(path="/x/p", content="three", authority=SYSTEM)
    await step("written again (revived)")
    await fs.delete("/x/p", authority=SYSTEM)
    await fs.restore("/x/p", authority=SYSTEM)
    await step("deleted and restored")
    await fs.move("/x/p", "/x/q", authority=SYSTEM)
    await step("moved to /x/q", "/x/q")
    await fs.move("/x", "/y", authority=SYSTEM)
    await step("its parent moved (/x -> /y)", "/y/q")
    await fs.copy("/y/q", "/y/c", authority=SYSTEM)
    await step("the copy at /y/c", "/y/c")
    await fs.delete("/y", authority=SYSTEM)
    await step("its parent deleted", "/y/q")
    await fs.restore("/y", authority=SYSTEM)
    await step("its parent restored", "/y/q")
    await fs.edit("/y/q", old="three", new="four", authority=SYSTEM)
    await step("edited", "/y/q")
    await fs.write(path="/y/q", content="!", append=True, authority=SYSTEM)
    await step("appended to", "/y/q")
    granted = await fs.grant("/y/q", "alice", "read", authority=SYSTEM)
    await step(f"after a grant on it (success={granted.success})", "/y/q")
    posture = await fs.set_posture("/y", "read", authority=SYSTEM)
    await step(f"after a posture on its parent (success={posture.success})", "/y/q")
    rebuilt = await storage.rebuild()
    await step(f"after a rebuild (success={rebuilt.success})", "/y/q")


async def the_directory(fs: AsyncVirtualFileSystem, storage: DatabaseStorage) -> None:
    async def step(label: str, path: str = "/d") -> None:
        print(f"  {label:<44} {await stored(storage, path)}")

    await fs.mkdir("/d", authority=SYSTEM)
    await step("made")
    await fs.write(path="/d/a", content="1", authority=SYSTEM)
    await step("a child made")
    await fs.write(path="/d/a", content="2", authority=SYSTEM)
    await step("the child rewritten")
    await fs.edit("/d/a", old="2", new="3", authority=SYSTEM)
    await step("the child edited")
    await fs.mkdir("/d/sub", authority=SYSTEM)
    await step("a subdirectory made")
    await fs.write(path="/d/sub/g", content="1", authority=SYSTEM)
    await step("a grandchild made")
    await fs.delete("/d/a", authority=SYSTEM)
    await step("the child deleted")
    await fs.restore("/d/a", authority=SYSTEM)
    await step("the child restored")
    await fs.move("/d/a", "/d/b", authority=SYSTEM)
    await step("the child renamed inside")
    await fs.write(path="/elsewhere", content="1", authority=SYSTEM)
    await fs.move("/elsewhere", "/d/in", authority=SYSTEM)
    await step("a file moved in")
    await fs.move("/d/in", "/out", authority=SYSTEM)
    await step("a file moved out")
    await fs.copy("/out", "/d/copied", authority=SYSTEM)
    await step("a file copied in")
    await fs.delete("/d/copied", authority=SYSTEM)
    await fs.write(path="/d/copied", content="again", authority=SYSTEM)
    await step("a child deleted, then revived by a write")
    await fs.mkdir("/d/sub", exist_ok=True, authority=SYSTEM)
    await step("mkdir of a child that exists (exist_ok)")
    await fs.grant("/d", "alice", "read", authority=SYSTEM)
    await step("a grant on the directory")
    await fs.set_posture("/d", "read", authority=SYSTEM)
    await step("a posture on the directory")
    await fs.move("/d", "/e", authority=SYSTEM)
    await step("the directory itself moved", "/e")
    await fs.delete("/e/sub", authority=SYSTEM)
    await fs.sweep("/e/sub", authority=SYSTEM)
    await step("a deleted child swept (destroyed)", "/e")


async def the_trash_view(fs: AsyncVirtualFileSystem, storage: DatabaseStorage) -> None:
    await fs.write(path="/t.md", content="body", authority=SYSTEM)
    await fs.mkdir("/td", authority=SYSTEM)
    await fs.write(path="/td/in.md", content="body", authority=SYSTEM)
    deleted = await fs.delete("/t.md", authority=SYSTEM)
    cascade = await fs.delete("/td", authority=SYSTEM)
    print(f"  delete /t.md reports           path={deleted.observations[0].path} version={deleted.observations[0].version}")
    print(f"  delete /td reports             {[(o.path, o.version) for o in cascade.observations]}")
    print(f"  stored /t.md                   {await stored(storage, '/t.md')}")
    print(f"  stored /td, /td/in.md          {await stored(storage, '/td')}; {await stored(storage, '/td/in.md')}")
    listing = await fs.ls("/.vfs/trash", authority=SYSTEM)
    print(f"  ls /.vfs/trash                 {[(o.path, o.kind, o.version) for o in listing.observations]} errors={listing.errors}")
    stat = await fs.stat("/.vfs/trash/t.md", authority=SYSTEM)
    print(f"  stat /.vfs/trash/t.md          {[(o.path, o.version) for o in stat.observations]} errors={[e.kind for e in stat.errors]}")
    inner = await fs.stat("/.vfs/trash/td/in.md", authority=SYSTEM)
    print(f"  stat /.vfs/trash/td/in.md      {[(o.path, o.version) for o in inner.observations]} errors={[e.kind for e in inner.errors]}")
    by_trash = await fs.restore("/.vfs/trash/t.md", authority=SYSTEM)
    print(f"  restore('/.vfs/trash/t.md')    success={by_trash.success} errors={[(e.kind, e.message) for e in by_trash.errors]}")
    by_rows = await fs.restore(observations=listing.observations[:1], authority=SYSTEM)
    print(f"  restore(observations=<trash row>) success={by_rows.success} rows={[(o.path, o.version) for o in by_rows.observations]} errors={[(e.kind, e.message) for e in by_rows.errors]}")
    again = await fs.restore("/t.md", authority=SYSTEM)
    print(f"  restore('/t.md') once it is live  success={again.success} errors={[(e.kind, e.data) for e in again.errors]}")


async def the_problem(fs: AsyncVirtualFileSystem) -> None:
    async def case(label: str, rival) -> None:
        for path in ("/x", "/y", "/other"):
            await fs.delete(path, authority=SYSTEM)
            await fs.sweep(path, authority=SYSTEM)
        await fs.mkdir("/x", authority=SYSTEM)
        await fs.write(path="/x/p", content="read by the caller", authority=SYSTEM)
        seen = (await fs.stat("/x/p", authority=SYSTEM)).observations[0].version
        await fs.write(path="/other", content="another file", authority=SYSTEM)
        await rival()
        now = (await fs.stat("/x/p", authority=SYSTEM)).observations[0].version
        if now != seen:
            print(f"  {label}: the version differs ({seen} -> {now}); the case needs the versions to line up")
            return
        result = await fs.write(path="/x/p", content="CLOBBER", if_version=seen, authority=SYSTEM)
        print(f"  {label}: write(if_version={seen}) success={result.success} status={[o.status for o in result.observations]}")

    async def moved_away_and_written() -> None:
        await fs.move("/x/p", "/x/gone", authority=SYSTEM)
        await fs.write(path="/x/p", content="a new file", authority=SYSTEM)

    async def moved_away_and_moved_in() -> None:
        await fs.move("/x/p", "/x/gone", authority=SYSTEM)
        await fs.move("/other", "/x/p", authority=SYSTEM)

    async def moved_away_and_copied_in() -> None:
        await fs.move("/x/p", "/x/gone", authority=SYSTEM)
        await fs.copy("/other", "/x/p", authority=SYSTEM)

    async def parent_moved_and_remade() -> None:
        await fs.move("/x", "/y", authority=SYSTEM)
        await fs.mkdir("/x", authority=SYSTEM)
        await fs.write(path="/x/p", content="a new file", authority=SYSTEM)

    await case("moved away, new file written   ", moved_away_and_written)
    # The moved-in file must stand at the version the caller saw: write the caller's file twice first.
    await fs.delete("/x", authority=SYSTEM)
    await fs.sweep("/x", authority=SYSTEM)
    await fs.delete("/other", authority=SYSTEM)
    await fs.sweep("/other", authority=SYSTEM)
    await fs.mkdir("/x", authority=SYSTEM)
    await fs.write(path="/x/p", content="v1", authority=SYSTEM)
    await fs.write(path="/x/p", content="read by the caller", authority=SYSTEM)
    await fs.write(path="/other", content="another file", authority=SYSTEM)
    await moved_away_and_moved_in()
    result = await fs.write(path="/x/p", content="CLOBBER", if_version=2, authority=SYSTEM)
    print(f"  moved away, another file moved in: write(if_version=2) success={result.success} status={[o.status for o in result.observations]}")
    await case("moved away, another file copied in", moved_away_and_copied_in)
    await case("parent moved, remade, rewritten   ", parent_moved_and_remade)


async def main() -> None:
    for engine in engines():
        print(f"== {engine}: one file")
        async with storage_on(engine) as (storage, _):
            fs = AsyncVirtualFileSystem(storage=storage)
            await the_file(fs, storage)
        print(f"== {engine}: one directory")
        async with storage_on(engine) as (storage, _):
            fs = AsyncVirtualFileSystem(storage=storage)
            await the_directory(fs, storage)
        print(f"== {engine}: delete, the trash view and restore")
        async with storage_on(engine) as (storage, _):
            fs = AsyncVirtualFileSystem(storage=storage)
            await the_trash_view(fs, storage)
        print(f"== {engine}: the four cases of The problem")
        async with storage_on(engine) as (storage, _):
            fs = AsyncVirtualFileSystem(storage=storage)
            await the_problem(fs)


if __name__ == "__main__":
    run(main)
