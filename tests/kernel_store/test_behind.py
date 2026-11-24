"""The writer behind: ``put_behind``, the one task, ``drain``, the rows that wait, the bound, and the flushes at close.

Each test runs on a SQLite file and on a store in memory unless it names
a place, and a test marked for both engines runs on a SQLite file and on
the Postgres leg behind ``VFS_TEST_POSTGRES_URL``. Rows are written in the
test's own ``vfs_kernel_probe`` by kinds of the test's own. The task is
driven by ``put_behind``, ``drain`` and ``close`` alone, and held at the
store's seams; every count is of statements, rows, calls of a kind's
``write``, files, log records or an exit status, and none reads a clock.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import random
import subprocess
import sys
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, event, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.lint.shapes import REPO
from tests.support.cancelled_callers import turns_of_the_loop
from tests.support.kernel_store import (
    BOTH_ENGINES,
    IN_A_FILE,
    PROBE_TABLE,
    SQLITE_PLACES,
    Connections,
    Gate,
    HeldWriter,
    Written,
    begins,
    count_rows,
    file_rows,
    files_in,
    inserting,
    probe_kind,
    probe_rows,
    probe_table,
    probe_table_shape,
    records,
    sqlite_file_of,
    statements_of,
    store_tasks,
    without_waiting,
)
from tests.support.server_schemas import server_storage
from vfs import AsyncVirtualFileSystem, RecordPlace, SQLiteStorage, VirtualFileSystem
from vfs import deadline as deadline_module
from vfs.kernel_store import BEHIND_CAPACITY, FLUSH_ROWS, BehindKind, KernelStore, KernelStoreUnavailable
from vfs.models.kernel_rows import KERNEL_FORMAT_VERSION
from vfs.results import ErrorKind
from vfs.storage.backends.database import seams

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Mapping, Sequence

    from vfs.kernel_store import Transaction

_DEADLINE = 30.0
"""The seconds a test waits for a drain that may never end, so that a hang fails the test and is not the run's."""


class Probe(NamedTuple):
    """A store that is ready, its probe table, a kind registered on it, and the calls of that kind's ``write``."""

    store: KernelStore
    table: Table
    kind: BehindKind
    seen: list[Written]


@pytest.fixture
async def probe(stores: Callable[..., KernelStore]) -> Probe:
    """A store on the test's place, with the probe table made and one kind, ``probe``, registered."""
    return await _probe(stores())


async def _probe(store: KernelStore, *, keyed: bool = False) -> Probe:
    table = await probe_table(store)
    seen: list[Written] = []
    kind = probe_kind(table, keyed=keyed, seen=seen)
    store.register_behind(kind)
    return Probe(store, table, kind, seen)


def _file_kernel(tmp_path: pathlib.Path) -> AsyncVirtualFileSystem:
    return AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")))


async def _the_task_ends() -> None:
    """Wait for the store's task, which a test held at a seam and has let go, to end."""
    await asyncio.gather(*store_tasks())


def _rows_with(counter: int | None, count: int, *, owner: str = "o") -> list[dict[str, object]]:
    """*count* probe rows whose counter is *counter*; a counter of ``None`` breaks the table's constraint."""
    return [{**row, "counter": counter} for row in probe_rows(count, owner=owner)]


# ---------------------------------------------------------------------------
# A failed flush, and the place that cannot be written
# ---------------------------------------------------------------------------


