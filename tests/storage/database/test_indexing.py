"""The reindex verb: chunking, epoch builds, publish atomicity, gates.

Direct backend tests (reindex is an admin method beside close(), not a
routed verb): flag lifecycle against real sqlite rows, the epoch
fingerprint no-op, drop-and-rebuild on options drift, the eligibility
gates' scan-side residency, and the publish CAS losing to a rival.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from sqlalchemy import event, func, select, update
from sqlalchemy.dialects import mssql, postgresql

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.models.code_grams import pack_gram
from vfs.models.postings import decode_postings, encode_postings
from vfs.models.rows import ENCODING_DELTA_VARINT, build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database.dialects import GENERIC, POSTGRESQL
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.seams import installed

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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


async def _seed_built_epoch(storage: DatabaseStorage, epoch: int, *, with_fingerprint: bool) -> None:
    """Stage a rival's committed build: posting rows at *epoch*, pointer unmoved."""
    tables = storage._host.tables
    blob = encode_postings([1])
    row = {
        "epoch": epoch,
        "gram_key": pack_gram(ord("a"), ord("b"), ord("c")),
        "postings": blob,
        "encoding": ENCODING_DELTA_VARINT,
        "doc_count": 1,
        "byte_size": len(blob),
    }
    async with storage._host.engine.begin() as conn:
        await conn.execute(tables.posting_list.insert(), [row])
        if with_fingerprint:
            fingerprint = {
                "epoch": epoch,
                "format_version": indexing.INDEX_FORMAT_VERSION,
                "options_hash": indexing.index_options_hash(),
            }
            await conn.execute(tables.gram_epochs.insert(), [fingerprint])


