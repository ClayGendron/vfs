"""The sweep: expired records leave only when ``sweep`` is called, in bounded chunks, dependents before parents.

Each test runs on a SQLite file and on a store in memory unless it names
a place, and a test marked for both engines runs on a SQLite file and on
the Postgres leg behind ``VFS_TEST_POSTGRES_URL``. Time moves only when a
test steps the store's clock. Every count is of statements the store's
engine sent, rows read back, or calls of a sweeper, and none reads a clock.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import sqlite3
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table

from tests.support.kernel_store import (
    BOTH_ENGINES,
    PROBE_TABLE,
    SQLITE_PLACES,
    START,
    Gate,
    HeldWriter,
    SteppedClock,
    count_rows,
    file_rows,
    inserting,
    probe_kind,
    probe_rows,
    probe_table,
    probe_table_shape,
    records,
    statements_of,
    without_waiting,
)
from vfs import AsyncVirtualFileSystem, RecordPlace, SQLiteStorage
from vfs.authority import Authority, Principal
from vfs.kernel_store import SWEEP_CHUNK, KernelStore, KernelStoreUnavailable, expiry_sweeper
from vfs.results import Severity
from vfs.storage.backends.database import seams

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable
    from datetime import datetime

    from vfs.kernel_store import Sweeper, Transaction

# The day the expired rows of a test expire, and a clock a day past it.
EXPIRED = START
LATER = START + timedelta(days=1)


class Spy:
    """A sweeper that wraps another, and keeps what each call removed."""

    def __init__(self, sweeper: Sweeper) -> None:
        self.removed: list[int] = []
        self._sweeper = sweeper

    async def __call__(self, store: KernelStore, transaction: Transaction, now: datetime, limit: int) -> int:
        removed = await self._sweeper(store, transaction, now, limit)
        self.removed.append(removed)
        return removed


async def _expiring(store: KernelStore, *, expired: int, live: int = 0, none: int = 0) -> Table:
    """The probe table, with *expired* rows past their expiry, *live* rows that are not, and *none* with none."""
    table = await probe_table(store)
    for owner, count, expires_at in (
        ("old", expired, EXPIRED),
        ("live", live, LATER + timedelta(days=9)),
        ("none", none, None),
    ):
        if count:
            await store.commit(inserting(table, _named(owner, count, expires_at), store))
    return table


def _named(owner: str, count: int, expires_at: datetime | None) -> list[dict[str, object]]:
    """*count* probe rows of *owner*, whose names carry the owner: the sweepers here key on the name alone."""
    rows = probe_rows(count, owner=owner, expires_at=expires_at)
    return [{**row, "name": f"{owner}-{row['name']}"} for row in rows]


def _probe_sweeper(table: Table) -> Sweeper:
    return expiry_sweeper(table, key=table.c.name, expires=table.c.expires_at)


def _later_store(stores: Callable[..., KernelStore]) -> KernelStore:
    return stores(clock=SteppedClock(LATER))


def _deletes(sent: list[Any]) -> list[Any]:
    return [item for item in sent if item.sql.startswith("DELETE")]


# ---------------------------------------------------------------------------
# A pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_record_past_its_expiry_is_still_there_until_a_sweep(stores: Callable[..., KernelStore]) -> None:
    """Guards a store that removes an expired record by itself, before anyone asked for a sweep."""
    clock = SteppedClock(EXPIRED - timedelta(days=1))
    store = stores(clock=clock)
    table = await _expiring(store, expired=3)
    store.register_sweeper("probe", _probe_sweeper(table))
    clock.step(2 * 86_400)
    kept = await count_rows(store, table)
    assert (kept, await store.sweep(), await count_rows(store, table)) == (3, 3, 0)


@pytest.mark.slow
@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_pass_removes_expired_rows_in_chunks_of_five_thousand(stores: Callable[..., KernelStore]) -> None:
    """Guards a pass that removes everything in one statement, or more than its chunk in one transaction."""
    store = _later_store(stores)
    table = await _expiring(store, expired=12_000, live=100)
    spy = Spy(_probe_sweeper(table))
    store.register_sweeper("probe", spy)
    sent = statements_of(store)
    removed = await store.sweep()
    assert (removed, len(_deletes(sent)), spy.removed) == (12_000, 4, [5_000, 5_000, 2_000, 0])
    assert (await count_rows(store, table), SWEEP_CHUNK) == (100, 5_000)


@pytest.mark.slow
@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_pass_goes_on_until_nothing_expired_is_left(stores: Callable[..., KernelStore]) -> None:
    """Guards a pass that stops at a cap of chunks and leaves expired rows for a later pass."""
    store = _later_store(stores)
    table = await _expiring(store, expired=60_000)
    spy = Spy(_probe_sweeper(table))
    store.register_sweeper("probe", spy)
    sent = statements_of(store)
    assert await store.sweep() == 60_000
    assert (len(_deletes(sent)), spy.removed) == (13, [5_000] * 12 + [0])


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_nothing_is_swept_until_sweep_is_called(stores: Callable[..., KernelStore]) -> None:
    """Guards a store that sweeps after a count of its writes, a count of flushes, or at close."""
    store = _later_store(stores)
    table = await _expiring(store, expired=3)
    spy = Spy(_probe_sweeper(table))
    store.register_sweeper("probe", spy)
    kind = probe_kind(table)
    store.register_behind(kind)
    for index in range(2_000):
        await store.commit(inserting(table, probe_rows(1, owner=f"c{index}"), store))
    for index in range(20):
        store.put_behind(kind, probe_rows(1, owner=f"f{index}"))
        await store.drain()
    left = await count_rows(store, table)
    await store.close()
    assert (spy.removed, left) == ([], 2_023)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_cancelled_pass_has_removed_whole_chunks(stores: Callable[..., KernelStore]) -> None:
    """Guards a pass whose cancellation lands a part of a chunk, or undoes a chunk already committed."""
    store = _later_store(stores)
    table = await _expiring(store, expired=12_000)
    store.register_sweeper("probe", _probe_sweeper(table))
    gate = Gate(skip=1)
    with seams.installed("kernel-store:before-commit", gate):
        sweeping = asyncio.ensure_future(store.sweep())
        await gate.reached.wait()
        sweeping.cancel()
        gate.open()
        with pytest.raises(asyncio.CancelledError):
            await sweeping
    assert await count_rows(store, table) == 7_000


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_two_passes_at_once_remove_each_row_once(stores: Callable[..., KernelStore]) -> None:
    """Guards two processes' passes that remove one row twice, count it twice, or deadlock."""
    first, second = _later_store(stores), _later_store(stores)
    table = await _expiring(first, expired=2_000)
    for store in (first, second):
        store.register_sweeper("probe", _probe_sweeper(table))
    removed = await asyncio.gather(first.sweep(), second.sweep())
    assert (sum(removed), await count_rows(first, table)) == (2_000, 0)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
