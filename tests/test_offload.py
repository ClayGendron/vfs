"""The offload seam — the process pool, the hop, the wrapper laws, the wall's record.

The wrapper's result parity with the direct call, the absolute deadline
crossing the hop (queue wait shortens the budget), the one-in-flight
guard, and the one process pool: its lazy birth, the close that leaves
it alone, the shutdown that serves queued work, and the fork that
forgets it.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from time import monotonic
from typing import TYPE_CHECKING, Any

import pytest

from tests.support.database_helpers import _url
from tests.support.loop_ticks import LoopTicker
from vfs import base as base_module
from vfs import chain as chain_module
from vfs import deadline as deadline_module
from vfs import offload as offload_module
from vfs.base import AsyncVirtualFileSystem
from vfs.deadline import Deadline
from vfs.models import MEASURE_OFFLOAD_BYTES, Entry, Observation
from vfs.offload import (
    OFFLOAD_WORKERS,
    VerifyOffload,
    judge_rows,
    offload_pool,
    shutdown_offload_pool,
    wall_truncation,
)
from vfs.paths import Path
from vfs.pattern_matching import ScopeChannel, compile_gates, compile_verifier
from vfs.pattern_matching import glob as glob_module
from vfs.results import ErrorKind, ResultError, Severity
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database import indexing as indexing_module
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from concurrent.futures import Future

    from vfs.pattern_matching import Body
    from vfs.pattern_matching.grep import MatchSpan


class _RecordingMatcher:
    """A matcher double that records the budget each call receives."""

    def __init__(self) -> None:
        self.budgets: list[float] = []

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        assert budget is not None
        self.budgets.append(budget)
        return [1] * len(texts), True

    def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        budget: float | None,
    ) -> tuple[list[list[MatchSpan]], bool]:
        assert budget is not None
        self.budgets.append(budget)
        return [[] for _ in texts], True


class _GatedMatcher:
    """A matcher double that blocks until its gate opens, tracing its life."""

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.started = threading.Event()
        self.finished = False

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        self.started.set()
        assert self.gate.wait(timeout=5.0)
        self.finished = True
        return [0] * len(texts), True

    def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        budget: float | None,
    ) -> tuple[list[list[MatchSpan]], bool]:  # pragma: no cover - protocol completeness
        assert self.gate.wait(timeout=5.0)
        return [[] for _ in texts], True


async def _until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    start = monotonic()
    while not predicate():
        assert monotonic() - start < timeout, "condition never held"
        await asyncio.sleep(0.01)


class _QueueClock:
    """A queue wait the deadline's clock can see without anyone sleeping.

    One job holds the pool's single worker while the clock stands at the
    submit instant, until the next job waits in the queue behind it; the
    job then moves the clock forward by *wait* and returns, so the next
    job starts on a worker that reads a later time. A budget cut at worker
    start reads ``left_at_worker_start``; one hoisted to submit time would
    read the whole span.
    """

    span = 100.0
    wait = 60.0

    def __init__(self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch) -> None:
        self._now = monotonic()
        self._pool = pool
        monkeypatch.setattr(deadline_module, "monotonic", lambda: self._now)
        self.deadline = Deadline(at=self._now + self.span)
        self.left_at_worker_start = self.span - self.wait
        pool.submit(self._hold_then_advance)

    def _hold_then_advance(self) -> None:
        # Held until the measured job is queued, so a submit-time cut reads the clock before it moves.
        patience = time.monotonic() + 5.0
        while self._pool._work_queue.qsize() < 1 and time.monotonic() < patience:
            time.sleep(0.001)
        self._now += self.wait


@pytest.fixture
def pool() -> Iterator[ThreadPoolExecutor]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-verify")
    yield executor
    executor.shutdown(wait=True)


@pytest.fixture
def fresh_process_pool() -> Iterator[None]:
    """The process pool shut before the test and after it, so a narrowed or shut pool never reaches a neighbour."""
    shutdown_offload_pool()
    yield
    shutdown_offload_pool()


# ---------------------------------------------------------------------------
# The wrapper laws
# ---------------------------------------------------------------------------


class TestVerifyOffload:
    async def test_count_lines_matches_the_direct_call(self, pool: ThreadPoolExecutor) -> None:
        matcher = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        texts = ["a needle here\nno hit", "nothing", "needle\nneedle"]
        direct = matcher.count_lines(texts, cap=None, invert=False, budget=5.0)
        offloaded = await VerifyOffload(matcher, pool).count_lines(
            texts, cap=None, invert=False, deadline=Deadline.after(5.0)
        )
        assert offloaded == direct

    async def test_hit_lines_matches_the_direct_call(self, pool: ThreadPoolExecutor) -> None:
        matcher = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        texts = ["a needle here\nno hit", "nothing", "needle\nneedle"]
        direct = matcher.hit_lines(texts, before=1, after=1, cap=None, invert=False, budget=5.0)
        offloaded = await VerifyOffload(matcher, pool).hit_lines(
            texts, before=1, after=1, cap=None, invert=False, deadline=Deadline.after(5.0)
        )
        assert offloaded == direct

    async def test_queue_wait_shortens_the_budget_never_the_wall(
        self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the budget cut moves to submit time (deadline.remaining()
        hoisted out of the worker fn), silently extending the wall by the
        queue wait."""
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        clock = _QueueClock(pool, monkeypatch)
        await offload.count_lines(["text"], cap=None, invert=False, deadline=clock.deadline)
        assert matcher.budgets == [pytest.approx(clock.left_at_worker_start)]

    async def test_hit_lines_budget_is_cut_at_worker_start_too(
        self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the same submit-time hoist on the hit_lines arm."""
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        clock = _QueueClock(pool, monkeypatch)
        await offload.hit_lines(["text"], before=0, after=0, cap=None, invert=False, deadline=clock.deadline)
        assert matcher.budgets == [pytest.approx(clock.left_at_worker_start)]

    async def test_overlapping_calls_are_refused(self, pool: ThreadPoolExecutor) -> None:
        """Guards: the one-in-flight guard is deleted, letting a second batch
        race the first onto the pool."""
        matcher = _GatedMatcher()
        offload = VerifyOffload(matcher, pool)
        first = asyncio.ensure_future(offload.count_lines(["a"], cap=None, invert=False, deadline=Deadline.after(5.0)))
        await asyncio.sleep(0.05)
        with pytest.raises(RuntimeError, match="one batch in flight"):
            await offload.count_lines(["b"], cap=None, invert=False, deadline=Deadline.after(5.0))
        matcher.gate.set()
        counts, completed = await first
        assert counts == [0] and completed is True

    async def test_the_guard_clears_when_the_worker_drains(self, pool: ThreadPoolExecutor) -> None:
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        for _ in range(2):
            counts, completed = await offload.count_lines(["a"], cap=None, invert=False, deadline=Deadline.after(5.0))
            assert counts == [1] and completed is True
        assert len(matcher.budgets) == 2


# ---------------------------------------------------------------------------
# The proof: the loop keeps ticking while verify runs
# ---------------------------------------------------------------------------


class _HoppingMatcher:
    """A matcher double whose work waits for the loop to turn, as the engines' GIL-releasing work lets it."""

    def __init__(self, ticker: LoopTicker) -> None:
        self._ticker = ticker

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        self._ticker.hop()
        return [1] * len(texts), True

    def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        budget: float | None,
    ) -> tuple[list[list[MatchSpan]], bool]:  # pragma: no cover - protocol completeness
        self._ticker.hop()
        return [[] for _ in texts], True


