"""The incremental index pass, ``refresh()``: a delta beside the base, published by the generation, folded away.

A refresh posts only the dirty entries no live segment already holds,
flips the kept ones, refuses without a published base or on fingerprint
drift, shares the rebuild's lease, seams and phases where they are
dirty-bounded, and finds every row it handles by a seek, never a walk.
"""

from __future__ import annotations

import asyncio
import math
import re
import shutil
import sqlite3
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
import sqlite_vec
from sqlalchemy import event, func, select, text, update

from tests.support.database_helpers import _url
from tests.support.documents import pdf_bytes
from tests.support.embedding_doubles import ScriptedProvider
from tests.support.oracles.postings import decode_postings
from tests.support.partial_callers import BOB, SYSTEM
from tests.support.statements import is_statistics_statement
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.models.chunking import chunk_generation
from vfs.paths import Path
from vfs.rendering.pdf import PdfRenderer
from vfs.results import ErrorKind, Result, Severity
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database import lexical as lexical_store
from vfs.storage.backends.database import maintenance as maintenance_module
from vfs.storage.backends.database import render as render_module
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.seams import installed
from vfs.storage.protocol import ResolvedPair

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncSession

SUFFIXES = (
    "before-render",
    "before-render-land",
    "before-chunk-split",
    "before-chunk-flip",
    "before-lexical",
    "before-publish",
    "before-reclaim",
    "before-embed",
)
NO_BASE = "no index is published yet; run rebuild"
NO_TEXT = "the published index holds no text yet; run rebuild"
DRIFT = (
    "the published index was built under other index options (a format, gram-option or chunk-generation change);"
    " run rebuild"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _store(tmp_path: Any, files: dict[str, str] | None = None) -> DatabaseStorage:
    tmp_path.mkdir(parents=True, exist_ok=True)
    storage = DatabaseStorage(url=_url(tmp_path))
    if files:
        await _written(storage, files)
    return storage


async def _written(storage: DatabaseStorage, files: dict[str, str]) -> None:
    entries = [Entry(path=Path(path), content=body) for path, body in files.items()]
    written = await storage.write(entries=entries, parents=True, authority=SYSTEM)
    assert written.success is True, written.errors


async def _scalar(storage: DatabaseStorage, statement: Any) -> Any:
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(statement)).scalar_one()


async def _state(storage: DatabaseStorage) -> tuple[int | None, int]:
    """The pointer and the generation, as the index-state row holds them."""
    index_state = storage._host.tables.index_state
    async with storage._host.engine.connect() as conn:
        row = (await conn.execute(select(index_state.c.current_gram_epoch, index_state.c.index_generation))).one()
    return row._tuple()


async def _row(storage: DatabaseStorage, path: str) -> Any:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry).where(entry.c.path == path))).one()


async def _per_epoch(storage: DatabaseStorage) -> dict[str, Counter[int]]:
    """Each epoch-scoped table's row count per epoch."""
    out: dict[str, Counter[int]] = {}
    async with storage._host.engine.connect() as conn:
        for table in storage._host.tables.epoch_scoped():
            rows = await conn.execute(select(table.c.epoch, func.count()).group_by(table.c.epoch))
            out[table.name] = Counter({int(epoch): int(count) for epoch, count in rows})
    return out


async def _table_counts(storage: DatabaseStorage) -> dict[str, int]:
    """Every table's row count."""
    async with storage._host.engine.connect() as conn:
        return {
            table.name: (await conn.execute(select(func.count()).select_from(table))).scalar_one()
            for table in storage._host.tables.metadata.sorted_tables
        }


async def _gram_epochs(storage: DatabaseStorage) -> list[tuple[int, int | None, bool]]:
    """``(epoch, base_epoch, published)`` for every built epoch, ascending."""
    epochs = storage._host.tables.gram_epochs
    stmt = select(epochs.c.epoch, epochs.c.base_epoch, epochs.c.published_at.isnot(None)).order_by(epochs.c.epoch)
    async with storage._host.engine.connect() as conn:
        return [row._tuple() for row in await conn.execute(stmt)]


async def _chunk_ids(storage: DatabaseStorage, path: str) -> list[int]:
    chunks, entry = storage._host.tables.chunks, storage._host.tables.entry
    stmt = select(chunks.c.id).join(entry, entry.c.entry_id == chunks.c.entry_id).where(entry.c.path == path)
    async with storage._host.engine.connect() as conn:
        return sorted((await conn.execute(stmt)).scalars())


async def _all_chunk_ids(storage: DatabaseStorage) -> list[int]:
    chunks = storage._host.tables.chunks
    async with storage._host.engine.connect() as conn:
        return sorted((await conn.execute(select(chunks.c.id))).scalars())


async def _lexical_ids(storage: DatabaseStorage, path: str) -> dict[int, list[int]]:
    """The chunk ids ``vfs_lex_docs`` names for *path*, per epoch."""
    docs, entry = storage._host.tables.lex_docs, storage._host.tables.entry
    stmt = select(docs.c.epoch, docs.c.chunk_id).join(entry, entry.c.entry_id == docs.c.entry_id)
    out: dict[int, list[int]] = {}
    async with storage._host.engine.connect() as conn:
        for epoch, chunk_id in await conn.execute(stmt.where(entry.c.path == path).order_by(docs.c.chunk_id)):
            out.setdefault(epoch, []).append(chunk_id)
    return out


async def _stranded(storage: DatabaseStorage) -> int:
    """``vfs_lex_docs`` rows that name a chunk id no ``vfs_chunks`` row holds."""
    docs, chunks = storage._host.tables.lex_docs, storage._host.tables.chunks
    held = select(chunks.c.id).where(chunks.c.id == docs.c.chunk_id).exists()
    return await _scalar(storage, select(func.count()).select_from(docs).where(~held))


async def _set_lease(storage: DatabaseStorage, holder: str | None, heartbeat: int | None) -> None:
    index_state = storage._host.tables.index_state
    async with storage._host.engine.begin() as conn:
        await conn.execute(update(index_state).values(lease_holder=holder, lease_heartbeat=heartbeat))


async def _made_stale(storage: DatabaseStorage) -> None:
    """The running lease backdated past its TTL; the holder stays."""
    index_state = storage._host.tables.index_state
    stale = maintenance_module._now_ms() - maintenance_module.INDEX_LEASE_TTL_MS - 1_000
    async with storage._host.engine.begin() as conn:
        await conn.execute(update(index_state).values(lease_heartbeat=stale))


async def _claimed(storage: DatabaseStorage, token: str = "MINE") -> str:
    tables = storage._host.tables
    claim = await storage._execute_maintenance(
        "rebuild", lambda s: maintenance_module.claim_index_lease(s, tables, token)
    )
    assert claim.success, claim.errors
    return token


@contextmanager
def _recorded(storage: DatabaseStorage) -> Iterator[list[tuple[str, Any]]]:
    """Every ``(statement, parameters)`` the store issues inside the block, the statistics step's left out."""
    recorded: list[tuple[str, Any]] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if not is_statistics_statement(statement):
            recorded.append((statement, parameters))

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def _arrived(event: asyncio.Event, *running: asyncio.Task[Any]) -> None:
    """Wait for *event*; fail at once, never hang, when a task in *running* ends before it is set."""
    waiter = asyncio.ensure_future(event.wait())
    done, _pending = await asyncio.wait({waiter, *running}, return_when=asyncio.FIRST_COMPLETED)
    if waiter not in done:
        waiter.cancel()
        ended = [task.result() for task in running if task.done()]
        raise AssertionError(f"a run ended before it reached its seam: {ended}")


