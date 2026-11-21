"""The rebuild verb: chunking, epoch builds, publish atomicity, gates.

Direct backend tests (rebuild is an admin method beside close(), not a
routed verb): flag lifecycle against real sqlite rows, the epoch
fingerprint no-op, drop-and-rebuild on options drift, the eligibility
gates' scan-side residency, and the publish CAS losing to a rival.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

import pytest
from sqlalchemy import event, func, insert, select, update
from sqlalchemy.dialects import postgresql, sqlite

from tests.support.database_helpers import _url
from tests.support.documents import pdf_bytes
from tests.support.loop_ticks import LoopTicker
from tests.support.oracles.postings import decode_postings
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.models.chunk import Chunk
from vfs.models.chunking import chunk_generation
from vfs.models.code_grams import pack_gram
from vfs.models.postings import encode_postings
from vfs.models.rows import ENCODING_DELTA_VARINT, build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database import flags as flags_module
from vfs.storage.backends.database import maintenance as maintenance_module
from vfs.storage.backends.database.dialects import GENERIC, POSTGRESQL, SQLITE
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.seams import installed
from vfs.storage.protocol import ResolvedPair

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables


async def _flags(storage: DatabaseStorage, path: str) -> tuple[bool, bool]:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        row = (await conn.execute(select(entry.c.chunked, entry.c.encoded).where(entry.c.path == path))).one()
    return row._tuple()


async def _indexable_flag(storage: DatabaseStorage, path: str) -> bool:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry.c.indexable).where(entry.c.path == path))).scalar_one()


async def _epoch(storage: DatabaseStorage) -> int | None:
    index_state = storage._host.tables.index_state
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(index_state.c.current_gram_epoch))).scalar_one()


async def _count(storage: DatabaseStorage, table) -> int:
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(table))).scalar_one()


async def _claimed(storage: DatabaseStorage, token: str = "MINE") -> str:
    """Claim the lease for *token*, as the verb does before its phases; the token the fences then check."""
    tables = storage._host.tables
    claim = await storage._execute_maintenance(
        "rebuild", lambda s: maintenance_module.claim_index_lease(s, tables, token)
    )
    assert claim.success, claim.errors
    return token


async def _entry_id(storage: DatabaseStorage, path: str) -> str:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry.c.entry_id).where(entry.c.path == path))).scalar_one()


async def _chunk_ids(storage: DatabaseStorage, path: str) -> set[int]:
    tables = storage._host.tables
    stmt = select(tables.chunks.c.id).where(tables.chunks.c.entry_id == await _entry_id(storage, path))
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _lexical_chunk_ids(storage: DatabaseStorage, path: str) -> set[int]:
    """The chunk ids the published epoch's ``vfs_lex_docs`` names for *path*."""
    docs = storage._host.tables.lex_docs
    entry_id, epoch = await _entry_id(storage, path), await _epoch(storage)
    stmt = select(docs.c.chunk_id).where(docs.c.epoch == epoch, docs.c.entry_id == entry_id)
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _lexical_entries(storage: DatabaseStorage) -> set[str]:
    """Every entry the published epoch's ``vfs_lex_docs`` holds a row for."""
    docs = storage._host.tables.lex_docs
    stmt = select(docs.c.entry_id).where(docs.c.epoch == await _epoch(storage)).distinct()
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _encoded_content(storage: DatabaseStorage) -> set[str]:
    entry = storage._host.tables.entry
    stmt = select(entry.c.entry_id).where(entry.c.encoded, entry.c.kind != "directory")
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _chunked_paths(session: AsyncSession, tables: VFSTables) -> frozenset[str]:
    entry = tables.entry
    stmt = select(entry.c.path).where(entry.c.chunked, entry.c.kind != "directory")
    return frozenset((await session.execute(stmt)).scalars())


async def _split_is_stored(storage: DatabaseStorage, path: str, body: str) -> bool:
    """Whether *path*'s chunk rows are exactly the split of *body*, in order."""
    tables = storage._host.tables
    entry, chunks = tables.entry, tables.chunks
    async with storage._host.engine.connect() as conn:
        ext = (await conn.execute(select(entry.c.ext).where(entry.c.path == path))).scalar_one()
        stmt = select(chunks.c.content).where(chunks.c.entry_id == await _entry_id(storage, path))
        stored = list((await conn.execute(stmt.order_by(chunks.c.chunk_index))).scalars())
    [pieces] = Chunk.split_batch([(Path(path), body, ext)])
    return stored == [piece.content for piece in pieces]


def _recorded(storage: DatabaseStorage) -> list[str]:
    """Every statement *storage* issues from here on, in order."""
    statements: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    return statements


def _write_order(statements: list[str]) -> tuple[list[int], list[int], list[int]]:
    """The positions of the entry flips that set ``chunked``, the chunk-row writes and the edge-row writes."""

    def at(*heads: str) -> list[int]:
        return [i for i, statement in enumerate(statements) if statement.startswith(heads)]

    flips = [i for i in at("UPDATE vfs_entries SET") if "chunked=" in statements[i]]
    chunk_writes = at("DELETE FROM vfs_chunks", "INSERT INTO vfs_chunks")
    return flips, chunk_writes, at("DELETE FROM vfs_edges", "INSERT INTO vfs_edges")


class _Fenced(NamedTuple):
    """One fenced transaction: the statements its body issued, and the content paths chunked as it ended."""

    statements: list[str]
    chunked: frozenset[str]


def _spy_fenced(storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch) -> list[_Fenced]:
    """Every fenced transaction the backend runs from here on, in order (a redriven body is listed per attempt)."""
    fenced: list[_Fenced] = []
    open_bodies: list[list[str]] = []
    real = maintenance_module.lease_fenced

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if open_bodies:
            open_bodies[-1].append(statement)

    def spy(tables: VFSTables, token: str, fn: Any) -> Any:
        body = real(tables, token, fn)

        async def observed(session: AsyncSession) -> Result:
            statements: list[str] = []
            open_bodies.append(statements)
            try:
                result = await body(session)
            finally:
                open_bodies.pop()
            fenced.append(_Fenced(statements, await _chunked_paths(session, tables)))
            return result

        return observed

    monkeypatch.setattr(maintenance_module, "lease_fenced", spy, raising=False)
    return fenced


def _body(index: int, size: int) -> str:
    """An ASCII text body of exactly *size* bytes, distinct per *index*."""
    return (f"body {index} line " * size)[: size - 1] + "\n"