class TestLoopResponsiveness:
    async def test_the_loop_keeps_ticking_while_verify_runs(self, pool: ThreadPoolExecutor) -> None:
        """Guards: `_run` calls the work inline instead of through the pool,
        holding the loop for the whole batch."""
        ticker = LoopTicker().start()
        offload = VerifyOffload(_HoppingMatcher(ticker), pool)
        counts, completed = await offload.count_lines(["a"], cap=None, invert=False, deadline=Deadline.after(5.0))
        ticker.stop()
        assert counts == [1] and completed is True
        assert ticker.hops == 1  # the one batch hopped off the loop and saw it turn


# ---------------------------------------------------------------------------
# The judge hop: one native set, built under the wall, judged on a worker
# ---------------------------------------------------------------------------

_ROWS = [("/src/a.py", "a.py"), ("/src/b.md", "b.md")]


class _HoppingSet:
    """A native set double whose judging waits for the loop to turn."""

    def __init__(self, ticker: LoopTicker) -> None:
        self._ticker = ticker

    def judge(self, rows: Sequence[tuple[str, str]], *, budget: float | None) -> tuple[list[int | None], bool]:
        self._ticker.hop()
        return [1] * len(rows), True


class _RecordingSet:
    """A native set double that records the budget it was handed."""

    def __init__(self, events: list[object]) -> None:
        self._events = events

    def judge(self, rows: Sequence[tuple[str, str]], *, budget: float | None) -> tuple[list[int | None], bool]:
        self._events.append(("judge", budget))
        return [0] * len(rows), True


