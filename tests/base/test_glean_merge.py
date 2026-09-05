"""The ranked verb through the router: one answering entry stands, several
merge through ``vfs.rerank`` — the fan-out depth, the order law, the
truncation record, the explanation, and the stage seam on the instance."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.base_doubles import CannedStorage, RecorderStorage
from vfs.base import VirtualFileSystem
from vfs.models import Match, Observation
from vfs.paths import Path
from vfs.rerank import FANOUT_CAP, BM25Rerank, Candidate
from vfs.results import Result, VFSErrorKind

STATS = {"n_docs": 50, "avg_dl": 3.0, "terms": {"lease": {"df": 5, "idf": 0.0}}}


def _row(path: str, score: float, text: str | None = None) -> Observation:
    matches = None if text is None else [Match(start=1, end=1, content=text, score=score)]
    return Observation(path=Path(path), score=score, matches=matches)


def _mount(rows: list[Observation], **extras: Any) -> CannedStorage:
    return CannedStorage({"glean": Result(ops=("glean",), observations=rows, **extras)})


def _limits(storage: RecorderStorage) -> list[int]:
    return [kwargs["limit"] for op, kwargs in storage.calls if op == "glean"]


def _legs(result: Result) -> dict[str, Any]:
    assert result.model_extra is not None
    return result.model_extra["legs"]


def _paths(result: Result) -> list[str]:
    return [str(path) for path in result.paths]


async def _two_mounts(
    rerankers: tuple[Any, ...] | None = None,
) -> tuple[VirtualFileSystem, CannedStorage, CannedStorage]:
    root = VirtualFileSystem() if rerankers is None else VirtualFileSystem(rerankers=rerankers)
    low = _mount(
        [_row("/l1", 0.2, "lease lease lease"), _row("/l2", 0.1, "nothing")], lexical_stats=STATS, legs={"m": 1}
    )
    high = _mount([_row("/h1", 0.9, "unrelated"), _row("/h2", 0.8, "a lease")], lexical_stats=STATS, legs={"m": 2})
    await root.add_mount(low, "/low")
    await root.add_mount(high, "/high")
    return root, low, high


# ---------------------------------------------------------------------------
# The merge
# ---------------------------------------------------------------------------


async def test_two_mounts_merge_by_the_query_not_by_their_own_scores() -> None:
    root, low, high = await _two_mounts()
    result = await root.glean("lease", limit=3)
    assert result.success is True
    assert result.paths == ("/low/l1", "/high/h1", "/high/h2")
    assert result.observations[0].score == 1.0
    legs = _legs(result)
    assert legs["merge"]["mounts"] == ["/low", "/high"] and legs["merge"]["depth"] == 9
    assert legs["mounts"] == {"/low": {"m": 1}, "/high": {"m": 2}}
    assert _limits(low) == [9] and _limits(high) == [9]


async def test_the_law_holds_through_the_router() -> None:
    # /high said h1 > h2; the rerank prefers h2. h1 rides up beside it and
    # both stay in their mount's order.
    root, _low, _high = await _two_mounts()
    result = await root.glean("lease", limit=4)
    paths = _paths(result)
    assert paths.index("/high/h1") < paths.index("/high/h2")
    assert paths.index("/low/l1") < paths.index("/low/l2")


async def test_one_answering_mount_stands_at_the_callers_limit() -> None:
    root = VirtualFileSystem()
    only = _mount([_row("/a", 0.9, "x"), _row("/b", 0.4, "y"), _row("/c", 0.1, "z")], legs={"lexical": {"hits": 3}})
    await root.add_mount(only, "/only")
    result = await root.glean("x", limit=2)
    assert result.paths == ("/only/a", "/only/b")
    assert [o.score for o in result.observations] == [0.9, 0.4]
    assert _legs(result) == {"lexical": {"hits": 3}}
    # The root memory entry answers glean too, so the fan-out asked for the depth.
    assert _limits(only) == [6]


async def test_a_scope_naming_one_mount_never_over_fetches_or_reranks() -> None:
    root, low, high = await _two_mounts()
    result = await root.glean("lease", paths=("/high",), limit=2)
    assert result.paths == ("/high/h1", "/high/h2")
    assert [o.score for o in result.observations] == [0.9, 0.8]
    assert _limits(high) == [2] and _limits(low) == []


async def test_observations_across_mounts_merge_the_same_way() -> None:
    root, low, high = await _two_mounts()
    held = [Observation(path=Path("/low/l1")), Observation(path=Path("/high/h2"))]
    result = await root.glean("lease", observations=held, limit=3)
    assert result.paths == ("/low/l1", "/high/h1", "/high/h2")
    assert _limits(low) == [9] and _limits(high) == [9]
    assert "merge" in _legs(result)


async def test_a_mount_at_the_cap_leaves_a_truncation_warning() -> None:
    root = VirtualFileSystem()
    full = _mount([_row(f"/r{i}", 1.0 - i / 300, "lease") for i in range(FANOUT_CAP)])
    other = _mount([_row("/one", 0.5, "lease")])
    await root.add_mount(full, "/full")
    await root.add_mount(other, "/other")
    result = await root.glean("lease", limit=100)
    assert result.success is True and len(result.observations) == 100
    [record] = [e for e in result.errors if e.kind is VFSErrorKind.truncated]
    assert record.data == {"mount": "/full", "cap": FANOUT_CAP}
    assert _limits(full) == [FANOUT_CAP]


async def test_a_dead_mount_among_answering_ones_is_loss_on_record() -> None:
    root = VirtualFileSystem()
    live = _mount([_row("/a", 0.5, "lease")])
    dead = CannedStorage({"glean": Result(ops=("glean",), errors=[])})
    dead.answers["glean"] = Result.model_validate(
        {"ops": ["glean"], "errors": [{"kind": "vfs.unavailable", "message": "down", "severity": "error"}]}
    )
    await root.add_mount(live, "/live")
    await root.add_mount(dead, "/dead")
    result = await root.glean("lease", limit=5)
    assert result.success is True and result.paths == ("/live/a",)
    assert [e.kind for e in result.warnings] == [VFSErrorKind.unavailable]


# ---------------------------------------------------------------------------
# The stage seam
# ---------------------------------------------------------------------------


class _Reverse:
    """A stage that scores by the mount's reverse rank — the law must still hold."""

    async def rerank(self, query: str, candidates: list[Candidate], *, limit: int) -> list[Candidate]:
        return [c._replace(score=float(c.rank)) for c in candidates]

    def __repr__(self) -> str:
        return "_Reverse()"


