"""The embed step of reindex against real sqlite rows: every chunk embedded and the
space stamped, the chunk-row cache (dedup and carry-over), migration on a model
change, resume after a provider failure, the timeout and ``Retry-After``, the lease
through a slow batch, the batcher's laws, and the identity refusals at first touch.
"""

from __future__ import annotations

import asyncio
from itertools import chain
from typing import Any

import pytest
from sqlalchemy import event, select, update

from tests.support.database_helpers import _url
from tests.support.embedding_doubles import RateLimitedError, ScriptedProvider
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.models.vector import NativeEmbeddingConfig
from vfs.paths import Path
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import embed as embed_module
from vfs.storage.backends.database.embed import EmbedRow, token_batched, truncated_for
from vfs.storage.backends.database.seams import installed

CORPUS = {
    "/a.txt": "alpha bravo charlie\n",
    "/b.txt": "delta echo foxtrot\n",
    "/c.txt": "golf hotel india\n",
    "/d.txt": "juliet kilo lima\n",
    "/e.txt": "mike november oscar\n",
}


def _long_body(tail: str) -> str:
    paragraphs = [f"paragraph {i} " + "word " * 120 + "\n\n" for i in range(8)]
    return "".join(paragraphs) + tail


async def _fresh(tmp_path: Any, files: dict[str, str] | None = None, **kwargs: Any) -> DatabaseStorage:
    storage = DatabaseStorage(url=_url(tmp_path), **kwargs)
    entries = [Entry(path=Path(path), content=body) for path, body in (files or CORPUS).items()]
    assert (await storage.write(entries=entries, parents=True)).success is True
    return storage


async def _vectors(storage: DatabaseStorage) -> dict[int, list[float] | None]:
    chunks = storage._host.tables.chunks
    async with storage._host.engine.connect() as conn:
        rows = await conn.execute(select(chunks.c.id, chunks.c.embedding).order_by(chunks.c.id))
        return {row.id: (None if row.embedding is None else list(row.embedding)) for row in rows}


async def _identity(storage: DatabaseStorage) -> tuple[str | None, int | None]:
    meta = storage._host.tables.meta
    async with storage._host.engine.connect() as conn:
        row = (await conn.execute(select(meta.c.embedding_model, meta.c.embedding_dimension))).one()
        return (row.embedding_model, row.embedding_dimension)


def _extra(result: Any) -> dict[str, Any]:
    return result.embedding


