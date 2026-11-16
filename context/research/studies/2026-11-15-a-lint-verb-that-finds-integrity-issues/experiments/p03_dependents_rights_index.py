"""Probe 03: rows left behind (versions, bodies, chunks, edges, grants, marks, the lease), labels, and index cover."""

from __future__ import annotations

import asyncio
from time import time

from sqlalchemy import delete, insert, select, text, update
from ulid import ULID

from lint_common import ALICE, ANON, SYSTEM, attempt, counts, fetch, make, run_sql
from vfs.storage.backends.database.labels import label_of

RESIDUE = {
    "content with no entry": "SELECT COUNT(*) FROM vfs_content c LEFT JOIN vfs_entries e ON e.entry_id = c.entry_id WHERE e.id IS NULL",
    "version with no entry": "SELECT COUNT(*) FROM vfs_versions v LEFT JOIN vfs_entries e ON e.entry_id = v.entry_id WHERE e.id IS NULL",
    "version subject with no version": "SELECT COUNT(*) FROM vfs_version_subjects s LEFT JOIN vfs_versions v"
    " ON v.entry_id = s.entry_id AND v.version_number = s.version_number WHERE v.entry_id IS NULL",
    "chunk with no entry": "SELECT COUNT(*) FROM vfs_chunks c LEFT JOIN vfs_entries e ON e.entry_id = c.entry_id WHERE e.id IS NULL",
    "lexical doc with no entry": "SELECT COUNT(*) FROM vfs_lex_docs d LEFT JOIN vfs_entries e ON e.entry_id = d.entry_id WHERE e.id IS NULL",
    "segment with no entry": "SELECT COUNT(*) FROM vfs_segments s LEFT JOIN vfs_entries e ON e.entry_id = s.entry_id WHERE e.id IS NULL",
    "edge with a missing endpoint": "SELECT COUNT(*) FROM vfs_edges g LEFT JOIN vfs_entries s ON s.entry_id = g.source_id"
    " LEFT JOIN vfs_entries t ON t.entry_id = g.target_id WHERE s.id IS NULL OR t.id IS NULL",
    "signal with no entry": "SELECT COUNT(*) FROM vfs_signals g LEFT JOIN vfs_entries e ON e.entry_id = g.entry_id WHERE e.id IS NULL",
    "grant on a path with no row": "SELECT COUNT(*) FROM vfs_grants g LEFT JOIN vfs_entries e ON e.path = g.path_prefix WHERE e.id IS NULL",
    "version chain gap": "SELECT COUNT(*) FROM vfs_entries e WHERE e.kind = 'file' AND e.version - 1 <>"
    " (SELECT COUNT(*) FROM vfs_versions v WHERE v.entry_id = e.entry_id)",
    "version number at or above the entry's": "SELECT COUNT(*) FROM vfs_versions v JOIN vfs_entries e ON e.entry_id = v.entry_id"
    " WHERE v.version_number >= e.version",
    "marked covered, no chunk rows": "SELECT COUNT(*) FROM vfs_entries e WHERE e.kind = 'file' AND e.chunked AND e.size_bytes > 0"
    " AND NOT EXISTS (SELECT 1 FROM vfs_chunks c WHERE c.entry_id = e.entry_id)",
    "marked encoded, chunk not in the lexical docs": "SELECT COUNT(*) FROM vfs_entries e JOIN vfs_chunks c ON c.entry_id = e.entry_id"
    " WHERE e.encoded AND e.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM vfs_lex_docs d WHERE d.chunk_id = c.id)",
    "relabel mark standing": "SELECT COUNT(*) FROM vfs_relabels",
    "index lease held": "SELECT COUNT(*) FROM vfs_index_state WHERE lease_holder IS NOT NULL",
}


async def residue(storage, label: str) -> None:
    async with storage._host.session_factory() as session:
        found = {name: (await session.execute(text(sql))).scalar_one() for name, sql in RESIDUE.items()}
    print(f"    residue {label}: {({k: v for k, v in found.items() if v}) or 'clean'}")


async def label_lint(storage) -> None:
    t = storage._host.tables
    postures = {r.path_prefix: r.level for r in await fetch(storage, select(t.grants.c.path_prefix, t.grants.c.level).where(t.grants.c.principal_id == "*"))}
    wrong = [
        (r.path, r.everyone_level, label_of(postures, r.path))
        for r in await fetch(storage, select(t.entry.c.path, t.entry.c.everyone_level))
        if r.everyone_level != label_of(postures, r.path)
    ]
    print(f"    label lint (path, stored, posture gives): {wrong or 'clean'}  postures={postures}")


