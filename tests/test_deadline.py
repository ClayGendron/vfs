"""The deadline value: an absolute instant, the budget left, and the chunked clock read.

Every node drives a fake clock patched on ``vfs.deadline.monotonic`` and
asserts states and read counts, never elapsed time.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import FrozenInstanceError

import pytest

from vfs import deadline as deadline_module
from vfs.deadline import CHECK_EVERY, WALL_TIME_BUDGET, WALL_TIME_CAUSE, Deadline


class _Clock:
    """A fake monotonic clock that counts its reads and passes *late* after *early_reads* of them."""

    def __init__(self, now: float = 0.0, *, late: float | None = None, early_reads: int = 0) -> None:
        self.now = now
        self.reads = 0
        self._late = late
        self._early_reads = early_reads

    def __call__(self) -> float:
        self.reads += 1
        if self._late is not None and self.reads > self._early_reads:
            return self._late
        return self.now


def _patched(monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> _Clock:
    monkeypatch.setattr(deadline_module, "monotonic", clock)
    return clock


def test_the_constants_are_the_wall_and_the_cadence() -> None:
    assert (WALL_TIME_BUDGET, WALL_TIME_CAUSE, CHECK_EVERY) == (10.0, "wall-time budget", 64)


def test_a_deadline_is_absolute_and_never_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: ``expired`` comparing with ``>=``, ``remaining`` going negative past the
    instant, or a never-deadline answering a budget."""
    clock = _patched(monkeypatch, _Clock(1000.0))
    deadline = Deadline.after(10.0)
    assert deadline.at == 1010.0
    assert deadline.expired() is False
    clock.now = 1010.0
    assert deadline.expired() is False
    clock.now = math.nextafter(1010.0, math.inf)
    assert deadline.expired() is True

    never = Deadline.never()
    for now in (0.0, 1e12, math.inf):
        clock.now = now
        assert never.expired() is False
        assert never.remaining() is None

    clock.now = 1000.0
    five = Deadline.after(5.0)
    clock.now = 1002.0
    assert five.remaining() == 3.0
    clock.now = 1007.0
    assert five.remaining() == 0.0

    clock.now = 1000.0
    unbounded = Deadline.after(math.inf)
    clock.now = 1e300
    assert unbounded.expired() is False
    assert unbounded.remaining() == math.inf


def test_the_clock_is_read_once_per_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: ``after`` reading the clock twice, or a never-deadline reading it at all."""
    clock = _patched(monkeypatch, _Clock(50.0))
    deadline = Deadline.after(1.0)
    assert clock.reads == 1
    deadline.expired()
    deadline.remaining()
    assert clock.reads == 3
    never = Deadline.never()
    never.expired()
    never.remaining()
    assert clock.reads == 3


def test_a_deadline_built_at_an_instant_is_already_past(monkeypatch: pytest.MonkeyPatch) -> None:
    _patched(monkeypatch, _Clock(0.0))
    past = Deadline(at=-1.0)
    assert past.expired() is True
    assert past.remaining() == 0.0


def test_a_deadline_is_a_frozen_value() -> None:
    deadline = Deadline(at=1.0)
    assert deadline == Deadline(at=1.0)
    assert Deadline.never() == Deadline(at=None)
    with pytest.raises(FrozenInstanceError):
        deadline.at = 2.0  # ty: ignore[invalid-assignment]


def test_chunks_read_the_clock_once_per_chunk_and_stop_at_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the clock read per item instead of per chunk, a chunk yielded past the
    deadline, the trailing short chunk dropped, or a never-deadline reading the clock."""
    _patched(monkeypatch, _Clock(0.0))
    deadline = Deadline.after(1.0)

    clock = _patched(monkeypatch, _Clock(0.0, late=2.0, early_reads=3))
    chunks = list(deadline.chunks(range(1000)))
    assert [len(chunk) for chunk in chunks] == [64, 64, 64]
    assert [item for chunk in chunks for item in chunk] == list(range(192))
    assert clock.reads == 4

    clock = _patched(monkeypatch, _Clock(0.0, late=2.0, early_reads=3))
    assert [len(chunk) for chunk in deadline.chunks(range(1000), size=100)] == [100, 100, 100]
    assert clock.reads == 4

    clock = _patched(monkeypatch, _Clock(0.0))
    pairs = list(deadline.chunks(itertools.product(range(10), range(10))))
    assert [len(chunk) for chunk in pairs] == [64, 36]
    assert [pair for chunk in pairs for pair in chunk] == list(itertools.product(range(10), range(10)))
    assert clock.reads == 3

    clock = _patched(monkeypatch, _Clock(0.0))
    assert [len(chunk) for chunk in Deadline.never().chunks(range(100))] == [64, 36]
    assert clock.reads == 0


def test_chunks_never_materialize_their_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the items listed whole before the first chunk, or an item taken past the deadline."""
    _patched(monkeypatch, _Clock(0.0))
    endless = Deadline.never().chunks(itertools.count())
    assert next(endless) == list(range(64))
    assert next(endless) == list(range(64, 128))

    items = iter(range(10))
    assert list(Deadline(at=-1.0).chunks(items)) == []
    assert next(items) == 0


def test_chunks_of_nothing_yield_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _patched(monkeypatch, _Clock(0.0))
    assert list(Deadline.after(1.0).chunks([])) == []
    assert clock.reads == 2
    exact = list(Deadline.after(1.0).chunks(range(128)))
    assert [len(chunk) for chunk in exact] == [64, 64]
