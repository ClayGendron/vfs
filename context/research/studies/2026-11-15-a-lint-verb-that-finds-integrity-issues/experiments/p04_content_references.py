"""Probe 04, the content layer: what the rows know about references between files, and what a caller may learn."""

from __future__ import annotations

import asyncio

from sqlalchemy import select, text

from lint_common import ALICE, SYSTEM, StatementCounter, attempt, fetch, make, plan
from vfs.models.links import extract_links, link_candidates
from vfs.paths import Path

LINKS = (
    "SELECT s.path, g.edge_type, g.provenance, t.path, t.deleted_at IS NOT NULL, g.weight, g.context"
    " FROM vfs_edges g JOIN vfs_entries s ON s.entry_id = g.source_id JOIN vfs_entries t ON t.entry_id = g.target_id"
    " WHERE g.edge_type <> 'fs' ORDER BY s.path, t.path"
)
LINK_TO_TOMBSTONE = (
    "SELECT s.path, t.path FROM vfs_edges g JOIN vfs_entries s ON s.entry_id = g.source_id"
    " JOIN vfs_entries t ON t.entry_id = g.target_id"
    " WHERE g.edge_type <> 'fs' AND s.deleted_at IS NULL AND t.deleted_at IS NOT NULL"
)
NO_INBOUND = (
    "SELECT e.path FROM vfs_entries e WHERE e.kind = 'file' AND e.deleted_at IS NULL AND e.path LIKE '/wiki/%'"
    " AND NOT EXISTS (SELECT 1 FROM vfs_edges g WHERE g.target_id = e.entry_id AND g.edge_type <> 'fs') ORDER BY e.path"
)
TWINS = (
    "SELECT e.content_hash, COUNT(*) FROM vfs_entries e WHERE e.kind = 'file' AND e.deleted_at IS NULL"
    " AND e.content_hash IS NOT NULL GROUP BY e.content_hash HAVING COUNT(*) > 1"
)
TWIN_PATHS = "SELECT path FROM vfs_entries WHERE content_hash = :h AND deleted_at IS NULL ORDER BY path"


async def rows(storage, sql: str, **params):
    async with storage._host.session_factory() as session:
        return [tuple(r) for r in await session.execute(text(sql), params)]


async def links(storage, label: str) -> None:
    print(f"    link rows {label}:")
    for source, kind, provenance, target, dead, weight, context in await rows(storage, LINKS):
        print(f"      {source} -[{kind}/{provenance} w={weight}]-> {target}{' (tombstoned)' if dead else ''}  context={context!r}")


async def reextract(storage, label: str) -> None:
    """The check that needs bodies: parse each markdown body again and probe every candidate path."""
    t = storage._host.tables
    with StatementCounter(storage) as counter:
        docs = await fetch(
            storage,
            select(t.entry.c.path, t.content.c.content)
            .select_from(t.entry.join(t.content, t.content.c.entry_id == t.entry.c.entry_id))
            .where(t.entry.c.ext.in_(("md", "markdown")), t.entry.c.deleted_at.is_(None))
            .order_by(t.entry.c.path),
        )
        parsed = extract_links([doc.content for doc in docs])
        wanted = {str(c) for doc, refs in zip(docs, parsed, strict=True) for ref in refs for c in link_candidates(Path(doc.path), ref.dest)}
        live = {r.path for r in await fetch(storage, select(t.entry.c.path).where(t.entry.c.path.in_(sorted(wanted)), t.entry.c.deleted_at.is_(None)))}
    broken = [
        (doc.path, ref.dest)
        for doc, refs in zip(docs, parsed, strict=True)
        for ref in refs
        if not any(str(c) in live for c in link_candidates(Path(doc.path), ref.dest))
    ]
    print(f"    re-extraction {label}: documents={len(docs)} candidate paths={len(wanted)} statements={counter.statements} broken={broken}")


