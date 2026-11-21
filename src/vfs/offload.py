"""CPU-bound work leaves the event loop: the one process pool and the hop every stage takes.

A stage that runs real CPU inside its coroutine holds the event loop
against every other caller on the host: grep's verify stage, rebuild's
chunk and posting stages, a large write's measurement, edit's matching,
glob judging in storage and in the router, and the router's chained
grep and planning walk. Each hands its work to :func:`call_offloaded`
on the one pool :func:`offload_pool` makes for the whole process.
:class:`VerifyOffload` runs a compiled matcher's batches on a worker,
:func:`judge_rows` judges one stage's rows against a call's glob gates
in one hop, and :func:`wall_truncation` mints the record a stage writes
when its wall stops it.

Four laws govern a hop:

- **The deadline crosses absolute.** The work takes the caller's
  :class:`~vfs.deadline.Deadline` and cuts its budget when the worker
  starts, so time queued behind a busy pool shortens the budget and
  never extends the wall.
- **One batch in flight per** :class:`VerifyOffload`. A batch loop
  awaits each call before issuing the next; the wrapper refuses overlap
  loudly.
- **Cancellation is abandonment made safe.** A cancelled await returns
  at once and a worker already running finishes into the void: it
  touches no session and its results are dropped. It holds what its
  caller already holds, or one batch, bounded by
  :data:`CONTENT_BYTE_BUDGET` or one body, whichever is larger (a
  batcher that meters characters holds up to four times that in UTF-8
  bytes). No protocol-level interrupt exists.
- **A shut executor serves inline.** A caller holding an executor that
  was shut under it runs its remaining hops on the loop, never a raw
  escape. No vfs code path shuts the process pool or waits on one of
  its workers; the next :func:`offload_pool` call after a shutdown
  makes a new one.

The Rust matcher and the glob set release the GIL for a whole batch, so
their hops free the loop outright. Pure-Python work on a worker (edit's
matching, the glob atom walk, the planning walk) holds the GIL in turns,
so its hop bounds a stall at the interpreter's switch interval; a Rust
kernel is the direction for each.

These are the tree's deliberate threads, and there are no others: the
process pool; the engine's rayon workers, a global pool the Rust kernels
start on their first parallel call, as wide as the machine, which the
Python side neither owns nor re-makes; the synchronous face's loop
thread (``vfs.sync``); the executor a local embedding provider is
constructed with; and the shell runtime's epoch thread, one per process
in the extension, which advances the WebAssembly engine's clock every
10 ms so a deadline or a cancel ends a running slice of a line; and the
short-lived thread each slice of a line runs on, started by the extension
from a pool worker with a stack of the module's own size.

Across a fork, a child forgets the inherited pool and makes its own on
its first hop. The engine's pool is not covered. A forked child may
write, and may hop pure-Python work. If its parent ran a parallel
kernel before the fork, the child's own kernel calls (grep, glob,
search, rebuild) never return once a batch is large enough to go
parallel; a call over one item returns. Start workers with ``spawn``
or ``forkserver`` to avoid that.
"""

from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, Final, TypeVar

from vfs.deadline import WALL_TIME_CAUSE
from vfs.models import MEASURE_OFFLOAD_BYTES, MEASURED_BODY, Entry, measure_bytes, measure_text
from vfs.results import classified
from vfs.results.kinds import ErrorKind, Severity

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from concurrent.futures import Executor

    from vfs.deadline import Deadline
    from vfs.paths import Path
    from vfs.pattern_matching import Body, ContentMatcher, GlobGates
    from vfs.pattern_matching.glob import GlobRow
    from vfs.pattern_matching.grep import MatchSpan
    from vfs.results import ResultError

T = TypeVar("T")

# Offload pool width: available parallelism, no knob. One native call
# already saturates the cores, so wider only oversubscribes.
OFFLOAD_WORKERS: Final = os.cpu_count() or 1

# Bytes of bodies one hop holds at once: content is fetched, matched or
# counted, and released in batches cut to this size.
CONTENT_BYTE_BUDGET: Final = 32 * 1024 * 1024


# ---------------------------------------------------------------------------
# The wall's truncation record
# ---------------------------------------------------------------------------


def wall_truncation(guidance: str) -> ResultError:
    """One stage's truncation at its wall; *guidance* says what shrinks that stage's work."""
    return classified(ErrorKind.truncated, severity=Severity.warning, detail=f"at the {WALL_TIME_CAUSE}; {guidance}")


# ---------------------------------------------------------------------------
# The process pool
# ---------------------------------------------------------------------------

