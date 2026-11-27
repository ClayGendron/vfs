"""The kernel builds one store of its own, keeps it private, and closes it with its storages.

A store is built in the kernel's constructor from the place the root
storage names, with no I/O. ``close()`` closes it beside the storages,
within the same ``close_timeout``, and waits for its transactions in
flight. Every count is of connections, rows, files, log records, closes
or errors, and none reads a clock.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event
from sqlalchemy.pool import Pool

from tests.support.base_doubles import BadCloseStorage, RecorderStorage, SpyCloseStorage
from tests.support.cancelled_callers import held_round_trips, starts_with, turns_of_the_loop
from tests.support.kernel_store import (
    PROBE_TABLE,
    Connections,
    Gate,
    HeldWriter,
    begins,
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
from vfs import AsyncVirtualFileSystem, SQLiteStorage
from vfs.kernel_store import KernelStore, KernelStoreUnavailable, Transaction
from vfs.session import AsyncSession
from vfs.storage.backends.database import seams
from vfs.sync import Session

if TYPE_CHECKING:
    import pathlib


def _file_kernel(tmp_path: pathlib.Path, **options: Any) -> AsyncVirtualFileSystem:
    """A file system whose root is a SQLite file, ``knowledge.db``, under *tmp_path*."""
    return AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")), **options)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


async def test_the_kernel_builds_its_store_with_no_io(tmp_path: pathlib.Path) -> None:
    """Guards a store that connects, or makes a file, when the file system is made."""
    opened: list[object] = []

    def connected(*made: object) -> None:
        opened.append(made)

    event.listen(Pool, "connect", connected)
    try:
        kernels = [_file_kernel(tmp_path), AsyncVirtualFileSystem()]
    finally:
        event.remove(Pool, "connect", connected)
    assert (len(opened), files_in(tmp_path)) == (0, [])
    assert [kernel._kernel_store.durable for kernel in kernels] == [True, False]
    for kernel in kernels:
        await kernel.close()


async def test_an_in_memory_root_keeps_records_on_a_connection_of_their_own() -> None:
    """Guards a store in memory that rides the mount's one connection, and so waits for its turn or costs it."""
    fs = AsyncVirtualFileSystem()
    storage = fs.mounts()[0].storage
    mount_connections: list[object] = []
    event.listen(storage.engine.sync_engine, "connect", lambda made, _record: mount_connections.append(made))  # ty: ignore[unresolved-attribute]
    store = fs._kernel_store
    connections = Connections(store)
    table = await probe_table(store)
    assert (await fs.write(path="/a.txt", content="first")).success
    gate = Gate()
    with seams.installed("write:before-apply", gate):
        write = asyncio.ensure_future(fs.write(path="/b.txt", content="held"))
        await gate.reached.wait()
        await store.commit(inserting(table, probe_rows(1), store))
        landed = write.done()
        gate.open()
        assert (await write).success
    assert (landed, len(connections.opened), await count_rows(store, table)) == (False, 1, 1)
    assert [made for made in connections.opened if made in mount_connections] == []
    await fs.close()


async def test_a_root_that_names_no_place_keeps_records_in_memory() -> None:
    """Guards a root storage with no ``record_place`` that is refused, or whose records are said to last."""
    fs = AsyncVirtualFileSystem(storage=RecorderStorage())
    store = fs._kernel_store
    table = await probe_table(store)
    await store.commit(inserting(table, probe_rows(2), store))
    assert (store.durable, await count_rows(store, table)) == (False, 2)
    await fs.close()


@pytest.mark.parametrize("mounted", ["before the first record", "after the first record"])
async def test_records_in_memory_beside_a_database_mount_warn_once(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture, mounted: str
) -> None:
    """Guards a warning that is never given, given at every record, or given before a database is mounted."""
    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    fs = AsyncVirtualFileSystem()
    store = fs._kernel_store
    table = await probe_table(store)
    database = SQLiteStorage(path=str(tmp_path / "data.db"))
    if mounted == "before the first record":
        await fs.add_mount(database, "/data")
    warned: list[int] = []
    for owner in ("first", "second"):
        caplog.clear()
        await store.commit(inserting(table, probe_rows(1, owner=owner), store))
        warned.append(len(records(caplog, "WARNING")))
        if mounted == "after the first record" and owner == "first":
            await fs.add_mount(database, "/data")
    await fs.close()
    assert warned == ([1, 0] if mounted == "before the first record" else [0, 1])


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


