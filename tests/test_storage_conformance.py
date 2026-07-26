"""Conformance-suite instantiations — one subclass per backend.

The contract itself lives in ``storage_conformance.StorageContract``;
this file only wires backends in. The memory leg is ``InMemoryStorage``
— ``DatabaseStorage`` over in-memory SQLite — so it runs the same
families as the sqlite-file leg, trash arc included; capability gating
skips only what a backend leaves undeclared.

Real-server legs activate when their ``VFS_TEST_<ENGINE>_URL`` variable
is set and skip otherwise, so a plain run never needs Docker. Servers
come from ``docker/compose.test.yml`` (same file CI uses); each test
gets a clean slate — tables dropped up front, recreated by the
backend's own first touch — because the server outlives the test where
sqlite's tmp file does not. Selection is URL-driven per SQLAlchemy's
own harness; drop-before-run is its ``provision`` reset, minus the
xdist follower machinery this sequential suite doesn't need.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from storage_conformance import StorageContract
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator

    from vfs.results import Result


class TestMemoryConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[InMemoryStorage]:
        storage = InMemoryStorage()
        yield storage
        await storage.close()


class TestSqliteConformance(StorageContract):
    @pytest.fixture
    async def storage(self, tmp_path: pathlib.Path) -> AsyncIterator[DatabaseStorage]:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite")
        yield storage
        await storage.close()


@asynccontextmanager
async def _server_storage(env_var: str) -> AsyncIterator[DatabaseStorage]:
    """A fresh backend on the server named by ``env_var``, tables reset."""
    url = os.environ.get(env_var)
    if url is None:
        pytest.skip(f"{env_var} is not set")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(build_vfs_tables(table_name="vfs").metadata.drop_all)
    finally:
        await engine.dispose()
    storage = DatabaseStorage(url=url)
    try:
        yield storage
    finally:
        await storage.close()


@pytest.mark.postgres
class TestPostgresConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            yield storage


@pytest.mark.mysql
class TestMySQLConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_MYSQL_URL") as storage:
            yield storage


@pytest.mark.mssql
class TestMSSQLConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            yield storage


@pytest.mark.oracle
class TestOracleConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_ORACLE_URL") as storage:
            yield storage


async def _one_increment_race(storage: DatabaseStorage) -> Result:
    """Stage a rival one increment ahead inside the guard's window.

    The rival lands through the write path's declared seam — after the
    snapshot read and staging, before any mutation statement — and the
    victim is the real public verb, so retry and classification run
    live; nothing is mirrored. Post-image inference cannot see this
    rival: the row lands on exactly the version the victim staged, so
    only statement-native attribution can fail the batch. The handler
    uninstalls itself so the rival's own write (and any retry of the
    victim) passes the seam untouched.
    """
    target = Path("/race.txt")
    assert (await storage.write(entries=[Entry(path=target, content="base")])).success

    async def rival() -> None:
        seams.clear("write:before-apply")
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success

    with seams.installed("write:before-apply", rival):
        return await storage.write(entries=[Entry(path=target, content="mine")])


@pytest.mark.mssql
class TestMSSQLBindBudget:
    async def test_bumping_over_a_thousand_parents_stays_under_the_cap(self) -> None:
        """The steady-state ingest shape: one batch of files under more
        pre-existing parents than a single bump statement may carry —
        chunked under the measured bind budget, never the raw cap."""
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            n = 1_100
            dirs = [Entry(path=Path(f"/p{i:04d}"), kind="directory") for i in range(n)]
            assert (await storage.write(entries=dirs)).success is True
            files = [Entry(path=Path(f"/p{i:04d}/f.txt"), content="x") for i in range(n)]
            result = await storage.write(entries=files)
            assert result.success is True, result.errors[:3]


@pytest.mark.mssql
class TestMSSQLTornRowRegression:
    async def test_one_increment_rival_classifies_conflict(self) -> None:
        """READ COMMITTED cannot redrive: the guard must classify, never tear.

        A false success is a torn row — the rival's entry columns over
        our content rows — which is exactly what the pre-079 read-back
        produced on this engine.
        """
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is False
            assert [e.kind for e in result.errors] == [VFSErrorKind.conflict]
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "content_hash"}))
            after = read.observations[0]
            assert after.content == "rival"
            assert after.content_hash == Entry(path=Path("/race.txt"), content=after.content).content_hash


@pytest.mark.postgres
class TestPostgresRivalRedrive:
    async def test_one_increment_rival_redrives_to_success(self) -> None:
        """REPEATABLE READ surfaces the rival as 40001 and the method redrives.

        The same staged race that must classify ``conflict`` on MSSQL
        resolves to a clean success here: the whole method restarts from
        a fresh snapshot and lands on top of the rival's version.
        """
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is True
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "version"}))
            after = read.observations[0]
            assert after.content == "mine"
            assert after.version == 3


async def _purge_sweeps_a_mid_purge_rival(env_var: str) -> None:
    """A rival write landing inside the purge window is swept, not orphaned.

    Writes are not serialized with topology, so a rival can commit a new
    child between the purge's id collection and its deletes. The purge's
    re-collection must sweep it with the subtree — the stale-id-list
    alternative left a permanent orphan row on every real engine.
    """
    async with _server_storage(env_var) as storage:
        assert (await storage.mkdir(path=Path("/d"))).success
        assert (await storage.write(entries=[Entry(path=Path("/d/base.txt"), content="x")])).success
        rival_results: list[Result] = []

        async def rival() -> None:
            seams.clear("purge:post-collect")
            rival_results.append(await storage.write(entries=[Entry(path=Path("/d/fresh.txt"), content="rival")]))

        with seams.installed("purge:post-collect", rival):
            victim = await storage.sweep(path=Path("/d"))
        assert victim.success is True, victim.errors
        assert rival_results and rival_results[0].success is True
        assert (await storage.stat(path=Path("/d/fresh.txt"))).success is False
        assert (await storage.stat(path=Path("/d"))).success is False
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            subtree = (entry.c.path == "/d") | entry.c.path.like("/d/%")
            leftovers = (await session.execute(select(entry.c.path).where(subtree))).scalars().all()
        assert leftovers == []


async def _serialization_point_blocks_a_rival_topology_verb(env_var: str) -> None:
    """A rival topology verb launched mid-window waits out the point.

    The rival move is spawned — never awaited — inside the delete's
    post-snapshot window: it must block on the serialization point and
    run only after the victim commits, so it finds its source already
    trashed. Without the point the rival would commit mid-window and
    both verbs would report success.
    """
    async with _server_storage(env_var) as storage:
        assert (await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])).success
        tasks: list[asyncio.Task[Result]] = []

        async def rival() -> None:
            seams.clear("delete:post-snapshot")
            move = storage.move(operations=[ResolvedPair(src=Path("/x.txt"), dest=Path("/y.txt"))])
            tasks.append(asyncio.ensure_future(move))
            # Give the rival time to reach — and block on — the point.
            await asyncio.sleep(0.5)

        with seams.installed("delete:post-snapshot", rival):
            victim = await storage.delete(path=Path("/x.txt"))
        rival_result = await asyncio.wait_for(tasks[0], timeout=60)
        assert victim.success is True, victim.errors
        assert rival_result.success is False
        assert rival_result.errors[0].kind == VFSErrorKind.not_found
        assert (await storage.stat(path=Path("/y.txt"))).success is False


@pytest.mark.postgres
class TestPostgresTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_POSTGRES_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_POSTGRES_URL")


@pytest.mark.mysql
class TestMySQLTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_MYSQL_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_MYSQL_URL")


@pytest.mark.mssql
class TestMSSQLTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_MSSQL_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_MSSQL_URL")


@pytest.mark.oracle
class TestOracleTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_ORACLE_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_ORACLE_URL")


@pytest.mark.mysql
class TestMySQLTornRowRegression:
    async def test_one_increment_rival_redrives_to_success(self) -> None:
        """InnoDB's REPEATABLE READ current-reads past the rival — no 40001.

        The guarded UPDATE matches nothing, and at this isolation a
        re-probe would report the stale snapshot rather than the rival —
        so the declared ``guard_miss`` mode redrives the whole method
        from fresh state instead of classifying off a lying probe. The
        outcome converges with the Postgres redrive: a clean success on
        top of the rival's version, never a torn row.
        """
        async with _server_storage("VFS_TEST_MYSQL_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is True
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "content_hash", "version"}))
            after = read.observations[0]
            assert after.content == "mine"
            assert after.version == 3
            assert after.content_hash == Entry(path=Path("/race.txt"), content=after.content).content_hash
