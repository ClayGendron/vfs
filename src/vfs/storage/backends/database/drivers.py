"""What VFS asks of a database driver when it builds an engine from a URL.

``url_of_engine`` reads which dialect a URL names, for a storage that
serves only one. ``merge_engine_arguments`` gives the arguments for one
URL: the ones the application gave, and the ones VFS requires. One driver
needs something. SQLite needs its connections opened as
``ClosingConnection``, whose cursors close themselves when a statement
fails, and an in-memory SQLite database that SQLAlchemy gives one
connection needs to keep it. ``load_sqlite_vec`` loads the vector
extension into each SQLite connection that ``has_sqlite_vec`` finds
without it. No engine may autocommit.

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

import importlib.util
import sqlite3
from collections.abc import Mapping
from contextlib import suppress
from functools import wraps
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from sqlalchemy.util.concurrency import await_only

from vfs.storage.backends.database.dialects import SQLITE_VEC_PROBE

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import URL

_AUTOCOMMIT = "AUTOCOMMIT"
_ONE_CONNECTION = "an in-memory database lives in its one connection"

# Some system Pythons build sqlite3 without extension loading; the hook
# then loads nothing and first touch refuses with the reason.
_EXTENSIONS_LOADABLE = hasattr(sqlite3.Connection, "enable_load_extension")

# The extension's loadable file, located without importing the package
# (its ``__init__`` pulls numpy in when numpy is installed).
_SQLITE_VEC_SPEC = importlib.util.find_spec("sqlite_vec")
SQLITE_VEC_PATH: str | None = (
    str(next(iter(_SQLITE_VEC_SPEC.submodule_search_locations or ()), "") or "") + "/vec0"
    if _SQLITE_VEC_SPEC is not None and _SQLITE_VEC_SPEC.submodule_search_locations
    else None
)

# ---------------------------------------------------------------------------
# Engine URLs and arguments
# ---------------------------------------------------------------------------


def url_of_engine(url: str | URL, *, engine: str, storage: str) -> URL:
    """Return ``url`` parsed, when it names the ``engine`` dialect.

    ``storage`` is the name of the class that serves only that engine.
    A URL of any other dialect raises a ``ValueError`` that names both
    dialects and never the URL, which can hold a password. The check
    reads the URL alone, so it runs before any engine is built.
    """
    address = make_url(url)
    given = address.get_backend_name()
    if given != engine:
        raise ValueError(
            f"{storage} serves the {engine!r} dialect and was given a URL of {given!r}. DatabaseStorage serves any "
            "SQLAlchemy URL, SQLite's and Postgres's on their tuned profiles and any other dialect on the generic "
            "floor, and SQLiteStorage takes a path."
        )
    return address


def merge_engine_arguments(url: str | URL, given: Mapping[str, Any] | None = None) -> dict[str, Any]:
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

    SQLite needs ``connect_args["factory"]`` to be ``ClosingConnection``.
    SQLAlchemy passes ``connect_args`` to its own connect call only, so
    an application that gives ``creator`` or ``async_creator`` opens the
    connections itself, and they are closing ones only if it makes them so.

    An in-memory SQLite database lives in its one connection. Where
    SQLAlchemy itself gives the URL the pool of one connection, its
    ``poolclass`` is ``StaticPool``, its ``pool_recycle`` is ``-1``,
    which is never, and a ``pool`` made by the application is refused.
    Any other pool, or a recycle, would open a second connection, and
    that is a new database with no table in it. Two spellings are not
    covered. SQLAlchemy takes ``file::memory:?uri=true`` and
    ``file::memory:?cache=shared&uri=true`` for a file, so nothing is
    required of them, and another pool or a recycle there loses the
    database as it would on any in-memory URL.
    """
    merged = dict(given or {})
    for within in (None, "execution_options"):
        # Options that are no mapping hold no isolation level to refuse, and are SQLAlchemy's to refuse.
        options = merged if within is None else merged.get(within)
        if isinstance(options, Mapping) and str(options.get("isolation_level")).upper() == _AUTOCOMMIT:
            raise ValueError(
                f"{_named('isolation_level', within)} must not be {_AUTOCOMMIT!r}, because a write is one "
                "transaction, and under autocommit each statement commits alone and a failed write is left half done"
            )
    address = make_url(url)
    if address.get_backend_name() == "sqlite":
        merged["connect_args"] = connect = dict(merged.get("connect_args") or {})
        _require(
            connect, "factory", ClosingConnection, "a cursor whose statement failed is closed at once", "connect_args"
        )
        # The dialect says which URLs name a database in memory: it gives those the pool of one connection.
        if address.get_dialect()().get_dialect_pool_class(address) is StaticPool:
            if "pool" in merged:
                made = "VFS makes its pool, so leave it out"
                raise ValueError(f"{_named('pool')} must not be given, because {_ONE_CONNECTION}; {made}")
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
# The vector extension SQLite connections load
# ---------------------------------------------------------------------------


def load_sqlite_vec(dbapi_connection: Any) -> None:
    """Load the sqlite-vec extension into one DBAPI connection.

    The async adapter wraps an ``aiosqlite`` connection whose worker
    thread owns the real ``sqlite3`` handle, so the load is issued as
    that connection's own coroutines, awaited from the pool event's
    greenlet — the adapter's own pattern for ``create_function``. An
    interpreter without extension loading is left as it is; first touch
    probes and refuses with the reason.
    """
    inner = getattr(dbapi_connection, "_connection", None)
    if not _EXTENSIONS_LOADABLE or inner is None or SQLITE_VEC_PATH is None:
        return
    await_only(inner.enable_load_extension(True))
    try:
        await_only(inner.load_extension(SQLITE_VEC_PATH))
    finally:
        await_only(inner.enable_load_extension(False))


def has_sqlite_vec(cursor: Any) -> bool:
    """Whether one SQLite connection already answers the extension's version function, so it needs no load."""
    try:
        cursor.execute(SQLITE_VEC_PROBE)
    except sqlite3.OperationalError:
        return False
    cursor.fetchall()
    return True


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
