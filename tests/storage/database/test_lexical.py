"""The lexical index's storage half: the epoch build, its publish and
reclaim parity with grams, the options fingerprint, the statistics
probe, the batch budgets, and the BM25 fidelity referees on sqlite.
"""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any

from sqlalchemy import event, func, select, update

from tests.support.database_helpers import _url
from tests.support.lexical_fidelity import assert_lexical_fidelity, assert_two_round_fidelity
from vfs.models import Entry
from vfs.models import lexical as lexical_model
from vfs.models.lexical import BM25_B, BM25_K1, SummaryRow, decode_summary, idf, pure_tokenize, term_weight
from vfs.models.postings import decode_postings, decode_varints
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database import lexical as lexical_store
from vfs.storage.backends.database.lexical import TermStatistics, lexical_stats
from vfs.storage.backends.database.seams import installed

BODIES = {
    "/a.py": "def build_index(rows):\n    return PostingsBuilder(rows)\n",
    "/b.py": "rows = build_rows()\nrows.sort()\n",
    "/c.md": "The index is built from rows.\n",
}


async def _epoch(storage: DatabaseStorage) -> int | None:
    meta = storage._host.tables.meta
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()


async def _count(storage: DatabaseStorage, table: Any, epoch: int | None = None) -> int:
    stmt = select(func.count()).select_from(table)
    if epoch is not None:
        stmt = stmt.where(table.c.epoch == epoch)
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(stmt)).scalar_one()


async def _seeded(tmp_path) -> DatabaseStorage:
    storage = DatabaseStorage(url=_url(tmp_path))
    entries = [Entry(path=Path(path), content=body) for path, body in BODIES.items()]
    assert (await storage.write(entries=entries)).success is True
    assert (await storage.reindex()).success is True
    return storage


async def _seed_lexical_rows(storage: DatabaseStorage, epoch: int) -> None:
    tables = storage._host.tables
    async with storage._host.engine.begin() as conn:
        await conn.execute(
            tables.lex_stats.insert(), [{"epoch": epoch, "n_docs": 1, "avg_dl": 1.0, "k1": BM25_K1, "b": BM25_B}]
        )
        await conn.execute(
            tables.lex_df.insert(),
            [{"epoch": epoch, "term": "seed", "df": 1, "idf": 0.5, "max_weight": 0.5, "blocks": b""}],
        )
        await conn.execute(
            tables.lex_postings.insert(),
            [
                {
                    "epoch": epoch,
                    "term": "seed",
                    "block_no": 0,
                    "doc_count": 1,
                    "doc_ids": b"\x01\x01",
                    "tfs": b"\x01",
                    "dls": b"\x01",
                }
            ],
        )
        await conn.execute(tables.lex_docs.insert(), [{"epoch": epoch, "chunk_id": 1, "entry_id": "0" * 26, "dl": 1}])


def _lexical_tables(storage: DatabaseStorage) -> tuple[Any, ...]:
    tables = storage._host.tables
    return (tables.lex_docs, tables.lex_postings, tables.lex_df, tables.lex_stats)


