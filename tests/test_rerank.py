"""The cross-mount merge in isolation: the statistics, the BM25 stage, the
order law, and ``merge_ranked`` over canned mount answers."""

from __future__ import annotations

import math
from typing import Any

import pytest

from vfs.models import Match, Observation
from vfs.models.lexical import idf, term_weight, tokenize
from vfs.paths import Path
from vfs.rerank import (
    FANOUT_CAP,
    BM25Rerank,
    Candidate,
    Statistics,
    fanout_depth,
    isotonic_nonincreasing,
    merge_ranked,
    order_law,
    region_texts,
)
from vfs.results import Result, VFSErrorKind


def _row(path: str, score: float, *texts: str, content_hash: str | None = None) -> Observation:
    matches = [Match(start=1, end=1, content=text, score=score) for text in texts]
    return Observation(path=Path(path), score=score, matches=matches or None, content_hash=content_hash)


def _answer(mount: str, rows: list[Observation], **extras: Any) -> tuple[Path, Result]:
    return Path(mount), Result(ops=("glean",), observations=rows, **extras).with_mount(mount)


def _stats(n_docs: int, avg_dl: float, **df: int) -> dict[str, object]:
    return {
        "n_docs": n_docs,
        "avg_dl": avg_dl,
        "terms": {term: {"df": count, "idf": 0.0} for term, count in df.items()},
    }


def _candidate(source: int, rank: int, score: float, path: str = "/x") -> Candidate:
    return Candidate(source, Path("/m"), rank, _row(path, score), score, (score,), Statistics(1, 1.0, {}, 1))


# ---------------------------------------------------------------------------
# The pieces
# ---------------------------------------------------------------------------


class TestPieces:
    def test_the_depth_is_three_times_the_limit_capped(self) -> None:
        assert fanout_depth(10) == 30
        assert fanout_depth(100) == FANOUT_CAP == 256

    def test_isotonic_repair_pools_violators_to_their_mean(self) -> None:
        assert isotonic_nonincreasing([3.0, 2.0, 1.0]) == [3.0, 2.0, 1.0]
        assert isotonic_nonincreasing([1.0, 3.0]) == [2.0, 2.0]
        assert isotonic_nonincreasing([5.0, 1.0, 3.0, 2.0]) == [5.0, 2.0, 2.0, 2.0]
        assert isotonic_nonincreasing([]) == []

    def test_region_texts_fall_back_to_the_preview(self) -> None:
        row = Observation(
            path=Path("/a"),
            matches=[
                Match(start=1, end=2, content="the body"),
                Match(start=1, end=2, content=None, preview="an excerpt", preview_start=1, preview_end=1),
                Match(start=1, end=1),
            ],
        )
        assert region_texts(row) == ["the body", "an excerpt", ""]
        assert region_texts(Observation(path=Path("/a"))) == []

    async def test_the_stage_scores_each_region_with_the_index_formula(self) -> None:
        stats = Statistics(n_docs=100, avg_dl=4.0, df={"lease": 10}, exported=2)
        row = _row("/a", 0.5, "lease lease token", "nothing here")
        [scored] = await BM25Rerank().rerank(
            "lease", [Candidate(0, Path("/m"), 0, row, 0.5, (0.5, 0.5), stats)], limit=5
        )
        expected = term_weight(2, 3, 4.0, idf(10, 100))
        assert scored.chunk_scores == (pytest.approx(expected), 0.0)
        assert scored.score == pytest.approx(expected)

    async def test_the_stage_folds_the_query_like_the_index(self) -> None:
        stats = Statistics(n_docs=10, avg_dl=2.0, df={}, exported=1)
        row = _row("/a", 0.5, "reindexHeartbeat")
        [scored] = await BM25Rerank().rerank(
            "Reindex_Heartbeat", [Candidate(0, Path("/m"), 0, row, 0.5, (0.5,), stats)], limit=5
        )
        assert scored.score > 0.0
        assert set(tokenize("reindexHeartbeat")) >= {"reindex", "heartbeat"}

    async def test_an_empty_region_scores_zero(self) -> None:
        stats = Statistics(n_docs=10, avg_dl=2.0, df={"lease": 1}, exported=1)
        row = _row("/a", 0.5, "", "   ", "lease")
        [scored] = await BM25Rerank().rerank(
            "lease", [Candidate(0, Path("/m"), 0, row, 0.5, (0.5, 0.5, 0.5), stats)], limit=5
        )
        assert scored.chunk_scores[:2] == (0.0, 0.0) and scored.chunk_scores[2] > 0.0

    def test_the_stage_is_a_value(self) -> None:
        assert BM25Rerank() == BM25Rerank() and hash(BM25Rerank()) == hash(BM25Rerank())
        assert repr(BM25Rerank()) == "BM25Rerank()"


# ---------------------------------------------------------------------------
# The order law
# ---------------------------------------------------------------------------