@pytest.mark.parametrize("flush", ["lands", "fails"])
async def test_a_flush_runs_between_two_chunks(stores: Callable[..., KernelStore], flush: str) -> None:
    """Guards a pass that keeps the store's own flush waiting behind every chunk of a pass."""
    store = _later_store(stores)
    table = await _expiring(store, expired=12_000)
    store.register_sweeper("probe", _probe_sweeper(table))
    kind = probe_kind(table)
    store.register_behind(kind)
    sent = statements_of(store)
    gate = Gate()
    with seams.installed("kernel-store:before-commit", gate):
        sweeping = asyncio.ensure_future(store.sweep())
        await gate.reached.wait()
        counter = 1 if flush == "lands" else None
        store.put_behind(kind, [{**row, "counter": counter} for row in probe_rows(3, owner="behind")])
        gate.open()
        removed = await sweeping
    order = [item.sql.split()[0] for item in sent if item.sql.startswith(("INSERT", "DELETE"))]
    assert (removed, [verb for verb, _ in itertools.groupby(order)][:3]) == (12_000, ["DELETE", "INSERT", "DELETE"])


async def test_a_root_that_masks_sweep_runs_no_pass(tmp_path: pathlib.Path) -> None:
    """Guards a masked sweep that still reclaims records, and a file system of its own that cannot reclaim them."""
    path = str(tmp_path / "knowledge.db")
    masked = AsyncVirtualFileSystem(storage=SQLiteStorage(path=path), deny_ops={"sweep"})
    store = masked._kernel_store
    store.clock = SteppedClock(LATER)
    table = await _expiring(store, expired=3)
    spy = Spy(_probe_sweeper(table))
    store.register_sweeper("probe", spy)
    refused = await masked.sweep()
    await masked.close()
    unmasked = AsyncVirtualFileSystem(storage=SQLiteStorage(path=path))
    unmasked._kernel_store.clock = SteppedClock(LATER)
    unmasked._kernel_store.register_sweeper("probe", _probe_sweeper(table))
    swept = await unmasked.sweep()
    await unmasked.close()
    assert (refused.success, spy.removed, swept.success, file_rows(tmp_path / "knowledge.db", PROBE_TABLE)) == (
        False,
        [],
        True,
        0,
    )


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_sweeper_with_small_batches_is_called_until_it_finds_nothing(
    stores: Callable[..., KernelStore],
) -> None:
    """Guards a pass that ends a sweeper's turn when a call removes less than its limit."""
    store = _later_store(stores)
    table = await _expiring(store, expired=300)

    async def by_hundreds(owner: KernelStore, transaction: Transaction, now: datetime, _limit: int) -> int:
        return await owner.delete_expired(
            transaction, table, key=table.c.name, expires=table.c.expires_at, now=now, limit=100
        )

    spy = Spy(by_hundreds)
    store.register_sweeper("probe", spy)
    assert (await store.sweep(), spy.removed) == (300, [100, 100, 100, 0])


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_sweeper_is_registered_once(stores: Callable[..., KernelStore]) -> None:
    """Guards two sweepers of one name, of which a pass would run one twice or one never."""
    store = stores()
    table = await probe_table(store)
    store.register_sweeper("probe", _probe_sweeper(table))
    with pytest.raises(ValueError, match="already"):
        store.register_sweeper("probe", _probe_sweeper(table))


