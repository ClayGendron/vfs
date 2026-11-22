"""Shared helpers for the database-backend test files.

The per-module suites under ``tests/storage/database/`` all build the
same sqlite URL, and several of them need the same doubles: a driver
error the retry classifier recognizes, and a session whose UPDATEs
answer with canned RETURNING rows (the VALUES-join arm sqlite cannot
execute). Helpers used by a single file stay in that file.
"""

from __future__ import annotations

import asyncio
import functools
import pathlib
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, event
from sqlalchemy.dialects import postgresql

from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.staging import StagedEntry

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

    from vfs.storage.backends.database.staging import PersistenceState


# ---------------------------------------------------------------------------
# Mount URLs
# ---------------------------------------------------------------------------


def _url(tmp_path: pathlib.Path) -> str:
    """A mount URL under *tmp_path*, already provisioned: first touch adopts instead of creating.

    The file is a copy of one template provisioned once per process, so a
    test pays a 0.2 ms copy rather than the 94-statement schema build.
    Two calls on one *tmp_path* name the same file, as before. A test that
    proves provisioning itself takes :func:`_fresh_url`.
    """
    target = tmp_path / "vfs.sqlite"
    if not target.exists():
        shutil.copy(_template(), target)
    return f"sqlite+aiosqlite:///{target}"


def _fresh_url(tmp_path: pathlib.Path) -> str:
    """A mount URL under *tmp_path* with no file behind it: first touch provisions from nothing."""
    return f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite"


@functools.cache
def _template() -> pathlib.Path:
    """The provisioned sqlite file every `_url` copies, built once per process on a private thread.

    A private thread because the first caller is usually inside a running
    loop, where ``asyncio.run`` is refused; the template's own loop lives
    and dies on that thread.
    """
    target = pathlib.Path(tempfile.mkdtemp(prefix="vfs-template-")) / "vfs.sqlite"

    async def provision() -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{target}")
        assert (await storage.first_touch()).success, "the template must provision cleanly"
        await storage.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, provision()).result()
    return target


# ---------------------------------------------------------------------------
# A test's own writing transaction
# ---------------------------------------------------------------------------


async def begin_as_writer(session: AsyncSession) -> AsyncConnection:
    """Begin *session*'s transaction as a verb's writer does, ``BEGIN IMMEDIATE`` on SQLite; its first statement.

    A plain ``BEGIN`` takes SQLite's write lock only at its first write. A
    transaction that has read by then is refused at once with ``database
    is locked`` if another connection committed after that read, such as
    the host's background statistics pass, and no busy wait runs. A
    writer's ``BEGIN IMMEDIATE`` takes the lock first and waits for it.
    Every session a test opens by hand and writes through begins here;
    ``tests/conftest.py`` fails a test whose plain transaction reads and
    then writes. Off SQLite the option changes nothing.
    """
    return await session.connection(execution_options={"vfs_writer": True})


def writer_engine(engine: AsyncEngine) -> AsyncEngine:
    """*engine*, every transaction of which begins as a verb's writer does: ``writer_engine(e).begin()``.

    The connection-level counterpart of :func:`begin_as_writer`, for a test
    that writes through ``engine.begin()`` rather than a session.
    """
    return engine.execution_options(vfs_writer=True)


UNBOUNDED_BUSY_MILLISECONDS = 2**31 - 1
"""The largest ``busy_timeout`` SQLite takes, about 24 days: a wait no test reaches before its own deadline."""


def _waits_out_every_lock(storage: DatabaseStorage) -> None:
    """Make each connection *storage* checks out wait on a rival's write lock for as long as the rival holds it.

    A write of thousands of files holds the file's lock for seconds, and
    for longer on a loaded machine, past the shipped five-second
    ``busy_timeout`` and its retries. A test of two crossing writers waits
    on the rival's commit, and the run's own deadline bounds that wait.
    """

    @event.listens_for(storage._host.engine.sync_engine, "checkout")
    def patient(dbapi_connection, record, proxy) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA busy_timeout = {UNBOUNDED_BUSY_MILLISECONDS}")
        cursor.close()


# ---------------------------------------------------------------------------
# Driver-error doubles
# ---------------------------------------------------------------------------


class _SqliteError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("locked")
        self.sqlite_errorcode = code


# ---------------------------------------------------------------------------
# Session doubles for the arms sqlite cannot execute
# ---------------------------------------------------------------------------


class _CannedReturning:
    """Result double: canned RETURNING mappings, iterable as row objects."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows

    def all(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(**row) for row in self._rows]

    def __iter__(self) -> Iterator[SimpleNamespace]:
        return iter(SimpleNamespace(**row) for row in self._rows)

    @property
    def rowcount(self) -> int:
        return len(self._rows)


class _ReturningSession:
    """Session double for the VALUES-join arm SQLite cannot execute.

    UPDATE statements answer with the canned RETURNING rows; the guard
    miss re-probe (a SELECT) answers with *probed*.
    """

    def __init__(self, returned: list[dict[str, object]], probed: list[dict[str, object]] | None = None) -> None:
        self.returned = returned
        self.probed = probed if probed is not None else []
        self.statements: list[Any] = []

    def get_bind(self) -> SimpleNamespace:
        # A real dialect so probe statements compile; flags declared as
        # the double intends, independent of the driver's own defaults.
        dialect = postgresql.dialect()
        dialect.update_returning = True
        dialect.update_returning_multifrom = True
        dialect.supports_sane_rowcount = True
        dialect.supports_sane_multi_rowcount = False
        return SimpleNamespace(dialect=dialect)

    async def execute(self, stmt: Any, params: Any = None) -> _CannedReturning:
        self.statements.append(stmt)
        if isinstance(stmt, Select):
            return _CannedReturning(self.probed)
        return _CannedReturning(self.returned)


# ---------------------------------------------------------------------------
# Staged material
# ---------------------------------------------------------------------------


def _staged_material(path: str, entry_id: str, *, persistence: PersistenceState = "update") -> StagedEntry:
    return StagedEntry(
        path=Path(path),
        parent=Path("/"),
        kind="file",
        persistence=persistence,
        entry_id=entry_id,
        content="mine",
        base_version=1,
        version=2,
    )