class TestStatementLegality:
    async def test_pending_probe_is_row_presence_not_bare_exists_on_tsql(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        tables = storage._host.tables
        sql = str(indexing._pending_probe(tables.entry, tables.chunks).compile(dialect=mssql.dialect())).upper()
        assert not sql.startswith("SELECT EXISTS")
        assert "WHERE" in sql and "EXISTS" in sql  # the correlated probe stays in the WHERE
        await storage.close()


class TestPublishRace:
    async def test_a_rival_built_epoch_collides_into_a_clean_conflict(self, tmp_path, monkeypatch) -> None:
        # The staged rows are what a rival's commit leaves between this
        # build's epoch mint and its posting insert: the same epoch number.
        storage = DatabaseStorage(url=_url(tmp_path))
        monkeypatch.setattr(storage._host, "_retry_attempts", 2)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        await _seed_built_epoch(storage, 1, with_fingerprint=False)
        result = await storage.reindex()
        assert result.success is False
        error = result.errors[0]
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "unique" not in error.message.lower() and "constraint" not in error.message.lower()
        await storage.close()

    async def test_a_crashed_build_never_poisons_the_number_line(self, tmp_path) -> None:
        # A built-but-unpublished epoch is skipped by the next mint and
        # reclaimed once the pointer moves past it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        await _seed_built_epoch(storage, 7, with_fingerprint=True)
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 8
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            epochs = (await conn.execute(select(tables.posting_list.c.epoch).distinct())).scalars().all()
            fingerprints = (await conn.execute(select(tables.gram_epochs.c.epoch))).scalars().all()
        assert epochs == [8] and fingerprints == [8]
        await storage.close()

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


class TestFlagAlgebra:
    async def test_delete_demotes_encoded_at_the_claim(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        assert (await storage.reindex()).success is True
        assert await _flags(storage, "/a.txt") == (True, True)
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        assert await _flags(storage, str(trash_path)) == (True, False)
        await storage.close()

    async def test_delete_reindex_restore_stays_greppable_on_both_tiers(self, tmp_path) -> None:
        # The forbidden state: a live row invisible to both tiers after
        # delete → rebuild → restore. Demote-at-delete closes it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        assert (await storage.reindex()).success is True
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="other stuff")])
        assert (await storage.reindex()).success is True  # a rebuild without the trashed row
        assert (await storage.restore(path=trash_path)).success is True
        assert await _flags(storage, "/a.txt") == (True, False)  # pending — the scan side serves
        found = await storage.grep(pattern="needle")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        assert (await storage.reindex()).success is True  # and the next build re-covers
        assert await _flags(storage, "/a.txt") == (True, True)
        found = await storage.grep(pattern="needle")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        await storage.close()

    async def test_trash_scoped_grep_serves_the_trashed_root_scan_side(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        assert (await storage.reindex()).success is True
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        assert (await storage.reindex()).success is True
        assert (await storage.grep(pattern="needle")).observations == []  # default scope hides trash
        found = await storage.grep(pattern="needle", globs=(str(trash_path),))
        assert [str(o.path) for o in found.observations] == [str(trash_path)]
        await storage.close()

    async def test_a_write_racing_the_publish_window_stays_scan_side(self, tmp_path) -> None:
        # The publish flip's version guard: the raced entry keeps fresh
        # flags and the fresh body is served, never stamped over dead grams.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="stale needle")])

        async def rival() -> None:
            fresh = Entry(path=Path("/a.txt"), content="fresh needle")
            assert (await storage.write(entries=[fresh], overwrite=True)).success is True

        with installed("reindex:before-publish", rival):
            assert (await storage.reindex()).success is True
        assert await _flags(storage, "/a.txt") == (False, False)
        found = await storage.grep(pattern="fresh")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        assert (await storage.reindex()).success is True
        assert await _flags(storage, "/a.txt") == (True, True)
        found = await storage.grep(pattern="fresh")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        await storage.close()


class TestReclaim:
    async def test_a_cas_loser_reclaims_its_own_built_epoch(self, tmp_path) -> None:
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
        tables = storage._host.tables
        assert await _count(storage, tables.posting_list) == 0  # the lost build left no residue
        assert await _count(storage, tables.gram_epochs) == 0
        await storage.close()

    async def test_reclaim_never_destroys_a_rivals_newer_published_epoch(self, tmp_path) -> None:
        # A rival publishing between this publish and its reclaim must
        # keep its epoch: reclaim reads the live pointer, never a stale one.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        meta = storage._host.tables.meta

        async def rival() -> None:
            await _seed_built_epoch(storage, 2, with_fingerprint=True)
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(meta).values(current_gram_epoch=2))

        with installed("reindex:before-reclaim", rival):
            result = await storage.reindex()
        assert result.success is True
        assert await _epoch(storage) == 2
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            epochs = (await conn.execute(select(tables.posting_list.c.epoch).distinct())).scalars().all()
        assert epochs == [2]  # the rival's published epoch stands; only the stale one is gone
        await storage.close()

    async def test_reclaim_before_any_publish_is_a_no_op(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        async with storage._host.session_factory() as session:
            result = await indexing.reclaim_epochs(session, storage._host.tables)
        assert result.success is True
        await storage.close()

    async def test_reclaim_built_epoch_never_touches_the_published_pointer(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        assert (await storage.reindex()).success is True
        async with storage._host.session_factory() as session:
            result = await indexing.reclaim_built_epoch(session, storage._host.tables, 1)
        assert result.success is True
        assert await _count(storage, storage._host.tables.posting_list) > 0  # the published rows stand
        await storage.close()


class _RecordingSession:
    """Session double for the flip arms sqlite cannot execute: records, never runs."""

    def __init__(self, dialect: Any) -> None:
        self._dialect = dialect
        self.calls: list[tuple[Any, Any]] = []

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=self._dialect)

    async def execute(self, stmt: Any, params: Any = None) -> None:
        self.calls.append((stmt, params))


def _values_join_dialect() -> Any:
    # The flags supports_values_update reads, declared as the arm intends.
    dialect = postgresql.dialect()
    dialect.update_returning = True
    dialect.update_returning_multifrom = True
    return dialect


class TestFlipArms:
    async def test_the_values_join_arm_is_one_set_based_statement(self) -> None:
        dialect = _values_join_dialect()
        session = _RecordingSession(dialect)
        entry = build_vfs_tables(table_name="vfs").entry
        pairs = [("01A", 1), ("01B", 2)]
        await indexing._flip_flags(
            cast("AsyncSession", session), entry, POSTGRESQL, 2_000, 1_000, pairs, flag="encoded"
        )
        ((stmt, params),) = session.calls
        assert params is None  # set-based, not executemany
        sql = str(stmt.compile(dialect=dialect))
        assert "FROM (VALUES" in sql and "encoded" in sql

    async def test_the_generic_floor_falls_back_to_executemany(self) -> None:
        session = _RecordingSession(postgresql.dialect())
        entry = build_vfs_tables(table_name="vfs").entry
        await indexing._flip_flags(
            cast("AsyncSession", session), entry, GENERIC, 2_000, 1_000, [("01A", 1)], flag="chunked"
        )
        ((_stmt, params),) = session.calls
        assert params == [{"b_id": "01A", "b_ver": 1}]

    async def test_no_pairs_is_a_no_op(self) -> None:
        session = _RecordingSession(postgresql.dialect())
        entry = build_vfs_tables(table_name="vfs").entry
        await indexing._flip_flags(cast("AsyncSession", session), entry, POSTGRESQL, 2_000, 1_000, [], flag="encoded")
        assert session.calls == []


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

    async def test_flag_flips_are_set_based_not_per_row(self, tmp_path) -> None:
        # One statement flips many (entry, version) pairs: executemany
        # degrades to a round trip per row on the MySQL family and MSSQL.
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i:02}.txt"), content=f"needle body {i:02}") for i in range(10)]
        assert (await storage.write(entries=entries)).success is True
        statements: list[tuple[str, bool]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append((statement, executemany))

        assert (await storage.reindex()).success is True
        flips = [(s, many) for s, many in statements if s.startswith("UPDATE") and ("chunked" in s or "encoded" in s)]
        assert len(flips) == 2  # ten pairs fit one statement per flag
        assert all(many is False for _, many in flips)
        await storage.close()
