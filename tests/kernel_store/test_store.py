"""The kernel's store: its tables and first touch, its two transactions, the record after a change, its statements.

Each test runs on a SQLite file and on a store in memory, and a test
marked for both engines runs on a SQLite file and on the Postgres leg
behind ``VFS_TEST_POSTGRES_URL``. Rows are written in the test's own
``vfs_kernel_probe`` (``tests/support/kernel_store.py``). Every count is
of statements the store's engine sent, rows read back, files in a
directory, log records or an exit status, and none reads a clock.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import random
import sqlite3
import subprocess
import sys
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import Column, Integer, MetaData, Table, event, insert, select, text, update
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.lint.shapes import REPO
from tests.support.cancelled_callers import turns_of_the_loop
from tests.support.kernel_store import (
    PROBE_KEY,
    PROBE_TABLE,
    START,
    Gate,
    HeldWriter,
    SteppedClock,
    begins,
    chunk_sizes,
    count_rows,
    file_rows,
    files_in,
    inserting,
    probe_rows,
    probe_table,
    records,
    statements_of,
    without_waiting,
)
from tests.support.server_schemas import server_storage
from vfs import AsyncVirtualFileSystem, PostgresStorage, RecordPlace, SQLiteStorage, kernel_store
from vfs.kernel_store import KernelStore, KernelStoreUnavailable
from vfs.models.kernel_rows import KERNEL_FORMAT_VERSION, KERNEL_TABLE_PREFIXES, build_kernel_tables
from vfs.models.rows import SCHEMA_FORMAT_VERSION, build_vfs_tables
from vfs.results import ErrorKind, Severity
from vfs.storage.backends.database import seams
from vfs.storage.backends.database.dialects import StaleSnapshot
from vfs.storage.backends.database.engine import advisory_key

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from vfs.kernel_store import Transaction

IN_A_FILE = pytest.param("file", id="file")
IN_MEMORY = pytest.param("memory", id="memory")
ON_POSTGRES = pytest.param("postgres", marks=pytest.mark.postgres, id="postgres")

SQLITE_PLACES = [IN_A_FILE, IN_MEMORY]
"""Every test that names no engine: a SQLite file and a store in memory."""
BOTH_ENGINES = [IN_A_FILE, ON_POSTGRES]
"""A test of both engines: a SQLite file and the Postgres leg."""
EVERY_PLACE = [IN_A_FILE, IN_MEMORY, ON_POSTGRES]

NARROW_BUDGET = 1_000
"""The parameter budget a test narrows the store's dialect to, so 10,000 rows take many statements."""

# The words a closed store answers with, the closed kernel's own.
CLOSED = "the filesystem is closed"


@pytest.fixture
async def place(request: pytest.FixtureRequest, tmp_path: pathlib.Path) -> AsyncIterator[RecordPlace]:
    """The place the test names: a SQLite file a storage names, a database in memory, or a Postgres schema."""
    kind = request.param
    if kind == "file":
        place = SQLiteStorage(path=str(tmp_path / "knowledge.db")).record_place
        assert place is not None
        yield place
    elif kind == "memory":
        yield RecordPlace.in_memory()
    else:
        async with server_storage("VFS_TEST_POSTGRES_URL") as storage:
            place = storage.record_place
            assert place is not None
            yield place


@pytest.fixture
async def stores(place: RecordPlace) -> AsyncIterator[Callable[..., KernelStore]]:
    """A maker of stores on the test's place, each closed at teardown."""
    made: list[KernelStore] = []

    def make(**options: Any) -> KernelStore:
        made.append(store := KernelStore(place, **options))
        return store

    yield make
    for store in made:
        await store.close()


def narrowed(store: KernelStore, budget: int = NARROW_BUDGET) -> KernelStore:
    """*store* with its dialect's parameter budget narrowed to *budget*."""
    store.engine.sync_engine.dialect.insertmanyvalues_max_parameters = budget
    return store


async def rows_of(store: KernelStore, table: Table) -> list[tuple[Any, ...]]:
    """Every row of *table*, ordered by its key."""

    async def read(transaction: Transaction) -> list[tuple[Any, ...]]:
        statement = select(table).order_by(*(table.c[name] for name in PROBE_KEY))
        return [tuple(row) for row in (await transaction.execute(statement)).all()]

    return await store.query(read)


async def counter_of(store: KernelStore, table: Table, name: str = "n00000") -> int:
    async def read(transaction: Transaction) -> int:
        return (await transaction.execute(select(table.c.counter).where(table.c.name == name))).scalar_one()

    return await store.query(read)


def sqlite_file_of(place: RecordPlace) -> pathlib.Path:
    """The path of the SQLite file *place* names."""
    database = make_url(place.url).database
    assert database is not None
    return pathlib.Path(database)


