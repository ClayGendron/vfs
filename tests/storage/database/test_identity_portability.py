"""Durable references survive integer renumbering — the identity contract.

A mount's rows, copied row-wise into a freshly provisioned schema with
every integer ``id`` re-minted (entries are even inserted in reversed
order so the new ids cannot match the old), must leave tree traversal,
listings, content reads, parent wiring, and every dependent store —
versions, chunks, edges — fully intact: everything durable joins on
``entry_id``, and the integer is a local locator no reference depends
on. No verb authors the dependent stores yet, so their rows are seeded
directly, keyed by the written entries' identities.
"""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage


async def test_row_copy_survives_integer_renumbering(tmp_path) -> None:
    src = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/src.sqlite")
    written = await src.write(
        entries=[
            Entry(path=Path("/projects"), kind="directory"),
            Entry(path=Path("/projects/docs"), kind="directory"),
            Entry(path=Path("/projects/docs/a.md"), content="alpha"),
            Entry(path=Path("/projects/notes.txt"), content="beta"),
        ],
    )
    assert written.success is True
    expected_tree = [(str(o.path), o.kind, o.version) for o in (await src.tree(path=Path("/"))).observations]
    tables = src._host.tables

    # No verb authors the dependent stores yet: seed a version, a chunk,
    # and an edge keyed by the written entries' identities.
    async with src._host.engine.begin() as conn:
        keys = {
            row.path: row.entry_id for row in await conn.execute(select(tables.entry.c.path, tables.entry.c.entry_id))
        }
        await conn.execute(
            insert(tables.versions).values(
                entry_id=keys["/projects/docs/a.md"],
                version_number=1,
                is_snapshot=True,
                content_hash="hash-a1",
                content="alpha",
            )
        )
        await conn.execute(
            insert(tables.chunks).values(
                entry_id=keys["/projects/docs/a.md"], chunk_index=0, line_start=1, line_end=1, content="alpha"
            )
        )
        await conn.execute(
            insert(tables.edges).values(
                source_id=keys["/projects/docs/a.md"], target_id=keys["/projects/notes.txt"], edge_type="links_to"
            )
        )

    async with src._host.engine.connect() as conn:
        entry_rows = [dict(m) for m in (await conn.execute(select(tables.entry))).mappings()]
        content_rows = [dict(m) for m in (await conn.execute(select(tables.content))).mappings()]
        meta_rows = [dict(m) for m in (await conn.execute(select(tables.meta))).mappings()]
        version_rows = [dict(m) for m in (await conn.execute(select(tables.versions))).mappings()]
        chunk_rows = [dict(m) for m in (await conn.execute(select(tables.chunks))).mappings()]
        edge_rows = [dict(m) for m in (await conn.execute(select(tables.edges))).mappings()]
    await src.close()

    # Row-wise copy: drop every integer id and insert entries children-first,
    # so the destination's re-minted ids cannot reproduce the source mapping.
    fresh = build_vfs_tables(table_name="vfs")
    dest_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/dest.sqlite")
    async with dest_engine.begin() as conn:
        await conn.run_sync(fresh.metadata.create_all)
        for row in reversed(entry_rows):
            await conn.execute(insert(fresh.entry).values(**{k: v for k, v in row.items() if k != "id"}))
        for row in content_rows:
            await conn.execute(insert(fresh.content).values(**row))
        for row in meta_rows:
            await conn.execute(insert(fresh.meta).values(**row))
        for row in version_rows:
            await conn.execute(insert(fresh.versions).values(**row))
        for row in chunk_rows:
            await conn.execute(insert(fresh.chunks).values(**{k: v for k, v in row.items() if k != "id"}))
        for row in edge_rows:
            await conn.execute(insert(fresh.edges).values(**{k: v for k, v in row.items() if k != "id"}))
    await dest_engine.dispose()

    dest = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/dest.sqlite")
    tree = await dest.tree(path=Path("/"))
    assert [(str(o.path), o.kind, o.version) for o in tree.observations] == expected_tree
    listing = await dest.ls(path=Path("/projects"))
    assert {str(o.path) for o in listing.observations} == {"/projects/docs", "/projects/notes.txt"}
    read = await dest.read(path=Path("/projects/docs/a.md"))
    assert read.observations[0].content == "alpha"

    # The dependent stores joined through the copy: version history, chunk
    # rows, and the edge triple all resolve by entry_id alone.
    copied = dest._host.tables
    entry, versions, chunks, edges = copied.entry, copied.versions, copied.chunks, copied.edges
    async with dest._host.engine.connect() as conn:
        source, target = entry.alias(), entry.alias()
        linked = (
            await conn.execute(
                select(source.c.path, target.c.path, edges.c.edge_type).select_from(
                    edges.join(source, source.c.entry_id == edges.c.source_id).join(
                        target, target.c.entry_id == edges.c.target_id
                    )
                )
            )
        ).all()
        assert linked == [("/projects/docs/a.md", "/projects/notes.txt", "links_to")]
        history = (
            await conn.execute(
                select(versions.c.version_number, versions.c.content)
                .select_from(versions.join(entry, entry.c.entry_id == versions.c.entry_id))
                .where(entry.c.path == "/projects/docs/a.md")
            )
        ).all()
        assert history == [(1, "alpha")]
        pieces = (
            await conn.execute(
                select(chunks.c.chunk_index, chunks.c.content).select_from(
                    chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
                )
            )
        ).all()
        assert pieces == [(0, "alpha")]

    appended = await dest.write(entries=[Entry(path=Path("/projects/docs/b.md"), content="gamma")])
    assert appended.success is True  # new children wire to copied parents by entry_id
    docs = await dest.ls(path=Path("/projects/docs"))
    assert sorted(str(o.path) for o in docs.observations) == ["/projects/docs/a.md", "/projects/docs/b.md"]
    await dest.close()
