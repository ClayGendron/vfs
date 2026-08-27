"""The vector leg of glean against real sqlite rows (sqlite-vec): a hit only the vectors can
find, the fusion of both legs, the ladder's two rungs, the records a mount emits when the leg
cannot run, the tier inference, the query-vector cache, and the Rust referee's verdict."""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from tests.support.database_helpers import _url
from tests.support.embedding_doubles import ScriptedProvider
from vfs.embedding import Embedded, HashEmbeddingProvider, estimate_tokens
from vfs.models import Entry
from vfs.models.vector import cosine_topk, pack_vector
from vfs.paths import Path
from vfs.results import Severity, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import glean as glean_module
from vfs.storage.backends.database.dialects import POSTGRESQL
from vfs.storage.ranking import RRF, Convex, Ranker

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pytest


class PlantedProvider:
    """Vectors from a table: a document's vector is the query's when the table pairs them.

    Every text embeds to the hash vector unless *plants* names it; a
    planted text embeds to the vector of the key it is planted under, so
    a query can be made semantically identical to one document and
    unrelated to every other, whatever the words say.
    """

    def __init__(self, plants: dict[str, str], dimension: int = 32) -> None:
        self._hash = HashEmbeddingProvider(dimension)
        self._plants = plants
        self.dimension = dimension
        self.model_id = f"planted/fake@{dimension}"
        self.max_input_tokens = None
        self.max_batch_inputs = 64
        self.max_batch_tokens = None
        self.queries: list[str] = []

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def _vector(self, text: str) -> list[float]:
        return self._hash.embed_batch([self._plants.get(text, text)])[0]

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vector(text)

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        return Embedded([self._vector(text) for text in texts], len(texts))


FILES = {
    "/notes/one.md": "alpha bravo charlie\n",
    "/notes/two.md": "delta echo foxtrot\n",
    "/src/three.py": "golf hotel india\n",
    "/src/four.py": "juliet kilo lima\n",
}


async def _indexed(tmp_path: Any, files: dict[str, str] | None = None, **kwargs: Any) -> DatabaseStorage:
    storage = DatabaseStorage(url=_url(tmp_path), **kwargs)
    entries = [Entry(path=Path(path), content=body) for path, body in (files or FILES).items()]
    assert (await storage.write(entries=entries, parents=True)).success is True
    assert (await storage.reindex()).success is True
    return storage


def _paths(result: Any) -> list[str]:
    return [str(o.path) for o in result.observations]