class _Observed:
    """The active builder with a hook on every feed (a pyclass takes no new attributes)."""

    def __init__(self, inner: Any, on_add: Any) -> None:
        self._inner, self._on_add = inner, on_add

    def add_docs(self, docs: Any) -> Any:
        self._on_add(docs)
        return self._inner.add_docs(docs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class TestBuild:
    async def test_reindex_builds_the_four_row_sets_under_the_gram_epoch(self, tmp_path) -> None:
        storage = await _seeded(tmp_path)
        tables = storage._host.tables
        epoch = await _epoch(storage)
        assert epoch == 1
        async with storage._host.engine.connect() as conn:
            chunks = (
                await conn.execute(select(tables.chunks.c.id, tables.chunks.c.entry_id, tables.chunks.c.content))
            ).all()
            docs = (await conn.execute(select(tables.lex_docs).order_by(tables.lex_docs.c.chunk_id))).all()
            dfs = {row.term: row for row in await conn.execute(select(tables.lex_df))}
            blocks = (await conn.execute(select(tables.lex_postings))).all()
            stats = (await conn.execute(select(tables.lex_stats))).one()
        assert {row.epoch for row in docs} == {1} and {row.epoch for row in blocks} == {1} and stats.epoch == 1
        # One doc row per chunk with the exact emitted token count.
        tokens = {chunk.id: pure_tokenize(chunk.content) for chunk in chunks}
        assert {(row.chunk_id, row.entry_id, row.dl) for row in docs} == {
            (chunk.id, chunk.entry_id, len(tokens[chunk.id])) for chunk in chunks
        }
        n_docs = len(chunks)
        avg_dl = sum(len(t) for t in tokens.values()) / n_docs
        assert (stats.n_docs, stats.avg_dl, stats.k1, stats.b) == (n_docs, avg_dl, BM25_K1, BM25_B)
        # df/idf per term; every block decodes to the postings the tokens say.
        assert (dfs["rows"].df, dfs["rows"].idf) == (3, idf(3, n_docs))
        assert (dfs["postingsbuilder"].df, dfs["postingsbuilder"].idf) == (1, idf(1, n_docs))
        assert "the" in dfs and "is" in dfs  # no stop list
        postings = 0
        for row in blocks:
            assert row.block_no == 0  # three bodies: one block per term
            ids, tfs, dls = decode_postings(row.doc_ids), decode_varints(row.tfs), decode_varints(row.dls)
            assert row.doc_count == ids.size == tfs.size == dls.size
            for chunk_id, tf, dl in zip(ids.tolist(), tfs.tolist(), dls.tolist(), strict=True):
                assert tokens[chunk_id].count(row.term) == tf > 0
                assert len(tokens[chunk_id]) == dl
            summary = decode_summary(dfs[row.term].blocks)
            assert summary.first_ids.tolist() == [int(ids[0])]
            truth = max(term_weight(tf, dl, avg_dl, dfs[row.term].idf) for tf, dl in zip(tfs, dls, strict=True))
            assert summary.max_weights.tolist() == [truth] and dfs[row.term].max_weight == truth
            postings += row.doc_count
        assert postings == sum(len(set(t)) for t in tokens.values())
        await storage.close()

    async def test_the_fidelity_referee_holds_on_sqlite(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await assert_lexical_fidelity(storage)
        await storage.close()

    async def test_the_two_round_fetch_ranks_as_the_whole_fetch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await assert_two_round_fidelity(storage)
        await storage.close()

    async def test_an_empty_store_writes_the_stats_row_only(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.reindex()).success is True
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            stats = (await conn.execute(select(tables.lex_stats))).one()
        assert (stats.epoch, stats.n_docs, stats.avg_dl, stats.k1, stats.b) == (1, 0, 0.0, BM25_K1, BM25_B)
        assert await _count(storage, tables.lex_docs) == 0
        assert await _count(storage, tables.lex_postings) == 0
        await storage.close()

    async def test_ineligible_entries_have_no_lexical_rows(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexing, "MAX_INDEXABLE_BYTES", 40)
        storage = DatabaseStorage(url=_url(tmp_path))
        small = Entry(path=Path("/small.py"), content="tiny_body = 1\n")
        big = Entry(path=Path("/big.py"), content="oversized_body = " + "x" * 80 + "\n")
        assert (await storage.write(entries=[small, big])).success is True
        assert (await storage.reindex()).success is True
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            located = select(tables.entry.c.path, tables.entry.c.indexable, tables.lex_docs.c.chunk_id).select_from(
                tables.entry.outerjoin(tables.lex_docs, tables.lex_docs.c.entry_id == tables.entry.c.entry_id)
            )
            rows = {row.path: (row.indexable, row.chunk_id) for row in await conn.execute(located)}
            big_terms = (
                await conn.execute(select(tables.lex_df.c.term).where(tables.lex_df.c.term == "oversized_body"))
            ).all()
        assert rows["/small.py"][0] is True and rows["/small.py"][1] is not None
        assert rows["/big.py"] == (False, None)
        assert big_terms == []
        await storage.close()

    async def test_the_publish_invariant(self, tmp_path) -> None:
        """``encoded=True`` implies every chunk of the entry is in the current
        lexical epoch; an entry written after the build has no current rows."""
        storage = await _seeded(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/late.py"), content="late_arrival = True\n")])).success
        tables = storage._host.tables
        entry, chunks, docs = tables.entry, tables.chunks, tables.lex_docs

        def coverage(epoch: int) -> Any:
            joined = entry.outerjoin(chunks, chunks.c.entry_id == entry.c.entry_id).outerjoin(
                docs, (docs.c.chunk_id == chunks.c.id) & (docs.c.epoch == epoch)
            )
            columns = (entry.c.path, entry.c.encoded, chunks.c.id, docs.c.chunk_id)
            return select(*columns).select_from(joined).where(entry.c.kind == "file")

        async with storage._host.engine.connect() as conn:
            rows = (await conn.execute(coverage(1))).all()
        assert {row.path for row in rows} == {*BODIES, "/late.py"}
        for row in rows:
            if row.encoded:
                assert row.chunk_id == row.id, row.path  # every chunk of a covered entry is in the epoch
            else:
                assert row.path == "/late.py" and row.chunk_id is None
        assert (await storage.reindex()).success is True
        async with storage._host.engine.connect() as conn:
            late = (await conn.execute(coverage(2).where(entry.c.path == "/late.py"))).all()
        assert len(late) == 1 and late[0].encoded is True and late[0].chunk_id == late[0].id
        await storage.close()

    async def test_a_trashed_entry_leaves_the_next_epoch(self, tmp_path) -> None:
        """Delete demotes ``encoded``; its chunk rows survive for restore but
        the next build must not index them (the scan's ``deleted_at`` gate).
        A delete alone pends no build — the invariant is one-directional —
        so a dirtying write forces the epoch that must exclude the trash."""
        storage = await _seeded(tmp_path)
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            trashed = (
                await conn.execute(select(tables.entry.c.entry_id).where(tables.entry.c.path == "/a.py"))
            ).scalar_one()
        assert (await storage.delete(path=Path("/a.py"))).success is True
        assert (await storage.write(entries=[Entry(path=Path("/d.py"), content="fresh_body = 4\n")])).success
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        async with storage._host.engine.connect() as conn:
            docs = (await conn.execute(select(tables.lex_docs).where(tables.lex_docs.c.entry_id == trashed))).all()
            dfs = {row.term: row.df for row in await conn.execute(select(tables.lex_df))}
        assert docs == []
        assert "postingsbuilder" not in dfs  # /a.py's own vocabulary is gone
        assert dfs["rows"] == 2  # df counts the two live bodies only
        await storage.close()

    async def test_the_build_cpu_hops_through_the_offload_pool(self, tmp_path, monkeypatch) -> None:
        hops: list[str] = []
        real = lexical_store.call_offloaded

        async def counting(executor: Any, fn: Any) -> Any:
            target = fn.func if isinstance(fn, partial) else fn
            hops.append(getattr(target, "__name__", repr(target)))
            return await real(executor, fn)

        monkeypatch.setattr(lexical_store, "call_offloaded", counting)
        storage = await _seeded(tmp_path)
        # One feed on three small bodies, the seal, then each drain until it answers None.
        assert hops == ["add_docs", "finish", "_df_rows", "_df_rows", "_block_rows", "_block_rows"]
        await storage.close()

    async def test_the_loop_keeps_ticking_through_a_slow_feed(self, tmp_path, monkeypatch) -> None:
        real_builder = lexical_store.lexical_builder
        monkeypatch.setattr(
            lexical_store, "lexical_builder", lambda: _Observed(real_builder(), lambda _d: time.sleep(0.3))
        )
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content="slow_body = 1\n")])).success is True
        gaps: list[float] = []

        async def tick() -> None:
            last = time.monotonic()
            while True:
                await asyncio.sleep(0.01)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        ticker = asyncio.ensure_future(tick())
        result = await storage.reindex()
        ticker.cancel()
        assert result.success is True
        assert gaps and max(gaps) < 0.2
        await storage.close()


