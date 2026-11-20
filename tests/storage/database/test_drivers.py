"""What VFS asks of a driver for one URL, and the SQLite cursor that closes itself when its statement fails.

A cursor that is left open after a failure keeps its statement on Python
3.11. A connection closed while that cursor lives leaves its log and its
index file behind, and freeing the cursor later waits on the connection.
These tests hold the cursor in hand across the close, as a traceback does.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.drivers import ClosingConnection, ClosingCursor, engine_arguments

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

CLOSED = "Cannot operate on a closed cursor"
COUNTING = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT x FROM c"
"""A statement with no last row, so a fetch of every row ends only when it is stopped."""


def left_behind(folder: pathlib.Path) -> list[str]:
    """The log and index files SQLite has not deleted in ``folder``."""
    return sorted(path.name for path in folder.iterdir() if path.name.endswith(("-wal", "-shm")))


def is_closed(cursor: sqlite3.Cursor) -> bool:
    """Report whether ``cursor`` refuses a fetch as a closed cursor does."""
    try:
        cursor.fetchone()
    except sqlite3.ProgrammingError as refused:
        return CLOSED in str(refused)
    return False


@pytest.fixture
def connection() -> Iterator[ClosingConnection]:
    """An in-memory database with one table whose column is unique."""
    with closing(sqlite3.connect(":memory:", factory=ClosingConnection, isolation_level=None)) as opened:
        opened.execute("CREATE TABLE t (x INTEGER UNIQUE)")
        yield opened


class TestTheEngineArguments:
    def test_a_sql_server_url_leaves_text_binds_as_unicode(self) -> None:
        # pyodbc's ANSI setinputsizes mangles non-Latin1 bytes, so only this URL carries the override.
        assert engine_arguments("mssql+aioodbc://sa:pw@host/db") == {"use_setinputsizes": False}

    @pytest.mark.parametrize("url", ["sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:////tmp/vfs.sqlite"])
    def test_a_sqlite_url_opens_closing_connections(self, url) -> None:
        assert engine_arguments(url) == {"connect_args": {"factory": ClosingConnection}}

    def test_any_other_url_needs_nothing(self) -> None:
        assert engine_arguments("postgresql+asyncpg://vfs:vfs@host/vfs") == {}


class TestACursorWhoseStatementFails:
    def test_a_refused_begin_closes_its_cursor_and_the_closed_file_keeps_no_log(self, tmp_path) -> None:
        path = tmp_path / "one.sqlite"
        with closing(sqlite3.connect(path, isolation_level=None)) as holder:
            holder.execute("PRAGMA journal_mode=WAL")
            holder.execute("CREATE TABLE t (x)")
            holder.execute("BEGIN IMMEDIATE")
            waiter = sqlite3.connect(path, factory=ClosingConnection, isolation_level=None, timeout=0)
            assert waiter.execute("SELECT count(*) FROM t").fetchall() == [(0,)]
            cursor = waiter.cursor()
            with pytest.raises(sqlite3.OperationalError, match="database is locked"):
                cursor.execute("BEGIN IMMEDIATE")
            holder.execute("COMMIT")
        waiter.close()
        assert left_behind(tmp_path) == []
        assert is_closed(cursor)

    def test_a_statement_that_cannot_be_prepared_closes_its_cursor(self, connection) -> None:
        cursor = connection.cursor()
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            cursor.execute("SELECT x FROM missing")
        assert is_closed(cursor)

    def test_a_batch_that_fails_on_a_later_row_closes_its_cursor(self, connection) -> None:
        cursor = connection.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.executemany("INSERT INTO t VALUES (?)", [(1,), (1,)])
        assert is_closed(cursor)

    def test_a_script_that_fails_closes_its_cursor(self, connection) -> None:
        cursor = connection.cursor()
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            cursor.executescript("INSERT INTO t VALUES (1); INSERT INTO missing VALUES (1);")
        assert is_closed(cursor)

    @pytest.mark.parametrize("fetch", ["fetchone", "fetchmany", "fetchall"])
    def test_a_fetch_that_is_stopped_closes_its_cursor(self, connection, fetch) -> None:
        cursor = connection.cursor()
        cursor.execute(COUNTING)
        connection.set_progress_handler(lambda: 1, 1)
        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            getattr(cursor, fetch)()
        connection.set_progress_handler(None, 1)
        assert is_closed(cursor)

    def test_a_statement_that_succeeds_leaves_its_cursor_open(self, connection) -> None:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO t VALUES (1)")
        cursor.executemany("INSERT INTO t VALUES (?)", [(2,), (3,)])
        assert cursor.execute("SELECT x FROM t ORDER BY x").fetchall() == [(1,), (2,), (3,)]
        assert cursor.fetchone() is None

    def test_a_failure_on_a_closed_connection_is_the_one_the_caller_sees(self) -> None:
        opened = sqlite3.connect(":memory:", factory=ClosingConnection)
        cursor = opened.cursor()
        opened.close()
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            cursor.execute("SELECT 1")


class TestTheConnection:
    @pytest.mark.parametrize(
        ("method", "arguments"),
        [
            ("execute", ("SELECT 1",)),
            ("executemany", ("INSERT INTO t VALUES (?)", [(1,)])),
            ("executescript", ("INSERT INTO t VALUES (2);",)),
        ],
    )
    def test_every_way_to_run_a_statement_hands_back_a_closing_cursor(self, connection, method, arguments) -> None:
        assert isinstance(getattr(connection, method)(*arguments), ClosingCursor)

    def test_a_cursor_class_that_is_asked_for_by_name_is_the_one_made(self, connection) -> None:
        assert type(connection.cursor(sqlite3.Cursor)) is sqlite3.Cursor
        assert type(connection.cursor()) is ClosingCursor

    def test_a_statement_run_on_the_connection_closes_its_cursor_when_it_fails(self, connection, monkeypatch) -> None:
        made: list[sqlite3.Cursor] = []
        cursor = ClosingConnection.cursor

        def kept(self: ClosingConnection) -> sqlite3.Cursor:
            made.append(cursor(self))
            return made[-1]

        monkeypatch.setattr(ClosingConnection, "cursor", kept)
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            connection.execute("SELECT x FROM missing")
        assert [is_closed(one) for one in made] == [True]


class TestAStorageOpenedFromAUrl:
    async def test_its_connections_close_a_cursor_whose_statement_fails(self, tmp_path) -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path / 'vfs.sqlite'}")
        assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
        async with storage._host.engine.connect() as connection:
            raw = await connection.get_raw_connection()
            assert isinstance(raw.driver_connection._conn, ClosingConnection)  # ty: ignore[unresolved-attribute]
        await storage.close()