class TestTheLeg:
    async def test_a_document_only_the_vectors_know_is_found(self, tmp_path: Any) -> None:
        # "meaning" shares no word with any file; its vector is two.md's.
        provider = PlantedProvider({"meaning": FILES["/notes/two.md"]})
        storage = await _indexed(tmp_path, embedder=provider)
        result = await storage.glean(query="meaning", limit=2)
        assert result.success is True, result.errors
        assert _paths(result)[0] == "/notes/two.md" and result.observations[0].score == 1.0
        legs = result.legs  # ty: ignore[unresolved-attribute]
        assert legs["lexical"] == {"hits": 0, "terms": []}
        assert legs["vector"]["tier"] == "native_exact" and legs["vector"]["model"] == provider.model_id
        assert legs["vector"]["hits"] == len(FILES) and legs["vector"]["depth"] == glean_module.VECTOR_DEPTH_FLOOR
        assert legs["fusion"] == "Convex({'vector': 0.5, 'lexical': 0.5})"
        [match] = result.observations[0].matches or []
        assert match.content == FILES["/notes/two.md"] and match.preview is not None
        assert result.errors == []
        await storage.close()

    async def test_both_legs_fuse_and_a_document_both_know_wins(self, tmp_path: Any) -> None:
        # "alpha" is a word of one.md; its vector is planted as four.py's.
        provider = PlantedProvider({"alpha": FILES["/src/four.py"]})
        storage = await _indexed(tmp_path, embedder=provider)
        result = await storage.glean(query="alpha", limit=4)
        paths = _paths(result)
        assert set(paths[:2]) == {"/notes/one.md", "/src/four.py"}
        lexical_only = await storage.glean(query="alpha", limit=4, globs=("notes/**",))
        assert _paths(lexical_only)[0] == "/notes/one.md"
        heavy = DatabaseStorage(
            url=_url(tmp_path), embedder=provider, ranker=Ranker(fusion=Convex({"vector": 0.9, "lexical": 0.1}))
        )
        assert _paths(await heavy.glean(query="alpha", limit=1)) == ["/src/four.py"]
        rank_only = DatabaseStorage(url=_url(tmp_path), embedder=provider, ranker=Ranker(fusion=RRF(k=1)))
        rrf = await rank_only.glean(query="alpha", limit=4)
        assert set(_paths(rrf)[:2]) == {"/notes/one.md", "/src/four.py"}
        assert rrf.legs["fusion"] == "RRF(k=1, weights={'vector': 1.0, 'lexical': 1.0})"  # ty: ignore[unresolved-attribute]
        await storage.close()
        await heavy.close()
        await rank_only.close()

    async def test_scores_stay_on_the_unit_scale_best_first(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, embedder=HashEmbeddingProvider(16))
        result = await storage.glean(query="alpha bravo", limit=4)
        scores = [o.score for o in result.observations]
        assert scores[0] == 1.0 and scores == sorted(scores, reverse=True) and scores[-1] == 0.0
        for row in result.observations:
            assert row.matches and row.matches[0].score == row.score
        await storage.close()

    async def test_the_narrow_rung_merges_per_chunk_lists_and_the_wide_rung_gates(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = PlantedProvider({"meaning": FILES["/src/four.py"]})
        storage = await _indexed(tmp_path, embedder=provider)
        narrow = await storage.glean(query="meaning", globs=("src/**",))
        assert _paths(narrow)[0] == "/src/four.py" and set(_paths(narrow)) == {"/src/four.py", "/src/three.py"}
        monkeypatch.setattr(glean_module, "SCOPE_ID_BUDGET", 0)
        wide = await storage.glean(query="meaning", globs=("src/**",))
        assert _paths(wide) == _paths(narrow)
        assert [o.score for o in wide.observations] == [o.score for o in narrow.observations]
        await storage.close()

    async def test_the_wide_rung_deepens_once_when_the_gate_starves_it(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        files = {f"/a/{i}.txt": f"alpha number {i}\n" for i in range(6)} | {"/b/target.txt": "bravo target\n"}
        storage = await _indexed(tmp_path, files, embedder=HashEmbeddingProvider(16))
        monkeypatch.setattr(glean_module, "SCOPE_ID_BUDGET", 0)
        monkeypatch.setattr(glean_module, "VECTOR_DEPTH_FLOOR", 2)
        monkeypatch.setattr(glean_module, "VECTOR_DEPTH_FACTOR", 1)
        monkeypatch.setattr(glean_module, "PROBE_DEEPEN", 8)
        # An exclusion is never pushed into SQL: the two nearest chunks to
        # "alpha number" are /a files the gate refuses, so the leg deepens.
        result = await storage.glean(query="alpha number", limit=1, globs_not=("a/**",))
        assert _paths(result) == ["/b/target.txt"]
        await storage.close()

    async def test_a_long_entry_carries_several_chunks_from_the_vector_leg(self, tmp_path: Any) -> None:
        sections = "".join(f"## Section {i}\n\nlantern words in section {i}, plain prose.\n\n" for i in range(120))
        provider = PlantedProvider(
            {"nothing": "## Section 7\n\nlantern words in section 7, plain prose.\n\n"}, dimension=64
        )
        storage = await _indexed(tmp_path, {"/big.md": sections, "/small.md": "quiet river stone\n"}, embedder=provider)
        [row, *_] = (await storage.glean(query="nothing", limit=1)).observations
        assert str(row.path) == "/big.md" and len(row.matches or []) == 3
        bounds = [(m.start, m.end) for m in row.matches or []]
        assert len(set(bounds)) == 3 and bounds == sorted(bounds)
        await storage.close()

    async def test_a_prelude_runs_before_the_statement(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = await _indexed(tmp_path, embedder=HashEmbeddingProvider(8))
        real = storage._vector_leg_for

        async def with_prelude(query: str, *, scoped: bool):
            leg, records = await real(query, scoped=scoped)
            assert leg is not None
            return leg._replace(prelude="SELECT 1"), records

        monkeypatch.setattr(storage, "_vector_leg_for", with_prelude)
        result = await storage.glean(query="alpha")
        assert result.success is True and result.legs["vector"]["hits"] == len(FILES)  # ty: ignore[unresolved-attribute]
        assert storage.ranker == Ranker()
        await storage.close()

    async def test_unembedded_and_trashed_rows_are_absent_from_the_leg(self, tmp_path: Any) -> None:
        provider = PlantedProvider({"meaning": FILES["/notes/two.md"]}, dimension=16)
        storage = await _indexed(tmp_path, embedder=provider)
        assert (await storage.delete(path=Path("/notes/two.md"))).success is True
        result = await storage.glean(query="meaning", limit=1)
        assert "/notes/two.md" not in _paths(result)
        assert (await storage.write(entries=[Entry(path=Path("/late.md"), content="late arrival\n")])).success
        late = await storage.glean(query="arrival", limit=2)
        assert _paths(late)[0] == "/late.md"  # the overlay serves it lexically; the vector leg has no row for it
        assert late.legs["vector"]["hits"] == len(FILES) - 1  # ty: ignore[unresolved-attribute]
        await storage.close()


class TestRecords:
    async def test_no_provider_is_an_info_record_and_a_lexical_answer(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.glean(query="alpha")
        [note] = result.errors
        assert note.severity == Severity.info and note.kind == VFSErrorKind.unavailable
        assert note.data == {"leg": "vector", "reason": "no_provider"}
        assert result.legs["vector"] is None and _paths(result) == ["/notes/one.md"]  # ty: ignore[unresolved-attribute]
        assert storage.traits()["glean_signals"] == "lexical"
        await storage.close()

    async def test_a_stale_space_is_a_conflict_record_and_a_lexical_answer(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, embedder=ScriptedProvider(8, model="one"))
        await storage.close()
        other = DatabaseStorage(url=_url(tmp_path), embedder=ScriptedProvider(8, model="two"))
        result = await other.glean(query="alpha")
        [note] = [e for e in result.errors if e.severity == Severity.warning]
        assert note.kind == VFSErrorKind.conflict and note.data is not None
        assert note.data["reason"] == "stale_identity" and note.data["stored"] == "scripted/one@8"
        assert result.legs["vector"] is None and _paths(result) == ["/notes/one.md"]  # ty: ignore[unresolved-attribute]
        assert other.traits()["glean_signals"] == "hybrid"
        await other.close()

    async def test_a_failing_query_embed_is_a_warning_and_a_lexical_answer(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path, embedder=HashEmbeddingProvider(8))
        broken = ScriptedProvider(8)
        broken.model_id = "hash/blake2b-tokens-bigrams@8"  # the same space: only the call fails

        async def failing(text: str) -> list[float]:
            raise RuntimeError("provider down")

        monkeypatch.setattr(broken, "embed_query", failing)
        storage._host.embedder = broken
        result = await storage.glean(query="alpha")
        [note] = result.errors
        assert note.severity == Severity.warning and note.retryable is True
        assert note.data == {"leg": "vector", "reason": "embed_failed", "provider": "hash/blake2b-tokens-bigrams@8"}
        assert _paths(result) == ["/notes/one.md"]
        await storage.close()

    async def test_the_query_vector_is_memoised_per_space(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = PlantedProvider({}, dimension=8)
        storage = await _indexed(tmp_path, embedder=provider)
        await storage.glean(query="alpha")
        await storage.glean(query="alpha")
        await storage.glean(query="bravo")
        assert provider.queries == ["alpha", "bravo"]
        monkeypatch.setattr(backend_module, "QUERY_VECTOR_CACHE", 1)
        await storage.glean(query="charlie")
        await storage.glean(query="alpha")  # evicted: embedded again
        assert provider.queries == ["alpha", "bravo", "charlie", "alpha"]
        await storage.close()


class TestTiers:
    async def test_sqlite_serves_exact_and_never_a_prelude(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, embedder=HashEmbeddingProvider(8))
        leg, records = await storage._vector_leg_for("alpha", scoped=False)
        assert leg is not None and records == []
        assert (leg.tier, leg.prelude, leg.model_id) == ("native_exact", None, "hash/blake2b-tokens-bigrams@8")
        await storage.close()

    async def test_the_ann_tier_is_inferred_from_configuration(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path, embedder=HashEmbeddingProvider(8))
        monkeypatch.setattr(storage._host, "_profile", POSTGRESQL)
        storage._host.pgvector_version = (0, 8, 1)
        leg, _ = await storage._vector_leg_for("alpha", scoped=False)
        assert leg is not None and (leg.tier, leg.prelude) == ("native_ann", backend_module.PGVECTOR_ITERATIVE_SCAN)
        scoped, _ = await storage._vector_leg_for("alpha", scoped=True)
        assert scoped is not None and scoped.tier == "native_ann"  # pgvector filters inside the index scan
        storage._host.pgvector_version = (0, 7, 4)
        older, _ = await storage._vector_leg_for("alpha", scoped=False)
        assert older is not None and (older.tier, older.prelude) == ("native_ann", None)
        monkeypatch.setattr(storage._host, "_profile", replace(POSTGRESQL, ann_honours_scope=False))
        dropped, _ = await storage._vector_leg_for("alpha", scoped=True)
        assert dropped is not None and dropped.tier == "native_exact"
        wide = DatabaseStorage(url=_url(tmp_path), embedder=HashEmbeddingProvider(4096))
        monkeypatch.setattr(wide._host, "_profile", POSTGRESQL)
        assert wide._ann_indexed() is False  # over pgvector's index cap: the column, an exact scan
        await storage.close()
        await wide.close()


class TestReferee:
    async def test_the_engines_order_is_the_rust_kernels_order(self, tmp_path: Any) -> None:
        """sqlite-vec's ranking is the kernel's: every answered chunk scores at least the kernel's
        tenth-best, in non-increasing kernel order — the exact referee, tolerant only of float32 ties."""
        files = {f"/d/{i:02}.txt": f"word{i} word{i % 3} shared token {i * 7 % 5}\n" for i in range(40)}
        provider = HashEmbeddingProvider(24)
        storage = await _indexed(tmp_path, files, embedder=provider)
        chunks, entry = storage._host.tables.chunks, storage._host.tables.entry
        async with storage._host.session_factory() as session:
            joined = select(chunks.c.id, entry.c.path, chunks.c.embedding).select_from(
                chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
            )
            rows = (await session.execute(joined.order_by(chunks.c.id))).all()
        ids = [row.id for row in rows]
        packed = b"".join(pack_vector(list(row.embedding)) for row in rows)
        query = await storage._embed_query(provider, "shared token 3")
        kernel = dict(cosine_topk(query, ids, packed, len(ids)))
        tenth = sorted(kernel.values(), reverse=True)[9]
        chunk_of = {row.path: row.id for row in rows}
        vector_only = DatabaseStorage(
            url=_url(tmp_path), embedder=provider, ranker=Ranker(fusion=Convex({"vector": 1.0}))
        )
        answer = await vector_only.glean(query="shared token 3", limit=10, globs=("d/**",))
        scores = [kernel[chunk_of[path]] for path in _paths(answer)]
        assert len(scores) == 10 and all(score >= tenth - 1e-6 for score in scores)
        assert all(earlier >= later - 1e-6 for earlier, later in pairwise(scores))
        await storage.close()
        await vector_only.close()