def _split_rows(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The paths each slice hands ``_assess_and_split``, one list a call."""
    real = indexing._assess_and_split
    seen: list[list[str]] = []

    def counting(rows: Any, *args: Any) -> Any:
        seen.append(sorted(row.path for row in rows))
        return real(rows, *args)

    monkeypatch.setattr(indexing, "_assess_and_split", counting)
    return seen


def _calls(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> list[Any]:
    """Each call's result of *module*'s async *name*, the real one run."""
    real = getattr(module, name)
    results: list[Any] = []

    async def counted(*args: Any, **kwargs: Any) -> Any:
        result = await real(*args, **kwargs)
        results.append(result)
        return result

    monkeypatch.setattr(module, name, counted)
    return results


def _only(result: Result) -> Any:
    [error] = result.errors
    return error


# ---------------------------------------------------------------------------
# The delta build
# ---------------------------------------------------------------------------


class TestDeltaBuild:
    async def test_a_delta_posts_only_the_dirty_under_its_base(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words", "/b.txt": "bravo body words"})
        assert (await storage.rebuild()).success is True
        before = await _per_epoch(storage)
        pointer, generation = await _state(storage)
        await _written(storage, {"/c.txt": "charlie fresh words", "/d.txt": "delta fresh words"})
        result = await storage.refresh()
        assert result.success is True, result.errors
        after = await _per_epoch(storage)
        [(base, none, base_done), (delta, base_of, delta_done)] = await _gram_epochs(storage)
        assert (none, base_done, delta_done) == (None, False, True)  # a full epoch is live by the pointer alone
        assert (base, base_of) == (pointer, pointer) and delta > base
        for name, counts in after.items():
            assert counts[base] == before[name][base], name
            assert set(counts) == {base, delta}, name
        assert after[storage._host.tables.posting_list.name][delta] > 0 and after["vfs_lex_docs"][delta] == 2
        assert await _state(storage) == (pointer, generation + 1)
        for path in ("/c.txt", "/d.txt"):
            row = await _row(storage, path)
            assert (row.encoded, row.indexed_epoch) == (True, delta), path
        await storage.close()

    async def test_a_quiet_refresh_mints_nothing(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        counts, state = await _table_counts(storage), await _state(storage)
        result = await storage.refresh()
        assert (result.success, result.ops) == (True, ("refresh",)), result.errors
        assert await _table_counts(storage) == counts
        assert await _state(storage) == state
        await storage.close()

    async def test_a_refresh_of_kept_entries_flips_and_bumps_only(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words", "/b.txt": "bravo body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/a.txt": "alpha body words"})
        assert (await storage.delete(path=Path("/b.txt"))).success is True
        assert (await storage.restore(path=Path("/b.txt"))).success is True
        epochs, per_epoch = await _gram_epochs(storage), await _per_epoch(storage)
        pointer, generation = await _state(storage)
        assert [(await _row(storage, path)).encoded for path in ("/a.txt", "/b.txt")] == [False, False]
        assert (await storage.refresh()).success is True
        assert await _gram_epochs(storage) == epochs
        assert await _per_epoch(storage) == per_epoch
        assert await _state(storage) == (pointer, generation + 1)
        assert [(await _row(storage, path)).encoded for path in ("/a.txt", "/b.txt")] == [True, True]
        await storage.close()

    async def test_a_rival_built_delta_collides_into_a_clean_conflict(self, tmp_path, monkeypatch) -> None:
        # The staged row is what a rival's commit leaves between this build's mint and its lexical insert.
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        monkeypatch.setattr(storage._host, "_retry_attempts", 2)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        await _written(storage, {"/b.txt": "bravo body words"})
        stats = storage._host.tables.lex_stats
        async with storage._host.engine.begin() as conn:
            await conn.execute(stats.insert().values(epoch=2, n_docs=0, avg_dl=0.0, k1=1.2, b=0.75))
        result = await storage.refresh()
        error = _only(result)
        assert (error.kind, error.retryable, result.ops) == (ErrorKind.conflict, True, ("refresh",))
        assert "unique" not in error.message.lower() and "constraint" not in error.message.lower()
        assert (await _row(storage, "/b.txt")).encoded is False
        await storage.close()

    async def test_a_delta_feed_cut_by_bytes_feeds_every_posted_chunk(self, tmp_path, monkeypatch) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        monkeypatch.setattr(lexical_store, "_TOKENIZE_BATCH_BYTES", 1)
        await _written(storage, {f"/n{n}.txt": f"november body {n}" for n in range(3)})
        assert (await storage.refresh()).success is True
        [*_, (delta, _base, _done)] = await _gram_epochs(storage)
        assert (await _per_epoch(storage))["vfs_lex_docs"][delta] == 3
        assert [sorted((await _lexical_ids(storage, f"/n{n}.txt"))[delta]) for n in range(3)] == [
            await _chunk_ids(storage, f"/n{n}.txt") for n in range(3)
        ]
        await storage.close()


class TestWritePath:
    async def test_write_statements_do_not_change_with_live_deltas(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/seed.txt": "seed body words"})
        assert (await storage.rebuild()).success is True

        async def counted(prefix: str) -> int:
            entries = [Entry(path=Path(f"/{prefix}/f{n:03}.txt"), content=f"body {n}") for n in range(500)]
            with _recorded(storage) as statements:
                assert (await storage.write(entries=entries, parents=True)).success is True
            return len(statements)

        none_live = await counted("w0")
        for n in range(3):
            await _written(storage, {f"/delta{n}.txt": f"delta body {n}"})
            assert (await storage.refresh()).success is True
        assert len([e for e in await _gram_epochs(storage) if e[1] is not None]) == 3
        assert await counted("w3") == none_live
        await storage.close()


# ---------------------------------------------------------------------------
# Rivals and the lease
# ---------------------------------------------------------------------------


class TestRivals:
    async def test_the_loser_of_the_publish_cas_reclaims_its_delta(self, tmp_path) -> None:
        url = _url(tmp_path)
        storage = DatabaseStorage(url=url)
        await _written(storage, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/n.txt": "november fresh words"})
        rival = DatabaseStorage(url=url)
        arrived, released = asyncio.Event(), asyncio.Event()

        async def first_waits() -> None:
            if not arrived.is_set():
                arrived.set()
                await released.wait()

        try:
            with installed("refresh:before-publish", first_waits):
                first = asyncio.create_task(storage.refresh())
                await _arrived(arrived, first)
                [*_, (lost_epoch, _base, published)] = await _gram_epochs(storage)
                assert published is False
                await _made_stale(storage)
                won = await rival.refresh()
                released.set()
                lost = await first
        finally:
            await rival.close()
        assert won.success is True, won.errors
        error = _only(lost)
        assert (error.kind, error.retryable) == (ErrorKind.conflict, False)
        assert error.message.endswith(f"refresh lost the index publish race for epoch {lost_epoch}"), error.message
        published_deltas = [epoch for epoch, base, done in await _gram_epochs(storage) if base is not None and done]
        assert len(published_deltas) == 1 and published_deltas[0] != lost_epoch
        assert (await _row(storage, "/n.txt")).indexed_epoch == published_deltas[0]
        assert all(counts[lost_epoch] == 0 for counts in (await _per_epoch(storage)).values())
        await storage.close()

    @pytest.mark.parametrize("case", ["publish", "chunk-pass"])
    async def test_a_refresh_whose_lease_was_taken_commits_nothing(self, tmp_path, monkeypatch, case) -> None:
        url = _url(tmp_path)
        storage = DatabaseStorage(url=url)
        await _written(storage, {"/e.txt": "echo body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/e.txt": "echo changed words"})
        if case == "chunk-pass":
            before = await _chunk_ids(storage, "/e.txt")
            row = await _row(storage, "/e.txt")
            real = indexing._carried_embeddings

            async def rival_claims(session: AsyncSession, *args: Any, **kwargs: Any) -> Any:
                index_state = storage._host.tables.index_state
                fresh = {"lease_holder": "RIVAL", "lease_heartbeat": maintenance_module._now_ms()}
                await session.execute(update(index_state).values(**fresh))
                return await real(session, *args, **kwargs)

            monkeypatch.setattr(indexing, "_carried_embeddings", rival_claims)
            lapsed = await storage.refresh()
            assert maintenance_module.lease_lost(lapsed), lapsed.errors
            assert await _chunk_ids(storage, "/e.txt") == before
            after = await _row(storage, "/e.txt")
            assert (after.indexed_epoch, after.chunked) == (row.indexed_epoch, row.chunked)
            assert (await _scalar(storage, select(storage._host.tables.index_state.c.lease_holder))) is None
            await storage.close()
            return
        rival = DatabaseStorage(url=url)
        arrived, released = [asyncio.Event(), asyncio.Event()], [asyncio.Event(), asyncio.Event()]

        async def hold() -> None:
            for arrival, release in zip(arrived, released, strict=True):
                if not arrival.is_set():
                    arrival.set()
                    await release.wait()
                    return

        try:
            with installed("refresh:before-publish", hold):
                first = asyncio.create_task(storage.refresh())
                await _arrived(arrived[0], first)
                generation = (await _state(storage))[1]
                await _written(storage, {"/e.txt": "echo rewritten again"})
                await _made_stale(storage)
                second = asyncio.create_task(rival.refresh())
                await _arrived(arrived[1], second)
                [*_, (b_epoch, _base, _done)] = await _gram_epochs(storage)
                released[0].set()
                lost = await first
                assert (await _state(storage))[1] == generation
                released[1].set()
                won = await second
        finally:
            await rival.close()
        error = _only(lost)
        assert error.message.endswith("refresh lost the index publish race for epoch 2"), error.message
        assert won.success is True, won.errors
        assert (await _row(storage, "/e.txt")).indexed_epoch == b_epoch
        assert set((await _lexical_ids(storage, "/e.txt"))[b_epoch]) == set(await _chunk_ids(storage, "/e.txt"))
        assert all(counts[2] == 0 for counts in (await _per_epoch(storage)).values())
        await storage.close()


class TestFold:
    async def test_the_full_rebuild_folds_every_delta(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        for n in range(3):
            await _written(storage, {f"/d{n}.txt": f"delta body {n}"})
            assert (await storage.refresh()).success is True
        _pointer, generation = await _state(storage)
        assert (await storage.rebuild()).success is True
        current, after = await _state(storage)
        assert after == generation + 1
        for name, counts in (await _per_epoch(storage)).items():
            assert set(counts) == {current}, name
        entry = storage._host.tables.entry
        covered = select(entry.c.indexed_epoch).where(entry.c.kind == "file", entry.c.deleted_at.is_(None))
        async with storage._host.engine.connect() as conn:
            assert set((await conn.execute(covered)).scalars()) == {current}
        await storage.close()


# ---------------------------------------------------------------------------
# Bounds: no statement grows with the dirty set or the live set
# ---------------------------------------------------------------------------

_IN_LIST = re.compile(r"([\w.]+) IN \(((?:\?, )*\?)\)")


def _over_budget(statements: list[tuple[str, Any]], budget: int, parameters: int) -> list[str]:
    """Statements past *parameters* binds, or carrying the live set with more than *budget* list members."""
    over: list[str] = []
    for statement, _params in statements:
        if statement.count("?") > parameters:
            over.append(statement)
            continue
        lists = [(column, members.count("?")) for column, members in _IN_LIST.findall(statement)]
        epochs = sum(size for column, size in lists if column.endswith(".epoch"))
        keys = max((size for column, size in lists if not column.endswith(".epoch")), default=0)
        if epochs and epochs + keys > budget:
            over.append(statement)
    return over


@pytest.mark.slow
class TestBounds:
    async def test_no_statement_grows_with_the_dirty_set_or_the_live_set(self, tmp_path, monkeypatch) -> None:
        budget = 64
        monkeypatch.setattr(EngineHost, "membership_budget", property(lambda self: budget))
        storage = await _store(tmp_path)
        body = "lantern {n} kestrel words over the river"
        entries = [Entry(path=Path(f"/bulk/f{n:05}.txt"), content=body.format(n=n)) for n in range(10_000)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        await _written(storage, {"/d/a.txt": "lantern visible", "/h/b.txt": "lantern hidden"})
        assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        assert (await storage.grant(path=Path("/d"), principal="bob", level="read", authority=SYSTEM)).success
        assert (await storage.rebuild()).success is True
        parameters = storage._host.parameter_budget

        async def readers() -> list[tuple[str, Any]]:
            with _recorded(storage) as statements:
                assert (await storage.grep(pattern="lantern")).success is True
                assert (await storage.search(query="lantern kestrel")).success is True
                assert (await storage.search(query="lantern kestrel", authority=BOB)).success is True
            return statements

        for live in (49, budget + 2):
            while len(await _gram_epochs(storage)) < live:
                n = len(await _gram_epochs(storage))
                await _written(storage, {f"/d/n{n:03}.txt": f"lantern delta {n}", f"/h/n{n:03}.txt": "lantern"})
                assert (await storage.refresh()).success is True
            assert _over_budget(await readers(), budget, parameters) == []
        rewritten = [Entry(path=entry.path, content=f"{entry.content} again") for entry in entries]
        assert (await storage.write(entries=rewritten, parents=True)).success is True
        with _recorded(storage) as statements:
            assert (await storage.refresh()).success is True
        assert _over_budget(statements, budget, parameters) == []
        assert len(await _gram_epochs(storage)) == budget + 3
        await storage.close()


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class TestRefusals:
    async def test_a_base_with_no_text_refuses_naming_rebuild(self, tmp_path) -> None:
        """Guards: the no-text test deleted, so a refresh publishes a delta on a base no length can weigh under.

        The schedule a deployment runs from day one: a rebuild of the empty store, then writes and refreshes.
        """
        storage = await _store(tmp_path)
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/one.txt": "heron one words"})
        counts, state, epochs = await _table_counts(storage), await _state(storage), await _gram_epochs(storage)
        error = _only(await storage.refresh())
        assert (error.kind, error.retryable) == (ErrorKind.unavailable, False)
        assert error.message.endswith(NO_TEXT), error.message
        assert await _table_counts(storage) == counts and await _state(storage) == state
        assert await _gram_epochs(storage) == epochs
        await _written(storage, {"/two.txt": "heron two words"})
        found = await storage.search(query="heron")
        assert found.success is True and sorted(str(o.path) for o in found.observations) == ["/one.txt", "/two.txt"]
        assert all(o.score is not None and math.isfinite(o.score) for o in found.observations)
        assert (await storage.rebuild()).success is True
        stats = storage._host.tables.lex_stats
        async with storage._host.engine.connect() as conn:
            assert (await conn.execute(select(func.max(stats.c.n_docs)))).scalar_one() > 0
        await _written(storage, {"/three.txt": "heron three words"})
        assert (await storage.refresh()).success is True
        assert (await _row(storage, "/three.txt")).indexed_epoch is not None
        await storage.close()

    async def test_a_base_of_wordless_documents_refreshes_and_scores(self, tmp_path) -> None:
        """Guards: the no-text test reading the mean length, which would refuse a base of counted documents.

        Documents with no term are counted with a mean length of 0; the refresh runs and the search answers.
        """
        storage = await _store(tmp_path, {"/dots.txt": "... --- ..."})
        assert (await storage.rebuild()).success is True
        stats = storage._host.tables.lex_stats
        async with storage._host.engine.connect() as conn:
            assert (await conn.execute(select(stats.c.n_docs, stats.c.avg_dl))).one()._tuple() == (1, 0.0)
        await _written(storage, {"/one.txt": "heron one words"})
        assert (await storage.refresh()).success is True
        found = await storage.search(query="heron")
        assert found.success is True and [str(o.path) for o in found.observations] == ["/one.txt"], found.errors
        assert all(o.score is not None and math.isfinite(o.score) for o in found.observations)
        await storage.close()

    async def test_no_base_and_drift_refuse_naming_rebuild(self, tmp_path, monkeypatch) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        pdf = Entry(path=Path("/p.pdf"), data=pdf_bytes(["The quokka smiles"]))
        assert (await storage.write(entries=[pdf])).success is True
        counts = await _table_counts(storage)
        refused = await storage.refresh()
        error = _only(refused)
        assert (error.kind, error.retryable) == (ErrorKind.unavailable, False)
        assert error.message.endswith(NO_BASE), error.message
        assert refused.ops == ("refresh",)
        assert await _table_counts(storage) == counts
        assert (await _row(storage, "/a.txt")).chunked is False
        assert (await _row(storage, "/p.pdf")).render_status == "pending"
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/b.txt": "bravo body words"})
        monkeypatch.setattr(indexing, "INDEX_FORMAT_VERSION", indexing.INDEX_FORMAT_VERSION + 1)
        counts, state = await _table_counts(storage), await _state(storage)
        error = _only(await storage.refresh())
        assert (error.kind, error.retryable) == (ErrorKind.unavailable, False)
        assert error.message.endswith(DRIFT), error.message
        assert await _table_counts(storage) == counts and await _state(storage) == state
        assert (await _row(storage, "/b.txt")).chunked is False
        await storage.close()

    async def test_a_chunk_generation_bump_refuses_until_a_rebuild(self, tmp_path, monkeypatch) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words", "/b.txt": "bravo body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/c.txt": "charlie fresh words"})
        ids = await _all_chunk_ids(storage)
        entry = storage._host.tables.entry
        stamps = select(entry.c.path, entry.c.indexed_epoch).order_by(entry.c.path)
        async with storage._host.engine.connect() as conn:
            before = [row._tuple() for row in await conn.execute(stamps)]
        state = await _state(storage)
        monkeypatch.setattr(indexing, "chunk_generation", lambda: chunk_generation() + "-bumped")
        error = _only(await storage.refresh())
        assert (error.kind, error.retryable) == (ErrorKind.unavailable, False)
        assert error.message.endswith(DRIFT), error.message
        assert await _all_chunk_ids(storage) == ids
        async with storage._host.engine.connect() as conn:
            assert [row._tuple() for row in await conn.execute(stamps)] == before
        assert await _state(storage) == state
        assert await _stranded(storage) == 0
        assert (await storage.rebuild()).success is True
        pointer, _generation = await _state(storage)
        for path in ("/a.txt", "/b.txt", "/c.txt"):
            assert (await _row(storage, path)).indexed_epoch == pointer, path
        await _written(storage, {"/d.txt": "delta fresh words"})
        assert (await storage.refresh()).success is True
        await storage.close()

    async def test_a_held_lease_refuses_with_conflict(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/b.txt": "bravo body words"})
        await _set_lease(storage, "RIVAL", maintenance_module._now_ms())
        counts = await _table_counts(storage)
        refused = await storage.refresh()
        error = _only(refused)
        assert (error.kind, error.retryable) == (ErrorKind.conflict, True)
        assert await _table_counts(storage) == counts
        assert (await _row(storage, "/b.txt")).chunked is False
        await storage.close()

    async def test_a_lease_lost_at_a_render_landing_answers_as_refresh(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/p.pdf"), data=pdf_bytes(["quokka"]))])).success

        async def rival_claims() -> None:
            await _made_stale(storage)
            await _claimed(storage, "RIVAL")

        with installed("refresh:before-render-land", rival_claims):
            lost = await storage.refresh()
        assert maintenance_module.lease_lost(lost) and lost.ops == ("refresh",), lost.errors
        assert (await _row(storage, "/p.pdf")).render_status == "pending"
        await storage.close()

    async def test_a_lease_lost_in_the_last_slice_stops_before_the_build(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/b.txt": "bravo body words"})
        state, epochs = await _state(storage), await _gram_epochs(storage)
        token, lost = await _claimed(storage), asyncio.Event()

        async def taken() -> None:
            lost.set()

        with installed("refresh:before-chunk-split", taken):
            result = await maintenance_module._refresh_phases(
                storage._maintenance("refresh"), storage._host.tables, lost, token, indexing.ChunkCursor()
            )
        assert maintenance_module.lease_lost(result), result.errors
        assert (await _row(storage, "/b.txt")).chunked is True  # the slice the flag rose in committed
        assert (await _gram_epochs(storage), await _state(storage)) == (epochs, state)
        await storage.close()

    async def test_bytes_replaced_mid_render_warn_to_run_refresh_again(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/q.pdf"), data=pdf_bytes(["quokka"]))])).success

        async def rival() -> None:
            assert (await storage.write(entries=[Entry(path=Path("/q.pdf"), data=pdf_bytes(["bilby"]))])).success

        with installed("refresh:before-render-land", rival):
            result = await storage.refresh()
        assert result.success is True and result.ops == ("refresh",), result.errors
        [warning] = [error for error in result.errors if error.kind == ErrorKind.unavailable]
        assert warning.retryable is True and "run refresh again" in warning.message, warning.message
        assert (result.model_extra or {})["rendering"]["unrendered"] == 1
        await storage.close()

    async def test_a_lost_lease_stops_the_refresh_before_its_publish(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/b.txt": "bravo body words"})
        state = await _state(storage)
        token, lost = await _claimed(storage), asyncio.Event()

        async def taken() -> None:
            await _set_lease(storage, "RIVAL", maintenance_module._now_ms())
            lost.set()

        with installed("refresh:before-publish", taken):
            result = await maintenance_module._refresh_phases(
                storage._maintenance("refresh"), storage._host.tables, lost, token, indexing.ChunkCursor()
            )
        assert maintenance_module.lease_lost(result), result.errors
        [*_, (built, base, published)] = await _gram_epochs(storage)
        assert (base, published) == (state[0], False)
        assert await _state(storage) == state
        async with storage._host.session_factory() as session:
            assert await indexing.live_set(session, storage._host.tables, base) == (base,)
        assert (await _row(storage, "/b.txt")).encoded is False
        await _set_lease(storage, None, None)
        assert (await storage.rebuild()).success is True
        assert all(counts[built] == 0 for counts in (await _per_epoch(storage)).values())
        await storage.close()


# ---------------------------------------------------------------------------
# Phases, seams and labels
# ---------------------------------------------------------------------------


class TestPhases:
    async def test_refresh_runs_only_the_dirty_bounded_phases(self, tmp_path, monkeypatch) -> None:
        storage = await _store(tmp_path, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/a.txt": "alpha new words", "/b.txt": "bravo body words"})
        reconverged = _calls(monkeypatch, maintenance_module, "_reconverge")
        signalled = _calls(monkeypatch, maintenance_module, "_signal_phase")
        named = {storage._host.tables.segments.name, storage._host.tables.edges.name}
        with _recorded(storage) as statements:
            assert (await storage.refresh()).success is True
        touched = [sql for sql, _ in statements if any(re.search(rf"\b{name}\b", sql) for name in named)]
        assert touched == []
        assert (reconverged, signalled) == ([], [])
        await storage.close()

    async def test_a_refresh_awaits_its_own_seams_and_answers_as_refresh(self, tmp_path) -> None:
        base = {"/a.txt": "alpha body words", "/b.txt": "bravo body words"}
        since = {"/a.txt": "alpha rewritten words", "/c.txt": "charlie fresh words"}
        stores = []
        for name in ("rebuilt", "refreshed"):
            storage = await _store(tmp_path / name, base)
            assert (await storage.rebuild()).success is True
            await _written(storage, since)
            stores.append(storage)
        awaited: Counter[str] = Counter()

        def counter(name: str) -> Any:
            async def count() -> None:
                awaited[name] += 1

            return count

        names = [f"{verb}:{suffix}" for verb in ("rebuild", "refresh") for suffix in SUFFIXES]
        with ExitStack() as stack:
            for name in names:
                stack.enter_context(installed(name, counter(name)))
            assert (await stores[0].rebuild()).success is True
            rebuilt = Counter({name.split(":")[1]: n for name, n in awaited.items()})
            awaited.clear()
            refreshed = await stores[1].refresh()
        assert refreshed.ops == ("refresh",) and refreshed.success, refreshed.errors
        assert not any(name.startswith("rebuild:") for name in awaited)
        assert awaited["refresh:before-reclaim"] == 0
        for suffix in SUFFIXES:
            if suffix != "before-reclaim":
                assert awaited[f"refresh:{suffix}"] == rebuilt[suffix], suffix
        assert (awaited["refresh:before-chunk-split"], awaited["refresh:before-publish"]) == (1, 1)
        clean = await stores[1].refresh()
        assert (clean.success, clean.ops) == (True, ("refresh",))
        await _set_lease(stores[1], "RIVAL", maintenance_module._now_ms())
        held = await stores[1].refresh()
        assert held.ops == ("refresh",)
        assert "an index run is already running (lease heartbeat" in _only(held).message
        empty = await _store(tmp_path / "empty", {"/z.txt": "zulu words"})
        assert (await empty.refresh()).ops == ("refresh",)
        for storage in (*stores, empty):
            await storage.close()

    async def test_a_refresh_fills_the_vectors_of_what_it_chunked(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path), embedder=HashEmbeddingProvider(8))
        await _written(storage, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/b.txt": "bravo body words"})
        embeds: list[int] = []

        async def counted() -> None:
            embeds.append(1)

        with installed("refresh:before-embed", counted):
            result = await storage.refresh()
        assert result.success is True and result.ops == ("refresh",), result.errors
        assert embeds and (result.model_extra or {})["embedding"]["unembedded"] == 0
        chunks = storage._host.tables.chunks
        missing = select(func.count()).select_from(chunks).where(chunks.c.embedding.is_(None))
        assert await _scalar(storage, missing) == 0
        await storage.close()

    async def test_the_posting_meta_sums_a_gram_across_the_live_set(self, tmp_path) -> None:
        storage = await _store(tmp_path, {"/a.txt": "needle alpha"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/b.txt": "needle bravo words"})
        assert (await storage.refresh()).success is True
        host, postings = storage._host, storage._host.tables.posting_list
        async with host.session_factory() as session:
            live = await indexing.live_set(session, host.tables, 1)
            meta_rows = select(postings.c.gram_key, postings.c.doc_count, postings.c.byte_size)
            rows = (await session.execute(meta_rows)).all()
            gram = next(row.gram_key for row in rows if sum(1 for other in rows if other.gram_key == row.gram_key) == 2)
            meta = await grep_module._posting_meta(session, host.tables, host.profile, 4, live, [gram])
        held = [row for row in rows if row.gram_key == gram]
        assert meta[gram] == (sum(row.doc_count for row in held), sum(row.byte_size for row in held))
        await storage.close()

    async def test_a_link_generation_bump_reads_only_what_writes_dirtied(self, tmp_path, monkeypatch) -> None:
        files = {f"/f{n:02}.md": f"note {n} links to [next](f{n + 1:02}.md)" for n in range(20)}
        storage = await _store(tmp_path, files)
        assert (await storage.rebuild()).success is True
        await _written(storage, {"/f00.md": "note zero rewritten", "/f01.md": "note one rewritten"})
        old = (await _row(storage, "/f05.md")).link_generation
        monkeypatch.setattr(indexing, "link_generation", lambda: "a-newer-extractor")
        probes = _calls(monkeypatch, maintenance_module, "stale_generation")
        slices = _calls(monkeypatch, maintenance_module, "chunk_dirty")
        split = _split_rows(monkeypatch)
        assert (await storage.refresh()).success is True
        assert (probes, len(slices), split) == ([], 1, [["/f00.md", "/f01.md"]])
        entry = storage._host.tables.entry
        generations = select(entry.c.path, entry.c.link_generation).where(entry.c.kind == "file")
        async with storage._host.engine.connect() as conn:
            stamped = [row._tuple() for row in await conn.execute(generations)]
        assert sorted(path for path, generation in stamped if generation == old) == sorted(files)[2:]
        split.clear()
        assert (await storage.rebuild()).success is True
        assert (len(probes), len(slices), split) == (1, 2, [sorted(files)[2:]])
        async with storage._host.engine.connect() as conn:
            assert {row.link_generation for row in await conn.execute(generations)} == {"a-newer-extractor"}
        await storage.close()

    async def test_a_renderer_generation_bump_renders_only_what_writes_dirtied(self, tmp_path, monkeypatch) -> None:
        url = _url(tmp_path)
        storage = DatabaseStorage(url=url)
        pdfs = [Entry(path=Path(f"/p{n}.pdf"), data=pdf_bytes([f"quokka page {n}"])) for n in range(5)]
        assert (await storage.write(entries=pdfs)).success is True
        assert (await storage.rebuild()).success is True
        old = (await _row(storage, "/p0.pdf")).render_generation
        assert (await storage.write(entries=[Entry(path=Path("/new.pdf"), data=pdf_bytes(["wombat"]))])).success
        await storage.close()
        content = storage._host.tables.content
        monkeypatch.setattr(PdfRenderer, "revision", PdfRenderer.revision + 1)
        storage = DatabaseStorage(url=url)
        async with storage._host.engine.connect() as conn:
            bodies = sorted((await conn.execute(select(content.c.entry_id, content.c.content))).all())
        pages = _calls(monkeypatch, maintenance_module, "select_render_dirty")
        assert (await storage.refresh()).success is True
        assert [row.name for page in pages for row in page] == ["new.pdf"]
        for n in range(5):
            assert (await _row(storage, f"/p{n}.pdf")).render_generation == old
        async with storage._host.engine.connect() as conn:
            now = sorted((await conn.execute(select(content.c.entry_id, content.c.content))).all())
        assert [body for body in now if body in bodies] == bodies
        pages.clear()
        assert (await storage.rebuild()).success is True
        assert sorted(row.name for page in pages for row in page) == [f"p{n}.pdf" for n in range(5)]
        newer = (await _row(storage, "/new.pdf")).render_generation
        assert newer != old
        for n in range(5):
            assert (await _row(storage, f"/p{n}.pdf")).render_generation == newer
        await storage.close()


# ---------------------------------------------------------------------------
# Build agreement: the delta's lexical feed is the posted set
# ---------------------------------------------------------------------------


class TestBuildAgreement:
    async def test_a_write_between_the_two_reads_leaves_grams_and_lexical_rows_together(
        self, tmp_path, monkeypatch
    ) -> None:
        # A twin store takes the same writes through the verbs with no rival: what each entry scores after.
        raced, twin = await _agreement_store(tmp_path / "raced"), await _agreement_store(tmp_path / "twin")
        before = await _chunk_ids(raced, "/b.txt")
        entry = raced._host.tables.entry
        real = indexing.build_lexical_delta

        async def rivals_first(session: AsyncSession, *args: Any, **kwargs: Any) -> Any:
            now = datetime.now(UTC)
            bump = {"version": entry.c.version + 1}
            overwrite = update(entry).where(entry.c.path == "/a.txt")
            await session.execute(overwrite.values(chunked=False, encoded=False, **bump))
            restore = update(entry).where(entry.c.path == "/b.txt")
            await session.execute(restore.values(deleted_at=None, trash_root_id=None, **bump))
            root = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            directory = update(entry).where(entry.c.path == "/d")
            await session.execute(directory.values(deleted_at=now, trash_root_id=root, **bump))
            member = update(entry).where(entry.c.path == "/d/x.txt")
            await session.execute(member.values(deleted_at=now, trash_root_id=root, encoded=False))
            return await real(session, *args, **kwargs)

        monkeypatch.setattr(indexing, "build_lexical_delta", rivals_first)
        assert (await raced.refresh()).success is True
        monkeypatch.undo()
        [*_, (delta, _base, _done)] = await _gram_epochs(raced)
        for path in ("/a.txt", "/b.txt", "/d/x.txt", "/n.txt"):
            grams, lexical = await _posted_in(raced, path, delta), delta in await _lexical_ids(raced, path)
            assert grams == lexical, path
            if (await _row(raced, path)).encoded:
                assert grams and lexical, path
        assert (await raced.refresh()).success is True
        await _written(twin, {"/a.txt": "apricot changed words"})
        assert (await twin.delete(path=Path("/d"))).success is True
        assert (await twin.restore(path=Path("/b.txt"))).success is True
        assert (await twin.refresh()).success is True
        for word in ("apricot", "bravo"):
            assert await _top_score(raced, word) == await _top_score(twin, word), word
        live = await _lexical_ids(raced, "/b.txt")
        assert sum(1 for ids in live.values() if set(ids) & set(before)) == 1
        assert (await raced.restore(path=Path("/d"))).success is True
        assert (await raced.refresh()).success is True
        assert [str(o.path) for o in (await raced.search(query="xylophone")).observations] == ["/d/x.txt"]
        assert [str(o.path) for o in (await raced.grep(pattern="xylophone")).observations] == ["/d/x.txt"]
        for storage in (raced, twin):
            await storage.close()


async def _agreement_store(tmp_path: Any) -> DatabaseStorage:
    """A base over four files, then /a.txt and /d/x.txt rewritten, /n.txt new and /b.txt in the trash."""
    files = {"/a.txt": "apricot body words", "/b.txt": "bravo body words", "/d/x.txt": "xylophone body"}
    storage = await _store(tmp_path, files)
    assert (await storage.rebuild()).success is True
    await _written(storage, {"/a.txt": "apricot changed words", "/d/x.txt": "xylophone changed body"})
    await _written(storage, {"/n.txt": "november fresh words"})
    assert (await storage.delete(path=Path("/b.txt"))).success is True
    return storage


async def _top_score(storage: DatabaseStorage, query: str) -> float | None:
    found = await storage.search(query=query)
    assert found.success is True, found.errors
    return found.observations[0].score if found.observations else None


async def _posted_in(storage: DatabaseStorage, path: str, epoch: int) -> bool:
    """Whether *epoch*'s posting rows name *path*'s surrogate id."""
    surrogate = (await _row(storage, path)).id
    postings = storage._host.tables.posting_list
    async with storage._host.engine.connect() as conn:
        blobs = (await conn.execute(select(postings.c.postings).where(postings.c.epoch == epoch))).scalars()
        return any(surrogate in decode_postings(blob) for blob in blobs)


# ---------------------------------------------------------------------------
# Seeks: every read a refresh issues to find its work
# ---------------------------------------------------------------------------

_READS = {
    "render": lambda sql: sql.startswith("SELECT vfs_entries.id, vfs_entries.entry_id, vfs_entries.name"),
    "slice": lambda sql: "candidates" in sql,
    "posting": lambda sql: "indexed_epoch IS NULL OR" in sql,
    "kept": lambda sql: "indexed_epoch >=" in sql,
}
_INDEX = {"render": "ix_vfs_entries_render_status", "slice": "ix_vfs_entries_index_pending"}
_INDEX["posting"] = _INDEX["kept"] = _INDEX["slice"]


async def _seek_store(tmp_path: Any, files: int, *, analyzed: bool) -> tuple[DatabaseStorage, str]:
    """A file store of *files* text files, a fifth too short to index and a tenth trashed after the full pass,
    50 bytes rows, five rows chunked and awaiting the publish and five written and not chunked."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    url = _url(tmp_path)
    storage = DatabaseStorage(url=url)
    bodies = {f"/t/f{n:05}.txt": ("ab" if n % 5 == 0 else f"text body {n} words") for n in range(files)}
    await _written(storage, bodies)
    blobs = [Entry(path=Path(f"/b/blob{n:02}.bin"), data=bytes([1, 2, n])) for n in range(50)]
    assert (await storage.write(entries=blobs, parents=True)).success is True
    assert (await storage.rebuild()).success is True
    for n in range(0, files, 10):
        assert (await storage.delete(path=Path(f"/t/f{n + 1:05}.txt"))).success is True
    await _written(storage, {f"/w/a{n}.txt": f"awaiting body {n}" for n in range(5)})

    async def stop() -> None:
        raise RuntimeError("stopped before the lexical build")

    with installed("refresh:before-lexical", stop), pytest.raises(RuntimeError):
        await storage.refresh()
    await _written(storage, {f"/w/n{n}.txt": f"new body {n}" for n in range(5)})
    await storage._host.settle_statistics()
    if analyzed:
        async with storage._host.engine.begin() as conn:
            await conn.execute(text("ANALYZE"))
    return storage, url.split("///", 1)[1]


async def _selection_reads(storage: DatabaseStorage) -> dict[str, tuple[str, Any]]:
    with _recorded(storage) as statements:
        assert (await storage.refresh()).success is True
    found: dict[str, tuple[str, Any]] = {}
    for name, matches in _READS.items():
        found[name] = next((sql, params) for sql, params in statements if matches(sql))
    return found


def _plan_and_steps(path: str, sql: str, params: Any) -> tuple[str, int]:
    connection = sqlite3.connect(path)
    try:
        plan = "\n".join(row[-1] for row in connection.execute("EXPLAIN QUERY PLAN " + sql, params))
        steps = [0]

        def step() -> int:
            steps[0] += 1
            return 0

        connection.set_progress_handler(step, 1)
        connection.execute(sql, params).fetchall()
        connection.set_progress_handler(None, 1)
        return plan, steps[0]
    finally:
        connection.close()


class TestSeeks:
    @pytest.mark.parametrize("state", ["raw", "analyzed"])
    async def test_the_selection_reads_seek_an_index(self, tmp_path, state) -> None:
        storage, path = await _seek_store(tmp_path, 1_000, analyzed=state == "analyzed")
        for name, (sql, params) in (await _selection_reads(storage)).items():
            plan, _steps = _plan_and_steps(path, sql, params)
            assert "SCAN vfs_entries" not in plan, (name, plan)
            [search] = [line for line in plan.splitlines() if line.startswith("SEARCH vfs_entries")]
            assert f"INDEX {_INDEX[name]} (" in search, (name, plan)
            constraint = search.split("(", 1)[1]
            assert "deleted_at=?" in constraint, (name, plan)
            if name in ("render", "slice"):
                assert "deleted_at=? AND id>?" in constraint, (name, plan)
        await storage.close()

    @pytest.mark.slow
    @pytest.mark.parametrize("state", ["raw", "analyzed"])
    async def test_the_selection_reads_do_not_grow_with_the_corpus(self, tmp_path, state) -> None:
        steps: dict[int, dict[str, int]] = {}
        for files in (1_000, 4_000):
            storage, path = await _seek_store(tmp_path / str(files), files, analyzed=state == "analyzed")
            reads = await _selection_reads(storage)
            steps[files] = {name: _plan_and_steps(path, sql, params)[1] for name, (sql, params) in reads.items()}
            await storage.close()
        for name in _READS:
            assert steps[4_000][name] <= 1.5 * steps[1_000][name], (name, steps)

    @pytest.mark.parametrize("case", ["landing", "writes", "outside"])
    async def test_a_row_the_seek_cannot_see_is_found(self, tmp_path, monkeypatch, case) -> None:
        url = _url(tmp_path)
        storage = DatabaseStorage(url=url)
        if case == "landing":
            pdfs = [Entry(path=Path(f"/p{n}.pdf"), data=pdf_bytes([f"quokka page {n} words"])) for n in range(5)]
            assert (await storage.write(entries=pdfs)).success is True
            assert (await storage.rebuild()).success is True
            assert all([(await _row(storage, f"/p{n}.pdf")).indexable for n in range(5)])
            await storage.close()
            monkeypatch.setattr(PdfRenderer, "revision", PdfRenderer.revision + 1)
            storage = DatabaseStorage(url=url)

            async def stop() -> None:
                raise RuntimeError("stopped before the first slice")

            with installed("rebuild:before-chunk-split", stop), pytest.raises(RuntimeError):
                await storage.rebuild()
            for n in range(5):
                row = await _row(storage, f"/p{n}.pdf")
                assert (row.chunked, row.encoded, row.indexable) == (False, False, False)
            split = _split_rows(monkeypatch)
            assert (await storage.refresh()).success is True
            assert split == [[f"/p{n}.pdf" for n in range(5)]]
            for n in range(5):
                row = await _row(storage, f"/p{n}.pdf")
                assert (row.chunked, row.indexable, row.encoded) == (True, True, True)
                assert row.chunk_source_hash == row.content_hash
        elif case == "writes":
            await _written(storage, {"/a.txt": "alpha body words", "/b.txt": "bravo body words"})
            assert (await storage.rebuild()).success is True
            await _written(storage, {"/a.txt": "alpha overwritten words", "/c.txt": "charlie words"})
            copied = await storage.copy(operations=[_pair("/b.txt", "/copy.txt")])
            assert copied.success is True, copied.errors
            pdf = Entry(path=Path("/p.pdf"), data=pdf_bytes(["quokka landing words"]))
            assert (await storage.write(entries=[pdf])).success is True
            seen: list[int] = []

            async def landed() -> None:
                seen.append(await _bad_rows(storage))

            with installed("rebuild:before-chunk-split", landed):
                assert (await storage.rebuild()).success is True
            assert await _bad_rows(storage) == 0 and seen == [0]
        else:
            await _written(storage, {"/a.txt": "alpha body words", "/o.txt": "outside body words"})
            assert (await storage.rebuild()).success is True
            entry = storage._host.tables.entry
            async with storage._host.engine.begin() as conn:
                outside = update(entry).where(entry.c.path == "/o.txt")
                await conn.execute(outside.values(encoded=True, chunked=False, indexable=True))
            await _written(storage, {"/b.txt": "bravo body words"})
            split = _split_rows(monkeypatch)
            assert (await storage.refresh()).success is True
            assert split == [["/b.txt"]]
            split.clear()
            assert (await storage.rebuild()).success is True
            assert split == [["/o.txt"]]
            row = await _row(storage, "/o.txt")
            assert (row.chunked, row.indexable, row.encoded) == (True, True, True)
            pointer, _generation = await _state(storage)
            assert pointer in await _lexical_ids(storage, "/o.txt")
        await storage.close()


def _pair(src: str, dest: str) -> ResolvedPair:
    return ResolvedPair(src=Path(src), dest=Path(dest))


async def _bad_rows(storage: DatabaseStorage) -> int:
    """Live content rows NOT ``chunked`` yet ``encoded`` or ``indexable``: a state no vfs path may leave."""
    entry = storage._host.tables.entry
    bad = (~entry.c.chunked) & (entry.c.encoded | entry.c.indexable) & (entry.c.kind == "file")
    return await _scalar(storage, select(func.count()).select_from(entry).where(bad))


# ---------------------------------------------------------------------------
# Scale: a pass costs what was written since the last pass, never the corpus
# ---------------------------------------------------------------------------


REFUSED_MARK = "refusedmark"
WALKS = re.compile(r"\bSCAN (vfs_entries|vfs_chunks)\b")
CORPUS_COUNT = re.compile(r"^SELECT count\(\*\).*\bFROM (vfs_entries|vfs_chunks)\b", re.DOTALL)


class _Replayed(NamedTuple):
    """One statement of a pass replayed on the store as the pass found it: its text, steps, rows and plan."""

    shape: str
    steps: int
    rows: int
    plan: str


class _PassReplay(NamedTuple):
    """Every statement of one refresh, replayed in order, with the embedding extra and the chunk rows it wrote."""

    statements: list[_Replayed]
    embedding: dict[str, Any]
    new_chunks: int
    refused_chunks: int


def _refusing_provider() -> ScriptedProvider:
    """The hash vectors, refusing for its input any text that carries :data:`REFUSED_MARK`."""
    return ScriptedProvider(
        8, real_input_tokens=1_000, token_of=lambda body: 5_000 if REFUSED_MARK in body else len(body.split())
    )


async def _seeded_store(tmp_path: Any, files: int, options: dict[str, Any]) -> DatabaseStorage:
    """*files* text files, a fifth too short to index, and 50 PDFs, rebuilt; then a tenth of the files trashed."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    storage = DatabaseStorage(url=_url(tmp_path), **options)
    bodies = {f"/c/f{n:05}.txt": ("ab" if n % 5 == 0 else f"corpus body {n} words") for n in range(files)}
    await _written(storage, bodies)
    pdfs = [Entry(path=Path(f"/b/p{n}.pdf"), data=pdf_bytes([f"quokka page {n}"])) for n in range(50)]
    assert (await storage.write(entries=pdfs, parents=True)).success is True
    await storage._host.settle_statistics()  # each step's own pass ends before the next, the same on every run
    assert (await storage.rebuild()).success is True
    await storage._host.settle_statistics()
    for n in range(3, files, 10):
        assert (await storage.delete(path=Path(f"/c/f{n:05}.txt"))).success is True
    await storage._host.settle_statistics()
    return storage


async def _changed(storage: DatabaseStorage, *, refused: bool) -> None:
    """The pass's changes, the same at every size: rewrites, overwrites, new files, a trash, a restore, a PDF,
    a linking markdown file, and with *refused* a text the provider refuses."""
    rewrites = {f"/c/f{n:05}.txt": f"rewritten body {n} words" for n in (1, 2, 4)}
    overwrites = {f"/c/f{n:05}.txt": f"corpus body {n} words" for n in (6, 7)}
    fresh = {f"/new/n{n}.txt": f"fresh body {n} words" for n in range(3)}
    linking = {"/m/note.md": "a note that links to [the fresh file](../new/n0.txt)\n"}
    await _written(storage, {**rewrites, **overwrites, **fresh, **linking})
    if refused:
        await _written(storage, {"/new/refused.txt": f"a body the provider {REFUSED_MARK} will not take"})
    assert (await storage.delete(path=Path("/c/f00008.txt"))).success is True
    assert (await storage.restore(path=Path("/c/f00013.txt"))).success is True
    assert (await storage.write(entries=[Entry(path=Path("/b/new.pdf"), data=pdf_bytes(["wombat"]))])).success


async def _pass_replay(tmp_path: Any, files: int, *, analyzed: bool, embedder: bool) -> _PassReplay:
    """Every statement one refresh issues over a store of *files* files, replayed in order on a copy of the store
    as it stood before the pass: each one's VM steps, the rows a read returns, and the plan of each write."""
    options: dict[str, Any] = {"embedder": _refusing_provider()} if embedder else {}
    storage = await _seeded_store(tmp_path, files, options)
    await _changed(storage, refused=embedder)
    await storage._host.settle_statistics()
    if analyzed:
        async with storage._host.engine.begin() as conn:
            await conn.execute(text("ANALYZE"))
    before = max(await _all_chunk_ids(storage))
    storage, result, statements = await _refresh_replayed(storage, tmp_path, options)
    chunks = storage._host.tables.chunks
    written = select(func.count()).select_from(chunks).where(chunks.c.id > before)
    new_chunks = await _scalar(storage, written)
    refused_chunks = await _scalar(storage, written.where(chunks.c.content.contains(REFUSED_MARK)))
    await storage.close()
    return _PassReplay(statements, (result.model_extra or {}).get("embedding", {}), new_chunks, refused_chunks)


async def _refresh_replayed(
    storage: DatabaseStorage, tmp_path: Any, options: dict[str, Any]
) -> tuple[DatabaseStorage, Result, list[_Replayed]]:
    """*storage* closed and copied, reopened, refreshed with every statement recorded, and each statement replayed
    in order on the copy; the reopened store is the caller's to close."""
    path = str(storage._host.engine.url.database)
    await storage.close()
    replay = shutil.copy(path, f"{path}.before")
    storage = DatabaseStorage(url=_url(tmp_path), **options)
    recorded: list[tuple[str, Any, bool]] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if not is_statistics_statement(statement):
            recorded.append((statement, parameters, executemany))

    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
    result = await storage.refresh()
    event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
    assert result.success is True, result.errors
    return storage, result, _replayed(replay, recorded)


async def _stale_replay(tmp_path: Any, files: int, monkeypatch: pytest.MonkeyPatch) -> list[_Replayed]:
    """A refresh with an embedder over a store whose planner statistics were taken at 20 files, replayed.

    The statistics are taken at 20 files by one ``ANALYZE``; vfs's analysis requests are then dropped while the
    store grows by *files* and is rebuilt, the state a young store is in before its next analysis pass; then
    three files are written.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {"embedder": HashEmbeddingProvider(8)}
    storage = DatabaseStorage(url=_url(tmp_path), **options)
    await _written(storage, {f"/s/f{n:02}.txt": f"seed body {n} words" for n in range(20)})
    assert (await storage.rebuild()).success is True
    await storage._host.settle_statistics()
    async with storage._host.engine.begin() as conn:
        await conn.execute(text("ANALYZE"))
    monkeypatch.setattr(EngineHost, "request_analysis", lambda _self: None)
    await _written(storage, {f"/c/f{n:05}.txt": f"corpus body {n} words" for n in range(files)})
    assert (await storage.rebuild()).success is True
    await _written(storage, {f"/new/n{n}.txt": f"fresh body {n} words" for n in range(3)})
    chunk_rows = len(await _all_chunk_ids(storage))
    storage, _result, statements = await _refresh_replayed(storage, tmp_path, options)
    connection = sqlite3.connect(str(storage._host.engine.url.database) + ".before")
    try:
        [(stat,)] = connection.execute("SELECT stat FROM sqlite_stat1 WHERE idx = 'ix_vfs_chunks_entry_id'")
    finally:
        connection.close()
    assert int(stat.split()[0]) < chunk_rows // 2, (stat, chunk_rows)  # the planner reads the small store's
    await storage.close()
    return statements


def _replayed(path: str, recorded: list[tuple[str, Any, bool]]) -> list[_Replayed]:
    """*recorded* run again in order on the store at *path*, each statement's steps counted one by one."""
    connection = sqlite3.connect(path, isolation_level=None)
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    out: list[_Replayed] = []
    try:
        for statement, parameters, many in recorded:
            if statement.lstrip().upper().startswith("BEGIN") and connection.in_transaction:
                connection.execute("COMMIT")  # the pass's own commits are the driver's, never a statement
            verb = statement.lstrip().split(None, 1)[0].upper()
            plan = ""
            if verb in ("UPDATE", "DELETE"):
                first = parameters[0] if many else parameters
                plan = " | ".join(row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {statement}", first))
            counted = [0]

            def step(counted: list[int] = counted) -> int:
                counted[0] += 1
                return 0

            connection.set_progress_handler(step, 1)
            run = connection.executemany(statement, parameters) if many else connection.execute(statement, parameters)
            rows = len(run.fetchall())
            connection.set_progress_handler(None, 1)
            out.append(_Replayed(re.sub(r"\((?:\?, )*\?\)", "(?)", statement), counted[0], rows, plan))
    finally:
        connection.close()
    return out


class TestScale:
    @pytest.mark.slow
    @pytest.mark.parametrize("analyzed", [False, True], ids=["raw", "analyzed"])
    @pytest.mark.parametrize("embedder", [False, True], ids=["plain", "embedder"])
    async def test_every_statement_of_a_refresh_is_flat_in_the_corpus(self, tmp_path, analyzed, embedder) -> None:
        """Guards: any statement of the pass walking a table its changes do not bound — the embed step's page and
        counts run without the pass's entries, the unrendered count, a selection read, a write keyed off its
        index — under either statistics state; and the pass issuing other statements on a larger store."""
        small = await _pass_replay(tmp_path / "small", 1_000, analyzed=analyzed, embedder=embedder)
        large = await _pass_replay(tmp_path / "large", 4_000, analyzed=analyzed, embedder=embedder)
        assert [one.shape for one in small.statements] == [one.shape for one in large.statements]
        pairs = list(zip(small.statements, large.statements, strict=True))
        reads = [(a, b) for a, b in pairs if a.shape.lstrip().upper().startswith("SELECT")]
        tables = re.compile(r"\bFROM (vfs_entries|vfs_chunks)\b")
        assert [(a.shape[:90], a.rows, b.rows) for a, b in reads if tables.search(a.shape) and a.rows != b.rows] == []
        whole = [a.shape[:90] for a, _ in reads if CORPUS_COUNT.search(a.shape) and "entry_id IN (" not in a.shape]
        assert whole == []  # a count the pass's own entries bound is the pass's; one over the table is not
        assert [(a.shape[:90], a.steps, b.steps) for a, b in pairs if b.steps > 1.5 * a.steps] == []
        assert [(one.shape[:90], one.plan) for one in large.statements if WALKS.search(one.plan)] == []
        if embedder:
            for replay in (small, large):
                assert replay.refused_chunks > 0
                expected = (replay.new_chunks - replay.refused_chunks, replay.refused_chunks, 0)
                embedding = replay.embedding
                assert (embedding["embedded"], embedding["refused"], embedding["unembedded"]) == expected, embedding

    @pytest.mark.slow
    async def test_every_statement_of_a_refresh_is_flat_on_stale_statistics(self, tmp_path, monkeypatch) -> None:
        """Guards, on statistics a planner took when the store was a fiftieth of its size: the embed step's read of
        the pass's rows ordered by id under a limit, which walks the chunk table's primary key from id 0; and the
        chunk slice's flip keyed on its ``(entry_id, version)`` pairs alone, which walks the entry table."""
        small = await _stale_replay(tmp_path / "small", 1_000, monkeypatch)
        large = await _stale_replay(tmp_path / "large", 4_000, monkeypatch)
        assert [one.shape for one in small] == [one.shape for one in large]
        grown = [(a.shape[:90], a.steps, b.steps) for a, b in zip(small, large, strict=True) if b.steps > 1.5 * a.steps]
        assert grown == [], grown
        assert any("vfs_chunks.embedding IS NULL" in one.shape for one in small)

    @pytest.mark.slow
    @pytest.mark.parametrize("store", ["mixed-analyzed", "text-own-statistics"])
    async def test_the_rebuilds_unrendered_count_seeks(self, tmp_path, store) -> None:
        """Guards: the rarity hint taken off the rebuild's unrendered count, so it walks the entry table on SQLite.

        Two stores: the all-statements corpus with its PDFs after an explicit ``ANALYZE``, and a store of text
        files alone under the statistics vfs's own step writes, a code tree or a notes mount, where the bare
        count walks.
        """
        steps: list[int] = []
        for files in (1_000, 4_000):
            if store == "mixed-analyzed":
                storage = await _seeded_store(tmp_path / str(files), files, {})
                await _changed(storage, refused=False)
                async with storage._host.engine.begin() as conn:
                    await conn.execute(text("ANALYZE"))
            else:
                bodies = {f"/c/f{n:05}.txt": f"body {n} words" for n in range(files)}
                storage = await _store(tmp_path / str(files), bodies)
                assert (await storage.rebuild()).success is True
                await storage._host.settle_statistics()
            with _recorded(storage) as statements:
                async with storage._host.session_factory() as session:
                    await render_module.count_unrendered(session, storage._host.tables, storage._host.profile)
            path = str(storage._host.engine.url.database)
            await storage.close()
            [counted] = _replayed(path, [(sql, params, False) for sql, params in statements if "count(*)" in sql])
            steps.append(counted.steps)
        assert steps[1] <= 1.5 * steps[0], steps


# ---------------------------------------------------------------------------
# The embed step a refresh runs
# ---------------------------------------------------------------------------

LEFT_FOR_REBUILD = "; the chunks this pass left without a vector are embedded by the next rebuild"
MODEL_CHANGED = "the embedding model changed since the last rebuild; run rebuild"


def _embedding(result: Result) -> dict[str, Any]:
    assert result.success is True, result.errors
    return (result.model_extra or {})["embedding"]


async def _chunk_rows(storage: DatabaseStorage, *paths: str) -> list[Any]:
    """``(id, embedding)`` of every chunk row of *paths*, by id."""
    chunks, entry = storage._host.tables.chunks, storage._host.tables.entry
    joined = chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
    stmt = select(chunks.c.id, chunks.c.embedding).select_from(joined).where(entry.c.path.in_(paths))
    async with storage._host.engine.connect() as conn:
        return [row._tuple() for row in await conn.execute(stmt.order_by(chunks.c.id))]


async def _stragglers(tmp_path: Any) -> None:
    storage = DatabaseStorage(url=_url(tmp_path), embedder=HashEmbeddingProvider(8))
    await _written(storage, {"/a.txt": "alpha body words", "/b.txt": "bravo body words"})
    assert _embedding(await storage.rebuild())["unembedded"] == 0
    [(straggler, _vector)] = await _chunk_rows(storage, "/a.txt")
    chunks = storage._host.tables.chunks
    async with storage._host.engine.begin() as conn:
        await conn.execute(update(chunks).where(chunks.c.id == straggler).values(embedding=None))
    await _written(storage, {"/c.txt": "charlie fresh words", "/d.txt": "delta fresh words"})
    with _recorded(storage) as statements:
        embedding = _embedding(await storage.refresh())
    fresh = await _chunk_rows(storage, "/c.txt", "/d.txt")
    assert (embedding["embedded"], embedding["unembedded"]) == (len(fresh), 0) and fresh, embedding
    assert all(vector is not None for _id, vector in fresh)
    assert await _chunk_rows(storage, "/a.txt") == [(straggler, None)]
    finding = [sql for sql, _params in statements if sql.startswith("SELECT")]
    nulls = [sql for sql in finding if "vfs_chunks.embedding IS NULL" in sql]  # the reads that find the work
    keyed = ("vfs_chunks.entry_id IN (", "vfs_chunks.id IN (")  # the pass's entries, then the rows they hold
    assert nulls and all(any(term in sql for term in keyed) for sql in nulls), nulls
    assert _embedding(await storage.rebuild())["embedded"] == 1
    assert [vector is not None for _id, vector in await _chunk_rows(storage, "/a.txt")] == [True]
    await storage.close()


async def _refused(tmp_path: Any) -> None:
    provider = _refusing_provider()
    storage = DatabaseStorage(url=_url(tmp_path), embedder=provider)
    await _written(storage, {"/a.txt": "alpha body words"})
    assert (await storage.rebuild()).success is True
    await _written(storage, {"/ok.txt": "okay fresh words", "/no.txt": f"a text the provider {REFUSED_MARK} refuses"})
    result = await storage.refresh()
    embedding = _embedding(result)
    ok, no = await _chunk_rows(storage, "/ok.txt"), await _chunk_rows(storage, "/no.txt")
    assert (embedding["embedded"], embedding["refused"], embedding["unembedded"]) == (len(ok), len(no), 0)
    [invalid] = [error for error in result.errors if error.kind is ErrorKind.invalid]
    assert str(invalid.path) == "/no.txt", invalid
    assert await _scalar(storage, select(func.count()).select_from(storage._host.tables.embed_refusals)) == 1
    calls = len(provider.calls)
    embedding = _embedding(await storage.refresh())
    assert (embedding["embedded"], embedding["refused"], embedding["unembedded"]) == (0, 0, 0)
    assert len(provider.calls) == calls
    await storage.close()


def _stored_vectors(storage: DatabaseStorage) -> list[tuple[int, bytes | None]]:
    """Every chunk row's stored vector bytes, by id, read raw: no provider's dimension decodes them."""
    connection = sqlite3.connect(str(storage._host.engine.url.database))
    try:
        return connection.execute("SELECT id, embedding FROM vfs_chunks ORDER BY id").fetchall()
    finally:
        connection.close()


async def _identity(tmp_path: Any) -> None:
    # The model changes at the same width: the mount refuses a new width at first touch, before any pass.
    storage = DatabaseStorage(url=_url(tmp_path), embedder=ScriptedProvider(8, model="first"))
    await _written(storage, {"/a.txt": "alpha body words", "/b.txt": "bravo body words"})
    assert (await storage.rebuild()).success is True
    await storage.close()
    second = ScriptedProvider(8, model="second")
    storage = DatabaseStorage(url=_url(tmp_path), embedder=second)
    stored = _stored_vectors(storage)
    await _written(storage, {"/c.txt": "charlie fresh words"})
    result = await storage.refresh()
    assert result.success is True, result.errors
    [warning] = result.errors
    assert (warning.kind, warning.severity, warning.retryable) == (ErrorKind.unavailable, Severity.warning, False)
    assert warning.message.endswith(MODEL_CHANGED), warning.message
    after = _stored_vectors(storage)
    assert [row for row in after if row[0] in dict(stored)] == stored and stored
    assert [vector for chunk_id, vector in after if chunk_id not in dict(stored)] == [None]
    assert second.batches == []
    migrated = _embedding(await storage.rebuild())
    assert (migrated["model"], migrated["embedded"], migrated["unembedded"]) == (second.model_id, 3, 0), migrated
    assert all(vector is not None for _id, vector in _stored_vectors(storage))
    await storage.close()


async def _outage(tmp_path: Any) -> None:
    provider = ScriptedProvider(8)
    storage = DatabaseStorage(url=_url(tmp_path), embedder=provider)
    await _written(storage, {"/a.txt": "alpha body words"})
    assert (await storage.rebuild()).success is True
    provider.fail_after = len(provider.batches)  # the next request fails, the refresh's first
    await _written(storage, {"/b.txt": "bravo fresh words", "/c.txt": "charlie fresh words"})
    result = await storage.refresh()
    assert result.success is True, result.errors
    [warning] = [error for error in result.errors if error.kind is ErrorKind.unavailable]
    assert (warning.severity, warning.retryable) == (Severity.warning, False)
    assert warning.message.endswith(LEFT_FOR_REBUILD) and "rebuild" in warning.message, warning.message
    calls = len(provider.calls)
    assert _embedding(await storage.refresh())["embedded"] == 0 and len(provider.calls) == calls
    provider.fail_after = None
    assert _embedding(await storage.rebuild())["embedded"] == len(await _chunk_rows(storage, "/b.txt", "/c.txt"))
    await _written(storage, {"/d.txt": "delta fresh words"})
    provider.fail_after = len(provider.batches)
    result = await storage.rebuild()
    [warning] = [error for error in result.errors if error.kind is ErrorKind.unavailable]
    assert warning.retryable is True and "embedding stopped after" in warning.message, warning.message
    assert not warning.message.endswith(LEFT_FOR_REBUILD)
    await storage.close()


class TestEmbed:
    @pytest.mark.parametrize(
        "scenario",
        [_stragglers, _refused, _identity, _outage],
        ids=["stragglers", "refused", "identity", "outage"],
    )
    async def test_a_refresh_embeds_only_what_its_pass_chunked(self, tmp_path, scenario) -> None:
        """Guards: the pass's entries dropped from its embed step, so it pages and counts the chunk table whole
        and embeds a straggler (``stragglers``); a refresh migrating a changed embedding space (``identity``);
        and a refresh's outage worded as the rebuild's, retryable and promising a next run (``outage``)."""
        await scenario(tmp_path)

    async def test_a_lost_lease_stops_the_embed_step_between_pages(self, tmp_path, monkeypatch) -> None:
        """Guards: a refresh's embed step reading its next page of ids after its lease was lost."""
        monkeypatch.setattr(maintenance_module, "EMBED_PAGE_ROWS", 1)
        storage = DatabaseStorage(url=_url(tmp_path), embedder=HashEmbeddingProvider(8))
        await _written(storage, {"/a.txt": "alpha body words"})
        assert (await storage.rebuild()).success is True
        await _written(storage, {f"/n{n}.txt": f"fresh body {n} words" for n in range(3)})
        token, lost = await _claimed(storage), asyncio.Event()
        context, cursor = storage._maintenance("refresh"), indexing.ChunkCursor()
        tables = storage._host.tables
        assert (await maintenance_module._refresh_phases(context, tables, lost, token, cursor)).success is True
        pages = _calls(monkeypatch, maintenance_module, "select_pass_page")

        async def taken() -> None:
            lost.set()

        passed = Result(ops=("refresh",))
        with installed("refresh:before-embed", taken):
            result = await maintenance_module._embedded(context, tables, lost, token, passed, cursor.resplit)
        assert maintenance_module.lease_lost(result), result.errors
        assert len(pages) == 1
        vectors = [vector for _id, vector in await _chunk_rows(storage, "/n0.txt", "/n1.txt", "/n2.txt")]
        assert sum(vector is not None for vector in vectors) == 1
        await storage.close()
