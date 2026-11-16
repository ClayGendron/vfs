"""Probe 05, cost: each check as a keyset page, a directory form and a subtree form, with plans, statements and rows.

Counts are the evidence. The clock lines are facts about this machine and this in-process SQLite, nothing more.
"""

from __future__ import annotations

import asyncio
import hashlib
import platform
from time import perf_counter

from sqlalchemy import text

from lint_common import SYSTEM, StatementCounter, counts, make, plan
from vfs.models import Entry

FILES = 20_000
PER_DIR = 100
PAGE = 1_000

STRUCTURE_PAGE = (
    "SELECT e.id, e.path, p.id IS NULL AS dangling,"
    " e.path <> (CASE WHEN p.path = '/' THEN '' ELSE p.path END) || '/' || e.name AS torn,"
    " p.kind <> 'directory' AS under_file, (e.deleted_at IS NULL AND p.deleted_at IS NOT NULL) AS live_under_dead,"
    " g.id IS NULL AS no_fs_edge"
    " FROM vfs_entries e LEFT JOIN vfs_entries p ON p.entry_id = e.parent_id"
    " LEFT JOIN vfs_edges g ON g.target_id = e.entry_id AND g.edge_type = 'fs' AND g.source_id = e.parent_id"
    " WHERE e.parent_id IS NOT NULL AND {scope} ORDER BY {order} LIMIT :n"
)
SCOPES = {
    "whole mount, keyset on id": ("e.id > :after", "e.id"),
    "one directory's children": ("e.parent_id = (SELECT entry_id FROM vfs_entries WHERE path = :dir) AND e.name > :after", "e.name"),
    "one subtree, keyset on path": ("e.path > :after AND e.path < :stop", "e.path"),
}
BODY_PAGE = (
    "SELECT e.id, e.path, e.content_hash, e.size_bytes, c.content FROM vfs_entries e"
    " LEFT JOIN vfs_content c ON c.entry_id = e.entry_id WHERE e.kind = 'file' AND e.source = 'text' AND e.id > :after"
    " ORDER BY e.id LIMIT :n"
)
ANTI_JOINS = {
    "content with no entry": "SELECT c.entry_id FROM vfs_content c WHERE c.entry_id > :after AND NOT EXISTS"
    " (SELECT 1 FROM vfs_entries e WHERE e.entry_id = c.entry_id) ORDER BY c.entry_id LIMIT :n",
    "version with no entry": "SELECT v.entry_id FROM vfs_versions v WHERE v.entry_id > :after AND NOT EXISTS"
    " (SELECT 1 FROM vfs_entries e WHERE e.entry_id = v.entry_id) ORDER BY v.entry_id LIMIT :n",
    "chunk with no entry": "SELECT c.id FROM vfs_chunks c WHERE c.id > :after AND NOT EXISTS"
    " (SELECT 1 FROM vfs_entries e WHERE e.entry_id = c.entry_id) ORDER BY c.id LIMIT :n",
    "edge with a missing endpoint": "SELECT g.id FROM vfs_edges g WHERE g.id > :after AND (NOT EXISTS"
    " (SELECT 1 FROM vfs_entries e WHERE e.entry_id = g.source_id) OR NOT EXISTS"
    " (SELECT 1 FROM vfs_entries e WHERE e.entry_id = g.target_id)) ORDER BY g.id LIMIT :n",
    "grant on a path with no row": "SELECT g.id FROM vfs_grants g WHERE g.id > :after AND NOT EXISTS"
    " (SELECT 1 FROM vfs_entries e WHERE e.path = g.path_prefix) ORDER BY g.id LIMIT :n",
    "version chain gap": "SELECT e.id FROM vfs_entries e WHERE e.kind = 'file' AND e.id > :after AND e.version - 1 <>"
    " (SELECT COUNT(*) FROM vfs_versions v WHERE v.entry_id = e.entry_id) ORDER BY e.id LIMIT :n",
    "marked covered, no chunk rows": "SELECT e.id FROM vfs_entries e WHERE e.kind = 'file' AND e.chunked AND e.size_bytes > 0"
    " AND e.id > :after AND NOT EXISTS (SELECT 1 FROM vfs_chunks c WHERE c.entry_id = e.entry_id) ORDER BY e.id LIMIT :n",
    "file nothing links to": "SELECT e.id FROM vfs_entries e WHERE e.kind = 'file' AND e.deleted_at IS NULL AND e.id > :after"
    " AND NOT EXISTS (SELECT 1 FROM vfs_edges g WHERE g.target_id = e.entry_id AND g.edge_type <> 'fs') ORDER BY e.id LIMIT :n",
    "link to a tombstoned row": "SELECT g.id FROM vfs_edges g JOIN vfs_entries t ON t.entry_id = g.target_id"
    " WHERE g.edge_type <> 'fs' AND t.deleted_at IS NOT NULL AND g.id > :after ORDER BY g.id LIMIT :n",
    "two files with one content hash (whole mount)": "SELECT e.content_hash, COUNT(*) FROM vfs_entries e"
    " WHERE e.content_hash IS NOT NULL GROUP BY e.content_hash HAVING COUNT(*) > 1",
    "two files with one content hash (one subtree, probing the mount)": "SELECT e.path FROM vfs_entries e"
    " WHERE e.path > :after AND e.path < :stop AND e.kind = 'file' AND EXISTS (SELECT 1 FROM vfs_entries o"
    " WHERE o.content_hash = e.content_hash AND o.id <> e.id) ORDER BY e.path LIMIT :n",
}


