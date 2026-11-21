"""The ranked verb through the router: one answering entry stands, several
merge through ``vfs.rerank`` — the fan-out depth, the order law, the
truncation record, the explanation, and the stage seam on the instance."""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from tests.support.base_doubles import CannedStorage, RecorderStorage
from vfs import chain as chain_module
from vfs import deadline as deadline_module
from vfs.base import AsyncVirtualFileSystem
from vfs.chain import admit_rows_in_hand
from vfs.models import Match, Observation
from vfs.paths import Path
from vfs.rerank import FANOUT_CAP, BM25Rerank, Candidate
from vfs.results import ErrorKind, Result, ResultError
from vfs.results.kinds import Severity
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from vfs.deadline import Deadline

STATS = {"n_docs": 50, "avg_dl": 3.0, "terms": {"lease": {"df": 5, "idf": 0.0}}}


def _row(path: str, score: float, text: str | None = None) -> Observation:
    matches = None if text is None else [Match(start=1, end=1, content=text, score=score)]
    return Observation(path=Path(path), score=score, matches=matches)


def _mount(rows: list[Observation], **extras: Any) -> CannedStorage:
    return CannedStorage({"search": Result(ops=("search",), observations=rows, **extras)})


def _limits(storage: RecorderStorage) -> list[int]:
    return [kwargs["limit"] for op, kwargs in storage.calls if op == "search"]


def _sent(storage: RecorderStorage) -> list[list[str]]:
    return [[str(row.path) for row in kwargs["observations"]] for op, kwargs in storage.calls if op == "search"]


def _legs(result: Result) -> dict[str, Any]:
    assert result.model_extra is not None
    return result.model_extra["legs"]


def _paths(result: Result) -> list[str]:
    return [str(path) for path in result.paths]


async def _two_mounts(
    rerankers: tuple[Any, ...] | None = None,
) -> tuple[AsyncVirtualFileSystem, CannedStorage, CannedStorage]:
    root = AsyncVirtualFileSystem() if rerankers is None else AsyncVirtualFileSystem(rerankers=rerankers)
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
    result = await root.search("lease", limit=3)
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
    result = await root.search("lease", limit=4)
    paths = _paths(result)
    assert paths.index("/high/h1") < paths.index("/high/h2")
    assert paths.index("/low/l1") < paths.index("/low/l2")


async def test_one_answering_mount_stands_at_the_callers_limit() -> None:
    root = AsyncVirtualFileSystem()
    only = _mount([_row("/a", 0.9, "x"), _row("/b", 0.4, "y"), _row("/c", 0.1, "z")], legs={"lexical": {"hits": 3}})
    await root.add_mount(only, "/only")
    result = await root.search("x", limit=2)
    assert result.paths == ("/only/a", "/only/b")
    assert [o.score for o in result.observations] == [0.9, 0.4]
    assert _legs(result) == {"lexical": {"hits": 3}}
    # The root memory entry answers search too, so the fan-out asked for the depth.
    assert _limits(only) == [6]


async def test_a_scope_naming_one_mount_never_over_fetches_or_reranks() -> None:
    root, low, high = await _two_mounts()
    result = await root.search("lease", paths=("/high",), limit=2)
    assert result.paths == ("/high/h1", "/high/h2")
    assert [o.score for o in result.observations] == [0.9, 0.8]
    assert _limits(high) == [2] and _limits(low) == []


async def test_observations_across_mounts_merge_the_same_way() -> None:
    root, low, high = await _two_mounts()
    held = [Observation(path=Path("/low/l1")), Observation(path=Path("/high/h2"))]
    result = await root.search("lease", observations=held, limit=3)
    assert result.paths == ("/low/l1", "/high/h1", "/high/h2")
    assert _limits(low) == [9] and _limits(high) == [9]
    assert "merge" in _legs(result)


async def test_a_row_at_a_storage_root_in_hand_is_left_out_as_a_directory_is() -> None:
    # The row of a mount point reaches its storage as "/", and the trash view's head as "/.vfs/trash".
    root = AsyncVirtualFileSystem()
    assert (await root.write(path="/notes/a.md", content="lantern", parents=True)).success is True
    await root.add_mount(InMemoryStorage(name="child"), "/m")
    listed = await root.glob("/*")
    assert {str(row.path) for row in listed.observations} == {"/m", "/notes"}
    held = [*listed.observations, Observation(path=Path("/notes/a.md"))]
    result = await root.search("lantern", observations=held)
    assert result.success is True, result.error_message
    assert result.paths == ("/notes/a.md",)
    for alone in ("/", "/m", "/.vfs/trash"):
        answer = await root.search("lantern", observations=[Observation(path=Path(alone))])
        assert (answer.success, answer.paths, answer.errors) == (True, (), []), alone


