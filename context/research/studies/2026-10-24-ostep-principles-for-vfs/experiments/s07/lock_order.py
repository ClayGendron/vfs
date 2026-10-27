"""Study 07 experiment: in what order does a batch overwrite address its rows?"""
import asyncio, tempfile, os
from sqlalchemy import event
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.database.backend import DatabaseStorage

async def main():
    d = tempfile.mkdtemp()
    url = f"sqlite+aiosqlite:///{os.path.join(d, 'x.db')}"
    st = DatabaseStorage(url=url)
    fs = VirtualFileSystem(storage=st)
    names = ["/d/c.txt", "/d/a.txt", "/d/b.txt", "/e/z.txt", "/e/y.txt"]
    await fs.mkdir("/e")
    await fs.mkdir("/d")
    await fs.write([Entry(path=p, content="v1") for p in names])
    log = []
    eng = st._host.engine.sync_engine if hasattr(st._host, "engine") else None
    def capture(conn, cursor, statement, params, context, executemany):
        s = " ".join(statement.split())
        if s.startswith("UPDATE vfs_entries") or s.startswith("INSERT INTO vfs_entries"):
            rows = params if executemany else [params]
            log.append((s[:60], [[v for v in r if isinstance(v, str) and v.startswith("/")] for r in rows]))
    event.listen(eng, "before_cursor_execute", capture)
    r = await fs.write([Entry(path=p, content="v2") for p in names])
    print("success", r.success)
    for s, p in log:
        print(s); print("   params:", p)
    log.clear()
    r = await fs.write([Entry(path=p, content="new") for p in ["/e/q.txt", "/d/p.txt", "/e/n.txt"]])
    print("creates success", r.success)
    for s, p in log:
        print(s); print("   params:", p)
    await fs.close()

asyncio.run(main())