async def paged(storage, sql: str, key: int, params: dict, *, start) -> tuple[int, int, int, float]:
    """Run *sql* page after page; returns (statements, rows, findings, seconds)."""
    after, rows, findings = start, 0, 0
    began = perf_counter()
    with StatementCounter(storage) as counter:
        async with storage._host.session_factory() as session:
            while True:
                page = (await session.execute(text(sql), {**params, "after": after, "n": PAGE})).all()
                rows += len(page)
                findings += sum(1 for row in page if any(bool(flag) for flag in row[2:]))
                if len(page) < PAGE:
                    break
                after = page[-1][key]
    return counter.statements, rows, findings, perf_counter() - began


async def main() -> None:
    print(f"machine: {platform.machine()} {platform.system()} python {platform.python_version()}; in-process SQLite")
    fs, storage = make()
    began = perf_counter()
    for start in range(0, FILES, 10_000):
        batch = [
            Entry(path=f"/data/t{i % 4}/d{i // PER_DIR:04d}/f{i:06d}.txt", content=f"file number {i}\nsecond line of {i}\n")
            for i in range(start, start + 10_000)
        ]
        result = await fs.write(batch, parents=True, authority=SYSTEM)
        assert not result.errors, result.errors[:2]
    print(f"seeded {FILES} files in {perf_counter() - began:.1f}s; counts: {await counts(storage, 'entry', 'content', 'edges', 'segments', 'versions', 'chunks')}")

    print("== K1. The structure check: one statement per page, each row joined to its parent and its fs edge")
    for label, (scope, order) in SCOPES.items():
        sql = STRUCTURE_PAGE.format(scope=scope, order=order)
        params = {"dir": "/data/t0/d0000", "stop": "/data/t00"} if "directory" in label or "subtree" in label else {}
        if "whole" in label:
            params, start, key = {}, 0, 0
        elif "directory" in label:
            params, start, key = {"dir": "/data/t0/d0000"}, "", 1
            sql = sql.replace("SELECT e.id, e.path,", "SELECT e.id, e.name,")
        else:
            params, start, key = {"stop": "/data/t0/d00050"}, "/data/t0/d0000/", 1
        statements, rows, findings, seconds = await paged(storage, sql, key, params, start=start)
        print(f"  {label}: statements={statements} rows visited={rows} findings={findings} clock={seconds * 1000:.0f} ms")
        for line in await plan(storage, sql, {**params, "after": start, "n": PAGE}):
            print(f"      plan: {line}")

    print("== K2. The bytes check: one statement per page of bodies, hashed in this process")
    after, rows, size, faults = 0, 0, 0, 0
    began = perf_counter()
    hashing = 0.0
    with StatementCounter(storage) as counter:
        async with storage._host.session_factory() as session:
            while True:
                page = (await session.execute(text(BODY_PAGE), {"after": after, "n": PAGE})).all()
                tick = perf_counter()
                for row in page:
                    body = (row.content or "").encode()
                    size += len(body)
                    faults += row.content is None or hashlib.sha256(body).hexdigest() != row.content_hash
                hashing += perf_counter() - tick
                rows += len(page)
                if len(page) < PAGE:
                    break
                after = page[-1].id
    print(f"  whole mount: statements={counter.statements} bodies={rows} bytes={size} faults={faults} clock={(perf_counter() - began) * 1000:.0f} ms of which hashing {hashing * 1000:.0f} ms")
    for line in await plan(storage, BODY_PAGE, {"after": 0, "n": PAGE}):
        print(f"      plan: {line}")
    blob = b"x" * 64_000_000
    tick = perf_counter()
    hashlib.sha256(blob).hexdigest()
    print(f"  sha256 of 64 MB in one call: {(perf_counter() - tick) * 1000:.0f} ms")

    print("== K3. The plans of the dependent-row, index-cover and content checks")
    for label, sql in ANTI_JOINS.items():
        params = {"after": "/data/t0/d0000/" if ":stop" in sql else 0, "n": PAGE, "stop": "/data/t0/d00050"}
        if "c.entry_id > :after" in sql or "v.entry_id > :after" in sql:
            params["after"] = b""
        used = {k: v for k, v in params.items() if f":{k}" in sql}
        began = perf_counter()
        async with storage._host.session_factory() as session:
            found = (await session.execute(text(sql), used)).all()
        print(f"  {label}: first page rows={len(found)} clock={(perf_counter() - began) * 1000:.0f} ms")
        for line in await plan(storage, sql, used):
            print(f"      plan: {line}")
    await fs.close()


asyncio.run(main())
