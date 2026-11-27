"""What the tests of the kernel's store share: a clock a test steps, a table to write rows in, a kind, and counts.

The store's one table, ``vfs_kernel_meta``, holds one row, so a test that
writes rows writes them in ``vfs_kernel_probe``, a table of the test's own
that :func:`probe_table` makes in a ``commit`` of the store. It is in no
build of ``build_kernel_tables``. Its key is three columns, so a bounded
delete by a row value has one to run on; it has a counter for
``next_number`` and ``newest``, and an expiry, which may be null.

    table = await probe_table(store)
    await store.commit(lambda t: store.insert_rows(t, table, probe_rows(3)))
    assert await count_rows(store, table) == 3

A kind written behind that writes in the probe table is :func:`probe_kind`.

Every count reads the database through the store or through a plain
``sqlite3`` connection on the file, and none reads a clock.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, event, func, select
from sqlalchemy.engine import make_url

from vfs.kernel_store import BehindKind

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence

    from vfs import RecordPlace
    from vfs.kernel_store import KernelStore, Transaction

PROBE_TABLE: Final = "vfs_kernel_probe"
"""The name of the test's own table; it begins with a kernel prefix, as every kernel table's does."""

PROBE_KEY: Final = ("owner", "scope", "name")
"""The probe table's key, three columns."""

START: Final = datetime(2026, 1, 1, tzinfo=UTC)
"""Where a stepped clock starts."""

TASK_NAME: Final = "vfs-kernel-store"
"""The name of the store's one background task, as the tests look for it."""

IN_A_FILE = pytest.param("file", id="file")
IN_MEMORY = pytest.param("memory", id="memory")
ON_POSTGRES = pytest.param("postgres", marks=pytest.mark.postgres, id="postgres")

SQLITE_PLACES: Final = [IN_A_FILE, IN_MEMORY]
"""Every test that names no engine: a SQLite file and a store in memory."""
BOTH_ENGINES: Final = [IN_A_FILE, ON_POSTGRES]
"""A test of both engines: a SQLite file and the Postgres leg."""
EVERY_PLACE: Final = [IN_A_FILE, IN_MEMORY, ON_POSTGRES]


class SteppedClock:
    """A clock that a test steps forward, and that never moves by itself."""

    def __init__(self, start: datetime = START) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def step(self, seconds: float) -> None:
        """Move the clock *seconds* forward."""
        self._now += timedelta(seconds=seconds)


class Sent(NamedTuple):
    """One statement the store's engine sent: its text, its binds, and whether it was an executemany."""

    sql: str
    binds: int
    many: bool
    rows: int


# ---------------------------------------------------------------------------
# The probe table
# ---------------------------------------------------------------------------


async def probe_table(store: KernelStore) -> Table:
    """Make the test's ``vfs_kernel_probe`` in the store's schema, in a ``commit`` of the store's own."""
    table = probe_table_shape(store)

    async def make(transaction: Transaction) -> None:
        connection = await transaction.connection()
        await connection.run_sync(table.metadata.create_all, checkfirst=True)

    await store.commit(make)
    return table


def probe_table_shape(store: KernelStore) -> Table:
    """The test's ``vfs_kernel_probe`` in the store's schema, as a table, made nowhere."""
    return Table(
        PROBE_TABLE,
        MetaData(),
        Column("owner", String(64), primary_key=True),
        Column("scope", String(64), primary_key=True),
        Column("name", String(64), primary_key=True),
        Column("counter", Integer, nullable=False),
        Column("expires_at", DateTime(timezone=True)),
        schema=store.tables.meta.schema,
    )


def probe_rows(
    count: int, *, owner: str = "o", scope: str = "s", counter: int = 0, expires_at: datetime | None = None
) -> list[dict[str, object]]:
    """*count* rows of five fields, named ``n00000`` upwards so their keys sort as they are numbered."""
    return [
        {"owner": owner, "scope": scope, "name": f"n{index:05d}", "counter": counter, "expires_at": expires_at}
        for index in range(count)
    ]


def probe_kind(
    table: Table,
    *,
    name: str = "probe",
    keyed: bool = False,
    seen: list[Written] | None = None,
) -> BehindKind:
    """A kind written behind into *table*: inserted, or upserted by the probe key when *keyed*.

    Each call of its ``write`` is appended to *seen*, with the transaction
    it was handed and a copy of its rows.
    """

    async def write(store: KernelStore, transaction: Transaction, rows: Sequence[Mapping[str, object]]) -> None:
        if seen is not None:
            seen.append(Written(name, transaction, [dict(row) for row in rows]))
        if keyed:
            await store.upsert_rows(transaction, table, rows, key=PROBE_KEY, update=("counter",))
        else:
            await store.insert_rows(transaction, table, rows)

    return BehindKind(name=name, write=write, key=PROBE_KEY if keyed else None)