# The one pool every hop in the process runs on, made on first use, and the lock its slot is read under.
_pool: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def offload_pool() -> ThreadPoolExecutor:
    """The process pool, made on first call: ``OFFLOAD_WORKERS`` threads named ``vfs-offload``.

    The router and every storage host share it. One native call already
    saturates the machine, so a second pool over the same engine would
    buy latency and no work. The width was measured on 10 cores with
    32 MiB batches: throughput plateaus by 4 workers and holds flat at
    the core count, callers that run together queue cleanly, and only a
    width past the cores degrades.
    """
    global _pool
    with _lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=OFFLOAD_WORKERS, thread_name_prefix="vfs-offload")
        return _pool


def shutdown_offload_pool() -> None:
    """Shut the process pool without waiting and clear its slot; the next hop makes a new one.

    Running work finishes and queued work is served, never cancelled.
    vfs calls this nowhere: it is for a host's own teardown, and for a
    test that narrows the pool.
    """
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# The hop
# ---------------------------------------------------------------------------


async def call_offloaded(executor: Executor, work: Callable[[], T]) -> T:
    """Run *work* on *executor*, the process pool or one a test injects; the loop keeps ticking.

    The one hop every offloaded stage takes. An executor that was shut
    serves the work inline, and a caller that holds it serves *all* its
    remaining hops that way, never a raw escape.
    """
    try:
        future = executor.submit(work)
    except RuntimeError:
        return work()
    return await asyncio.wrap_future(future)


async def measured_entry(path: Path, content: str | None, data: bytes | None) -> Entry:
    """Build the :term:`entry` that a write to one path makes.

    A small body is hashed in place by the model's own validator, because the hash costs less than a hop
    to another thread. A body at or past ``MEASURE_OFFLOAD_BYTES`` is measured on the process pool first
    and handed to the validator already measured. One caller's 16 MB write then never stalls every other
    coroutine for the length of a SHA-256.
    """
    body: str | bytes | None = data if data is not None else content
    if body is None or len(body) < MEASURE_OFFLOAD_BYTES:
        return Entry(path=str(path), content=content, data=data)
    if isinstance(body, bytes):
        metrics = await call_offloaded(offload_pool(), partial(measure_bytes, body))
    else:
        metrics = await call_offloaded(offload_pool(), partial(measure_text, body))
    return Entry.model_validate({"path": str(path), "content": content, "data": data}, context={MEASURED_BODY: metrics})


async def judge_rows(
    executor: Executor, gates: GlobGates, rows: Sequence[GlobRow], *, deadline: Deadline
) -> tuple[list[int | None], bool]:
    """Every row's verdict against *gates*, judged in one hop; and whether every row was judged.

    The hop builds the gates' native set if no earlier hop has, then
    cuts the budget from *deadline*, so time queued for a thread and
    time spent building both shorten it, and neither extends the wall.
    A build that reached the deadline answers every row unjudged
    (``None``). With no rows, or gates that hold no pattern (the ext
    facts need no engine), no hop is made: the verdicts are ``[]`` or
    ``0`` per row, and judging is complete whatever the clock reads.

    Gates with a scope also build its pairs in the same worker, one per
    covering root, and judge them against the scope's set
    (:meth:`~vfs.pattern_matching.GlobGates.judge_scope`), the deadline
    read between chunks of rows; a row not reached is unjudged.
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
            verdicts, completed = native.judge(rows, budget=deadline.remaining())
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
        self, texts: Sequence[Body], *, cap: int | None, invert: bool, deadline: Deadline
    ) -> tuple[list[int], bool]:
        """`ContentMatcher.count_lines` off-loop, budget cut at worker start."""

        def work() -> tuple[list[int], bool]:
            return self._matcher.count_lines(texts, cap=cap, invert=invert, budget=deadline.remaining())

        return await self._run(work)

    async def hit_lines(
        self,
        texts: Sequence[Body],
        *,
        before: int,
        after: int,
        cap: int | None,
        invert: bool,
        deadline: Deadline,
    ) -> tuple[list[list[MatchSpan]], bool]:
        """`ContentMatcher.hit_lines` off-loop, budget cut at worker start."""

        def work() -> tuple[list[list[MatchSpan]], bool]:
            budget = deadline.remaining()
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _forget_pool() -> None:  # pragma: no cover - runs only in a forked child; pinned by a subprocess test
    """Drop the pool and the lock a forked child inherited; its first hop makes a pool of its own.

    The inherited executor's threads do not exist in the child, so it is
    dropped without a shutdown; and a lock another thread held at the
    fork is held in the child by no thread, so the lock is replaced.
    """
    global _pool, _lock
    _pool = None
    _lock = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_forget_pool)
