"""The byte batcher: items cut into batches by a byte budget the caller names.

The flush law: items accumulate until adding the next would pass the
budget, and the full batch is flushed *before* that add. One item larger
than the budget rides alone, so the budget bounds how much is held at
once and never decides what is eligible or what is returned.

    for batch in byte_chunked(bodies, len, 32 * 1024 * 1024):
        ...

Its callers size two different things with it: the payload of one hop
to a worker, and the bytes one SQL statement fetches. It imports the
standard library only, so the chained filters and the database adapter
both import it downward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

# Spelled pre-PEP-695: type-parameter syntax is 3.12+, above the floor.
T = TypeVar("T")


class ByteBatcher(Generic[T]):
    """Byte-bounded singleton-exempt accumulator — the flush law's one owner.

    Items accumulate until adding the next would exceed *budget*, at
    which point the full batch flushes *before* the add (bound =
    ``max(budget, one item)``): one oversized item rides alone, so the
    budget shapes transient residency, never eligibility or results.
    *size_of* is the caller's declared metering — exact bytes where it
    has them, chars-as-proxy where it declares one. This incremental
    form serves streaming producers (an async row scan cannot feed a
    sync generator); sequence callers use :func:`byte_chunked`.
    """

    def __init__(self, size_of: Callable[[T], int], budget: int) -> None:
        self._size_of = size_of
        self._budget = budget
        self._batch: list[T] = []
        self._total = 0

    def add(self, item: T) -> list[T] | None:
        """Accumulate *item*; return the batch the flush law completed, if any."""
        size = self._size_of(item)
        full = None
        if self._batch and self._total + size > self._budget:
            full = self._batch
            self._batch, self._total = [], 0
        self._batch.append(item)
        self._total += size
        return full

    def flush(self) -> list[T] | None:
        """Return the final partial batch, or ``None`` when nothing is held."""
        batch = self._batch or None
        self._batch, self._total = [], 0
        return batch


def byte_chunked(items: Iterable[T], size_of: Callable[[T], int], budget: int) -> Iterator[list[T]]:
    """Slices of *items* whose summed *size_of* fits *budget*, in order.

    The byte-bounded twin of
    :func:`vfs.storage.backends.database.dialects.chunked`: every item
    is emitted in exactly one batch, concatenation preserves order, and
    the :class:`ByteBatcher` flush law bounds each batch at
    ``max(budget, one item)``.
    """
    batcher: ByteBatcher[T] = ByteBatcher(size_of, budget)
    for item in items:
        full = batcher.add(item)
        if full is not None:
            yield full
    final = batcher.flush()
    if final is not None:
        yield final
