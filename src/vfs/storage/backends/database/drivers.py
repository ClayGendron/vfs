"""What VFS asks of a database driver when it builds an engine from a URL.

``merge_engine_arguments`` gives the arguments for one URL: the ones the
application gave, and the ones VFS requires. Two drivers need something.
SQL Server through pyodbc needs its text binds left as Unicode. SQLite
needs its connections opened as ``ClosingConnection``, whose cursors
close themselves when a statement fails, and an in-memory SQLite
database needs to keep its one connection. No engine may autocommit.

    create_async_engine(url, **merge_engine_arguments(url, given))

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
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_AUTOCOMMIT = "AUTOCOMMIT"
_ONE_CONNECTION = "an in-memory database lives in its one connection"

# ---------------------------------------------------------------------------
# Engine arguments
# ---------------------------------------------------------------------------


def merge_engine_arguments(url: str, given: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the arguments for the engine of ``url``: what the application gave, and what VFS requires.

    An argument VFS has no stake in passes through as it was given: the
    pool's class and size, ``pool_pre_ping``, ``async_creator`` and the
    like. VFS requires a few, and puts each in. Where the application
    gives another value for one of them, a ``ValueError`` names it and
    says why, because a storage that dropped it in silence would corrupt
    text, leave files open or lose its database. ``connect_args`` is
    merged key by key, and the mapping that was given is not changed.

    No engine may autocommit. ``isolation_level`` set to ``AUTOCOMMIT``,
    on the engine or in its ``execution_options``, is refused on every
    dialect: a write is one transaction, and under autocommit each of
    its statements would commit alone.

    SQL Server needs ``use_setinputsizes`` false. SQLAlchemy's pyodbc
    dialect declares ``String`` binds as ANSI ``SQL_VARCHAR`` via
    setinputsizes, and the server squeezes those through the database
    codepage before they reach a UTF-8 column — mangling non-Latin1 to
    ``?``. Disabling setinputsizes restores pyodbc's Unicode default
    (``SQL_WVARCHAR``), whose conversion into the UTF-8 collation is
    lossless. pyodbc's ``fast_executemany`` is deliberately *not* set:
    engine-wide it rewrites UPDATE executemany, whose rowcount the
    guarded bumps verify, and as a bulk-insert mode it is still one RPC
    per row, slower than Core's pages on wide rows — SQL Server's bulk
    inserts take Core's pages.

    SQLite needs ``connect_args["factory"]`` to be ``ClosingConnection``.
    SQLAlchemy passes ``connect_args`` to its own connect call only, so
    an application that gives ``creator`` or ``async_creator`` opens the
    connections itself, and they are closing ones only if it makes them so.

    An in-memory SQLite database lives in its one connection, so its
    ``poolclass`` is ``StaticPool`` and its ``pool_recycle`` is ``-1``,
    which is never: any other pool, or a recycle, would open a second
    connection, and that is a new database with no table in it.
    """
    merged = dict(given or {})
    for within in (None, "execution_options"):
        options = merged if within is None else merged.get(within) or {}
        if str(options.get("isolation_level")).upper() == _AUTOCOMMIT:
            raise ValueError(
                f"{_named('isolation_level', within)} must not be {_AUTOCOMMIT!r}, because a write is one "
                "transaction, and under autocommit each statement commits alone and a failed write is left half done"
            )
    address = make_url(url)
    backend = address.get_backend_name()
    if backend == "mssql":
        _require(merged, "use_setinputsizes", False, "pyodbc then binds text as Unicode, and as ANSI it stores '?'")
    if backend == "sqlite":
        merged["connect_args"] = connect = dict(merged.get("connect_args") or {})
        _require(
            connect, "factory", ClosingConnection, "a cursor whose statement failed is closed at once", "connect_args"
        )
        # The dialect says which URLs name a database in memory: it gives those the pool of one connection.
        if address.get_dialect()().get_dialect_pool_class(address) is StaticPool:
            _require(merged, "poolclass", StaticPool, f"{_ONE_CONNECTION}, and another pool opens a second, empty one")
            _require(merged, "pool_recycle", -1, f"{_ONE_CONNECTION}, and a recycled connection is a new, empty one")
    return merged


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require(arguments: dict[str, Any], key: str, value: object, reason: str, within: str | None = None) -> None:
    """Put ``value`` at ``key`` of ``arguments``, or raise if the application gave it another value."""
    if arguments.setdefault(key, value) != value:
        raise ValueError(f"{_named(key, within)} must be {value!r}, because {reason}; VFS sets it, so leave it out")


def _named(key: str, within: str | None = None) -> str:
    """How an error names one engine argument, as the application wrote it."""
    return f"engine_arguments[{within!r}][{key!r}]" if within else f"engine_arguments[{key!r}]"
