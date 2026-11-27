"""The engine core: what any database needs, and nothing about a mount.

:class:`EngineCore` builds an engine from a URL and the engine arguments
it is given, makes every session that runs on it, and disposes it at
``close()``. An application may put listeners on the engine, and must
open no connection or session on it: beside a call on an in-memory
database, one costs the database. Construction binds nothing to a loop
and opens no connection, so a SQLite file is not made until first use.

The dialect is known once the engine is built, so its declared policy is
resolved at construction, with no IO. Facts SQLAlchemy models are read
from the dialect, never redeclared: the parameter budget is
``dialect.insertmanyvalues_max_parameters`` and transport-down
classification uses ``dialect.is_disconnect()``.

On SQLite the core takes over the start of a transaction: session
settings stamp every pool checkout, and an explicit ``BEGIN`` is sent at
transaction start instead of the driver's deferred implicit one, same
semantics, earlier lock acquisition for writers only. Each checkout
loads the vector extension unless the core is built with
``vector=False``. An attempt runs out of its cancelled caller's reach
(``attempts.py``), and a database that lives in one connection takes
turns and tells a subclass when a second connection, a new and empty
database, is opened.

The engine host of a mount is a subclass that adds the mount's tables,
its first touch and its planner statistics.

    core = EngineCore(url="sqlite+aiosqlite:///records.db", vector=False)
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any, Final, TypeVar

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from vfs.results import ErrorKind, ResultError, classified
from vfs.storage.backends.database.attempts import (
    AttemptSession,
    refuse_statements_of_marked_attempts,
    run_out_of_reach,
)
from vfs.storage.backends.database.dialects import (
    DialectProfile,
    StaleSnapshot,
    driver_origin,
    is_permanent_defect,
    is_retryable,
    is_value_too_large,
    membership_budget,
    profile_for,
)
from vfs.storage.backends.database.drivers import has_sqlite_vec, load_sqlite_vec, merge_engine_arguments
from vfs.storage.backends.database.oneconnection import SerializedSessions, rearm_on_fresh_connection

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from sqlalchemy import Engine
    from sqlalchemy.engine import URL, Dialect
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

T = TypeVar("T")

BEGIN_TAG: Final = "vfs_begin_tag"
"""The execution option whose text a SQLite transaction's ``BEGIN`` carries as a comment, told apart in a trace."""


# ---------------------------------------------------------------------------
# The statement that begins a SQLite transaction
# ---------------------------------------------------------------------------


def begin_statement(*, writer: bool, tag: str | None = None) -> str:
    """The ``BEGIN`` a SQLite transaction sends: ``IMMEDIATE`` for a writer, and *tag* as a comment."""
    mode = "BEGIN IMMEDIATE" if writer else "BEGIN"
    return f"{mode} /* {tag} */" if tag else mode


# ---------------------------------------------------------------------------
# The engine core
# ---------------------------------------------------------------------------


