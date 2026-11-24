"""The kernel's store: one place, for each file system, where the kernel keeps rows about calls.

A record is a row the kernel keeps about calls, a session's, a turn's, a
job's. It has no path, and no verb, session, policy or tool reaches it:
the store is a private attribute of the kernel and judges no rights,
because every call on it is the kernel's own. The kernel builds one
store in its constructor, with no I/O, from the place its root storage
names, and closes it inside its own ``close``.

The place is the root's own database. On SQLite it is the mount's file,
reached through an engine of the store's own, so a store transaction is
never a mount's and never rides a mount's connection. On Postgres it is
the mount's database and schema, on a pool of the store's own of the
mount's size, and every store transaction runs at READ COMMITTED,
whatever the role, the database or the server defaults to, so a counter
reads what a rival committed while it waited for the rival's row lock. A
root in memory names a second database in memory, with a connection and
a turn lock of its own.

The store is used through two transactions. ``query`` reads and writes
nothing. ``commit`` opens a writer transaction, ``BEGIN IMMEDIATE`` on
SQLite, and commits when its function returns. Each runs first touch
when it is needed, then its function on one ``Transaction`` under the
engine core's retry, so it waits as a mount's write does: four tries,
and on SQLite five seconds a try. ``record_after`` is a ``commit`` for
the record of a change that has already landed: it never raises for a
store failure, and returns the warning the change's result carries, and
it runs out of its caller's reach to its end, so a cancelled caller
leaves its record whole. A store failure is one exception,
:class:`KernelStoreUnavailable`, which carries a classified error.

On SQLite the store shares the file's one writer with the mount. A store
write waits behind a mount's write and a mount's write behind a store
write, each for a commit's length, and a store write behind a batch on
the mount waits its four tries and then fails as unavailable. A read of
the mount never waits on the store: in WAL a reader runs beside the
writer.

A record that may be dropped is written behind: ``put_behind`` adds it
to a buffer and returns, sending nothing, and one background task of the
store's own, ``vfs-kernel-store``, writes it as soon as it is free, in
transactions of at most ``FLUSH_ROWS`` rows. A change that must read what
its own session wrote behind drains that session's rows first, or reads
them where they wait. Expired records leave only when ``sweep`` is
called, in chunks of ``SWEEP_CHUNK``, and the task's flush goes between
two chunks.

Every time the store keeps comes from its ``clock``, which a test
replaces, and is bound as a parameter: no statement names the engine's
own clock.

    store = KernelStore(storage.record_place)
    count = await store.query(lambda transaction: transaction.execute(statement))
"""

from __future__ import annotations

import asyncio
import functools
import itertools
import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, TypeVar

from sqlalchemy import Column, and_, delete, event, insert, select, tuple_, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.util import greenlet_spawn

from vfs.deadline import Deadline
from vfs.kernel_store.behind import BEHIND_CAPACITY, BehindWriter, FlushOutcome
from vfs.kernel_store.sweep import sweep_pass
from vfs.models.kernel_rows import KERNEL_FORMAT_VERSION, build_kernel_tables
from vfs.results import ErrorKind, ResultError, Severity, classified
from vfs.storage.backends.database.attempts import run_to_its_end
from vfs.storage.backends.database.core import EngineCore
from vfs.storage.backends.database.dialects import (
    StaleSnapshot,
    bulk_insert,
    chunked,
    is_insufficient_privilege,
    is_permanent_defect,
    is_value_too_large,
    rows_per_statement,
    upsert_constructor,
)
from vfs.storage.backends.database.drivers import url_of_place
from vfs.storage.backends.database.engine import advisory_key
from vfs.storage.backends.database.seams import seam
from vfs.storage.protocol import RecordPlace, SupportsRecordPlace

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Hashable, Iterable, Iterator, Mapping, Sequence

    from sqlalchemy import ColumnElement, Engine, Table
    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    from vfs.kernel_store.behind import BehindKind, Groups
    from vfs.kernel_store.sweep import Sweeper
    from vfs.models.kernel_rows import KernelTables
    from vfs.storage.protocol import StorageBackend

T = TypeVar("T")
K = TypeVar("K")

Transaction = AsyncSession
"""One transaction of the store; a session in VFS is something else, so the store never calls it one."""