async def test_close_closes_the_store_within_the_close_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards a close that leaves the store open, closes it twice, or gives it no budget."""
    given: list[float | None] = []
    close = KernelStore.close

    async def counted(self: KernelStore, *, within: float | None = None) -> None:
        given.append(within)
        await close(self, within=within)

    monkeypatch.setattr(KernelStore, "close", counted)
    fs = AsyncVirtualFileSystem(close_timeout=7.0)
    await fs.close()
    assert given == [7.0]


async def test_a_cancelled_close_keeps_the_store_for_a_second_close(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards a cancelled close that drops the store with its engine open, or that a second close cannot finish."""
    entered: list[float | None] = []
    close = KernelStore.close

    async def counted(self: KernelStore, *, within: float | None = None) -> None:
        entered.append(within)
        await close(self, within=within)

    monkeypatch.setattr(KernelStore, "close", counted)
    fs = _file_kernel(tmp_path)
    store = fs._kernel_store
    connections = Connections(store)
    table = await probe_table(store)
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        commit = asyncio.ensure_future(store.commit(inserting(table, probe_rows(1), store)))
        await gate.reached.wait()
        first = asyncio.ensure_future(fs.close())
        await turns_of_the_loop()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.ensure_future(fs.close())
        await turns_of_the_loop()
        held = second.done()
        gate.open()
        await commit
        await second
    assert (len(entered), held, connections.open) == (2, False, 0)
    assert (file_rows(tmp_path / "knowledge.db", PROBE_TABLE), files_in(tmp_path)) == (1, ["knowledge.db"])


@pytest.mark.parametrize("storage_fails", [False, True])
async def test_a_store_that_fails_to_close_joins_the_storages_errors(storage_fails: bool) -> None:
    """Guards a store whose failure to close is swallowed, or stops the storages from closing."""
    root = BadCloseStorage() if storage_fails else SpyCloseStorage()
    fs = AsyncVirtualFileSystem(storage=root)

    async def broken(*, within: float | None = None) -> None:
        raise RuntimeError("the store would not close")

    fs._kernel_store.close = broken  # ty: ignore[invalid-assignment]
    raised: list[BaseException] = []
    try:
        await fs.close()
    except BaseException as error:
        raised.append(error)
    errors = list(raised[0].exceptions) if isinstance(raised[0], BaseExceptionGroup) else raised
    assert (len(errors), root.close_count) == (2 if storage_fails else 1, 1)
    assert "the store would not close" in [str(error) for error in errors]


async def test_close_waits_for_a_record_in_flight(tmp_path: pathlib.Path) -> None:
    """Guards a close that disposes under a record in flight: the record is lost and the side files stay."""
    fs = _file_kernel(tmp_path)
    store = fs._kernel_store
    connections = Connections(store)
    table = await probe_table(store)
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        record = asyncio.ensure_future(store.record_after(inserting(table, probe_rows(1), store)))
        await gate.reached.wait()
        closing = asyncio.ensure_future(fs.close())
        await turns_of_the_loop()
        waited = not closing.done()
        gate.open()
        assert await record is None
        await closing
    assert (waited, connections.open) == (True, 0)
    assert (file_rows(tmp_path / "knowledge.db", PROBE_TABLE), files_in(tmp_path)) == (1, ["knowledge.db"])


async def test_a_close_cut_short_leaves_the_transaction_in_flight_to_close_its_connection(
    tmp_path: pathlib.Path,
) -> None:
    """Guards a transaction a close left running that returns its connection to a pool nobody disposes."""
    fs = _file_kernel(tmp_path)
    store = fs._kernel_store
    connections = Connections(store)
    table = await probe_table(store)
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        commit = asyncio.ensure_future(store.commit(inserting(table, probe_rows(1), store)))
        await gate.reached.wait()
        await store.close(within=0)
        left = connections.open
        gate.open()
        await commit
    await fs.close()
    assert (left, connections.open) == (1, 0)
    assert (file_rows(tmp_path / "knowledge.db", PROBE_TABLE), files_in(tmp_path)) == (1, ["knowledge.db"])


async def test_a_commit_in_hand_at_close_starts_no_further_try(tmp_path: pathlib.Path) -> None:
    """Guards a close that lets a failing commit try four times, which outlasts the close's timeout."""
    fs = _file_kernel(tmp_path)
    store = fs._kernel_store
    table = await probe_table(store)
    without_waiting(store)
    holder = HeldWriter(tmp_path / "knowledge.db")
    holder.hold()
    sent = statements_of(store)
    gate = Gate()
    try:
        with seams.installed("kernel-store:before-try", gate):
            commit = asyncio.ensure_future(store.commit(inserting(table, probe_rows(1), store)))
            await gate.reached.wait()
            closing = asyncio.ensure_future(fs.close())
            await turns_of_the_loop()
            gate.open()
            with pytest.raises(KernelStoreUnavailable):
                await commit
            await closing
    finally:
        holder.release()
    assert begins(sent) == ["BEGIN IMMEDIATE"]