async def test_a_mount_at_the_cap_leaves_a_truncation_warning() -> None:
    root = AsyncVirtualFileSystem()
    full = _mount([_row(f"/r{i}", 1.0 - i / 300, "lease") for i in range(FANOUT_CAP)])
    other = _mount([_row("/one", 0.5, "lease")])
    await root.add_mount(full, "/full")
    await root.add_mount(other, "/other")
    result = await root.search("lease", limit=100)
    assert result.success is True and len(result.observations) == 100
    [record] = [e for e in result.errors if e.kind is ErrorKind.truncated]
    assert record.data == {"mount": "/full", "cap": FANOUT_CAP}
    assert _limits(full) == [FANOUT_CAP]


async def test_a_dead_mount_among_answering_ones_is_loss_on_record() -> None:
    root = AsyncVirtualFileSystem()
    live = _mount([_row("/a", 0.5, "lease")])
    dead = CannedStorage({"search": Result(ops=("search",), errors=[])})
    dead.answers["search"] = Result.model_validate(
        {"ops": ["search"], "errors": [{"kind": "vfs.unavailable", "message": "down", "severity": "error"}]}
    )
    await root.add_mount(live, "/live")
    await root.add_mount(dead, "/dead")
    result = await root.search("lease", limit=5)
    assert result.success is True and result.paths == ("/live/a",)
    assert [e.kind for e in result.warnings] == [ErrorKind.unavailable]


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
    result = await root.search("lease", limit=4)
    assert _legs(result)["merge"]["rerankers"] == ["BM25Rerank()", "_Reverse()"]
    paths = _paths(result)
    assert paths.index("/low/l1") < paths.index("/low/l2") and paths.index("/high/h1") < paths.index("/high/h2")


async def test_no_stages_means_the_mounts_scores_under_the_law() -> None:
    root, _low, _high = await _two_mounts(rerankers=())
    result = await root.search("lease", limit=4)
    assert result.paths == ("/high/h1", "/high/h2", "/low/l1", "/low/l2")


async def test_a_stage_that_is_not_one_is_refused_at_construction() -> None:
    with pytest.raises(TypeError, match="rerankers must implement rerank"):
        AsyncVirtualFileSystem(rerankers=(object(),))  # ty: ignore[invalid-argument-type]


async def test_a_stage_that_changes_the_row_set_is_an_error() -> None:
    class Dropper:
        async def rerank(self, query: str, candidates: list[Candidate], *, limit: int) -> list[Candidate]:
            return candidates[:1]

    root, _low, _high = await _two_mounts(rerankers=(Dropper(),))
    with pytest.raises(ValueError, match="reorders, never retrieves"):
        await root.search("lease", limit=4)


# ---------------------------------------------------------------------------
# Rows in hand and the file filters
# ---------------------------------------------------------------------------

TRUNCATED = "Truncated: at the wall-time budget; send fewer rows, or fewer globs"
MD_PATHS = ["/data/b.md", "/data/deep/c.md", "/y.md"]
# Each filter set over the two real mounts, and the sorted paths it keeps.
FILTERED = (
    ({"ext": ("md",)}, MD_PATHS),
    ({"ext": (".MD",)}, MD_PATHS),
    ({"ext_not": ("md",)}, ["/data/a.txt", "/x.txt"]),
    ({"globs": ("*.md",)}, MD_PATHS),
    ({"globs": ("*.{md,rst}",)}, MD_PATHS),
    ({"globs": ("/data/**",)}, ["/data/a.txt", "/data/b.md", "/data/deep/c.md"]),
    ({"globs": ("deep/*",)}, []),
    ({"globs_not": ("/data/**",)}, ["/x.txt", "/y.md"]),
    ({"globs": ("/data/**",), "ext_not": ("txt",)}, ["/data/b.md", "/data/deep/c.md"]),
)
HELD = ("/low/l1.md", "/low/l2.txt", "/high/h1.txt", "/high/h2.md")


