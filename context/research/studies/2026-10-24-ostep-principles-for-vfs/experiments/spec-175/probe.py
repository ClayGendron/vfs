"""Spec 175 probe: counts only, never times. Rot, missing bodies, write observation, edit, mint laundering."""

from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
from unittest import mock

from sqlalchemy import delete, event, select, update

from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.replace import EditOperation
import vfs.storage.backends.database.offload as offload_mod

LOG: list[str] = []


def label(statement: str) -> str:
    head = statement.split(None, 1)[0].upper()
    tables = re.findall(r"\bvfs_[a-z_]+", statement)
    return f"{head} {' '.join(dict.fromkeys(tables))}"


async def main() -> None:
    tmp = tempfile.mkdtemp()
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/p.sqlite")
    fs = VirtualFileSystem(storage=s)
    big = ("x" * 99 + "\n") * 10_000  # 1,000,000 bytes
    r = await fs.write(path="/a.txt", content="needle in a haystack")
    print("write observation fields:", sorted(r.observations[0].populated), "content_hash:", r.observations[0].content_hash)
    await fs.write(path="/b.txt", content="second file")
    await fs.write(path="/e.txt", content="")
    await fs.write(path="/big.txt", content=big)
    await fs.write(path="/bin.dat", data=b"\x00\x01binary")
    await fs.mkdir("/d")
    await fs.write(path="/v.txt", content="v1")
    await fs.write(path="/v.txt", content="v2")
    t = s._host.tables

    @event.listens_for(s._host.engine.sync_engine, "before_cursor_execute")
    def _log(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        LOG.append(label(statement))

    async with s._host.engine.begin() as c:
        rows = (await c.execute(select(t.entry.c.path, t.entry.c.kind, t.entry.c.source, t.entry.c.content_hash))).all()
        print("entries (path, kind, source, hash set):", [(p, k, src, h is not None) for p, k, src, h in rows])
        ids = {p for (p,) in (await c.execute(select(t.entry.c.path).join(t.content, t.content.c.entry_id == t.entry.c.entry_id))).all()}
        print("paths with a vfs_content row:", sorted(ids))
        blob_ids = {p for (p,) in (await c.execute(select(t.entry.c.path).join(t.blobs, t.blobs.c.entry_id == t.entry.c.entry_id))).all()}
        print("paths with a vfs_blobs row:", sorted(blob_ids))
        vrows = (await c.execute(select(t.versions.c.version_number, t.versions.c.content_hash, t.versions.c.content))).all()
        print("version rows ok:", [(n, h == hashlib.sha256(body.encode()).hexdigest()) for n, h, body in vrows])

    for verb, call in (
        ("read small", fs.read("/a.txt")),
        ("read 1MB", fs.read("/big.txt")),
        ("stat 1MB", fs.stat("/big.txt")),
        ("ls /", fs.ls("/")),
        ("read columns path,content", fs.read("/a.txt", columns=frozenset({"path", "content"}))),
    ):
        LOG.clear()
        res = await call
        stmts = [x for x in LOG if not x.startswith(("BEGIN", "COMMIT", "PRAGMA", "ROLLBACK"))]
        print(f"{verb}: success={res.success} statements={len(stmts)} {stmts}")

    # offload hop count on reads today
    calls = 0
    real = offload_mod.call_offloaded

    async def spy(executor, work):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return await real(executor, work)

    with mock.patch.object(offload_mod, "call_offloaded", spy):
        await fs.read("/big.txt")
    print("offload hops on a 1MB read today:", calls)

    # rot
    async with s._host.engine.begin() as c:
        eid_a = (await c.execute(select(t.entry.c.entry_id).where(t.entry.c.path == "/a.txt"))).scalar()
        await c.execute(update(t.content).where(t.content.c.entry_id == eid_a).values(content="neeXle in a haystacK"))
        eid_b = (await c.execute(select(t.entry.c.entry_id).where(t.entry.c.path == "/b.txt"))).scalar()
        await c.execute(delete(t.content).where(t.content.c.entry_id == eid_b))
        eid_bin = (await c.execute(select(t.entry.c.entry_id).where(t.entry.c.path == "/bin.dat"))).scalar()
        await c.execute(delete(t.blobs).where(t.blobs.c.entry_id == eid_bin))
    ra = await fs.read("/a.txt")
    print("rotten read success:", ra.success, "content:", ra.observations[0].content if ra.observations else None)
    rb = await fs.read("/b.txt")
    o = rb.observations[0]
    print("missing-body read success:", rb.success, "content:", o.content, "size:", o.size_bytes, "errors:", [e.kind for e in rb.errors])
    rbin = await fs.read("/bin.dat", columns=frozenset({"path", "data", "content_hash"}))
    print("missing-blob read success:", rbin.success, "data:", rbin.observations[0].data, "errors:", [e.kind for e in rbin.errors])
    eb = await fs.edit("/b.txt", old="second", new="third")
    print("edit on missing body:", eb.success, [(e.kind, e.message) for e in eb.errors])
    ea = await fs.edit("/a.txt", old="haystacK", new="haystack!")
    print("edit on rotten body:", ea.success, [(e.kind) for e in ea.errors])
    # overwrite launders: does the version row record the rotten body as a valid version?
    await fs.write(path="/a.txt", content="fresh")
    async with s._host.engine.begin() as c:
        vrows = (await c.execute(select(t.versions.c.version_number, t.versions.c.content_hash, t.versions.c.content).where(t.versions.c.entry_id == eid_a))).all()
        print("versions of /a.txt after overwrite:", [(n, body, h == hashlib.sha256(body.encode()).hexdigest()) for n, h, body in vrows])
    await s.close()


asyncio.run(main())