class Written(NamedTuple):
    """One call of a kind's ``write``: the kind's name, the transaction it was handed, and its rows."""

    kind: str
    transaction: object
    rows: list[dict[str, object]]


async def count_rows(store: KernelStore, table: Table) -> int:
    """How many rows *table* holds, read in a ``query`` of the store."""

    async def count(transaction: Transaction) -> int:
        return (await transaction.execute(select(func.count()).select_from(table))).scalar_one()

    return await store.query(count)


def file_rows(path: Path, table: str) -> int:
    """How many rows *table* holds in the SQLite file at *path*, read by a plain ``sqlite3`` connection."""
    connection = sqlite3.connect(path)
    try:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


def inserting(table: Table, rows: list[dict[str, object]], store: KernelStore) -> Callable[[Any], Awaitable[None]]:
    """The ``fn`` of a commit that inserts *rows* into *table* through the store's ``insert_rows``."""

    async def insert(transaction: Transaction) -> None:
        await store.insert_rows(transaction, table, rows)

    return insert


# ---------------------------------------------------------------------------
# Counting what the store sends
# ---------------------------------------------------------------------------


def statements_of(store: KernelStore) -> list[Sent]:
    """A list that fills with every statement the store's engine sends from now on."""
    sent: list[Sent] = []

    @event.listens_for(store.engine.sync_engine, "before_cursor_execute")
    def record(_conn: Any, _cursor: Any, statement: str, parameters: Any, _context: Any, executemany: bool) -> None:
        rows = len(parameters) if executemany else 1
        binds = sum(len(row) for row in parameters) if executemany else len(parameters or ())
        sent.append(Sent(statement, binds, executemany, rows))

    return sent


def begins(sent: list[Sent]) -> list[str]:
    """Each ``BEGIN`` among *sent*, as it was written."""
    return [item.sql for item in sent if item.sql.startswith("BEGIN")]


class Connections:
    """The connections a store's engine opens from now on, and how many of them are still open."""

    def __init__(self, store: KernelStore) -> None:
        self.opened: list[object] = []
        self.closed = 0
        engine = store.engine.sync_engine
        event.listen(engine, "connect", self._connected)
        event.listen(engine, "close", self._closed)
        event.listen(engine, "close_detached", self._detached)

    @property
    def open(self) -> int:
        """How many of the connections opened are not yet closed."""
        return len(self.opened) - self.closed

    def _connected(self, dbapi_connection: object, _record: object) -> None:
        self.opened.append(dbapi_connection)

    def _closed(self, _dbapi_connection: object, _record: object) -> None:
        self.closed += 1

    def _detached(self, _dbapi_connection: object) -> None:
        self.closed += 1


def without_waiting(store: KernelStore) -> None:
    """Make each connection the store checks out from now on give up at once on a held writer."""

    @event.listens_for(store.engine.sync_engine, "checkout")
    def impatient(dbapi_connection: Any, _record: Any, _proxy: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 0")
        cursor.close()


class HeldWriter:
    """A plain ``sqlite3`` connection that holds a file's writer from :meth:`hold` until :meth:`release`."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path, isolation_level=None)

    def hold(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def release(self) -> None:
        if self._connection.in_transaction:
            self._connection.execute("ROLLBACK")
        self._connection.close()


class Gate:
    """A seam handler that holds its caller the first *times* it is reached after *skip*, until the test opens it."""

    def __init__(self, times: int = 1, *, skip: int = 0) -> None:
        self.reached = asyncio.Event()
        self.entered = 0
        self._open = asyncio.Event()
        self._times = times
        self._skip = skip

    async def __call__(self) -> None:
        self.entered += 1
        if self._skip < self.entered <= self._skip + self._times:
            self.reached.set()
            await self._open.wait()

    def open(self) -> None:
        self._open.set()


def store_tasks() -> list[asyncio.Task[Any]]:
    """The tasks of the running loop that are a store's one background task."""
    return [task for task in asyncio.all_tasks() if task.get_name() == TASK_NAME]


def sqlite_file_of(place: RecordPlace) -> Path:
    """The path of the SQLite file *place* names."""
    database = make_url(place.url).database
    assert database is not None
    return Path(database)


def files_in(path: Path) -> list[str]:
    """The names of the files in the directory *path*, sorted."""
    return sorted(item.name for item in path.iterdir())


def records(caplog: Any, level: str) -> list[str]:
    """The messages logged at *level* under ``vfs.kernel_store``."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("vfs.kernel_store") and record.levelname == level
    ]


def chunk_sizes(chunks: Iterator[Any]) -> list[int]:
    """The length of each chunk an iterator gives."""
    return [len(chunk) for chunk in chunks]
