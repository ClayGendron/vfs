"""The verify offload seam — wrapper laws, executor ownership, lifecycle.

The wrapper's result parity with the direct call, the absolute deadline
crossing the hop (queue wait shortens the budget), the one-in-flight
guard, and the backend-owned pool's lazy birth and non-blocking death.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.paths import Path
from vfs.pattern_matching import compile_verifier
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database.offload import VerifyOffload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

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


@pytest.fixture
def pool() -> Iterator[ThreadPoolExecutor]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-verify")
    yield executor
    executor.shutdown(wait=True)


# ---------------------------------------------------------------------------
# The wrapper laws
# ---------------------------------------------------------------------------


class TestVerifyOffload:
    async def test_count_lines_matches_the_direct_call(self, pool: ThreadPoolExecutor) -> None:
        matcher = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        texts = ["a needle here\nno hit", "nothing", "needle\nneedle"]
        direct = matcher.count_lines(texts, cap=None, invert=False, budget=5.0)
        offloaded = await VerifyOffload(matcher, pool).count_lines(
            texts, cap=None, invert=False, deadline=monotonic() + 5.0
        )
        assert offloaded == direct

    async def test_hit_lines_matches_the_direct_call(self, pool: ThreadPoolExecutor) -> None:
        matcher = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        texts = ["a needle here\nno hit", "nothing", "needle\nneedle"]
        direct = matcher.hit_lines(texts, before=1, after=1, cap=None, invert=False, budget=5.0)
        offloaded = await VerifyOffload(matcher, pool).hit_lines(
            texts, before=1, after=1, cap=None, invert=False, deadline=monotonic() + 5.0
        )
        assert offloaded == direct

    async def test_queue_wait_shortens_the_budget_never_the_wall(self, pool: ThreadPoolExecutor) -> None:
        """Guards: the budget cut moves to submit time (deadline - monotonic()
        hoisted out of the worker fn), silently extending the wall by the
        queue wait."""
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        pool.submit(time.sleep, 0.5)
        await offload.count_lines(["text"], cap=None, invert=False, deadline=monotonic() + 0.6)
        assert matcher.budgets and matcher.budgets[0] <= 0.35

    async def test_hit_lines_budget_is_cut_at_worker_start_too(self, pool: ThreadPoolExecutor) -> None:
        """Guards: the same submit-time hoist on the hit_lines arm."""
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        pool.submit(time.sleep, 0.5)
        await offload.hit_lines(["text"], before=0, after=0, cap=None, invert=False, deadline=monotonic() + 0.6)
        assert matcher.budgets and matcher.budgets[0] <= 0.35

    async def test_overlapping_calls_are_refused(self, pool: ThreadPoolExecutor) -> None:
        """Guards: the one-in-flight guard is deleted, letting a second batch
        race the first onto the pool."""
        matcher = _GatedMatcher()
        offload = VerifyOffload(matcher, pool)
        first = asyncio.ensure_future(offload.count_lines(["a"], cap=None, invert=False, deadline=monotonic() + 5.0))
        await asyncio.sleep(0.05)
        with pytest.raises(RuntimeError, match="one batch in flight"):
            await offload.count_lines(["b"], cap=None, invert=False, deadline=monotonic() + 5.0)
        matcher.gate.set()
        counts, completed = await first
        assert counts == [0] and completed is True

    async def test_the_guard_clears_when_the_worker_drains(self, pool: ThreadPoolExecutor) -> None:
        matcher = _RecordingMatcher()
        offload = VerifyOffload(matcher, pool)
        for _ in range(2):
            counts, completed = await offload.count_lines(["a"], cap=None, invert=False, deadline=monotonic() + 5.0)
            assert counts == [1] and completed is True
        assert len(matcher.budgets) == 2


# ---------------------------------------------------------------------------
# The proof: the loop keeps ticking while verify runs
# ---------------------------------------------------------------------------


class _SleepingMatcher:
    """A matcher double whose work releases the GIL — the engines' shape."""

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        time.sleep(1.0)
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
        time.sleep(1.0)
        return [[] for _ in texts], True


class TestLoopResponsiveness:
    async def test_the_loop_keeps_ticking_while_verify_runs(self, pool: ThreadPoolExecutor) -> None:
        """Guards: `_run` calls the work inline instead of through the pool,
        holding the loop for the whole batch."""
        offload = VerifyOffload(_SleepingMatcher(), pool)
        gaps: list[float] = []

        async def tick() -> None:
            last = monotonic()
            while True:
                await asyncio.sleep(0.01)
                now = monotonic()
                gaps.append(now - last)
                last = now

        ticker = asyncio.ensure_future(tick())
        counts, completed = await offload.count_lines(["a"], cap=None, invert=False, deadline=monotonic() + 5.0)
        ticker.cancel()
        assert counts == [1] and completed is True
        assert gaps and max(gaps) < 0.5


# ---------------------------------------------------------------------------
# Cancellation is abandonment made safe
# ---------------------------------------------------------------------------