class TestRebuild:
    async def test_the_full_pass_answers_as_rebuild(self, tmp_path, monkeypatch) -> None:
        """A dirty pass, a clean pass, a pass whose lease a rival took and a refused claim each answer under
        the verb's own op, in their records too, and hand their runners no other op label.

        Mutant: the reclaim's success, the claim's refusal, the lease-lost verdict or a runner's label answers
        under the old op name.
        """
        storage = DatabaseStorage(url=_url(tmp_path), embedder=HashEmbeddingProvider())
        labels: set[str] = set()
        for runner in ("_execute", "_execute_maintenance", "_execute_leased", "_rows"):
            real = getattr(storage, runner)

            async def labelled(op: str, fn: Any, real: Any = real) -> Any:
                labels.add(op)
                return await real(op, fn)

            monkeypatch.setattr(storage, runner, labelled)
        await storage.write(entries=[Entry(path=Path("/a.py"), content="needle one\nneedle two")])
        labels.clear()
        dirty = await storage.rebuild()
        clean = await storage.rebuild()
        written = [Entry(path=Path("/b.txt"), content="bravo body"), Entry(path=Path("/c.pdf"), data=pdf_bytes(["c"]))]
        assert (await storage.write(entries=written)).success is True

        async def rival_claims() -> None:
            index_state = storage._host.tables.index_state
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(index_state).values(lease_heartbeat=0))
            await _claimed(storage, "RIVAL")

        with installed("rebuild:before-render-land", rival_claims):
            lost = await storage.rebuild()
        refused = await storage.rebuild()
        assert (dirty.success, clean.success, lost.success, refused.success) == (True, True, False, False)
        assert maintenance_module.lease_lost(lost), lost.errors
        assert [dirty.ops, clean.ops, lost.ops, refused.ops] == [("rebuild",)] * 4
        assert "the index lease expired mid-run" in lost.errors[0].message
        assert "an index run is already running" in refused.errors[0].message
        assert lost.errors[0].data == {"index_lease": "lost"}
        assert labels == {"rebuild"}
        await storage.close()

    async def test_rebuild_chunks_encodes_and_publishes(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.py"), content="needle one\nneedle two")])
        assert (await storage.rebuild()).success is True
        tables = storage._host.tables
        assert await _flags(storage, "/a.py") == (True, True)
        assert await _epoch(storage) == 1
        async with storage._host.engine.connect() as conn:
            doc_id = (await conn.execute(select(tables.entry.c.id).where(tables.entry.c.path == "/a.py"))).scalar_one()
            chunk = (await conn.execute(select(tables.chunks.c.line_start, tables.chunks.c.line_end))).one()
            posting = (
                await conn.execute(
                    select(tables.posting_list).where(
                        tables.posting_list.c.gram_key == pack_gram(ord("n"), ord("e"), ord("e"))
                    )
                )
            ).one()
            fingerprint = (await conn.execute(select(tables.gram_epochs))).one()
        assert (chunk.line_start, chunk.line_end) == (1, 2)  # semantic chunks still refresh
        assert decode_postings(posting.postings) == [doc_id]
        assert posting.doc_count == 1
        assert posting.byte_size == len(posting.postings)
        assert (fingerprint.epoch, fingerprint.format_version) == (1, indexing.INDEX_FORMAT_VERSION)
        assert fingerprint.options_hash == indexing.index_options_hash()
        await storage.close()

    async def test_rebuild_is_idempotent_cheap_when_nothing_is_dirty(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="stable body")])
        assert (await storage.rebuild()).success is True
        assert (await storage.rebuild()).success is True
        assert await _epoch(storage) == 1
        assert await _count(storage, storage._host.tables.gram_epochs) == 1
        await storage.close()

    async def test_rewrite_dirties_and_the_next_rebuild_advances_the_epoch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="first body")])
        assert (await storage.rebuild()).success is True
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="second body")])
        assert await _flags(storage, "/a.txt") == (False, False)
        assert (await storage.rebuild()).success is True
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
        assert (await storage.rebuild()).success is True
        assert await _epoch(storage) == 1
        assert await _count(storage, storage._host.tables.posting_list) == 0
        assert (await storage.rebuild()).success is True  # and now a no-op
        assert await _epoch(storage) == 1
        await storage.close()

    async def test_trashed_entries_are_left_out(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/gone.txt"), content="trashed body")])
        assert (await storage.delete(path=Path("/gone.txt"))).success is True
        assert (await storage.rebuild()).success is True
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            row = (
                await conn.execute(select(entry.c.chunked, entry.c.encoded).where(entry.c.deleted_at.isnot(None)))
            ).one()
        assert row._tuple() == (False, False)  # scan-side wherever it resurfaces
        await storage.close()

    async def test_rebuild_repairs_directories_written_before_the_rule(self, tmp_path) -> None:
        # A store written before directories were created encoded holds
        # them false; one rebuild repairs them and reports the count once.
        storage = DatabaseStorage(url=_url(tmp_path))
        for name in ("a", "b", "c"):
            assert (await storage.mkdir(path=Path(f"/{name}"))).success is True
        entry = storage._host.tables.entry
        predated = entry.c.path.in_(["/a", "/b", "/c"])
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(update(entry).where(predated).values(encoded=False))
            await session.commit()

        async def repairs(result: Result) -> list[ResultError]:
            return [error for error in result.errors if (error.data or {}).get("directories") is not None]

        first = await storage.rebuild()
        assert first.success is True
        [warning] = await repairs(first)
        assert warning.kind == ErrorKind.internal
        assert warning.severity == Severity.warning
        assert warning.retryable is False
        assert warning.path is None
        assert warning.data == {"directories": 3}
        async with storage._host.engine.connect() as conn:
            flags = (await conn.execute(select(entry.c.encoded).where(predated))).scalars().all()
        assert flags == [True, True, True]
        second = await storage.rebuild()
        assert second.success is True
        assert await repairs(second) == []
        await storage.close()

    async def test_the_flag_repair_skips_a_row_whose_kind_moved_under_it(self, tmp_path, monkeypatch) -> None:
        # The repair's guard: a collected row that is no longer a directory
        # when the writer transaction runs is left as found, not stamped covered.
        storage = DatabaseStorage(url=_url(tmp_path))
        for name in ("a", "b"):
            assert (await storage.mkdir(path=Path(f"/{name}"))).success is True
        entry = storage._host.tables.entry
        predated = entry.c.path.in_(["/a", "/b"])
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(update(entry).where(predated).values(encoded=False))
            await session.commit()
        collect = flags_module.collect_flag_drift

        async def rekinded(session, tables, state) -> Result:
            result = await collect(session, tables, state)
            async with storage._host.session_factory() as rival:
                conn = await rival.connection(execution_options={"vfs_writer": True})
                await conn.execute(update(entry).where(entry.c.path == "/b").values(kind="file"))
                await rival.commit()
            return result

        monkeypatch.setattr(maintenance_module, "collect_flag_drift", rekinded)
        result = await storage.rebuild()
        assert result.success is True
        [warning] = [error for error in result.errors if (error.data or {}).get("directories") is not None]
        assert warning.data == {"directories": 1}
        async with storage._host.engine.connect() as conn:
            rows = await conn.execute(select(entry.c.path, entry.c.encoded).where(predated).order_by(entry.c.path))
            assert [row._tuple() for row in rows] == [("/a", True), ("/b", False)]
        await storage.close()

    async def test_a_lease_lost_after_the_flag_collect_stops_before_the_repair(self, tmp_path, monkeypatch) -> None:
        # The beat proves the lease taken while the collect runs: the run
        # stops at the boundary and the predated rows are left as found.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.mkdir(path=Path("/a"))).success is True
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(update(entry).where(entry.c.path == "/a").values(encoded=False))
            await session.commit()
        lost = asyncio.Event()
        collect = flags_module.collect_flag_drift

        async def poisoned(session, tables, state) -> Result:
            lost.set()
            return await collect(session, tables, state)

        monkeypatch.setattr(maintenance_module, "collect_flag_drift", poisoned)
        result = await maintenance_module._rebuild_phases(
            storage._maintenance(), storage._host.tables, lost, await _claimed(storage)
        )
        assert result.success is False
        assert "expired mid-run" in result.errors[0].message
        async with storage._host.engine.connect() as conn:
            assert (await conn.execute(select(entry.c.encoded).where(entry.c.path == "/a"))).scalar_one() is False
        await storage.close()

    async def test_the_chunk_pass_takes_its_entry_rows_before_any_chunk_or_edge_row(self, tmp_path) -> None:
        """Guards: the chunk pass's flips moved back after its chunk-row and edge-row writes, reversing the
        purge's order, entry row first."""
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {"/b.md": "# Bravo\n\nbravo body\n", "/a.md": "# Alpha\n\nSee [bravo](b.md).\n"}
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
        assert (await storage.rebuild()).success is True
        rewritten = Entry(path=Path("/a.md"), content="# Alpha\n\nStill see [bravo](b.md), rewritten.\n")
        assert (await storage.write(entries=[rewritten])).success is True
        statements = _recorded(storage)
        assert (await storage.rebuild()).success is True
        flips, chunk_writes, edge_writes = _write_order(statements)
        assert flips and chunk_writes and edge_writes, statements
        assert flips[0] < chunk_writes[0] and flips[0] < edge_writes[0], (flips, chunk_writes, edge_writes)
        await storage.close()

    async def test_the_chunk_pass_commits_one_slice_at_a_time(self, tmp_path, monkeypatch) -> None:
        """Guards: the slice's size read losing its limit, so the whole dirty set is one transaction."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 2)
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {f"/f{i}.txt": f"file {i} body\n" for i in range(5)}
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
        fenced = _spy_fenced(storage, monkeypatch)
        assert (await storage.rebuild()).success is True
        assert [len(each.chunked) for each in fenced] == [2, 4, 5]
        for each in fenced:
            flips, chunk_writes, _edge_writes = _write_order(each.statements)
            assert flips and chunk_writes and flips[0] < chunk_writes[0], each.statements
        for path, body in bodies.items():
            assert await _flags(storage, path) == (True, True)
            assert await _split_is_stored(storage, path, body), path
        await storage.close()

    async def test_an_entry_whose_flip_missed_waits_for_the_next_run(self, tmp_path, monkeypatch) -> None:
        """Guards: the pass never moving its cursor past a committed slice, so a later slice re-reads an entry
        its own slice already read and whose flip a write made miss."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {f"/f{i}.txt": f"file {i} body\n" for i in range(2)}
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
        real_flip = indexing._flip_flags
        written: list[str] = []

        async def written_after_the_read(
            session: AsyncSession, entry: Any, *args: Any, assignments: Any, **stamp: Any
        ) -> None:
            # A write after the slice's dirty read bumps the version, as an overwrite does; staged in-session.
            pairs = args[-1]
            if pairs and not written:
                written.append(pairs[0][0])
                bump = update(entry).values(version=entry.c.version + 1)
                await session.execute(bump.where(entry.c.entry_id == pairs[0][0]))
            await real_flip(session, entry, *args, assignments=assignments, **stamp)

        monkeypatch.setattr(indexing, "_flip_flags", written_after_the_read)
        assert (await storage.rebuild()).success is True
        assert [await _flags(storage, path) for path in bodies] == [(False, False), (True, True)]
        assert (await storage.rebuild()).success is True
        assert [await _flags(storage, path) for path in bodies] == [(True, True), (True, True)]
        await storage.close()

    async def test_the_slices_link_counts_fold_into_one_record(self, tmp_path, monkeypatch) -> None:
        """Guards: the pass reporting one slice's link counts, a slice counting only when a reference is
        unresolved, or a record raised when every reference resolved."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {
            "/a.md": "See [b](b.md) and [gone](gone.md).\n",
            "/b.md": "Back to [a](a.md).\n",
            "/c.md": "[b](b.md)\n",
        }
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success

        def link_records(result: Result) -> list[dict[str, Any]]:
            return [error.data for error in result.errors if error.data and error.data.get("leg") == "links"]

        first = await storage.rebuild()
        assert link_records(first) == [{"leg": "links", "sources": 3, "edges": 3, "unresolved": 1}]
        assert (await storage.write(entries=[Entry(path=Path("/gone.md"), content="here now\n")])).success
        assert (await storage.write(entries=[Entry(path=Path("/a.md"), content=bodies["/a.md"] + "\n")])).success
        second = await storage.rebuild()
        assert second.success is True and link_records(second) == []
        await storage.close()

    async def test_a_generation_change_keeps_every_entry_in_the_vector_leg_until_its_slice(
        self, tmp_path, monkeypatch
    ) -> None:
        """Guards: the slice read losing its stale-generation term when the probe finds stale rows."""
        storage = DatabaseStorage(url=_url(tmp_path), embedder=HashEmbeddingProvider(8))
        entries = [Entry(path=Path(f"/v{i}.txt"), content=f"vector body {i}\n") for i in range(6)]
        assert (await storage.write(entries=entries)).success is True
        assert (await storage.rebuild()).success is True
        tables = storage._host.tables
        entry, chunks = tables.entry, tables.chunks
        reachable = (
            select(func.count(func.distinct(chunks.c.entry_id)))
            .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
            .where(chunks.c.embedding.isnot(None), entry.c.chunked, entry.c.deleted_at.is_(None))
        )

        async def vector_leg() -> int:
            async with storage._host.engine.connect() as conn:
                return (await conn.execute(reachable)).scalar_one()

        assert await vector_leg() == 6
        monkeypatch.setattr(indexing, "chunk_generation", lambda: "next-generation")
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 2)
        slices = 0
        counts: list[int] = []

        async def counted_at_the_second_slice() -> None:
            nonlocal slices
            slices += 1
            if slices == 2:
                counts.append(await vector_leg())

        with installed("rebuild:before-chunk-split", counted_at_the_second_slice):
            assert (await storage.rebuild()).success is True
        assert counts == [6]
        assert await vector_leg() == 6
        async with storage._host.engine.connect() as conn:
            generations = set((await conn.execute(select(entry.c.chunk_generation).where(entry.c.chunked))).scalars())
        assert generations == {"next-generation"}
        await storage.close()

    async def test_a_slice_is_cut_at_its_body_budget(self, tmp_path, monkeypatch) -> None:
        """Guards: the byte cut deleted, so a slice keeps every row its size read returned."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_BYTES", 1_000)
        storage = DatabaseStorage(url=_url(tmp_path))
        fenced = _spy_fenced(storage, monkeypatch)
        counts: list[int] = []
        for size, offset in ((300, 0), (2_000, 4), (250, 8)):
            bodies = {f"/f{offset + i}.txt": _body(offset + i, size) for i in range(4)}
            written = await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])
            assert written.success is True
            before = len(fenced)
            assert (await storage.rebuild()).success is True
            counts.append(len(fenced) - before)
            for path, body in bodies.items():
                assert await _flags(storage, path) == (True, True)
                assert await _split_is_stored(storage, path, body), path
        assert counts == [2, 4, 1]  # four 250-byte files fill the budget exactly: one slice
        await storage.close()

    async def test_a_slice_after_a_byte_cut_holds_no_more_than_its_entries(self, tmp_path, monkeypatch) -> None:
        """Guards: the shortfall read sized without the carried candidates, so a slice after a byte cut holds
        more than its entry limit, or the carried candidates kept past the byte cut."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 4)
        monkeypatch.setattr(indexing, "CHUNK_SLICE_BYTES", 1_000)
        storage = DatabaseStorage(url=_url(tmp_path))
        sizes = {f"/f{i:02}.txt": 900 if i < 3 else 10 for i in range(15)}
        for index, (path, size) in enumerate(sizes.items()):
            assert (await storage.write(entries=[Entry(path=Path(path), content=_body(index, size))])).success
        fenced = _spy_fenced(storage, monkeypatch)
        assert (await storage.rebuild()).success is True
        slices: list[list[str]] = []
        done: set[str] = set()
        for each in fenced:
            slices.append(sorted(each.chunked - done))
            done |= each.chunked
        for paths in slices:
            assert len(paths) <= 4 and (len(paths) == 1 or sum(sizes[p] for p in paths) <= 1_000), slices
        # The second slice is carried candidates alone; the third is carried ones topped up to the limit.
        assert [len(paths) for paths in slices] == [1, 1, 4, 4, 4, 1], slices
        assert done == set(sizes)
        await storage.close()

    async def test_a_steady_state_slice_reads_no_generation_term(self, tmp_path) -> None:
        """Guards: the slice read's stale-generation term applied when the probe finds no stale row."""
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/s{i}.txt"), content=f"steady body {i}\n") for i in range(2)]
        assert (await storage.write(entries=entries)).success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/s0.txt"), content="steady body, rewritten\n")])).success
        statements = _recorded(storage)
        assert (await storage.rebuild()).success is True
        wheres = [s.partition("WHERE")[2] for s in statements if s.startswith("SELECT") and "vfs_entries" in s]
        named = [where for where in wheres if "chunk_generation" in where]
        assert len(named) == 1, named  # the probe's, and no slice read's
        await storage.close()

    async def test_each_candidate_is_metered_once_a_pass(self, tmp_path, monkeypatch) -> None:
        """Guards: a slice re-reading the candidates the last slice's byte cut left, so a run of entries each past
        the budget meters every rendering up to once per slice it waits through, not once a pass."""
        storage = DatabaseStorage(url=_url(tmp_path))
        files = 60
        for index in range(files):
            entry = Entry(path=Path(f"/p{index:02}.pdf"), data=pdf_bytes([f"first {index:02}"]))
            assert (await storage.write(entries=[entry])).success
        assert (await storage.rebuild()).success is True
        for index in range(files):
            entry = Entry(path=Path(f"/p{index:02}.pdf"), data=pdf_bytes([f"again {index:02}"]))
            assert (await storage.write(entries=[entry])).success
        measured: list[int] = []

        def counting_length(value: Any) -> int | None:
            measured.append(1)
            return None if value is None else len(value)

        @event.listens_for(storage._host.engine.sync_engine, "connect")
        def register(dbapi_connection: Any, record: Any) -> None:
            dbapi_connection.create_function("length", 1, counting_length)

        # A pass holding a connection through the dispose would check it back in to a pool nothing closes.
        await storage._host.settle_statistics()
        await storage._host.engine.dispose()
        statements = _recorded(storage)
        monkeypatch.setattr(indexing, "CHUNK_SLICE_BYTES", 1)
        assert (await storage.rebuild()).success is True
        size_reads = [s for s in statements if s.startswith("SELECT") and "CASE WHEN" in s and "meter" in s]
        assert len(size_reads) == files  # a slice of one each
        assert len(measured) == files  # each rendering measured once, where re-reading measured 1,830
        for index in range(files):
            assert await _flags(storage, f"/p{index:02}.pdf") == (True, True)
        await storage.close()

    async def test_a_carried_candidate_written_between_slices_is_split_from_its_current_body(
        self, tmp_path, monkeypatch
    ) -> None:
        """Guards: a slice trusting what a candidate was when an earlier slice measured it, so a candidate
        rewritten or trashed while it waited is split from a body it no longer has, or split at all."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_BYTES", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {f"/f{i}.txt": f"file {i} body\n" for i in range(4)}
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
        real = storage._execute_leased
        rewritten = "file 2 body, rewritten while it waited its turn\n"
        written: list[bool] = []

        async def writes_between_slices(op: str, fn: Any) -> Result:
            result = await real(op, fn)
            if not written:
                written.append((await storage.write(entries=[Entry(path=Path("/f2.txt"), content=rewritten)])).success)
                written.append((await storage.delete(path=Path("/f3.txt"))).success)
            return result

        monkeypatch.setattr(storage, "_execute_leased", writes_between_slices)
        assert (await storage.rebuild()).success is True
        assert written == [True, True]
        assert await _flags(storage, "/f2.txt") == (True, True)
        assert await _split_is_stored(storage, "/f2.txt", rewritten)
        assert await _chunk_ids(storage, "/f3.txt") == set()
        assert await _flags(storage, "/f3.txt") == (False, False)
        await storage.close()

    async def test_a_trashed_dirty_entry_is_never_split(self, tmp_path) -> None:
        """Guards: the slice reads losing their own ``deleted_at IS NULL``, so an entry trashed while dirty is
        split again on every run, its flip missing each time on the flips' own liveness term."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/t.md"), content="# Trashed\n\nbody\n")])).success
        assert (await storage.delete(path=Path("/t.md"))).success
        splits: list[int] = []

        async def split() -> None:
            splits.append(len(splits))

        with installed("rebuild:before-chunk-split", split):
            for _ in range(2):
                assert (await storage.rebuild()).success is True
        assert splits == []
        assert await _count(storage, storage._host.tables.chunks) == 0
        await storage.close()

    async def test_a_pass_with_nothing_dirty_ends_at_its_empty_slice(self, tmp_path) -> None:
        """Guards: an empty slice going on to read bodies by an empty id list and to hop to the offload pool."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="settled body\n")])).success
        assert (await storage.rebuild()).success is True
        splits: list[int] = []

        async def split() -> None:
            splits.append(len(splits))

        with installed("rebuild:before-chunk-split", split):
            assert (await storage.rebuild()).success is True
        assert splits == []
        await storage.close()

    async def test_a_rendered_binary_is_metered_by_its_rendering(self, tmp_path, monkeypatch) -> None:
        """Guards: the slice meter reduced to ``size_bytes`` for every row, so a rendered binary is metered by
        its bytes and not by the text its rendering stored."""
        storage = DatabaseStorage(url=_url(tmp_path))
        tables = storage._host.tables
        entry = tables.entry
        pdfs = {"/p0.pdf": ("kiwi", "kowi"), "/p1.pdf": ("emu", "ume"), "/p2.pdf": ("moa", "mao")}
        for path, (first, _second) in pdfs.items():
            assert (await storage.write(entries=[Entry(path=Path(path), data=pdf_bytes([first]))])).success
        assert (await storage.rebuild()).success is True
        stored = select(func.sum(func.length(tables.content.c.content))).select_from(tables.content_joined())
        async with storage._host.engine.connect() as conn:
            renderings = (await conn.execute(stored.where(entry.c.path.in_(pdfs)))).scalar_one()
        for path, (_first, second) in pdfs.items():
            assert (await storage.write(entries=[Entry(path=Path(path), data=pdf_bytes([second]))])).success
        smallest = select(func.min(entry.c.size_bytes)).where(entry.c.path.in_(pdfs))
        async with storage._host.engine.connect() as conn:
            least = (await conn.execute(smallest)).scalar_one()
        assert 0 < renderings < least - 1, (renderings, least)
        monkeypatch.setattr(indexing, "CHUNK_SLICE_BYTES", least - 1)
        fenced = _spy_fenced(storage, monkeypatch)
        assert (await storage.rebuild()).success is True
        assert len(fenced) == 2  # the renderings' one landing, then one chunk-pass slice
        assert {path for path in pdfs if await _flags(storage, path) == (True, True)} == set(pdfs)
        await storage.close()


class TestEligibilityGates:
    async def test_oversized_content_stays_scan_side_without_retriggering_builds(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "MAX_INDEXABLE_BYTES", 8)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/big.txt"), content="well past eight bytes")])
        assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/big.txt") == (True, False)
        assert await _indexable_flag(storage, "/big.txt") is False
        assert await _count(storage, storage._host.tables.chunks) == 0
        epoch = await _epoch(storage)
        assert (await storage.rebuild()).success is True  # ineligible ≠ pending
        assert await _epoch(storage) == epoch
        await storage.close()

    async def test_gram_saturated_content_stays_scan_side(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "MAX_DISTINCT_GRAMS", 2)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/wide.txt"), content="abcdefgh")])
        assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/wide.txt") == (True, False)
        assert await _indexable_flag(storage, "/wide.txt") is False
        await storage.close()

    async def test_sub_trigram_content_stays_scan_side_and_findable(self, tmp_path) -> None:
        # A body too short to form a trigram posts nothing; it must stay
        # scan-side, where a gramless pattern's opt-out scan can serve it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/tiny.txt"), content="ab")])
        assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/tiny.txt") == (True, False)
        assert await _indexable_flag(storage, "/tiny.txt") is False
        epoch = await _epoch(storage)
        assert (await storage.rebuild()).success is True  # ineligible ≠ pending
        assert await _epoch(storage) == epoch
        found = await storage.grep(pattern="ab", allow_scan=True)
        assert [str(o.path) for o in found.observations] == ["/tiny.txt"]
        await storage.close()

    async def test_eligible_content_is_stamped_indexable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/ok.txt"), content="plenty of body")])
        assert (await storage.rebuild()).success is True
        assert await _indexable_flag(storage, "/ok.txt") is True
        await storage.close()

    async def test_options_drift_forces_a_rebuild_with_no_dirty_rows(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="steady body")])
        assert (await storage.rebuild()).success is True
        assert await _epoch(storage) == 1
        monkeypatch.setattr(indexing, "MAX_DISTINCT_GRAMS", 19_000)  # options hash moves
        assert (await storage.rebuild()).success is True
        assert await _epoch(storage) == 2
        await storage.close()

    async def test_a_missing_fingerprint_row_forces_a_rebuild(self, tmp_path) -> None:
        # A pointer with no fingerprint row is unverifiable — rebuild.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="steady body")])
        assert (await storage.rebuild()).success is True
        tables = storage._host.tables
        async with storage._host.engine.begin() as conn:
            await conn.execute(tables.gram_epochs.delete())
        assert (await storage.rebuild()).success is True
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
    async def test_pending_probe_is_row_presence_not_bare_exists(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        tables = storage._host.tables
        sql = str(indexing._pending_probe(tables.entry).compile(dialect=postgresql.dialect())).upper()
        assert not sql.startswith("SELECT EXISTS")
        assert "WHERE" in sql and "INDEXABLE" in sql
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
        result = await storage.rebuild()
        assert result.success is False
        error = result.errors[0]
        assert error.kind == ErrorKind.conflict
        assert error.retryable is True
        assert "unique" not in error.message.lower() and "constraint" not in error.message.lower()
        await storage.close()

    async def test_a_crashed_build_never_poisons_the_number_line(self, tmp_path) -> None:
        # A built-but-unpublished epoch is skipped by the next mint and
        # reclaimed once the pointer moves past it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        await _seed_built_epoch(storage, 7, with_fingerprint=True)
        assert (await storage.rebuild()).success is True
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
        index_state = storage._host.tables.index_state

        async def rival() -> None:
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(index_state).values(current_gram_epoch=99))

        with installed("rebuild:before-publish", rival):
            result = await storage.rebuild()
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.conflict
        assert await _epoch(storage) == 99  # the rival's publish stood
        await storage.close()


class TestFlagAlgebra:
    async def test_delete_demotes_encoded_at_the_claim(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/a.txt") == (True, True)
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        assert await _flags(storage, "/a.txt") == (True, False)
        await storage.close()

    async def test_delete_rebuild_restore_stays_greppable_on_both_tiers(self, tmp_path) -> None:
        # The forbidden state: a live row invisible to both tiers after
        # delete → rebuild → restore. Demote-at-delete closes it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        assert (await storage.rebuild()).success is True
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="other stuff")])
        assert (await storage.rebuild()).success is True  # a rebuild without the deleted row
        assert (await storage.restore(path=Path("/a.txt"))).success is True
        assert await _flags(storage, "/a.txt") == (True, False)  # pending — the scan side serves
        found = await storage.grep(pattern="needle")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        assert (await storage.rebuild()).success is True  # and the next build re-covers
        assert await _flags(storage, "/a.txt") == (True, True)
        found = await storage.grep(pattern="needle")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        await storage.close()

    async def test_trash_scoped_grep_serves_the_trashed_root_scan_side(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        assert (await storage.rebuild()).success is True
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.grep(pattern="needle")).observations == []  # default scope hides the deleted
        found = await storage.grep(pattern="needle", globs=("/.vfs/trash/a.txt",))
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        await storage.close()

    async def test_copy_onto_an_occupant_leaves_its_coverage_intact(self, tmp_path) -> None:
        # No copy replaces a body: the occupant keeps its flags and grams,
        # and the refused copy changes nothing either tier serves.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/src.txt"), content="alpha needle")])
        await storage.write(entries=[Entry(path=Path("/dst.txt"), content="bravo body")])
        assert (await storage.rebuild()).success is True
        pair = ResolvedPair(Path("/src.txt"), Path("/dst.txt"))
        refused = await storage.copy(operations=[pair])
        assert [e.kind for e in refused.errors] == [ErrorKind.exists]
        assert await _flags(storage, "/dst.txt") == (True, True)
        found = await storage.grep(pattern="alpha")
        assert sorted(str(o.path) for o in found.observations) == ["/src.txt"]
        found = await storage.grep(pattern="bravo")
        assert sorted(str(o.path) for o in found.observations) == ["/dst.txt"]
        await storage.close()

    async def test_a_write_racing_the_publish_window_stays_scan_side(self, tmp_path) -> None:
        # The publish flip's version guard: the raced entry keeps fresh
        # flags and the fresh body is served, never stamped over dead grams.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="stale needle")])

        async def rival() -> None:
            fresh = Entry(path=Path("/a.txt"), content="fresh needle")
            assert (await storage.write(entries=[fresh])).success is True

        with installed("rebuild:before-publish", rival):
            assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/a.txt") == (False, False)
        found = await storage.grep(pattern="fresh")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/a.txt") == (True, True)
        found = await storage.grep(pattern="fresh")
        assert [str(o.path) for o in found.observations] == ["/a.txt"]
        await storage.close()

    async def test_a_directory_delete_at_the_publish_seam_leaves_its_descendant_pending(self, tmp_path) -> None:
        """Guards: the flip's liveness term dropped, so a descendant a delete tombstoned with no version bump
        is marked encoded."""
        storage = DatabaseStorage(url=_url(tmp_path))
        body = Entry(path=Path("/d/x.txt"), content="xylophone body")
        assert (await storage.write(entries=[body], parents=True)).success is True
        deleted: list[bool] = []

        async def rival() -> None:
            deleted.append((await storage.delete(path=Path("/d"))).success)

        with installed("rebuild:before-publish", rival):
            assert (await storage.rebuild()).success is True
        assert deleted == [True]
        assert await _flags(storage, "/d/x.txt") == (True, False)
        assert (await storage.write(entries=[Entry(path=Path("/g.txt"), content="golf body")])).success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.restore(path=Path("/d"))).success is True
        assert [str(o.path) for o in (await storage.search(query="xylophone")).observations] == ["/d/x.txt"]
        assert [str(o.path) for o in (await storage.grep(pattern="xylophone")).observations] == ["/d/x.txt"]
        assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/d/x.txt") == (True, True)
        await storage.close()


class TestBuildAgreement:
    """The lexical feed takes exactly the entries the posting scan covered, whatever commits between the reads."""

    async def test_a_write_between_the_two_reads_never_splits_an_entry(self, tmp_path, monkeypatch) -> None:
        """Guards: the lexical feed choosing its own rows, by dropping the covered filter or by re-testing
        the entry flags the posting scan already read."""
        storage = DatabaseStorage(url=_url(tmp_path))
        files = {"/d/x.txt": "xylophone body", "/b.txt": "bravo body", "/e.txt": "echo body"}
        written = await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in files.items()], parents=True)
        assert written.success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.delete(path=Path("/b.txt"))).success is True
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="foxtrot body")])).success is True
        entry = storage._host.tables.entry
        real_lexical, real_publish = indexing.build_lexical_epoch, maintenance_module.publish_epoch
        received: dict[str, int] = {}

        async def rivals_first(session: AsyncSession, *args: Any, **kwargs: Any) -> None:
            # A delete of /d stamps its descendant with no bump; a restore of /b.txt clears it with one.
            now = datetime.now(UTC)
            root = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            tombstone = {"deleted_at": now, "trash_root_id": root}
            bumped = {**tombstone, "version": entry.c.version + 1}
            await session.execute(update(entry).where(entry.c.path == "/d").values(**bumped))
            await session.execute(update(entry).where(entry.c.path == "/d/x.txt").values(**tombstone, encoded=False))
            revived = {"deleted_at": None, "trash_root_id": None, "version": entry.c.version + 1}
            await session.execute(update(entry).where(entry.c.path == "/b.txt").values(**revived))
            await real_lexical(session, *args, **kwargs)

        async def capturing(session: AsyncSession, *args: Any) -> Result:
            state = args[-1]
            received.update(state.covered)
            return await real_publish(session, *args)

        monkeypatch.setattr(indexing, "build_lexical_epoch", rivals_first)
        monkeypatch.setattr(maintenance_module, "publish_epoch", capturing)
        assert (await storage.rebuild()).success is True
        lexical = await _lexical_entries(storage)
        for path in (*files, "/f.txt"):
            entry_id = await _entry_id(storage, path)
            assert (entry_id in received) == (entry_id in lexical), path
        assert await _encoded_content(storage) <= set(received) & lexical
        assert await _flags(storage, "/d/x.txt") == (True, False)
        assert (await storage.restore(path=Path("/d"))).success is True
        assert [str(o.path) for o in (await storage.search(query="xylophone")).observations] == ["/d/x.txt"]
        assert [str(o.path) for o in (await storage.grep(pattern="xylophone")).observations] == ["/d/x.txt"]
        await storage.close()


class TestReclaim:
    async def test_a_cas_loser_reclaims_its_own_built_epoch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="raced body")])
        index_state = storage._host.tables.index_state

        async def rival() -> None:
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(index_state).values(current_gram_epoch=99))

        with installed("rebuild:before-publish", rival):
            result = await storage.rebuild()
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.conflict
        tables = storage._host.tables
        assert await _count(storage, tables.posting_list) == 0  # the lost build left no residue
        assert await _count(storage, tables.gram_epochs) == 0
        await storage.close()

    async def test_reclaim_never_destroys_a_rivals_newer_published_epoch(self, tmp_path) -> None:
        # A rival publishing between this publish and its reclaim must
        # keep its epoch: reclaim reads the live pointer, never a stale one.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abc")])
        index_state = storage._host.tables.index_state

        async def rival() -> None:
            await _seed_built_epoch(storage, 2, with_fingerprint=True)
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(index_state).values(current_gram_epoch=2))

        with installed("rebuild:before-reclaim", rival):
            result = await storage.rebuild()
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
        assert (await storage.rebuild()).success is True
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


class _MatchingSession(_RecordingSession):
    """A recording session whose every statement reports one row matched, as a landed compare-and-set does."""

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        self.calls.append((stmt, params))
        return SimpleNamespace(rowcount=1)


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
        entry = build_vfs_tables().entry
        pairs = [("01A", 1), ("01B", 2)]
        await indexing._flip_flags(
            cast("AsyncSession", session), entry, POSTGRESQL, 2_000, 1_000, pairs, assignments={"encoded": True}
        )
        ((stmt, params),) = session.calls
        assert params is None  # set-based, not executemany
        sql = str(stmt.compile(dialect=dialect))
        assert "FROM (VALUES" in sql and "encoded" in sql

    async def test_the_generic_floor_falls_back_to_executemany(self) -> None:
        session = _RecordingSession(postgresql.dialect())
        entry = build_vfs_tables().entry
        await indexing._flip_flags(
            cast("AsyncSession", session), entry, GENERIC, 2_000, 1_000, [("01A", 1)], assignments={"chunked": True}
        )
        ((_stmt, params),) = session.calls
        assert params == [{"b_id": "01A", "b_ver": 1}]

    async def test_no_pairs_is_a_no_op(self) -> None:
        session = _RecordingSession(postgresql.dialect())
        entry = build_vfs_tables().entry
        await indexing._flip_flags(
            cast("AsyncSession", session), entry, POSTGRESQL, 2_000, 1_000, [], assignments={"encoded": True}
        )
        assert session.calls == []

    async def test_every_flip_spelling_lands_only_on_a_live_row(self) -> None:
        """Guards: ``deleted_at IS NULL`` dropped from any one spelling's guard — the VALUES join, the
        row-constructor ``IN``'s CASE or the executemany floor — so a tombstoned row is flipped."""
        entry = build_vfs_tables().entry
        pairs = [("01A", 1), ("01B", 2)]
        # Per spelling: where the liveness term sits, (binds in the compiled statement, executemany rows).
        spellings = (
            (POSTGRESQL, _values_join_dialect(), "where", [(5, None)]),
            (SQLITE, sqlite.dialect(), "case", [(3, None)]),  # the ids that key the unique index beside the pairs
            (GENERIC, postgresql.dialect(), "where", [(3, 2)]),
        )
        for profile, dialect, place, shape in spellings:
            session = _RecordingSession(dialect)
            await indexing._flip_flags(
                cast("AsyncSession", session), entry, profile, 2_000, 1_000, pairs, assignments={"encoded": True}
            )
            seen = []
            for stmt, params in session.calls:
                compiled = stmt.compile(dialect=dialect)
                assignment, _where, where = str(compiled).partition(" WHERE ")
                guarded = "CASE WHEN (vfs_entries.deleted_at IS NULL) THEN" in assignment
                assert guarded if place == "case" else "vfs_entries.deleted_at IS NULL" in where, str(compiled)
                seen.append((len(compiled.params), None if params is None else len(params)))
            assert seen == shape, profile.name


