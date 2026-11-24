"""The writer behind: one buffer for each file system, which one task of the store's own empties as soon as it is free.

A record written behind is put in a buffer in memory and written by the
task after the call that produced it has returned, so a read's whole
dealing with the store is one call that sends nothing and awaits
nothing. Every record written behind may be dropped: the buffer is
bounded, drops its oldest rows when full, and a process that dies loses
it. A record that may not be dropped is written with ``commit`` or
``record_after`` instead.

The task flushes while the buffer holds anything, up to ``FLUSH_ROWS``
rows a transaction, and then waits for the next put, ``drain``, sweep
chunk or ``close``: there is no row count to reach and no timer. A flush
that fails for a reason a retry can clear keeps its rows at the head of
the buffer; one that can never land is tried once more a kind at a time,
and only the kinds that fail again are dropped.

    writer.register(kind)
    writer.put(kind, rows, scope=session)
    await writer.drain(session)

The writer sends no statement itself. The store hands it the function
that writes one flush, and judges whether a failure can be cleared.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable, Iterable, Mapping, Sequence

    from vfs.deadline import Deadline
    from vfs.kernel_store.store import KernelStore, KernelStoreUnavailable, Transaction

    Groups = Sequence[tuple["BehindKind", Sequence[Mapping[str, object]]]]
    Flush = Callable[[Groups, Deadline | None], Awaitable["FlushOutcome"]]

FLUSH_ROWS: Final = 1_024
"""The most rows one flush takes from the head of the buffer."""

BEHIND_CAPACITY: Final = 16_384
"""The rows the buffer holds before it drops its oldest: about 16 MB at ordinary widths."""

TASK_NAME: Final = "vfs-kernel-store"
"""The name of the store's one background task."""

_log: Final = logging.getLogger(__name__)

_HELD: Final = (
    "the kernel store at %s could not be written (%s); records written behind are held in memory, "
    "and the oldest are dropped past %d"
)
_WRITTEN_AGAIN: Final = "the kernel store at %s is written again after %d failed flushes; %d records were dropped"
_NEVER: Final = "a flush of %d %s records to the kernel store at %s can never land (%s); they are dropped"
_CLOSED_WITH: Final = "the kernel store at %s was closed with %d records written behind that it could not write"


@dataclass(frozen=True, slots=True)
class BehindKind:
    """One sort of row that is written behind, with the function that writes a batch of it.

    ``write`` is handed the store, the flush's one transaction and the
    rows, and writes them with the store's chunked statements. ``key`` is
    the fields that make two rows one: a row put behind replaces a waiting
    row of the same kind whose key fields are equal, in that row's place.
    It is the conflict key of the kind's statement, or coarser.
    """

    name: str
    write: Callable[[KernelStore, Transaction, Sequence[Mapping[str, object]]], Awaitable[None]]
    key: tuple[str, ...] | None = None


class FlushOutcome(NamedTuple):
    """What became of one flush, as the store judged it: written, held for a retry, or some kinds dropped."""

    held: KernelStoreUnavailable | None = None
    """A failure a retry can clear: every row of the flush goes back to the head of the buffer."""
    lost: Mapping[str, KernelStoreUnavailable] | None = None
    """Each kind that can never land, with its failure; its rows are dropped and the others are written."""
    refused: KernelStoreUnavailable | None = None
    """A store of another format: the whole flush is dropped, with no second try."""


@dataclass(slots=True, eq=False)
class _Waiting:
    """One row put behind and not yet stored or dropped, under the number it was first put as."""

    number: int
    kind: BehindKind
    row: Mapping[str, object]
    scope: Hashable | None
    key: tuple[object, ...] | None


@dataclass(slots=True, eq=False)
class _Drain:
    """A ``drain`` that waits for the rows of *scope*, every scope when ``None``, put before *mark*."""

    scope: Hashable | None
    mark: int
    done: asyncio.Future[None]


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