async def seeded():
    fs, storage = make()
    for path, body in (("/p/a.md", "apple one\n"), ("/p/b.md", "banana one\n"), ("/q/c.md", "cherry one\n")):
        await fs.write(path=path, content=body, parents=True, authority=SYSTEM)
    await fs.write(path="/p/a.md", content="apple two\n", authority=ALICE)
    await fs.write(path="/p/a.md", content="apple three\n", authority=ALICE)
    await fs.mkedge(source="/p/a.md", target="/q/c.md", edge_type="cites", authority=SYSTEM)
    await fs.grant("/q/c.md", "alice", "read", authority=SYSTEM)
    await storage.rebuild()
    return fs, storage


async def main() -> None:
    print("== D0. A clean store")
    fs, storage = await seeded()
    await residue(storage, "clean")
    await label_lint(storage)
    print("    counts:", await counts(storage))
    await fs.close()

    print("== D1. An entry row removed by SQL: every dependent row is left behind")
    fs, storage = await seeded()
    t = storage._host.tables
    await run_sql(storage, delete(t.entry).where(t.entry.c.path == "/p/a.md"), delete(t.entry).where(t.entry.c.path == "/q/c.md"))
    await residue(storage, "after the SQL delete")
    await attempt("traverse outbound /p/b.md", fs.traverse("outbound", "/p/b.md", authority=SYSTEM))
    await attempt("search apple", fs.search("apple", authority=SYSTEM))
    await attempt("grep apple", fs.grep("apple", authority=SYSTEM))
    await attempt("grants /q/c.md", fs.grants("/q/c.md", authority=SYSTEM))
    await attempt("refresh", storage.refresh())
    await residue(storage, "after refresh")
    await attempt("sweep trash", fs.sweep(authority=SYSTEM))
    await residue(storage, "after sweep (the orphan fence is an age)")
    await attempt("rebuild", storage.rebuild())
    await residue(storage, "after rebuild")
    await attempt("write /q/c.md again by system", fs.write(path="/q/c.md", content="a new file at the old path\n", authority=SYSTEM))
    await attempt("alice reads the new /q/c.md", fs.read("/q/c.md", authority=ALICE))
    await attempt("grants /q/c.md", fs.grants("/q/c.md", authority=SYSTEM))
    await fs.close()

    print("== D2. A grant outlives a purge done by the verbs themselves")
    fs, storage = await seeded()
    await attempt("sweep /q/c.md (purge arm)", fs.sweep("/q/c.md", authority=SYSTEM))
    await residue(storage, "after the purge")
    await fs.close()

    print("== D3. A version chain with a gap; a version numbered above its entry")
    fs, storage = await seeded()
    t = storage._host.tables
    aid = (await fetch(storage, select(t.entry.c.entry_id).where(t.entry.c.path == "/p/a.md")))[0][0]
    print("    versions before:", await fetch(storage, select(t.versions.c.version_number).where(t.versions.c.entry_id == aid)), "entry.version:", await fetch(storage, select(t.entry.c.version).where(t.entry.c.entry_id == aid)))
    await run_sql(storage, delete(t.versions).where(t.versions.c.entry_id == aid, t.versions.c.version_number == 1))
    await attempt("read /p/a.md", fs.read("/p/a.md", authority=SYSTEM))
    await attempt("write /p/a.md", fs.write(path="/p/a.md", content="apple four\n", authority=SYSTEM))
    await attempt("rebuild", storage.rebuild())
    await residue(storage, "after the gap")
    await run_sql(storage, update(t.entry).where(t.entry.c.entry_id == aid).values(version=1))
    await attempt("write /p/a.md after entry.version reset to 1", fs.write(path="/p/a.md", content="apple five\n", authority=SYSTEM))
    await residue(storage, "after the reset and a write")
    await fs.close()

    print("== D4. A stored label that differs from the posture")
    fs, storage = await seeded()
    t = storage._host.tables
    await attempt("posture /q none", fs.posture("/q", "none", authority=SYSTEM))
    await label_lint(storage)
    await attempt("anonymous reads /q/c.md", fs.read("/q/c.md", authority=ANON))
    await attempt("anonymous glob **/*.md", fs.glob("**/*.md", authority=ANON))
    await run_sql(storage, update(t.entry).where(t.entry.c.path == "/q/c.md").values(everyone_level=5))
    print("    -- label of /q/c.md raised to 5 by SQL")
    await label_lint(storage)
    await attempt("anonymous reads /q/c.md", fs.read("/q/c.md", authority=ANON))
    await attempt("anonymous glob **/*.md", fs.glob("**/*.md", authority=ANON))
    await attempt("anonymous grep cherry", fs.grep("cherry", authority=ANON))
    await run_sql(storage, update(t.entry).where(t.entry.c.path == "/p/b.md").values(everyone_level=0))
    print("    -- label of /p/b.md lowered to 0 by SQL")
    await attempt("anonymous reads /p/b.md", fs.read("/p/b.md", authority=ANON))
    await attempt("anonymous glob **/*.md", fs.glob("**/*.md", authority=ANON))
    await attempt("rebuild", storage.rebuild())
    await attempt("refresh", storage.refresh())
    await label_lint(storage)
    await attempt("posture /q none again", fs.posture("/q", "none", authority=SYSTEM))
    await label_lint(storage)
    await fs.close()

    print("== D5. A relabel mark left standing with no relabel running")
    fs, storage = await seeded()
    t = storage._host.tables
    revision = (await fetch(storage, select(t.meta.c.grant_revision)))[0][0]
    await run_sql(storage, insert(t.relabels).values(path_prefix="/p", revision=revision, cursor=None))
    await attempt("anonymous reads /p/b.md", fs.read("/p/b.md", authority=ANON))
    await attempt("alice writes /p/new.md", fs.write(path="/p/new.md", content="x\n", authority=ALICE))
    await attempt("rebuild", storage.rebuild())
    await residue(storage, "after rebuild")
    await attempt("posture /q read", fs.posture("/q", "read", authority=SYSTEM))
    await residue(storage, "after an unrelated posture call")
    await fs.close()

    print("== D6. Index cover: a row marked covered that the index does not hold")
    fs, storage = await seeded()
    t = storage._host.tables
    bid = (await fetch(storage, select(t.entry.c.entry_id).where(t.entry.c.path == "/p/b.md")))[0][0]
    print("    flags of /p/b.md:", await fetch(storage, select(t.entry.c.chunked, t.entry.c.encoded, t.entry.c.indexable, t.entry.c.indexed_epoch).where(t.entry.c.entry_id == bid)))
    await attempt("grep banana (clean)", fs.grep("banana", authority=SYSTEM))
    await attempt("search banana (clean)", fs.search("banana", limit=3, authority=SYSTEM))
    await run_sql(storage, delete(t.chunks).where(t.chunks.c.entry_id == bid))
    print("    -- chunk rows of /p/b.md deleted by SQL, flags untouched")
    await attempt("grep banana", fs.grep("banana", authority=SYSTEM))
    await attempt("search banana", fs.search("banana", limit=3, authority=SYSTEM))
    await residue(storage, "after the chunk delete")
    await attempt("refresh", storage.refresh())
    await attempt("grep banana after refresh", fs.grep("banana", authority=SYSTEM))
    await attempt("rebuild", storage.rebuild())
    await attempt("grep banana after rebuild", fs.grep("banana", authority=SYSTEM))
    await attempt("search banana after rebuild", fs.search("banana", limit=3, authority=SYSTEM))
    await residue(storage, "after rebuild")
    print("    -- a new file written, then stamped chunked and encoded by SQL before any index pass")
    await fs.write(path="/p/d.md", content="durian one\n", authority=SYSTEM)
    await run_sql(storage, update(t.entry).where(t.entry.c.path == "/p/d.md").values(chunked=True, encoded=True, indexable=True))
    await attempt("grep durian", fs.grep("durian", authority=SYSTEM))
    await attempt("refresh", storage.refresh())
    await attempt("grep durian after refresh", fs.grep("durian", authority=SYSTEM))
    await attempt("rebuild", storage.rebuild())
    await attempt("grep durian after rebuild", fs.grep("durian", authority=SYSTEM))
    await residue(storage, "after rebuild")
    await fs.close()

    print("== D7. An index lease left behind by a dead runner")
    fs, storage = await seeded()
    t = storage._host.tables
    await run_sql(storage, update(t.index_state).values(lease_holder=str(ULID()), lease_heartbeat=int(time() * 1000)))
    await attempt("rebuild with a fresh foreign lease", storage.rebuild())
    await attempt("refresh with a fresh foreign lease", storage.refresh())
    await run_sql(storage, update(t.index_state).values(lease_heartbeat=int(time() * 1000) - 6 * 60 * 1000))
    await attempt("rebuild once the heartbeat is six minutes old", storage.rebuild())
    await residue(storage, "after")
    await fs.close()

    print("== D8. A dangling parent: does a second rebuild settle")
    fs, storage = await seeded()
    t = storage._host.tables
    await run_sql(storage, update(t.entry).where(t.entry.c.path == "/q/c.md").values(parent_id=str(ULID())))
    for n in (1, 2, 3):
        result = await storage.rebuild()
        print(f"    rebuild {n}: warnings={[e.message[:110] for e in result.errors]}")
    await fs.close()


asyncio.run(main())