def _derived_table(sql: str) -> tuple[str, str]:
    """The first parenthesised ``select`` in lower-cased *sql* and everything outside it."""
    start = sql.index("(select")
    depth = 0
    for at in range(start, len(sql)):
        depth += {"(": 1, ")": -1}.get(sql[at], 0)
        if depth == 0:
            return sql[start : at + 1], sql[:start] + sql[at + 1 :]
    raise AssertionError(sql)


class TestSliceSizeRead:
    def test_the_candidates_are_chosen_before_any_body_is_measured(self) -> None:
        """Guards: the size read measuring before it limits, so a planner without statistics joins and sizes every
        candidate; sizing with a function that reads the body where the profile names one that does not; or the
        outer order dropped, so a hash join hands the byte cut its rows in the content table's order."""
        tables = build_vfs_tables()
        terms = [tables.entry.c.deleted_at.is_(None), ~tables.entry.c.chunked]
        engines = (
            (SQLITE, sqlite.dialect(), "limit", "length("),
            (POSTGRESQL, postgresql.dialect(), "limit", "octet_length("),
            (GENERIC, postgresql.dialect(), "limit", "length("),
        )
        for profile, dialect, limit, function in engines:
            read = indexing._size_read(tables, profile, terms, past=1_000, wanted=17)
            sql = str(read.compile(dialect=dialect, compile_kwargs={"literal_binds": True})).lower()
            inner, outer = _derived_table(" ".join(sql.split()))
            assert limit in inner and "17" in inner and limit not in outer, (profile.name, sql)
            assert "length(" not in inner and "vfs_content" not in inner, (profile.name, sql)
            assert outer.count("length(") == 1 and function in outer, (profile.name, sql)
            # The byte cut keeps the leading rows and seeks past the last: the order is the outer statement's own.
            assert outer.rstrip().endswith("order by candidates.id"), (profile.name, sql)