# ---------------------------------------------------------------------------
# expiry_sweeper
# ---------------------------------------------------------------------------


async def _family(store: KernelStore) -> tuple[Table, Table]:
    """A parent table with an expiry and a dependent table that holds the parent's key, made in a commit."""
    metadata = MetaData()
    schema = store.tables.meta.schema
    parents = Table(
        "vfs_kernel_parents",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("expires_at", DateTime(timezone=True)),
        schema=schema,
    )
    dependents = Table(
        "vfs_kernel_dependents",
        metadata,
        Column("parent_id", Integer, primary_key=True),
        Column("number", Integer, primary_key=True),
        Column("note", String(16)),
        schema=schema,
    )

    async def make(transaction: Transaction) -> None:
        await (await transaction.connection()).run_sync(metadata.create_all, checkfirst=True)

    await store.commit(make)
    return parents, dependents


async def _families(store: KernelStore, parents: Table, dependents: Table, *, expired: int, each: int) -> None:
    """*expired* expired parents with *each* dependents, and one live parent, id 0, with 2."""
    parent_rows = [{"id": 0, "expires_at": LATER + timedelta(days=9)}]
    parent_rows += [{"id": index, "expires_at": EXPIRED} for index in range(1, expired + 1)]
    dependent_rows = [{"parent_id": 0, "number": number, "note": "live"} for number in range(2)]
    dependent_rows += [
        {"parent_id": index, "number": number, "note": "old"}
        for index in range(1, expired + 1)
        for number in range(each)
    ]

    async def fill(transaction: Transaction) -> None:
        await store.insert_rows(transaction, parents, parent_rows)
        await store.insert_rows(transaction, dependents, dependent_rows)

    await store.commit(fill)