class TestFingerprint:
    async def test_a_bm25_constant_change_forces_a_rebuild(self, tmp_path, monkeypatch) -> None:
        storage = await _seeded(tmp_path)
        assert await _epoch(storage) == 1
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 1  # steady state is a no-op
        monkeypatch.setattr(lexical_model, "BM25_K1", 0.9)
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        await storage.close()

    async def test_a_tokenizer_version_bump_forces_a_rebuild(self, tmp_path, monkeypatch) -> None:
        storage = await _seeded(tmp_path)
        monkeypatch.setattr(lexical_model, "TOKENIZER_VERSION", 2)
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        await storage.close()

    async def test_a_block_size_or_codec_change_forces_a_rebuild(self, tmp_path, monkeypatch) -> None:
        storage = await _seeded(tmp_path)
        monkeypatch.setattr(lexical_model, "BLOCK_SIZE", 64)
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        monkeypatch.setattr(lexical_model, "BLOCK_CODEC", "other")
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 3
        await storage.close()

    def test_the_declared_format_version(self) -> None:
        assert indexing.INDEX_FORMAT_VERSION == 4
        assert "tokenizer=1" in lexical_model.options_fingerprint()


class TestReclaim:
    async def test_a_rewrite_reclaims_the_old_epochs_lexical_rows(self, tmp_path) -> None:
        storage = await _seeded(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content="rewritten_body = 2\n")])).success
        assert (await storage.reindex()).success is True
        assert await _epoch(storage) == 2
        for table in _lexical_tables(storage):
            assert await _count(storage, table, epoch=1) == 0
            assert await _count(storage, table, epoch=2) > 0
        await storage.close()

    async def test_a_cas_loser_reclaims_its_lexical_build(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content="raced_body = 1\n")])).success
        meta = storage._host.tables.meta

        async def rival() -> None:
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(meta).values(current_gram_epoch=99))

        with installed("reindex:before-publish", rival):
            result = await storage.reindex()
        assert result.success is False and result.errors[0].kind == VFSErrorKind.conflict
        for table in _lexical_tables(storage):
            assert await _count(storage, table) == 0
        await storage.close()

    async def test_reclaim_built_epoch_never_touches_the_published_rows(self, tmp_path) -> None:
        storage = await _seeded(tmp_path)
        await _seed_lexical_rows(storage, 7)
        async with storage._host.session_factory() as session, session.begin():
            assert (await indexing.reclaim_built_epoch(session, storage._host.tables, 7)).success is True
        for table in _lexical_tables(storage):
            assert await _count(storage, table, epoch=7) == 0
            assert await _count(storage, table, epoch=1) > 0
        await storage.close()

    async def test_a_rival_build_collides_into_a_clean_conflict(self, tmp_path, monkeypatch) -> None:
        """A rival's committed lexical rows at the minted epoch are a
        stale snapshot, redriven, and an exhausted redrive is a conflict."""
        storage = DatabaseStorage(url=_url(tmp_path))
        monkeypatch.setattr(storage._host, "_retry_attempts", 2)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        assert (await storage.write(entries=[Entry(path=Path("/a.py"), content="collide_body = 1\n")])).success
        await _seed_lexical_rows(storage, 1)  # only the lexical stats row: the postings insert never collides
        result = await storage.reindex()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.conflict
        await storage.close()