class TestPostingBatches:
    async def test_posting_inserts_split_by_byte_cap(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "_POSTING_BATCH_BYTES", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abcd")])
        assert (await storage.rebuild()).success is True  # every row its own statement
        assert await _count(storage, storage._host.tables.posting_list) > 1
        await storage.close()

    async def test_extraction_feeds_flush_mid_stream_at_the_byte_budget(self, tmp_path, monkeypatch) -> None:
        # Several engine feeds, one build: the corpus outgrows a shrunken
        # extract budget, and the flushed batches still index completely.
        monkeypatch.setattr(indexing, "_EXTRACT_BATCH_BYTES", 8)
        feeds = 0
        real_feed = indexing._feed_docs

        def counting(builder: Any, batch: Any) -> None:
            nonlocal feeds
            feeds += 1
            real_feed(builder, batch)

        monkeypatch.setattr(indexing, "_feed_docs", counting)
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i}.txt"), content=f"needle {i} padding") for i in range(5)]
        assert (await storage.write(entries=entries)).success is True
        assert (await storage.rebuild()).success is True
        # The existence referee: each over-budget body fed alone — a
        # whole-corpus reversion collapses this to one feed.
        assert feeds == 5
        result = await storage.grep(pattern="needle")
        assert result.success is True
        assert sum(len(o.matches or ()) for o in result.observations) == 5
        await storage.close()

    async def test_posting_drain_actually_slices_by_the_byte_cap(self, tmp_path, monkeypatch) -> None:
        # The existence referee: a voided or bypassed drain budget would
        # collapse the posting inserts into one statement.
        monkeypatch.setattr(indexing, "_POSTING_BATCH_BYTES", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="abcd")])
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        assert (await storage.rebuild()).success is True
        inserts = [s for s in statements if s.startswith("INSERT") and "grams_posting_list" in s]
        assert len(inserts) > 1
        await storage.close()

    async def test_posting_insert_rides_uncapped_past_the_parameter_budget(self, tmp_path, monkeypatch) -> None:
        # The lean-on behind the deleted row cap: a posting batch whose
        # summed binds dwarf the parameter budget still lands whole, as
        # one executemany whose statement carries a single row's binds —
        # SQLAlchemy owns row chunking, and no statement text grows.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 42))
        storage = DatabaseStorage(url=_url(tmp_path))
        content = " ".join(f"tok{i:02}" for i in range(40))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content=content)])).success is True
        statements: list[tuple[str, bool]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append((statement, executemany))

        assert (await storage.rebuild()).success is True
        inserts = [(s, many) for s, many in statements if s.startswith("INSERT") and "grams_posting_list" in s]
        assert len(inserts) == 1, inserts  # no vfs-side row cap splits the batch
        statement, many = inserts[0]
        assert many is True and statement.count("?") == 6  # one row's binds per parameter set
        grams = await _count(storage, storage._host.tables.posting_list)
        assert grams * 6 > 42  # the batch genuinely outgrew the budget
        await storage.close()

    async def test_no_rebuild_statement_grows_with_entry_count(self, tmp_path, monkeypatch) -> None:
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

        assert (await storage.rebuild()).success is True
        deletes = [s for s in statements if s.startswith("DELETE") and "chunks" in s]
        assert len(deletes) == 3  # ten entries at a budget of four: 4 + 4 + 2
        assert all(s.count("?") <= 4 for s in deletes)
        assert all(s.count("?") <= storage._host.parameter_budget for s in statements)
        await storage.close()

    async def test_flag_flips_are_set_based_not_per_row(self, tmp_path) -> None:
        # One statement flips many (entry, version) pairs: executemany
        # degrades to a round trip per row on some drivers.
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i:02}.txt"), content=f"needle body {i:02}") for i in range(10)]
        assert (await storage.write(entries=entries)).success is True
        statements: list[tuple[str, bool]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append((statement, executemany))

        assert (await storage.rebuild()).success is True
        updates = [(s, many) for s, many in statements if s.startswith("UPDATE") and ("chunked" in s or "encoded" in s)]
        assert all(many is False for _, many in updates)
        flips = [(s, many) for s, many in updates if "version" in s]
        assert len(flips) == 2  # ten pairs fit one statement per flag
        assert len(updates) == len(flips)  # no stale generations: the probe skips the re-dirty
        await storage.close()

    async def test_steady_state_rebuild_issues_no_entry_update(self, tmp_path) -> None:
        # The probe-guarded re-dirty: a settled store's rebuild must not
        # UPDATE the entry table at all (scan-locking engines lock the scan).
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i:02}.txt"), content=f"needle body {i:02}") for i in range(10)]
        assert (await storage.write(entries=entries)).success is True
        assert (await storage.rebuild()).success is True
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        assert (await storage.rebuild()).success is True
        assert not [s for s in statements if s.startswith("UPDATE") and "chunked" in s]
        await storage.close()