_log: Final = logging.getLogger(__name__)

# The context the core's classifier names, and the closed kernel's own words.
_CONTEXT: Final = "kernel store"
_CLOSED: Final = "the filesystem is closed"

# Kept back from a close's budget for the dispose.
_DISPOSE_SECONDS: Final = 1.0

# The execution option that bounds, in milliseconds, how long a flush at close waits for SQLite's writer.
_WAIT_AT_CLOSE: Final = "vfs_kernel_wait_ms"

_IN_MEMORY_WARNING: Final = (
    "this file system keeps its sessions and jobs in memory, because its root storage names no database for "
    "them; they end with this process and no other process sees them. A mount beneath the root is a database: "
    "make the root storage a database to keep them there."
)


class KernelStoreUnavailable(Exception):  # noqa: N818 — the store's state, named as the error kind it carries
    """The store could not be read or written; ``error`` is the classified reason, a ``Result`` error."""

    def __init__(self, error: ResultError) -> None:
        super().__init__(error.message)
        self.error = error


def system_clock() -> datetime:
    """The system's time, aware and in UTC: the default clock of every store."""
    return datetime.now(UTC)


class KernelStore:
    """The kernel's own records, kept in the place the root storage names.

    ``place`` is read when the store is built, with no I/O; one of
    another dialect than SQLite or Postgres raises ``ValueError``, which
    names the dialect and never the URL. The store's engine is built at
    its first use and disposed by :meth:`close`. ``clock`` returns an
    aware UTC time; every time a record stores is read from it. The
    kernel builds its store through :func:`store_for_root`.
    ``behind_capacity`` bounds the rows written behind that wait.
    """

    def __init__(
        self,
        place: RecordPlace,
        *,
        clock: Callable[[], datetime] = system_clock,
        retry_attempts: int = 4,
        retry_base_delay: float = 0.05,
        behind_capacity: int = BEHIND_CAPACITY,
    ) -> None:
        self._url = url_of_place(place)
        self._place = place
        self.tables: KernelTables = build_kernel_tables(schema=place.schema)
        self.durable = place.durable
        self.clock = clock
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        # Whether the file system holds a mount on a database; set by store_for_root.
        self._holds_durable_mount: Callable[[], bool] | None = None
        self._core: _StoreCore | None = None
        self._ready = False
        self._closing = False
        self._warned_of_memory = False
        self._warned_of_format = False
        # Made on the caller's loop at first use: construction binds nothing to a loop.
        self._touch: asyncio.Lock | None = None
        self._idle: asyncio.Event | None = None
        self._in_flight = 0
        self._key = advisory_key(self.tables.meta.fullname)
        self._writer = BehindWriter(
            flush=self._flush,
            before_flush=functools.partial(seam, "kernel-store:before-flush"),
            label=place.label,
            capacity=behind_capacity,
        )
        self._sweepers: dict[str, Sweeper] = {}

    # -------------------------------------------------------------------
    # Facts, with no I/O
    # -------------------------------------------------------------------

    @property
    def engine(self) -> AsyncEngine:
        """The store's own engine, for listeners alone; building it opens no connection."""
        return self._engine_core().engine

    @property
    def dropped(self) -> int:
        """Rows written behind that were dropped: by the bound, by a flush that can never land, or at close."""
        return self._writer.dropped

    @property
    def parameter_budget(self) -> int:
        """Bind parameters one statement may carry on the place's dialect."""
        return self._engine_core().parameter_budget

    @property
    def membership_budget(self) -> int:
        """Elements one ``IN`` list may carry on the place's dialect."""
        return self._engine_core().membership_budget

    def now(self) -> datetime:
        """The store's clock, read once: the one time every record and every expiry compares with."""
        return self.clock()

    # -------------------------------------------------------------------
    # Transactions
    # -------------------------------------------------------------------

    async def query(self, fn: Callable[[Transaction], Awaitable[T]]) -> T:
        """Run *fn* on one transaction that reads and writes nothing, and return what it returns.

        On SQLite it begins with a plain ``BEGIN``: a transaction that read
        and then wrote would be refused whenever another connection
        committed in between. *fn* runs again from its first statement
        when the engine asks for a retry. A store failure raises
        :class:`KernelStoreUnavailable`; anything else *fn* raises is
        raised as it is.
        """
        return await self._transact(fn, writer=False, to_its_end=False)

    async def commit(self, fn: Callable[[Transaction], Awaitable[T]]) -> T:
        """Run *fn* on one writer transaction and commit it when *fn* returns; return what *fn* returns.

        An exception from *fn* rolls back and is raised as it is. A store
        failure, retries that run out among them, raises
        :class:`KernelStoreUnavailable`.
        """
        self._warn_of_memory()
        return await self._transact(fn, writer=True, to_its_end=False)

    async def record_after(self, fn: Callable[[Transaction], Awaitable[object]]) -> ResultError | None:
        """Commit the record of a change that has landed; ``None``, or the warning the change's result carries.

        A store failure is never raised: the change stands, and the
        warning says the record was not written. Each try runs out of the
        caller's reach to its commit. A caller cancelled meanwhile waits
        for the try in hand, starts no other, and is then raised the
        cancellation it was cancelled with.
        """
        self._warn_of_memory()
        try:
            await self._transact(fn, writer=True, to_its_end=True)
        except KernelStoreUnavailable as failure:
            detail = f"the change is committed, and the kernel's record of it was not written: {failure.error.message}"
            return classified(ErrorKind.unavailable, severity=Severity.warning, detail=detail)
        return None

    # -------------------------------------------------------------------
    # Statements, called inside a transaction
    # -------------------------------------------------------------------

    async def next_number(
        self, transaction: Transaction, counter: Column[int], *where: ColumnElement[bool], count: int = 1
    ) -> int:
        """Add *count* to *counter* on the one row *where* names, and return the last number of the block.

        One ``UPDATE … RETURNING``. Two processes never take one number:
        on SQLite one writer holds the file, and on Postgres the second
        waits for the first one's row lock and reads what it committed.
        A row that matches nothing raises ``LookupError``: the owner makes
        the row first, in the same commit.
        """
        statement = update(counter.table).where(*where).values({counter.name: counter + count}).returning(counter)
        number = (await transaction.execute(statement)).scalar_one_or_none()
        if number is None:
            raise LookupError(f"no row of {counter.table.name} holds the counter {counter.name} asked for")
        return number

    async def insert_rows(self, transaction: Transaction, table: Table, rows: Sequence[Mapping[str, object]]) -> None:
        """Insert *rows* into *table*, paged under the live parameter budget: ``COPY`` on Postgres."""
        await bulk_insert(transaction, table, rows)

    async def upsert_rows(
        self,
        transaction: Transaction,
        table: Table,
        rows: Sequence[Mapping[str, object]],
        *,
        key: Sequence[str],
        update: Sequence[str],
        newest: str | None = None,
    ) -> int:
        """Insert *rows*, or update the *update* fields of a row whose *key* is taken; return the rows written.

        The rows are sorted by *key*, so two processes lock rows in one
        order, and cut under the live parameter budget. An empty *update*
        does nothing on a conflict. With *newest*, an older row never
        replaces a newer one. Two rows of one key raise ``ValueError``
        before a statement is sent: Postgres refuses a statement that
        updates a row twice, and SQLite keeps the later row.
        """
        ordered = sorted(rows, key=lambda row: tuple(row[name] for name in key))
        for earlier, later in itertools.pairwise(ordered):
            if all(earlier[name] == later[name] for name in key):
                raise ValueError(f"upsert_rows was given the key {[later[name] for name in key]} twice")
        written = 0
        constructor = upsert_constructor(self._engine_core().profile)
        for chunk in self.row_chunks(ordered):
            statement = constructor(table).values(list(chunk))
            if update:
                newer = None if newest is None else statement.excluded[newest] >= table.c[newest]
                fields = {name: statement.excluded[name] for name in update}
                statement = statement.on_conflict_do_update(index_elements=list(key), set_=fields, where=newer)
            else:
                statement = statement.on_conflict_do_nothing(index_elements=list(key))
            written += (await transaction.execute(statement)).rowcount  # ty: ignore[unresolved-attribute]
        return written

    def key_chunks(self, keys: Sequence[K], *, width: int = 1) -> Iterator[Sequence[K]]:
        """Slices of *keys* for an ``IN`` list, each under the membership budget at *width* binds a key."""
        return chunked(keys, self.membership_budget // max(1, width))

    def row_chunks(
        self, rows: Sequence[Mapping[str, object]], *, width: int | None = None
    ) -> Iterator[Sequence[Mapping[str, object]]]:
        """Slices of *rows* for one multi-row statement each, under the live parameter budget.

        *width* is the binds one row takes when the statement binds more
        than the row's own fields; by default it is the widest row.
        """
        if not rows:
            return iter(())
        per = rows_per_statement(self.parameter_budget, rows) if width is None else self.parameter_budget // width
        return chunked(rows, per)

    async def delete_where(
        self,
        transaction: Transaction,
        table: Table,
        *,
        key: Column[Any] | Sequence[Column[Any]],
        where: ColumnElement[bool],
        limit: int,
        order_by: ColumnElement[Any] | None = None,
    ) -> int:
        """Delete at most *limit* rows that *where* matches, by *key*, and return how many went.

        ``DELETE … WHERE key IN (SELECT key … LIMIT :limit)``: its text and
        its binds do not change with the rows it removes. A key of several
        columns is compared as a row value.
        """
        columns = (key,) if isinstance(key, Column) else tuple(key)
        chosen = select(*columns).where(where)
        if order_by is not None:
            chosen = chosen.order_by(order_by)
        target = columns[0] if len(columns) == 1 else tuple_(*columns)
        statement = delete(table).where(target.in_(chosen.limit(limit)))
        return (await transaction.execute(statement)).rowcount  # ty: ignore[unresolved-attribute]

    async def delete_expired(
        self,
        transaction: Transaction,
        table: Table,
        *,
        key: Column[Any],
        expires: Column[datetime],
        now: datetime,
        limit: int,
        where: ColumnElement[bool] | None = None,
    ) -> int:
        """Delete at most *limit* rows whose *expires* is at or before *now*, oldest first; a null never expires."""
        expired = expires <= now if where is None else and_(expires <= now, where)
        return await self.delete_where(transaction, table, key=key, where=expired, limit=limit, order_by=expires)

    # -------------------------------------------------------------------
    # Written behind
    # -------------------------------------------------------------------

    def register_behind(self, kind: BehindKind) -> None:
        """Register a kind written behind, once, when the kernel is built; kinds flush in the order registered.

        A kind that needs another kind's rows is registered after it. A
        second kind of one name raises ``ValueError``.
        """
        self._writer.register(kind)

    def put_behind(
        self, kind: BehindKind, rows: Iterable[Mapping[str, object]], *, scope: Hashable | None = None
    ) -> None:
        """Add *rows* to the buffer, wake the task, and return; it sends nothing, awaits nothing and never fails.

        A row of a keyed kind replaces a waiting row of that kind with the
        same key, in that row's place. Past ``behind_capacity`` the oldest
        rows are dropped and counted in ``dropped``. After ``close`` the
        rows are dropped. A kind that was not registered raises
        ``ValueError``. Called on the loop's thread only; the task belongs
        to the loop of the last put.
        """
        self._writer.put(kind, rows, scope=scope)

    def waiting_behind(
        self,
        kind: BehindKind,
        *,
        scope: Hashable | None = None,
        keys: Iterable[tuple[object, ...]] | None = None,
    ) -> list[Mapping[str, object]]:
        """The rows of *kind* put behind and neither stored nor dropped: buffered, or in the flush in flight.

        It takes a scope, keys of the kind's ``key`` fields, or both, and
        sends nothing; with neither it raises ``ValueError``. A key that
        has no waiting row is in the store, unless it was dropped.
        """
        return self._writer.waiting(kind, scope=scope, keys=keys)

    def discard_behind(
        self,
        kind: BehindKind,
        *,
        scope: Hashable | None = None,
        keys: Iterable[tuple[object, ...]] | None = None,
    ) -> int:
        """Take the rows of *kind* under *scope*, or with one of *keys*, out of the buffer; return how many.

        A row of the flush in flight is not withdrawn, and is stored.
        """
        return self._writer.discard(kind, scope=scope, keys=keys)

    async def drain(self, scope: Hashable | None = None) -> None:
        """Wait until every row put behind before the call, under *scope*, or every row, is written or dropped.

        Nothing waiting returns at once and sends nothing. When the flush
        that carries one of those rows fails, it raises
        :class:`KernelStoreUnavailable`. A caller cancelled while it waits
        loses no row: the flush goes on.
        """
        await self._writer.drain(scope)

    # -------------------------------------------------------------------
    # The sweep
    # -------------------------------------------------------------------

    def register_sweeper(self, name: str, sweep: Sweeper) -> None:
        """Register a sweeper for a table that expires, in the order its parents and dependents need."""
        if name in self._sweepers:
            raise ValueError(f"a sweeper named {name!r} is already registered")
        self._sweepers[name] = sweep

    async def sweep(self) -> int:
        """One pass: every sweeper in turn, in chunks of ``SWEEP_CHUNK``, until a call removes no row; the rows removed.

        Each chunk is a ``commit`` of its own, and the task's flush goes
        between two chunks. A store whose place holds no kernel table
        removes nothing and makes none. A pass that fails logs one
        ``WARNING`` and raises :class:`KernelStoreUnavailable`; the next
        pass starts over. Only the public ``sweep`` of the root's trash
        calls it: the task writes and never removes.
        """
        if not self._sweepers:
            return 0
        return await sweep_pass(
            self,
            self._sweepers.values(),
            label=self._place.label,
            keeps_records=self._keeps_records,
            between=self._writer.let_one_flush,
        )

    # -------------------------------------------------------------------
    # Life
    # -------------------------------------------------------------------

    async def ensure_ready(self) -> None:
        """Make or verify the kernel's tables, once; raise :class:`KernelStoreUnavailable` when that fails.

        First touch sends the file settings and opens one writer
        transaction at the serialization point: ``BEGIN IMMEDIATE`` on
        SQLite, an advisory lock on Postgres keyed by the meta table's
        name, which is not the mount's key. The tables are made when the
        meta table is missing, and the meta row is written under a
        savepoint, so a rival's is harmless. A store of another format is
        refused, and the refusal names the tables to drop. A failure is
        not remembered: the next call tries again. So a store of another
        format pays a first touch at every call before it is refused: on
        SQLite the file settings and a ``BEGIN IMMEDIATE``, which waits
        behind the mount's writer, a ``query`` among them.
        """
        self._enter()
        try:
            await self._first_touch()
        finally:
            self._leave()

    async def close(self, *, within: float | None = None) -> None:
        """Stop taking rows and transactions, flush what waits, wait for what is in flight, and dispose the engine.

        *within* is the seconds the store has. It keeps one for the
        dispose, and never less than half of *within*, as a budget; with
        none, or an infinite one, there is no budget and no clock is read.
        Within it, and at the same time, the task flushes the buffer with
        one try a flush, on SQLite waiting for the file's writer at most
        half of what is left, and the transactions in flight end. A flush
        that fails ends the flushing. When the budget is spent, or the
        close is cancelled, the task starts no further flush, and the rows
        left are dropped and counted, with one ``WARNING``. A transaction
        or a flush a close leaves running ends the try it has in hand,
        starts no other, and closes its own connection when it ends. A
        close that is cancelled disposes all the same, and a second one
        waits again for what is still in hand. A store never used has no
        engine, and its close does nothing.
        """
        # A close with no bound reads no clock.
        unbounded = within is None or math.isinf(within)
        budget = Deadline.never() if unbounded else Deadline.after(max(within - _DISPOSE_SECONDS, within / 2))
        self._closing = True
        ending = self._writer.close(budget)
        try:
            await asyncio.gather(ending, self._wait_for_in_flight(budget))
        finally:
            self._writer.cut_short()
            if self._core is not None:
                await self._core.close()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _engine_core(self) -> _StoreCore:
        """The store's engine core, built at its first use; building it opens no connection."""
        if self._core is None:
            self._core = _StoreCore(
                self,
                url=self._url,
                engine_arguments=self._place.engine_arguments,
                retry_attempts=self._retry_attempts,
                retry_base_delay=self._retry_base_delay,
                vector=False,
            )
            if self._core.profile.name == "sqlite":
                _bound_the_wait_at_close(self._core.engine.sync_engine)
        return self._core

    def _rearm(self) -> None:
        """A database in memory opened a second connection, a new and empty database: make the tables again."""
        self._ready = False

    def _enter(self) -> None:
        if self._closing:
            raise KernelStoreUnavailable(classified(ErrorKind.backend_unavailable, detail=_CLOSED))
        self._in_flight += 1

    def _leave(self) -> None:
        self._in_flight -= 1
        if self._in_flight == 0 and self._idle is not None:
            self._idle.set()

    async def _wait_for_in_flight(self, budget: Deadline) -> None:
        if self._in_flight == 0:
            return
        if self._idle is None:
            self._idle = asyncio.Event()
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=budget.remaining())
        except TimeoutError:
            return

    async def _transact(
        self,
        fn: Callable[[Transaction], Awaitable[T]],
        *,
        writer: bool,
        to_its_end: bool,
        at_close: Deadline | None = None,
    ) -> T:
        # A flush at close is the close's own work: it is not refused, not counted in flight, and makes one try.
        if at_close is None:
            self._enter()
        try:
            await self._first_touch(at_close)
            core = self._engine_core()
            options = self._options(writer=writer, at_close=at_close)

            async def body() -> T:
                await seam("kernel-store:before-try")
                async with core.session_factory() as transaction:
                    await transaction.connection(execution_options=options)
                    answer = await fn(transaction)
                    if writer:
                        await seam("kernel-store:before-commit")
                        await transaction.commit()
                    return answer

            def attempt() -> Awaitable[T]:
                return self._try(body, at_close=at_close is not None)

            try:
                if at_close is not None:
                    return await attempt()
                return await core.with_retry((lambda: run_to_its_end(attempt)) if to_its_end else attempt)
            except (StaleSnapshot, SQLAlchemyError, OSError) as exc:
                raise self._unavailable(exc) from exc
        finally:
            if at_close is None:
                self._leave()

    async def _try(self, body: Callable[[], Awaitable[T]], *, at_close: bool = False) -> T:
        """One try of a transaction or of first touch: none starts after a close, and none leaves a connection open.

        A try *at_close* is the close's own flush, and is not refused.
        """
        if self._closing and not at_close:
            raise KernelStoreUnavailable(classified(ErrorKind.backend_unavailable, detail=_CLOSED))
        engine = self._engine_core().engine.sync_engine
        began_on = engine.pool
        try:
            return await body()
        finally:
            # A close replaced the pool under this try, and disposes neither the one it began on nor the new one again.
            if began_on is not engine.pool:
                for pool in (began_on, engine.pool):
                    await greenlet_spawn(pool.dispose)

    def _options(self, *, writer: bool, at_close: Deadline | None = None) -> dict[str, str | bool | int]:
        options: dict[str, str | bool | int] = {"vfs_writer": True} if writer else {}
        # As a topology verb's: a counter and a claim read what a rival committed while they waited for its lock.
        if (isolation := self._engine_core().profile.topology_isolation) is not None:
            options["isolation_level"] = isolation
        if at_close is not None and (left := at_close.remaining()) is not None:
            # Half of what is left, in milliseconds, for SQLite's wait for its writer; busy_timeout bounds it too.
            options[_WAIT_AT_CLOSE] = int(left * 500)
        return options

    async def _flush(self, groups: Groups, at_close: Deadline | None) -> FlushOutcome:
        """Write one flush of rows written behind, every kind's ``write`` in one transaction; say what became of it.

        A failure a retry can clear holds the flush. A store of another
        format refuses it whole. Any other failure, of a statement or of a
        kind's own code, is tried once more a kind at a time.
        """
        self._warn_of_memory()

        async def every_kind(transaction: Transaction) -> None:
            for kind, rows in groups:
                await kind.write(self, transaction, rows)

        try:
            await self._transact(every_kind, writer=True, to_its_end=False, at_close=at_close)
        except KernelStoreUnavailable as failure:
            if failure.error.kind is ErrorKind.schema_mismatch:
                return FlushOutcome(refused=failure)
            if _can_clear(failure.__cause__):
                return FlushOutcome(held=failure)
        except Exception:  # A kind's own code raised: the second try names the kind.
            pass
        else:
            return FlushOutcome()
        return await self._flush_a_kind_at_a_time(groups, at_close)

    async def _flush_a_kind_at_a_time(self, groups: Groups, at_close: Deadline | None) -> FlushOutcome:
        """The second try of a flush that can never land whole: each kind under a savepoint, in one transaction."""
        lost: dict[str, KernelStoreUnavailable] = {}

        async def each_kind(transaction: Transaction) -> None:
            lost.clear()
            for kind, rows in groups:
                try:
                    async with transaction.begin_nested():
                        await kind.write(self, transaction, rows)
                except SQLAlchemyError as exc:
                    if _can_clear(exc):
                        raise
                    lost[kind.name] = KernelStoreUnavailable(self._classify(exc))
                except Exception as exc:  # A kind's own code raised, which no retry clears.
                    detail = f"the write of {kind.name} records raised {exc!r}"
                    lost[kind.name] = KernelStoreUnavailable(classified(ErrorKind.internal, detail=detail))

        try:
            await self._transact(each_kind, writer=True, to_its_end=False, at_close=at_close)
        except KernelStoreUnavailable as failure:
            # Each kind's failure was caught under its savepoint: what is left is the store's, which a retry clears.
            return FlushOutcome(held=failure)
        return FlushOutcome(lost=lost)

    async def _keeps_records(self) -> bool:
        """Whether the place holds the kernel's tables; it makes none and runs no first touch."""
        if self._ready:
            return True
        self._enter()

        async def look() -> bool:
            async with self._engine_core().session_factory() as transaction:
                connection = await transaction.connection()
                return await connection.run_sync(self._has_meta_table)

        try:
            return await self._try(look)
        except (SQLAlchemyError, OSError) as exc:
            raise self._unavailable(exc) from exc
        finally:
            self._leave()

    async def _first_touch(self, at_close: Deadline | None = None) -> None:
        if self._ready:
            return
        if self._touch is None:
            self._touch = asyncio.Lock()
        async with self._touch:
            if self._ready:
                return
            core = self._engine_core()
            try:
                if at_close is not None:
                    found = await self._try(functools.partial(self._verify_or_make, at_close), at_close=True)
                else:
                    found = await core.with_retry(lambda: self._try(self._verify_or_make))
            except (StaleSnapshot, SQLAlchemyError, OSError) as exc:
                raise self._unavailable(exc) from exc
            if found != KERNEL_FORMAT_VERSION:
                refusal = self._format_refusal(found)
                if not self._warned_of_format:
                    self._warned_of_format = True
                    _log.warning("%s", refusal.message)
                raise KernelStoreUnavailable(refusal)
            self._ready = True

    async def _verify_or_make(self, at_close: Deadline | None = None) -> int:
        """One first touch: the file settings, then the tables and the meta row at the serialization point."""
        core = self._engine_core()
        meta = self.tables.meta
        await core.apply_file_settings()
        async with core.session_factory() as transaction:
            options = self._options(writer=True, at_close=at_close)
            connection = await transaction.connection(execution_options=options)
            await self._serialization_point(connection)
            if not await connection.run_sync(self._has_meta_table):
                await connection.run_sync(self.tables.metadata.create_all, checkfirst=True)
            found = (await connection.execute(select(meta.c.format_version))).scalar_one_or_none()
            if found is None:
                try:
                    # A rival's first touch may write the row first; its insert is the one kept.
                    async with connection.begin_nested():
                        row = {"id": 1, "format_version": KERNEL_FORMAT_VERSION, "created_at": self.now()}
                        await connection.execute(insert(meta).values(row))
                except IntegrityError:  # pragma: no cover - the serialization point admits no rival on either engine
                    pass
                found = (await connection.execute(select(meta.c.format_version))).scalar_one()
            await transaction.commit()
        return found

    async def _serialization_point(self, connection: AsyncConnection) -> None:
        # Keyed by the store's own meta table, so first touch never waits on the mount's.
        await self._engine_core().serialization_point(connection, self._key)

    def _has_meta_table(self, connection: Connection) -> bool:
        return self._engine_core().has_table(connection, self.tables.meta)

    def _format_refusal(self, found: int) -> ResultError:
        names = ", ".join(self.tables.names_to_drop())
        if self._engine_core().profile.name == "sqlite":
            remedy = f"close every process that uses {self._place.label} and drop these tables: {names}"
        else:
            remedy = f"drop these tables in {self._where()}: {names}"
        detail = (
            f"the kernel store at {self._place.label} has format {found} and this build keeps format "
            f"{KERNEL_FORMAT_VERSION}; no session or job is kept until it is made again: {remedy}"
        )
        return classified(
            ErrorKind.schema_mismatch, detail=detail, data={"found": found, "expected": KERNEL_FORMAT_VERSION}
        )

    def _where(self) -> str:
        schema = self._place.schema
        return "the default schema" if schema is None else f"schema {schema}"

    def _unavailable(self, exc: StaleSnapshot | SQLAlchemyError | OSError) -> KernelStoreUnavailable:
        """A store failure that escaped the core's retry, as the one exception the store raises."""
        if isinstance(exc, StaleSnapshot):
            detail = f"kernel store kept losing to concurrent changes: {exc.context}"
            return KernelStoreUnavailable(classified(ErrorKind.unavailable, retryable=True, detail=detail))
        return KernelStoreUnavailable(self._classify(exc))

    def _classify(self, exc: BaseException) -> ResultError:
        """A store failure as a ``Result`` error; a refused privilege is the role's to fix, never a defect."""
        if is_insufficient_privilege(exc):
            names = ", ".join(self.tables.names_to_drop())
            detail = (
                f"the role may not make or write the kernel's tables in {self._place.label}: make them once with a "
                f"role that may, and grant this role SELECT, INSERT, UPDATE and DELETE on these tables: {names}"
            )
            return classified(ErrorKind.unavailable, detail=detail)
        return self._engine_core().classify_failure(exc, context=_CONTEXT)

    def _warn_of_memory(self) -> None:
        """Warn once, at a write, when records in memory sit beside a mount whose files outlive the process."""
        if self.durable or self._warned_of_memory or self._holds_durable_mount is None:
            return
        if self._holds_durable_mount():
            self._warned_of_memory = True
            _log.warning(_IN_MEMORY_WARNING)


