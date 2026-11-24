"""Probe 01: what a deleted row does to its name on today's tree, through the public verbs and through the shell."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path as FsPath

from sqlalchemy import func, select

sys.path.insert(0, str(FsPath(__file__).parent))

from harness import ALICE, ANON, BOB, SYSTEM, make, show


async def line(fs, text: str) -> None:
    result = await fs.cli(text, authority=ALICE)
    out = result.stdout.decode() if isinstance(result.stdout, bytes) else str(result.stdout)
    err = result.stderr.decode() if isinstance(result.stderr, bytes) else str(result.stderr)
    print(f"  $ {text}\n      exit={result.exit_code} out={out.strip()!r} err={err.strip()!r}")


async def row_at(storage, path: str) -> None:
    entry = storage._host.tables.entry
    stmt = select(entry.c.entry_id, entry.c.owner_id, entry.c.version, entry.c.deleted_at).where(entry.c.path == path)
    async with storage._host.session_factory() as conn:
        found = (await conn.execute(stmt)).all()
    for entry_id, owner, version, deleted_at in found:
        gone = deleted_at is not None
        print(f"    row at {path}: entry ...{entry_id[-6:]} owner={owner} version={version} deleted={gone}")


async def main() -> None:
    fs, storage = make()
    await fs.mkdir("/proj", authority=SYSTEM)

    print("== 1. the shell: a folder removed and made again")
    await line(fs, "mkdir /proj/build && echo a > /proj/build/out.txt")
    await line(fs, "rm -r /proj/build && mkdir /proj/build")
    await line(fs, "mkdir -p /proj/build/sub")

    print("== 2. the verbs at a deleted directory's name")
    show("mkdir /proj/build", await fs.mkdir("/proj/build", authority=ALICE))
    made = await fs.write(path="/proj/build/new.txt", content="x\n", parents=True, authority=ALICE)
    show("write /proj/build/new.txt parents=True", made)
    await fs.mkdir("/proj/other", authority=ALICE)
    show("move /proj/other -> /proj/build", await fs.move("/proj/other", "/proj/build", authority=ALICE))

    print("== 3. a file deleted by one caller and written again by another")
    await fs.write(path="/proj/f.txt", content="first\n", authority=ALICE)
    await row_at(storage, "/proj/f.txt")
    show("delete as alice", await fs.delete("/proj/f.txt", authority=ALICE))
    again = await fs.write(path="/proj/f.txt", content="second\n", if_absent=True, authority=BOB)
    show("write as bob, if_absent=True", again)
    await row_at(storage, "/proj/f.txt")
    show("restore as alice", await fs.restore("/proj/f.txt", authority=ALICE))

    print("== 4. the shell: a file saved by writing a temporary file and moving it over")
    await line(fs, "echo v1 > /proj/conf.txt && echo v2 > /proj/conf.tmp")
    await line(fs, "mv -f /proj/conf.tmp /proj/conf.txt; cat /proj/conf.txt")
    await line(fs, "rm /proj/conf.txt && mv /proj/conf.tmp /proj/conf.txt; cat /proj/conf.txt")

    print("== 5. one name written and deleted 50 times")
    for round_ in range(50):
        await fs.write(path="/proj/scratch.txt", content=f"round {round_}\n", authority=ALICE)
        await fs.delete("/proj/scratch.txt", authority=ALICE)
    entry, versions = storage._host.tables.entry, storage._host.tables.versions
    at_path = select(func.count()).select_from(entry).where(entry.c.path == "/proj/scratch.txt")
    async with storage._host.session_factory() as conn:
        rows = (await conn.execute(at_path)).scalar()
        kept = (await conn.execute(select(func.count()).select_from(versions))).scalar()
    print(f"  entry rows at /proj/scratch.txt: {rows}; version rows in the mount: {kept}")

    print("== 6. one file out of a deleted directory")
    await fs.mkdir("/proj/docs", authority=ALICE)
    await fs.write(path="/proj/docs/1.md", content="doc\n", authority=ALICE)
    show("delete /proj/docs", await fs.delete("/proj/docs", authority=ALICE))
    show("restore /proj/docs/1.md", await fs.restore("/proj/docs/1.md", authority=ALICE))

    print("== 7. sweep at a live path, on a mount where everyone holds read_write")
    await fs.mkdir("/work", authority=SYSTEM)
    await fs.write(path="/work/keep.txt", content="live\n", authority=ALICE)
    show("sweep /work as anonymous", await fs.sweep("/work", authority=ANON))
    show("stat /work/keep.txt", await fs.stat("/work/keep.txt", authority=SYSTEM))
    show("restore /work", await fs.restore("/work", authority=SYSTEM))

    print("== 8. a deleted file beneath a directory that is then moved")
    await fs.mkdir("/a", authority=SYSTEM)
    await fs.write(path="/a/gone.txt", content="x\n", authority=ALICE)
    await fs.delete("/a/gone.txt", authority=ALICE)
    show("move /a -> /b", await fs.move("/a", "/b", authority=SYSTEM))
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash", authority=SYSTEM))
    show("restore /a/gone.txt", await fs.restore("/a/gone.txt", authority=ALICE))
    show("restore /b/gone.txt", await fs.restore("/b/gone.txt", authority=ALICE))

    print("== 9. a miss at a deleted path, and a read through the trash view")
    await fs.write(path="/proj/note.md", content="n\n", authority=ALICE)
    await fs.delete("/proj/note.md", authority=ALICE)
    missed = await fs.stat("/proj/note.md", authority=ALICE)
    print(f"  stat /proj/note.md: {missed.errors[0].kind.value} data keys={sorted(missed.errors[0].data)}")
    show("stat /.vfs/trash/proj/note.md", await fs.stat("/.vfs/trash/proj/note.md", authority=ALICE))
    await fs.close()


asyncio.run(main())
