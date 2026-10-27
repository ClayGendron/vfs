"""Study 07 experiment: read-then-write append across two callers on SQLite."""
import asyncio, sys, tempfile, os
from vfs.base import VirtualFileSystem
from vfs.storage.backends.database.backend import DatabaseStorage

async def body(fs, path):
    r = await fs.read(path)
    return r.observations[0].content

async def main():
    d = tempfile.mkdtemp()
    url = f"sqlite+aiosqlite:///{os.path.join(d, 'x.db')}"
    fs = VirtualFileSystem(storage=DatabaseStorage(url=url))
    print("seed", (await fs.write(path="/log.txt", content="line0\n")).success)
    # Interleaving 1: both read, then both write (the >> shape).
    a = await body(fs, "/log.txt"); b = await body(fs, "/log.txt")
    ra = await fs.write(path="/log.txt", content=a + "from-A\n")
    rb = await fs.write(path="/log.txt", content=b + "from-B\n")
    print("A write", ra.success, "B write", rb.success)
    print("final:", repr(await body(fs, "/log.txt")))
    # Interleaving 2: 20 concurrent appenders via gather.
    await fs.write(path="/log2.txt", content="")
    async def append(i):
        cur = await body(fs, "/log2.txt")
        await asyncio.sleep(0)
        return (await fs.write(path="/log2.txt", content=cur + f"{i}\n")).success
    oks = await asyncio.gather(*(append(i) for i in range(20)))
    final = await body(fs, "/log2.txt")
    print("appends reported success:", sum(oks), "/ 20; lines kept:", len(final.splitlines()))
    # Contrast: the same append through edit is read-and-write in one guarded transaction.
    await fs.write(path="/log3.txt", content="END\n")
    async def edit_append(i):
        return (await fs.edit("/log3.txt", old="END\n", new=f"{i}\nEND\n")).success
    oks3 = await asyncio.gather(*(edit_append(i) for i in range(20)))
    final3 = await body(fs, "/log3.txt")
    print("edit appends success:", sum(oks3), "/ 20; lines kept:", len(final3.splitlines()) - 1)
    await fs.close()

asyncio.run(main())
