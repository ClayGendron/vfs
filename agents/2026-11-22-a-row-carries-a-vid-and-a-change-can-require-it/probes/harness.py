"""Shared setup for the probes of the etag spec: one storage per engine, a rival handle, a statement recorder.

Nothing of the etag spec is built, so every probe exercises the code as it
stands at the commit under review, or sends the statements the spec quotes
to a server directly. This module is imported by the numbered probes and
shows nothing by itself. Each probe is run from the repository root:

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/<probe>.py

With ``VFS_TEST_POSTGRES_URL`` unset a probe runs its SQLite leg alone and
says the Postgres leg was not run. Every probe carries its own deadline
(``DEADLINE_SECONDS``, enforced by :func:`run`), and a deadline that fires
is reported as a failure, never waited out.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path as OsPath
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.storage.backends.postgres import PostgresStorage
from vfs.storage.backends.sqlite import SQLiteStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

    from vfs.storage.backends.database import DatabaseStorage

POSTGRES_ENV = "VFS_TEST_POSTGRES_URL"
DEADLINE_SECONDS = 120.0

_NOISE = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK", "ANALYZE", "SET ", "SHOW ")


def engines() -> list[str]:
    """The engine legs this run can reach: SQLite always, Postgres when its URL is set."""
    legs = ["sqlite"]
    if os.environ.get(POSTGRES_ENV):
        legs.append("postgres")
    else:
        print(f"NOT RUN: the postgres leg, because {POSTGRES_ENV} is unset")
    return legs


@asynccontextmanager
async def storage_on(engine: str) -> AsyncIterator[tuple[DatabaseStorage, Callable[[], DatabaseStorage]]]:
    """A storage on *engine* in a place of its own, and a factory of rival handles on the same database.

    SQLite is a file in a fresh temporary directory. Postgres is a fresh
    schema on the server ``VFS_TEST_POSTGRES_URL`` names, dropped on exit.
    Every rival handle the factory made is closed on exit.
    """
    rivals: list[DatabaseStorage] = []
    if engine == "sqlite":
        with tempfile.TemporaryDirectory() as directory:
            path = OsPath(directory) / "probe.sqlite"
            storage: DatabaseStorage = SQLiteStorage(path=path)

            def rival() -> DatabaseStorage:
                rivals.append(SQLiteStorage(path=path))
                return rivals[-1]

            try:
                yield storage, rival
            finally:
                for handle in (*rivals, storage):
                    await handle.close()
        return
    url = os.environ[POSTGRES_ENV]
    schema = f"vfs_t_{uuid4().hex[:12]}"
    await _schema(url, f"CREATE SCHEMA {schema}")
    storage = PostgresStorage(url=url, schema=schema)

    def rival() -> DatabaseStorage:
        rivals.append(PostgresStorage(url=url, schema=schema))
        return rivals[-1]

    try:
        yield storage, rival
    finally:
        for handle in (*rivals, storage):
            await handle.close()
        await _schema(url, f"DROP SCHEMA {schema} CASCADE")


@contextmanager
def recorded(storage: DatabaseStorage) -> Iterator[list[str]]:
    """Every statement *storage* sends while the block runs, transaction control and settings left out."""
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        # The planner-statistics step is SQLite's own and no verb's: the suite leaves it out of a count too.
        statistics = "sqlite_stat1" in statement or "vfs_statistics" in statement
        if not statistics and not statement.lstrip().upper().startswith(_NOISE):
            statements.append(" ".join(statement.split()))

    sync_engine = storage._host.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)


def verbs(statements: list[str]) -> list[str]:
    """The first word of each statement: the list a statement-count test compares."""
    return [statement.split(None, 1)[0].upper() for statement in statements]


def where_of(statement: str) -> str:
    """The text of *statement* from its ``WHERE`` on, with the ``RETURNING`` tail kept."""
    upper = statement.upper()
    return statement[upper.index(" WHERE ") + 1 :] if " WHERE " in upper else "(no WHERE)"


def run(main: Callable[[], Awaitable[None]], *, deadline: float = DEADLINE_SECONDS) -> None:
    """Run *main* under the probe's own deadline; a deadline that fires exits 2 and says so."""

    async def bounded() -> None:
        async with asyncio.timeout(deadline):
            await main()

    try:
        asyncio.run(bounded())
    except TimeoutError:
        print(f"DEADLINE: the probe did not finish in {deadline:.0f} s")
        sys.exit(2)


async def _schema(url: str, statement: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()
