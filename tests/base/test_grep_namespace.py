"""Namespace-coordinate grep over real storages — the placement-invariance law.

Grep's analog of the glob namespace battery: the same logical tree
answers the same call identically whether a subtree is plain
directories or a mount, with scoping and the glob channels crossing the
seam as composed pattern text.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from tests.support.base_doubles import RecorderStorage
from vfs import base as base_module
from vfs.base import AsyncVirtualFileSystem
from vfs.models import Observation
from vfs.params import INT_CEILING
from vfs.paths import Path
from vfs.pattern_matching import glob as glob_module
from vfs.results import ErrorKind, Result
from vfs.results.kinds import Severity
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# The demo tree: needle sits at every level; decoy never matches.
TREE = (("/notes.txt", "needle root"), ("/data/a.txt", "needle a"), ("/data/deep/b.py", "needle b"))


async def _plain_world() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    for path, content in TREE:
        await fs.write(path=path, content=content, parents=True)
    return fs


async def _mounted_world() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/notes.txt", content="needle root")
    await fs.add_mount(InMemoryStorage(), "/data")
    await fs.write(path="/data/a.txt", content="needle a")
    await fs.write(path="/data/deep/b.py", content="needle b", parents=True)
    return fs


INVARIANCE_BATTERY: tuple[dict[str, Any], ...] = (
    {},  # unscoped, unfiltered
    {"paths": ("/data",)},  # scope root at the mount point
    {"paths": ("/data/deep",)},  # scope root inside the mount
    {"paths": ("/data/a.txt", "/notes.txt")},  # file operands
    {"globs": ("*.txt",)},  # name-arm filter
    {"globs": ("/data/**",)},  # path-arm filter across the seam
    {"paths": ("/data",), "globs": ("*.py",)},  # scope with filter
    {"globs_not": ("*.py",)},  # exclusion channel
    {"paths": ("/data",), "globs_not": ("deep/**",)},  # composed exclusion
)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def plain_world() -> AsyncIterator[AsyncVirtualFileSystem]:
    """The plain world once per module; the invariance battery only reads it."""
    fs = await _plain_world()
    yield fs
    await fs.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def mounted_world() -> AsyncIterator[AsyncVirtualFileSystem]:
    """The mounted world once per module; the invariance battery only reads it."""
    fs = await _mounted_world()
    yield fs
    await fs.close()


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("kwargs", INVARIANCE_BATTERY)
async def test_mount_placement_is_invisible_to_grep(
    kwargs: dict[str, Any], plain_world: AsyncVirtualFileSystem, mounted_world: AsyncVirtualFileSystem
) -> None:
    plain = await plain_world.grep("needle", **kwargs)
    mounted = await mounted_world.grep("needle", **kwargs)
    assert plain.success is True and mounted.success is True
    assert sorted(plain.paths) == sorted(mounted.paths)


async def test_a_scoped_call_carries_only_its_own_op_and_renders_natively() -> None:
    # The scope-root probe is a stat on the router's behalf, not a verb of
    # its own: a scoped grep still says ``grep`` and prints rg-style lines.
    fs = await _mounted_world()
    scoped = await fs.grep("needle", paths=("/data",))
    assert scoped.ops == ("grep",) and scoped.op == "grep"
    assert scoped.to_str() == "/data/a.txt:1:needle a\n/data/deep/b.py:1:needle b"
    found = await fs.glob("**/*.txt", paths=("/data",))
    assert found.ops == ("glob",) and found.to_str() == "/data/a.txt"
    await fs.close()


async def test_scoped_grep_reaches_across_the_seam() -> None:
    fs = await _mounted_world()
    result = await fs.grep("needle", paths=("/data",))
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.py"]


async def test_a_file_operand_is_grepped_itself() -> None:
    # find parity: the operand's own content joins the scan; a glob
    # filter the operand fails drops it as clean success.
    fs = await _mounted_world()
    hit = await fs.grep("needle", paths=("/data/a.txt",))
    assert hit.paths == ("/data/a.txt",)
    miss = await fs.grep("needle", paths=("/data/a.txt",), globs=("*.py",))
    assert miss.success is True and miss.paths == ()


async def test_missing_roots_stay_loud_per_root_assertions() -> None:
    fs = await _mounted_world()
    result = await fs.grep("needle", paths=("/data", "/data/nope"))
    assert result.success is False
    assert [(e.kind, e.path) for e in result.failures] == [(ErrorKind.not_found, "/data/nope")]
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.py"]


async def test_root_order_does_not_change_the_answer() -> None:
    fs = await _mounted_world()
    forward = await fs.grep("needle", paths=("/data", "/missing"))
    reverse = await fs.grep("needle", paths=("/missing", "/data"))
    assert sorted(forward.paths) == sorted(reverse.paths)
    assert forward.success is False and reverse.success is False
    assert [(e.kind, e.path) for e in forward.failures] == [(e.kind, e.path) for e in reverse.failures]


async def test_metachar_roots_scope_grep_to_their_own_subtree() -> None:
    # Roots are paths, never glob syntax — including the find-operand
    # rule, where the root's own path rides the batch as a literal.
    for fs in (await _plain_world(), await _mounted_world()):
        await fs.write(path="/data/[x]/n.txt", content="needle bracket", parents=True)
        await fs.write(path="/data/x/n.txt", content="needle sibling", parents=True)
        scoped = await fs.grep("needle", paths=("/data/[x]",))
        assert scoped.success is True
        assert scoped.paths == ("/data/[x]/n.txt",)
        operand = await fs.grep("needle", paths=("/data/[x]/n.txt",))
        assert operand.paths == ("/data/[x]/n.txt",)


async def test_defective_globs_refuse_before_any_dispatch() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    channels: tuple[dict[str, Any], ...] = ({"globs": ("a**b",)}, {"globs_not": ("x/",)})
    for channel in channels:
        result = await fs.grep("needle", **channel)
        assert result.success is False
        assert result.errors[0].kind is ErrorKind.invalid


async def test_unscoped_glob_channels_cross_the_seam_composed() -> None:
    # Name-arm filters broadcast verbatim; path-arm filters residuate
    # into entry coordinates; exclusions ride the same composition.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/m")
    await fs.grep("needle", globs=("*.py", "/m/src/**"), globs_not=("*.log",))
    [(op, kwargs)] = recorder.calls
    assert op == "grep"
    assert kwargs["globs"] == ("*.py", "/src/**")
    assert kwargs["globs_not"] == ("*.log",)
    assert "paths" not in kwargs


async def test_a_dead_admission_set_is_routing_not_a_skip() -> None:
    # The path-arm glob cannot reach /m: the entry is simply not
    # dispatched, with no record minted — dead residuals are routing.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/m")
    result = await fs.grep("needle", globs=("/elsewhere/**",))
    assert result.success is True
    assert recorder.calls == []
    assert result.errors == []


async def test_ten_thousand_roots_stay_two_calls() -> None:
    # The ETL scale row: contract-scale root batches reach storage as
    # exactly one grep call and one probe call — every root contributes
    # its subtree member and its literal to the composed globs batch.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    data = RecorderStorage()
    await fs.add_mount(data, "/data")
    await fs.grep("needle", paths=tuple(f"/data/part{i:05}" for i in range(10_000)))
    assert [op for op, _ in data.calls] == ["stat", "grep"]
    [grep_call] = [kw for op, kw in data.calls if op == "grep"]
    assert len(grep_call["globs"]) == 20_000
    [probe] = [kw for op, kw in data.calls if op == "stat"]
    assert len(probe["observations"]) == 10_000


async def test_capability_skips_survive_only_where_the_globs_reach() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(RecorderStorage(caps=frozenset({"read"})), "/thin")
    reached = await fs.grep("needle")
    assert [e.path for e in reached.errors] == ["/thin"]
    unreached = await fs.grep("needle", globs=("/elsewhere/**",))
    assert unreached.errors == []


# ----------------------------------------------------------------------
# Chaining — observations are rows in hand, filtered without dispatch
# ----------------------------------------------------------------------


async def test_chained_grep_matches_held_content_without_storage() -> None:
    # Pure filter posture: the rows' paths exist nowhere in storage,
    # and content in hand still matches — no call, no assertion.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/a.txt"), kind="file", content="a needle here"),
        Observation(path=Path("/b.txt"), kind="file", content="nothing"),
    ]
    result = await fs.grep("needle", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/a.txt"]
    [hit] = result.observations
    assert hit.matches is not None


async def test_chained_grep_fetches_absent_content_and_errors_loudly() -> None:
    fs = await _plain_world()
    rows = [Observation(path=Path("/data/a.txt"), kind="file"), Observation(path=Path("/ghost.txt"), kind="file")]
    result = await fs.grep("needle", observations=rows)
    assert result.success is False
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]
    assert [e.kind for e in result.errors] == [ErrorKind.not_found]


async def test_chained_grep_skips_contentless_kinds_silently() -> None:
    # A directory row is a filter non-match, never an error and never
    # a fetch.
    fs = await _plain_world()
    rows = [Observation(path=Path("/data"), kind="directory"), Observation(path=Path("/data/a.txt"), kind="file")]
    result = await fs.grep("needle", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]


async def test_chained_grep_applies_the_glob_and_ext_gates_in_memory() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/x/a.py"), kind="file", content="needle"),
        Observation(path=Path("/x/b.txt"), kind="file", content="needle"),
    ]
    by_glob = await fs.grep("needle", observations=rows, globs=("*.py",))
    assert [str(o.path) for o in by_glob.observations] == ["/x/a.py"]
    by_ext = await fs.grep("needle", observations=rows, ext_not=("py",))
    assert [str(o.path) for o in by_ext.observations] == ["/x/b.txt"]


async def test_chained_grep_ext_members_normalize_dots_and_case() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/x/a.py"), kind="file", content="needle"),
        Observation(path=Path("/x/b.txt"), kind="file", content="needle"),
    ]
    dotted = await fs.grep("needle", observations=rows, ext=(".PY",))
    assert [str(o.path) for o in dotted.observations] == ["/x/a.py"]
    dropped = await fs.grep("needle", observations=rows, ext_not=(".PY",))
    assert [str(o.path) for o in dropped.observations] == ["/x/b.txt"]


async def test_chained_grep_never_refuses_on_indexability() -> None:
    # The index tier is not involved: a pattern with no indexable
    # literal matches rows in hand without allow_scan.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/a.txt"), kind="file", content="alpha")]
    result = await fs.grep(".*", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/a.txt"]


async def test_chained_grep_never_hides_meta_rows_in_hand() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/.vfs/state/s.txt"), kind="file", content="needle hidden")]
    result = await fs.grep("needle", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/.vfs/state/s.txt"]


async def test_chained_grep_attaches_fetched_content_only_when_projected() -> None:
    fs = await _plain_world()
    rows = [Observation(path=Path("/data/a.txt"), kind="file")]
    bare = await fs.grep("needle", observations=rows)
    assert bare.observations[0].content is None
    projected = await fs.grep("needle", observations=rows, columns=frozenset({"content"}))
    assert projected.observations[0].content == "needle a"


async def test_chained_grep_output_modes_shape_the_held_row() -> None:
    # files mode strips content even when held; count mode reports the
    # hit count on score — same contract as the storage tiers.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/a.txt"), kind="file", content="needle\nplain\nneedle")]
    files = await fs.grep("needle", observations=rows, output_mode="files")
    assert files.observations[0].content is None
    assert files.observations[0].matches is None
    counted = await fs.grep("needle", observations=rows, output_mode="count")
    assert counted.observations[0].score == 2.0


async def test_int_channels_refuse_past_the_shared_ceiling() -> None:
    # The former raw-OverflowError shape: a router-admitted value the
    # FFI seam could not carry. Over-max now refuses typed invalid.
    fs = await _plain_world()
    over = await fs.grep("needle", before_context=2**32)
    assert over.success is False
    assert over.errors[0].kind is ErrorKind.invalid
    assert "before_context" in over.errors[0].message
    huge_count = await fs.grep("needle", max_count=2**64)
    assert huge_count.success is False
    assert huge_count.errors[0].kind is ErrorKind.invalid


async def test_the_ceiling_itself_is_served_on_the_live_engine() -> None:
    # The declared maximum is a lawful value: it must cross the engine
    # seam and answer, not refuse at one and overflow at the other.
    fs = await _plain_world()
    result = await fs.grep("needle", before_context=INT_CEILING, after_context=INT_CEILING, max_count=INT_CEILING)
    assert result.success is True
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.py", "/notes.txt"]


# ----------------------------------------------------------------------
# Chained verification — once per distinct body, off the loop, under a wall
# ----------------------------------------------------------------------


class _CountingVerifier:
    """Wraps the real verifier, recording each batch's bodies; can report one batch unfinished."""

    def __init__(self, inner: Any, *, unfinished_batch: int | None = None) -> None:
        self._inner = inner
        self.batches: list[list[Any]] = []
        self._unfinished = unfinished_batch

    def _record(self, texts: Any, answer: tuple[Any, bool]) -> tuple[Any, bool]:
        self.batches.append(list(texts))
        if self._unfinished is not None and len(self.batches) - 1 == self._unfinished:
            return answer[0], False
        return answer

    def count_lines(self, texts: Any, **kwargs: Any) -> tuple[Any, bool]:
        return self._record(texts, self._inner.count_lines(texts, **kwargs))

    def hit_lines(self, texts: Any, **kwargs: Any) -> tuple[Any, bool]:
        return self._record(texts, self._inner.hit_lines(texts, **kwargs))