class TestTermStatistics:
    async def test_probes_the_summary_rows_and_the_corpus_row(self, tmp_path) -> None:
        storage = await _seeded(tmp_path)
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            stats = await lexical_stats(session, tables, 1, ["rows", "rows", "absent_term", "index"], 100)
        assert isinstance(stats, TermStatistics)
        assert stats.n_docs == 3 and stats.avg_dl > 0 and (stats.k1, stats.b) == (BM25_K1, BM25_B)
        rows = stats.terms["rows"]
        assert isinstance(rows, SummaryRow) and (rows.df, rows.idf) == (3, idf(3, 3))
        assert rows.max_weight == decode_summary(rows.blocks).max_weights.max()
        assert stats.terms["index"].df == 2
        assert "absent_term" not in stats.terms
        await storage.close()

    async def test_an_unbuilt_epoch_answers_zero_documents(self, tmp_path) -> None:
        storage = await _seeded(tmp_path)
        async with storage._host.session_factory() as session:
            stats = await lexical_stats(session, storage._host.tables, 42, ["rows"], 100)
        assert stats == TermStatistics({}, 0, 0.0, BM25_K1, BM25_B)
        await storage.close()

    async def test_the_probe_chunks_by_the_membership_budget(self, tmp_path) -> None:
        storage = await _seeded(tmp_path)
        probes: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if "lex_df" in statement:
                probes.append(statement)

        terms = [f"t{i}" for i in range(7)] + ["rows"]
        async with storage._host.session_factory() as session:
            stats = await lexical_stats(session, storage._host.tables, 1, terms, 3)
        assert len(probes) == 3  # eight distinct terms at a budget of three
        assert set(stats.terms) == {"rows"}
        await storage.close()