def _held(*paths: str) -> list[Observation]:
    return [Observation(path=Path(path)) for path in paths or HELD]


def _no_search_calls(*storages: RecorderStorage) -> bool:
    return all(op != "search" for storage in storages for op, _kwargs in storage.calls)


async def _memory(files: dict[str, str], *, deleted: tuple[str, ...] = ()) -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    for path, content in files.items():
        assert (await fs.write(path=path, content=content, parents=True)).success is True
    for path in deleted:
        assert (await fs.delete(path)).success is True
    return fs


@pytest_asyncio.fixture
async def two_real_mounts() -> AsyncIterator[tuple[AsyncVirtualFileSystem, list[Observation]]]:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(InMemoryStorage(), "/data")
    files = {
        "/x.txt": "alpha beta",
        "/y.md": "alpha gamma",
        "/data/a.txt": "alpha one",
        "/data/b.md": "alpha two alpha",
        "/data/deep/c.md": "alpha three",
    }
    for path, content in files.items():
        assert (await fs.write(path=path, content=content, parents=True)).success is True
    rows = list((await fs.glob("**/*", kind="file")).observations)
    assert len(rows) == 5
    yield fs, rows
    await fs.close()


@pytest_asyncio.fixture
async def four_ranked() -> AsyncIterator[tuple[AsyncVirtualFileSystem, list[Observation]]]:
    fs = await _memory(
        {
            "/top.txt": "alpha alpha alpha alpha",
            "/next.txt": "alpha alpha alpha",
            "/third.md": "alpha" + " filler" * 5,
            "/fourth.md": "alpha" + " filler" * 8,
        }
    )
    yield fs, list((await fs.glob("/*")).observations)
    await fs.close()


@pytest.mark.parametrize(("filters", "expected"), FILTERED)
async def test_a_file_filter_keeps_only_the_rows_it_admits(
    two_real_mounts: tuple[AsyncVirtualFileSystem, list[Observation]], filters: dict[str, Any], expected: list[str]
) -> None:
    fs, rows = two_real_mounts
    result = await fs.search("alpha", observations=rows, **filters)
    assert result.success is True and result.errors == []
    assert sorted(_paths(result)) == expected


@pytest.mark.parametrize("filters", [filters for filters, _expected in FILTERED] + [{"ext": ("rs",)}])
async def test_search_and_grep_keep_the_same_rows_in_hand(
    two_real_mounts: tuple[AsyncVirtualFileSystem, list[Observation]], filters: dict[str, Any]
) -> None:
    fs, rows = two_real_mounts
    searched = await fs.search("alpha", observations=rows, limit=50, **filters)
    grepped = await fs.grep("alpha", observations=rows, **filters)
    assert set(searched.paths) == set(grepped.paths)


async def test_the_filter_runs_before_the_limit(four_ranked: tuple[AsyncVirtualFileSystem, list[Observation]]) -> None:
    fs, rows = four_ranked
    assert (await fs.search("alpha", observations=rows, limit=2)).paths == ("/top.txt", "/next.txt")
    filtered = await fs.search("alpha", observations=rows, ext=("md",), limit=2)
    assert filtered.paths == ("/third.md", "/fourth.md")


async def test_a_filtered_call_answers_as_the_passing_rows_alone(
    four_ranked: tuple[AsyncVirtualFileSystem, list[Observation]],
) -> None:
    fs, rows = four_ranked
    filtered = await fs.search("alpha", observations=rows, ext=("md",), limit=2)
    alone = await fs.search("alpha", observations=[row for row in rows if str(row.path).endswith(".md")], limit=2)
    assert filtered.paths == alone.paths
    assert [row.score for row in filtered.observations] == [row.score for row in alone.observations]
    assert _legs(filtered) == _legs(alone)


async def test_rows_that_pass_in_one_mount_ask_that_mount_alone() -> None:
    root, low, high = await _two_mounts()
    result = await root.search("lease", observations=_held(), globs=("/low/**",), limit=3)
    assert _sent(low) == [["/l1.md", "/l2.txt"]] and _limits(low) == [3] and high.calls == []
    assert result.paths == ("/low/l1", "/low/l2")
    assert [row.score for row in result.observations] == [0.2, 0.1]
    assert _legs(result) == {"m": 1}