async def test_a_flush_behind_a_held_mount_writer_keeps_its_rows(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a flush that drops its rows, or loses them, when the mount's write holds the file's writer."""
    fs = _file_kernel(tmp_path)
    probe = await _probe(fs._kernel_store)
    store = probe.store
    assert (await fs.write(path="/a.txt", content="first")).success
    without_waiting(store)
    caplog.set_level(logging.INFO, logger="vfs.kernel_store")
    gate = Gate()
    with seams.installed("write:before-apply", gate):
        write = asyncio.ensure_future(fs.write(path="/b.txt", content="held"))
        await gate.reached.wait()
        store.put_behind(probe.kind, probe_rows(3), scope="s")
        with pytest.raises(KernelStoreUnavailable):
            await store.drain("s")
        waiting = store.waiting_behind(probe.kind, scope="s")
        gate.open()
        assert (await write).success
    store.put_behind(probe.kind, probe_rows(1, owner="later"), scope="s")
    await store.drain("s")
    assert (len(waiting), len(records(caplog, "WARNING")), await count_rows(store, probe.table)) == (3, 1, 4)
    await fs.close()


@pytest.mark.parametrize("rows", [3, FLUSH_ROWS + 2])
async def test_close_behind_a_held_writer_still_disposes_the_store(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture, rows: int
) -> None:
    """Guards a close whose last flush tries four times behind a held writer, or leaves its engine undisposed.

    With more rows than one flush takes, it also guards a close that flushes
    on after a flush failed.
    """
    fs = _file_kernel(tmp_path)
    connections = Connections(fs._kernel_store)
    probe = await _probe(fs._kernel_store)
    store = probe.store
    without_waiting(store)
    holder = HeldWriter(tmp_path / "knowledge.db")
    holder.hold()
    try:
        store.put_behind(probe.kind, probe_rows(rows))
        with pytest.raises(KernelStoreUnavailable):
            await store.drain()
        caplog.clear()
        caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
        sent = statements_of(store)
        await fs.close()
        warned = records(caplog, "WARNING")
        left = connections.open
    finally:
        holder.release()
    assert (begins(sent), len(warned), left, store.dropped) == (["BEGIN IMMEDIATE"], 1, 0, rows)
    assert f"{rows} records" in warned[0]
    assert files_in(tmp_path) == ["knowledge.db"]


async def test_a_flush_in_hand_at_close_starts_no_further_try(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a flush in hand at close that goes on to its four tries, which outlast the close's timeout."""
    fs = _file_kernel(tmp_path)
    probe = await _probe(fs._kernel_store)
    store = probe.store
    without_waiting(store)
    holder = HeldWriter(tmp_path / "knowledge.db")
    holder.hold()
    sent = statements_of(store)
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    gate = Gate()
    try:
        with seams.installed("kernel-store:before-try", gate):
            store.put_behind(probe.kind, probe_rows(3))
            await gate.reached.wait()
            closing = asyncio.ensure_future(fs.close())
            await turns_of_the_loop()
            gate.open()
            await closing
    finally:
        holder.release()
    warned = records(caplog, "WARNING")
    assert (begins(sent), len(warned), store.dropped) == (["BEGIN IMMEDIATE"] * 2, 1, 3)
    assert "3 records" in warned[0]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_close_with_no_budget_left_starts_no_flush(
    stores: Callable[..., KernelStore], caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a close that starts a flush it has no time for, or raises for rows that may be dropped."""
    store = stores()
    connections = Connections(store)
    probe = await _probe(store)
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    gate = Gate()
    with seams.installed("kernel-store:before-flush", gate):
        store.put_behind(probe.kind, probe_rows(3))
        await gate.reached.wait()
        sent = statements_of(store)
        await store.close(within=0)
        gate.open()
        await _the_task_ends()
    warned = records(caplog, "WARNING")
    assert (begins(sent), len(warned), connections.open, store.dropped) == ([], 1, 0, 3)
    assert "3 records" in warned[0]


@pytest.mark.parametrize("cut", ["budget spent", "cancelled"])
async def test_a_close_cut_short_starts_no_further_flush(tmp_path: pathlib.Path, cut: str) -> None:
    """Guards a close cut short whose task goes on flushing, on the new pool, after the engine is disposed."""
    fs = _file_kernel(tmp_path)
    connections = Connections(fs._kernel_store)
    probe = await _probe(fs._kernel_store)
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        store.put_behind(probe.kind, probe_rows(3))
        await gate.reached.wait()
        store.put_behind(probe.kind, probe_rows(2_000, owner="behind"))
        sent = statements_of(store)
        if cut == "budget spent":
            await store.close(within=0)
        else:
            closing = asyncio.ensure_future(store.close())
            await turns_of_the_loop()
            closing.cancel()
            with pytest.raises(asyncio.CancelledError):
                await closing
        dropped = store.dropped
        gate.open()
        await _the_task_ends()
    await fs.close()
    assert (begins(sent), connections.open, dropped) == ([], 0, 2_000)
    assert (file_rows(tmp_path / "knowledge.db", PROBE_TABLE), files_in(tmp_path)) == (3, ["knowledge.db"])


async def test_a_read_only_file_holds_its_rows_and_warns_once(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a store on a file it cannot write that drops its rows, warns at each try, or falls back to memory.

    The file is opened read-only through SQLite's own ``mode=ro``, so the
    test holds whoever runs it, the root user among them.
    """
    path = tmp_path / "knowledge.db"
    writable = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{path}", label=str(path)))
    await probe_table(writable)
    await writable.close()
    read_only = RecordPlace(url=f"sqlite+aiosqlite:///file:{path}?mode=ro&uri=true", label=str(path))
    store = KernelStore(read_only)
    probe = await _probe_on(store)
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    tries = Gate(times=0)
    with seams.installed("kernel-store:before-flush", tries):
        for index in range(3):
            store.put_behind(probe.kind, probe_rows(1, owner=f"o{index}"), scope="s")
            with pytest.raises(KernelStoreUnavailable):
                await store.drain("s")
    with pytest.raises(KernelStoreUnavailable):
        await store.commit(inserting(probe.table, probe_rows(1), store))
    waiting = store.waiting_behind(probe.kind, scope="s")
    warned = records(caplog, "WARNING")
    await store.close()
    assert (len(waiting), tries.entered, len(warned)) == (3, 3, 1)
    assert str(path) in warned[0]


async def _probe_on(store: KernelStore) -> Probe:
    """The probe kind on a store whose probe table another store made."""
    table = probe_table_shape(store)
    seen: list[Written] = []
    kind = probe_kind(table, seen=seen)
    store.register_behind(kind)
    return Probe(store, table, kind, seen)


@pytest.mark.postgres
async def test_a_role_that_may_not_write_keeps_its_rows_and_names_the_grant(caplog: pytest.LogCaptureFixture) -> None:
    """Guards a refused privilege that drops a flush as one that can never land, or tells no grant to give."""
    async with server_storage("VFS_TEST_POSTGRES_URL") as storage:
        place = storage.record_place
        assert place is not None and place.schema is not None
        owner = KernelStore(place)
        table = await probe_table(owner)
        role = f"vfs_role_{uuid4().hex[:12]}"
        await _run_as_owner(
            f"CREATE ROLE {role} LOGIN PASSWORD 'pw'", f"GRANT USAGE ON SCHEMA {place.schema} TO {role}"
        )
        url = make_url(os.environ["VFS_TEST_POSTGRES_URL"]).set(username=role, password="pw")
        store = KernelStore(RecordPlace(url=url, label=place.label, schema=place.schema))
        kind = probe_kind(table)
        store.register_behind(kind)
        caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
        try:
            store.put_behind(kind, probe_rows(3), scope="s")
            with pytest.raises(KernelStoreUnavailable):
                await store.drain("s")
            waiting = len(store.waiting_behind(kind, scope="s"))
            names = f"{place.schema}.vfs_kernel_meta, {place.schema}.{PROBE_TABLE}"
            await _run_as_owner(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {names} TO {role}")
            store.put_behind(kind, probe_rows(1, owner="later"), scope="s")
            await store.drain("s")
            written = await count_rows(owner, table)
        finally:
            await store.close()
            await owner.close()
            await _run_as_owner(f"DROP OWNED BY {role}", f"DROP ROLE {role}")
    warned = records(caplog, "WARNING")
    assert (waiting, len(warned), records(caplog, "ERROR"), written) == (3, 1, [], 4)
    assert "grant this role SELECT, INSERT, UPDATE and DELETE" in warned[0]


@pytest.mark.parametrize("place", [IN_A_FILE], indirect=True)
async def test_a_row_put_again_while_its_flush_fails_keeps_the_later_row(
    place: RecordPlace, stores: Callable[..., KernelStore]
) -> None:
    """Guards a failed flush whose row comes back beside a later row of its key: the buffer would hold the key twice."""
    probe = await _probe(stores(), keyed=True)
    store = probe.store
    without_waiting(store)
    key = ("o", "s", "n00000")
    holder = HeldWriter(sqlite_file_of(place))
    holder.hold()
    gate = Gate()
    try:
        with seams.installed("kernel-store:before-try", gate):
            store.put_behind(probe.kind, _rows_with(1, 1), scope="first")
            await gate.reached.wait()
            store.put_behind(probe.kind, _rows_with(2, 1), scope="later")
            gate.open()
            with pytest.raises(KernelStoreUnavailable):
                await store.drain()
        waiting = [row["counter"] for row in store.waiting_behind(probe.kind, keys=[key])]
        scopes = [len(store.waiting_behind(probe.kind, scope=scope)) for scope in ("first", "later")]
    finally:
        holder.release()
    await store.drain()
    assert (waiting, scopes, probe.seen[-1].rows) == ([2], [0, 1], _rows_with(2, 1))


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_task_cancelled_from_outside_keeps_its_flush(probe: Probe) -> None:
    """Guards a task that a loop's end cancels in a flush, and that loses its rows, or leaves no task to put to."""
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        store.put_behind(probe.kind, probe_rows(3), scope="s")
        await gate.reached.wait()
        (task,) = store_tasks()
        task.cancel()
        await turns_of_the_loop()
        gate.open()
        with pytest.raises(asyncio.CancelledError):
            await task
    waiting = len(store.waiting_behind(probe.kind, scope="s"))
    store.put_behind(probe.kind, probe_rows(1, owner="later"), scope="s")
    await store.drain("s")
    assert (waiting, await count_rows(store, probe.table)) == (3, 4)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_second_try_that_meets_a_passing_failure_holds_every_row(
    probe: Probe, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a second try a kind at a time whose passing failure drops the rows as rows that can never land."""
    store = probe.store
    calls: list[int] = []

    async def flaky(owner: KernelStore, transaction: Transaction, rows: Sequence[Mapping[str, object]]) -> None:
        calls.append(len(rows))
        if len(calls) == 1:
            raise RuntimeError("this kind's write is broken once")
        if len(calls) == 2:
            raise OperationalError("INSERT", None, Exception("the connection was lost"))
        await owner.insert_rows(transaction, probe.table, rows)

    kind = BehindKind(name="flaky", write=flaky)
    store.register_behind(kind)
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    store.put_behind(kind, probe_rows(3), scope="s")
    with pytest.raises(KernelStoreUnavailable):
        await store.drain("s")
    waiting = len(store.waiting_behind(kind, scope="s"))
    store.put_behind(kind, probe_rows(1, owner="later"), scope="s")
    await store.drain("s")
    told = (len(records(caplog, "WARNING")), records(caplog, "ERROR"))
    assert (waiting, calls, await count_rows(store, probe.table), store.dropped, told) == (3, [3, 3, 4], 4, 0, (1, []))


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_kind_that_can_never_land_drops_its_own_rows_alone(
    probe: Probe, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a row that can never land dropping the rows of a sound kind that rode its flush."""
    store = probe.store
    broken = probe_kind(probe.table, name="broken")
    store.register_behind(broken)
    caplog.set_level(logging.ERROR, logger="vfs.kernel_store")
    store.put_behind(broken, _rows_with(None, 3, owner="broken"), scope="broken")
    store.put_behind(probe.kind, probe_rows(3), scope="sound")
    await store.drain("sound")
    failed = records(caplog, "ERROR")
    assert (await count_rows(store, probe.table), store.dropped, len(failed)) == (3, 3, 1)
    assert "3 broken records" in failed[0]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_flush_that_can_never_land_drops_its_batch(probe: Probe, caplog: pytest.LogCaptureFixture) -> None:
    """Guards a batch that can never land and is tried again forever, blocking every row behind it."""
    store = probe.store
    caplog.set_level(logging.ERROR, logger="vfs.kernel_store")
    sent = statements_of(store)
    store.put_behind(probe.kind, _rows_with(None, 3), scope="s")
    with pytest.raises(KernelStoreUnavailable):
        await store.drain("s")
    tries = len(begins(sent))
    store.put_behind(probe.kind, probe_rows(2, owner="later"))
    await store.drain()
    assert (tries, len(records(caplog, "ERROR")), store.dropped) == (2, 1, 3)
    assert await count_rows(store, probe.table) == 2


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_kind_whose_write_raises_is_dropped_as_one_that_can_never_land(
    probe: Probe, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a kind whose own code raises, which no retry clears, held at the head of the buffer forever."""
    store = probe.store

    async def raising(_store: KernelStore, _transaction: Transaction, _rows: Sequence[Mapping[str, object]]) -> None:
        raise RuntimeError("this kind's write is broken")

    broken = BehindKind(name="raising", write=raising)
    store.register_behind(broken)
    caplog.set_level(logging.ERROR, logger="vfs.kernel_store")
    store.put_behind(broken, probe_rows(2, owner="broken"), scope="broken")
    store.put_behind(probe.kind, probe_rows(3), scope="sound")
    await store.drain("sound")
    failed = records(caplog, "ERROR")
    assert (await count_rows(store, probe.table), store.dropped, len(failed)) == (3, 2, 1)
    assert "this kind's write is broken" in failed[0]


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_a_store_of_another_format_drops_what_is_written_behind(
    place: RecordPlace, stores: Callable[..., KernelStore], caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a store of another format that is written behind, or whose rows are tried again a kind at a time."""
    other = stores()
    table = await probe_table(other)
    meta = other.tables.meta

    async def age(transaction: Transaction) -> None:
        await transaction.execute(update(meta).values(format_version=KERNEL_FORMAT_VERSION + 1))

    await other.commit(age)
    store = stores()
    kind = probe_kind(table)
    store.register_behind(kind)
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    store.put_behind(kind, probe_rows(3))
    with pytest.raises(KernelStoreUnavailable) as refused:
        await store.drain()
    store.put_behind(kind, probe_rows(2, owner="later"))
    with pytest.raises(KernelStoreUnavailable):
        await store.drain()
    assert (refused.value.error.kind, store.dropped) == (ErrorKind.schema_mismatch, 5)
    assert (len(records(caplog, "WARNING")), records(caplog, "ERROR"), await count_rows(other, table)) == (1, [], 0)


# ---------------------------------------------------------------------------
# put_behind and the task
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_put_behind_sends_nothing_before_it_returns(probe: Probe) -> None:
    """Guards a put that sends a statement, or waits for one, before it returns: a read would then wait."""
    store = probe.store
    sent = statements_of(store)
    gate = Gate()
    with seams.installed("kernel-store:before-flush", gate):
        store.put_behind(probe.kind, probe_rows(3))
        returned = len(sent)
        await gate.reached.wait()
        held = len(sent)
        gate.open()
        await store.drain()
    assert (returned, held, await count_rows(store, probe.table)) == (0, 0, 3)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_the_task_runs_in_a_context_of_its_own(probe: Probe) -> None:
    """Guards a task that copies its starter's context: it would carry an attempt's mark and a call's variables."""
    store = probe.store
    caller: contextvars.ContextVar[str] = contextvars.ContextVar("caller")
    observed: list[str | None] = []

    async def observing(_store: KernelStore, _transaction: Transaction, _rows: Sequence[Mapping[str, object]]) -> None:
        observed.append(caller.get(None))

    kind = BehindKind(name="observing", write=observing)
    store.register_behind(kind)
    caller.set("the putter")
    store.put_behind(kind, [{"row": 1}])
    await store.drain()
    assert observed == [None]
    assert [task.get_name() for task in store_tasks()] == ["vfs-kernel-store"]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
@pytest.mark.parametrize(("rows", "flushes"), [(300, 1), (3_000, 3)])
async def test_rows_put_in_one_turn_ride_one_flush(probe: Probe, rows: int, flushes: int) -> None:
    """Guards a writer that sends a transaction for each put, or waits for a count of rows or a timer."""
    store = probe.store
    sent = statements_of(store)
    for row in probe_rows(rows):
        store.put_behind(probe.kind, [row])
    await store.drain()
    assert (len(begins(sent)), len(probe.seen[0].rows)) == (flushes, min(rows, FLUSH_ROWS))
    assert await count_rows(store, probe.table) == rows


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_rows_with_one_key_become_one_row(stores: Callable[..., KernelStore]) -> None:
    """Guards a keyed kind that sends every row it was given, so one flush updates one row many times."""
    probe = await _probe(stores(), keyed=True)
    for counter in range(50):
        probe.store.put_behind(probe.kind, [{**probe_rows(1)[0], "counter": counter}])
    await probe.store.drain()
    assert [call.rows for call in probe.seen] == [[{**probe_rows(1)[0], "counter": 49}]]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_keyed_rows_reach_the_writer_sorted(stores: Callable[..., KernelStore]) -> None:
    """Guards a keyed kind handed its rows as they were put: two processes would lock its rows crosswise."""
    probe = await _probe(stores(), keyed=True)
    rows = probe_rows(40)
    random.Random(5).shuffle(rows)
    probe.store.put_behind(probe.kind, rows)
    await probe.store.drain()
    assert [row["name"] for row in probe.seen[0].rows] == [f"n{index:05d}" for index in range(40)]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_kinds_flush_in_the_order_they_were_registered(probe: Probe) -> None:
    """Guards a flush that writes kinds in the order their rows arrived, so a kind runs before one it needs."""
    store = probe.store
    later = probe_kind(probe.table, name="later", seen=probe.seen)
    store.register_behind(later)
    store.put_behind(later, probe_rows(2, owner="later"))
    store.put_behind(probe.kind, probe_rows(2))
    await store.drain()
    assert [call.kind for call in probe.seen] == ["probe", "later"]
    assert probe.seen[0].transaction is probe.seen[1].transaction


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_full_buffer_drops_its_oldest_and_counts_them(stores: Callable[..., KernelStore]) -> None:
    """Guards a bound that drops the newest rows, or none, while the store cannot be written."""
    probe = await _probe(stores(behind_capacity=8))
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-flush", gate):
        for row in probe_rows(12):
            store.put_behind(probe.kind, [row])
        await gate.reached.wait()
        gate.open()
        await store.drain()
    assert (store.dropped, [row["name"] for call in probe.seen for row in call.rows]) == (
        4,
        [f"n{index:05d}" for index in range(4, 12)],
    )


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_one_put_past_the_bound_keeps_its_last_rows(stores: Callable[..., KernelStore]) -> None:
    """Guards a put larger than the bound that keeps its first rows, or every row."""
    probe = await _probe(stores(behind_capacity=8))
    probe.store.put_behind(probe.kind, probe_rows(20))
    await probe.store.drain()
    assert (probe.store.dropped, probe.seen[0].rows[0]["name"]) == (12, "n00012")
    assert BEHIND_CAPACITY == 16_384


@pytest.mark.slow
@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_a_flush_stays_under_the_parameter_cap(stores: Callable[..., KernelStore]) -> None:
    """Guards a flush whose statement grows with its batch, past the engine's cap on binds."""
    store = stores()
    columns = [Column("id", Integer, primary_key=True), *(Column(f"c{index:02d}", String(16)) for index in range(14))]
    wide = Table("vfs_kernel_wide", MetaData(), *columns, schema=store.tables.meta.schema)

    async def make(transaction: Transaction) -> None:
        await (await transaction.connection()).run_sync(wide.metadata.create_all, checkfirst=True)

    await store.commit(make)
    calls: list[int] = []

    async def write(owner: KernelStore, transaction: Transaction, rows: Sequence[Mapping[str, object]]) -> None:
        calls.append(len(rows))
        await owner.upsert_rows(transaction, wide, rows, key=("id",), update=("c00",))

    kind = BehindKind(name="wide", write=write, key=("id",))
    store.register_behind(kind)
    sent = statements_of(store)
    store.put_behind(
        kind, [{"id": index, **{f"c{column:02d}": "v" for column in range(14)}} for index in range(10_000)]
    )
    await store.drain()
    inserts = [item for item in sent if item.sql.startswith("INSERT")]
    assert (len(calls), sum(calls), max(item.binds for item in inserts) <= store.parameter_budget) == (10, 10_000, True)


@pytest.mark.parametrize("place", [IN_A_FILE], indirect=True)
async def test_a_failed_flush_keeps_its_rows_and_the_next_put_sends_them(
    place: RecordPlace, probe: Probe, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a failed flush that drops its rows, warns at every try, or never says the store is written again."""
    store = probe.store
    without_waiting(store)
    caplog.set_level(logging.INFO, logger="vfs.kernel_store")
    holder = HeldWriter(sqlite_file_of(place))
    holder.hold()
    try:
        store.put_behind(probe.kind, probe_rows(3), scope="s")
        with pytest.raises(KernelStoreUnavailable) as failed:
            await store.drain()
        waiting = len(store.waiting_behind(probe.kind, scope="s"))
        held = await count_rows(store, probe.table)
    finally:
        holder.release()
    store.put_behind(probe.kind, probe_rows(1, owner="later"))
    await store.drain()
    told = (len(records(caplog, "WARNING")), len(records(caplog, "INFO")))
    assert (failed.value.error.retryable, waiting, held, await count_rows(store, probe.table), told) == (
        True,
        3,
        0,
        4,
        (1, 1),
    )


# ---------------------------------------------------------------------------
# drain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_drain_returns_at_once_when_its_scope_has_nothing_waiting(probe: Probe) -> None:
    """Guards a drain that sends a statement, or waits behind another scope's rows, when its own have landed."""
    store = probe.store
    sent = statements_of(store)
    gate = Gate()
    with seams.installed("kernel-store:before-flush", gate):
        store.put_behind(probe.kind, probe_rows(3), scope="other")
        await gate.reached.wait()
        await store.drain("mine")
        drained = len(sent)
        gate.open()
        await store.drain("other")
    assert drained == 0


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_drain_waits_for_its_scope_alone(probe: Probe) -> None:
    """Guards a drain that waits for every scope's backlog, where its own rows rode the first flush."""
    store = probe.store
    gate = Gate(skip=1)
    with seams.installed("kernel-store:before-flush", gate):
        store.put_behind(probe.kind, probe_rows(1, owner="mine"), scope="mine")
        store.put_behind(probe.kind, probe_rows(3_000), scope="other")
        await store.drain("mine")
        others = len(store.waiting_behind(probe.kind, scope="other"))
        gate.open()
        await store.drain()
    assert (others, await count_rows(store, probe.table)) == (3_000 - (FLUSH_ROWS - 1), 3_001)


@pytest.mark.parametrize("place", [IN_A_FILE], indirect=True)
async def test_drain_raises_when_its_flush_fails(place: RecordPlace, probe: Probe) -> None:
    """Guards a drain that returns as if its rows were written when the flush that carried them failed."""
    store = probe.store
    without_waiting(store)
    holder = HeldWriter(sqlite_file_of(place))
    holder.hold()
    try:
        store.put_behind(probe.kind, probe_rows(2), scope="s")
        with pytest.raises(KernelStoreUnavailable) as failed:
            await store.drain("s")
    finally:
        holder.release()
    await store.drain("s")
    assert (failed.value.error.kind, await count_rows(store, probe.table)) == (ErrorKind.unavailable, 2)


@pytest.mark.parametrize("place", [IN_A_FILE], indirect=True)
async def test_a_drain_behind_a_failed_flush_raises(place: RecordPlace, probe: Probe) -> None:
    """Guards a drain whose rows wait behind a failed flush, which then waits for a wake that never comes.

    The mutant it kills raises a held failure only to the drains with a row
    in the failed flush; the deadline only bounds the wait of that mutant.
    """
    store = probe.store
    without_waiting(store)
    holder = HeldWriter(sqlite_file_of(place))
    holder.hold()
    try:
        store.put_behind(probe.kind, probe_rows(FLUSH_ROWS + 10, scope="a"), scope="a")
        store.put_behind(probe.kind, probe_rows(3), scope="s")
        with pytest.raises(KernelStoreUnavailable) as failed:
            await asyncio.wait_for(store.drain("s"), timeout=_DEADLINE)
        waiting = len(store.waiting_behind(probe.kind, scope="s"))
    finally:
        holder.release()
    await store.drain("s")
    stored = await count_rows(store, probe.table)
    assert (failed.value.error.kind, waiting, stored) == (ErrorKind.unavailable, 3, FLUSH_ROWS + 13)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_cancelled_drain_loses_no_row(probe: Probe) -> None:
    """Guards a drain whose cancellation reaches the flush it waits for, and so loses that flush's rows."""
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        store.put_behind(probe.kind, probe_rows(3), scope="s")
        waiter = asyncio.ensure_future(store.drain("s"))
        await gate.reached.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        gate.open()
        await store.drain("s")
    assert await count_rows(store, probe.table) == 3


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_drain_whose_rows_are_dropped_returns(stores: Callable[..., KernelStore]) -> None:
    """Guards a drain that waits for ever for rows the bound has dropped."""
    probe = await _probe(stores(behind_capacity=2))
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-flush", gate):
        store.put_behind(probe.kind, probe_rows(1, owner="first"), scope="first")
        await gate.reached.wait()
        waiter = asyncio.ensure_future(store.drain("first"))
        await asyncio.sleep(0)
        store.put_behind(probe.kind, probe_rows(2), scope="later")
        await waiter
        gate.open()
        await store.drain()
    assert (store.dropped, await count_rows(store, probe.table)) == (1, 2)


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_put_after_close_is_dropped_and_raises_nothing(probe: Probe) -> None:
    """Guards a put after close that raises, starts a task, or keeps rows nothing will write."""
    store = probe.store
    await store.close()
    store.put_behind(probe.kind, probe_rows(3), scope="s")
    assert (store.dropped, store.waiting_behind(probe.kind, scope="s"), store_tasks()) == (3, [], [])
    await store.drain("s")


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_close_flushes_what_the_buffer_holds(place: RecordPlace, probe: Probe) -> None:
    """Guards a close that drops the rows a short script put last, so the next process never finds them."""
    store = probe.store
    store.put_behind(probe.kind, probe_rows(3))
    await store.close()
    written = [len(call.rows) for call in probe.seen]
    if place.durable:
        assert file_rows(sqlite_file_of(place), PROBE_TABLE) == 3
    assert (written, store.dropped, store_tasks()) == ([3], 0, [])


class _SteppedMonotonic:
    """The monotonic clock of ``vfs.deadline``, which a test steps and which never moves by itself."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("place", [IN_A_FILE], indirect=True)
async def test_a_close_whose_budget_is_spent_between_two_flushes_starts_no_more(
    place: RecordPlace,
    stores: Callable[..., KernelStore],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guards a close that reads its budget once: a slow first flush would be followed by more than it has time for.

    The budget is a ``Deadline``, so the deadline module's clock is
    stepped by the kind's own ``write`` and no clock is read. The store
    was never used, so its first touch is made at close, with one try.
    """
    table = await probe_table(stores())
    clock = _SteppedMonotonic()
    monkeypatch.setattr(deadline_module, "monotonic", clock)
    store = stores()

    async def slow(owner: KernelStore, transaction: Transaction, rows: Sequence[Mapping[str, object]]) -> None:
        clock.now += 60
        await owner.insert_rows(transaction, table, rows)

    kind = BehindKind(name="slow", write=slow)
    store.register_behind(kind)
    sent = statements_of(store)
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    store.put_behind(kind, probe_rows(FLUSH_ROWS + 5))
    await store.close(within=10)
    warned = records(caplog, "WARNING")
    assert (len(begins(sent)), file_rows(sqlite_file_of(place), PROBE_TABLE), store.dropped) == (2, FLUSH_ROWS, 5)
    assert (len(warned), "5 records" in warned[0]) == (1, True)


@pytest.mark.parametrize("place", [IN_A_FILE], indirect=True)
async def test_a_flush_at_close_on_sqlite_waits_at_most_half_of_what_is_left(
    place: RecordPlace, probe: Probe, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards a flush at close that waits for the file's writer its whole ``busy_timeout`` and not half its budget.

    The connection keeps the profile's own ``busy_timeout``, and the deadline
    module's clock stands still, so a close of 4 seconds has a budget of 3
    and its one ``BEGIN IMMEDIATE`` waits at most 1,500 ms. The mutants it
    kills lower the wait after the ``BEGIN`` is sent, or by all that is left.
    """
    store = probe.store
    monkeypatch.setattr(deadline_module, "monotonic", _SteppedMonotonic())
    waits: list[tuple[str, int]] = []

    @event.listens_for(store.engine.sync_engine, "before_cursor_execute")
    def read_the_wait(conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.startswith("BEGIN"):
            cursor = conn.connection.dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout")
            waits.append((statement, cursor.fetchone()[0]))
            cursor.close()

    store.put_behind(probe.kind, probe_rows(3))
    await store.close(within=4)
    assert (waits, file_rows(sqlite_file_of(place), PROBE_TABLE)) == ([("BEGIN IMMEDIATE", 1_500)], 3)


@pytest.mark.slow
async def test_a_process_that_dies_loses_at_most_its_buffer(tmp_path: pathlib.Path) -> None:
    """Guards rows written behind that a store writes before they were put, or a buffer that outlives its process."""
    path = tmp_path / "knowledge.db"
    done = subprocess.run([sys.executable, "-c", _CHILD, str(path)], cwd=REPO, timeout=120, check=False)
    assert (done.returncode, file_rows(path, PROBE_TABLE)) == (0, 5)


# ---------------------------------------------------------------------------
# A loop that changes
# ---------------------------------------------------------------------------


async def test_a_put_on_another_loop_moves_the_task_there(tmp_path: pathlib.Path) -> None:
    """Guards a task left on the loop that first put rows, which no longer runs once the facade's loop takes over."""
    fs = _file_kernel(tmp_path)
    probe = await _probe(fs._kernel_store)
    store = probe.store
    store.put_behind(probe.kind, probe_rows(1))
    await store.drain()
    first = store_tasks()

    async def on_the_facade() -> bool:
        store.put_behind(probe.kind, probe_rows(2, owner="facade"))
        await store.drain()
        return [task.get_loop() for task in store_tasks()] == [asyncio.get_running_loop()]

    facade = VirtualFileSystem.wrap(fs)
    moved = asyncio.run_coroutine_threadsafe(on_the_facade(), facade._loop).result(timeout=60)
    await asyncio.gather(*first)
    facade.close()
    assert (len(first), moved, file_rows(tmp_path / "knowledge.db", PROBE_TABLE)) == (1, True, 3)


# ---------------------------------------------------------------------------
# What waits, and withdrawing it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_waiting_behind_returns_what_is_buffered_and_what_is_in_flight(probe: Probe) -> None:
    """Guards a row that reads as gone while its flush is in flight, so a change would read the store and miss it."""
    store = probe.store
    before_flush, before_commit = Gate(), Gate()
    with (
        seams.installed("kernel-store:before-flush", before_flush),
        seams.installed("kernel-store:before-commit", before_commit),
    ):
        store.put_behind(probe.kind, probe_rows(3), scope="s")
        await before_flush.reached.wait()
        sent = statements_of(store)
        buffered = len(store.waiting_behind(probe.kind, scope="s"))
        asked = len(sent)
        before_flush.open()
        await before_commit.reached.wait()
        sent.clear()
        in_flight = len(store.waiting_behind(probe.kind, scope="s"))
        asked += len(sent)
        before_commit.open()
        await store.drain("s")
    assert (buffered, in_flight, asked, store.waiting_behind(probe.kind, scope="s")) == (3, 3, 0, [])


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_discard_behind_withdraws_by_scope_and_by_key(stores: Callable[..., KernelStore]) -> None:
    """Guards a discard that withdraws another scope's rows, or none, or misses a row named by its key."""
    probe = await _probe(stores(), keyed=True)
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-flush", gate):
        store.put_behind(probe.kind, probe_rows(3, owner="a"), scope="a")
        store.put_behind(probe.kind, probe_rows(3, owner="b"), scope="b")
        await gate.reached.wait()
        by_scope = store.discard_behind(probe.kind, scope="a")
        by_key = store.discard_behind(probe.kind, keys=[("b", "s", "n00000"), ("b", "s", "n00002")])
        both = store.discard_behind(probe.kind, scope="a", keys=[("b", "s", "n00001")])
        gate.open()
        await store.drain()
    assert (by_scope, by_key, both, await count_rows(store, probe.table)) == (3, 2, 0, 1)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_row_in_flight_is_not_withdrawn(probe: Probe) -> None:
    """Guards a discard that takes a row from a flush in flight: the store would say it is gone and then write it."""
    store = probe.store
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        store.put_behind(probe.kind, probe_rows(1), scope="s")
        await gate.reached.wait()
        withdrawn = store.discard_behind(probe.kind, scope="s")
        gate.open()
        await store.drain("s")
    assert (withdrawn, await count_rows(store, probe.table)) == (0, 1)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_waiting_and_discard_with_no_scope_and_no_key_are_refused(probe: Probe) -> None:
    """Guards a call with neither a scope nor keys that reads or withdraws every row of a kind."""
    store = probe.store
    with pytest.raises(ValueError, match="scope"):
        store.waiting_behind(probe.kind)
    with pytest.raises(ValueError, match="scope"):
        store.discard_behind(probe.kind)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_kind_is_registered_once_and_used_only_when_registered(probe: Probe) -> None:
    """Guards two kinds of one name, a row put for a kind no kernel registered, and a key of a kind with none."""
    store = probe.store
    stranger = probe_kind(probe.table, name="stranger")
    with pytest.raises(ValueError, match="already"):
        store.register_behind(probe_kind(probe.table))
    with pytest.raises(ValueError, match="registered"):
        store.put_behind(stranger, probe_rows(1))
    with pytest.raises(ValueError, match="registered"):
        store.waiting_behind(stranger, scope="s")
    with pytest.raises(ValueError, match="key"):
        store.discard_behind(probe.kind, keys=[("o", "s", "n00000")])


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_deferred_task_runs_once_after_its_rows(probe: Probe) -> None:
    """Guards a deferred task run once for each request, or before the rows it follows, or in a transaction apart."""
    store = probe.store
    runs: list[Written] = []

    async def task(_store: KernelStore, transaction: Transaction, rows: Sequence[Mapping[str, object]]) -> None:
        runs.append(Written("task", transaction, [dict(row) for row in rows]))
        probe.seen.append(runs[-1])

    deferred = BehindKind(name="task", write=task, key=("target",))
    store.register_behind(deferred)
    for _ in range(50):
        store.put_behind(deferred, [{"target": "the index"}])
    store.put_behind(probe.kind, probe_rows(3))
    await store.drain()
    assert ([call.kind for call in probe.seen], [len(run.rows) for run in runs]) == (["probe", "task"], [1])
    assert probe.seen[0].transaction is probe.seen[1].transaction


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_as_owner(*statements: str) -> None:
    """Run *statements* on the Postgres leg as the role the suite connects with."""
    engine = create_async_engine(os.environ["VFS_TEST_POSTGRES_URL"], isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


# What a child process runs: it commits 5 rows, puts 7 behind, and leaves through os._exit before they flush.
_CHILD = """
import asyncio, os, sys
from vfs.kernel_store import KernelStore
from vfs import SQLiteStorage
from vfs.storage.backends.database import seams
from tests.support.kernel_store import inserting, probe_kind, probe_rows, probe_table


async def leave():
    os._exit(0)


async def main(path):
    store = KernelStore(SQLiteStorage(path=path).record_place)
    table = await probe_table(store)
    await store.commit(inserting(table, probe_rows(5), store))
    kind = probe_kind(table)
    store.register_behind(kind)
    seams.install("kernel-store:before-flush", leave)
    store.put_behind(kind, probe_rows(7, owner="behind"))
    await store.drain()
    sys.exit(3)


asyncio.run(main(sys.argv[1]))
"""
