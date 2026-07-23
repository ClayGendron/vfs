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
from vfs.models.rows import build_vfs_tables
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator


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