class EngineCore:
    """One database's connectivity and policy: the engine, its sessions, the retry, the classifier, the dispose.

    A subclass that keeps tables in a database held in one connection
    overrides ``_rearm``, which is called when that connection is replaced.
    """

    def __init__(
        self,
        *,
        url: str | URL,
        engine_arguments: Mapping[str, Any] | None = None,
        retry_attempts: int = 4,
        retry_base_delay: float = 0.05,
        vector: bool = True,
    ) -> None:
        # The engine is the core's own: an application puts listeners on it, and opens no connection or session.
        self.engine: AsyncEngine = create_async_engine(url, **merge_engine_arguments(url, engine_arguments))
        bind = self.engine.sync_engine
        # The declared policy and the live dialect it is read beside, both known with no IO.
        self._profile: DialectProfile = profile_for(bind.dialect.name)
        self._dialect: Dialect = bind.dialect
        sessions: Callable[[], AsyncSession]
        if self._profile.attempts_out_of_reach:
            # An attempt whose caller was cancelled is refused its next statement, its sessions and its commit.
            refuse_statements_of_marked_attempts(bind)
            sessions = async_sessionmaker(self.engine, expire_on_commit=False, sync_session_class=AttemptSession)
        else:
            sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        # One shared DBAPI connection cannot overlap transactions: calls
        # take turns, and a re-minted connection is told to the subclass.
        if isinstance(bind.pool, StaticPool):
            sessions = SerializedSessions(sessions)
            rearm_on_fresh_connection(bind, self._rearm)
        self.session_factory = sessions
        if self._profile.name == "sqlite":
            _install_sqlite_transaction_control(bind, self._profile, vector=vector)
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay

    @property
    def profile(self) -> DialectProfile:
        """Declared dialect policy, resolved from the engine's dialect at construction."""
        return self._profile

    @property
    def parameter_budget(self) -> int:
        """Bind params per statement — SQLAlchemy's own declared datum."""
        return self._dialect.insertmanyvalues_max_parameters

    @property
    def membership_budget(self) -> int:
        """Elements per ``IN``-list chunk under this dialect's budgets."""
        return membership_budget(self.profile, self.parameter_budget)

    async def with_retry(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run *fn*, restarting whole on a retryable outcome, with jittered backoff.

        A :class:`StaleSnapshot` is always retryable: a guard proved the
        snapshot stale, and a fresh attempt re-derives everything from
        current state. Exhaustion has one channel: it always leaves as
        :class:`StaleSnapshot` — the in-band signal as itself, a native
        serialization error wrapped as the cause — so every caller
        classifies both identically. Only non-retryable failures escape
        raw to the caller's classifier.

        Each wait is drawn uniformly between half the step and the whole
        step, the step doubling per attempt, so two rivals that collided
        do not retry in lockstep and collide again; the base delay bounds
        the longest wait the same as an unjittered schedule would.

        On SQLite each attempt runs in a task of its own. A caller that is
        cancelled waits for the attempt in hand, which ends the statement
        in flight or its wait for a connection, sends no other and is
        rolled back, and its own cancellation is raised then; ``attempts.py``
        has the reasons. Elsewhere an attempt runs in its caller's task.
        """
        step = self._retry_base_delay
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await (run_out_of_reach(fn) if self.profile.attempts_out_of_reach else fn())
            except (DBAPIError, StaleSnapshot) as exc:
                if not isinstance(exc, StaleSnapshot) and not is_retryable(self.profile, exc):
                    raise
                if attempt >= self._retry_attempts:
                    if isinstance(exc, StaleSnapshot):
                        raise
                    raise StaleSnapshot(f"a retryable engine conflict outlived {attempt} attempts") from exc
                await asyncio.sleep(random.uniform(step / 2, step))
                step *= 2
        raise AssertionError("unreachable")  # pragma: no cover

    def classify_failure(self, exc: BaseException, *, context: str) -> ResultError:
        """Classify a driver failure that escaped retry — always a Result, never a raise.

        A statement defect (syntax class) is a vfs bug, classified
        ``internal`` and never retryable — retrying a broken statement
        forever would disguise the bug as an operating condition.
        """
        origin = driver_origin(exc)
        try:
            # The runtime contract takes any driver exception; the stub's
            # `Error` type is the DBAPI module protocol, not a real class.
            disconnected = isinstance(origin, Exception) and self._dialect.is_disconnect(
                origin,  # ty: ignore[invalid-argument-type]
                None,
                None,
            )
        except Exception:
            disconnected = False
        if disconnected:
            return classified(ErrorKind.backend_unavailable, retryable=True, detail=f"{context} failed: {origin}")
        if is_value_too_large(exc):
            # The engine's own single-value cap, named by the engine: not a vfs ceiling.
            detail = f"{context} exceeded this engine's single-value limit: {origin}"
            return classified(ErrorKind.unsupported, detail=detail)
        if is_permanent_defect(exc):
            return classified(ErrorKind.internal, detail=f"{context} hit a permanent statement defect: {origin}")
        return classified(ErrorKind.unavailable, retryable=True, detail=f"{context} failed: {origin}")

    async def apply_file_settings(self) -> None:
        """Send the profile's database-file settings, outside any transaction; nothing when it declares none.

        A file's journal mode and page size cannot be set inside a
        transaction, so ``vfs_no_begin`` keeps the begin listener silent,
        and the driver is already in autocommit.
        """
        if not self._profile.file_settings:
            return
        async with self.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_no_begin": True})
            for statement in self._profile.file_settings:
                await conn.exec_driver_sql(statement)

    async def close(self) -> None:
        """Dispose the engine; every close releases what it holds now, so a second finds empty pools and does nothing.

        Nothing records teardown ahead of the awaited dispose returning,
        so a close cancelled mid-dispose leaves a retry that finishes
        the job.
        """
        await self.engine.dispose()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _rearm(self) -> None:
        """Told that a database in one connection opened a second, a new and empty one; a subclass makes its tables."""


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _install_sqlite_transaction_control(sync_engine: Engine, profile: DialectProfile, *, vector: bool) -> None:
    """Take over BEGIN emission and stamp session settings at checkout.

    The documented SQLAlchemy recipe: the driver's deferred implicit
    BEGIN is disabled so the begin event controls transaction start —
    writers (``vfs_writer`` execution option) get ``BEGIN IMMEDIATE``.
    Session settings are connection state applied at every pool checkout
    (op-session start), and with *vector* the extension is loaded there.
    """

    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(dbapi_connection, _record, _proxy) -> None:  # noqa: ANN001
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        # A connection already carrying the function skips the load.
        if vector and not has_sqlite_vec(cursor):
            load_sqlite_vec(dbapi_connection)
        for statement in profile.session_settings:
            cursor.execute(statement)
        cursor.close()

    @event.listens_for(sync_engine, "begin")
    def _on_begin(conn) -> None:  # noqa: ANN001
        options = conn.get_execution_options()
        if options.get("vfs_no_begin"):
            return
        conn.exec_driver_sql(begin_statement(writer=bool(options.get("vfs_writer")), tag=options.get(BEGIN_TAG)))