async def test_rows_that_pass_in_two_mounts_merge_at_the_depth() -> None:
    root, low, high = await _two_mounts()
    result = await root.search("lease", observations=_held(), ext=("md",), limit=3)
    assert _sent(low) == [["/l1.md"]] and _sent(high) == [["/h2.md"]]
    assert _limits(low) == [9] and _limits(high) == [9]
    assert "merge" in _legs(result)
    for storage in (low, high):
        [(_op, kwargs)] = storage.calls
        assert set(kwargs) == {"query", "limit", "observations", "columns"}


async def test_no_row_passing_calls_no_storage() -> None:
    root, low, high = await _two_mounts()
    result = await root.search("lease", observations=_held(), ext=("rs",))
    assert result.success is True and result.observations == [] and result.errors == []
    assert result.ops == ("search",)
    assert "legs" not in (result.model_extra or {})
    assert low.calls == [] and high.calls == []


async def test_the_filter_keeps_order_and_duplicates() -> None:
    root, low, _high = await _two_mounts()
    await root.search("lease", observations=_held("/low/l1.md", "/low/l2.txt", "/low/l1.md", "/low/a.md"), ext=("md",))
    assert _sent(low) == [["/l1.md", "/l1.md", "/a.md"]]


async def test_a_generator_of_rows_is_filtered_as_a_list() -> None:
    root, low, high = await _two_mounts()
    rows: Iterator[Observation] = iter(_held())
    await root.search("lease", observations=rows, ext=("md",), limit=3)  # ty: ignore[invalid-argument-type]
    assert _sent(low) == [["/l1.md"]] and _sent(high) == [["/h2.md"]]


@pytest.mark.parametrize("channel", ["globs", "globs_not"])
async def test_a_glob_that_cannot_be_parsed_is_refused_as_grep_refuses_it(channel: str) -> None:
    root, low, high = await _two_mounts()
    bad: dict[str, Any] = {channel: ("{a",)}
    searched = await root.search("lease", observations=_held(), **bad)
    grepped = await root.grep("lease", observations=_held(), **bad)
    [error] = searched.errors
    [expected] = grepped.errors
    assert searched.success is False and error.kind is ErrorKind.invalid and error.message == expected.message
    assert searched.ops == ("search",)
    assert low.calls == [] and high.calls == []


async def test_a_closed_kernel_is_unavailable_unless_a_glob_is_bad() -> None:
    root, _low, _high = await _two_mounts()
    await root.close()
    closed = await root.search("lease", observations=_held(), ext=("md",))
    assert [error.kind for error in closed.errors] == [ErrorKind.backend_unavailable]
    not_rows = await root.search("lease", observations="abc", ext=("md",))  # ty: ignore[invalid-argument-type]
    assert [error.kind for error in not_rows.errors] == [ErrorKind.backend_unavailable]
    bad = await root.search("lease", observations=_held(), globs=("{a",))
    assert [error.kind for error in bad.errors] == [ErrorKind.invalid]


async def test_a_batch_that_is_not_rows_is_refused_before_the_filter() -> None:
    root, low, high = await _two_mounts()
    text = await root.search("lease", observations="abc", ext=("md",))  # ty: ignore[invalid-argument-type]
    [error] = text.errors
    assert (error.kind, error.message) == (
        ErrorKind.invalid,
        "Invalid: observations must be an iterable of Observation, got str",
    )
    mixed: list[Any] = [Observation(path=Path("/low/l1.md")), "x"]
    [error] = (await root.search("lease", observations=mixed, ext=("md",))).errors
    assert (error.kind, error.message) == (
        ErrorKind.invalid,
        "Invalid: observations must be Observation instances, got str",
    )
    assert low.calls == [] and high.calls == []


async def test_a_filter_at_its_budget_drops_what_it_did_not_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chain_module, "WALL_TIME_BUDGET", -1.0)
    root, low, high = await _two_mounts()
    result = await root.search("lease", observations=_held(), globs=("*.md",))
    assert result.success is True and result.observations == []
    assert low.calls == [] and high.calls == []
    [error] = result.errors
    assert (error.kind, error.severity, error.message) == (ErrorKind.truncated, Severity.warning, TRUNCATED)


