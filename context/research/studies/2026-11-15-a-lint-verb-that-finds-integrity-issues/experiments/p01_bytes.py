"""Probe 01, the bytes layer: break a body, its hash or its measures with direct SQL, then run each verb."""

from __future__ import annotations

import asyncio
import hashlib

from sqlalchemy import delete, select, update

from lint_common import SYSTEM, StatementCounter, attempt, counts, fetch, make, run_sql


async def seeded():
    fs, storage = make()
    await fs.mkdir("/docs", authority=SYSTEM)
    await fs.write(path="/docs/a.md", content="alpha original body\nline two\n", authority=SYSTEM)
    await fs.write(path="/docs/a.md", content="alpha second body\nline two\n", authority=SYSTEM)
    await fs.write(path="/docs/b.md", content="bravo body\n", authority=SYSTEM)
    await fs.write(path="/docs/c.bin", data=b"\x00\x01binary-charlie\xff", authority=SYSTEM)
    await storage.rebuild()
    return fs, storage


async def id_of(storage, path: str) -> str:
    entry = storage._host.tables.entry
    return (await fetch(storage, select(entry.c.entry_id).where(entry.c.path == path)))[0][0]


async def battery(fs, storage, path: str, needle: str) -> None:
    await attempt("read", fs.read(path, authority=SYSTEM))
    await attempt("stat", fs.stat(path, authority=SYSTEM))
    await attempt(f"grep {needle!r}", fs.grep(needle, authority=SYSTEM))
    await attempt(f"search {needle!r}", fs.search(needle, authority=SYSTEM))
    await attempt("copy to /docs/copy.md", fs.copy(path, "/docs/copy.md", authority=SYSTEM))
    await attempt("read the copy", fs.read("/docs/copy.md", authority=SYSTEM))
    await attempt("edit (body -> BODY)", fs.edit(path, "body", "BODY", authority=SYSTEM))
    await attempt("read after edit", fs.read(path, authority=SYSTEM))
    await attempt("refresh", storage.refresh())
    await attempt("rebuild", storage.rebuild())
    await attempt("sweep trash", fs.sweep(authority=SYSTEM))


async def versions_of(storage, path: str) -> None:
    v = storage._host.tables.versions
    eid = await id_of(storage, path)
    for row in await fetch(
        storage, select(v.c.version_number, v.c.content_hash, v.c.content).where(v.c.entry_id == eid)
    ):
        body = row.content or ""
        match = hashlib.sha256(body.encode()).hexdigest() == row.content_hash
        print(f"      version {row.version_number}: body={body[:30]!r} hash matches its own body={match}")