async def main() -> None:
    fs, storage = make()
    files = {
        "/wiki/index.md": "# Index\nSee [A](a.md), [B](b.md), [gone](nope.md), [later](later.md) and `b.md`.\n",
        "/wiki/a.md": "# A\nBuilds on [B](b.md) and [the secret](/private/secret.md).\n",
        "/wiki/b.md": "# B\nNo links here.\n",
        "/wiki/lonely.md": "# Lonely\nNothing links to this page.\n",
        "/wiki/dup1.md": "# Same\nidentical body\n",
        "/wiki/dup2.md": "# Same\nidentical body\n",
        "/private/secret.md": "# Secret\nonly system reads this\n",
    }
    for path, body in files.items():
        await fs.write(path=path, content=body, parents=True, authority=SYSTEM)
    await fs.posture("/private", "none", authority=SYSTEM)
    result = await storage.rebuild()
    print("== C1. What the rebuild's extractor says and stores")
    for error in result.errors:
        print(f"    rebuild note: kind={error.kind.value} sev={error.severity.value} msg={error.message!r} data={error.data}")
    await links(storage, "after the first rebuild")
    await reextract(storage, "after the first rebuild")

    print("== C2. The missing target is created later")
    await fs.write(path="/wiki/later.md", content="# Later\nnow I exist\n", authority=SYSTEM)
    await attempt("refresh", storage.refresh())
    result = await attempt("rebuild", storage.rebuild())
    await links(storage, "after later.md exists and a refresh and a rebuild ran")
    e = storage._host.tables.entry
    print("    stamps of index.md:", await fetch(storage, select(e.c.content_hash == e.c.link_source_hash, e.c.link_generation).where(e.c.path == "/wiki/index.md")))

    print("== C3. A link target is deleted, and another is moved")
    await attempt("delete /wiki/b.md", fs.delete("/wiki/b.md", authority=SYSTEM))
    await attempt("move /wiki/a.md /wiki/a2.md", fs.move("/wiki/a.md", "/wiki/a2.md", authority=SYSTEM))
    await attempt("rebuild", storage.rebuild())
    await links(storage, "after the delete, the move and a rebuild")
    print("    rows-only check, link to a tombstoned row:", await rows(storage, LINK_TO_TOMBSTONE))
    await attempt("traverse outbound /wiki/index.md", fs.traverse("outbound", "/wiki/index.md", authority=SYSTEM))
    await reextract(storage, "after the delete and the move")

    print("== C4. Rows-only wiki checks and their plans")
    print("    files nothing links to:", [r[0] for r in await rows(storage, NO_INBOUND)])
    for line in await plan(storage, NO_INBOUND):
        print(f"      plan: {line}")
    twins = await rows(storage, TWINS)
    print("    content hashes held by more than one live file:", [(h[:8], n) for h, n in twins])
    for h, _ in twins:
        print(f"      {h[:8]}: {[r[0] for r in await rows(storage, TWIN_PATHS, h=h)]}")
    for line in await plan(storage, TWINS):
        print(f"      plan: {line}")

    print("== C5. What a caller who may not read a target learns today")
    await attempt("alice reads /private/secret.md (exists, hidden)", fs.read("/private/secret.md", authority=ALICE))
    await attempt("alice reads /private/nothing.md (does not exist)", fs.read("/private/nothing.md", authority=ALICE))
    await attempt("alice stats /private/secret.md", fs.stat("/private/secret.md", authority=ALICE))
    await attempt("alice traverse outbound /wiki/a2.md", fs.traverse("outbound", "/wiki/a2.md", authority=ALICE))
    await attempt("system traverse outbound /wiki/a2.md", fs.traverse("outbound", "/wiki/a2.md", authority=SYSTEM))
    await attempt("alice traverse inbound /wiki/lonely.md", fs.traverse("inbound", "/wiki/lonely.md", authority=ALICE))
    await attempt("alice globs /private/**", fs.glob("/private/**", authority=ALICE))

    print("== C6. A grant on a path whose row was purged, then the path is written again")
    await attempt("grant /private/secret.md alice read", fs.grant("/private/secret.md", "alice", "read", authority=SYSTEM))
    await attempt("alice reads /private/secret.md", fs.read("/private/secret.md", authority=ALICE))
    await attempt("sweep /private/secret.md (purge)", fs.sweep("/private/secret.md", authority=SYSTEM))
    print("    grant rows left:", await rows(storage, "SELECT principal_id, path_prefix, level FROM vfs_grants ORDER BY id"))
    await attempt("system writes a new /private/secret.md", fs.write(path="/private/secret.md", content="a different secret\n", authority=SYSTEM))
    await attempt("alice reads the new /private/secret.md", fs.read("/private/secret.md", authority=ALICE))
    await fs.close()


asyncio.run(main())
