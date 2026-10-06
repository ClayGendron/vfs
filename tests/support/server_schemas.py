"""A fresh schema per test on the real-engine legs.

vfs's table names are fixed, so a running server isolates two mounts by
schema. Each engine-leg test gets its own uniquely named schema, created
before the backend's first touch and dropped (with every table in it)
after. That keeps the legs reentrant: concurrent runs against one server
never tear each other down.

    async with server_storage("VFS_TEST_POSTGRES_URL") as storage:
        await storage.mkdir(path=Path("/docs"))

What a schema is differs by engine. On Postgres and SQL Server it is a
schema; on MariaDB it is a database; on Oracle it is a user, created
schema-only (no password, no login). Names are lowercase ascii and
digits, so no engine needs them quoted; Oracle folds them to uppercase.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models.rows import build_vfs_tables
from vfs.storage.backends.database import DatabaseStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncConnection

# Per dialect: the statement that makes a schema, and the one that removes it.
_SCHEMA_DDL: dict[str, tuple[str, str]] = {
    "postgresql": ("CREATE SCHEMA {schema}", "DROP SCHEMA {schema} CASCADE"),
    "mssql": ("CREATE SCHEMA {schema}", "DROP SCHEMA {schema}"),
    "mariadb": ("CREATE DATABASE {schema}", "DROP DATABASE {schema}"),
    "mysql": ("CREATE DATABASE {schema}", "DROP DATABASE {schema}"),
    "oracle": (
        "CREATE USER {schema} NO AUTHENTICATION DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS",
        "DROP USER {schema} CASCADE",
    ),
}


# ---------------------------------------------------------------------------
# Per-test schemas
# ---------------------------------------------------------------------------


@asynccontextmanager
async def server_storage(env_var: str, **options: Any) -> AsyncIterator[DatabaseStorage]:
    """A backend on the server named by *env_var*, in a schema of its own.

    Skips when *env_var* is unset. *options* pass through to
    :class:`DatabaseStorage`. Teardown closes the backend, then drops the
    schema and everything in it.
    """
    url = os.environ.get(env_var)
    if url is None:
        pytest.skip(f"{env_var} is not set")
    schema = f"vfs_t_{uuid4().hex[:12]}"
    await _apply(url, schema, create=True)
    storage = DatabaseStorage(url=url, schema=schema, **options)
    try:
        yield storage
    finally:
        await storage.close()
        await _apply(url, schema, create=False)


def sibling(env_var: str, storage: DatabaseStorage, **options: Any) -> DatabaseStorage:
    """A rival handle on *storage*'s own schema — a second process on the same mount."""
    return DatabaseStorage(url=os.environ[env_var], schema=storage._host.tables.entry.schema, **options)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _apply(url: str, schema: str, *, create: bool) -> None:
    """Create or drop *schema* on the server at *url*, on a short-lived engine."""
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await _run(conn, schema, create=create)
    finally:
        await engine.dispose()


async def _run(conn: AsyncConnection, schema: str, *, create: bool) -> None:
    """The dialect's schema statement; SQL Server drops only an empty schema, so its tables go first."""
    make, remove = _SCHEMA_DDL[conn.dialect.name]
    if not create and conn.dialect.name == "mssql":
        await conn.run_sync(build_vfs_tables(schema=schema).metadata.drop_all)
    await conn.execute(text((make if create else remove).format(schema=schema)))