class TestOrderLaw:
    def test_each_mount_contributes_a_prefix_of_its_own_list(self) -> None:
        # Mount 0 scored 3 > 2 > 1; mount 1's own order is a, b, c but the
        # rerank likes b best: b cannot pass a, so a is pulled up beside it.
        candidates = [
            _candidate(0, 0, 3.0, "/m0/a"),
            _candidate(0, 1, 2.0, "/m0/b"),
            _candidate(0, 2, 1.0, "/m0/c"),
            _candidate(1, 0, 0.5, "/m1/a"),
            _candidate(1, 1, 2.5, "/m1/b"),
            _candidate(1, 2, 0.1, "/m1/c"),
        ]
        ordered = order_law(candidates)
        assert [str(c.row.path) for c in ordered] == ["/m0/a", "/m0/b", "/m1/a", "/m1/b", "/m0/c", "/m1/c"]
        assert [c.score for c in ordered[2:4]] == [1.5, 1.5]

    def test_ties_fall_to_dispatch_order_then_rank(self) -> None:
        ordered = order_law([_candidate(1, 0, 1.0), _candidate(0, 1, 1.0), _candidate(0, 0, 1.0)])
        assert [(c.source, c.rank) for c in ordered] == [(0, 0), (0, 1), (1, 0)]

    def test_the_law_never_reorders_within_a_mount(self) -> None:
        scores = [0.3, 0.9, 0.1, 0.7, 0.7, 0.2]
        ordered = order_law([_candidate(0, rank, score) for rank, score in enumerate(scores)])
        assert [c.rank for c in ordered] == list(range(len(scores)))


# ---------------------------------------------------------------------------
# The merge
# ---------------------------------------------------------------------------