async def until_sent(store: KernelStore, prefix: str) -> asyncio.Event:
    """An event set the first time the store's engine sends a statement that begins with *prefix*."""
    sent = asyncio.Event()

    @event.listens_for(store.engine.sync_engine, "before_cursor_execute")
    def watch(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.startswith(prefix):
            sent.set()

    return sent


# ---------------------------------------------------------------------------
# Where the records live, and first touch
# ---------------------------------------------------------------------------


def test_the_package_exports_the_constants_of_the_interface() -> None:
    """Guards a constant a spec that keeps a record reaches only through the module of the tables."""
    exported = {name: getattr(kernel_store, name) for name in ("KERNEL_FORMAT_VERSION", "KERNEL_TABLE_PREFIXES")}
    assert exported == {"KERNEL_FORMAT_VERSION": KERNEL_FORMAT_VERSION, "KERNEL_TABLE_PREFIXES": KERNEL_TABLE_PREFIXES}
    assert set(exported) <= set(kernel_store.__all__)


async def test_a_file_system_that_keeps_no_record_makes_no_file(tmp_path: pathlib.Path) -> None:
    """Guards a store that opens its engine, and so makes a file or a side file, when no record is kept."""
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")))
    connected: list[object] = []
    event.listen(fs._kernel_store.engine.sync_engine, "connect", lambda *made: connected.append(made))
    assert (await fs.write(path="/a.txt", content="kept")).success
    assert (await fs.read("/a.txt")).success
    await fs.close()
    assert (files_in(tmp_path), len(connected)) == (["knowledge.db"], 0)


async def test_first_use_makes_the_kernel_tables_in_the_mounts_file(tmp_path: pathlib.Path) -> None:
    """Guards a store that makes a file of its own, or touches the mount's meta row, at its first use."""
    path = tmp_path / "knowledge.db"
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(path)))
    assert (await fs.write(path="/a.txt", content="kept")).success
    await fs._kernel_store.ensure_ready()
    await fs.close()
    connection = sqlite3.connect(path)
    try:
        kernel = connection.execute("SELECT id, format_version FROM vfs_kernel_meta").fetchall()
        mount = connection.execute("SELECT schema_format_version FROM vfs_meta").fetchall()
    finally:
        connection.close()
    assert files_in(tmp_path) == ["knowledge.db"]
    assert (kernel, mount) == ([(1, KERNEL_FORMAT_VERSION)], [(SCHEMA_FORMAT_VERSION,)])


@pytest.mark.parametrize("order", ["together", "store first", "mount first"])
async def test_close_leaves_one_file_and_no_side_file(tmp_path: pathlib.Path, order: str) -> None:
    """Guards a second engine on the mount's file that leaves its log or its index file behind at close."""
    storage = SQLiteStorage(path=str(tmp_path / "knowledge.db"))
    fs = AsyncVirtualFileSystem(storage=storage)
    store = fs._kernel_store
    assert (await fs.write(path="/a.txt", content="kept")).success
    table = await probe_table(store)
    await store.commit(inserting(table, probe_rows(3), store))
    if order == "together":
        await fs.close()
    elif order == "store first":
        await store.close()
        await storage.close()
    else:
        await storage.close()
        await store.close()
    assert files_in(tmp_path) == ["knowledge.db"]
    assert file_rows(tmp_path / "knowledge.db", PROBE_TABLE) == 3


async def test_a_store_commit_waits_for_the_mount_writer_and_then_lands(tmp_path: pathlib.Path) -> None:
    """Guards a store write that fails, or lands, while a mount's write holds the file's writer."""
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")))
    store = fs._kernel_store
    table = await probe_table(store)
    assert (await fs.write(path="/a.txt", content="first")).success
    gate = Gate()
    with seams.installed("write:before-apply", gate):
        write = asyncio.ensure_future(fs.write(path="/b.txt", content="held"))
        await gate.reached.wait()
        began = await until_sent(store, "BEGIN IMMEDIATE")
        commit = asyncio.ensure_future(store.commit(inserting(table, probe_rows(1), store)))
        await began.wait()
        await turns_of_the_loop()
        assert (commit.done(), await count_rows(store, table)) == (False, 0)
        gate.open()
        assert (await write).success
        await commit
    assert await count_rows(store, table) == 1
    await fs.close()


async def test_a_store_commit_behind_a_held_mount_writer_fails_as_unavailable(tmp_path: pathlib.Path) -> None:
    """Guards a store write that waits past its tries, or that breaks the mount's write it waited behind."""
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")))
    store = fs._kernel_store
    table = await probe_table(store)
    assert (await fs.write(path="/a.txt", content="first")).success
    without_waiting(store)
    gate = Gate()
    with seams.installed("write:before-apply", gate):
        write = asyncio.ensure_future(fs.write(path="/b.txt", content="held"))
        await gate.reached.wait()
        sent = statements_of(store)
        with pytest.raises(KernelStoreUnavailable) as refused:
            await store.commit(inserting(table, probe_rows(1), store))
        gate.open()
        assert (await write).success
    assert begins(sent) == ["BEGIN IMMEDIATE"] * 4
    assert (refused.value.error.kind, refused.value.error.retryable) == (ErrorKind.unavailable, True)
    assert (await fs.read("/b.txt")).one().content == "held"
    await fs.close()


