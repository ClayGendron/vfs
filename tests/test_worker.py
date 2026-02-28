"""Tests for BackgroundWorker — debounced background task scheduling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grover.worker import BackgroundWorker, IndexingMode

if TYPE_CHECKING:
    import pytest


class TestBackgroundWorker:
    """Unit tests for BackgroundWorker in isolation."""

    async def test_schedule_runs_in_background(self) -> None:
        """Scheduled work executes after drain."""
        worker = BackgroundWorker()
        ran = []

        async def work() -> None:
            ran.append(True)

        worker.schedule("key", lambda: work())
        assert len(ran) == 0
        await worker.drain()
        assert len(ran) == 1

    async def test_debounce_coalesces(self) -> None:
        """Rapid calls to same key -> only latest runs."""
        worker = BackgroundWorker(debounce_delay=0.05)
        calls: list[int] = []

        for i in range(5):
            worker.schedule("key", lambda v=i: _record(calls, v))
        await worker.drain()
        assert calls == [4]  # Last one wins

    async def test_debounce_different_keys(self) -> None:
        """Different keys run independently."""
        worker = BackgroundWorker(debounce_delay=0.05)
        calls: list[str] = []

        worker.schedule("a", lambda: _record_str(calls, "a"))
        worker.schedule("b", lambda: _record_str(calls, "b"))
        await worker.drain()
        assert sorted(calls) == ["a", "b"]

    async def test_cancel_removes_pending(self) -> None:
        """cancel(key) prevents execution."""
        worker = BackgroundWorker(debounce_delay=10.0)
        ran = []

        async def work() -> None:
            ran.append(True)

        worker.schedule("key", lambda: work())
        assert worker.pending_count >= 1
        worker.cancel("key")
        assert worker.pending_count == 0
        await worker.drain()
        assert len(ran) == 0

    async def test_cancel_nonexistent_is_noop(self) -> None:
        """cancel() on unknown key does nothing."""
        worker = BackgroundWorker()
        worker.cancel("no-such-key")  # Should not raise

    async def test_schedule_immediate_no_debounce(self) -> None:
        """schedule_immediate runs immediately without waiting for delay."""
        worker = BackgroundWorker(debounce_delay=10.0)  # Very long delay
        ran = []

        async def work() -> None:
            ran.append(True)

        worker.schedule_immediate(work())
        await worker.drain()
        assert len(ran) == 1

    async def test_manual_mode_is_noop(self) -> None:
        """schedule/schedule_immediate do nothing in MANUAL mode."""
        worker = BackgroundWorker(indexing_mode=IndexingMode.MANUAL)
        ran = []

        async def work() -> None:
            ran.append(True)

        worker.schedule("key", lambda: work())
        worker.schedule_immediate(work())
        await worker.drain()
        assert len(ran) == 0

    async def test_drain_fires_all_pending(self) -> None:
        """drain() flushes everything."""
        worker = BackgroundWorker(debounce_delay=10.0)
        calls: list[str] = []

        for i in range(10):
            worker.schedule(f"k{i}", lambda v=i: _record_str(calls, f"k{v}"))
        assert worker.pending_count >= 10
        await worker.drain()
        assert worker.pending_count == 0
        assert len(calls) == 10

    async def test_drain_handles_cascading_work(self) -> None:
        """Work scheduled during drain is also drained."""
        worker = BackgroundWorker()
        order: list[str] = []

        async def first() -> None:
            order.append("first")
            worker.schedule("second", lambda: second())

        async def second() -> None:
            order.append("second")

        worker.schedule("first", lambda: first())
        await worker.drain()
        assert order == ["first", "second"]

    async def test_exception_isolation(self) -> None:
        """Failing task doesn't crash worker or other tasks."""
        worker = BackgroundWorker()
        ran = []

        async def failing() -> None:
            raise RuntimeError("boom")

        async def good() -> None:
            ran.append(True)

        worker.schedule_immediate(failing())
        worker.schedule_immediate(good())
        await worker.drain()
        assert len(ran) == 1

    async def test_pending_count(self) -> None:
        """Tracks pending + active correctly."""
        worker = BackgroundWorker(debounce_delay=10.0)

        async def noop() -> None:
            pass

        worker.schedule("a", lambda: noop())
        worker.schedule("b", lambda: noop())
        assert worker.pending_count == 2
        await worker.drain()
        assert worker.pending_count == 0

    async def test_indexing_mode_property(self) -> None:
        """indexing_mode reflects constructor arg."""
        bg = BackgroundWorker(indexing_mode=IndexingMode.BACKGROUND)
        assert bg.indexing_mode == IndexingMode.BACKGROUND

        manual = BackgroundWorker(indexing_mode=IndexingMode.MANUAL)
        assert manual.indexing_mode == IndexingMode.MANUAL

    async def test_schedule_replaces_pending(self) -> None:
        """Scheduling same key replaces the pending work."""
        worker = BackgroundWorker(debounce_delay=10.0)
        calls: list[int] = []

        worker.schedule("key", lambda: _record(calls, 1))
        worker.schedule("key", lambda: _record(calls, 2))
        assert worker.pending_count == 1  # Only one pending entry
        await worker.drain()
        assert calls == [2]  # Second one runs

    async def test_exception_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Failing task should log a warning."""
        import logging

        worker = BackgroundWorker()

        async def failing() -> None:
            raise RuntimeError("test-error-msg")

        with caplog.at_level(logging.WARNING, logger="grover.worker"):
            worker.schedule_immediate(failing())
            await worker.drain()

        assert "test-error-msg" in caplog.text

    async def test_factory_exception_isolation(self, caplog: pytest.LogCaptureFixture) -> None:
        """A factory that raises should not crash drain or prevent other work."""
        import logging

        worker = BackgroundWorker(debounce_delay=0.05)
        ran = []

        def bad_factory() -> None:
            raise RuntimeError("factory-boom")

        async def good() -> None:
            ran.append(True)

        worker.schedule("bad", bad_factory)  # type: ignore[arg-type]
        worker.schedule("good", lambda: good())

        with caplog.at_level(logging.WARNING, logger="grover.worker"):
            await worker.drain()

        assert len(ran) == 1
        assert "factory-boom" in caplog.text


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _record(calls: list[int], value: int) -> None:
    calls.append(value)


async def _record_str(calls: list[str], value: str) -> None:
    calls.append(value)