async def test_an_extension_filter_reads_no_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[float] = []

    def clock() -> float:
        reads.append(monotonic())
        return reads[-1]

    monkeypatch.setattr(deadline_module, "monotonic", clock)
    monkeypatch.setattr(chain_module, "WALL_TIME_BUDGET", -1.0)
    root, low, high = await _two_mounts()
    result = await root.search("lease", observations=_held(), ext=("md",))
    assert result.errors == [] and reads == []
    assert _sent(low) == [["/l1.md"]] and _sent(high) == [["/h2.md"]]
    await root.search("lease", observations=_held(), globs=("*.md",))
    assert reads != []


async def test_no_filter_does_no_work_on_the_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    extensions: list[str] = []
    real = chain_module.extract_extension

    def counted(path: Any) -> Any:
        extensions.append(str(path))
        return real(path)

    monkeypatch.setattr(chain_module, "extract_extension", counted)
    judged = _count_judges(monkeypatch)
    rows = [Observation(path=Path(f"/d{i % 100}/f{i % 5_000}.md")) for i in range(10_000)]
    kept, records = await admit_rows_in_hand(rows, globs=(), globs_not=(), ext=(), ext_not=())
    assert extensions == [] and judged == [] and records == []
    assert kept == rows


async def test_an_unfinished_filter_searches_the_rows_it_admitted(monkeypatch: pytest.MonkeyPatch) -> None:
    real = chain_module.judge_rows

    async def partly(executor: Any, gates: Any, rows: Any, *, deadline: Deadline) -> Any:
        first, _completed = await real(executor, gates, rows[:1], deadline=deadline)
        return [*first, *([None] * (len(rows) - 1))], False

    monkeypatch.setattr(chain_module, "judge_rows", partly)
    own = ResultError(kind=ErrorKind.truncated, message="the storage's own", severity=Severity.warning)
    root = AsyncVirtualFileSystem()
    low = _mount([_row("/l1", 0.2, "lease lease"), _row("/l2", 0.1, "nothing")], lexical_stats=STATS, errors=[own])
    high = _mount([_row("/h2", 0.8, "a lease")], lexical_stats=STATS)
    await root.add_mount(low, "/low")
    await root.add_mount(high, "/high")
    held = _held("/low/l1.md", "/low/l3.md", "/high/h2.md")
    result = await root.search("lease", observations=held, globs=("*.md",), limit=3)
    assert _sent(low) == [["/l1.md"]] and _limits(low) == [3] and high.calls == []
    assert result.success is True and result.paths == ("/low/l1", "/low/l2")
    stored, error = result.errors
    assert stored.message == "the storage's own"
    assert (error.kind, error.severity, error.message) == (ErrorKind.truncated, Severity.warning, TRUNCATED)


