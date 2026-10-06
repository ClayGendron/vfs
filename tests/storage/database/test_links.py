"""Tests for the extracted ``links`` edges — markdown references minted inside the chunk pass.

Every reindex rewrites the extracted out-edges of the markdown documents
whose stamp pair does not cover their body, and nothing else: a row a
verb authored survives, a changed *target* keeps its in-edges, a
same-body overwrite and a rename re-extract nothing, and a reference
that names no live entry is counted on an info record, never an error.
The signals phase then reads the rows like any other reference edge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from tests.storage.database.test_signals import ENGINE_LEGS
from tests.support.database_helpers import _url
from tests.support.server_schemas import server_storage
from vfs.models import Edge, Entry
from vfs.models import links as links_model
from vfs.paths import Path
from vfs.results import Severity, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import indexing as indexing_module
from vfs.storage.protocol import ResolvedPair
from vfs.storage.ranking import Ranker, Signal

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from vfs.results import Result

# A hub referenced three ways, a directory, a dead link, and a self-link.
GUIDE = (
    "See [the hub](../hub.md) twice: [again](../hub.md#top).\n"
    "Also `notes/plan.md`, the [notes](notes/) directory, and [me](guide.md).\n"
    "A [dead link](missing.md) and [a url](https://example.com/x.md).\n"
)
DOCS = [
    Entry(path=Path("/docs/guide.md"), content=GUIDE),
    Entry(path=Path("/hub.md"), content="# hub\n"),
    Entry(path=Path("/docs/notes/plan.md"), content="plan, links to [hub](/hub.md)\n"),
    Entry(path=Path("/docs/readme.txt"), content="[looks like a link](../hub.md) in a text file\n"),
]


def _mount(tmp_path, ranker: Ranker | None = None) -> DatabaseStorage:
    return DatabaseStorage(url=_url(tmp_path), ranker=ranker)


async def _seed(storage: DatabaseStorage) -> None:
    assert (await storage.write(entries=DOCS, parents=True)).success is True


async def _put(storage: DatabaseStorage, path: str, content: str) -> None:
    assert (await storage.write(entries=[Entry(path=Path(path), content=content)], parents=True)).success is True


async def _edges(storage: DatabaseStorage) -> dict[tuple[str, str, str], tuple[int, float | None, str, str | None]]:
    """Every non-fs edge as ``(source, target, type) → (row id, weight, provenance, context)``."""
    tables = storage._host.tables
    entry, edges = tables.entry, tables.edges
    source, target = entry.alias("source"), entry.alias("target")
    stmt = (
        select(
            source.c.path,
            target.c.path,
            edges.c.edge_type,
            edges.c.id,
            edges.c.weight,
            edges.c.provenance,
            edges.c.context,
        )
        .join(source, source.c.entry_id == edges.c.source_id)
        .join(target, target.c.entry_id == edges.c.target_id)
        .where(edges.c.edge_type != "fs")
    )
    async with storage._host.session_factory() as session:
        rows = (await session.execute(stmt)).all()
    return {(row[0], row[1], row[2]): (row.id, row.weight, row.provenance, row.context) for row in rows}


async def _stamps(storage: DatabaseStorage, path: str) -> tuple[str | None, str | None]:
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        row = (
            await session.execute(select(entry.c.link_source_hash, entry.c.link_generation).where(entry.c.path == path))
        ).one()
    return row.link_source_hash, row.link_generation


def _link_notes(result: Result) -> list[dict]:
    return [error.data for error in result.errors if error.data and error.data.get("leg") == "links"]


# ---------------------------------------------------------------------------
# What a reindex mints
# ---------------------------------------------------------------------------


class TestExtraction:
    async def test_reindex_mints_the_resolved_references_with_count_and_context(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        result = await storage.reindex()
        assert result.success is True
        edges = await _edges(storage)
        assert set(edges) == {
            ("/docs/guide.md", "/hub.md", "links"),
            ("/docs/guide.md", "/docs/notes/plan.md", "links"),
            ("/docs/guide.md", "/docs/notes", "links"),
            ("/docs/notes/plan.md", "/hub.md", "links"),
        }
        _, weight, provenance, context = edges[("/docs/guide.md", "/hub.md", "links")]
        assert (weight, provenance) == (2.0, "extracted")
        assert context == "See [the hub](../hub.md) twice: [again](../hub.md#top)."
        assert edges[("/docs/guide.md", "/docs/notes", "links")][1] == 1.0
        # The dead link is counted, never an error; the url and the self-link are not references.
        [note] = [error for error in result.errors if error.data and error.data.get("leg") == "links"]
        assert (note.severity, note.kind) == (Severity.info, VFSErrorKind.not_found)
        assert note.data == {"leg": "links", "sources": 3, "edges": 4, "unresolved": 1}
        assert (await _stamps(storage, "/docs/guide.md"))[1] == links_model.link_generation()
        await storage.close()

    async def test_a_second_reindex_touches_nothing(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        before = await _edges(storage)
        result = await storage.reindex()
        assert result.success is True and _link_notes(result) == []
        assert await _edges(storage) == before
        await storage.close()

    async def test_a_document_without_references_stamps_but_mints_nothing(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/plain.md", "no links here\n")
        result = await storage.reindex()
        assert result.success is True and _link_notes(result) == []
        assert await _edges(storage) == {}
        assert (await _stamps(storage, "/plain.md"))[1] == links_model.link_generation()
        await storage.close()

    async def test_non_markdown_bodies_are_never_read(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        assert not any(source == "/docs/readme.txt" for source, _, _ in await _edges(storage))
        assert (await _stamps(storage, "/docs/readme.txt"))[1] == links_model.link_generation()
        await storage.close()


# ---------------------------------------------------------------------------
# The ledger: what a rerun replaces and what it leaves alone
# ---------------------------------------------------------------------------


class TestLedger:
    async def test_a_changed_source_is_replaced_not_duplicated(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        await _put(storage, "/docs/guide.md", "only [the hub](../hub.md) now\n")
        assert (await storage.reindex()).success is True
        edges = await _edges(storage)
        assert {key for key in edges if key[0] == "/docs/guide.md"} == {("/docs/guide.md", "/hub.md", "links")}
        assert edges[("/docs/guide.md", "/hub.md", "links")][1] == 1.0
        await storage.close()

    async def test_a_source_whose_links_were_all_removed_loses_its_edges(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        await _put(storage, "/docs/guide.md", "prose only\n")
        assert (await storage.reindex()).success is True
        assert not any(source == "/docs/guide.md" for source, _, _ in await _edges(storage))
        await storage.close()

    async def test_a_changed_target_keeps_its_in_edges_untouched(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        row_id = (await _edges(storage))[("/docs/guide.md", "/hub.md", "links")][0]
        await _put(storage, "/hub.md", "# hub, revised\n")
        assert (await storage.reindex()).success is True
        assert (await _edges(storage))[("/docs/guide.md", "/hub.md", "links")][0] == row_id

    async def test_a_same_body_overwrite_and_a_rename_re_extract_nothing(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        row_id = (await _edges(storage))[("/docs/guide.md", "/hub.md", "links")][0]
        await _put(storage, "/docs/guide.md", GUIDE)
        moved = ResolvedPair(src=Path("/docs/guide.md"), dest=Path("/docs/moved.md"))
        assert (await storage.move(operations=[moved])).success is True
        result = await storage.reindex()
        assert result.success is True and _link_notes(result) == []
        assert (await _edges(storage))[("/docs/moved.md", "/hub.md", "links")][0] == row_id
        await storage.close()

    async def test_a_user_minted_row_on_the_same_triple_survives_a_rerun(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        edge = Edge(source=Path("/docs/guide.md"), target=Path("/hub.md"), edge_type="links", weight=9.0)
        assert (await storage.mkedge(edges=[edge], provenance="user")).success is True
        result = await storage.reindex()
        assert result.success is True
        edges = await _edges(storage)
        assert edges[("/docs/guide.md", "/hub.md", "links")][1:] == (9.0, "user", None)
        assert _link_notes(result) == [{"leg": "links", "sources": 3, "edges": 3, "unresolved": 1}]
        await storage.close()

    async def test_a_touch_claims_an_extracted_row_and_the_extractor_then_leaves_it(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        edge = Edge(source=Path("/docs/guide.md"), target=Path("/hub.md"), edge_type="links", weight=5.0)
        assert (await storage.mkedge(edges=[edge], provenance="agent")).success is True
        await _put(storage, "/docs/guide.md", "[hub](../hub.md)\n")
        assert (await storage.reindex()).success is True
        assert (await _edges(storage))[("/docs/guide.md", "/hub.md", "links")][1:3] == (5.0, "agent")
        await storage.close()

    async def test_rmedge_removes_an_extracted_row_until_its_source_changes(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        edge = Edge(source=Path("/docs/guide.md"), target=Path("/hub.md"), edge_type="links")
        assert (await storage.rmedge(edges=[edge])).success is True
        assert (await storage.reindex()).success is True
        assert ("/docs/guide.md", "/hub.md", "links") not in await _edges(storage)
        await _put(storage, "/docs/guide.md", "[hub](../hub.md)\n")
        assert (await storage.reindex()).success is True
        assert ("/docs/guide.md", "/hub.md", "links") in await _edges(storage)
        await storage.close()

    async def test_a_deleted_target_cascades_its_extracted_in_edges(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        assert (await storage.delete(path=Path("/hub.md"))).success is True
        assert not any(target == "/hub.md" for _, target, _ in await _edges(storage))
        await storage.close()

    async def test_a_generation_bump_re_extracts_every_document_once(self, tmp_path, monkeypatch) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        row_id = (await _edges(storage))[("/docs/guide.md", "/hub.md", "links")][0]
        monkeypatch.setattr(indexing_module, "link_generation", lambda: "md:test")
        assert (await storage.reindex()).success is True
        edges = await _edges(storage)
        assert edges[("/docs/guide.md", "/hub.md", "links")][0] != row_id
        assert (await _stamps(storage, "/docs/guide.md"))[1] == "md:test"
        assert (await storage.reindex()).success is True
        assert await _edges(storage) == edges
        await storage.close()

    async def test_a_reference_resolves_once_its_target_exists_and_the_source_changes(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        await _put(storage, "/docs/missing.md", "here now\n")
        assert (await storage.reindex()).success is True
        assert ("/docs/guide.md", "/docs/missing.md", "links") not in await _edges(storage)
        await _put(storage, "/docs/guide.md", "[found](missing.md)\n")
        result = await storage.reindex()
        assert result.success is True and _link_notes(result) == []
        assert ("/docs/guide.md", "/docs/missing.md", "links") in await _edges(storage)
        await storage.close()


# ---------------------------------------------------------------------------
# The consumer: the centrality prior reads the extracted rows
# ---------------------------------------------------------------------------


class TestSignals:
    async def test_the_prior_counts_extracted_references(self, tmp_path) -> None:
        ranker = Ranker(signals=(Signal("centrality", weight=0.5),))
        storage = _mount(tmp_path, ranker)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        signals, entry = storage._host.tables.signals, storage._host.tables.entry
        async with storage._host.session_factory() as session:
            rows = (
                await session.execute(
                    select(entry.c.path, signals.c.value).join(entry, entry.c.entry_id == signals.c.entry_id)
                )
            ).all()
        stored = {row.path: row.value for row in rows}
        assert stored["/hub.md"] == 1.0
        assert all(stored.get(path, 0.0) < 1.0 for path in ("/docs/guide.md", "/docs/notes/plan.md"))
        await storage.close()


# ---------------------------------------------------------------------------
# Engine legs
# ---------------------------------------------------------------------------


def _server_storage(env_var: str) -> AbstractAsyncContextManager[DatabaseStorage]:
    """A backend on *env_var*'s server, in a schema of its own, configured for this file."""
    return server_storage(env_var, ranker=Ranker(signals=(Signal("centrality"),)))


class TestEngineLegs:
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_extraction_replacement_and_the_prior_on_every_engine(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            await _seed(storage)
            edge = Edge(source=Path("/docs/notes/plan.md"), target=Path("/hub.md"), edge_type="links", weight=3.0)
            assert (await storage.mkedge(edges=[edge], provenance="user")).success is True
            result = await storage.reindex()
            assert result.success is True
            edges = await _edges(storage)
            assert edges[("/docs/guide.md", "/hub.md", "links")][1:3] == (2.0, "extracted")
            assert edges[("/docs/notes/plan.md", "/hub.md", "links")][1:3] == (3.0, "user")
            assert _link_notes(result) == [{"leg": "links", "sources": 3, "edges": 3, "unresolved": 1}]
            await _put(storage, "/docs/guide.md", "[hub](../hub.md)\n")
            assert (await storage.reindex()).success is True
            edges = await _edges(storage)
            assert {key for key in edges if key[0] == "/docs/guide.md"} == {("/docs/guide.md", "/hub.md", "links")}
            assert edges[("/docs/guide.md", "/hub.md", "links")][1] == 1.0
            glean = await storage.glean(query="hub")
            assert glean.success is True and glean.observations[0].path == "/hub.md"