@pytest.mark.parametrize("close", ["waits for it", "is cut short"])
async def test_a_first_touch_in_hand_at_close_starts_no_further_try(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, close: str
) -> None:
    """Guards a first touch that tries again after a close, on a pool nothing disposes, and leaves the side files."""
    fs = _file_kernel(tmp_path)
    assert (await fs.write(path="/a.txt", content="kept")).success
    await fs.mounts()[0].storage._host.settle_statistics()  # ty: ignore[unresolved-attribute]
    store = fs._kernel_store
    without_waiting(store)
    connections = Connections(store)
    sent = statements_of(store)
    round_trip = held_round_trips(monkeypatch)
    round_trip.hold(starts_with("execute BEGIN IMMEDIATE"))
    holder = HeldWriter(tmp_path / "knowledge.db")
    holder.hold()

    async def nothing(_transaction: Transaction) -> None:
        return None

    try:
        commit = asyncio.ensure_future(store.commit(nothing))
        await round_trip.reached.wait()
        if close == "is cut short":
            await store.close(within=0)
            round_trip.let_go()
            with pytest.raises(KernelStoreUnavailable):
                await commit
            left = connections.open
            await fs.close()
        else:
            closing = asyncio.ensure_future(fs.close())
            await turns_of_the_loop()
            round_trip.let_go()
            with pytest.raises(KernelStoreUnavailable):
                await commit
            await closing
            left = connections.open
    finally:
        holder.release()
    assert (begins(sent), left, connections.open) == (["BEGIN IMMEDIATE"], 0, 0)
    assert files_in(tmp_path) == ["knowledge.db"]


async def test_a_close_between_first_touchs_two_checkouts_leaves_no_connection(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards a try that disposes only the pool it began on, when a close replaced the pool in between."""
    first = _file_kernel(tmp_path)
    assert (await first.write(path="/a.txt", content="kept")).success
    await first.close()
    fs = _file_kernel(tmp_path)
    store = fs._kernel_store
    core = store._engine_core()
    connections = Connections(store)
    reached, go = asyncio.Event(), asyncio.Event()
    settings = core.apply_file_settings

    async def held() -> None:
        await settings()
        reached.set()
        await go.wait()

    async def nothing(_transaction: Transaction) -> None:
        return None

    monkeypatch.setattr(core, "apply_file_settings", held)
    commit = asyncio.ensure_future(store.commit(nothing))
    await reached.wait()
    await store.close(within=0)
    go.set()
    with pytest.raises(KernelStoreUnavailable):
        await commit
    await turns_of_the_loop()
    left = connections.open
    await fs.close()
    assert (left, connections.open) == (0, 0)
    assert files_in(tmp_path) == ["knowledge.db"]


# ---------------------------------------------------------------------------
# Out of every verb's reach
# ---------------------------------------------------------------------------


async def test_no_verb_shows_a_kernel_table(tmp_path: pathlib.Path) -> None:
    """Guards a kernel table that a listing, a glob or the ``/.vfs`` view reads as entries of the mount."""
    fs = _file_kernel(tmp_path)
    for path in ("/a.txt", "/docs/b.md"):
        assert (await fs.write(path=path, content="kept", parents=True)).success

    async def shown() -> list[tuple[str, ...]]:
        results = [await fs.tree("/"), await fs.glob("**"), await fs.ls("/.vfs")]
        return [tuple(str(path) for path in result.paths) for result in results]

    before = await shown()
    store = fs._kernel_store
    table = await probe_table(store)
    await store.commit(inserting(table, probe_rows(3), store))
    assert (await shown(), await count_rows(store, table)) == (before, 3)
    assert [len(paths) > 0 for paths in before[:2]] == [True, True]
    await fs.close()


@pytest.mark.parametrize("face", [AsyncSession, Session])
def test_a_session_cannot_reach_the_kernel_store(face: type) -> None:
    """Guards a session member that is, or returns, the kernel's store, which would go around every rights rule."""
    public = sorted(name for name in dir(face) if not name.startswith("_"))
    for name in public:
        member = inspect.getattr_static(face, name)
        assert not isinstance(member, KernelStore), name
        returns = inspect.signature(member.fget if isinstance(member, property) else member).return_annotation
        assert "KernelStore" not in str(returns), name
    assert public