async def test_a_mount_read_returns_while_the_store_writer_is_held(tmp_path: pathlib.Path) -> None:
    """Guards a read of the mount that waits on the store's writer; a write waits for it and then lands."""
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")))
    store = fs._kernel_store
    table = await probe_table(store)
    assert (await fs.write(path="/a.txt", content="a needle here")).success
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        rival = asyncio.ensure_future(store.commit(inserting(table, probe_rows(1), store)))
        await gate.reached.wait()
        answered = [
            await fs.read("/a.txt"),
            await fs.grep("needle"),
            await fs.glob("**"),
            await fs.search("needle"),
        ]
        edit = asyncio.ensure_future(fs.edit("/a.txt", "needle", "pin"))
        await turns_of_the_loop()
        assert (len([result for result in answered if result.success]), edit.done()) == (4, False)
        gate.open()
        await rival
        assert (await edit).success
    assert (await fs.read("/a.txt")).one().content == "a pin here"
    await fs.close()


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_two_stores_touch_one_place_first_together(stores: Callable[..., KernelStore]) -> None:
    """Guards a first touch that two processes run at once and that makes two meta rows, or fails one."""
    first, second = stores(), stores()
    await asyncio.gather(first.ensure_ready(), second.ensure_ready())
    meta = first.tables.meta

    async def read(transaction: Transaction) -> list[tuple[Any, ...]]:
        return [tuple(row) for row in (await transaction.execute(select(meta.c.id, meta.c.format_version))).all()]

    assert await second.query(read) == [(1, KERNEL_FORMAT_VERSION)]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_two_calls_on_one_store_touch_it_first_once(stores: Callable[..., KernelStore]) -> None:
    """Guards a first touch that each waiting call runs again once the first has made the tables."""
    store = stores()
    sent = statements_of(store)
    await asyncio.gather(store.ensure_ready(), store.ensure_ready())
    assert begins(sent) == ["BEGIN IMMEDIATE"]


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_a_store_of_another_format_is_refused_and_named(
    place: RecordPlace, stores: Callable[..., KernelStore], caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a store of another format that is served, repaired, or named by a prefix a person would drop by."""
    other = stores()
    await other.ensure_ready()
    meta = other.tables.meta

    async def age(transaction: Transaction) -> None:
        await transaction.execute(update(meta).values(format_version=KERNEL_FORMAT_VERSION + 6))

    await other.commit(age)
    await other.close()
    storage = (
        SQLiteStorage(path=str(sqlite_file_of(place)))
        if place.schema is None
        else PostgresStorage(url=os.environ["VFS_TEST_POSTGRES_URL"], schema=place.schema)
    )
    fs = AsyncVirtualFileSystem(storage=storage)
    assert (await fs.write(path="/a.txt", content="kept")).success
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    for _ in range(2):
        with pytest.raises(KernelStoreUnavailable) as refused:
            await fs._kernel_store.query(lambda transaction: transaction.execute(select(meta.c.id)))
    error = refused.value.error
    assert (error.kind, error.data) == (
        ErrorKind.schema_mismatch,
        {"found": KERNEL_FORMAT_VERSION + 6, "expected": KERNEL_FORMAT_VERSION},
    )
    assert all(name in error.message for name in build_kernel_tables().names_to_drop())
    assert [word for word in (*KERNEL_TABLE_PREFIXES[1:], "prefix") if word in error.message] == []
    assert len(records(caplog, "WARNING")) == 1
    assert (await fs.read("/a.txt")).one().content == "kept"
    await fs.close()


@pytest.mark.postgres
async def test_the_store_pins_read_committed() -> None:
    """Guards a store transaction that runs at the role's or the server's level: a counter is then refused 40001."""
    async with server_storage("VFS_TEST_POSTGRES_URL") as storage:
        place = storage.record_place
        assert place is not None
        settings = {"connect_args": {"server_settings": {"default_transaction_isolation": "repeatable read"}}}
        repeatable = RecordPlace(url=place.url, label=place.label, engine_arguments=settings, schema=place.schema)
        first, second = KernelStore(repeatable), KernelStore(repeatable)
        refused: list[object] = []
        for store in (first, second):
            event.listen(store.engine.sync_engine, "handle_error", lambda context: refused.append(context))
        table = await probe_table(first)
        await first.commit(inserting(table, probe_rows(1), first))
        try:
            taken = await asyncio.gather(*(_take_numbers(store, table, 50) for store in (first, second)))
        finally:
            await first.close()
            await second.close()
    assert (sorted(taken[0] + taken[1]), len(refused)) == (list(range(1, 101)), 0)


@pytest.mark.postgres
@pytest.mark.parametrize("tables", ["missing", "present"])
async def test_a_role_that_may_not_create_is_told_the_grant(tables: str) -> None:
    """Guards a privilege refusal classified as a defect in vfs, or told with no grant to give."""
    async with server_storage("VFS_TEST_POSTGRES_URL") as storage:
        place = storage.record_place
        assert place is not None and place.schema is not None
        if tables == "present":
            owner = KernelStore(place)
            await owner.ensure_ready()
            await owner.close()
        role = f"vfs_role_{uuid4().hex[:12]}"
        grant = f"GRANT USAGE ON SCHEMA {place.schema} TO {role}"
        await _run_as_owner(f"CREATE ROLE {role} LOGIN PASSWORD 'pw'", grant)
        url = make_url(os.environ["VFS_TEST_POSTGRES_URL"]).set(username=role, password="pw")
        store = KernelStore(RecordPlace(url=url, label=place.label, schema=place.schema))
        raised: list[KernelStoreUnavailable] = []
        try:
            try:
                await store.commit(lambda transaction: transaction.execute(select(text("1"))))
            except KernelStoreUnavailable as refusal:
                raised.append(refusal)
        finally:
            await store.close()
            await _run_as_owner(f"DROP OWNED BY {role}", f"DROP ROLE {role}")
    errors = [refusal.error for refusal in raised]
    assert (len(errors), [error for error in errors if error.kind is ErrorKind.internal]) == (1, [])
    assert (errors[0].kind, errors[0].retryable) == (ErrorKind.unavailable, False)
    assert "grant this role SELECT, INSERT, UPDATE and DELETE" in errors[0].message
    assert "vfs_kernel_meta" in errors[0].message


async def test_a_place_that_is_not_a_database_is_refused(tmp_path: pathlib.Path) -> None:
    """Guards a first touch whose failure escapes raw, where every caller of the store expects one exception."""
    path = tmp_path / "knowledge.db"
    path.write_bytes(b"this file is no database at all, and SQLite says so" * 100)
    store = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{path}", label=str(path)))
    with pytest.raises(KernelStoreUnavailable) as refused:
        await store.ensure_ready()
    await store.close()
    assert refused.value.error.kind is ErrorKind.unavailable


async def test_a_database_in_memory_opened_again_has_its_tables_made_again() -> None:
    """Guards a store in memory that trusts its first touch after its one connection, and its tables, were lost.

    As a mount's host does, the store learns of the new connection when the call that opened it is already
    past first touch, so that call meets the empty database and the next one makes the tables again.
    """
    store = KernelStore(RecordPlace.in_memory())
    await store.ensure_ready()
    await store.engine.dispose()
    read = select(store.tables.meta.c.format_version)
    with pytest.raises(KernelStoreUnavailable):
        await store.query(lambda transaction: _scalar(transaction, read))
    found = await store.query(lambda transaction: _scalar(transaction, read))
    await store.close()
    assert found == KERNEL_FORMAT_VERSION


# ---------------------------------------------------------------------------
# What Postgres decides, read with no server
# ---------------------------------------------------------------------------


POSTGRES_PLACE = RecordPlace(url="postgresql+asyncpg://app@db/vfs", label="tenant_a", schema="tenant_a")
"""A place on Postgres that no test connects to: the store's choices for it are read with no I/O."""


async def test_a_postgres_transaction_is_pinned_to_read_committed_and_a_sqlite_one_is_not(
    tmp_path: pathlib.Path,
) -> None:
    """Guards the pin each store transaction carries on Postgres, and an isolation level SQLite would refuse."""
    on_postgres = KernelStore(POSTGRES_PLACE)
    on_sqlite = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{tmp_path}/k.db", label="k.db"))
    options = [store._options(writer=writer) for store in (on_postgres, on_sqlite) for writer in (True, False)]
    for store in (on_postgres, on_sqlite):
        await store.close()
    assert options == [
        {"vfs_writer": True, "isolation_level": "READ COMMITTED"},
        {"isolation_level": "READ COMMITTED"},
        {"vfs_writer": True},
        {},
    ]


async def test_first_touch_on_postgres_takes_a_lock_of_its_own() -> None:
    """Guards a first touch that two processes run unserialized, or that takes the mount's own lock."""

    class Recording:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def execute(self, statement: object) -> None:
            self.statements.append(statement)

    store = KernelStore(POSTGRES_PLACE)
    connection = Recording()
    await store._serialization_point(connection)  # ty: ignore[invalid-argument-type]
    await store.close()
    mount_key = advisory_key(build_vfs_tables(schema="tenant_a").entry.fullname)
    assert ["pg_advisory_xact_lock" in str(statement) for statement in connection.statements] == [True]
    assert store._key != mount_key


@pytest.mark.parametrize(
    ("place", "remedy"),
    [
        (
            RecordPlace(url="sqlite+aiosqlite:////srv/k.db", label="/srv/k.db"),
            "close every process that uses /srv/k.db",
        ),
        (POSTGRES_PLACE, "drop these tables in schema tenant_a: vfs_kernel_meta"),
        (RecordPlace(url="postgresql+asyncpg://app@db/vfs", label="the default schema"), "in the default schema"),
    ],
    ids=["sqlite", "postgres", "postgres-default-schema"],
)
async def test_the_refusal_of_another_format_names_each_engines_remedy(place: RecordPlace, remedy: str) -> None:
    """Guards a remedy that names the file for deletion, which holds the mount, or no table at all."""
    store = KernelStore(place)
    refusal = store._format_refusal(KERNEL_FORMAT_VERSION + 1)
    await store.close()
    assert remedy in refusal.message
    assert ("delete" in refusal.message, refusal.message.endswith("vfs_kernel_meta")) == (False, True)


async def test_a_refused_privilege_is_never_a_defect() -> None:
    """Guards a privilege refusal read as a statement defect, ``vfs.internal``, which only VFS could fix."""
    origin = AsyncAdapt_asyncpg_dbapi.ProgrammingError("permission denied for table vfs_kernel_meta")
    origin.pgcode = origin.sqlstate = "42501"  # ty: ignore[unresolved-attribute]
    store = KernelStore(POSTGRES_PLACE)
    error = store._classify(ProgrammingError("SELECT 1", None, origin))
    defect = store._classify(ProgrammingError("SELEC 1", None, _defect()))
    await store.close()
    assert (error.kind, error.retryable, defect.kind) == (ErrorKind.unavailable, False, ErrorKind.internal)
    assert "make them once with a role that may" in error.message


# ---------------------------------------------------------------------------
# query and commit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_query_is_not_a_writer(stores: Callable[..., KernelStore]) -> None:
    """Guards a query that takes the file's writer, which would queue it behind every write of the mount."""
    store = stores()
    await store.ensure_ready()
    sent = statements_of(store)
    await store.query(lambda transaction: transaction.execute(select(store.tables.meta.c.id)))
    assert begins(sent) == ["BEGIN"]


async def test_a_commit_behind_a_held_writer_gives_up_after_four_tries(tmp_path: pathlib.Path) -> None:
    """Guards a commit that tries more or fewer times than a mount's write, or gives up as no retryable refusal."""
    path = tmp_path / "knowledge.db"
    store = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{path}", label=str(path)))
    table = await probe_table(store)
    without_waiting(store)
    holder = HeldWriter(path)
    holder.hold()
    sent = statements_of(store)
    try:
        with pytest.raises(KernelStoreUnavailable) as refused:
            await store.commit(inserting(table, probe_rows(1), store))
    finally:
        holder.release()
        await store.close()
    assert begins(sent) == ["BEGIN IMMEDIATE"] * 4
    assert (refused.value.error.kind, refused.value.error.retryable) == (ErrorKind.unavailable, True)
    assert "kernel store kept losing to concurrent changes" in refused.value.error.message


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_closed_store_answers_as_the_closed_kernel_does(stores: Callable[..., KernelStore]) -> None:
    """Guards a closed store that opens its engine again, or answers in words of its own."""
    store = stores()
    await store.ensure_ready()
    await store.close()
    raised: list[KernelStoreUnavailable] = []
    for call in (store.query, store.commit):
        with pytest.raises(KernelStoreUnavailable) as refused:
            await call(lambda transaction: transaction.execute(select(text("1"))))
        raised.append(refused.value)
    with pytest.raises(KernelStoreUnavailable) as touched:
        await store.ensure_ready()
    raised.append(touched.value)
    warning = await store.record_after(lambda transaction: transaction.execute(select(text("1"))))
    assert [(refusal.error.kind, refusal.error.message.endswith(CLOSED)) for refusal in raised] == [
        (ErrorKind.backend_unavailable, True)
    ] * 3
    assert warning is not None and warning.message.endswith(CLOSED)


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_next_number_has_no_repeat_and_no_gap_under_two_stores(stores: Callable[..., KernelStore]) -> None:
    """Guards a counter that two processes read before either writes: they would take one number twice."""
    first, second = stores(), stores()
    table = await probe_table(first)
    await first.commit(inserting(table, probe_rows(1), first))
    taken = await asyncio.gather(*(_take_numbers(store, table, 50) for store in (first, second)))
    assert sorted(taken[0] + taken[1]) == list(range(1, 101))


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_block_of_numbers_ends_at_what_is_returned(stores: Callable[..., KernelStore]) -> None:
    """Guards a block whose first number is returned, or that adds one in place of its count."""
    store = stores()
    table = await probe_table(store)
    await store.commit(inserting(table, probe_rows(1, counter=7), store))

    async def take(transaction: Transaction) -> int:
        return await store.next_number(transaction, table.c.counter, table.c.name == "n00000", count=5)

    assert (await store.commit(take), await counter_of(store, table)) == (12, 12)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_next_number_on_no_row_raises(stores: Callable[..., KernelStore]) -> None:
    """Guards a counter with no owning row that answers a number, or a store failure in place of the caller's."""
    store = stores()
    table = await probe_table(store)

    async def take(transaction: Transaction) -> int:
        return await store.next_number(transaction, table.c.counter, table.c.name == "nobody")

    with pytest.raises(LookupError):
        await store.commit(take)


# ---------------------------------------------------------------------------
# Many rows
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_insert_rows_stays_under_the_parameter_budget(
    place: RecordPlace, stores: Callable[..., KernelStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards an insert that pages by the engine's own cap, or by none, in place of the live budget."""
    store = narrowed(stores())
    table = await probe_table(store)
    copied: list[int] = []
    copy = asyncpg.Connection.copy_records_to_table

    async def counted(self: asyncpg.Connection, *arguments: Any, records: list[Any], **options: Any) -> Any:
        copied.append(len(records))
        return await copy(self, *arguments, records=records, **options)

    monkeypatch.setattr(asyncpg.Connection, "copy_records_to_table", counted)
    sent = statements_of(store)
    await store.commit(inserting(table, probe_rows(10_000), store))
    pages = copied if place.schema is not None else [item.rows for item in sent if item.sql.startswith("INSERT")]
    assert (len(pages), max(pages), sum(pages)) == (50, 200, 10_000)
    assert await count_rows(store, table) == 10_000


@pytest.mark.slow
@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_upsert_rows_chunks_sorts_and_keeps_the_newest(stores: Callable[..., KernelStore]) -> None:
    """Guards an upsert that grows with its rows, locks keys out of order, or lets an older row win."""
    store = narrowed(stores())
    table = await probe_table(store)
    shuffled = probe_rows(10_000, counter=1)
    random.Random(7).shuffle(shuffled)

    def upsert(counter: int) -> Callable[[Transaction], Any]:
        rows = [{**row, "counter": counter} for row in shuffled]

        async def write(transaction: Transaction) -> int:
            return await store.upsert_rows(
                transaction, table, rows, key=PROBE_KEY, update=("counter",), newest="counter"
            )

        return write

    sent = statements_of(store)
    written = await store.commit(upsert(1))
    inserts = [item for item in sent if item.sql.startswith("INSERT")]
    assert (written, len(inserts), max(item.binds for item in inserts)) == (10_000, 50, 1_000)
    assert await store.commit(upsert(0)) == 0
    assert await store.commit(upsert(2)) == 10_000
    assert {row[3] for row in await rows_of(store, table)} == {2}


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_upsert_rows_sends_keys_in_order(stores: Callable[..., KernelStore]) -> None:
    """Guards an upsert that sends its rows as given: two processes would then lock one pair of keys crosswise."""
    store = narrowed(stores(), budget=10)
    table = await probe_table(store)
    rows = probe_rows(6)
    random.Random(3).shuffle(rows)
    sent: list[tuple[Any, ...]] = []

    @event.listens_for(store.engine.sync_engine, "before_cursor_execute")
    def record(_conn: Any, _cursor: Any, statement: str, parameters: Any, *_rest: Any) -> None:
        if statement.startswith("INSERT"):
            sent.append(tuple(parameters))

    async def write(transaction: Transaction) -> int:
        return await store.upsert_rows(transaction, table, rows, key=PROBE_KEY, update=())

    assert await store.commit(write) == 6
    names = [value for parameters in sent for value in parameters if str(value).startswith("n0")]
    assert (len(sent), names) == (3, [f"n{index:05d}" for index in range(6)])


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_an_upsert_that_names_a_key_twice_is_refused(stores: Callable[..., KernelStore]) -> None:
    """Guards the one check that keeps SQLite, which stores the later row, from Postgres, which refuses 21000."""
    store = stores()
    table = await probe_table(store)
    rows = [*probe_rows(2), probe_rows(1)[0]]
    sent = statements_of(store)

    async def write(transaction: Transaction) -> int:
        return await store.upsert_rows(transaction, table, rows, key=PROBE_KEY, update=("counter",))

    with pytest.raises(ValueError, match="twice"):
        await store.commit(write)
    assert [item for item in sent if item.sql.startswith("INSERT")] == []


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_upsert_rows_says_how_many_rows_it_wrote(stores: Callable[..., KernelStore]) -> None:
    """Guards an insert that does nothing on a conflict and still counts the rows it was given."""
    store = stores()
    table = await probe_table(store)

    def insert_new(rows: list[dict[str, object]]) -> Callable[[Transaction], Any]:
        async def write(transaction: Transaction) -> int:
            return await store.upsert_rows(transaction, table, rows, key=PROBE_KEY, update=())

        return write

    first = await store.commit(insert_new(probe_rows(8)))
    second = await store.commit(insert_new(probe_rows(9)[5:]))
    assert (first, second, await count_rows(store, table)) == (8, 1, 9)


@pytest.mark.parametrize("place", [IN_MEMORY], indirect=True)
async def test_row_chunks_and_key_chunks_cut_by_the_budget(stores: Callable[..., KernelStore]) -> None:
    """Guards a chunking that ignores a statement's extra binds, or the binds a key of two columns takes."""
    store = narrowed(stores())
    rows = probe_rows(10_000)
    pairs = [(row["owner"], row["name"]) for row in rows]
    pair_chunks = chunk_sizes(store.key_chunks(pairs, width=2))
    assert (len(chunk_sizes(store.row_chunks(rows))), len(chunk_sizes(store.row_chunks(rows, width=10)))) == (50, 100)
    assert max(pair_chunks) <= store.membership_budget // 2
    assert sum(pair_chunks) == 10_000
    assert chunk_sizes(store.key_chunks(list(range(5)))) == [5]
    assert chunk_sizes(store.row_chunks([])) == []


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_delete_expired_binds_the_same_values_whatever_it_removes(stores: Callable[..., KernelStore]) -> None:
    """Guards a reclaim that binds a key list, which grows with the rows it removes to an engine's cap."""
    clock = SteppedClock()
    store = stores(clock=clock)
    table = await probe_table(store)
    sent = statements_of(store)
    shapes: list[tuple[str, int]] = []
    removed: list[int] = []
    for count in (3, 12_000):
        await store.commit(inserting(table, probe_rows(count, owner=f"o{count}", expires_at=START), store))
        clock.step(60)

        async def reclaim(transaction: Transaction) -> int:
            return await store.delete_expired(
                transaction, table, key=table.c.name, expires=table.c.expires_at, now=store.now(), limit=5_000
            )

        sent.clear()
        removed.append(await store.commit(reclaim))
        deletes = [item for item in sent if item.sql.startswith("DELETE")]
        shapes += [(item.sql, item.binds) for item in deletes]
    assert (removed, len(shapes), len(set(shapes)), shapes[0][1]) == ([3, 5_000], 2, 1, 3)


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_delete_where_removes_at_most_its_limit_by_a_three_column_key(
    place: RecordPlace, stores: Callable[..., KernelStore]
) -> None:
    """Guards a bounded delete that takes one column of a key of three, or grows with the rows it matches."""
    store = stores()
    table = await probe_table(store)
    key = [table.c[name] for name in PROBE_KEY]
    sent = statements_of(store)
    binds: list[int] = []
    for count, owner in ((8, "small"), (8_000, "large")):
        await store.commit(inserting(table, probe_rows(count, owner=owner), store))
        await store.commit(inserting(table, probe_rows(2, owner=owner, scope="other"), store))

        async def remove(transaction: Transaction, owner: str = owner) -> int:
            match = (table.c.owner == owner) & (table.c.scope == "s")
            return await store.delete_where(transaction, table, key=key, where=match, limit=5, order_by=table.c.name)

        sent.clear()
        assert await store.commit(remove) == 5
        binds += [item.binds for item in sent if item.sql.startswith("DELETE")]
    kept = await rows_of(store, table)
    small = [row for row in kept if row[0] == "small"]
    assert ([row[2] for row in small if row[1] == "s"], len(small), len(set(binds))) == (
        ["n00005", "n00006", "n00007"],
        5,
        1,
    )
    assert binds[0] == (4 if place.schema is None else 3)


# ---------------------------------------------------------------------------
# One transaction for several functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
@pytest.mark.parametrize("second_raises", [False, True])
async def test_two_functions_share_one_commit(stores: Callable[..., KernelStore], second_raises: bool) -> None:
    """Guards a commit whose functions each commit alone: a failure in the second would keep the first's row."""
    store = stores()
    table = await probe_table(store)

    async def first(transaction: Transaction) -> None:
        await transaction.execute(insert(table).values(probe_rows(1, owner="first")))

    async def second(transaction: Transaction) -> None:
        await transaction.execute(insert(table).values(probe_rows(1, owner="second")))
        if second_raises:
            raise RuntimeError("the second function failed")

    async def both(transaction: Transaction) -> None:
        await first(transaction)
        await second(transaction)

    if second_raises:
        with pytest.raises(RuntimeError, match="second"):
            await store.commit(both)
    else:
        await store.commit(both)
    assert await count_rows(store, table) == (0 if second_raises else 2)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_transactions_info_ends_with_it(stores: Callable[..., KernelStore]) -> None:
    """Guards a store that reuses one transaction, or one ``info``, across commits or across a retry."""
    store = stores(retry_base_delay=0)
    seen: list[dict[str, Any]] = []

    async def first(transaction: Transaction) -> None:
        transaction.info["found"] = "once"
        await transaction.execute(select(text("1")))
        seen.append(dict(transaction.info))

    async def retried(transaction: Transaction) -> None:
        seen.append(dict(transaction.info))
        transaction.info["found"] = "again"
        if len(seen) == 2:
            raise StaleSnapshot("a rival moved")

    await store.commit(first)
    await store.commit(retried)
    assert seen == [{"found": "once"}, {}, {}]


@pytest.mark.parametrize("place", EVERY_PLACE, indirect=True)
async def test_two_commits_at_once_both_land(stores: Callable[..., KernelStore]) -> None:
    """Guards two commits of one store that share a connection, or of which one waits forever on the other."""
    store = stores()
    table = await probe_table(store)
    await asyncio.gather(*(store.commit(inserting(table, probe_rows(1, owner=owner), store)) for owner in "ab"))
    assert await count_rows(store, table) == 2


# ---------------------------------------------------------------------------
# A record after its change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_record_after_survives_its_callers_cancellation(
    stores: Callable[..., KernelStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards a record that a cancellation stops between a change and its record, or that answers a new error."""
    store = stores()
    table = await probe_table(store)
    thrown: list[BaseException] = []
    wait = asyncio.wait

    async def recording(tasks: Any) -> Any:
        try:
            return await wait(tasks)
        except asyncio.CancelledError as error:
            thrown.append(error)
            raise

    gate = Gate()
    monkeypatch.setattr(asyncio, "wait", recording)
    with seams.installed("kernel-store:before-commit", gate):
        caller = asyncio.ensure_future(store.record_after(inserting(table, probe_rows(1), store)))
        await gate.reached.wait()
        caller.cancel("the caller gave up")
        await turns_of_the_loop()
        gate.open()
        with pytest.raises(asyncio.CancelledError) as raised:
            await caller
    monkeypatch.undo()
    assert (await count_rows(store, table), raised.value is thrown[0]) == (1, True)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_record_after_returns_a_warning_when_the_store_cannot_be_written(
    stores: Callable[..., KernelStore],
) -> None:
    """Guards a record that raises after its change has landed, or answers with an error the change would fail on."""
    store = stores()
    missing = Table("vfs_kernel_never_made", MetaData(), Column("id", Integer, primary_key=True))
    warning = await store.record_after(lambda transaction: transaction.execute(insert(missing).values(id=1)))
    assert warning is not None
    assert (warning.kind, warning.severity, warning.retryable) == (ErrorKind.unavailable, Severity.warning, False)
    assert "the change is committed, and the kernel's record of it was not written" in warning.message
    assert await store.record_after(lambda transaction: transaction.execute(select(text("1")))) is None


async def test_record_after_behind_a_held_writer_returns_its_warning_after_four_tries(tmp_path: pathlib.Path) -> None:
    """Guards a record behind a held writer that raises, tries more or fewer times than a commit, or says retry."""
    path = tmp_path / "knowledge.db"
    store = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{path}", label=str(path)))
    table = await probe_table(store)
    without_waiting(store)
    holder = HeldWriter(path)
    holder.hold()
    sent = statements_of(store)
    try:
        warning = await store.record_after(inserting(table, probe_rows(1), store))
    finally:
        holder.release()
    assert warning is not None
    assert (warning.kind, warning.severity, warning.retryable) == (ErrorKind.unavailable, Severity.warning, False)
    assert "kernel store kept losing to concurrent changes" in warning.message
    assert (begins(sent), await count_rows(store, table)) == (["BEGIN IMMEDIATE"] * 4, 0)
    await store.close()


async def test_a_failed_first_touch_is_tried_again(tmp_path: pathlib.Path) -> None:
    """Guards a first touch whose failure is remembered: the store would refuse every call after a passing hold."""
    path = tmp_path / "knowledge.db"
    sqlite3.connect(path).close()
    store = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{path}", label=str(path)), retry_base_delay=0)
    without_waiting(store)
    holder = HeldWriter(path)
    holder.hold()
    try:
        with pytest.raises(KernelStoreUnavailable):
            await store.ensure_ready()
    finally:
        holder.release()
    await store.ensure_ready()
    assert await store.query(lambda transaction: _scalar(transaction, select(store.tables.meta.c.id))) == 1
    await store.close()


@pytest.mark.slow
async def test_a_process_that_dies_between_a_change_and_its_record_leaves_the_change_alone(
    tmp_path: pathlib.Path,
) -> None:
    """Guards a record written before its change, or inside the mount's transaction: it would outlive the change."""
    path = tmp_path / "knowledge.db"
    status = _child(path, "record")
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(path)))
    content = (await fs.read("/change.txt")).one().content
    await fs.close()
    assert (status, content, file_rows(path, PROBE_TABLE)) == (0, "landed", 0)


@pytest.mark.slow
@pytest.mark.parametrize(("stage", "landed"), [("claim", False), ("completion", True)])
async def test_a_process_that_dies_after_its_claim_leaves_the_claim_in_doubt(
    tmp_path: pathlib.Path, stage: str, landed: bool
) -> None:
    """Guards a claim committed after its change, or a completion committed with the claim."""
    path = tmp_path / "knowledge.db"
    status = _child(path, stage)
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(path)))
    found = (await fs.read("/change.txt")).success
    await fs.close()
    connection = sqlite3.connect(path)
    try:
        claims = connection.execute(f"SELECT counter FROM {PROBE_TABLE}").fetchall()
    finally:
        connection.close()
    assert (status, claims, found) == (0, [(0,)], landed)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _take_numbers(store: KernelStore, table: Table, count: int) -> list[int]:
    """Take *count* numbers from the probe row's counter, one commit each."""

    async def take(transaction: Transaction) -> int:
        return await store.next_number(transaction, table.c.counter, table.c.name == "n00000")

    return [await store.commit(take) for _ in range(count)]