class TestAbandonment:
    async def test_a_cancelled_await_returns_while_the_worker_drains_into_the_void(
        self, pool: ThreadPoolExecutor
    ) -> None:
        matcher = _GatedMatcher()
        offload = VerifyOffload(matcher, pool)
        task = asyncio.ensure_future(offload.count_lines(["a"], cap=None, invert=False, deadline=monotonic() + 5.0))
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
        task = asyncio.ensure_future(offload.count_lines(["a"], cap=None, invert=False, deadline=monotonic() + 5.0))
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
        task = asyncio.ensure_future(first.count_lines(["a"], cap=None, invert=False, deadline=monotonic() + 5.0))
        await _until(abandoned.started.is_set)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        matcher = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
        second = VerifyOffload(matcher, pool)
        successor = asyncio.ensure_future(
            second.count_lines(["a needle", "no hit"], cap=None, invert=False, deadline=monotonic() + 5.0)
        )
        abandoned.gate.set()
        counts, completed = await successor
        assert counts == [1, 0] and completed is True
        await _until(lambda: abandoned.finished)

    async def test_a_cancelled_grep_leaves_the_next_call_whole(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # The end-to-end law: the abandoned worker holds only its batch —
        # the cancelled call's session closed under it, and the reissued
        # grep answers correctly while that worker still drains.
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
        with pytest.raises(asyncio.CancelledError):
            await task
        result = await storage.grep(pattern="needle", allow_scan=True, output_mode="count")
        assert [str(row.path) for row in result.observations] == ["/a.txt"]
        gated.gate.set()
        await _until(lambda: gated.finished)
        await storage.close()


# ---------------------------------------------------------------------------
# Executor ownership and lifecycle
# ---------------------------------------------------------------------------


class TestExecutorOwnership:
    async def test_the_pool_is_lazy_and_minted_once(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        host = storage._host
        assert host._offload_executor is None
        first = host.offload_executor
        assert host.offload_executor is first
        await storage.close()

    async def test_close_shuts_the_pool_down_without_waiting(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        gate = threading.Event()
        pool = storage._host.offload_executor
        pool.submit(gate.wait, 5.0)
        start = monotonic()
        await storage.close()
        assert monotonic() - start < 1.0
        gate.set()
        with pytest.raises(RuntimeError):
            pool.submit(time.sleep, 0)
        # The slot is cleared, never left holding the dead pool: the
        # next grep re-mints fresh (the sibling serve-after-close law).
        assert storage._host._offload_executor is None
        assert storage._host.offload_executor is not pool
        await storage.close()

    async def test_a_pool_minted_after_close_is_shut_by_the_next_close(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.close()
        reminted = storage._host.offload_executor
        assert reminted.submit(time.sleep, 0).result(timeout=5.0) is None
        await storage.close()
        with pytest.raises(RuntimeError):
            reminted.submit(time.sleep, 0)
        assert storage._host._offload_executor is None

    async def test_a_grep_racing_close_is_served_whole(self, tmp_path) -> None:
        # close lands mid-grep, after the call captured its pool: the
        # shut pool serves the batch inline — a classified Result comes
        # back, never a raw "cannot schedule new futures" escape.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])).success is True
        warm = await storage.grep(pattern="needle")
        assert warm.success is True

        async def closer() -> None:
            seams.clear("grep:after-pointer-read")
            await storage.close()

        with seams.installed("grep:after-pointer-read", closer):
            raced = await storage.grep(pattern="needle")
        assert raced.success is True, raced.errors
        assert [str(o.path) for o in raced.observations] == ["/a.txt"]

    async def test_a_borrowed_host_still_shuts_its_own_pool(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        storage = DatabaseStorage(session_factory=factory)
        pool = storage._host.offload_executor
        await storage.close()
        with pytest.raises(RuntimeError):
            pool.submit(time.sleep, 0)
        await engine.dispose()

    async def test_close_without_a_grep_never_mints_the_pool(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.close()
        assert storage._host._offload_executor is None

    async def test_queued_work_at_close_is_served_never_cancelled(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Close lands with one batch running and one queued on a one-worker
        # pool: the queued grep must be served whole, never cancelled.
        monkeypatch.setattr(engine_module, "OFFLOAD_WORKERS", 1)
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="a needle body")])).success is True
        gated = _GatedMatcher()
        real = grep_module.compile_verifier
        compiled = 0

        def gate_first(*args: Any, **kwargs: Any) -> Any:
            nonlocal compiled
            compiled += 1
            return gated if compiled == 1 else real(*args, **kwargs)

        monkeypatch.setattr(grep_module, "compile_verifier", gate_first)
        pool = storage._host.offload_executor
        first = asyncio.ensure_future(storage.grep(pattern="needle", allow_scan=True, output_mode="count"))
        await _until(gated.started.is_set)
        queued = asyncio.ensure_future(storage.grep(pattern="needle", allow_scan=True, output_mode="count"))
        await _until(lambda: pool._work_queue.qsize() >= 1)
        await storage.close()
        gated.gate.set()
        result = await queued
        assert result.success is True, result.errors
        assert [str(row.path) for row in result.observations] == ["/a.txt"]
        assert (await first).success is True
        await _until(lambda: gated.finished)