def store_for_root(root: StorageBackend, *, mounted: Callable[[], Iterable[StorageBackend]]) -> KernelStore:
    """The store of a file system whose root storage is *root*, built with no I/O.

    Its records are kept in the place *root* names, or in memory when it
    names none. *mounted* gives the storages the file system mounts, each
    time it is called: a store in memory warns once, at a write, while one
    of them names a database that outlives the process.
    """

    store = KernelStore(_record_place_of(root))
    store._holds_durable_mount = lambda: any(_record_place_of(storage).durable for storage in mounted())
    return store


def _can_clear(exc: BaseException | None) -> bool:
    """Whether a retry, or a grant, can clear a flush's failure: never a broken row, statement or value."""
    if exc is None or is_insufficient_privilege(exc):
        return True
    return not (isinstance(exc, IntegrityError) or is_value_too_large(exc) or is_permanent_defect(exc))


def _bound_the_wait_at_close(sync_engine: Engine) -> None:
    """Make a flush at close wait for SQLite's writer at most what it carries, set before its ``BEGIN IMMEDIATE``.

    It runs before the core's own begin, and lowers the connection's
    ``busy_timeout`` and never raises it; the next checkout sets it again.
    """

    @event.listens_for(sync_engine, "begin", insert=True)
    def bounded(conn: Connection) -> None:
        wait = conn.get_execution_options().get(_WAIT_AT_CLOSE)
        if wait is None:
            return
        dbapi = conn.connection.dbapi_connection
        assert dbapi is not None
        cursor = dbapi.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout")
            (current,) = cursor.fetchone() or (wait,)
            cursor.execute(f"PRAGMA busy_timeout = {min(int(current), int(wait))}")
        finally:
            cursor.close()


class _StoreCore(EngineCore):
    """The store's engine core, which tells the store when a database in memory opened a second connection."""

    def __init__(self, store: KernelStore, **options: Any) -> None:
        self._store = store
        super().__init__(**options)

    def _rearm(self) -> None:
        self._store._rearm()


def _record_place_of(storage: StorageBackend) -> RecordPlace:
    """Where a file system whose root is *storage* keeps its records: the place it names, or memory."""
    place = storage.record_place if isinstance(storage, SupportsRecordPlace) else None
    return RecordPlace.in_memory() if place is None else place