async def _scalar(transaction: Transaction, statement: Any) -> Any:
    return (await transaction.execute(statement)).scalar_one()


def _defect() -> BaseException:
    """A driver error of a statement defect, SQLSTATE 42601."""
    origin = AsyncAdapt_asyncpg_dbapi.ProgrammingError("syntax error at or near SELEC")
    origin.pgcode = origin.sqlstate = "42601"  # ty: ignore[unresolved-attribute]
    return origin


async def _run_as_owner(*statements: str) -> None:
    """Run *statements* on the Postgres leg as the role the suite connects with."""
    engine = create_async_engine(os.environ["VFS_TEST_POSTGRES_URL"], isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


# What a child process runs: it changes the file system and leaves through os._exit at the stage it is given.
_CHILD = """
import asyncio, os, sys
from sqlalchemy import update
from vfs import AsyncVirtualFileSystem, SQLiteStorage
from vfs.storage.backends.database import seams
from tests.support.kernel_store import inserting, probe_rows, probe_table


async def leave():
    os._exit(0)


async def main(path, stage):
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=path))
    store = fs._kernel_store
    table = await probe_table(store)
    if stage != "record":
        await store.commit(inserting(table, probe_rows(1), store))
    if stage == "claim":
        seams.install("write:before-apply", leave)
    await fs.write(path="/change.txt", content="landed")
    seams.install("kernel-store:before-commit", leave)
    if stage == "record":
        await store.record_after(inserting(table, probe_rows(1), store))
    else:
        await store.record_after(lambda transaction: transaction.execute(update(table).values(counter=1)))
    sys.exit(3)


asyncio.run(main(sys.argv[1], sys.argv[2]))
"""


def _child(path: pathlib.Path, stage: str) -> int:
    """Run the child at *stage* on the file at *path*, and return its exit status."""
    done = subprocess.run([sys.executable, "-c", _CHILD, str(path), stage], cwd=REPO, timeout=120, check=False)
    return done.returncode
