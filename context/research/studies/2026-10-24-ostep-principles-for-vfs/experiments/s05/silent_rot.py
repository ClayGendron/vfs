"""Rot a stored body behind vfs's back; does any verb notice? Then: do lost body rows get noticed?"""
import asyncio, tempfile, hashlib
from sqlalchemy import update, delete, select
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

async def main():
    tmp = tempfile.mkdtemp()
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/rot.sqlite")
    await s.write(entries=[Entry(path=Path("/a.txt"), content="needle in a haystack"),
                           Entry(path=Path("/b.txt"), content="second file")])
    print("reindex:", (await s.reindex()).success)
    t = s._host.tables
    async with s._host.engine.begin() as c:
        eid = (await c.execute(select(t.entry.c.entry_id).where(t.entry.c.path == "/a.txt"))).scalar()
        await c.execute(update(t.content).where(t.content.c.entry_id == eid).values(content="neeXle in a haystacK"))
        eid_b = (await c.execute(select(t.entry.c.entry_id).where(t.entry.c.path == "/b.txt"))).scalar()
        await c.execute(delete(t.content).where(t.content.c.entry_id == eid_b))
    r = await s.read(path=Path("/a.txt"))
    o = r.observations[0]
    print("read /a.txt success:", r.success, "content:", repr(o.content))
    st = await s.stat(path=Path("/a.txt"))
    print("stat content_hash == sha256(read body)?",
          st.observations[0].content_hash == hashlib.sha256(o.content.encode()).hexdigest())
    g = await s.grep(pattern="needle")
    print("grep 'needle' paths:", [x.path for x in g.observations], "errors:", [e.kind for e in g.errors])
    rb = await s.read(path=Path("/b.txt"), columns=frozenset({"path","content","size_bytes","content_hash"}))
    print("read /b.txt (body row lost) success:", rb.success,
          "content:", repr(rb.observations[0].content), "size_bytes:", rb.observations[0].size_bytes, "hash set:", rb.observations[0].content_hash is not None,
          "errors:", [(e.kind, e.message) for e in rb.errors])
    ri = await s.reindex()
    print("reindex after rot:", ri.success, [(e.kind, e.severity, e.message[:80]) for e in ri.errors])
    await s.close()

asyncio.run(main())
