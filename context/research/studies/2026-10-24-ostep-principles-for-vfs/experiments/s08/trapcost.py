"""Count SQL statements per gated call: the cost of one 'trap' into vfs."""
import asyncio, sys, tempfile
from sqlalchemy import event
from vfs.base import VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.storage.backends.database import DatabaseStorage

async def main() -> None:
    d = tempfile.mkdtemp()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{d}/vfs.sqlite")
    fs = VirtualFileSystem(storage=storage)
    sysa = Authority.system()
    alice = Authority.of(Principal("alice"))
    r = await fs.write(path="/a.txt", content="hello", authority=sysa); assert r.success, r
    r = await fs.posture("/", "none", authority=sysa); assert r.success, r
    r = await fs.grant("/", "alice", "read", authority=sysa); assert r.success, r
    stmts: list[str] = []
    def rec(conn, cursor, statement, parameters, context, executemany):
        stmts.append(statement.split()[0] + " " + " ".join(t for t in statement.split() if t.startswith("vfs_"))[:80])
    eng = storage._host.engine.sync_engine
    event.listen(eng, "before_cursor_execute", rec)
    for label, auth in [("system read #1", sysa), ("alice read #1 (cold rights)", alice),
                        ("alice read #2 (rights cache hit)", alice), ("alice read #3", alice),
                        ("alice stat", alice), ("anonymous read", Authority.anonymous())]:
        stmts.clear()
        res = await fs.read("/a.txt", authority=auth)
        print(f"{label}: success={res.success} statements={len(stmts)}")
        for s in stmts: print("    ", s)
    stmts.clear()
    res = await fs.write(path="/b.txt", content="x", authority=alice)
    print(f"alice write (refused?): success={res.success} kinds={[e.kind for e in res.errors]} statements={len(stmts)}")
    event.remove(eng, "before_cursor_execute", rec)
    await fs.close()

asyncio.run(main())