class TestBatchBudgets:
    async def test_inserts_split_by_the_row_budget(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(lexical_store, "_LEXICAL_INSERT_ROWS", 2)
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(path), content=body) for path, body in BODIES.items()]
        assert (await storage.write(entries=entries)).success is True
        inserts: list[tuple[str, int]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement.startswith("INSERT INTO vfs_lex_"):
                inserts.append((statement.split(" ")[2], len(parameters) if executemany else 1))

        assert (await storage.reindex()).success is True
        by_table: dict[str, list[int]] = {}
        for table, rows in inserts:
            by_table.setdefault(table, []).append(rows)
        assert by_table["vfs_lex_stats"] == [1]
        assert by_table["vfs_lex_docs"] == [2, 1]  # three chunks at a budget of two
        assert all(rows <= 2 for rows in by_table["vfs_lex_df"]) and len(by_table["vfs_lex_df"]) > 1
        assert all(rows <= 2 for rows in by_table["vfs_lex_postings"]) and len(by_table["vfs_lex_postings"]) > 1
        await storage.close()

    async def test_feeds_flush_at_the_byte_budget(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(lexical_store, "_TOKENIZE_BATCH_BYTES", 8)
        feeds: list[int] = []
        real_builder = lexical_store.lexical_builder
        monkeypatch.setattr(
            lexical_store, "lexical_builder", lambda: _Observed(real_builder(), lambda docs: feeds.append(len(docs)))
        )
        storage = await _seeded(tmp_path)
        assert feeds == [1] * 3  # every body outsizes the budget: one per feed
        await storage.close()

    async def test_the_scan_reads_keyset_pages_never_an_open_cursor(self, tmp_path, monkeypatch) -> None:
        """A write between batches on a connection with an open cursor is
        refused by drivers without MARS (SQL Server over ODBC); the scan
        must fetch each page whole before the build writes."""
        monkeypatch.setattr(lexical_store, "_SCAN_PAGE_ROWS", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(path), content=body) for path, body in BODIES.items()]
        assert (await storage.write(entries=entries)).success is True
        pages: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement.startswith("SELECT") and "vfs_chunks.content" in statement:
                pages.append(statement)

        assert (await storage.reindex()).success is True
        assert len(pages) == len(BODIES) + 1  # one row per page plus the empty page
        assert all("LIMIT" in p and "vfs_chunks.id >" in p for p in pages)
        await storage.close()

    def test_the_declared_budgets(self) -> None:
        assert lexical_store._LEXICAL_INSERT_ROWS == 20_000
        assert lexical_store._TOKENIZE_BATCH_BYTES == 4 * 1024 * 1024
        assert lexical_store._SCAN_PAGE_ROWS == 256
