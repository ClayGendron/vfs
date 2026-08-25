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
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.support.database_helpers import _url
from vfs.pattern_matching import compile_verifier
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.offload import VerifyOffload

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

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
    """A matcher double that blocks until its gate opens."""

    def __init__(self) -> None:
        self.gate = threading.Event()

    def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, budget: float | None
    ) -> tuple[list[int], bool]:
        assert self.gate.wait(timeout=5.0)
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
# Executor ownership and lifecycle
# ---------------------------------------------------------------------------


class TestExecutorOwnership:
    async def test_the_pool_is_lazy_and_minted_once(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        host = storage._host
        assert host._verify_executor is None
        first = host.verify_executor
        assert host.verify_executor is first
        await storage.close()

    async def test_close_shuts_the_pool_down_without_waiting(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        gate = threading.Event()
        storage._host.verify_executor.submit(gate.wait, 5.0)
        start = monotonic()
        await storage.close()
        assert monotonic() - start < 1.0
        gate.set()
        with pytest.raises(RuntimeError):
            storage._host.verify_executor.submit(time.sleep, 0)

    async def test_a_borrowed_host_still_shuts_its_own_pool(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        storage = DatabaseStorage(session_factory=factory)
        pool = storage._host.verify_executor
        await storage.close()
        with pytest.raises(RuntimeError):
            pool.submit(time.sleep, 0)
        await engine.dispose()

    async def test_close_without_a_grep_never_mints_the_pool(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.close()
        assert storage._host._verify_executor is None
