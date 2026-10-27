"""Spec 177 probe: every mutating verb sent twice at HEAD, with error kind, severity and data."""

from __future__ import annotations

import asyncio

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

S = Authority.system()


def show(label, r):
    rows = [(str(o.path), o.status, o.version) for o in r.observations]
    errs = [(str(e.kind), str(e.severity), e.data) for e in r.errors]
    extra = {k: v for k, v in (r.model_extra or {}).items()}
    print(f"{label:<34} ok={r.success!s:<5} rows={rows} errs={errs} extra={list(extra)}")


async def twice(label, call):
    show(label + " #1", await call())
    show(label + " #2", await call())


async def main():
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await twice("write /a.md 'one'", lambda: fs.write(path="/a.md", content="one", authority=S))
    await twice("write overwrite=False /b.md", lambda: fs.write(path="/b.md", content="b", overwrite=False, authority=S))
    await fs.write(path="/e.md", content="x", authority=S)
    await twice("edit x->xx (new contains old)", lambda: fs.edit("/e.md", "x", "xx", authority=S))
    await fs.write(path="/f.md", content="hello world", authority=S)
    await twice("edit world->there", lambda: fs.edit("/f.md", "world", "there", authority=S))
    await twice("mkdir /d", lambda: fs.mkdir("/d", authority=S))
    await twice("mkdir /d2 exist_ok", lambda: fs.mkdir("/d2", exist_ok=True, authority=S))
    await fs.write(path="/x.md", content="x", authority=S)
    await twice("delete /x.md", lambda: fs.delete("/x.md", authority=S))
    await twice("restore /x.md", lambda: fs.restore("/x.md", authority=S))
    await twice("copy /x.md /y.md", lambda: fs.copy("/x.md", "/y.md", authority=S))
    await twice("move /y.md /z.md", lambda: fs.move("/y.md", "/z.md", authority=S))
    await twice("mkedge a->x", lambda: fs.mkedge(source="/a.md", target="/x.md", edge_type="cites", authority=S))
    await twice("rmedge a->x", lambda: fs.rmedge(source="/a.md", target="/x.md", edge_type="cites", authority=S))
    await twice("grant /d alice read", lambda: fs.grant("/d", "alice", "read", authority=S))
    await twice("revoke /d alice", lambda: fs.revoke("/d", "alice", authority=S))
    await twice("posture /d read", lambda: fs.posture("/d", "read", authority=S))
    await twice("add_member g alice", lambda: fs.add_member("group:g", "alice", authority=S))
    await twice("remove_member g alice", lambda: fs.remove_member("group:g", "alice", authority=S))
    await fs.delete("/z.md", authority=S)
    await twice("sweep /.vfs/trash", lambda: fs.sweep(authority=S))
    await fs.close()


asyncio.run(main())
