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

from tests.ranking.controls import uninformative_prior
from tests.ranking.corpora import VFS_NATIVE, Corpus, beir, vfs_native
from tests.ranking.driver import Loaded, bm25_run, load_corpus
from tests.ranking.merge import naive_score_sort, round_robin
from tests.ranking.metrics import METRICS, compare, evaluate
from tests.ranking.pins import assert_top10_pin
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage

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


class TestBaseline:
    async def test_bm25_holds_the_gate_on_vfs_native(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        loaded = await load_corpus(sqlite, golden)
        run = await bm25_run(loaded)
        assert set(run) == set(golden.queries)
        assert all(run[qid] for qid in run)  # every golden query finds something
        gate("vfs_native", "bm25", evaluate(golden.qrels, run))

    @pytest.mark.slow
    @pytest.mark.parametrize("name", ["scifact", "nfcorpus"])
    async def test_bm25_holds_the_gate_on_beir(self, sqlite: DatabaseStorage, name: str) -> None:
        corpus = beir(name)
        loaded = await load_corpus(sqlite, corpus)
        gate(name, "bm25", evaluate(corpus.qrels, await bm25_run(loaded)))


class TestDeterminism:
    async def test_the_ordered_top10_pin_holds_on_sqlite(self, sqlite: DatabaseStorage) -> None:
        await assert_top10_pin(sqlite)

    async def test_the_ordered_top10_pin_holds_in_memory(self) -> None:
        storage = InMemoryStorage()
        try:
            await assert_top10_pin(storage)
        finally:
            await storage.close()


class TestArms:
    """The named floors and the control, recorded beside the baseline."""

    @pytest.fixture
    async def mounts(self, tmp_path: pathlib.Path, golden: Corpus) -> AsyncIterator[tuple[Loaded, Loaded]]:
        """The golden corpus split by top-level directory into two backends."""
        halves = [
            Corpus(f"{golden.name}/{prefix}", docs, {d: golden.paths[d] for d in docs}, golden.queries, golden.qrels)
            for prefix in ("docs", "context")
            if (docs := {d: t for d, t in golden.docs.items() if d.startswith(prefix + "/")})
        ]
        stores = [DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/{i}.sqlite") for i in range(len(halves))]
        try:
            loaded = [await load_corpus(store, half) for store, half in zip(stores, halves, strict=True)]
            yield loaded[0], loaded[1]
        finally:
            for store in stores:
                await store.close()

    async def test_the_merge_floors_are_recorded(self, mounts: tuple[Loaded, Loaded], golden: Corpus) -> None:
        runs = [await bm25_run(mount) for mount in mounts]
        for arm, merge in (("naive_score_sort", naive_score_sort), ("round_robin", round_robin)):
            gate("vfs_native", f"merge/{arm}", evaluate(golden.qrels, merge(runs, 50)))

    async def test_the_uninformative_prior_control_is_recorded(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        run = await bm25_run(await load_corpus(sqlite, golden))
        gate("vfs_native", "control/uninformative_prior", evaluate(golden.qrels, uninformative_prior(run)))

    async def test_compare_reports_the_arms(self, sqlite: DatabaseStorage, golden: Corpus) -> None:
        run = await bm25_run(await load_corpus(sqlite, golden))
        report = compare(golden.qrels, {"bm25": run, "control": uninformative_prior(run)})
        table = report.to_dict()
        assert set(table["model_names"]) == {"bm25", "control"}
        assert set(table["metrics"]) == set(METRICS)