class TestStep:
    async def test_reindex_embeds_every_chunk_and_stamps_the_space(self, tmp_path: Any) -> None:
        provider = ScriptedProvider(max_batch_inputs=2)
        storage = await _fresh(tmp_path, embedder=provider)
        result = await storage.reindex()
        assert result.success is True, result.errors
        vectors = await _vectors(storage)
        assert len(vectors) == len(CORPUS) and all(v is not None and len(v) == 4 for v in vectors.values())
        assert all(abs(sum(x * x for x in v) - 1.0) < 1e-6 for v in vectors.values() if v is not None)
        assert _extra(result) == {
            "model": "scripted/fake@4",
            "embedded": 5,
            "cached": 0,
            "tokens": sum(provider.estimate_tokens(body) for body in CORPUS.values()),
            "requests": 3,
            "truncated": 0,
            "unembedded": 0,
        }
        assert await _identity(storage) == ("scripted/fake@4", 4)
        assert storage._host.embedding_identity == ("scripted/fake@4", 4)
        again = await storage.reindex()
        assert again.success is True and _extra(again)["embedded"] == 0 and _extra(again)["requests"] == 0
        await storage.close()

    async def test_no_provider_means_no_step_and_no_extra(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.reindex()
        assert result.success is True and result.model_extra == {}
        assert all(v is None for v in (await _vectors(storage)).values())
        assert await _identity(storage) == (None, None)
        assert storage.embedder is None
        await storage.close()

    async def test_identical_text_across_entries_embeds_once(self, tmp_path: Any) -> None:
        provider = ScriptedProvider()
        files = {"/x/LICENSE": "license text\n", "/y/LICENSE": "license text\n", "/z/LICENSE": "license text\n"}
        storage = await _fresh(tmp_path, files, embedder=provider)
        result = await storage.reindex()
        assert provider.batches == [["license text\n"]]
        assert (_extra(result)["embedded"], _extra(result)["cached"]) == (1, 2)
        vectors = await _vectors(storage)
        assert len({tuple(v) for v in vectors.values() if v is not None}) == 1
        await storage.close()

    async def test_a_later_page_borrows_a_vector_already_stored(self, tmp_path: Any, monkeypatch) -> None:
        monkeypatch.setattr(backend_module, "EMBED_PAGE_ROWS", 1)
        provider = ScriptedProvider()
        files = {"/x/LICENSE": "license text\n", "/y/LICENSE": "license text\n", "/other.txt": "other\n"}
        storage = await _fresh(tmp_path, files, embedder=provider)
        result = await storage.reindex()
        assert sorted(chain.from_iterable(provider.batches)) == ["license text\n", "other\n"]
        assert (_extra(result)["embedded"], _extra(result)["cached"]) == (2, 1)
        await storage.close()

    async def test_a_hash_embedded_in_an_earlier_run_is_lent_from_the_table(self, tmp_path: Any) -> None:
        provider = ScriptedProvider()
        storage = await _fresh(tmp_path, {"/x/LICENSE": "license text\n"}, embedder=provider)
        assert (await storage.reindex()).success is True
        assert (
            await storage.write(entries=[Entry(path=Path("/y/LICENSE"), content="license text\n")], parents=True)
        ).success
        result = await storage.reindex()
        assert (_extra(result)["embedded"], _extra(result)["cached"], _extra(result)["requests"]) == (0, 1, 0)
        assert len({tuple(v) for v in (await _vectors(storage)).values() if v is not None}) == 1
        await storage.close()

    def test_the_zero_vector_stays_zero_under_normalisation(self) -> None:
        assert embed_module.unit_vector([0.0, 0.0]) == [0.0, 0.0]
        assert embed_module.unit_vector([3.0, 4.0]) == [0.6, 0.8]

    async def test_a_failed_write_back_ends_the_step_with_its_failure(self, tmp_path: Any, monkeypatch) -> None:
        provider = ScriptedProvider()
        storage = await _fresh(tmp_path, embedder=provider)
        failure = Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.internal, message="write broke")])
        real = storage._execute_write

        async def failing(op: str, fn: Any) -> Result:
            partial_fn = getattr(fn, "func", None)
            if partial_fn is embed_module.write_vectors:
                return failure
            return await real(op, fn)

        monkeypatch.setattr(storage, "_execute_write", failing)
        result = await storage.reindex()
        assert result.success is False and result.errors[0].message == "write broke"
        await storage.close()

    async def test_a_failed_migration_ends_the_step_with_its_failure(self, tmp_path: Any, monkeypatch) -> None:
        storage = await _fresh(tmp_path, embedder=ScriptedProvider(model="one"))
        assert (await storage.reindex()).success is True
        await storage.close()
        other = DatabaseStorage(url=_url(tmp_path), embedder=ScriptedProvider(model="two"))
        failure = Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.internal, message="clear broke")])
        real = other._execute_write

        async def failing(op: str, fn: Any) -> Result:
            if "clear_embeddings" in getattr(getattr(fn, "__code__", None), "co_names", ()):
                return failure
            return await real(op, fn)

        monkeypatch.setattr(other, "_execute_write", failing)
        result = await other.reindex()
        assert result.success is False and result.errors[0].message == "clear broke"
        await other.close()

    async def test_a_resplit_carries_vectors_onto_unchanged_chunks(self, tmp_path: Any) -> None:
        provider = ScriptedProvider()
        storage = await _fresh(tmp_path, {"/doc.md": _long_body("first ending\n")}, embedder=provider)
        assert (await storage.reindex()).success is True
        before = await _vectors(storage)
        assert len(before) >= 3
        sent = sum(len(batch) for batch in provider.batches)
        assert sent == len(before)
        rewritten = Entry(path=Path("/doc.md"), content=_long_body("second ending\n"))
        assert (await storage.write(entries=[rewritten])).success is True
        result = await storage.reindex()
        after = await _vectors(storage)
        assert len(after) == len(before) and all(v is not None for v in after.values())
        resent = sum(len(batch) for batch in provider.batches) - sent
        assert resent == 1 and _extra(result)["embedded"] == 1  # only the changed tail chunk
        assert _extra(result)["cached"] == 0  # carry-over is not a provider-side cache hit
        await storage.close()

    async def test_a_model_change_migrates_the_whole_space(self, tmp_path: Any) -> None:
        first = ScriptedProvider(model="one")
        storage = await _fresh(tmp_path, embedder=first)
        assert (await storage.reindex()).success is True
        old = await _vectors(storage)
        await storage.close()
        second = ScriptedProvider(model="two")
        storage = DatabaseStorage(url=_url(tmp_path), embedder=second)
        assert (await storage.first_touch()).success is True
        assert storage._host.embedding_stale is True
        result = await storage.reindex()
        assert result.success is True, result.errors
        assert _extra(result)["embedded"] == len(CORPUS) and len(second.batches) >= 1
        assert await _identity(storage) == ("scripted/two@4", 4)
        assert storage._host.embedding_stale is False
        new = await _vectors(storage)
        assert set(new) == set(old) and all(v is not None for v in new.values())
        await storage.close()

    async def test_a_provider_failure_stops_the_step_and_the_next_run_resumes(self, tmp_path: Any) -> None:
        provider = ScriptedProvider(max_batch_inputs=2, fail_after=1)
        storage = await _fresh(tmp_path, embedder=provider, embed_concurrency=1)
        result = await storage.reindex()
        assert result.success is True
        [record] = result.errors
        assert record.kind == VFSErrorKind.unavailable and record.severity == Severity.warning
        assert record.retryable is True and record.data == {"provider": "scripted/fake@4"}
        assert "RuntimeError: provider down" in record.message
        assert (_extra(result)["embedded"], _extra(result)["unembedded"]) == (2, 3)
        assert await _identity(storage) == ("scripted/fake@4", 4)  # the first batch stamped
        provider.fail_after = None
        resumed = await storage.reindex()
        assert resumed.success is True and resumed.errors == []
        assert (_extra(resumed)["embedded"], _extra(resumed)["unembedded"]) == (3, 0)
        assert all(v is not None for v in (await _vectors(storage)).values())
        await storage.close()

    async def test_a_failure_before_any_vector_leaves_the_space_unstamped(self, tmp_path: Any) -> None:
        provider = ScriptedProvider(fail_after=0)
        storage = await _fresh(tmp_path, embedder=provider)
        result = await storage.reindex()
        assert result.success is True and _extra(result)["unembedded"] == len(CORPUS)
        assert await _identity(storage) == (None, None)
        assert storage._host.embedding_identity is None
        await storage.close()

    async def test_a_timeout_is_classified_and_the_rest_stays_null(self, tmp_path: Any) -> None:
        provider = ScriptedProvider(delay=0.5)
        storage = await _fresh(tmp_path, embedder=provider, embed_timeout_seconds=0.01)
        result = await storage.reindex()
        assert result.success is True
        [record] = result.errors
        assert record.kind == VFSErrorKind.unavailable and "TimeoutError" in record.message
        assert _extra(result)["unembedded"] == len(CORPUS)
        await storage.close()

    async def test_retry_after_is_honoured_once(self, tmp_path: Any, monkeypatch) -> None:
        slept: list[float] = []
        real_sleep = asyncio.sleep

        async def recording(delay: float) -> None:
            slept.append(delay)
            await real_sleep(0)

        monkeypatch.setattr(embed_module.asyncio, "sleep", recording)
        provider = ScriptedProvider(max_batch_inputs=3, failures=[RateLimitedError({"retry-after-ms": "250"})])
        storage = await _fresh(tmp_path, embedder=provider, embed_concurrency=1)
        result = await storage.reindex()
        assert result.success is True and result.errors == []
        assert [delay for delay in slept if delay != backend_module.REINDEX_HEARTBEAT_SECONDS] == [0.25]
        assert _extra(result)["requests"] == 2 and _extra(result)["unembedded"] == 0
        await storage.close()

    async def test_a_refusal_that_keeps_refusing_ends_the_step(self, tmp_path: Any, monkeypatch) -> None:
        async def instant(delay: float) -> None:
            return None

        monkeypatch.setattr(embed_module.asyncio, "sleep", instant)
        provider = ScriptedProvider(fail_after=0, error=RateLimitedError({"retry-after": "1"}))
        storage = await _fresh(tmp_path, embedder=provider)
        result = await storage.reindex()
        assert "RateLimitedError" in result.errors[0].message
        await storage.close()

    def test_retry_after_is_read_only_from_an_http_shaped_refusal(self) -> None:
        assert embed_module._retry_after_seconds(RuntimeError("x")) is None
        assert embed_module._retry_after_seconds(RateLimitedError({"retry-after": "soon"})) is None
        assert embed_module._retry_after_seconds(RateLimitedError({})) is None
        assert embed_module._retry_after_seconds(RateLimitedError({"retry-after": "2.5"})) == 2.5

    async def test_a_lost_lease_stops_between_pages(self, tmp_path: Any, monkeypatch) -> None:
        monkeypatch.setattr(backend_module, "EMBED_PAGE_ROWS", 2)
        provider = ScriptedProvider(fail_after=0)
        storage = await _fresh(tmp_path, embedder=provider)
        assert (await storage.reindex()).success is True  # chunk rows exist, every vector NULL
        provider.fail_after = None
        lost = asyncio.Event()

        async def rival() -> None:
            lost.set()

        with installed("reindex:before-embed", rival):
            result = await storage._embed_step(storage._host.tables, lost)
        assert result.success is False and result.errors[0].kind == VFSErrorKind.conflict
        vectors = await _vectors(storage)
        assert sum(v is not None for v in vectors.values()) == 2  # the page in flight landed; nothing more
        await storage.close()

    async def test_the_beat_keeps_ticking_through_a_slow_batch(self, tmp_path: Any, monkeypatch) -> None:
        monkeypatch.setattr(backend_module, "REINDEX_HEARTBEAT_SECONDS", 0.02)
        provider = ScriptedProvider(delay=0.3)
        storage = await _fresh(tmp_path, {"/a.txt": "slow body\n"}, embedder=provider)
        beats = 0

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            nonlocal beats
            if (
                statement.startswith("UPDATE")
                and "reindex_heartbeat" in statement
                and "reindex_holder=" not in statement
            ):
                beats += 1

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        result = await storage.reindex()
        assert result.success is True and _extra(result)["unembedded"] == 0
        assert beats >= 5  # the loop stayed free while the provider's socket waited
        await storage.close()

    async def test_trashed_entries_are_not_embedded_nor_counted(self, tmp_path: Any) -> None:
        provider = ScriptedProvider()
        storage = await _fresh(tmp_path, embedder=provider)
        assert (await storage.reindex()).success is True
        chunks = storage._host.tables.chunks
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(chunks).values(embedding=None))
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        result = await storage.reindex()
        assert (_extra(result)["embedded"], _extra(result)["unembedded"]) == (len(CORPUS) - 1, 0)
        await storage.close()

    async def test_the_in_memory_default_is_the_hashing_provider(self) -> None:
        from vfs.storage.backends.memory import InMemoryStorage

        storage = InMemoryStorage()
        assert isinstance(storage.embedder, HashEmbeddingProvider)
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha beta")])).success is True
        result = await storage.reindex()
        assert _extra(result)["model"] == "hash/blake2b-tokens-bigrams@64" and _extra(result)["unembedded"] == 0
        await storage.close()

    async def test_the_phases_failure_short_circuits_the_step(self, tmp_path: Any, monkeypatch) -> None:
        provider = ScriptedProvider()
        storage = await _fresh(tmp_path, embedder=provider)

        async def broken(session, tables, profile, parameter_budget, membership_budget, executor, **_kw):
            from vfs.results import Result, ResultError

            return Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.internal, message="chunk broke")])

        monkeypatch.setattr(backend_module, "chunk_dirty", broken)
        result = await storage.reindex()
        assert result.success is False and provider.batches == []
        await storage.close()