async def test_stages_are_configured_on_the_instance_and_the_law_binds_them() -> None:
    root, _low, _high = await _two_mounts(rerankers=(BM25Rerank(), _Reverse()))
    result = await root.glean("lease", limit=4)
    assert _legs(result)["merge"]["rerankers"] == ["BM25Rerank()", "_Reverse()"]
    paths = _paths(result)
    assert paths.index("/low/l1") < paths.index("/low/l2") and paths.index("/high/h1") < paths.index("/high/h2")


async def test_no_stages_means_the_mounts_scores_under_the_law() -> None:
    root, _low, _high = await _two_mounts(rerankers=())
    result = await root.glean("lease", limit=4)
    assert result.paths == ("/high/h1", "/high/h2", "/low/l1", "/low/l2")


async def test_a_stage_that_is_not_one_is_refused_at_construction() -> None:
    with pytest.raises(TypeError, match="rerankers must implement rerank"):
        VirtualFileSystem(rerankers=(object(),))  # ty: ignore[invalid-argument-type]


async def test_a_stage_that_changes_the_row_set_is_an_error() -> None:
    class Dropper:
        async def rerank(self, query: str, candidates: list[Candidate], *, limit: int) -> list[Candidate]:
            return candidates[:1]

    root, _low, _high = await _two_mounts(rerankers=(Dropper(),))
    with pytest.raises(ValueError, match="reorders, never retrieves"):
        await root.glean("lease", limit=4)
