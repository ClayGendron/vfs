"""What VFS asks of a database driver when it builds an engine from a URL.

``engine_arguments`` gives the arguments for one URL. Two drivers need
something. SQL Server through pyodbc needs its text binds left as Unicode.
SQLite needs its connections opened as ``ClosingConnection``, whose cursors
close themselves when a statement fails.

    create_async_engine(url, **engine_arguments(url))

A statement can fail for an ordinary reason. Another writer holds the
database for longer than the wait allows, or ``close()`` stops a running
statement. SQLAlchemy does not close the cursor of a statement that failed,
and the error that reports the failure keeps that cursor alive until Python
next collects garbage. On Python 3.11 a cursor left open this way still
holds its statement inside SQLite, and two things go wrong.

A connection that is closed while the cursor lives is not really closed.
SQLite keeps the database file open, with its log and its index file beside
it, until the cursor is freed.

Freeing the cursor needs the connection it belongs to. When the garbage
collector frees it on the event loop while the connection waits for
another writer, the event loop waits too, for up to the whole wait. Every
call in the process stops for that long, and the writer that holds the
database is slowed with them.

Closing the cursor where the statement fails lets go of the statement at
once, on the thread that ran it, so neither can happen. Python 3.12 and
later let go of it without help, and the close changes nothing there.
"""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from functools import wraps
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Engine arguments
# ---------------------------------------------------------------------------


def engine_arguments(url: str) -> dict[str, Any]:
    """Return the engine arguments the driver behind ``url`` needs.

    SQLAlchemy's pyodbc dialect declares ``String`` binds as ANSI
    ``SQL_VARCHAR`` via setinputsizes, and the server squeezes those
    through the database codepage before they reach a UTF-8 column —
    mangling non-Latin1 to ``?``. Disabling setinputsizes restores
    pyodbc's Unicode default (``SQL_WVARCHAR``), whose conversion into
    the UTF-8 collation is lossless. pyodbc's ``fast_executemany`` is
    deliberately *not* set: engine-wide it rewrites UPDATE executemany,
    whose rowcount the guarded bumps verify, and as a bulk-insert mode it
    is still one RPC per row, slower than Core's pages on wide rows —
    SQL Server's bulk inserts take Core's pages.

    A SQLite connection is opened as a ``ClosingConnection``.

    A borrowed session factory carries the engine of whoever built it, and
    that builder applies these arguments itself.
    """
    backend = make_url(url).get_backend_name()
    if backend == "mssql":
        return {"use_setinputsizes": False}
    if backend == "sqlite":
        return {"connect_args": {"factory": ClosingConnection}}
    return {}


# ---------------------------------------------------------------------------
# SQLite connections whose cursors close on a failure
# ---------------------------------------------------------------------------


def _closing(method: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``method`` of a cursor so that the cursor is closed when the method fails."""

    @wraps(method)
    def run(self: sqlite3.Cursor, *arguments: Any) -> Any:
        try:
            return method(self, *arguments)
        except BaseException:
            # The failure of the statement is the one the caller sees, never a failure to close.
            with suppress(sqlite3.Error):
                self.close()
            raise

    return run


class ClosingCursor(sqlite3.Cursor):
    """A cursor that closes itself when its statement fails.

    It covers every method that runs a statement or steps one forward. A
    cursor closed this way refuses further use, as any closed cursor does.
    """

    execute = _closing(sqlite3.Cursor.execute)
    executemany = _closing(sqlite3.Cursor.executemany)
    executescript = _closing(sqlite3.Cursor.executescript)
    fetchone = _closing(sqlite3.Cursor.fetchone)
    fetchmany = _closing(sqlite3.Cursor.fetchmany)
    fetchall = _closing(sqlite3.Cursor.fetchall)


class ClosingConnection(sqlite3.Connection):
    """A connection whose every cursor is a ``ClosingCursor``.

    The three methods that run a statement on the connection itself make
    their cursor through ``cursor``. The standard ones make a plain cursor
    and would leave it open on a failure.
    """

    def cursor(self, factory: Callable[[sqlite3.Connection], Any] | None = None) -> Any:
        """Return a new cursor, a ``ClosingCursor`` unless ``factory`` names another class."""
        return super().cursor(ClosingCursor if factory is None else factory)

    def execute(self, *arguments: Any) -> Any:
        """Run one statement on a new cursor and return that cursor."""
        return self.cursor().execute(*arguments)

    def executemany(self, *arguments: Any) -> Any:
        """Run one statement once for each row of parameters on a new cursor and return that cursor."""
        return self.cursor().executemany(*arguments)

    def executescript(self, *arguments: Any) -> Any:
        """Run a script of statements on a new cursor and return that cursor."""
        return self.cursor().executescript(*arguments)