async def main() -> None:
    print("== B1. A text body rewritten underneath vfs (hash now wrong)")
    fs, storage = await seeded()
    t = storage._host.tables
    eid = await id_of(storage, "/docs/a.md")
    print("    rows changed:", await run_sql(storage, update(t.content).where(t.content.c.entry_id == eid).values(content="tampered body\n")))
    await battery(fs, storage, "/docs/a.md", "tampered")
    await versions_of(storage, "/docs/a.md")
    await fs.close()

    print("== B2. A text body row deleted (hash present, body missing)")
    fs, storage = await seeded()
    t = storage._host.tables
    eid = await id_of(storage, "/docs/b.md")
    print("    rows changed:", await run_sql(storage, delete(t.content).where(t.content.c.entry_id == eid)))
    await battery(fs, storage, "/docs/b.md", "bravo")
    await attempt("overwrite /docs/b.md", fs.write(path="/docs/b.md", content="bravo rewritten\n", authority=SYSTEM))
    await attempt("read after overwrite", fs.read("/docs/b.md", authority=SYSTEM))
    await versions_of(storage, "/docs/b.md")
    await fs.close()

    print("== B3. A bytes body row deleted")
    fs, storage = await seeded()
    t = storage._host.tables
    eid = await id_of(storage, "/docs/c.bin")
    print("    rows changed:", await run_sql(storage, delete(t.blobs).where(t.blobs.c.entry_id == eid)))
    await attempt("read columns=data", fs.read("/docs/c.bin", columns=frozenset({"path", "data"}), authority=SYSTEM))
    await attempt("read default", fs.read("/docs/c.bin", authority=SYSTEM))
    await attempt("stat", fs.stat("/docs/c.bin", authority=SYSTEM))
    await attempt("copy", fs.copy("/docs/c.bin", "/docs/c2.bin", authority=SYSTEM))
    await attempt("rebuild", storage.rebuild())
    await fs.close()

    print("== B4. The recorded hash set to NULL, then to a wrong value; size and lines set wrong")
    fs, storage = await seeded()
    t = storage._host.tables
    print("    rows changed:", await run_sql(storage, update(t.entry).where(t.entry.c.path == "/docs/b.md").values(content_hash=None)))
    await attempt("read (hash NULL)", fs.read("/docs/b.md", authority=SYSTEM))
    await attempt("write the same body again", fs.write(path="/docs/b.md", content="bravo body\n", authority=SYSTEM))
    print("    stored hash now:", await fetch(storage, select(t.entry.c.content_hash, t.entry.c.version).where(t.entry.c.path == "/docs/b.md")))
    await run_sql(storage, update(t.entry).where(t.entry.c.path == "/docs/a.md").values(content_hash="0" * 64, size_bytes=999999, lines=4242))
    await attempt("read (hash wrong, size wrong)", fs.read("/docs/a.md", authority=SYSTEM))
    await attempt("stat (hash wrong, size wrong)", fs.stat("/docs/a.md", authority=SYSTEM))
    await attempt("write the same body again", fs.write(path="/docs/a.md", content="alpha second body\nline two\n", authority=SYSTEM))
    print("    stored hash, size, lines, version now:", await fetch(storage, select(t.entry.c.content_hash, t.entry.c.size_bytes, t.entry.c.lines, t.entry.c.version).where(t.entry.c.path == "/docs/a.md")))
    await attempt("rebuild", storage.rebuild())
    print("    after rebuild:", await fetch(storage, select(t.entry.c.content_hash, t.entry.c.size_bytes, t.entry.c.lines).where(t.entry.c.path == "/docs/a.md")))
    await fs.close()

    print("== B5. A version row's body rewritten")
    fs, storage = await seeded()
    t = storage._host.tables
    eid = await id_of(storage, "/docs/a.md")
    print("    rows changed:", await run_sql(storage, update(t.versions).where(t.versions.c.entry_id == eid).values(content="history rewritten\n")))
    await attempt("read", fs.read("/docs/a.md", authority=SYSTEM))
    await attempt("rebuild", storage.rebuild())
    await versions_of(storage, "/docs/a.md")
    await fs.close()

    print("== B6. A prototype of the check: one keyset page of entries joined to their bodies, hashed here")
    fs, storage = await seeded()
    t = storage._host.tables
    ida, idb, idc = [await id_of(storage, p) for p in ("/docs/a.md", "/docs/b.md", "/docs/c.bin")]
    await run_sql(
        storage,
        update(t.content).where(t.content.c.entry_id == ida).values(content="tampered body\n"),
        delete(t.content).where(t.content.c.entry_id == idb),
        delete(t.blobs).where(t.blobs.c.entry_id == idc),
    )
    e, c, b = t.entry, t.content, t.blobs
    with StatementCounter(storage) as counter:
        page = await fetch(
            storage,
            select(e.c.id, e.c.path, e.c.source, e.c.content_hash, e.c.size_bytes, c.c.content, b.c.data)
            .select_from(e.outerjoin(c, c.c.entry_id == e.c.entry_id).outerjoin(b, b.c.entry_id == e.c.entry_id))
            .where(e.c.kind == "file", e.c.id > 0)
            .order_by(e.c.id)
            .limit(1000),
        )
    findings = []
    for row in page:
        body = row.content.encode() if row.source == "text" and row.content is not None else row.data
        if row.content_hash is None:
            findings.append((row.path, "unhashed"))
        elif body is None:
            findings.append((row.path, "missing body"))
        elif hashlib.sha256(body).hexdigest() != row.content_hash:
            findings.append((row.path, "mismatch"))
        elif len(body) != row.size_bytes:
            findings.append((row.path, "size differs"))
    print(f"    statements={counter.statements} rows visited={len(page)} findings={findings}")
    print("    table counts:", await counts(storage, "entry", "content", "blobs", "versions"))
    await fs.close()


asyncio.run(main())
