"""The deadline every bounded stage takes: one absolute instant, read through one value.

The law: a relative budget becomes an absolute instant once, at a
stage's entry, and the time left is derived from that instant wherever
it is needed. A stage never carries seconds around and never adds them
to the clock a second time, so time spent queued for a worker, or spent
in an earlier step, shortens what is left and never extends the wall.

    deadline = Deadline.after(WALL_TIME_BUDGET)   # at the stage's entry
    for chunk in deadline.chunks(rows):           # one clock read per chunk
        ...
    budget = deadline.remaining()                 # cut where a worker starts

A deadline is passed as an argument and never stored on a long-lived
object. This module reads the clock for every stage that bounds its
work, so a test drives all of them through one fake clock patched here.
It imports the standard library only: every layer of the package may
take a deadline, so it sits beneath them all.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from time import monotonic
from typing import TYPE_CHECKING, Final, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# Spelled pre-PEP-695: type-parameter syntax is 3.12+, above the floor.
T = TypeVar("T")

# The wall every row-matching stage runs under, in seconds: storage grep,
# glob and search by default, and each of the router's matching stages.
WALL_TIME_BUDGET: Final = 10.0

# The wall's cause in a truncation record, the same words at every site that writes it.
WALL_TIME_CAUSE: Final = "wall-time budget"

# Items a loop takes between two reads of the clock. A stage names a size of
# its own only with a comment saying how long one of its items can take.
CHECK_EVERY: Final = 64


@dataclass(frozen=True, slots=True)
class Deadline:
    """An absolute instant on the monotonic clock before which a stage must finish, or none.

    Built at a stage's entry by :meth:`after` or :meth:`never`; a test
    builds one that has already passed as ``Deadline(at=-1.0)``.
    """

    at: float | None

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        """The deadline *seconds* from now, the clock read once."""
        return cls(at=monotonic() + seconds)

    @classmethod
    def never(cls) -> Deadline:
        """No deadline: it never expires, has no budget to cut, and reads no clock."""
        return cls(at=None)

    def remaining(self) -> float | None:
        """The seconds left, never negative; ``None`` when there is no deadline."""
        if self.at is None:
            return None
        return max(0.0, self.at - monotonic())

    def expired(self) -> bool:
        """Whether the clock is strictly past the instant; never, with no deadline."""
        return self.at is not None and monotonic() > self.at

    def chunks(self, items: Iterable[T], size: int = CHECK_EVERY) -> Iterator[list[T]]:
        """*items* in lists of at most *size*, the clock read once before each, stopping at the deadline.

        The iterable is consumed a chunk at a time and never
        materialized. The stop carries no signal: a caller that must
        know whether every item was reached counts what it consumed
        against what it gave.
        """
        iterator = iter(items)
        while not self.expired():
            chunk = list(islice(iterator, size))
            if not chunk:
                return
            yield chunk
