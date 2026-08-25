"""Verify leaves the event loop: the matcher offload seam.

The verify stage is CPU-bound — up to a full wall budget of matching
per grep call — and running it inline holds the event loop against
every concurrent caller on the host. :class:`VerifyOffload` decorates a
compiled :class:`~vfs.pattern_matching.ContentMatcher` so each
per-batch ``count_lines``/``hit_lines`` call runs on a worker thread
from a small executor the backend owns, while the loop keeps ticking.
Engines stay synchronous and thread-ignorant: the wrapper is the only
threaded code, and these are the tree's only deliberate threads — a
declared exception, owned here.

Three laws govern the hop:

- **The deadline crosses absolute.** The wrapper takes the caller's
  absolute deadline and computes the relative budget at *worker start*,
  so time spent queued behind a busy pool shortens the budget instead
  of silently extending the wall.
- **One batch in flight per instance.** The grep batch loop awaits
  each call before issuing the next; the wrapper enforces that shape
  structurally and refuses overlap loudly.
- **Cancellation is abandonment made safe.** A cancelled await returns
  immediately; a worker already running finishes into the void — it
  touches no session, its results are dropped, and its only residency
  is the batch it holds (bounded by the caller's content-byte budget,
  ≤32 MiB). No protocol-level interrupt exists.
- **The pool follows the host's close, and calls survive it.** A call
  that races close and finds its pool shut serves the batch inline —
  one on-loop batch in the close window, never a raw escape — and the
  next grep re-mints a fresh pool from the host.

On the Rust engine the matcher detaches the GIL for the whole batch,
so the offload removes loop occupancy wholesale; on the pure engine it
bounds stalls at the longest single ``re`` call — one backtracking
episode is a single GIL-holding C call no thread can interrupt, a
disclosed residual settled by engine choice. The hop itself costs
~40 µs per batch call — noise against a batch's matching work.
"""

from __future__ import annotations

import asyncio
import os
from time import monotonic
from typing import TYPE_CHECKING, Final, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from concurrent.futures import Executor

    from vfs.pattern_matching import Body, ContentMatcher
    from vfs.pattern_matching.grep import MatchSpan

T = TypeVar("T")

# Verify pool width: available parallelism, no knob. Measured (10-core,
# 32 MiB batches): throughput plateaus by 4 workers and holds flat at
# cores — rayon inside one native call already saturates the CPUs, and
# co-running callers queue cleanly; only past-cores oversubscription
# degrades, and this size never oversubscribes.
VERIFY_WORKERS: Final = os.cpu_count() or 1


class VerifyOffload:
    """One grep call's matcher, delegated to a worker per batch call.

    Minted per grep call, never shared: the one-in-flight guard is
    per-instance state, and an instance whose await was cancelled is
    abandoned with its worker — the redrive mints a fresh one.
    """

    def __init__(self, matcher: ContentMatcher, executor: Executor) -> None:
        self._matcher = matcher
        self._executor = executor
        self._in_flight = False

    async def count_lines(
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, deadline: float
    ) -> tuple[list[int], bool]:
        """`ContentMatcher.count_lines` off-loop, budget cut at worker start."""

        def work() -> tuple[list[int], bool]:
            budget = max(0.0, deadline - monotonic())
            return self._matcher.count_lines(texts, cap=cap, invert=invert, budget=budget)

        return await self._run(work)

    async def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        deadline: float,
    ) -> tuple[list[list[MatchSpan]], bool]:
        """`ContentMatcher.hit_lines` off-loop, budget cut at worker start."""

        def work() -> tuple[list[list[MatchSpan]], bool]:
            budget = max(0.0, deadline - monotonic())
            return self._matcher.hit_lines(texts, before=before, after=after, cap=cap, invert=invert, budget=budget)

        return await self._run(work)

    async def _run(self, work: Callable[[], T]) -> T:
        if self._in_flight:
            raise RuntimeError("VerifyOffload holds one batch in flight; overlapping calls break the verify law")
        self._in_flight = True

        def guarded() -> T:
            # Cleared worker-side: an abandoned worker is still in flight
            # until it drains, so the guard follows the thread, not the await.
            try:
                return work()
            finally:
                self._in_flight = False

        try:
            future = self._executor.submit(guarded)
        except RuntimeError:
            # close() shut this pool mid-call: serve the batch inline —
            # one on-loop batch in the close window, never a raw escape.
            return guarded()
        return await asyncio.wrap_future(future)