class TestChunkProvenance:
    """The chunk pass's generation and fingerprint-skip laws."""

    BODY = "def f():\n    return 1\n\n\n" + "".join(f"x{i} = {i}\n" for i in range(40))

    # Four one-chunk files, so a published epoch names four chunk ids.
    FOUR: ClassVar[dict[str, str]] = {
        "/docs/tokens.md": "Tokens are produced by the lexer and consumed by the parser.\n",
        "/notes.txt": "A stream of tokens, tokens, tokens.\n",
        "/src/lexer.py": "def lex(stream):\n    tokens = split(stream)\n    return tokens\n",
        "/src/parser.py": "def parse_tokens(stream):\n    return tokens_from(stream)\n",
    }

    def _record_into(self, storage: DatabaseStorage, statements: list[str]) -> None:
        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

    @staticmethod
    def _chunk_writes(statements: list[str]) -> list[str]:
        return [s for s in statements if s.startswith(("DELETE", "INSERT")) and "vfs_chunks" in s]

    async def _entry_row(self, storage: DatabaseStorage, path: str) -> Any:
        entry = storage._host.tables.entry
        async with storage._host.engine.begin() as conn:
            return (await conn.execute(select(entry).where(entry.c.path == path))).one()

    async def test_provenance_is_stamped_with_the_flip(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=self.BODY)])).success is True
        # A sub-trigram body: chunk-ineligible, but provenance still stamps.
        assert (await storage.write(entries=[Entry(path=Path("/tiny.py"), content="hi")])).success is True
        assert (await storage.rebuild()).success is True
        for path, indexable in (("/a.py", True), ("/tiny.py", False)):
            row = await self._entry_row(storage, path)
            assert row.chunked is True
            assert row.indexable is indexable
            assert row.chunk_source_hash == row.content_hash
            assert row.chunk_generation == chunk_generation()
        await storage.close()

    async def test_a_body_written_away_and_back_skips_the_resplit(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=self.BODY)])).success is True
        assert (await storage.rebuild()).success is True
        statements: list[str] = []
        self._record_into(storage, statements)
        # Two writes dirty the entry (each resets the flags) and leave the
        # hash where the chunks were built: the pass must not touch chunks.
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content="other = 1\n")])).success is True
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=self.BODY)])).success is True
        row = await self._entry_row(storage, "/a.py")
        assert row.chunked is False
        assert (await storage.rebuild()).success is True
        assert self._chunk_writes(statements) == []
        row = await self._entry_row(storage, "/a.py")
        assert row.chunked is True
        await storage.close()

    async def test_changed_body_still_resplits(self, tmp_path) -> None:
        """Guards the skip condition losing its body-hash equality (skip-everything)."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=self.BODY)])).success is True
        assert (await storage.rebuild()).success is True
        statements: list[str] = []
        self._record_into(storage, statements)
        changed = self.BODY + "tail_marker = True\n"
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=changed)])).success is True
        assert (await storage.rebuild()).success is True
        writes = self._chunk_writes(statements)
        assert any(s.startswith("DELETE") for s in writes)
        assert any(s.startswith("INSERT") for s in writes)
        chunks = storage._host.tables.chunks
        async with storage._host.engine.begin() as conn:
            bodies = (await conn.execute(select(chunks.c.content))).scalars().all()
        assert any("tail_marker" in body for body in bodies)
        await storage.close()

    async def test_a_malformed_notebook_never_wedges_the_rebuild(self, tmp_path) -> None:
        # A user-writable file must not jam the maintenance verb: junk
        # kernel metadata degrades to the default grammar and chunks.
        storage = DatabaseStorage(url=_url(tmp_path))
        body = json.dumps(
            {
                "cells": [{"cell_type": "code", "source": "needle_value = 1\n" * 40}],
                "metadata": {"kernelspec": {"language": 42}},
            },
        )
        assert (await storage.write(entries=[Entry(path=Path("/bad.ipynb"), content=body)])).success is True
        assert (await storage.rebuild()).success is True
        row = await self._entry_row(storage, "/bad.ipynb")
        assert row.chunked is True
        chunks = storage._host.tables.chunks
        async with storage._host.engine.begin() as conn:
            bodies = (await conn.execute(select(chunks.c.content))).scalars().all()
        assert bodies
        assert all("needle_value" in body for body in bodies)
        await storage.close()

    async def test_a_deep_nested_notebook_never_wedges_the_rebuild(self, tmp_path) -> None:
        # Nesting past the JSON parser's recursion budget must degrade to
        # the fallback split, never wedge the maintenance verb.
        storage = DatabaseStorage(url=_url(tmp_path))
        body = "[" * 10_000 + "]" * 10_000
        assert (await storage.write(entries=[Entry(path=Path("/deep.ipynb"), content=body)])).success is True
        assert (await storage.rebuild()).success is True
        row = await self._entry_row(storage, "/deep.ipynb")
        assert row.chunked is True
        chunks = storage._host.tables.chunks
        async with storage._host.engine.begin() as conn:
            query = select(chunks.c.content).order_by(chunks.c.chunk_index)
            bodies = (await conn.execute(query)).scalars().all()
        assert bodies and "".join(bodies) == body
        await storage.close()

    async def test_a_surrogate_escape_notebook_never_wedges_the_rebuild(self, tmp_path) -> None:
        # Pure-ASCII JSON passes the write gate; json.loads manufactures
        # the lone surrogate, which must degrade in chunks, never raise.
        storage = DatabaseStorage(url=_url(tmp_path))
        body = json.dumps({"cells": [{"cell_type": "code", "source": "needle_value = 1  # \ud800\n" * 40}]})
        assert body.isascii()
        assert (await storage.write(entries=[Entry(path=Path("/escape.ipynb"), content=body)])).success is True
        assert (await storage.rebuild()).success is True
        row = await self._entry_row(storage, "/escape.ipynb")
        assert row.chunked is True
        chunks = storage._host.tables.chunks
        async with storage._host.engine.begin() as conn:
            bodies = (await conn.execute(select(chunks.c.content))).scalars().all()
        assert bodies
        assert all("needle_value" in body and "\ud800" not in body for body in bodies)
        assert any("�" in body for body in bodies)
        # The scrub is chunk-side only: the stored body reads back verbatim.
        assert (await storage.read(path=Path("/escape.ipynb"))).observations[0].content == body
        await storage.close()

    async def test_generation_change_redirties_and_resplits(self, tmp_path) -> None:
        """Guards the skip condition losing its generation term, and the re-dirty statement vanishing."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=self.BODY)])).success is True
        assert (await storage.rebuild()).success is True
        entry = storage._host.tables.entry
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(entry).values(chunk_generation="stale:0"))
        statements: list[str] = []
        self._record_into(storage, statements)
        assert (await storage.rebuild()).success is True
        writes = self._chunk_writes(statements)
        assert any(s.startswith("DELETE") for s in writes)  # stale generation re-split, not skipped
        row = await self._entry_row(storage, "/a.py")
        assert row.chunked is True
        assert row.chunk_generation == chunk_generation()
        await storage.close()

    async def _four_indexed(self, tmp_path) -> DatabaseStorage:
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(path), content=body) for path, body in self.FOUR.items()]
        assert (await storage.write(entries=entries, parents=True)).success is True
        assert (await storage.rebuild()).success is True
        return storage

    async def _pointer(self, storage: DatabaseStorage) -> int | None:
        async with storage._host.session_factory() as session:
            return await indexing.current_epoch(session, storage._host.tables)

    async def _chunk_ids(self, storage: DatabaseStorage) -> tuple[set[int], set[int]]:
        """The chunk ids the published epoch's lexical documents name, and the ids the chunk table holds."""
        docs, chunks = storage._host.tables.lex_docs, storage._host.tables.chunks
        published = await self._pointer(storage)
        async with storage._host.engine.connect() as conn:
            named = (await conn.execute(select(docs.c.chunk_id).where(docs.c.epoch == published))).scalars().all()
            held = (await conn.execute(select(chunks.c.id))).scalars().all()
        return set(named), set(held)

    async def test_a_chunk_generation_bump_republishes_in_the_same_run(self, tmp_path, monkeypatch) -> None:
        """Guards the chunk generation dropped from the options hash: a bump re-splits every entry
        and publishes nothing, so the published epoch keeps naming chunk ids no row holds."""
        storage = await self._four_indexed(tmp_path)
        named, held = await self._chunk_ids(storage)
        assert await self._pointer(storage) == 1 and len(named) == 4 and named == held
        settled = indexing.index_options_hash()
        real = indexing.chunk_generation
        monkeypatch.setattr(indexing, "chunk_generation", lambda: real() + "-bumped")
        assert indexing.index_options_hash() != settled
        assert (await storage.rebuild()).success is True
        assert await self._pointer(storage) == 2
        renamed, resplit = await self._chunk_ids(storage)
        assert not resplit & held  # the bump re-split every entry into fresh ids
        assert len(renamed) == 4 and renamed - resplit == set()  # and the new epoch strands none of them
        await storage.close()

    async def test_a_chunk_generation_bump_leaves_encoded_alone(self, tmp_path, monkeypatch) -> None:
        """Guards the generation re-dirty demoting ``encoded``: a re-split changes no gram, and a demoted
        row leaves grep's index side and search's lexical leg for the whole build."""
        storage = await self._four_indexed(tmp_path)
        real = indexing.chunk_generation
        monkeypatch.setattr(indexing, "chunk_generation", lambda: real() + "-bumped")
        entry = storage._host.tables.entry
        flags = select(entry.c.path, entry.c.chunk_generation, entry.c.chunked, entry.c.encoded)
        seen: list[tuple[str, str, bool, bool]] = []

        async def observe() -> None:
            async with storage._host.engine.connect() as conn:
                rows = await conn.execute(flags.where(entry.c.path.in_(list(self.FOUR))).order_by(entry.c.path))
                seen.extend(row._tuple() for row in rows)

        with installed("rebuild:before-publish", observe):
            assert (await storage.rebuild()).success is True
        # Read once, after the chunk pass re-split all four and before the publish.
        assert seen == [(path, real() + "-bumped", True, True) for path in sorted(self.FOUR)]
        await storage.close()


