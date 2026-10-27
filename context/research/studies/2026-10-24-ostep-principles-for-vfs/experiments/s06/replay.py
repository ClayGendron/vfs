"""Study 06: what a re-issued (replayed) call does to vfs state, per verb.

Run from the repo root:
    uv run python <scratchpad>/ostep/s06/replay.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation

S = Authority.system()


def show(label, r):
    errs = [(str(e.kind), e.retryable) for e in r.errors]
    rows = [(str(o.path), o.status, o.version) for o in r.observations]
    print(f"{label:<44} ok={r.success!s:<5} errs={errs} rows={rows}")


async def versions(st, path=None):
    t = st._host.tables
    async with st._host.session_factory() as s:
        q = select(func.count()).select_from(t.versions)
        if path is not None:
            eid = (await s.execute(select(t.entry.c.entry_id).where(t.entry.c.path == path))).scalar()
            q = q.where(t.versions.c.entry_id == eid)
        return (await s.execute(q)).scalar()


async def entry_id(st, path):
    t = st._host.tables
    async with st._host.session_factory() as s:
        return (await s.execute(select(t.entry.c.entry_id).where(t.entry.c.path == path))).scalar()


async def stat(fs, path):
    r = await fs.stat(path, authority=S, columns=frozenset({"version", "content_hash"}))
    return [(o.version, (o.content_hash or "")[:8]) for o in r.observations] or [str(e.kind) for e in r.errors]


async def main():
    st = InMemoryStorage()
    fs = VirtualFileSystem(storage=st)

    print("== 1. write replay: identical body re-sent")
    show("write /a.md 'one'", await fs.write(path="/a.md", content="one", authority=S))
    show("write /a.md 'one' (replay)", await fs.write(path="/a.md", content="one", authority=S))
    print("   stat /a.md (version, hash):", await stat(fs, "/a.md"), " version rows:", await versions(st, "/a.md"))
    show("write /a.md 'two'", await fs.write(path="/a.md", content="two", authority=S))
    print("   stat:", await stat(fs, "/a.md"), " version rows:", await versions(st, "/a.md"))
    show("write /a.md 'two' (replay)", await fs.write(path="/a.md", content="two", authority=S))
    print("   stat:", await stat(fs, "/a.md"), " version rows:", await versions(st, "/a.md"))

    print("\n== 2. delayed replay after a rival writer (NFS Case 3 + a second client)")
    await fs.write(path="/b.md", content="base", authority=S)
    show("agent A writes 'A'", await fs.write(path="/b.md", content="A", authority=S))
    show("agent B writes 'B'", await fs.write(path="/b.md", content="B", authority=S))
    show("agent A's lost-reply retry of 'A'", await fs.write(path="/b.md", content="A", authority=S))
    body = (await fs.read("/b.md", authority=S)).observations[0].content
    print("   body now:", repr(body), " stat:", await stat(fs, "/b.md"), " version rows:", await versions(st, "/b.md"))

    print("\n== 3. edit replay (server-side find-and-replace)")
    await fs.write(path="/e.md", content="hello world", authority=S)
    show("edit world->there", await fs.edit("/e.md", "world", "there", authority=S))
    show("edit world->there (replay)", await fs.edit("/e.md", "world", "there", authority=S))
    print("   stat:", await stat(fs, "/e.md"))

    print("\n== 4. mkdir, delete, restore, move, copy replays")
    show("mkdir /d", await fs.mkdir("/d", authority=S))
    show("mkdir /d (replay)", await fs.mkdir("/d", authority=S))
    show("mkdir /d exist_ok (replay)", await fs.mkdir("/d", exist_ok=True, authority=S))
    await fs.write(path="/x.md", content="x", authority=S)
    show("delete /x.md", await fs.delete("/x.md", authority=S))
    show("delete /x.md (replay)", await fs.delete("/x.md", authority=S))
    show("restore /x.md", await fs.restore("/x.md", authority=S))
    show("restore /x.md (replay)", await fs.restore("/x.md", authority=S))
    show("copy /x.md /y.md", await fs.copy("/x.md", "/y.md", authority=S))
    show("copy /x.md /y.md (replay)", await fs.copy("/x.md", "/y.md", authority=S))
    show("move /y.md /z.md", await fs.move("/y.md", "/z.md", authority=S))
    show("move /y.md /z.md (replay)", await fs.move("/y.md", "/z.md", authority=S))

    print("\n== 5. edge and grant replays")
    show("mkedge a->x cites", await fs.mkedge(source="/a.md", target="/x.md", edge_type="cites", authority=S))
    show("mkedge (replay)", await fs.mkedge(source="/a.md", target="/x.md", edge_type="cites", authority=S))
    show("rmedge", await fs.rmedge(source="/a.md", target="/x.md", edge_type="cites", authority=S))
    show("rmedge (replay)", await fs.rmedge(source="/a.md", target="/x.md", edge_type="cites", authority=S))
    show("grant /d alice read", await fs.grant("/d", "alice", "read", authority=S))
    show("grant (replay)", await fs.grant("/d", "alice", "read", authority=S))
    show("revoke", await fs.revoke("/d", "alice", authority=S))
    show("revoke (replay)", await fs.revoke("/d", "alice", authority=S))

    print("\n== 6. batch atomicity: one bad entry in a batch of three")
    batch = [Entry(path="/p/1.md", content="1"), Entry(path="/nope/2.md", content="2"), Entry(path="/p/3.md", content="3")]
    await fs.mkdir("/p", authority=S)
    show("write batch [ok, missing parent, ok]", await fs.write(batch, authority=S))
    print("   /p/1.md after:", await stat(fs, "/p/1.md"))

    print("\n== 7. the generation question: is (path, version) a stable name?")
    await fs.write(path="/g.md", content="first life", authority=S)
    await fs.edit("/g.md", "first", "FIRST", authority=S)
    id1 = await entry_id(st, "/g.md")
    print("   life 1:", await stat(fs, "/g.md"), " entry_id:", id1)
    show("delete /g.md", await fs.delete("/g.md", authority=S))
    show("write /g.md (revive)", await fs.write(path="/g.md", content="second life", authority=S))
    print("   revived:", await stat(fs, "/g.md"), " same entry_id:", (await entry_id(st, "/g.md")) == id1)
    await fs.delete("/g.md", authority=S)
    show("sweep /g.md (purge)", await fs.sweep("/g.md", authority=S))
    show("write /g.md 'third life'", await fs.write(path="/g.md", content="third life", authority=S))
    print("   after sweep+create:", await stat(fs, "/g.md"), " same entry_id:", (await entry_id(st, "/g.md")) == id1)
    await fs.write(path="/h.md", content="v1", authority=S)
    await fs.move("/h.md", "/h2.md", authority=S)
    await fs.write(path="/h.md", content="other", authority=S)
    print("   rename then create at old path: /h.md", await stat(fs, "/h.md"), " /h2.md", await stat(fs, "/h2.md"))

    print("\n== total version rows:", await versions(st))
    await fs.close()


asyncio.run(main())