def _counting_verifiers(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> list[_CountingVerifier]:
    made: list[_CountingVerifier] = []
    real = base_module.compile_verifier

    def compile_counted(*args: Any, **kw: Any) -> _CountingVerifier:
        verifier = _CountingVerifier(real(*args, **kw), **kwargs)
        made.append(verifier)
        return verifier

    monkeypatch.setattr(base_module, "compile_verifier", compile_counted)
    return made


def _counted_hops(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    pools: list[Any] = []
    real = base_module.call_offloaded

    async def counted(executor: Any, work: Any) -> Any:
        pools.append(executor)
        return await real(executor, work)

    monkeypatch.setattr(base_module, "call_offloaded", counted)
    return pools


def _held(*pairs: tuple[str, str]) -> list[Observation]:
    return [Observation(path=Path(path), kind="file", content=content) for path, content in pairs]


async def test_chained_grep_verifies_each_distinct_body_once(monkeypatch: pytest.MonkeyPatch) -> None:
    made = _counting_verifiers(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.grep("x", observations=_held(*[("/a.txt", "x\n")] * 1_000))
    assert len(result.observations) == 1_000
    [verifier] = made
    assert sum(len(batch) for batch in verifier.batches) == 1


async def test_chained_grep_matches_in_byte_batches_on_the_router_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "CONTENT_BYTE_BUDGET", 10)
    pools = _counted_hops(monkeypatch)
    default = _CountingExecutor()
    asyncio.get_running_loop().set_default_executor(default)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = _held(*[(f"/{i}.txt", f"x{i:07d}") for i in range(5)])
    result = await fs.grep("x", observations=rows)
    assert len(result.observations) == 5
    assert len(pools) == 5
    assert all(pool is fs._verify_pool for pool in pools)
    assert default.submitted == 0
    await fs.close()


async def test_chained_grep_truncates_at_the_wall(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", -1.0)
    pools = _counted_hops(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.grep("x", observations=_held(("/a", "x"), ("/b", "x"), ("/c", "x")))
    assert result.observations == []
    [error] = result.errors
    assert error.kind is ErrorKind.truncated and error.severity is Severity.warning
    assert error.message == (
        "Truncated: at the wall-time budget; narrow the pattern, add globs or ext filters, or send fewer rows"
    )
    assert pools == []


async def test_a_batch_the_matcher_could_not_finish_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "CONTENT_BYTE_BUDGET", 1)
    made = _counting_verifiers(monkeypatch, unfinished_batch=0)
    pools = _counted_hops(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.grep("x", observations=_held(("/a", "x"), ("/b", "x")))
    assert [str(o.path) for o in result.observations] == ["/a"]
    assert [e.kind for e in result.errors] == [ErrorKind.truncated]
    assert len(pools) == 1 and len(made[0].batches) == 1
    await fs.close()


async def test_chained_grep_dedupes_without_reordering_or_aliasing(monkeypatch: pytest.MonkeyPatch) -> None:
    made = _counting_verifiers(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = _held(("/a", "x"), ("/b", "y"), ("/a", "x"), ("/a", "xx"))
    result = await fs.grep("x", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/a", "/a", "/a"]
    third = result.observations[2].matches
    assert third is not None and third[0].content == "xx"
    assert sum(len(batch) for batch in made[0].batches) == 3
    lists = [o.matches for o in result.observations]
    assert len({id(matches) for matches in lists}) == 3
    await fs.close()


async def test_close_shuts_the_verify_pool_and_a_closed_router_makes_none() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.grep("x", observations=_held(("/a", "x")))
    pool = fs._verify_pool
    assert pool is not None
    await fs.close()
    assert fs._verify_pool is None
    with pytest.raises(RuntimeError):
        pool.submit(int)
    closed = await fs.grep("x", observations=_held(("/a", "x")))
    assert [e.kind for e in closed.errors] == [ErrorKind.backend_unavailable]
    assert fs._verify_pool is None


async def test_close_shuts_the_verify_pool_with_nothing_to_dispose() -> None:
    # RecorderStorage exposes no close, so close() finds nothing to dispose and returns early.
    fs = AsyncVirtualFileSystem(storage=RecorderStorage())
    await fs.grep("x", observations=_held(("/a", "x")))
    pool = fs._verify_pool
    assert pool is not None
    await fs.close()
    assert fs._verify_pool is None
    with pytest.raises(RuntimeError):
        pool.submit(int)


async def test_a_chained_grep_racing_close_makes_no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "CONTENT_BYTE_BUDGET", 1)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    pools: list[Any] = []
    real = base_module.call_offloaded

    async def close_after_first(executor: Any, work: Any) -> Any:
        pools.append(executor)
        answer = await real(executor, work)
        if len(pools) == 1:
            await fs.close()
        return answer

    monkeypatch.setattr(base_module, "call_offloaded", close_after_first)
    result = await fs.grep("x", observations=_held(("/a", "x"), ("/b", "x")))
    assert [str(o.path) for o in result.observations] == ["/a", "/b"]
    assert len(pools) == 2 and pools[0] is pools[1]
    assert fs._verify_pool is None


async def test_a_chained_grep_closed_during_its_read_makes_no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())

    async def closing_read(*args: Any, **kwargs: Any) -> Result:
        await fs.close()
        return Result(ops=("read",))

    monkeypatch.setattr(fs, "read", closing_read)
    rows = [*_held(("/a", "x")), Observation(path=Path("/b"), kind="file")]
    result = await fs.grep("x", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/a"]
    assert fs._verify_pool is None


@pytest.mark.parametrize("mode", ["lines", "files"])
async def test_each_batch_gets_the_wall_budget_cut_at_worker_start(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    # A fake clock: the deadline is read at 100, the batch check at 101, the worker starts at 103.
    ticks = iter([100.0, 101.0, 103.0])
    monkeypatch.setattr(base_module, "monotonic", lambda: next(ticks))
    budgets: list[float | None] = []

    class Recording:
        def count_lines(self, texts: Any, **kwargs: Any) -> tuple[list[int], bool]:
            budgets.append(kwargs["budget"])
            return [1 for _ in texts], True

        def hit_lines(self, texts: Any, **kwargs: Any) -> tuple[list[list[Any]], bool]:
            budgets.append(kwargs["budget"])
            return [[(1, 1, 1, "x")] for _ in texts], True

    monkeypatch.setattr(base_module, "compile_verifier", lambda *a, **k: Recording())
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.grep("x", observations=_held(("/a", "x")), output_mode=mode)  # ty: ignore[invalid-argument-type]
    assert len(result.observations) == 1
    assert budgets == [base_module.WALL_TIME_BUDGET - 3.0]
    await fs.close()


async def test_close_never_waits_for_a_running_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    started, release = threading.Event(), threading.Event()
    finished: list[bool] = []
    real = base_module.compile_verifier

    class Held:
        def __init__(self) -> None:
            self._inner = real("x", fixed_strings=False, word_regexp=False, case_mode="sensitive")

        def hit_lines(self, texts: Any, **kwargs: Any) -> tuple[Any, bool]:
            started.set()
            release.wait()
            finished.append(True)
            return self._inner.hit_lines(texts, **kwargs)

    monkeypatch.setattr(base_module, "compile_verifier", lambda *a, **k: Held())
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    task = asyncio.create_task(fs.grep("x", observations=_held(("/a", "x"))))
    await asyncio.to_thread(started.wait)
    # A safety release, so a close() that waits on the worker fails this test instead of hanging it.
    safety = threading.Timer(5.0, release.set)
    safety.start()
    await fs.close()
    assert finished == []
    release.set()
    safety.cancel()
    result = await task
    assert [str(o.path) for o in result.observations] == ["/a"]


async def test_a_batch_queued_at_close_still_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    # One worker: grep a's batch holds it, grep b's batch waits in the queue when close() lands.
    monkeypatch.setattr(base_module, "OFFLOAD_WORKERS", 1)
    started, release = threading.Event(), threading.Event()
    real = base_module.compile_verifier

    class HeldOnce:
        def __init__(self, pattern: str, **kwargs: Any) -> None:
            self._inner = real(pattern, **kwargs)
            self._hold = pattern == "a"

        def hit_lines(self, texts: Any, **kwargs: Any) -> tuple[Any, bool]:
            if self._hold:
                started.set()
                release.wait()
            return self._inner.hit_lines(texts, **kwargs)

    monkeypatch.setattr(base_module, "compile_verifier", HeldOnce)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    first = asyncio.create_task(fs.grep("a", observations=_held(("/a", "a"))))
    await asyncio.to_thread(started.wait)
    second = asyncio.create_task(fs.grep("b", observations=_held(("/b", "b"))))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # A safety release, so a close() that waits on the worker fails this test instead of hanging it.
    safety = threading.Timer(5.0, release.set)
    safety.start()
    await fs.close()
    assert not release.is_set()
    release.set()
    safety.cancel()
    results = await asyncio.gather(first, second)
    assert [[str(o.path) for o in r.observations] for r in results] == [["/a"], ["/b"]]


async def test_wide_context_returns_each_line_once() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    body = "x\n" * 2_000
    await fs.write(path="/w.txt", content=body)
    result = await fs.grep("x", before_context=2_000, after_context=2_000, allow_scan=True)
    [row] = result.observations
    assert row.matches is not None and len(row.matches) == 2_000
    assert sum(len(m.content or "") for m in row.matches) <= len(body)
    await fs.close()


class _CountingExecutor(ThreadPoolExecutor):
    """The loop's default executor, counting what reaches it."""

    def __init__(self) -> None:
        super().__init__(max_workers=2)
        self.submitted = 0

    def submit(self, *args: Any, **kwargs: Any) -> Any:
        self.submitted += 1
        return super().submit(*args, **kwargs)


# ----------------------------------------------------------------------
# Off the loop: the router's glob judging runs on its pool
# ----------------------------------------------------------------------


def _spy_judges(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The executor each router judge hop ran on."""
    executors: list[Any] = []
    real = base_module.judge_rows

    async def spied(executor: Any, gates: Any, rows: Any, *, deadline: float) -> Any:
        executors.append(executor)
        return await real(executor, gates, rows, deadline=deadline)

    monkeypatch.setattr(base_module, "judge_rows", spied)
    return executors


async def test_chained_grep_filters_once_on_the_router_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the chained filter run inline per row instead of in one hop."""
    executors = _spy_judges(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = _held(*[(f"/{i}.{'txt' if i % 2 else 'md'}", "x") for i in range(100)])
    result = await fs.grep("x", observations=rows, globs=("*.txt",))
    assert len(result.observations) == 50
    assert len(executors) == 1 and executors[0] is fs._verify_pool
    await fs.close()


async def test_chained_grep_past_the_wall_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: rows the filter never judged read and matched anyway."""
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", -1.0)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    reads: list[Any] = []

    async def counted_read(*args: Any, **kwargs: Any) -> Result:
        reads.append(kwargs)
        return Result(ops=("read",))

    monkeypatch.setattr(fs, "read", counted_read)
    rows = [Observation(path=Path(f"/{name}"), kind="file") for name in ("a.txt", "b.txt")]
    result = await fs.grep("x", observations=rows, globs=("*.txt",))
    assert result.observations == []
    assert reads == []
    [error] = result.errors
    assert (error.kind, error.severity) == (ErrorKind.truncated, Severity.warning)
    await fs.close()


async def test_grep_root_admissions_judge_once_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the admissions compiled and matched once per root per glob per entry."""
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    for mount in ("/a", "/b"):
        await fs.add_mount(InMemoryStorage(), mount)
    roots = [f"/{mount}/f{i:02}.txt" for mount in "ab" for i in range(10)]
    for root in roots:
        assert (await fs.write(path=root, content="needle")).success is True
    executors = _spy_judges(monkeypatch)
    built: list[list[Any]] = []
    real = glob_module.glob_set

    def spied(programs: list[Any], groups: Any, *, budget: float | None) -> Any:
        built.append(programs)
        return real(programs, groups, budget=budget)

    monkeypatch.setattr(glob_module, "glob_set", spied)
    result = await fs.grep("needle", paths=tuple(roots), globs=("*.txt",))
    assert sorted(str(o.path) for o in result.observations) == sorted(roots)
    assert len(executors) == 1 and executors[0] is fs._verify_pool
    router_sets = [programs for programs in built if not any(by_path for _atoms, by_path in programs)]
    assert [len(programs) for programs in router_sets] == [1]
    await fs.close()


async def test_an_unfinished_filter_and_matching_stage_record_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the filter's wall record and the matching stage's identical one both carried."""

    async def unfinished(executor: Any, gates: Any, rows: Any, *, deadline: float) -> Any:
        return [1] * len(rows), False

    monkeypatch.setattr(base_module, "judge_rows", unfinished)
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", -1.0)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.grep("x", observations=_held(("/a.txt", "x"), ("/b.txt", "x")), globs=("*.txt",))
    assert result.observations == []
    [error] = result.errors
    assert (error.kind, error.severity) == (ErrorKind.truncated, Severity.warning)
    await fs.close()


_SCOPED_GUIDANCE = "Truncated: at the wall-time budget; narrow the patterns, or scope with fewer paths"


async def _two_file_roots() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    for path in ("/docs/a.md", "/docs/b.txt"):
        assert (await fs.write(path=path, content="needle", parents=True)).success is True
    return fs


async def test_an_unfinished_root_admission_hop_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the admissions' wall record dropped when its hop did not finish."""

    async def unfinished(executor: Any, gates: Any, rows: Any, *, deadline: float) -> Any:
        return [1] * len(rows), False

    monkeypatch.setattr(base_module, "judge_rows", unfinished)
    fs = await _two_file_roots()
    result = await fs.grep("needle", paths=("/docs/a.md", "/docs/b.txt"), globs=("*.txt",))
    walls = [error for error in result.errors if error.kind is ErrorKind.truncated]
    assert [(e.severity, e.message) for e in walls] == [(Severity.warning, _SCOPED_GUIDANCE)]
    await fs.close()


async def test_a_root_never_judged_is_never_admitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: an unjudged root admitted as a literal member, serving a path the caller's globs exclude."""

    async def unjudged(executor: Any, gates: Any, rows: Any, *, deadline: float) -> Any:
        return [None] * len(rows), False

    monkeypatch.setattr(base_module, "judge_rows", unjudged)
    fs = await _two_file_roots()
    result = await fs.grep("needle", paths=("/docs/a.md", "/docs/b.txt"), globs=("*.txt",))
    assert result.observations == []
    [error] = result.errors
    assert (error.kind, error.severity, error.message) == (ErrorKind.truncated, Severity.warning, _SCOPED_GUIDANCE)
    await fs.close()


async def test_a_planning_stop_keeps_every_undecided_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: a stopped walk dropping the coverage records of the skips it never decided."""
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", -1.0)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(RecorderStorage(caps=frozenset({"read", "stat"})), "/thin")
    result = await fs.grep("needle", paths=("/",))
    by_kind = sorted((e.kind, e.severity, str(e.path) if e.path else None) for e in result.errors)
    assert by_kind == sorted(
        [(ErrorKind.truncated, Severity.warning, None), (ErrorKind.unsupported, Severity.info, "/thin")]
    )
    await fs.close()