class TestIndexLease:
    async def _stamped(self, storage: DatabaseStorage, holder: str | None, heartbeat: int | None) -> None:
        index_state = storage._host.tables.index_state
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(index_state).values(lease_holder=holder, lease_heartbeat=heartbeat))

    async def _lease(self, storage: DatabaseStorage) -> tuple[str | None, int | None]:
        index_state = storage._host.tables.index_state
        async with storage._host.engine.connect() as conn:
            row = (await conn.execute(select(index_state.c.lease_holder, index_state.c.lease_heartbeat))).one()
        return row._tuple()

    async def _made_stale(self, storage: DatabaseStorage) -> None:
        """Backdate the running lease past its TTL, as a run stalled past it leaves the row; the holder stays."""
        index_state = storage._host.tables.index_state
        stale = maintenance_module._now_ms() - maintenance_module.INDEX_LEASE_TTL_MS - 1_000
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(index_state).values(lease_heartbeat=stale))

    async def test_a_live_lease_refuses_a_second_rebuild(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        await self._stamped(storage, "RIVAL", maintenance_module._now_ms())
        result = await storage.rebuild()
        assert result.success is False
        [error] = result.errors
        assert error.kind == ErrorKind.conflict
        assert error.retryable is True
        assert "already running" in error.message
        holder, _ = await self._lease(storage)
        assert holder == "RIVAL"  # the refused claimant released nothing
        await storage.close()

    async def test_an_expired_lease_is_claimed_through_and_released(self, tmp_path) -> None:
        # A crashed run frees itself by silence: past the TTL the next
        # claimant takes over, runs, and leaves the lease clear.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        stale = maintenance_module._now_ms() - maintenance_module.INDEX_LEASE_TTL_MS - 1_000
        await self._stamped(storage, "DEAD", stale)
        assert (await storage.rebuild()).success is True
        assert await self._lease(storage) == (None, None)
        await storage.close()

    async def test_a_lost_publish_still_releases_the_lease(self, tmp_path) -> None:
        # The release rides a finally: even a run that loses the CAS
        # leaves the lease clear for the next claimant.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="raced body")])
        index_state = storage._host.tables.index_state

        async def rival() -> None:
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(index_state).values(current_gram_epoch=99))

        with installed("rebuild:before-publish", rival):
            result = await storage.rebuild()
        assert result.success is False
        assert await self._lease(storage) == (None, None)
        await storage.close()

    async def test_a_preset_lost_flag_stops_at_the_phase_boundary(self, tmp_path) -> None:
        # The chunk pass reads the flag before every slice, the first
        # included: a lease already lost stops it before any chunk work.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        lost = asyncio.Event()
        lost.set()
        result = await maintenance_module._rebuild_phases(
            storage._maintenance(), storage._host.tables, lost, await _claimed(storage)
        )
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.conflict
        assert "expired mid-run" in result.errors[0].message
        assert await _flags(storage, "/a.txt") == (False, False)
        await storage.close()

    async def test_the_beat_task_flags_a_taken_lease(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(maintenance_module, "INDEX_LEASE_HEARTBEAT_SECONDS", 0.01)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        await self._stamped(storage, "RIVAL", maintenance_module._now_ms())
        lost = asyncio.Event()
        task = asyncio.create_task(
            maintenance_module._beat_index_lease(storage._maintenance(), storage._host.tables, "MINE", lost)
        )
        await lost.wait()
        await task
        await storage.close()

    async def test_a_transport_conflict_is_not_a_taken_lease(self, tmp_path, monkeypatch) -> None:
        """A beat that cannot get a writer (the build phase holds SQLite's
        lock past the beat's retries) comes back a ``conflict`` too; only
        the marked zero-row verdict stops the run — the TTL absorbs the rest."""
        monkeypatch.setattr(maintenance_module, "INDEX_LEASE_HEARTBEAT_SECONDS", 0.01)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        stalled = Result(
            ops=("rebuild",),
            errors=[ResultError(kind=ErrorKind.conflict, message="rebuild kept losing", retryable=True)],
        )
        beats = 0
        fifth = asyncio.Event()

        async def stalled_write(op: str, fn: Any) -> Result:
            nonlocal beats
            beats += 1
            if beats == 5:
                fifth.set()
            return stalled

        monkeypatch.setattr(storage, "_execute_maintenance", stalled_write)
        lost = asyncio.Event()
        task = asyncio.create_task(
            maintenance_module._beat_index_lease(storage._maintenance(), storage._host.tables, "MINE", lost)
        )
        await fifth.wait()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert beats >= 5 and not lost.is_set()
        assert maintenance_module.lease_lost(
            maintenance_module.lease_lost_result()
        ) and not maintenance_module.lease_lost(stalled)
        await storage.close()

    async def test_a_successful_beat_advances_the_heartbeat(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(maintenance_module, "INDEX_LEASE_HEARTBEAT_SECONDS", 0.01)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        backdated = maintenance_module._now_ms() - 60_000
        await self._stamped(storage, "MINE", backdated)
        beat = storage._execute_maintenance
        landed = asyncio.Event()

        async def landing(op: str, fn: Any) -> Result:
            result = await beat(op, fn)
            landed.set()
            return result

        monkeypatch.setattr(storage, "_execute_maintenance", landing)
        lost = asyncio.Event()
        task = asyncio.create_task(
            maintenance_module._beat_index_lease(storage._maintenance(), storage._host.tables, "MINE", lost)
        )
        await landed.wait()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert not lost.is_set()
        _, heartbeat = await self._lease(storage)
        assert heartbeat is not None and heartbeat > backdated
        await storage.close()

    async def test_a_failed_chunk_phase_returns_its_failure_and_releases(self, tmp_path, monkeypatch) -> None:
        # The phase failure is the verb's result — and the finally still
        # clears the lease for the next claimant.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])
        failure = Result(ops=("rebuild",), errors=[ResultError(kind=ErrorKind.internal, message="chunk broke")])

        async def broken(session, tables, profile, parameter_budget, membership_budget, executor, **_kw) -> Result:
            return failure

        monkeypatch.setattr(maintenance_module, "chunk_dirty", broken)
        result = await storage.rebuild()
        assert result.success is False
        assert result.errors[0].message == "chunk broke"
        assert await self._lease(storage) == (None, None)
        await storage.close()

    async def test_a_lease_lost_after_build_stops_before_publish(self, tmp_path) -> None:
        # The flag flips between the build and publish boundaries: the
        # built epoch is abandoned unpublished, never CAS-raced.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])

        class FlipsOnThirdCheck(asyncio.Event):
            # The checks: before the one chunk slice, after the pass, then after the build.
            calls = 0

            def is_set(self) -> bool:
                type(self).calls += 1
                return type(self).calls >= 3

        result = await maintenance_module._rebuild_phases(
            storage._maintenance(), storage._host.tables, FlipsOnThirdCheck(), await _claimed(storage)
        )
        assert result.success is False
        assert "expired mid-run" in result.errors[0].message
        assert await _epoch(storage) is None  # the publish never ran
        await storage.close()

    async def test_a_run_whose_lease_was_taken_publishes_nothing(self, tmp_path, monkeypatch) -> None:
        """Guards: ``lease_holder == state.token`` dropped from the publish's compare-and-set, so a run
        whose lease a rival claimed publishes an epoch naming chunk rows the rival has replaced."""
        lapsed = DatabaseStorage(url=_url(tmp_path))
        assert (await lapsed.write(entries=[Entry(path=Path("/e.txt"), content="echo body")])).success is True
        assert (await lapsed.rebuild()).success is True
        assert (await lapsed.write(entries=[Entry(path=Path("/f.txt"), content="foxtrot body")])).success is True
        holder = DatabaseStorage(url=_url(tmp_path))
        arrived = [asyncio.Event(), asyncio.Event()]
        released = [asyncio.Event(), asyncio.Event()]

        async def hold() -> None:
            mine = 0 if not arrived[0].is_set() else 1
            arrived[mine].set()
            await released[mine].wait()

        with installed("rebuild:before-publish", hold):
            first = asyncio.create_task(lapsed.rebuild())
            await arrived[0].wait()
            await self._made_stale(lapsed)
            # A newer chunker: the holder re-splits every entry with no version bump.
            monkeypatch.setattr(indexing, "chunk_generation", lambda: "a-newer-chunker")
            second = asyncio.create_task(holder.rebuild())
            await arrived[1].wait()
            released[0].set()
            lost = await first
            released[1].set()
            won = await second
        [error] = lost.errors
        assert (error.kind, error.retryable) == (ErrorKind.conflict, False)
        assert error.message.endswith("rebuild lost the index publish race for epoch 2"), error.message
        assert lost.ops == ("rebuild",)
        assert won.success is True, won.errors
        assert await _epoch(lapsed) == 3
        assert await _lexical_chunk_ids(lapsed, "/e.txt") == await _chunk_ids(lapsed, "/e.txt")
        with pytest.raises(TypeError):
            indexing.RebuildState()  # ty: ignore[missing-argument]
        tables = lapsed._host.tables
        for previous in (None, 3):
            session = _MatchingSession(sqlite.dialect())
            state = indexing.RebuildState(token="THE-TOKEN", previous_epoch=previous, epoch=4)
            await indexing.publish_epoch(cast("AsyncSession", session), tables, SQLITE, 2_000, 1_000, state)
            [(cas, _params)] = session.calls
            for dialect in (sqlite.dialect(), postgresql.dialect()):
                compiled = cas.compile(dialect=dialect)
                assert "lease_holder IS NULL" not in str(compiled), (dialect.name, compiled)
                assert "THE-TOKEN" in compiled.params.values(), (dialect.name, compiled.params)
        assert await self._lease(lapsed) == (None, None)
        never = indexing.RebuildState(token="NEVER-CLAIMED", previous_epoch=3, epoch=4)
        profile, budgets = lapsed._host.profile, (lapsed._host.parameter_budget, lapsed._host.membership_budget)
        missed = await lapsed._execute_maintenance(
            "rebuild", lambda session: indexing.publish_epoch(session, tables, profile, *budgets, never)
        )
        [error] = missed.errors
        assert (error.kind, error.retryable) == (ErrorKind.conflict, False)
        assert error.message.endswith("rebuild lost the index publish race for epoch 4"), error.message
        assert await _epoch(lapsed) == 3
        await holder.close()
        await lapsed.close()

    async def test_a_lease_lost_mid_pass_stops_before_the_next_slice(self, tmp_path, monkeypatch) -> None:
        """Guards: the chunk pass reading the beat's flag before its first slice alone, or a stopped pass
        dropping the link counts of the slices it committed."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 2)
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {f"/f{i}.md": f"See [gone](gone{i}.md).\n" for i in range(5)}
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
        lost = asyncio.Event()

        async def beat_proves_it_taken() -> None:
            lost.set()

        with installed("rebuild:before-chunk-split", beat_proves_it_taken):
            result = await maintenance_module._rebuild_phases(
                storage._maintenance(), storage._host.tables, lost, await _claimed(storage)
            )
        assert maintenance_module.lease_lost(result), result.errors
        assert {path for path in bodies if (await _flags(storage, path))[0]} == {"/f0.md", "/f1.md"}
        links = [error.data for error in result.errors if error.data and error.data.get("leg") == "links"]
        assert links == [{"leg": "links", "sources": 2, "edges": 0, "unresolved": 2}]
        await storage.close()

    async def test_a_lease_lost_in_the_last_slice_stops_before_the_build(self, tmp_path) -> None:
        """Guards: the gram phases going on to build after a pass whose last slice saw the lease taken."""
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body\n")])).success
        lost = asyncio.Event()

        async def beat_proves_it_taken() -> None:
            lost.set()

        with installed("rebuild:before-chunk-split", beat_proves_it_taken):
            result = await maintenance_module._rebuild_phases(
                storage._maintenance(), storage._host.tables, lost, await _claimed(storage)
            )
        assert maintenance_module.lease_lost(result), result.errors
        assert await _flags(storage, "/a.txt") == (True, False)  # the slice committed; no build followed
        assert await _count(storage, storage._host.tables.gram_epochs) == 0
        assert await _epoch(storage) is None
        await storage.close()

    async def test_a_lapsed_slice_reports_only_the_committed_slices_links(self, tmp_path, monkeypatch) -> None:
        """Guards: a slice its fence refused reporting the links of work it rolled back, a record raised when no
        reference is unresolved, or a failing pass dropping the counts of the slices it committed."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 2)
        real_beat = maintenance_module.heartbeat_index_lease
        fences = 0

        async def taken_before_the_second_fence(session: AsyncSession, tables: VFSTables, token: str) -> Result:
            nonlocal fences
            fences += 1
            if fences in (2, 4):
                await session.execute(update(tables.index_state).values(lease_holder="RIVAL"))
            return await real_beat(session, tables, token)

        monkeypatch.setattr(maintenance_module, "heartbeat_index_lease", taken_before_the_second_fence)
        for name, target in (("dead", "gone"), ("live", "here")):
            (tmp_path / name).mkdir()
            storage = DatabaseStorage(url=_url(tmp_path / name))
            bodies = {f"/f{i}.md": f"See [{target}]({target}.md).\n" for i in range(4)}
            bodies["/here.md"] = "here\n"
            assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
            result = await storage.rebuild()
            assert maintenance_module.lease_lost(result), result.errors
            links = [error.data for error in result.errors if error.data and error.data.get("leg") == "links"]
            expected = [{"leg": "links", "sources": 2, "edges": 0, "unresolved": 2}] if name == "dead" else []
            assert links == expected, name
            await storage.close()

    async def test_a_missed_fence_carries_the_bodys_own_records(self, tmp_path) -> None:
        """Guards: the lease-lost verdict dropping the advisory records its fenced body returned."""
        storage = DatabaseStorage(url=_url(tmp_path))
        note = classified(ErrorKind.not_found, severity=Severity.info, detail="an advisory the body returned")

        async def body(session: AsyncSession) -> Result:
            return Result(ops=("rebuild",), errors=[note])

        fenced = maintenance_module.lease_fenced(storage._host.tables, "NEVER-CLAIMED", body)
        result = await storage._execute_leased("rebuild", fenced)
        assert maintenance_module.lease_lost(result) and result.errors[0] == note, result.errors
        await storage.close()

    async def test_a_rival_chunk_row_collision_redrives_and_is_classified(self, tmp_path, monkeypatch) -> None:
        """Guards: the chunk pass's collision handler deleted, so a rival's chunk rows end the run in the
        driver's text; and the handler recognising every integrity failure, so a NOT NULL redrives as a conflict."""
        passes = 0
        real_pass, real_insert = maintenance_module.chunk_dirty, indexing.bulk_insert

        async def counted(*args: Any, **kwargs: Any) -> Result:
            nonlocal passes
            passes += 1
            return await real_pass(*args, **kwargs)

        monkeypatch.setattr(maintenance_module, "chunk_dirty", counted)
        body = TestChunkProvenance.BODY
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content=body)])).success is True
        planted: list[bool] = []

        async def collided(session: AsyncSession, table: Any, rows: Any) -> None:
            if table is storage._host.tables.chunks and not planted:
                planted.append(True)
                await session.execute(insert(table), [{**rows[0], "chunk_index": 0}])
            await real_insert(session, table, rows)

        monkeypatch.setattr(indexing, "bulk_insert", collided)
        result = await storage.rebuild()
        assert result.success is True, result.errors
        assert passes == 2
        assert not [error for error in result.errors if error.kind == ErrorKind.unavailable]
        assert await _split_is_stored(storage, "/a.py", body)
        await storage.close()

        passes = 0
        (tmp_path / "defect").mkdir()
        defect = DatabaseStorage(url=_url(tmp_path / "defect"))
        assert (await defect.write(entries=[Entry(path=Path("/a.py"), content=body)])).success is True

        async def unowned(session: AsyncSession, table: Any, rows: Any) -> None:
            orphaned = [{**row, "entry_id": None} for row in rows] if table is defect._host.tables.chunks else rows
            await real_insert(session, table, orphaned)

        monkeypatch.setattr(indexing, "bulk_insert", unowned)
        failed = await defect.rebuild()
        [error] = failed.errors
        assert failed.success is False and passes == 1
        assert not (error.kind == ErrorKind.conflict and error.retryable), error
        await defect.close()

    async def test_a_lease_taken_between_slices_keeps_the_committed_slice_and_the_next_run_finishes(
        self, tmp_path, monkeypatch
    ) -> None:
        """Guards: the fence taken off every slice after the first, so a slice commits after the lease was taken."""
        monkeypatch.setattr(indexing, "CHUNK_SLICE_ENTRIES", 2)
        storage = DatabaseStorage(url=_url(tmp_path))
        bodies = {f"/f{i}.txt": f"file {i} body\n" for i in range(5)}
        assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
        real_beat = maintenance_module.heartbeat_index_lease
        fences = 0

        async def taken_before_the_second_fence(session: AsyncSession, tables: VFSTables, token: str) -> Result:
            # On SQLite no rival can commit inside a slice, so the claim's effect is staged in its own session.
            nonlocal fences
            fences += 1
            if fences == 2:
                await session.execute(update(tables.index_state).values(lease_holder="RIVAL"))
            return await real_beat(session, tables, token)

        monkeypatch.setattr(maintenance_module, "heartbeat_index_lease", taken_before_the_second_fence)
        result = await storage.rebuild()
        assert maintenance_module.lease_lost(result), result.errors
        first = {"/f0.txt", "/f1.txt"}
        assert {path for path in bodies if (await _flags(storage, path))[0]} == first
        kept = {path: await _chunk_ids(storage, path) for path in first}
        fenced = _spy_fenced(storage, monkeypatch)
        assert (await storage.rebuild()).success is True
        assert [len(each.chunked) for each in fenced] == [4, 5]
        assert {path: await _chunk_ids(storage, path) for path in first} == kept  # no committed slice repeated
        for path, body in bodies.items():
            assert await _flags(storage, path) == (True, True)
            assert await _split_is_stored(storage, path, body), path
        await storage.close()