class _CountingExecutor(Executor):
    """An executor that counts submissions and records when each task starts."""

    def __init__(self, inner: ThreadPoolExecutor) -> None:
        self._inner = inner
        self.submitted = 0
        self.started = 0

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future[Any]:
        self.submitted += 1

        def run() -> Any:
            self.started += 1
            return fn(*args, **kwargs)

        return self._inner.submit(run)


class TestJudgeRows:
    async def test_judging_runs_on_a_worker_while_the_loop_turns(
        self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the judge work called inline instead of through the pool."""
        ticker = LoopTicker().start()
        gates = compile_gates(("*.py",))
        monkeypatch.setattr(gates, "native", lambda deadline: _HoppingSet(ticker))
        verdicts, completed = await judge_rows(pool, gates, _ROWS, deadline=Deadline.after(5.0))
        ticker.stop()
        assert (verdicts, completed) == ([1, 1], True)
        assert ticker.hops == 1

    async def test_the_budget_is_cut_after_the_build(
        self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the budget cut hoisted before the build, so the build's time
        extends the wall instead of shortening the judging."""
        events: list[object] = []
        gates = compile_gates(("*.py",))

        def build(deadline: Deadline) -> _RecordingSet:
            events.append("build")
            return _RecordingSet(events)

        def clock() -> float:
            events.append("cut")
            return 103.0

        monkeypatch.setattr(gates, "native", build)
        monkeypatch.setattr(deadline_module, "monotonic", clock)
        await judge_rows(pool, gates, _ROWS, deadline=Deadline(at=110.0))
        assert events == ["build", "cut", ("judge", 7.0)]

    async def test_a_build_past_the_deadline_stops(
        self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the build's deadline check dropped, so a stopped build still
        walks every pattern, or a later hop on the same gates builds again."""
        walks: list[str] = []
        sets: list[object] = []
        real_walk = glob_module._program
        real_set = glob_module.glob_set

        def walk(pattern: str, *, recursive: bool) -> Any:
            walks.append(pattern)
            return real_walk(pattern, recursive=recursive)

        def built(*args: Any, **kwargs: Any) -> Any:
            sets.append(args)
            return real_set(*args, **kwargs)

        monkeypatch.setattr(glob_module, "_program", walk)
        monkeypatch.setattr(glob_module, "glob_set", built)
        monkeypatch.setattr(deadline_module, "monotonic", lambda: 2.0 if walks else 0.0)
        gates = compile_gates(("*.py", "/src/**", "*.md"))
        for _hop in range(2):
            verdicts, completed = await judge_rows(pool, gates, _ROWS, deadline=Deadline(at=1.0))
            assert (verdicts, completed) == ([None, None], False)
            assert (len(walks), sets) == (1, [])

    def test_the_set_builds_and_the_scope_judge_take_the_remaining_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a native set built, or a scope's pairs judged, with no budget
        (``budget=None`` in place of the deadline's remainder), so the wall no
        longer stops that stage."""
        events: list[object] = []

        def built(programs: Any, groups: Any, *, budget: float | None) -> _RecordingSet:
            events.append(("build", budget))
            return _RecordingSet(events)

        monkeypatch.setattr(glob_module, "glob_set", built)
        monkeypatch.setattr(deadline_module, "monotonic", lambda: 103.0)
        scope = ScopeChannel(roots=(Path("/src"),), arms=("*.md",))
        for deadline, budget in ((Deadline(at=110.0), 7.0), (Deadline.never(), None)):
            events.clear()
            gates = compile_gates(("*.py",), scope=scope)
            assert gates.native(deadline) is not None
            assert gates.scope_native(deadline) is not None
            gates.judge_scope([("/src/a.md", "a.md")], [0], deadline=deadline)
            assert events == [("build", budget), ("build", budget), ("judge", budget)]

    async def test_no_rows_or_no_patterns_make_no_hop(self, pool: ThreadPoolExecutor) -> None:
        executor = _CountingExecutor(pool)
        past = Deadline(at=-1.0)
        assert await judge_rows(executor, compile_gates(("*.py",)), [], deadline=past) == ([], True)
        assert await judge_rows(executor, compile_gates((), ext=("py",)), _ROWS, deadline=past) == ([0, 0], True)
        assert executor.submitted == 0

    async def test_concurrent_hops_build_the_set_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards: the build lock removed, so two hops racing on one call's gates
        both build the set."""
        inner = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-judge")
        executor = _CountingExecutor(inner)
        both_started = threading.Event()
        calls: list[object] = []
        real = glob_module.glob_set

        def held(*args: Any, **kwargs: Any) -> Any:
            calls.append(args)
            # The first builder waits for the second hop to start, so the two overlap.
            deadline = time.monotonic() + 5.0
            while executor.started < 2 and time.monotonic() < deadline:
                time.sleep(0.001)
            both_started.set()
            return real(*args, **kwargs)

        monkeypatch.setattr(glob_module, "glob_set", held)
        gates = compile_gates(("*.py",))
        deadline = Deadline.after(30.0)
        first, second = await asyncio.gather(
            judge_rows(executor, gates, _ROWS, deadline=deadline),
            judge_rows(executor, gates, _ROWS, deadline=deadline),
        )
        inner.shutdown(wait=True)
        assert both_started.is_set() and executor.started == 2
        assert first == second == ([1, 0], True)
        assert len(calls) == 1

    async def test_a_shut_pool_judges_inline(self, pool: ThreadPoolExecutor) -> None:
        pool.shutdown(wait=True)
        gates = compile_gates(("*.py",))
        assert await judge_rows(pool, gates, _ROWS, deadline=Deadline.after(5.0)) == ([1, 0], True)

    async def test_nested_roots_judge_one_pair_per_covering_root(
        self, pool: ThreadPoolExecutor, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the pair walk stopping at the deepest covering root, or a
        root counted as covering a sibling that shares its prefix."""
        judged: list[list[tuple[str, str]]] = []
        threads: list[str] = []
        real = glob_module.glob_set

        class _Recording:
            def __init__(self, inner: Any) -> None:
                self._inner = inner

            def judge(self, rows: Sequence[tuple[str, str]], *, budget: float | None) -> Any:
                judged.append(list(rows))
                threads.append(threading.current_thread().name)
                return self._inner.judge(rows, budget=budget)

        monkeypatch.setattr(glob_module, "glob_set", lambda *args, **kwargs: _Recording(real(*args, **kwargs)))
        scope = ScopeChannel(roots=(Path("/a"), Path("/a/b")), arms=("**",))
        gates = compile_gates((), scope=scope)
        rows = [("/a/b/x", "x"), ("/a/c", "c"), ("/ab/y", "y")]
        verdicts, completed = await judge_rows(pool, gates, rows, deadline=Deadline.after(5.0))
        assert completed is True
        assert [gates.admits(verdict, None) for verdict in verdicts] == [True, True, False]
        [subjects] = judged
        assert subjects == [("/x", "x"), ("/b/x", "x"), ("/c", "c")]
        assert threads == ["test-verify_0"]


# ---------------------------------------------------------------------------
# Cancellation is abandonment made safe
# ---------------------------------------------------------------------------


class TestAbandonment:
    async def test_a_cancelled_await_returns_while_the_worker_drains_into_the_void(
        self, pool: ThreadPoolExecutor
    ) -> None:
        matcher = _GatedMatcher()
        offload = VerifyOffload(matcher, pool)
        task = asyncio.ensure_future(offload.count_lines(["a"], cap=None, invert=False, deadline=Deadline.after(5.0)))
        await _until(matcher.started.is_set)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert matcher.finished is False
        matcher.gate.set()
        await _until(lambda: matcher.finished)

    async def test_a_cancel_before_the_worker_starts_never_runs_the_matcher(self, pool: ThreadPoolExecutor) -> None:
        blocker = threading.Event()
        pool.submit(blocker.wait, 5.0)
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        task = asyncio.ensure_future(offload.count_lines(["a"], cap=None, invert=False, deadline=Deadline.after(5.0)))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        blocker.set()
        await asyncio.sleep(0.05)
        assert matcher.budgets == []

    async def test_a_superseded_worker_is_harmless_to_its_successor(self, pool: ThreadPoolExecutor) -> None:
        # The redrive shape at the seam: attempt one's worker drains
        # abandoned while attempt two, on a fresh instance, serves whole.
        abandoned = _GatedMatcher()
        first = VerifyOffload(abandoned, pool)
        task = asyncio.ensure_future(first.count_lines(["a"], cap=None, invert=False, deadline=Deadline.after(5.0)))
        await _until(abandoned.started.is_set)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        matcher = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        second = VerifyOffload(matcher, pool)
        successor = asyncio.ensure_future(
            second.count_lines(["a needle", "no hit"], cap=None, invert=False, deadline=Deadline.after(5.0))
        )
        abandoned.gate.set()
        counts, completed = await successor
        assert counts == [1, 0] and completed is True
        await _until(lambda: abandoned.finished)

    async def test_a_cancelled_grep_leaves_the_next_call_whole(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # The end-to-end law: the reissued grep answers correctly while the cancelled one's
        # worker still drains. On SQLite the cancelled caller waits for that worker to end.
        storage = DatabaseStorage(url=_url(tmp_path))
        entry = Entry(path=Path("/a.txt"), content="a needle body")
        assert (await storage.write(entries=[entry])).success is True
        gated = _GatedMatcher()
        real = grep_module.compile_verifier
        compiled = 0

        def gate_first(*args: Any, **kwargs: Any) -> Any:
            nonlocal compiled
            compiled += 1
            return gated if compiled == 1 else real(*args, **kwargs)

        monkeypatch.setattr(grep_module, "compile_verifier", gate_first)
        task = asyncio.ensure_future(storage.grep(pattern="needle", allow_scan=True, output_mode="count"))
        await _until(gated.started.is_set)
        task.cancel()
        result = await storage.grep(pattern="needle", allow_scan=True, output_mode="count")
        assert [str(row.path) for row in result.observations] == ["/a.txt"]
        assert not task.done()
        gated.gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gated.finished is True
        await storage.close()


# ---------------------------------------------------------------------------
# The wall's one record
# ---------------------------------------------------------------------------


def test_the_wall_truncation_has_one_text() -> None:
    """Guards: a stage minting the wall's record with words, a severity or data of its own."""
    record = wall_truncation("narrow it")
    assert isinstance(record, ResultError)
    assert (record.kind, record.severity, record.data) == (ErrorKind.truncated, Severity.warning, None)
    assert record.message == "Truncated: at the wall-time budget; narrow it"


# ---------------------------------------------------------------------------
# The process pool: one, lazy, shared, and left alone by every close
# ---------------------------------------------------------------------------


def _thread_name() -> str:
    return threading.current_thread().name


class _TracingMatcher:
    """A matcher that records the thread each batch call ran on, then delegates."""

    def __init__(self, inner: Any, threads: list[str]) -> None:
        self._inner = inner
        self._threads = threads

    def count_lines(self, texts: Sequence[Body], **kwargs: Any) -> tuple[list[int], bool]:
        self._threads.append(_thread_name())
        return self._inner.count_lines(texts, **kwargs)

    def hit_lines(self, texts: Sequence[Body], **kwargs: Any) -> tuple[list[list[MatchSpan]], bool]:
        self._threads.append(_thread_name())
        return self._inner.hit_lines(texts, **kwargs)


def _trace_verifiers(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[str]:
    """The thread of every batch call a matcher compiled through *module* makes."""
    threads: list[str] = []
    real = module.compile_verifier
    monkeypatch.setattr(module, "compile_verifier", lambda *a, **k: _TracingMatcher(real(*a, **k), threads))
    return threads


def _held(path: str, content: str) -> Observation:
    return Observation(path=Path(path), kind="file", content=content)


async def _needle_storage(tmp_path: Any) -> DatabaseStorage:
    storage = DatabaseStorage(url=_url(tmp_path))
    assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="a needle body")])).success is True
    return storage