def _count_judges(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The number of rows each call to the judge received."""
    judged: list[int] = []
    real = chain_module.judge_rows

    async def counted(executor: Any, gates: Any, rows: Any, *, deadline: Deadline) -> Any:
        judged.append(len(rows))
        return await real(executor, gates, rows, deadline=deadline)

    monkeypatch.setattr(chain_module, "judge_rows", counted)
    return judged


async def test_no_pattern_means_no_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    judged = _count_judges(monkeypatch)
    root, low, high = await _two_mounts()
    await root.search("lease", observations=_held())
    assert _sent(low) == [["/l1.md", "/l2.txt"]] and _sent(high) == [["/h1.txt", "/h2.md"]]
    low.calls.clear()
    high.calls.clear()
    await root.search("lease", observations=_held(), ext=("md",))
    assert _sent(low) == [["/l1.md"]] and _sent(high) == [["/h2.md"]]
    assert judged == []


@pytest.mark.slow
async def test_ten_thousand_rows_are_judged_in_one_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    judged = _count_judges(monkeypatch)
    root, low, high = await _two_mounts()
    big = [Observation(path=Path(f"/low/d{i % 100}/f{i}.{'md' if i % 2 else 'txt'}")) for i in range(10_000)]
    await root.search("lease", observations=big, globs=("*.md",), globs_not=("**/d7/**",), limit=3)
    assert judged == [10_000]
    assert [len(sent) for sent in _sent(low)] == [4_900]
    assert high.calls == []


async def _with_mute() -> tuple[AsyncVirtualFileSystem, CannedStorage, CannedStorage, RecorderStorage]:
    root, low, high = await _two_mounts()
    mute = RecorderStorage(caps=frozenset({"read", "stat", "ls", "glob", "grep"}))
    await root.add_mount(mute, "/mute")
    return root, low, high, mute


async def test_a_passing_row_in_a_mount_that_cannot_search_refuses_the_call() -> None:
    root, low, high, mute = await _with_mute()
    result = await root.search("lease", observations=_held(*HELD, "/mute/m.txt"), ext=("txt",))
    [error] = result.errors
    assert (error.kind, str(error.path)) == (ErrorKind.unsupported, "/mute")
    assert _no_search_calls(low, high, mute)


async def test_a_dropped_row_in_a_mount_that_cannot_search_is_never_checked() -> None:
    root, low, high, mute = await _with_mute()
    result = await root.search("lease", observations=_held(*HELD, "/mute/m.txt"), ext=("md",))
    assert result.success is True and mute.calls == []
    assert _sent(low) == [["/l1.md"]] and _sent(high) == [["/h2.md"]]


async def test_a_passing_directory_or_ghost_is_left_out_without_an_error() -> None:
    fs = await _memory({"/dir/z.md": "alpha delta"})
    rows = [
        Observation(path=Path("/dir"), kind="directory"),
        Observation(path=Path("/dir/ghost.md")),
        Observation(path=Path("/dir/z.md")),
    ]
    result = await fs.search("alpha", observations=rows, globs_not=("*.txt",))
    assert result.success is True and result.errors == []
    assert result.paths == ("/dir/z.md",)
    await fs.close()


@pytest.mark.parametrize("directory", ["/data", "/"])
async def test_a_passing_row_at_a_mount_point_or_the_root_is_left_out_as_a_directory_is(directory: str) -> None:
    """The row reaches its storage as ``/``, which names no file, so only the file beside it is ranked."""
    fs = await _memory({"/x.md": "alpha root"})
    await fs.add_mount(InMemoryStorage(), "/data")
    assert (await fs.write(path="/data/a.md", content="alpha one")).success is True
    rows = [Observation(path=Path(directory), kind="directory"), Observation(path=Path("/data/a.md"))]
    result = await fs.search("alpha", observations=rows, ext_not=("txt",))
    assert result.success is True and result.errors == []
    assert result.paths == ("/data/a.md",)
    await fs.close()


async def test_a_trashed_row_in_hand_is_filtered_like_any_other() -> None:
    fs = await _memory({"/gone.md": "alpha trashed"}, deleted=("/gone.md",))
    held = _held("/.vfs/trash/gone.md")
    plain = await fs.search("alpha", observations=held)
    assert len(plain.observations) == 1
    assert (await fs.search("alpha", observations=held, globs=("*.md",))).paths == plain.paths
    dropped = await fs.search("alpha", observations=held, globs_not=("*.md",))
    assert dropped.success is True and dropped.observations == []
    await fs.close()


async def test_a_filter_that_drops_one_side_of_the_trash_view_is_not_refused() -> None:
    fs = await _memory(
        {"/x.txt": "alpha beta", "/y.md": "alpha gamma", "/gone.md": "alpha trashed"}, deleted=("/gone.md",)
    )
    held = _held("/.vfs/trash/gone.md", "/x.txt", "/y.md")
    [error] = (await fs.search("alpha", observations=held)).errors
    assert (error.kind, error.message) == (
        ErrorKind.invalid,
        "Invalid: a scope under '/.vfs/trash' cannot mix with live paths",
    )
    live = await fs.search("alpha", observations=held, globs_not=("/.vfs/**",))
    assert live.success is True and sorted(_paths(live)) == ["/x.txt", "/y.md"]
    await fs.close()


async def test_a_call_that_asks_no_storage_checks_no_query(
    two_real_mounts: tuple[AsyncVirtualFileSystem, list[Observation]],
) -> None:
    fs, rows = two_real_mounts
    empty = await fs.search("", observations=rows, ext=("rs",))
    assert empty.success is True and empty.observations == [] and empty.errors == []
    refused = await fs.search("", observations=rows)
    assert refused.success is False and {error.kind for error in refused.errors} == {ErrorKind.invalid}


async def test_admitting_rows_in_hand_keeps_the_admitted_rows_in_order() -> None:
    rows = _held("/b.md", "/a.txt", "/a.md")
    kept, records = await admit_rows_in_hand(rows, globs=(), globs_not=(), ext=("md",), ext_not=())
    assert [str(row.path) for row in kept] == ["/b.md", "/a.md"] and records == []