class TestMergeRanked:
    async def test_one_answering_mount_stands_trimmed_with_its_explanation(self) -> None:
        rows = [_row("/a", 0.9, "x"), _row("/b", 0.4, "y"), _row("/c", 0.1, "z")]
        answers = [_answer("/m", rows, legs={"lexical": {"hits": 3}}), _answer("/n", [])]
        merged = await merge_ranked("x", answers, limit=2, depth=6, rerankers=(BM25Rerank(),))
        assert [str(o.path) for o in merged.observations] == ["/m/a", "/m/b"]
        assert [o.score for o in merged.observations] == [0.9, 0.4]
        assert merged.legs == {"lexical": {"hits": 3}} and merged.records == []

    async def test_nothing_answering_is_empty(self) -> None:
        merged = await merge_ranked("x", [_answer("/m", [])], limit=2, depth=6, rerankers=(BM25Rerank(),))
        assert merged.observations == [] and merged.legs == {}

    async def test_two_mounts_merge_on_one_scale_by_the_query_terms(self) -> None:
        # The mounts' own scores disagree with the text: the rerank decides.
        first = [_row("/near", 0.2, "nothing about it"), _row("/far", 0.1, "still nothing")]
        second = [_row("/hit", 0.9, "lease lease lease"), _row("/miss", 0.8, "unrelated words")]
        stats = _stats(50, 3.0, lease=5)
        answers = [_answer("/a", first, lexical_stats=stats), _answer("/b", second, lexical_stats=stats)]
        merged = await merge_ranked("lease", answers, limit=3, depth=9, rerankers=(BM25Rerank(),))
        # Zero-scored rows tie: dispatch order, then the mount's own rank.
        assert [str(o.path) for o in merged.observations] == ["/b/hit", "/a/near", "/a/far"]
        assert merged.observations[0].score == 1.0
        assert merged.observations[0].matches is not None and merged.observations[0].matches[0].score == 1.0
        assert merged.legs["merge"] == {
            "mounts": ["/a", "/b"],
            "depth": 9,
            "rerankers": ["BM25Rerank()"],
            "statistics": "corpus-wide",
            "candidates": 4,
            "duplicates": 0,
        }
        assert set(merged.legs["mounts"]) == {"/a", "/b"}

    async def test_the_law_pulls_a_mounts_first_row_above_its_stronger_second(self) -> None:
        # Clay's case: mount 2 said 1 > 2 > 3; the rerank prefers 2. Row 1
        # rides up beside row 2 and row 3 is the one bumped out.
        one = [_row("/1", 0.9, "lease token"), _row("/2", 0.8, "lease token"), _row("/3", 0.7, "lease token")]
        two = [_row("/1", 0.9, "nothing"), _row("/2", 0.8, "lease lease lease"), _row("/3", 0.7, "lease")]
        stats = _stats(50, 2.0, lease=5)
        answers = [_answer("/m1", one, lexical_stats=stats), _answer("/m2", two, lexical_stats=stats)]
        merged = await merge_ranked("lease", answers, limit=5, depth=15, rerankers=(BM25Rerank(),))
        paths = [str(o.path) for o in merged.observations]
        assert paths.index("/m2/1") < paths.index("/m2/2") and "/m2/3" not in paths
        assert [p for p in paths if p.startswith("/m1/")] == ["/m1/1", "/m1/2", "/m1/3"]
        scores = [o.score for o in merged.observations]
        assert scores == sorted(scores, reverse=True) and scores[0] == 1.0

    async def test_duplicates_across_mounts_keep_the_first_mounts_row(self) -> None:
        shared = _row("/same", 0.5, "lease", content_hash="h" * 64)
        answers = [
            _answer("/a", [shared], lexical_stats=_stats(5, 1.0)),
            _answer("/b", [shared], lexical_stats=_stats(5, 1.0)),
        ]
        merged = await merge_ranked("lease", answers, limit=5, depth=15, rerankers=(BM25Rerank(),))
        assert [str(o.path) for o in merged.observations] == ["/a/same"]
        assert merged.legs["merge"]["duplicates"] == 1

    async def test_statistics_sum_across_the_exporting_mounts(self) -> None:
        # df adds; avg_dl is length-weighted; a mount without an export contributes nothing.
        captured: list[Statistics] = []

        class Spy:
            async def rerank(self, query: str, candidates, *, limit: int):
                captured.extend(c.stats for c in candidates)
                return candidates

        answers = [
            _answer("/a", [_row("/x", 0.5, "t")], lexical_stats=_stats(10, 2.0, lease=1)),
            _answer("/b", [_row("/y", 0.5, "t")], lexical_stats=_stats(30, 6.0, lease=3, token=2)),
            _answer("/c", [_row("/z", 0.5, "t")]),
        ]
        await merge_ranked("lease token", answers, limit=5, depth=15, rerankers=(Spy(),))
        stats = captured[0]
        assert (stats.n_docs, stats.avg_dl, stats.df, stats.exported) == (40, 5.0, {"lease": 4, "token": 2}, 2)
        assert stats.idf("lease") == idf(4, 40) and stats.idf("absent") == idf(0, 40)

    async def test_without_any_export_the_union_supplies_the_statistics(self) -> None:
        answers = [_answer("/a", [_row("/x", 0.5, "lease token", "lease")]), _answer("/b", [_row("/y", 0.5, "token")])]
        merged = await merge_ranked("lease", answers, limit=5, depth=15, rerankers=(BM25Rerank(),))
        assert merged.legs["merge"]["statistics"] == "union"
        assert [str(o.path) for o in merged.observations] == ["/a/x", "/b/y"]

    async def test_no_stages_orders_by_the_mounts_own_scores_under_the_law(self) -> None:
        answers = [_answer("/a", [_row("/x", 0.2), _row("/y", 0.9)]), _answer("/b", [_row("/z", 0.5)])]
        merged = await merge_ranked("q", answers, limit=5, depth=15, rerankers=())
        assert [str(o.path) for o in merged.observations] == ["/a/x", "/a/y", "/b/z"]
        assert merged.observations[0].score == merged.observations[1].score

    async def test_a_stage_that_changes_the_row_set_is_refused(self) -> None:
        class Dropper:
            async def rerank(self, query: str, candidates, *, limit: int):
                return list(candidates)[:1]

        answers = [_answer("/a", [_row("/x", 0.5, "t")]), _answer("/b", [_row("/y", 0.5, "t")])]
        with pytest.raises(ValueError, match="reorders, never retrieves"):
            await merge_ranked("t", answers, limit=5, depth=15, rerankers=(Dropper(),))

    async def test_a_mount_that_fills_the_cap_earns_a_truncation_warning(self) -> None:
        full = [_row(f"/r{i}", 1.0 - i / 300, "lease") for i in range(FANOUT_CAP)]
        answers = [_answer("/a", full), _answer("/b", [_row("/one", 0.5, "lease")])]
        merged = await merge_ranked("lease", answers, limit=100, depth=FANOUT_CAP, rerankers=(BM25Rerank(),))
        assert len(merged.observations) == 100
        [record] = merged.records
        assert record.kind is VFSErrorKind.truncated and record.data == {"mount": "/a", "cap": FANOUT_CAP}
        below = await merge_ranked("lease", answers, limit=10, depth=30, rerankers=(BM25Rerank(),))
        assert below.records == []

    async def test_scores_land_on_the_unit_scale_with_the_best_chunk_carrying_the_entry(self) -> None:
        answers = [
            _answer("/a", [_row("/x", 0.5, "lease lease", "lease"), _row("/w", 0.4)]),
            _answer("/b", [_row("/y", 0.5, "lease")]),
        ]
        merged = await merge_ranked("lease", answers, limit=5, depth=15, rerankers=(BM25Rerank(),))
        top = merged.observations[0]
        assert str(top.path) == "/a/x" and top.score == 1.0
        assert top.matches is not None and top.matches[0].score == 1.0
        assert all(m.score is not None and 0.0 <= m.score <= 1.0 for m in top.matches)
        last = merged.observations[-1]
        assert last.score == 0.0 and last.matches is None
        assert all(not math.isnan(o.score or 0.0) for o in merged.observations)