def test_the_process_pool_is_lazy_shared_and_reminted(fresh_process_pool: None) -> None:
    """Guards: a pool made at import or one per caller, a width of its own, or a
    shutdown that keeps the dead pool in the slot so no later hop leaves the loop."""
    assert offload_module._pool is None
    first = offload_pool()
    assert offload_pool() is first
    assert offload_module._pool is first
    assert first._max_workers == OFFLOAD_WORKERS
    assert first.submit(_thread_name).result(timeout=5.0).startswith("vfs-offload")
    shutdown_offload_pool()
    assert offload_module._pool is None
    with pytest.raises(RuntimeError):
        first.submit(_thread_name)
    second = offload_pool()
    assert second is not first
    assert second.submit(_thread_name).result(timeout=5.0).startswith("vfs-offload")


async def test_every_hop_rides_the_process_pool(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: a hop left on a pool its owner makes, on the loop's default executor, or inline."""
    storage_threads = _trace_verifiers(monkeypatch, grep_module)
    router_threads = _trace_verifiers(monkeypatch, chain_module)
    measure_threads: list[str] = []
    real_measure = base_module.measure_text

    def measured(body: str) -> Any:
        measure_threads.append(_thread_name())
        return real_measure(body)

    monkeypatch.setattr(base_module, "measure_text", measured)
    storage = await _needle_storage(tmp_path)
    found = await storage.grep(pattern="needle", allow_scan=True)
    assert [str(row.path) for row in found.observations] == ["/a.txt"]
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    chained = await fs.grep("needle", observations=[_held("/b.txt", "a needle")])
    assert [str(row.path) for row in chained.observations] == ["/b.txt"]
    assert (await fs.write(path="/big.txt", content="x" * MEASURE_OFFLOAD_BYTES)).success is True
    await fs.close()
    for stage, threads in (("storage", storage_threads), ("router", router_threads), ("measure", measure_threads)):
        assert len(threads) == 1 and threads[0].startswith("vfs-offload"), (stage, threads)


async def test_close_leaves_the_process_pool_alone(tmp_path: Any, fresh_process_pool: None) -> None:
    """Guards: a close that shuts the pool every other caller shares, or one that mints a pool to shut."""
    idle = DatabaseStorage(url=_url(tmp_path))
    await idle.close()
    await AsyncVirtualFileSystem(storage=InMemoryStorage()).close()
    assert offload_module._pool is None

    built = await _needle_storage(tmp_path)
    assert len((await built.grep(pattern="needle", allow_scan=True)).observations) == 1
    pool = offload_module._pool
    assert pool is not None
    await built.close()
    assert offload_pool() is pool
    assert pool.submit(_thread_name).result(timeout=5.0).startswith("vfs-offload")

    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    assert len((await fs.grep("needle", observations=[_held("/b.txt", "a needle")])).observations) == 1
    await fs.close()
    assert offload_pool() is pool
    assert pool.submit(_thread_name).result(timeout=5.0).startswith("vfs-offload")


@pytest.mark.parametrize("verb", ["grep", "rebuild"])
async def test_a_hop_captured_before_shutdown_is_served_inline(
    verb: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, fresh_process_pool: None
) -> None:
    """Guards: the inline arm of the hop re-raising, so a builder holding a
    shut executor escapes a raw RuntimeError instead of finishing its work."""
    storage = DatabaseStorage(url=_url(tmp_path))
    entries = [Entry(path=Path(f"/f{i}.py"), content=f"def fn{i}():\n    return {i}\n") for i in range(3)]
    assert (await storage.write(entries=entries)).success is True
    threads = _trace_verifiers(monkeypatch, grep_module)
    seam_name = "grep:after-pointer-read"
    if verb == "rebuild":
        threads = []
        real = indexing_module._assess_and_split

        def tracing(*args: Any, **kwargs: Any) -> Any:
            threads.append(_thread_name())
            return real(*args, **kwargs)

        monkeypatch.setattr(indexing_module, "_assess_and_split", tracing)
        seam_name = "rebuild:before-chunk-split"

    async def shut() -> None:
        seams.clear(seam_name)
        shutdown_offload_pool()

    with seams.installed(seam_name, shut):
        raced = await (storage.rebuild() if verb == "rebuild" else storage.grep(pattern="return", allow_scan=True))
    assert raced.success is True, raced.errors
    assert threads == [threading.main_thread().name], threads
    # Every match, and after a rebuild every chunk: the index tier answers with no scan.
    found = raced if verb == "grep" else await storage.grep(pattern="return")
    assert found.success is True, found.errors
    assert sorted(str(row.path) for row in found.observations) == ["/f0.py", "/f1.py", "/f2.py"]


async def test_queued_work_at_shutdown_is_served_never_cancelled(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, fresh_process_pool: None
) -> None:
    """Guards: the shutdown passing ``cancel_futures=True``, so a batch queued
    behind a running one dies as a raw CancelledError instead of being served."""
    monkeypatch.setattr(offload_module, "OFFLOAD_WORKERS", 1)
    storage = await _needle_storage(tmp_path)
    gated = _GatedMatcher()
    real = grep_module.compile_verifier
    compiled = 0

    def gate_first(*args: Any, **kwargs: Any) -> Any:
        nonlocal compiled
        compiled += 1
        return gated if compiled == 1 else real(*args, **kwargs)

    monkeypatch.setattr(grep_module, "compile_verifier", gate_first)
    pool = offload_pool()
    first = asyncio.ensure_future(storage.grep(pattern="needle", allow_scan=True, output_mode="count"))
    await _until(gated.started.is_set)
    queued = asyncio.ensure_future(storage.grep(pattern="needle", allow_scan=True, output_mode="count"))
    await _until(lambda: pool._work_queue.qsize() >= 1)
    shutdown_offload_pool()
    gated.gate.set()
    result = await queued
    assert result.success is True, result.errors
    assert [str(row.path) for row in result.observations] == ["/a.txt"]
    assert (await first).success is True
    await _until(lambda: gated.finished)


# A parent makes a hop, then forks while another thread holds the pool's lock. The child
# exits 1 before any hop if it inherited the executor or a held lock, so a fault never hangs.
_FORK_SCRIPT = """
import json, os, threading
from vfs import offload

def thread_name():
    return threading.current_thread().name

parent_pool = offload.offload_pool()
assert parent_pool.submit(thread_name).result(timeout=30).startswith("vfs-offload")
held, release = threading.Event(), threading.Event()

def hold():
    with offload._lock:
        held.set()
        release.wait(30)

holder = threading.Thread(target=hold)
holder.start()
assert held.wait(30)
pid = os.fork()
if pid == 0:
    code = 3
    try:
        if offload._pool is not None or offload._lock.locked():
            code = 1
        else:
            child_pool = offload.offload_pool()
            name = child_pool.submit(thread_name).result(timeout=30)
            code = 0 if child_pool is not parent_pool and name.startswith("vfs-offload") else 2
    finally:
        os._exit(code)
release.set()
holder.join()
_, status = os.waitpid(pid, 0)
kept = offload.offload_pool() is parent_pool
print(json.dumps({"child_exit": os.waitstatus_to_exitcode(status), "parent_kept_its_pool": kept}))
"""


@pytest.mark.skipif(not hasattr(os, "fork"), reason="the platform has no fork to guard")
def test_a_forked_child_mints_its_own_pool() -> None:
    """Guards: the fork hook removed, or one that keeps the inherited executor or the inherited lock."""
    run = subprocess.run([sys.executable, "-c", _FORK_SCRIPT], capture_output=True, text=True, check=False, timeout=120)
    assert run.returncode == 0, run.stderr[-800:]
    assert json.loads(run.stdout) == {"child_exit": 0, "parent_kept_its_pool": True}
