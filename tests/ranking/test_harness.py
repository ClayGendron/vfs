"""The harness on its corpora: fixture shape, the BM25 baseline against the
recorded numbers (the 0.005 nDCG@10 gate), the determinism pin on the
sqlite and memory legs, the merge floors, the control arm, and ranx's
significance report.

Set ``VFS_RANKING_REBASELINE=1`` to rewrite ``baselines.json`` from the
current numbers and ``VFS_RANKING_REPIN=1`` to rewrite ``top10.json`` —
each is a deliberate act recorded in the landing note of the spec that
moved the number.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Final

import pytest
from sqlalchemy import func, select

from tests.ranking.controls import uninformative_prior
from tests.ranking.corpora import VFS_NATIVE, Corpus, beir, vfs_native
from tests.ranking.driver import Loaded, bm25_run, glean_run, load_corpus
from tests.ranking.embedders import HASH_DIMENSION, PIN_SENTENCE, POTION_MODEL, potion_embed
from tests.ranking.merge import halves, merged_glean_run, naive_score_sort, round_robin
from tests.ranking.metrics import METRICS, compare, evaluate
from tests.ranking.pins import MERGE_MOUNTS, assert_merge_top10_pin, assert_top10_pin
from tests.storage.database.test_signals import ENGINE_LEGS
from tests.support.server_schemas import server_storage
from vfs.base import VirtualFileSystem
from vfs.embedding import EmbeddingProvider, HashEmbeddingProvider, Model2VecEmbeddingProvider
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.ranking import Convex, InDegree, Log1p, PathShape, Ranker, Signal

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator

BASELINES: Final = VFS_NATIVE.parent / "baselines.json"
GATE: Final = 0.005
"""nDCG@10 may not fall more than this below the recorded baseline without an ADR note."""


def recorded() -> dict[str, dict[str, dict[str, float]]]:
    return json.loads(BASELINES.read_text(encoding="utf-8"))


def gate(corpus: str, arm: str, numbers: dict[str, float]) -> None:
    """Assert the arm's nDCG@10 holds the recorded baseline; rebaseline on request."""
    baselines = recorded()
    if os.environ.get("VFS_RANKING_REBASELINE"):
        baselines.setdefault(corpus, {})[arm] = {metric: round(value, 4) for metric, value in numbers.items()}
        BASELINES.write_text(json.dumps(baselines, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    baseline = baselines[corpus][arm]
    assert numbers["ndcg@10"] >= baseline["ndcg@10"] - GATE, (corpus, arm, numbers, baseline)


@pytest.fixture
async def sqlite(tmp_path: pathlib.Path) -> AsyncIterator[DatabaseStorage]:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite")
    yield storage
    await storage.close()


@pytest.fixture(scope="module")
def golden() -> Corpus:
    return vfs_native()


class TestFixture:
    def test_the_snapshot_is_the_declared_shape(self, golden: Corpus) -> None:
        assert len(golden.docs) == 200
        assert len(golden.queries) == 40
        assert set(golden.qrels) == set(golden.queries)

    def test_every_judgment_names_a_document_and_every_query_has_a_relevant_one(self, golden: Corpus) -> None:
        for qid, graded in golden.qrels.items():
            assert set(graded) <= set(golden.docs), qid
            assert all(0 <= grade <= 3 for grade in graded.values()), qid
            assert any(grade > 0 for grade in graded.values()), qid

    def test_beir_loader_skips_when_the_cache_is_absent(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        monkeypatch.setenv("VFS_RANKING_CACHE", str(tmp_path))
        with pytest.raises(pytest.skip.Exception):
            beir("scifact")


def assert_arms_agree(left: dict[str, float], right: dict[str, float]) -> None:
    """Two arms' metrics are the same numbers — the verb is the driver, any gap is a bug."""
    assert set(left) == set(right)
    for metric in left:
        assert left[metric] == pytest.approx(right[metric], abs=1e-9), metric


class TestBaseline:
    async def test_bm25_holds_the_gate_on_vfs_native(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        loaded = await load_corpus(sqlite, golden)
        run = await bm25_run(loaded)
        assert set(run) == set(golden.queries)
        assert all(run[qid] for qid in run)  # every golden query finds something
        gate("vfs_native", "bm25", evaluate(golden.qrels, run))

    async def test_glean_equals_the_bm25_baseline_on_vfs_native(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        loaded = await load_corpus(sqlite, golden)
        baseline = evaluate(golden.qrels, await bm25_run(loaded))
        arm = evaluate(golden.qrels, await glean_run(loaded))
        assert_arms_agree(arm, baseline)
        gate("vfs_native", "glean", arm)

    @pytest.mark.slow
    @pytest.mark.parametrize("name", ["scifact", "nfcorpus"])
    async def test_bm25_holds_the_gate_on_beir(self, sqlite: DatabaseStorage, name: str) -> None:
        corpus = beir(name)
        loaded = await load_corpus(sqlite, corpus)
        gate(name, "bm25", evaluate(corpus.qrels, await bm25_run(loaded)))

    @pytest.mark.slow
    @pytest.mark.parametrize("name", ["scifact", "nfcorpus"])
    async def test_glean_equals_the_bm25_baseline_on_beir(self, sqlite: DatabaseStorage, name: str) -> None:
        corpus = beir(name)
        loaded = await load_corpus(sqlite, corpus)
        baseline = evaluate(corpus.qrels, await bm25_run(loaded))
        arm = evaluate(corpus.qrels, await glean_run(loaded))
        assert_arms_agree(arm, baseline)
        gate(name, "glean", arm)


class TestDeterminism:
    async def test_the_ordered_top10_pin_holds_on_sqlite(self, sqlite: DatabaseStorage) -> None:
        await assert_top10_pin(sqlite)

    async def test_the_hybrid_ordered_top10_pin_holds_on_sqlite(self, tmp_path: pathlib.Path) -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/hybrid.sqlite", embedder=HashEmbeddingProvider())
        try:
            await assert_top10_pin(storage)
        finally:
            await storage.close()

    async def test_the_hybrid_ordered_top10_pin_holds_in_memory(self) -> None:
        storage = InMemoryStorage()  # the hashing embedder is its default
        try:
            await assert_top10_pin(storage)
        finally:
            await storage.close()

    async def test_the_merge_ordered_top10_pin_holds_on_two_sqlite_mounts(self, tmp_path: pathlib.Path) -> None:
        stores = [DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/{i}.sqlite") for i in range(2)]
        try:
            await assert_merge_top10_pin(*stores)
        finally:
            for store in stores:
                await store.close()

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_the_merge_ordered_top10_pin_holds_on_a_sqlite_and_server_mix(
        self, tmp_path: pathlib.Path, env_var: str
    ) -> None:
        local = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/local.sqlite")
        try:
            async with server_storage(env_var) as server:
                await assert_merge_top10_pin(local, server)
        finally:
            await local.close()


def _embedders() -> dict[str, EmbeddingProvider]:
    """The harness's embedders: the hash floor always, potion when its model is cached."""
    embedders: dict[str, EmbeddingProvider] = {"hash": HashEmbeddingProvider(HASH_DIMENSION)}
    if potion_embed(PIN_SENTENCE) is not None:
        embedders["potion"] = Model2VecEmbeddingProvider(model_name=POTION_MODEL)
    return embedders


class TestHybridArms:
    """The vector leg alone and the fused verb, per embedder, recorded beside the lexical baseline.

    The hashing embedder cannot rank by meaning, so its arms are floors
    the gate keeps honest, never targets; potion's arms are the
    semantic measurement and run only when the model is cached.
    """

    @pytest.mark.parametrize("name", ["hash", "potion"])
    async def test_vector_only_and_fused_are_recorded(self, tmp_path: pathlib.Path, golden: Corpus, name: str) -> None:
        embedders = _embedders()
        if name not in embedders:
            pytest.skip("potion-base-8M is not in the local Hub cache")
        embedder = embedders[name]
        arms = {
            "vector": Ranker(fusion=Convex({"vector": 1.0})),
            "fused": Ranker(fusion=Convex({"vector": 0.5, "lexical": 0.5})),
        }
        for arm, ranker in arms.items():
            storage = DatabaseStorage(
                url=f"sqlite+aiosqlite:///{tmp_path}/{name}_{arm}.sqlite", embedder=embedder, ranker=ranker
            )
            try:
                loaded = await load_corpus(storage, golden)
                numbers = evaluate(golden.qrels, await glean_run(loaded))
            finally:
                await storage.close()
            gate("vfs_native", f"{arm}/{name}", numbers)


class TestSignalArms:
    """The stored priors on the golden set, whose reference edges the reindex extracts from its markdown.

    The centrality arm reads the extracted ``links`` rows; the recorded
    arm is the one shape the measure-by-gamma table found neutral on this
    corpus (in-degree, log1p, half weight — every linear arm at that
    weight costs nDCG). The path-shape prior is recorded beside it.
    """

    async def test_the_centrality_prior_reads_the_extracted_links(self, tmp_path: pathlib.Path, golden: Corpus) -> None:
        signal = Signal("centrality", measure=InDegree(), smoothing=0.0, transform=Log1p(), weight=0.5)
        storage = DatabaseStorage(
            url=f"sqlite+aiosqlite:///{tmp_path}/centrality.sqlite", ranker=Ranker(signals=(signal,))
        )
        try:
            loaded = await load_corpus(storage, golden)
            edges = loaded.storage._host.tables.edges
            async with loaded.storage._host.session_factory() as session:
                stmt = select(func.count()).select_from(edges).where(edges.c.provenance == "extracted")
                extracted = (await session.execute(stmt)).scalar_one()
            numbers = evaluate(golden.qrels, await glean_run(loaded))
            answered = await loaded.storage.glean(query=next(iter(golden.queries.values())))
        finally:
            await storage.close()
        assert extracted > 100
        assert answered.model_extra is not None
        assert answered.model_extra["legs"]["signals"]["centrality"]["applied"] is True
        gate("vfs_native", "signals/centrality", numbers)

    async def test_the_path_shape_prior_is_recorded(self, tmp_path: pathlib.Path, golden: Corpus) -> None:
        ranker = Ranker(signals=(Signal("shape", measure=PathShape(), weight=0.15),))
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/shape.sqlite", ranker=ranker)
        try:
            loaded = await load_corpus(storage, golden)
            numbers = evaluate(golden.qrels, await glean_run(loaded))
            answered = await loaded.storage.glean(query=next(iter(golden.queries.values())))
        finally:
            await storage.close()
        assert answered.model_extra is not None and answered.model_extra["legs"]["signals"]["shape"]["applied"] is True
        gate("vfs_native", "signals/path_shape", numbers)


class TestArms:
    """The named floors and the control, recorded beside the baseline."""

    @pytest.fixture
    async def mounts(self, tmp_path: pathlib.Path, golden: Corpus) -> AsyncIterator[tuple[Loaded, Loaded]]:
        """The golden corpus split by top-level directory into two backends."""
        split = halves(golden)
        stores = [DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/{i}.sqlite") for i in range(len(split))]
        try:
            loaded = [await load_corpus(store, half) for store, half in zip(stores, split, strict=True)]
            yield loaded[0], loaded[1]
        finally:
            for store in stores:
                await store.close()

    async def test_the_merge_floors_are_recorded(self, mounts: tuple[Loaded, Loaded], golden: Corpus) -> None:
        runs = [await bm25_run(mount) for mount in mounts]
        for arm, merge in (("naive_score_sort", naive_score_sort), ("round_robin", round_robin)):
            gate("vfs_native", f"merge/{arm}", evaluate(golden.qrels, merge(runs, 50)))

    async def test_the_router_merge_beats_the_floors(self, mounts: tuple[Loaded, Loaded], golden: Corpus) -> None:
        """The verb over two mounts: the union reranked under the order law, within
        reach of the single-index arm and above both floors."""
        vfs = VirtualFileSystem()
        for loaded, mount in zip(mounts, MERGE_MOUNTS, strict=True):
            await vfs.add_mount(loaded.storage, mount, owned=False)
        numbers = evaluate(golden.qrels, await merged_glean_run(vfs, golden, MERGE_MOUNTS))
        gate("vfs_native", "merge/rerank", numbers)
        floors = recorded()["vfs_native"]
        assert numbers["ndcg@10"] > max(
            floors["merge/naive_score_sort"]["ndcg@10"], floors["merge/round_robin"]["ndcg@10"]
        )
        assert numbers["ndcg@10"] >= floors["glean"]["ndcg@10"] - 0.02

    async def test_the_uninformative_prior_control_is_recorded(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        run = await bm25_run(await load_corpus(sqlite, golden))
        gate("vfs_native", "control/uninformative_prior", evaluate(golden.qrels, uninformative_prior(run)))

    async def test_compare_reports_the_arms(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        run = await bm25_run(await load_corpus(sqlite, golden))
        report = compare(golden.qrels, {"bm25": run, "control": uninformative_prior(run)})
        table = report.to_dict()
        assert set(table["model_names"]) == {"bm25", "control"}
        assert set(table["metrics"]) == set(METRICS)