class BehindWriter:
    """The buffer of one store, and the one task that empties it.

    *flush* writes one flush in one transaction of the store and says what
    became of it; with a deadline it is a flush at close, which makes one
    try. *before_flush* is awaited each time the task is about to take a
    batch. *label* names the place in a log record, and *capacity* bounds
    the buffer. Every method but :meth:`drain`, :meth:`let_one_flush` and
    :meth:`close` is a plain function that sends nothing and is called on
    the loop's thread.
    """

    def __init__(
        self,
        *,
        flush: Flush,
        before_flush: Callable[[], Awaitable[None]],
        label: str,
        capacity: int = BEHIND_CAPACITY,
    ) -> None:
        self.dropped = 0
        self._flush = flush
        self._before_flush = before_flush
        self._label = label
        self._capacity = capacity
        self._kinds: dict[str, BehindKind] = {}
        # Waiting rows by number: the buffer in order from its head, and the flush in flight.
        self._buffer: OrderedDict[int, _Waiting] = OrderedDict()
        self._flight: dict[int, _Waiting] = {}
        self._keyed: dict[tuple[str, tuple[object, ...]], int] = {}
        self._flight_keyed: dict[tuple[str, tuple[object, ...]], int] = {}
        self._scopes: dict[Hashable | None, set[int]] = {}
        self._next_number = 0
        self._drains: list[_Drain] = []
        self._flush_waiters: list[asyncio.Future[None]] = []
        self._task: asyncio.Task[None] | None = None
        self._wake: asyncio.Event | None = None
        self._generation = 0
        # The close's budget, handed to the task, which takes it into a local at its next turn.
        self._told: Deadline | None = None
        self._closed = False
        self._stopped = False
        self._failures = 0
        self._dropped_at_failure = 0
        self._lost_at_close = 0

    # -------------------------------------------------------------------
    # Kinds and rows
    # -------------------------------------------------------------------

    def register(self, kind: BehindKind) -> None:
        """Register *kind*; kinds are flushed in the order they were registered."""
        if kind.name in self._kinds:
            raise ValueError(f"a kind named {kind.name!r} is already registered")
        self._kinds[kind.name] = kind

    def put(self, kind: BehindKind, rows: Iterable[Mapping[str, object]], *, scope: Hashable | None = None) -> None:
        """Add *rows* to the buffer and wake the task; past the bound the oldest rows are dropped and counted."""
        self._require(kind)
        if self._closed:
            self.dropped += sum(1 for _ in rows)
            return
        for row in rows:
            self._add(kind, row, scope)
        overflow = len(self._buffer) - self._capacity
        if overflow > 0:
            for _ in range(overflow):
                _number, entry = self._buffer.popitem(last=False)
                self._forget(entry, self._keyed)
            self.dropped += overflow
            self._settle_drains()
        self._start()
        self._wake_task()

    def waiting(
        self, kind: BehindKind, *, scope: Hashable | None = None, keys: Iterable[tuple[object, ...]] | None = None
    ) -> list[Mapping[str, object]]:
        """The rows of *kind* under *scope*, or with one of *keys*, that are buffered or in the flush in flight."""
        return [entry.row for entry in self._select(kind, scope, keys, in_flight=True)]

    def discard(
        self, kind: BehindKind, *, scope: Hashable | None = None, keys: Iterable[tuple[object, ...]] | None = None
    ) -> int:
        """Take the rows of *kind* under *scope*, or with one of *keys*, out of the buffer; return how many."""
        found = self._select(kind, scope, keys, in_flight=False)
        for entry in found:
            del self._buffer[entry.number]
            self._forget(entry, self._keyed)
        if found:
            self._settle_drains()
        return len(found)

    # -------------------------------------------------------------------
    # Waiting for rows
    # -------------------------------------------------------------------

    async def drain(self, scope: Hashable | None = None) -> None:
        """Return when every row of *scope*, every row with none, put before the call is written or dropped.

        Nothing waiting returns at once. When a flush that carries one of
        those rows fails, the store's failure is raised. A caller
        cancelled meanwhile loses no row: the flush goes on.
        """
        mark = self._next_number
        if not self._pending(scope, mark):
            return
        self._start()
        waiter = _Drain(scope, mark, asyncio.get_running_loop().create_future())
        self._drains.append(waiter)
        self._wake_task()
        try:
            await waiter.done
        finally:
            if waiter in self._drains:
                self._drains.remove(waiter)

    async def let_one_flush(self) -> None:
        """Wake the task when rows wait, and wait for the end of one flush, whether it landed or failed."""
        if self._closed or not (self._buffer or self._flight):
            return
        self._start()
        waiter = asyncio.get_running_loop().create_future()
        self._flush_waiters.append(waiter)
        self._wake_task()
        await waiter

    # -------------------------------------------------------------------
    # Close
    # -------------------------------------------------------------------

    def close(self, budget: Deadline) -> Awaitable[None]:
        """Take no more rows and tell the task to close, at once; return the wait for the task, within *budget*.

        The task flushes what is left, one try a flush. It is awaited and
        never interrupted, and ends when the buffer is empty, when a flush
        fails, or when the budget is spent before a flush; :meth:`cut_short`
        then drops and counts what is left. It is told before the caller
        awaits anything, so no flush of its own starts after the close.
        """
        if self._buffer:
            self._start()
        self._closed = True
        task = self._task
        if task is None or task.done() or task.get_loop() is not asyncio.get_running_loop():
            return _ended(None, None)
        self._told = budget
        self._wake_task()
        return _ended(task, budget.remaining())

    def cut_short(self) -> None:
        """Start no further flush, and drop and count the rows left; the flush in hand ends as it will.

        One ``WARNING`` says how many rows the close dropped: now, or when
        the flush in hand ends, so that it counts that flush's rows too.
        """
        self._closed = True
        self._stopped = True
        self._drop_buffer()
        if not self._flight:
            self._report_close()
        self._settle_drains()
        self._release_flush_waiters()
        self._wake_task()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _require(self, kind: BehindKind) -> None:
        if self._kinds.get(kind.name) is not kind:
            raise ValueError(f"the kind {kind.name!r} is not registered on this store")

    def _add(self, kind: BehindKind, row: Mapping[str, object], scope: Hashable | None) -> None:
        key = None if kind.key is None else tuple(row[name] for name in kind.key)
        if key is not None and (number := self._keyed.get((kind.name, key))) is not None:
            entry = self._buffer[number]
            self._rescope(entry, scope)
            entry.row = row
            return
        number = self._next_number
        self._next_number += 1
        self._buffer[number] = _Waiting(number, kind, row, scope, key)
        if key is not None:
            self._keyed[(kind.name, key)] = number
        self._scopes.setdefault(scope, set()).add(number)

    def _rescope(self, entry: _Waiting, scope: Hashable | None) -> None:
        """Move *entry* to *scope*, the scope of the later row that replaced its own."""
        if entry.scope == scope:
            return
        self._unscope(entry.number, entry.scope)
        entry.scope = scope
        self._scopes.setdefault(scope, set()).add(entry.number)

    def _unscope(self, number: int, scope: Hashable | None) -> None:
        held = self._scopes[scope]
        held.discard(number)
        if not held:
            del self._scopes[scope]

    def _forget(self, entry: _Waiting, keyed: dict[tuple[str, tuple[object, ...]], int]) -> None:
        """Drop *entry* from the scopes and from *keyed*, the key index of the place it left."""
        if entry.key is not None:
            del keyed[(entry.kind.name, entry.key)]
        self._unscope(entry.number, entry.scope)

    def _select(
        self,
        kind: BehindKind,
        scope: Hashable | None,
        keys: Iterable[tuple[object, ...]] | None,
        *,
        in_flight: bool,
    ) -> list[_Waiting]:
        self._require(kind)
        if scope is None and keys is None:
            raise ValueError("waiting_behind and discard_behind take a scope, keys, or both")
        if keys is not None and kind.key is None:
            raise ValueError(f"the kind {kind.name!r} has no key to name its rows by")
        places: tuple[Mapping[int, _Waiting], ...] = (self._buffer, self._flight) if in_flight else (self._buffer,)
        wanted = None if keys is None else {tuple(key) for key in keys}
        if scope is not None:
            numbers = sorted(self._scopes.get(scope, ()))
        else:
            assert wanted is not None
            indexes = (self._keyed, self._flight_keyed) if in_flight else (self._keyed,)
            found = (index.get((kind.name, key)) for index in indexes for key in wanted)
            numbers = sorted(number for number in found if number is not None)
        entries = [entry for number in numbers for place in places if (entry := place.get(number)) is not None]
        return [entry for entry in entries if entry.kind is kind and (wanted is None or entry.key in wanted)]

    def _pending(self, scope: Hashable | None, mark: int) -> bool:
        """Whether a row of *scope*, of any scope when ``None``, put before *mark* still waits."""
        if scope is None:
            return any(number < mark for place in (self._buffer, self._flight) for number in place)
        return any(number < mark for number in self._scopes.get(scope, ()))

    def _settle_drains(self, failed: Sequence[tuple[_Waiting, KernelStoreUnavailable]] = ()) -> None:
        """Answer each drain whose rows are all written or dropped, or raise to it a failure of one of its rows."""
        waiting: list[_Drain] = []
        for waiter in (waiter for waiter in self._drains if not waiter.done.done()):
            failure = next(
                (
                    cause
                    for entry, cause in failed
                    if entry.number < waiter.mark and (waiter.scope is None or entry.scope == waiter.scope)
                ),
                None,
            )
            if failure is not None:
                waiter.done.set_exception(failure)
            elif not self._pending(waiter.scope, waiter.mark):
                waiter.done.set_result(None)
            else:
                waiting.append(waiter)
        self._drains = waiting

    def _release_flush_waiters(self) -> None:
        # A waiter whose pass was cancelled is done already, and is let go with the others.
        for waiter in (waiter for waiter in self._flush_waiters if not waiter.done()):
            waiter.set_result(None)
        self._flush_waiters.clear()

    def _start(self) -> None:
        """Start the task on the running loop, unless it runs there; a task on another loop is retired."""
        loop = asyncio.get_running_loop()
        task = self._task
        if task is not None and not task.done() and task.get_loop() is loop:
            return
        elsewhere = task is not None and not task.done()
        self._generation += 1
        if elsewhere:
            # The task belongs to the loop of the last put: the old one sees a newer generation and ends.
            self._wake_task()
        self._wake = asyncio.Event()
        self._task = loop.create_task(self._run(self._generation), name=TASK_NAME, context=contextvars.Context())

    def _wake_task(self) -> None:
        task, wake = self._task, self._wake
        if task is None or wake is None or task.done():
            return
        loop = task.get_loop()
        if loop is asyncio.get_running_loop():
            wake.set()
        elif not loop.is_closed():
            loop.call_soon_threadsafe(wake.set)

    async def _run(self, generation: int) -> None:
        """The task: flush while rows wait, then wait to be woken; at close, flush what is left and end."""
        wake = self._wake
        assert wake is not None
        told: Deadline | None = None
        while generation == self._generation and not self._stopped:
            if self._told is not None:
                told, self._told = self._told, None
            if told is not None:
                await self._flush_at_close(told)
                break
            wake.clear()
            if self._buffer and await self._flush_once(None):
                continue
            self._release_flush_waiters()
            await wake.wait()
        if generation == self._generation:
            self._finish()

    async def _flush_at_close(self, deadline: Deadline) -> None:
        """Flush what is left, one try a flush, and start no flush once the budget is spent or a flush failed."""
        while self._buffer and not self._stopped:
            left = deadline.remaining()
            if left is not None and left <= 0:
                return
            if not await self._flush_once(deadline):
                return

    async def _flush_once(self, at_close: Deadline | None) -> bool:
        """Take one batch from the head of the buffer and flush it; whether the task may flush again at once."""
        await self._before_flush()
        if self._stopped or not self._buffer:
            return not self._stopped
        batch: list[_Waiting] = []
        while self._buffer and len(batch) < FLUSH_ROWS:
            _number, entry = self._buffer.popitem(last=False)
            if entry.key is not None:
                identity = (entry.kind.name, entry.key)
                del self._keyed[identity]
                self._flight_keyed[identity] = entry.number
            self._flight[entry.number] = entry
            batch.append(entry)
        try:
            outcome = await self._flush(self._groups(batch), at_close)
        except BaseException:
            self._return(batch)
            raise
        return self._settle(batch, outcome, at_close=at_close is not None)

    def _groups(self, batch: Sequence[_Waiting]) -> list[tuple[BehindKind, list[Mapping[str, object]]]]:
        """The batch's rows by kind, in the order the kinds were registered; a keyed kind's sorted by key."""
        by_kind: dict[str, list[_Waiting]] = {}
        for entry in batch:
            by_kind.setdefault(entry.kind.name, []).append(entry)
        groups: list[tuple[BehindKind, list[Mapping[str, object]]]] = []
        for name, kind in self._kinds.items():
            entries = by_kind.get(name)
            if not entries:
                continue
            if kind.key is not None:
                entries.sort(key=_key_of)
            groups.append((kind, [entry.row for entry in entries]))
        return groups

    def _settle(self, batch: list[_Waiting], outcome: FlushOutcome, *, at_close: bool) -> bool:
        """Apply what became of a flush to its rows; whether the task may flush again at once."""
        if outcome.held is not None and not at_close:
            self._return(batch)
            if self._failures == 0 and not self._closed:
                self._dropped_at_failure = self.dropped
                _log.warning(_HELD, self._label, outcome.held.error.message, self._capacity)
            self._failures += 1
            self._settle_drains([(entry, outcome.held) for entry in batch])
            self._release_flush_waiters()
            return False
        whole = outcome.held or outcome.refused
        lost = outcome.lost or {}
        if whole is None:
            for name, cause in lost.items():
                count = sum(1 for entry in batch if entry.kind.name == name)
                _log.error(_NEVER, count, name, self._label, cause.error.message)
            if self._failures:
                _log.info(_WRITTEN_AGAIN, self._label, self._failures, self.dropped - self._dropped_at_failure)
                self._failures = 0
        failed = [(entry, whole or lost[entry.kind.name]) for entry in batch if whole or entry.kind.name in lost]
        for entry in batch:
            del self._flight[entry.number]
            self._forget(entry, self._flight_keyed)
        self.dropped += len(failed)
        if at_close:
            self._lost_at_close += len(failed)
        self._settle_drains(failed)
        self._release_flush_waiters()
        return outcome.held is None and (outcome.refused is None or not at_close)

    def _return(self, batch: list[_Waiting]) -> None:
        """Put a flush's rows back at the head of the buffer, in order; a row put again since keeps the later row."""
        for entry in reversed(batch):
            del self._flight[entry.number]
            if entry.key is not None:
                identity = (entry.kind.name, entry.key)
                del self._flight_keyed[identity]
                later = self._keyed.get(identity)
                if later is not None:
                    newer = self._buffer.pop(later)
                    self._unscope(later, newer.scope)
                    self._rescope(entry, newer.scope)
                    entry.row = newer.row
                self._keyed[identity] = entry.number
            self._buffer[entry.number] = entry
            self._buffer.move_to_end(entry.number, last=False)

    def _drop_buffer(self) -> None:
        """Drop and count every buffered row, at close."""
        lost = len(self._buffer)
        for entry in self._buffer.values():
            self._forget(entry, self._keyed)
        self._buffer.clear()
        self.dropped += lost
        self._lost_at_close += lost

    def _report_close(self) -> None:
        if self._lost_at_close:
            _log.warning(_CLOSED_WITH, self._label, self._lost_at_close)
            self._lost_at_close = 0

    def _finish(self) -> None:
        """The task ends: what is left is dropped and counted, and the close's one warning is said."""
        self._drop_buffer()
        self._report_close()
        self._settle_drains()
        self._release_flush_waiters()


async def _ended(task: asyncio.Task[None] | None, timeout: float | None) -> None:
    """Wait for *task* to end, at most *timeout* seconds, and never interrupt it; at once when there is none."""
    if task is not None:
        await asyncio.wait({task}, timeout=timeout)


def _key_of(entry: _Waiting) -> Any:
    """A keyed row's key, which a flush sorts the kind's rows by."""
    return entry.key