class TestBatcher:
    @staticmethod
    def _rows(*sizes: int) -> list[EmbedRow]:
        return [EmbedRow(i, f"h{i}", "x" * size) for i, size in enumerate(sizes)]

    def test_inputs_cap_cuts_exactly(self) -> None:
        provider = ScriptedProvider(max_batch_inputs=2)
        batches = list(token_batched(self._rows(4, 4, 4, 4, 4), provider))
        assert [len(batch) for batch in batches] == [2, 2, 1]

    def test_tokens_cut_at_the_headroom_and_a_giant_rides_alone(self) -> None:
        # 120 tokens of cap plan to 100; rows of 40/40/40 tokens fill two per batch.
        provider = ScriptedProvider(max_batch_inputs=100, max_batch_tokens=120)
        batches = list(token_batched(self._rows(160, 160, 160, 4000, 160), provider))
        assert [[row.id for row in batch] for batch in batches] == [[0, 1], [2], [3], [4]]

    def test_empty_input_yields_nothing(self) -> None:
        assert list(token_batched([], ScriptedProvider())) == []

    def test_truncation_cuts_to_the_per_input_cap_by_the_estimator(self) -> None:
        provider = ScriptedProvider(max_input_tokens=10)
        assert truncated_for("short", provider) == "short"
        cut = truncated_for("y" * 400, provider)
        assert provider.estimate_tokens(cut) <= 10 and len(cut) == 40
        assert truncated_for("z" * 400, ScriptedProvider()) == "z" * 400  # no cap

    async def test_over_cap_inputs_are_truncated_and_counted(self, tmp_path: Any) -> None:
        provider = ScriptedProvider(max_input_tokens=2)
        storage = await _fresh(tmp_path, {"/a.txt": "a" * 40 + "\n", "/b.txt": "bb\n"}, embedder=provider)
        result = await storage.reindex()
        assert _extra(result)["truncated"] == 1
        sent = sorted(chain.from_iterable(provider.batches), key=len)
        assert [len(sent[0]), provider.estimate_tokens(sent[1])] == [3, 2] and 6 <= len(sent[1]) <= 8
        await storage.close()