# ---------------------------------------------------------------------------
# The offload seam: rebuild CPU leaves the event loop
# ---------------------------------------------------------------------------


class _HoppingBuilder:
    """A builder double whose work waits for the loop to turn, as the engines' GIL-releasing work lets it."""

    def __init__(self, inner: Any, ticker: LoopTicker) -> None:
        self._inner = inner
        self._ticker = ticker

    def add_docs(self, batch: Any) -> None:
        self._ticker.hop()
        self._inner.add_docs(batch)

    def next_batch(self, cap: int) -> Any:
        self._ticker.hop()
        return self._inner.next_batch(cap)


class TestRebuildLoopResponsiveness:
    async def test_the_loop_keeps_ticking_through_every_rebuild_hop(self, tmp_path, monkeypatch) -> None:
        """Guards: chunk_dirty's assessment-and-split, build_epoch's
        fold-and-feed, or the drain running inline on the loop."""
        real_assess = indexing._assess_and_split
        real_builder = indexing.postings_builder
        ticker = LoopTicker()

        def hopping_assess(rows: Any, generation: str, links_generation: str) -> Any:
            ticker.hop()
            return real_assess(rows, generation, links_generation)

        monkeypatch.setattr(indexing, "_assess_and_split", hopping_assess)
        monkeypatch.setattr(indexing, "postings_builder", lambda: _HoppingBuilder(real_builder(), ticker))
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i}.py"), content=f"def fn_{i}():\n    return {i}\n") for i in range(8)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        ticker.start()
        result = await storage.rebuild()
        ticker.stop()
        assert result.success is True, result.errors
        # One assessment, at least one feed and one drain: every hop saw the loop turn.
        assert ticker.hops >= 3
        assert await _flags(storage, "/f0.py") == (True, True)
        await storage.close()


