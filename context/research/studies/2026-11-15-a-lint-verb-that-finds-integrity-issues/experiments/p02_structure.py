"""Probe 02, the structure layer: break path, parent, name, tombstone, segment and fs-edge rows, then run each verb."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, select, text, update
from ulid import ULID

from lint_common import SYSTEM, StatementCounter, attempt, counts, fetch, make, run_sql

# The structural checks a lint could run as plain SQL over vfs_entries joined to itself.
CHECKS = {
    "rootless (no parent, not /)": "SELECT e.path FROM vfs_entries e WHERE e.parent_id IS NULL AND e.path <> '/'",
    "dangling parent": "SELECT e.path FROM vfs_entries e LEFT JOIN vfs_entries p ON p.entry_id = e.parent_id"
    " WHERE e.parent_id IS NOT NULL AND p.id IS NULL",
    "torn path (path <> parent path + name)": "SELECT e.path FROM vfs_entries e JOIN vfs_entries p ON p.entry_id = e.parent_id"
    " WHERE e.path <> (CASE WHEN p.path = '/' THEN '' ELSE p.path END) || '/' || e.name",
    "parent is not a directory": "SELECT e.path FROM vfs_entries e JOIN vfs_entries p ON p.entry_id = e.parent_id"
    " WHERE p.kind <> 'directory'",
    "live row under a tombstoned parent": "SELECT e.path FROM vfs_entries e JOIN vfs_entries p ON p.entry_id = e.parent_id"
    " WHERE e.deleted_at IS NULL AND p.deleted_at IS NOT NULL",
    "tombstone flags disagree": "SELECT e.path FROM vfs_entries e"
    " WHERE (e.deleted_at IS NULL) <> (e.trash_root_id IS NULL)",
    "fs edge missing or wrong": "SELECT e.path FROM vfs_entries e LEFT JOIN vfs_edges g"
    " ON g.target_id = e.entry_id AND g.edge_type = 'fs' AND g.source_id = e.parent_id"
    " WHERE e.parent_id IS NOT NULL AND g.id IS NULL",
    "edge endpoint has no entry": "SELECT g.id FROM vfs_edges g LEFT JOIN vfs_entries s ON s.entry_id = g.source_id"
    " LEFT JOIN vfs_entries t ON t.entry_id = g.target_id WHERE s.id IS NULL OR t.id IS NULL",
    "segment posting with no entry": "SELECT DISTINCT s.segment FROM vfs_segments s LEFT JOIN vfs_entries e"
    " ON e.entry_id = s.entry_id WHERE e.id IS NULL",
}


async def seeded():
    fs, storage = make()
    for path in ("/a/b/c.txt", "/a/d.txt", "/x/y.txt"):
        await fs.write(path=path, content=f"needle in {path}\n", parents=True, authority=SYSTEM)
    await storage.rebuild()
    return fs, storage


async def lint(storage) -> None:
    async with storage._host.session_factory() as session:
        with StatementCounter(storage) as counter:
            found = {name: [row[0] for row in await session.execute(text(sql))] for name, sql in CHECKS.items()}
    hits = {name: rows for name, rows in found.items() if rows}
    print(f"    prototype lint ({counter.statements} statements): {hits or 'clean'}")
    # Segment postings: recompute from the path and diff, the way rebuild's collect does.
    t = storage._host.tables
    rows = await fetch(storage, select(t.entry.c.entry_id, t.entry.c.path))
    held: dict[str, set[str]] = {}
    for seg in await fetch(storage, select(t.segments.c.segment, t.segments.c.entry_id)):
        held.setdefault(seg.entry_id, set()).add(seg.segment)
    drift = [row.path for row in rows if set(row.path.strip("/").split("/")[:-1]) - {""} != held.get(row.entry_id, set())]
    print(f"    segment postings that differ from the path: {drift or 'none'}")


async def battery(fs, storage, paths: list[str], dirs: list[str]) -> None:
    for path in paths:
        await attempt(f"read {path}", fs.read(path, authority=SYSTEM))
        await attempt(f"stat {path}", fs.stat(path, authority=SYSTEM))
    for d in dirs:
        await attempt(f"ls {d}", fs.ls(d, authority=SYSTEM))
    await attempt("tree /", fs.tree("/", authority=SYSTEM))
    await attempt("glob **/*.txt", fs.glob("**/*.txt", authority=SYSTEM))
    await attempt("grep needle", fs.grep("needle", authority=SYSTEM))
    await lint(storage)
    result = await attempt("rebuild", storage.rebuild())
    for error in (result.errors if result else []):
        print(f"      rebuild note data={error.data}")
    await lint(storage)


async def main() -> None:
    print("== S0. A clean store")
    fs, storage = await seeded()
    await lint(storage)
    print("    counts:", await counts(storage, "entry", "segments", "edges"))
    await fs.close()

    print("== S1. path cache torn: /a/d.txt's path column rewritten to /a/zzz.txt, name and parent untouched")
    fs, storage = await seeded()
    e = storage._host.tables.entry
    await run_sql(storage, update(e).where(e.c.path == "/a/d.txt").values(path="/a/zzz.txt"))
    await battery(fs, storage, ["/a/d.txt", "/a/zzz.txt"], ["/a"])
    await attempt("write /a/d.txt", fs.write(path="/a/d.txt", content="new\n", authority=SYSTEM))
    await attempt("write /a/zzz.txt", fs.write(path="/a/zzz.txt", content="new\n", authority=SYSTEM))
    await attempt("move /a /a2", fs.move("/a", "/a2", authority=SYSTEM))
    await lint(storage)
    await fs.close()

    print("== S2. dangling parent: /x/y.txt's parent_id points at no row")
    fs, storage = await seeded()
    e = storage._host.tables.entry
    await run_sql(storage, update(e).where(e.c.path == "/x/y.txt").values(parent_id=str(ULID())))
    await battery(fs, storage, ["/x/y.txt"], ["/x"])
    await attempt("delete /x", fs.delete("/x", authority=SYSTEM))
    await attempt("read /x/y.txt after delete /x", fs.read("/x/y.txt", authority=SYSTEM))
    await lint(storage)
    await fs.close()

    print("== S3. parent row removed: the row of /a/b deleted by SQL, its child left")
    fs, storage = await seeded()
    e = storage._host.tables.entry
    await run_sql(storage, delete(e).where(e.c.path == "/a/b"))
    await battery(fs, storage, ["/a/b/c.txt", "/a/b"], ["/a", "/a/b"])
    await attempt("mkdir /a/b", fs.mkdir("/a/b", authority=SYSTEM))
    await attempt("ls /a/b after mkdir", fs.ls("/a/b", authority=SYSTEM))
    await attempt("write /a/b/c.txt", fs.write(path="/a/b/c.txt", content="again\n", authority=SYSTEM))
    await lint(storage)
    await fs.close()

    print("== S4. live child under a tombstoned parent: /x stamped deleted by SQL, /x/y.txt left live")
    fs, storage = await seeded()
    e = storage._host.tables.entry
    xid = (await fetch(storage, select(e.c.entry_id).where(e.c.path == "/x")))[0][0]
    await run_sql(storage, update(e).where(e.c.path == "/x").values(deleted_at=datetime.now(UTC), trash_root_id=xid))
    await battery(fs, storage, ["/x/y.txt"], ["/x", "/"])
    await attempt("restore /x", fs.restore("/x", authority=SYSTEM))
    await lint(storage)
    await fs.close()

    print("== S5. name disagrees: /a/d.txt's name column set to other.txt")
    fs, storage = await seeded()
    e = storage._host.tables.entry
    await run_sql(storage, update(e).where(e.c.path == "/a/d.txt").values(name="other.txt"))
    await battery(fs, storage, ["/a/d.txt", "/a/other.txt"], ["/a"])
    await attempt("write /a/other.txt", fs.write(path="/a/other.txt", content="new\n", authority=SYSTEM))
    await lint(storage)
    await fs.close()

    print("== S6. a cycle: /a's parent_id set to its own child /a/b")
    fs, storage = await seeded()
    e = storage._host.tables.entry
    bid = (await fetch(storage, select(e.c.entry_id).where(e.c.path == "/a/b")))[0][0]
    await run_sql(storage, update(e).where(e.c.path == "/a").values(parent_id=bid))
    await battery(fs, storage, ["/a/b/c.txt"], ["/", "/a"])
    await fs.close()

    print("== S7. segment postings and the fs edge of /a/b/c.txt removed")
    fs, storage = await seeded()
    t = storage._host.tables
    cid = (await fetch(storage, select(t.entry.c.entry_id).where(t.entry.c.path == "/a/b/c.txt")))[0][0]
    await run_sql(
        storage,
        delete(t.segments).where(t.segments.c.entry_id == cid),
        delete(t.edges).where(t.edges.c.target_id == cid, t.edges.c.edge_type == "fs"),
    )
    await attempt("glob **/b/*.txt", fs.glob("**/b/*.txt", authority=SYSTEM))
    await attempt("glob /a/b/*.txt", fs.glob("/a/b/*.txt", authority=SYSTEM))
    await attempt("traverse inbound /a/b/c.txt", fs.traverse("inbound", "/a/b/c.txt", authority=SYSTEM))
    await attempt("traverse outbound /a/b", fs.traverse("outbound", "/a/b", authority=SYSTEM))
    await battery(fs, storage, ["/a/b/c.txt"], ["/a/b"])
    await attempt("glob **/b/*.txt after rebuild", fs.glob("**/b/*.txt", authority=SYSTEM))
    await fs.close()


asyncio.run(main())
