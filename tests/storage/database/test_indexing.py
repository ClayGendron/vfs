"""The reindex verb: chunking, epoch builds, publish atomicity, gates.

Direct backend tests (reindex is an admin method beside close(), not a
routed verb): flag lifecycle against real sqlite rows, the epoch
fingerprint no-op, drop-and-rebuild on options drift, the eligibility
gates' scan-side residency, and the publish CAS losing to a rival.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import event, func, select, update

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.models.code_grams import pack_gram
from vfs.models.postings import decode_postings
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.seams import installed


async def _flags(storage: DatabaseStorage, path: str) -> tuple[bool, bool]:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        row = (await conn.execute(select(entry.c.chunked, entry.c.encoded).where(entry.c.path == path))).one()
    return row._tuple()


async def _epoch(storage: DatabaseStorage) -> int | None:
    meta = storage._host.tables.meta
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()


async def _count(storage: DatabaseStorage, table) -> int:
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(table))).scalar_one()


class TestReindex:
    async def test_reindex_chunks_encodes_and_publishes(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.py"), content="needle one\nneedle two")])
        assert (await storage.reindex()).success is True
        tables = storage._host.tables
        assert await _flags(storage, "/a.py") == (True, True)
        assert await _epoch(storage) == 1
        async with storage._host.engine.connect() as conn:
            chunk = (
                await conn.execute(select(tables.chunks.c.id, tables.chunks.c.line_start, tables.chunks.c.line_end))
            ).one()
            posting = (
                await conn.execute(
                    select(tables.posting_list).where(
                        tables.posting_list.c.gram_key == pack_gram(ord("n"), ord("e"), ord("e"))
                    )
                )
            ).one()
            fingerprint = (await conn.execute(select(tables.gram_epochs))).one()
        assert (chunk.line_start, chunk.line_end) == (1, 2)
        assert np.array_equal(decode_postings(posting.postings), np.array([chunk.id]))
        assert posting.doc_count == 1
        assert posting.byte_size == len(posting.postings)
        assert (fingerprint.epoch, fingerprint.format_version) == (1, indexing.INDEX_FORMAT_VERSION)
        assert fingerprint.options_hash == indexing.index_options_hash()
        await storage.close()

    async def test_reindex_is_idempotent_cheap_when_nothing_is_dirty(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="stable body")])
        assert (await storage.reindex()).success is True
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 1
        assert await _count(storage, storage._host.tables.gram_epochs) == 1
        await storage.close()

    async def test_rewrite_dirties_and_the_next_reindex_advances_the_epoch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="first body")])
        assert (await storage.reindex()).success is True
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="second body")])
        assert await _flags(storage, "/a.txt") == (False, False)
        assert (await storage.reindex()).success is True
        assert await _flags(storage, "/a.txt") == (True, True)
        assert await _epoch(storage) == 2
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            epochs = (await conn.execute(select(tables.posting_list.c.epoch).distinct())).scalars().all()
            fingerprints = (await conn.execute(select(tables.gram_epochs.c.epoch))).scalars().all()
        assert epochs == [2] and fingerprints == [2]  # old epoch reclaimed
        await storage.close()

    async def test_empty_store_mints_an_empty_epoch_once(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 1
        assert await _count(storage, storage._host.tables.posting_list) == 0
        assert (await storage.reindex()).success is True  # and now a no-op
        assert await _epoch(storage) == 1
        await storage.close()

    async def test_trashed_entries_are_left_out(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/gone.txt"), content="trashed body")])
        assert (await storage.delete(path=Path("/gone.txt"))).success is True
        assert (await storage.reindex()).success is True
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            row = (
                await conn.execute(select(entry.c.chunked, entry.c.encoded).where(entry.c.deleted_at.isnot(None)))
            ).one()
        assert row._tuple() == (False, False)  # scan-side wherever it resurfaces
        await storage.close()


class TestEligibilityGates:
    async def test_oversized_content_stays_scan_side_without_retriggering_builds(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "MAX_INDEXABLE_BYTES", 8)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/big.txt"), content="well past eight bytes")])
        assert (await storage.reindex()).success is True
        assert await _flags(storage, "/big.txt") == (True, False)
        assert await _count(storage, storage._host.tables.chunks) == 0
        epoch = await _epoch(storage)
        assert (await storage.reindex()).success is True  # ineligible ≠ pending
        assert await _epoch(storage) == epoch
        await storage.close()

    async def test_gram_saturated_content_stays_scan_side(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "MAX_DISTINCT_GRAMS", 2)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/wide.txt"), content="abcdefgh")])
        assert (await storage.reindex()).success is True
        assert await _flags(storage, "/wide.txt") == (True, False)
        await storage.close()

    async def test_options_drift_forces_a_rebuild_with_no_dirty_rows(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="steady body")])
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 1
        monkeypatch.setattr(indexing, "MAX_DISTINCT_GRAMS", 19_000)  # options hash moves
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        await storage.close()

    async def test_a_missing_fingerprint_row_forces_a_rebuild(self, tmp_path) -> None:
        # A pointer with no fingerprint row is unverifiable — rebuild.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="steady body")])
        assert (await storage.reindex()).success is True
        tables = storage._host.tables
        async with storage._host.engine.begin() as conn:
            await conn.execute(tables.gram_epochs.delete())
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        await storage.close()


class TestPublishRace:
    async def test_a_rival_epoch_flip_loses_the_cas_classified(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="raced body")])
        meta = storage._host.tables.meta

        async def rival() -> None:
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(meta).values(current_gram_epoch=99))

        with installed("reindex:before-publish", rival):
            result = await storage.reindex()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.conflict
        assert await _epoch(storage) == 99  # the rival's publish stood
        await storage.close()


class TestPostingBatches:
    async def test_posting_inserts_split_by_byte_cap(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "_POSTING_BATCH_BYTES", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abcd")])
        assert (await storage.reindex()).success is True  # every row its own statement
        assert await _count(storage, storage._host.tables.posting_list) > 1
        await storage.close()

    async def test_no_reindex_statement_grows_with_entry_count(self, tmp_path, monkeypatch) -> None:
        # The scale law under a tightened budget: stale-chunk deletes
        # chunk their IN-lists, and no statement's bind count exceeds it.
        monkeypatch.setattr(EngineHost, "membership_budget", property(lambda self: 4))
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i:02}.txt"), content=f"needle body {i:02}") for i in range(10)]
        assert (await storage.write(entries=entries)).success is True
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        assert (await storage.reindex()).success is True
        deletes = [s for s in statements if s.startswith("DELETE") and "chunks" in s]
        assert len(deletes) == 3  # ten entries at a budget of four: 4 + 4 + 2
        assert all(s.count("?") <= 4 for s in deletes)
        assert all(s.count("?") <= storage._host.parameter_budget for s in statements)
        await storage.close()
