"""CPU-bound work leaves the event loop: the backend's offload seam.

Five kinds of work run real CPU inside their coroutines — grep's verify
stage (up to a full wall budget of matching per call), reindex's chunk
and posting stages, write's measurement of a call's bodies past the
inline total, edit's per-target matching, and glob gating: every stage
that matches rows against the glob channels (glob, grep and glean in
storage, and the router's chained calls, root probe and admissions) —
and running any inline holds the event loop against every concurrent
caller on the host. All hop through one small executor the backend
owns: :func:`call_offloaded` is the shared hop (submit, await, and the
close-window inline fallback), :class:`VerifyOffload` decorates a
compiled :class:`~vfs.pattern_matching.ContentMatcher` over it so each
per-batch ``count_lines``/``hit_lines`` call runs on a worker thread
while the loop keeps ticking, and :func:`judge_rows` judges one stage's
rows against a call's :class:`~vfs.pattern_matching.GlobGates` in one
hop. The router's residual walk, which plans a scoped fan-out by
matching pattern components against bind paths, hops too. Engines stay
synchronous and thread-ignorant: this seam, the router's body-measure
hop (a large write's sha256 on the loop's default executor,
``vfs.base``) and the router's verify pool (``OFFLOAD_WORKERS`` threads
of its own for chained grep, glob judging and planning, shut by its
``close``, riding :func:`call_offloaded`) are the tree's only deliberate
threads — declared exceptions, owned there.

Four laws govern the hop:

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
  is the batch it holds, bounded by the batcher's content-byte budget
  (a module constant, 32 MiB) *or one body, whichever is larger* — the
  batcher's singleton exemption sends an oversized body through alone.
  grep meters that budget in exact stored bytes; the reindex batchers
  and the router's chained grep riding the same hop meter characters
  as a declared ASCII-dominant proxy, so an abandoned batch of theirs
  can hold up to 4x the budget in UTF-8 bytes on CJK or emoji text
  (measured 3.00x/4.00x).
  write's measurement hop holds the call's own bodies, which its
  caller already holds; an abandoned edit hop finishes matching its
  remaining targets, holding one worker for up to its targets times the
  per-match budget; an abandoned judge hop finishes into the void
  within its wall, holding the call's rows and its set, which its
  caller already holds. No protocol-level interrupt exists.
- **The pool follows the host's close, and calls survive it.** A call
  that captured its pool before close serves every remaining hop it
  holds inline once the pool is shut — grep its remaining verify
  batches, reindex its chunk pass's whole split or its build's
  remaining feeds and drains — never a raw escape. The exposure is
  verb-sized, not batch-sized (executed: a reindex racing close at
  20,000 files ran its split 1.56 s on the loop, correctly), and it
  is the closer's cost to bear; only the next capture — the next
  verb, or reindex's next phase — re-mints a fresh pool from the host.
  A judge hop served inline after ``close()`` may wait on its gates'
  build lock while a worker builds the set, the closer's cost to bear.

On the Rust engine the matcher detaches the GIL for the whole batch,
so the offload removes loop occupancy wholesale; on the pure engine it
bounds stalls at the longest single ``re`` call — one backtracking
episode is a single GIL-holding C call no thread can interrupt, a
disclosed residual settled by engine choice. edit's matching is pure
Python and holds the GIL, so its hop bounds loop stalls at the
interpreter's switch interval rather than removing them; the Rust
kernel is the direction. The same holds for the glob set's atom walk,
which builds each pattern's program in Python before the native
construction releases the GIL, and for the router's residual walk,
pure Python on its worker: both hold the GIL in turns, and the loop
serves other calls between them. Glob judging itself releases the GIL
for the whole batch. The hop itself costs ~40 µs per batch call —
noise against a batch's matching work.
"""

from __future__ import annotations

import asyncio
import os
from time import monotonic
from typing import TYPE_CHECKING, Final, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from concurrent.futures import Executor

    from vfs.pattern_matching import Body, ContentMatcher, GlobGates
    from vfs.pattern_matching.glob import GlobRow
    from vfs.pattern_matching.grep import MatchSpan

T = TypeVar("T")

# The wall every row-matching stage runs under, in seconds: storage grep,
# glob and glean by default, and each of the router's matching stages.
WALL_TIME_BUDGET: Final = 10.0

# The wall's cause in a truncation record, the same words at every site that writes it.
WALL_TIME_CAUSE: Final = "wall-time budget"

# Offload pool width: available parallelism, no knob. Measured (10-core,
# 32 MiB batches): throughput plateaus by 4 workers and holds flat at
# cores — rayon inside one native call already saturates the CPUs, and
# co-running callers queue cleanly; only past-cores oversubscription
# degrades, and this size never oversubscribes.
OFFLOAD_WORKERS: Final = os.cpu_count() or 1


async def call_offloaded(executor: Executor, work: Callable[[], T]) -> T:
    """Run *work* on *executor*, a backend's pool or the router's verify pool; the loop keeps ticking.

    The one hop every offloaded stage takes. A pool shut by ``close()``
    serves the work inline — and a call that captured the pool serves
    *all* its remaining hops that way, verb-sized, never a raw escape;
    the next capture re-mints a fresh pool from the host.
    """
    try:
        future = executor.submit(work)
    except RuntimeError:
        return work()
    return await asyncio.wrap_future(future)


async def judge_rows(
    executor: Executor, gates: GlobGates, rows: Sequence[GlobRow], *, deadline: float
) -> tuple[list[int | None], bool]:
    """Every row's verdict against *gates*, judged in one hop; and whether every row was judged.

    The hop builds the gates' native set if no earlier hop has, then
    cuts the budget at ``deadline - monotonic()``, so time queued for a
    thread and time spent building both shorten it, and neither extends
    the wall. A build that reached the deadline answers every row
    unjudged (``None``). With no rows, or gates that hold no pattern (the
    ext facts need no engine), no hop is made: the verdicts are ``[]``
    or ``0`` per row, and judging is complete whatever the clock reads.

    Gates with a scope also build its pairs in the same worker, one per
    covering root, and judge them against the scope's set
    (:meth:`~vfs.pattern_matching.GlobGates.judge_scope`), the deadline
    read every 64 rows; a row not reached is unjudged.
    """
    if not rows:
        return [], True
    if not gates.has_patterns:
        return [0] * len(rows), True

    def work() -> tuple[list[int | None], bool]:
        verdicts: list[int | None] = [0] * len(rows)
        completed = True
        if gates.has_entry_patterns:
            native = gates.native(deadline)
            if native is None:
                return [None] * len(rows), False
            budget = max(0.0, deadline - monotonic())
            verdicts, completed = native.judge(rows, budget=budget)
        if not gates.scoped:
            return verdicts, completed
        joined, paired = gates.judge_scope(rows, verdicts, deadline=deadline)
        return joined, completed and paired

    return await call_offloaded(executor, work)


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

        return await call_offloaded(self._executor, guarded)
