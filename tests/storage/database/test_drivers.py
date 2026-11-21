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
from vfs.storage.backends.database.drivers import ClosingConnection, ClosingCursor, merge_engine_arguments

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


MSSQL = "mssql+aioodbc://sa:pw@host/db"
SQLITE = "sqlite+aiosqlite:////tmp/vfs.sqlite"
POSTGRES = "postgresql+asyncpg://vfs:vfs@host/vfs"


class TestTheEngineArguments:
    def test_a_sql_server_url_leaves_text_binds_as_unicode(self) -> None:
        # pyodbc's ANSI setinputsizes mangles non-Latin1 bytes, so only this URL carries the override.
        assert merge_engine_arguments(MSSQL) == {"use_setinputsizes": False}

    @pytest.mark.parametrize("url", ["sqlite+aiosqlite:///:memory:", SQLITE])
    def test_a_sqlite_url_opens_closing_connections(self, url) -> None:
        assert merge_engine_arguments(url) == {"connect_args": {"factory": ClosingConnection}}

    def test_any_other_url_needs_nothing(self) -> None:
        assert merge_engine_arguments(POSTGRES) == {}

    def test_an_argument_vfs_has_no_stake_in_passes_through(self) -> None:
        given = {"pool_size": 3, "max_overflow": 0, "pool_pre_ping": True, "connect_args": {"timeout": 9}}
        assert merge_engine_arguments(POSTGRES, given) == given
        assert merge_engine_arguments(MSSQL, given) == {**given, "use_setinputsizes": False}

    def test_connect_arguments_are_merged_key_by_key(self) -> None:
        """Guards the merge: the application's ``connect_args`` put in whole would drop the connection class."""
        given = {"pool_size": 1, "connect_args": {"timeout": 9}}
        merged = merge_engine_arguments(SQLITE, given)
        assert merged == {"pool_size": 1, "connect_args": {"timeout": 9, "factory": ClosingConnection}}
        # The application's own mapping is left as it was given.
        assert given == {"pool_size": 1, "connect_args": {"timeout": 9}}

    def test_the_value_vfs_requires_is_accepted_when_the_application_gives_it_too(self) -> None:
        assert merge_engine_arguments(MSSQL, {"use_setinputsizes": False}) == {"use_setinputsizes": False}
        given = {"connect_args": {"factory": ClosingConnection}}
        assert merge_engine_arguments(SQLITE, given) == given

    @pytest.mark.parametrize(
        ("url", "given", "named"),
        [
            (MSSQL, {"use_setinputsizes": True}, r"engine_arguments\['use_setinputsizes'\]"),
            (
                SQLITE,
                {"connect_args": {"factory": sqlite3.Connection}},
                r"engine_arguments\['connect_args'\]\['factory'\]",
            ),
        ],
        ids=["sql server", "sqlite"],
    )
    def test_another_value_for_an_argument_vfs_requires_is_refused_by_name(self, url, given, named) -> None:
        """Guards the refusal: a required argument dropped in silence is a storage that corrupts text or leaks files."""
        with pytest.raises(ValueError, match=named) as refused:
            merge_engine_arguments(url, given)
        assert "because" in str(refused.value)


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