class TestSplitBatchBudget:
    async def test_sub_batched_splits_match_the_whole_batch_answer(self, tmp_path, monkeypatch) -> None:
        # A one-byte budget forces every split target into its own
        # sub-batch (the flush and singleton-exemption path); the chunk
        # rows must equal the default whole-batch answer exactly.
        files = {
            f"/src/f{i}.py": "\n".join(f"def fn_{i}_{j}():\n    return {i + j}" for j in range(120)) for i in range(6)
        }

        async def chunk_rows(storage: DatabaseStorage) -> list[tuple]:
            chunks, entry = storage._host.tables.chunks, storage._host.tables.entry
            stmt = (
                select(entry.c.path, chunks.c.chunk_index, chunks.c.line_start, chunks.c.line_end, chunks.c.content)
                .select_from(chunks.join(entry, chunks.c.entry_id == entry.c.entry_id))
                .order_by(entry.c.path, chunks.c.chunk_index)
            )
            async with storage._host.engine.connect() as conn:
                return [row._tuple() for row in await conn.execute(stmt)]

        answers: list[list[tuple]] = []
        for name in ("whole", "batched"):
            if name == "batched":
                monkeypatch.setattr(indexing, "_SPLIT_BATCH_BYTES", 1)
            storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/{name}.sqlite")
            entries = [Entry(path=Path(path), content=content) for path, content in files.items()]
            assert (await storage.write(entries=entries, parents=True)).success is True
            assert (await storage.rebuild()).success is True
            answers.append(await chunk_rows(storage))
            await storage.close()
        whole, batched = answers
        assert whole and len(whole) > len(files)  # multi-chunk bodies referee the split
        assert batched == whole

    async def test_the_split_batcher_actually_slices(self, tmp_path, monkeypatch) -> None:
        # The existence referee: a whole-set reversion would serve every
        # target through one splitter call and still match the answer.
        monkeypatch.setattr(indexing, "_SPLIT_BATCH_BYTES", 1)
        calls = 0
        real = Chunk.split_batch

        def counting(files: Any) -> Any:
            nonlocal calls
            calls += 1
            return real(files)

        monkeypatch.setattr(Chunk, "split_batch", counting)
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/f{i}.py"), content=f"def fn{i}():\n    return {i}\n") for i in range(3)]
        assert (await storage.write(entries=entries)).success is True
        assert (await storage.rebuild()).success is True
        assert calls == 3
        await storage.close()

    def test_budgets_keep_their_declared_identities(self) -> None:
        # Voiding a budget must fail without a monkeypatch: split and extract
        # are declared twins; an insert's payload is far under a feed's.
        assert indexing._SPLIT_BATCH_BYTES == indexing._EXTRACT_BATCH_BYTES
        assert 0 < indexing._POSTING_BATCH_BYTES < indexing._EXTRACT_BATCH_BYTES


async def _stamp(storage: DatabaseStorage, path: str) -> int | None:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry.c.indexed_epoch).where(entry.c.path == path))).scalar_one()


class TestIndexedStamp:
    """``indexed_epoch`` names the published segment holding an entry's current chunks, or nothing."""

    async def test_the_full_publish_stamps_every_covered_entry(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        files = [Entry(path=Path(f"/f{n}.txt"), content=f"stamped body {n}") for n in range(3)]
        assert (await storage.write(entries=[*files, Entry(path=Path("/ab.txt"), content="ab")])).success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/f0.txt"), content="stamped other")])).success
        assert (await storage.rebuild()).success is True
        current = await _epoch(storage)
        assert [await _stamp(storage, f"/f{n}.txt") for n in range(3)] == [current] * 3
        assert await _stamp(storage, "/ab.txt") is None  # never indexable, never posted
        await storage.close()

    async def test_a_missed_flip_is_stamped_all_the_same(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success is True

        async def away_and_back() -> None:
            for body in ("other body", "alpha body"):
                assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content=body)])).success

        with installed("rebuild:before-publish", away_and_back):
            assert (await storage.rebuild()).success is True
        assert await _flags(storage, "/a.txt") == (False, False)
        assert await _stamp(storage, "/a.txt") == await _epoch(storage)
        await storage.close()

    async def test_a_re_split_clears_the_stamp(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success is True
        assert (await storage.write(entries=[Entry(path=Path("/b.txt"), content="bravo body")])).success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha changed")])).success
        assert (await storage.write(entries=[Entry(path=Path("/b.txt"), content="bravo body")])).success
        seen: dict[str, int | None] = {}

        async def at_the_flip() -> None:
            seen.update({path: await _stamp(storage, path) for path in ("/a.txt", "/b.txt")})

        stop = RuntimeError("stopped after the slice")

        async def stopped(*args: Any, **kwargs: Any) -> Result:
            raise stop

        with installed("rebuild:before-chunk-flip", at_the_flip):
            monkeypatch.setattr(maintenance_module, "build_epoch", stopped)
            with pytest.raises(RuntimeError):
                await storage.rebuild()
        assert seen == {"/a.txt": 1, "/b.txt": 1}
        assert (await _stamp(storage, "/a.txt"), await _stamp(storage, "/b.txt")) == (None, 1)
        await storage.close()

    async def test_live_deltas_are_work_pending(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success is True
        assert (await storage.rebuild()).success is True
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            assert await indexing._work_pending(session, tables, 1) is False
        assert (await storage.write(entries=[Entry(path=Path("/b.txt"), content="bravo body")])).success is True
        assert (await storage.refresh()).success is True
        async with storage._host.session_factory() as session:
            assert await indexing._work_pending(session, tables, 1) is True
        await storage.close()

    async def test_every_flip_spelling_stamps_by_id_and_guards_the_flag(self) -> None:
        """Guards: the stamp following the version or liveness guard, or the guard leaving the ``encoded`` CASE."""
        entry = build_vfs_tables().entry
        pairs = [("01A", 1), ("01B", 2), ("01C", 3)]
        # The row-constructor form binds three values a row: six binds take two rows a statement.
        spellings = (
            (POSTGRESQL, _values_join_dialect(), 2_000, 1),
            (SQLITE, sqlite.dialect(), 6, 2),
            (GENERIC, postgresql.dialect(), 2_000, 1),
        )
        for profile, dialect, budget, statements in spellings:
            session = _RecordingSession(dialect)
            await indexing._flip_flags(
                cast("AsyncSession", session),
                entry,
                profile,
                2_000,
                budget,
                pairs,
                assignments={"encoded": True},
                stamp={"indexed_epoch": 7},
            )
            assert len(session.calls) == statements, profile.name
            for stmt, _params in session.calls:
                sql = str(stmt.compile(dialect=dialect))
                setting, _, where = sql.partition(" WHERE ")
                assert "indexed_epoch=" in setting.replace(" ", "") and "CASE WHEN" in setting, (profile.name, sql)
                assert "deleted_at IS NULL" in setting and "deleted_at" not in where, (profile.name, sql)
                assert "version" not in where, (profile.name, sql)


class TestRareTerm:
    def test_only_sqlite_is_told_a_term_is_rare(self) -> None:
        """Guards: the hint dropped from SQLite, whose planner then walks the primary key under the limit, or
        rendered on an engine that has no such function."""
        tables = build_vfs_tables()
        terms = [tables.entry.c.deleted_at.is_(None), ~tables.entry.c.chunked]
        for profile, dialect, expected in (
            (SQLITE, sqlite.dialect(), "unlikely(vfs_entries.encoded = 0) AND vfs_entries.indexable = 0"),
            (POSTGRESQL, postgresql.dialect(), "AND NOT vfs_entries.encoded AND NOT vfs_entries.indexable"),
            (GENERIC, postgresql.dialect(), "AND NOT vfs_entries.encoded AND NOT vfs_entries.indexable"),
        ):
            read = indexing._size_read(tables, profile, terms, past=0, wanted=4, seek=True)
            sql = " ".join(str(read.compile(dialect=dialect)).split())
            assert expected in sql, (profile.name, sql)
            assert "unlikely" not in sql or profile.rarity_hint == "unlikely", (profile.name, sql)


class TestGenerationLaw:
    async def test_a_restore_across_a_bump_is_posted_until_the_rebuild_re_splits_it(
        self, tmp_path, monkeypatch
    ) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        files = [Entry(path=Path(p), content=c) for p, c in (("/a.txt", "alpha body"), ("/t.txt", "trashed body"))]
        assert (await storage.write(entries=files)).success is True
        assert (await storage.rebuild()).success is True
        assert (await storage.delete(path=Path("/t.txt"))).success is True
        real = chunk_generation
        monkeypatch.setattr(indexing, "chunk_generation", lambda: real() + "-bumped")
        assert (await storage.rebuild()).success is True
        held = await _chunk_ids(storage, "/t.txt")
        assert (await storage.restore(path=Path("/t.txt"))).success is True
        split: list[list[str]] = []
        real_split = indexing._assess_and_split

        def counting(rows: Any, *args: Any) -> Any:
            split.append([row.path for row in rows])
            return real_split(rows, *args)

        monkeypatch.setattr(indexing, "_assess_and_split", counting)
        assert (await storage.refresh()).success is True
        assert split == []
        delta = await _scalar_max_epoch(storage)
        assert await _chunk_ids(storage, "/t.txt") == held
        assert await _stamp(storage, "/t.txt") == delta
        assert await _segments_holding(storage, held) == {delta}
        assert (await storage.rebuild()).success is True
        assert split == [["/t.txt"]]
        assert not await _chunk_ids(storage, "/t.txt") & held
        assert await _stamp(storage, "/t.txt") == await _epoch(storage)
        assert await _stranded_ids(storage) == 0
        monkeypatch.setattr(indexing, "link_generation", lambda: "a-newer-extractor")
        stamps = {path: await _stamp(storage, path) for path in ("/a.txt", "/t.txt")}
        split.clear()
        assert (await storage.refresh()).success is True
        assert split == [] and {path: await _stamp(storage, path) for path in stamps} == stamps
        await storage.close()


async def _scalar_max_epoch(storage: DatabaseStorage) -> int:
    epochs = storage._host.tables.gram_epochs
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(func.max(epochs.c.epoch)))).scalar_one()


async def _segments_holding(storage: DatabaseStorage, chunk_ids: set[int]) -> set[int]:
    docs = storage._host.tables.lex_docs
    async with storage._host.engine.connect() as conn:
        rows = await conn.execute(select(docs.c.epoch).where(docs.c.chunk_id.in_(sorted(chunk_ids))))
        return set(rows.scalars())


async def _stranded_ids(storage: DatabaseStorage) -> int:
    docs, chunks = storage._host.tables.lex_docs, storage._host.tables.chunks
    held = select(chunks.c.id).where(chunks.c.id == docs.c.chunk_id).exists()
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(docs).where(~held))).scalar_one()