@pytest.mark.parametrize("place", BOTH_ENGINES, indirect=True)
async def test_an_expiry_sweeper_removes_dependents_before_parents(stores: Callable[..., KernelStore]) -> None:
    """Guards a sweeper that removes a parent before its dependents, or more than its limit in one call."""
    store = _later_store(stores)
    parents, dependents = await _family(store)
    await _families(store, parents, dependents, expired=3, each=4)
    sweeper = expiry_sweeper(
        parents, key=parents.c.id, expires=parents.c.expires_at, dependents=(dependents.c.parent_id,)
    )
    calls: list[tuple[int, int, int]] = []
    for _ in range(4):
        removed = await store.commit(lambda transaction: sweeper(store, transaction, store.now(), 5))
        calls.append((removed, await count_rows(store, parents), await count_rows(store, dependents)))
    assert calls == [(5, 4, 9), (5, 4, 4), (5, 1, 2), (0, 1, 2)]


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_an_expiry_sweeper_binds_the_same_values_at_any_size(stores: Callable[..., KernelStore]) -> None:
    """Guards a sweeper that binds a list of the keys it found, which grows to an engine's cap."""
    store = _later_store(stores)
    parents, dependents = await _family(store)
    sweeper = expiry_sweeper(
        parents, key=parents.c.id, expires=parents.c.expires_at, dependents=(dependents.c.parent_id,)
    )
    shapes: list[set[tuple[str, int]]] = []
    for expired in (3, 2_000):
        await _families(store, parents, dependents, expired=expired, each=2)
        sent = statements_of(store)
        await store.commit(lambda transaction: sweeper(store, transaction, store.now(), SWEEP_CHUNK))
        shapes.append({(item.sql, item.binds) for item in _deletes(sent)})
        await store.commit(lambda transaction: transaction.execute(dependents.delete()))
        await store.commit(lambda transaction: transaction.execute(parents.delete()))
    assert (shapes[0], len(shapes[0])) == (shapes[1], 2)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_an_expiry_sweeper_that_spends_its_limit_on_dependents_stops(stores: Callable[..., KernelStore]) -> None:
    """Guards a sweeper that goes on to a second dependent, or to the parents, with nothing of its limit left."""
    store = _later_store(stores)
    parents, dependents = await _family(store)
    await _families(store, parents, dependents, expired=2, each=3)
    sweeper = expiry_sweeper(
        parents,
        key=parents.c.id,
        expires=parents.c.expires_at,
        dependents=(dependents.c.parent_id, dependents.c.number),
    )
    sent = statements_of(store)
    removed = await store.commit(lambda transaction: sweeper(store, transaction, store.now(), 4))
    assert (removed, len(_deletes(sent))) == (4, 1)


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_row_with_no_expiry_is_never_swept(stores: Callable[..., KernelStore]) -> None:
    """Guards a sweep that reads a null expiry as long past: a session with no lifetime would be removed."""
    clock = SteppedClock(LATER)
    store = stores(clock=clock)
    table = await _expiring(store, expired=2, none=3)
    store.register_sweeper("probe", _probe_sweeper(table))
    clock.step(365 * 86_400)
    assert (await store.sweep(), await count_rows(store, table)) == (2, 3)


# ---------------------------------------------------------------------------
# The public sweep
# ---------------------------------------------------------------------------