class TestIdentity:
    def test_a_native_column_and_an_embedder_of_different_widths_refuse_at_construction(self, tmp_path: Any) -> None:
        with pytest.raises(ValueError, match="8-wide column"):
            DatabaseStorage(
                url=_url(tmp_path), embedder=ScriptedProvider(4), native_embedding=NativeEmbeddingConfig(dimension=8)
            )

    def test_the_step_knobs_are_validated(self, tmp_path: Any) -> None:
        with pytest.raises(ValueError, match="embed_concurrency"):
            DatabaseStorage(url=_url(tmp_path), embed_concurrency=0)
        with pytest.raises(ValueError, match="embed_timeout_seconds"):
            DatabaseStorage(url=_url(tmp_path), embed_timeout_seconds=0)

    async def test_a_stored_width_other_than_the_native_columns_refuses_at_first_touch(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path, embedder=ScriptedProvider(4))
        assert (await storage.reindex()).success is True
        await storage.close()
        wider = DatabaseStorage(url=_url(tmp_path), native_embedding=NativeEmbeddingConfig(dimension=8))
        result = await wider.first_touch()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid and "8 wide" in result.errors[0].message
        await wider.close()

    async def test_a_stored_model_mismatch_is_stale_not_refused(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path, embedder=ScriptedProvider(4, model="one"))
        assert (await storage.reindex()).success is True
        await storage.close()
        other = DatabaseStorage(url=_url(tmp_path), embedder=ScriptedProvider(4, model="two"))
        assert (await other.first_touch()).success is True
        assert other._host.embedding_identity == ("scripted/one@4", 4) and other._host.embedding_stale is True
        await other.close()
        none = DatabaseStorage(url=_url(tmp_path))
        assert (await none.first_touch()).success is True
        assert none._host.embedding_stale is False  # nothing configured, nothing to compare
        await none.close()
