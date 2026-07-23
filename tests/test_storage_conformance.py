"""Conformance-suite instantiations — one subclass per backend.

The contract itself lives in ``storage_conformance.StorageContract``;
this file only wires backends in. The sqlite leg runs the families
``DatabaseStorage`` declares so far — capability gating skips the rest,
and each mutation slice landing flips its rows from skipped to enforced.

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

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from storage_conformance import StorageContract
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator

    from vfs.results import Result


class TestMemoryConformance(StorageContract):
    @pytest.fixture
    def storage(self) -> InMemoryStorage:
        return InMemoryStorage()


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


@pytest.mark.mysql
class TestMySQLTornRowRegression:
    async def test_one_increment_rival_classifies_conflict(self) -> None:
        """InnoDB's REPEATABLE READ current-reads past the rival — no 40001.

        The guarded UPDATE matches nothing and the executemany ladder
        must classify ``conflict`` from its own rowcounts, exactly the
        MSSQL contract: the rival's row survives untorn.
        """
        async with _server_storage("VFS_TEST_MYSQL_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is False
            assert [e.kind for e in result.errors] == [VFSErrorKind.conflict]
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "content_hash"}))
            after = read.observations[0]
            assert after.content == "rival"
            assert after.content_hash == Entry(path=Path("/race.txt"), content=after.content).content_hash