async def test_the_public_sweep_runs_one_pass(tmp_path: pathlib.Path) -> None:
    """Guards a public sweep that reclaims no record, or reclaims them for another mount's trash or a refused caller.

    Under the default posture every caller may write the root, so a caller
    is refused here by a posture of ``none`` and no grant.
    """
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(tmp_path / "knowledge.db")))
    store = fs._kernel_store
    store.clock = SteppedClock(LATER)
    table = await _expiring(store, expired=3)
    spy = Spy(_probe_sweeper(table))
    store.register_sweeper("probe", spy)
    swept = await fs.sweep()
    found = [removed for removed in spy.removed if removed]
    await fs.add_mount(SQLiteStorage(path=str(tmp_path / "other.db")), "/m")
    await store.commit(inserting(table, _named("again", 3, EXPIRED), store))
    spy.removed.clear()
    other = await fs.sweep("/m/.vfs/trash")
    subtree = await fs.sweep("/.vfs/trash/gone")
    assert (await fs.set_posture("/", "none")).success
    refused = await fs.sweep(authority=Authority.of(Principal("bob")))
    left = await count_rows(store, table)
    await fs.close()
    assert (swept.success, swept.errors, found) == (True, [], [3])
    assert ([result.success for result in (other, subtree, refused)], spy.removed, left) == (
        [True, False, False],
        [],
        3,
    )


async def test_a_public_sweep_makes_no_kernel_table(tmp_path: pathlib.Path) -> None:
    """Guards a public sweep that makes the kernel's tables in a file that kept no record."""
    path = tmp_path / "knowledge.db"
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(path)))
    assert (await fs.write(path="/a.txt", content="kept")).success
    before = _tables(path)
    store = fs._kernel_store
    store.register_sweeper("probe", _probe_sweeper(probe_table_shape(store)))
    swept = await fs.sweep()
    after = _tables(path)
    await fs.close()
    kernel = [[name for name in tables if name.startswith("vfs_kernel")] for tables in (before, after)]
    assert (swept.success, kernel) == (True, [[], []])


async def test_a_failed_pass_is_a_warning_on_the_sweep(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Guards a failed pass that fails the sweep of the trash, or raises from it, or says nothing."""
    path = tmp_path / "knowledge.db"
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=str(path)))
    store = fs._kernel_store
    store.clock = SteppedClock(LATER)
    table = await _expiring(store, expired=3)
    store.register_sweeper("probe", _probe_sweeper(table))
    without_waiting(store)
    holder = HeldWriter(path)

    async def hold() -> None:
        holder.hold()
        seams.clear("kernel-store:before-try")

    caplog.set_level(logging.WARNING, logger="vfs.kernel_store")
    try:
        with seams.installed("kernel-store:before-try", hold):
            swept = await fs.sweep()
    finally:
        holder.release()
    await fs.close()
    assert (swept.success, [error.severity for error in swept.errors]) == (True, [Severity.warning])
    assert (len(records(caplog, "WARNING")), file_rows(path, PROBE_TABLE)) == (1, 3)


async def test_a_sweep_of_a_place_that_is_not_a_database_fails(tmp_path: pathlib.Path) -> None:
    """Guards a pass whose look for the kernel's tables fails raw, where every caller expects the store's one error."""
    path = tmp_path / "knowledge.db"
    path.write_bytes(b"this file is no database at all, and SQLite says so" * 100)
    store = KernelStore(RecordPlace(url=f"sqlite+aiosqlite:///{path}", label=str(path)))
    store.register_sweeper("probe", _probe_sweeper(probe_table_shape(store)))
    with pytest.raises(KernelStoreUnavailable):
        await store.sweep()
    await store.close()


@pytest.mark.parametrize("place", SQLITE_PLACES, indirect=True)
async def test_a_closed_store_sweeps_nothing(stores: Callable[..., KernelStore]) -> None:
    """Guards a pass on a closed store that opens its engine again."""
    store = stores()
    table = await probe_table(store)
    store.register_sweeper("probe", _probe_sweeper(table))
    await store.close()
    with pytest.raises(KernelStoreUnavailable):
        await store.sweep()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tables(path: pathlib.Path) -> list[str]:
    """The names of the tables in the SQLite file at *path*, sorted."""
    connection = sqlite3.connect(path)
    try:
        return sorted(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
    finally:
        connection.close()
