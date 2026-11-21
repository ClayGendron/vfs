"""Engine lifecycle — construction, first touch, retry, close.

:class:`EngineHost` owns one mount's database connectivity: it builds
the engine from a URL and the engine arguments it is given, makes every
session that runs on it, and disposes it at ``close()``. An application
may put listeners on the engine, and must open no connection or session
on it: beside a call on an in-memory database, one costs the database.
Construction binds nothing to a loop, so first touch may be on another.

The dialect is known once the engine is built, so its declared policy
is resolved at construction, with no IO. A dialect other than SQLite
and Postgres is served the generic floor, and the host logs one
``WARNING`` on this module's logger saying so. First touch is idempotent and
lazy, on the caller's loop: database-file settings, the profile's vector probe (the
cosine distance function is a precondition vfs proves and never
installs — sqlite-vec, pgvector), then — under the topology
serialization point (``BEGIN IMMEDIATE`` on SQLite via the installed
transaction control; a per-mount advisory lock on Postgres; a plain
transaction elsewhere, where the unique-violation arbitration is the
correctness backstop) — ``create_all`` and the schema-version row. An
existing row is verified: benign match serves and adopts the durable
mount identity; a mismatch refuses loudly as ``vfs.unavailable.schema``,
never PRAGMA/catalog sniffing.

Facts SQLAlchemy models are read from the dialect, never redeclared:
the parameter budget is ``dialect.insertmanyvalues_max_parameters`` and
transport-down classification uses ``dialect.is_disconnect()``. On
SQLite the host takes over the start of a transaction: session settings
stamp every pool checkout, and an explicit ``BEGIN`` is sent at
transaction start instead of the driver's deferred implicit one — same
semantics, earlier lock acquisition for writers only.

The host also owns SQLite's planner statistics, because without them the
planner assumes a million rows and ten per index key, and seeks the
tombstone index for every arm of a scoped glob. Each mutation detects,
inside the write lock it already holds, whether SQLite's own growth
listing names one of the mount's indexed tables; a crossing commit then
returns at once, and one host-tracked task takes the lock once more and
lands the statistics, uncapped, whatever happens to the caller. Pooled
connections of a database in a file replace themselves when the
statistics move; a connection to an in-memory database reloads at its
next write instead, because replacing the only connection to one would
drop it. ``close()`` interrupts a running pass rather than waiting on
it. Below SQLite 3.46 the listing depends on the connection's own query
history, so the step issues nothing there.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, TypeVar

from sqlalchemy import event, func, insert, inspect, select
from sqlalchemy.exc import DBAPIError, DisconnectionError, IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.util import greenlet_spawn
from ulid import ULID

from vfs.authority import EVERYONE_NAME
from vfs.models import encoded_at_creation
from vfs.models.rows import SCHEMA_FORMAT_VERSION, build_vfs_tables
from vfs.models.vector import NativeEmbeddingConfig
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.storage.backends.database.attempts import (
    AttemptSession,
    refuse_statements_of_marked_attempts,
    run_out_of_reach,
)
from vfs.storage.backends.database.dialects import (
    PROFILES,
    DialectProfile,
    StaleSnapshot,
    VectorFunction,
    driver_origin,
    is_insufficient_privilege,
    is_permanent_defect,
    is_retryable,
    is_value_too_large,
    membership_budget,
    profile_for,
    topology_execution_options,
)
from vfs.storage.backends.database.drivers import has_sqlite_vec, load_sqlite_vec, merge_engine_arguments
from vfs.storage.backends.database.oneconnection import SerializedSessions, rearm_on_fresh_connection
from vfs.storage.backends.database.rights import posture_row
from vfs.storage.grants import LEVEL_RANK

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from sqlalchemy import Engine
    from sqlalchemy.engine import URL, Connection, Dialect
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
    from sqlalchemy.pool import Pool, PoolProxiedConnection

    from vfs.embedding import EmbeddingProvider
    from vfs.models.rows import VFSTables
    from vfs.storage.grants import Posture

T = TypeVar("T")

_log: Final = logging.getLogger(__name__)

# The one warning a storage logs when it is built on a dialect no tuned profile serves.
_UNSUPPORTED_DIALECT: Final = (
    "vfs does not support the %r SQL dialect: it is served the generic floor, without search,"
    " and is fit for testing only. vfs supports SQLite and Postgres."
)

STATISTICS_NAME = "vfs_statistics"
"""The statistics step's one name: the detection savepoint, the pass's begin tag and option, the record key."""

STATISTICS_CLEAR = f"SELECT 1 /* {STATISTICS_NAME} */"
"""The statement a cancelled pass starts after its last interrupt, which is what clears a pending one."""

STATISTICS_FINGERPRINT = (
    "SELECT group_concat(tbl || ' ' || coalesce(idx, '') || ' ' || stat, ';') FROM {schema}.sqlite_stat1"
)
"""The identity of the statistics a connection plans from; a missing table reads as the empty fingerprint."""

STATISTICS_VERSION = (3, 46)
"""The first SQLite whose growth listing checks every table instead of the ones this connection planned."""

# A connection record that has recorded no fingerprint yet: fresh, so its first statement loaded the file's.
_FRESH = object()


def advisory_key(text: str) -> int:
    """Stable signed-64 advisory-lock key derived from *text*.

    Every rival instance hashing the same handle — the durable mount
    identity once adopted, the schema-qualified table name before it exists —
    lands on the same key, and the signed range is what Postgres's
    ``pg_advisory_xact_lock(bigint)`` accepts.
    """
    digest = hashlib.blake2b(text.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class _AnalysisPass:
    """One analysis pass's handles for the task that owns it: the driver connection, its pool, and an interrupt."""

    __slots__ = ("driver", "interrupted", "pool")

    def __init__(self) -> None:
        self.driver: Any | None = None
        self.pool: Pool | None = None
        self.interrupted = False


class EngineHost:
    """One mount's connectivity, tables, dialect policy, and first-touch state."""

    def __init__(
        self,
        *,
        url: str | URL,
        engine_arguments: Mapping[str, Any] | None = None,
        schema: str | None = None,
        embedder: EmbeddingProvider | None = None,
        native_embedding: NativeEmbeddingConfig | None = None,
        posture: Posture = "read_write",
        retry_attempts: int = 4,
        retry_base_delay: float = 0.05,
    ) -> None:
        if embedder is not None and native_embedding is not None and embedder.dimension != native_embedding.dimension:
            raise ValueError(
                f"native_embedding declares a {native_embedding.dimension}-wide column but the embedder "
                f"{embedder.model_id!r} produces {embedder.dimension}-wide vectors"
            )
        # An embedder fixes the space's width, and a fixed width is what the
        # engines' own vector columns need: the native column follows.
        if embedder is not None and native_embedding is None:
            native_embedding = NativeEmbeddingConfig(dimension=embedder.dimension)
        self.tables: VFSTables = build_vfs_tables(schema=schema, native_embedding=native_embedding)
        self.embedder = embedder
        self.native_embedding = native_embedding
        # What everyone holds at the root of a freshly provisioned mount;
        # an existing mount keeps its stored posture.
        self.posture: Posture = posture
        # The space the stored vectors live in, adopted at first touch and
        # moved by the embed step; ``None`` until the first embedding lands.
        self.embedding_identity: tuple[str, int] | None = None
        # The distance function's version where the profile's probe reports
        # one (pgvector's, sqlite-vec's); the ANN tier's iterative-scan gate.
        self.vector_version: tuple[int, ...] | None = None
        # The engine is the host's own: an application puts listeners on it, and opens no connection or session.
        self.engine: AsyncEngine = create_async_engine(url, **merge_engine_arguments(url, engine_arguments))
        bind = self.engine.sync_engine
        # The declared policy and the live dialect it is read beside, both known with no IO.
        self._profile: DialectProfile = profile_for(bind.dialect.name)
        self._dialect: Dialect = bind.dialect
        if self._profile.name not in PROFILES:
            _log.warning(_UNSUPPORTED_DIALECT, self._profile.name)
        sessions: Callable[[], AsyncSession]
        if self._profile.attempts_out_of_reach:
            # An attempt whose caller was cancelled is refused its next statement, its sessions and its commit.
            refuse_statements_of_marked_attempts(bind)
            sessions = async_sessionmaker(self.engine, expire_on_commit=False, sync_session_class=AttemptSession)
        else:
            sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        # One shared DBAPI connection cannot overlap transactions: ops
        # take turns, and a re-minted connection re-arms first touch.
        if isinstance(bind.pool, StaticPool):
            sessions = SerializedSessions(sessions)
            rearm_on_fresh_connection(bind, self._rearm)
        self.session_factory = sessions
        if self._profile.name == "sqlite":
            _install_sqlite_transaction_control(bind, self._profile)
        # Before first touch the schema-qualified table name is the handle,
        # so mounts in two schemas never share the provisioning lock.
        self._table_key = advisory_key(self.tables.entry.fullname)
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self.mount_identity: str | None = None
        self._ready = False
        # Created lazily on the caller's loop — construction must stay
        # loop-free so construct-here, first-touch-elsewhere works.
        self._lock: asyncio.Lock | None = None
        # Whether the database lives in memory, read once at first touch; a
        # connection to one is never replaced, whatever pool holds it.
        self.in_memory: bool | None = None
        # The one analysis task, kept after it ends so a test can see one ran;
        # ``_again`` asks a running task for one more pass once it finishes.
        self._analysis: asyncio.Task[None] | None = None
        self._again = False
        # Facts about the store's health found by work that outlived the call
        # that started it, each carried once by the next public mutating verb.
        self._advisories: list[ResultError] = []
        # Which own tables carry an index, read once per table per host; and
        # whether this host's checkout listener replaces stale connections.
        self._indexed: dict[str, bool] = {}
        self._replaces = self._profile.statistics_listing is not None
        if self._replaces:
            event.listen(bind, "checkout", self._replace_stale)

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

    @property
    def embedding_stale(self) -> bool:
        """Whether the stored vectors belong to a space other than the configured embedder's.

        ``False`` with no embedder or no stored identity: nothing to
        compare. A stale space is served lexical-only and migrated by
        the next ``rebuild``.
        """
        if self.embedder is None or self.embedding_identity is None:
            return False
        return self.embedding_identity != (self.embedder.model_id, self.embedder.dimension)

    @property
    def statistics_enabled(self) -> bool:
        """Whether this engine runs the planner-statistics step: a declared listing on SQLite 3.46 or later.

        The version is SQLAlchemy's own fact, set by its first-connect
        handler before any checkout, so it is read after a connection
        exists. Below 3.46 the listing names only the tables this
        connection's planner used, at 25x, so the step would depend on
        which pooled connection served it; there vfs issues nothing.
        """
        version = self._dialect.server_version_info
        listed = self._profile.statistics_listing is not None
        return listed and version is not None and tuple(version) >= STATISTICS_VERSION

    async def ensure_ready(self) -> ResultError | None:
        """Idempotent first touch; ``None`` when the mount is serving."""
        if self._ready:
            return None
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._ready:
                return None
            try:
                return await self.with_retry(self._first_touch)
            except StaleSnapshot as exc:
                detail = f"first touch kept losing to concurrent changes: {exc.context}"
                return classified(ErrorKind.conflict, retryable=True, detail=detail)
            except (SQLAlchemyError, OSError) as exc:
                # SQLAlchemyError, not just DBAPIError: pool exhaustion
                # (TimeoutError) is an operating condition, never a raise.
                return self.classify_failure(exc, context="First touch")

    async def install_extensions(self) -> ResultError | None:
        """Install what the dialect requires and this role may, then prove it; ``None`` when the mount can serve.

        The explicit half of the precondition: first touch only proves
        the distance function, and this verb — never called by first
        touch — runs the profile's install statement for a developer who
        chooses to do that work from code. Nothing declared is a success
        with nothing to do. The statement's own ``IF NOT EXISTS`` race
        (a rival mount installing first) is benign and recovered via
        savepoint; a role that may not install is answered
        ``permission_denied`` naming the fix, and any other failure,
        from the install or the probe, classifies as first touch's would.
        A caller that is cancelled waits as ``with_retry`` says it does.
        """
        function = self._profile.vector_function
        if function is None:
            return None

        async def install() -> ResultError | None:
            if function.install is not None:
                await self._install_vector_function(function.install)
            return await self._probe_vector_function(function)

        try:
            return await (run_out_of_reach(install) if self.profile.attempts_out_of_reach else install())
        except DBAPIError as exc:
            origin = driver_origin(exc)
            if is_insufficient_privilege(origin):
                detail = f"this role may not install the extension ({origin}); {function.missing}"
                return classified(ErrorKind.permission_denied, detail=detail)
            return self.classify_failure(exc, context="Install extensions")

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

    # -------------------------------------------------------------------
    # Planner statistics — detect inside the write, analyze in one tracked pass
    # -------------------------------------------------------------------

    async def detect_due(self, conn: AsyncConnection) -> frozenset[str] | ResultError:
        """The mount's indexed tables SQLite's growth listing names on *conn*, inside the caller's own transaction.

        Runs under a savepoint after the batch succeeded and before the
        commit, so it adds no lock acquisition: the attempt already
        holds the write lock, and the listing, which takes the lock,
        is free there. It sees the transaction's own rows, so the sizes
        it judges are the sizes the commit leaves. On a connection the
        replacement listener does not cover, an in-memory store's, it
        first reloads the statistics from the file when they moved,
        which is free under the lock too. Only the
        tables with an index are due: an index-less table gives the
        planner nothing to choose between, and the three such tables
        are named on every commit. Nothing is analyzed here. A driver
        failure rolls back to the savepoint, the mutation commits, and
        the failure is held as an advisory for the next public verb.
        """
        statement = f"SAVEPOINT {STATISTICS_NAME}"
        await conn.exec_driver_sql(statement)
        try:
            if not self._replaces:
                await self._reload_if_moved(conn)
            statement = self._listing()
            listed = [str(row[0]) for row in (await conn.exec_driver_sql(statement)).all()]
            own = self._own_statements()
            due: list[str] = []
            for listed_statement in listed:
                table = own.get(listed_statement)
                if table is not None and await self._has_index(conn, table):
                    due.append(table)
            statement = f"RELEASE {STATISTICS_NAME}"
            await conn.exec_driver_sql(statement)
        except (SQLAlchemyError, OSError) as exc:
            await conn.exec_driver_sql(f"ROLLBACK TO {STATISTICS_NAME}")
            await conn.exec_driver_sql(f"RELEASE {STATISTICS_NAME}")
            detail = (
                f"the planner-statistics detection inside a write failed at {_failed_statement(exc, statement)!r}: "
                f"{driver_origin(exc)}; the write is committed and the next write detects again"
            )
            advisory = classified(ErrorKind.unavailable, severity=Severity.warning, detail=detail)
            self._advisories.append(advisory)
            return advisory
        return frozenset(due)

    def request_analysis(self) -> None:
        """Start the host's one analysis task, or ask the running one for one more pass once it finishes.

        The task is the host's, not the caller's: a caller's cancellation
        or deadline never reaches it, so a crossing's statistics land
        once whatever happens to the write that found it. Crossings
        requested while a pass runs coalesce into one more pass, which
        re-lists under its own lock and analyzes only what is still due.
        """
        if self._analysis is not None and not self._analysis.done():
            self._again = True
            return
        self._again = False
        self._analysis = asyncio.create_task(self._analyze(), name=STATISTICS_NAME)

    async def settle_statistics(self) -> None:
        """Wait for every analysis pass in flight to end; what a test awaits before it counts a pass's work."""
        while (task := self._analysis) is not None and not task.done():
            await asyncio.wait({task})

    async def stop_analysis(self) -> None:
        """Cancel the analysis task and await only its end, which its interrupt makes a rollback's length.

        The wait is shielded: a caller whose own timeout fires, the
        router's bounded close, is cancelled alone, and the pass task
        keeps interrupting its statement until the inner task ends. A
        cancel forwarded into the pass would end that loop early and
        leave the inner task alive to commit on a disposed engine.
        """
        task = self._analysis
        if task is None or task.done():
            return
        task.cancel()
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise

    def take_advisories(self, result: Result) -> Result:
        """*result* with every held advisory appended, once, for a public mutating verb at its return.

        An advisory is a fact about the store's health found by work
        that outlived the call that started it: today a failed
        planner-statistics pass or detection. The caller whose write
        asked for that work has already returned, so the warning rides
        on a later public write to the same host, whoever's it is; it
        names no path, principal or body and is not retryable, because
        nothing in that call is to be retried. Only the public runners
        call this: an internal commit's Result discards its errors, and
        a held fact must never vanish that way.
        """
        if not self._advisories:
            return result
        held, self._advisories = self._advisories, []
        extras = result.model_extra or {}
        return Result(ops=result.ops, observations=result.observations, errors=[*result.errors, *held], **extras)

    async def close(self) -> None:
        """Dispose the engine; every close releases.

        No close is one-shot: verbs revive after close and re-mint
        pools and connections, so each close releases whatever the
        host holds *now*. Idempotence is by cheapness — a second close
        finds empty pools and does nothing — never by flag, matching
        the pools underneath; and nothing records teardown ahead of
        the awaited dispose returning, so a close cancelled mid-dispose
        leaves a retry that finishes the job.

        Background work never holds close hostage. A running analysis
        pass is interrupted, not awaited: its cancellation handler stops
        the statement through the driver's thread-safe interrupt, SQLite
        rolls the pass back, and close awaits only that end, about a
        millisecond. Two exceptions. A pass still waiting in SQLite's
        busy handler for its ``BEGIN IMMEDIATE`` cannot be interrupted,
        so a close that lands then can wait up to one ``busy_timeout``
        (5 s) before the pass ends; a caller whose own timeout fires
        first leaves the pass to end on its own, still interrupted, and
        it never commits. And the handler's last statement runs on the
        pass's connection once the pool has it back, so a verb that drew
        that connection in the instant before the handler woke is ahead
        of it on the driver's one thread: close then waits for that
        verb's one statement, a ``busy_timeout`` at most when it is a
        ``BEGIN IMMEDIATE``, and a router's ``close_timeout`` bounds the
        wait above that. An interrupted pass loses only its statistics;
        the table stays due and the next write asks again. The dispose
        below runs either way, in a ``finally``, and the pass leaves no
        interrupt pending on a connection it closes: one would stop
        SQLite's last close from folding the log in and deleting it. A
        pass a close cut short leaves running closes its own connection.
        """
        try:
            await self.stop_analysis()
        finally:
            # The ready latch falls with its connectivity: the next op re-runs
            # the idempotent first touch instead of serving off a stale latch.
            self._ready = False
            await self.engine.dispose()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _rearm(self) -> None:
        """Make the next call provision the schema again."""
        self._ready = False

    async def _first_touch(self) -> ResultError | None:
        profile = self._profile
        if profile.file_settings:
            await self._apply_file_settings(profile)
        if profile.statistics_listing is not None:
            self.in_memory = await self._read_in_memory()
            if self._replaces and (self.in_memory or not self.statistics_enabled):
                event.remove(self.engine.sync_engine, "checkout", self._replace_stale)
                self._replaces = False
        if profile.vector_function is not None:
            refusal = await self._probe_vector_function(profile.vector_function)
            if refusal is not None:
                return refusal
        refusal = await self._verify_or_provision()
        if refusal is None:
            self._ready = True
        return refusal

    async def _apply_file_settings(self, profile: DialectProfile) -> None:
        # Database-file state (WAL, page_size) cannot run inside a
        # transaction; vfs_no_begin keeps the begin listener silent, and
        # the driver is already in autocommit (isolation_level=None).
        async with self.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_no_begin": True})
            for statement in profile.file_settings:
                await conn.exec_driver_sql(statement)

    async def _install_vector_function(self, install: str) -> None:
        """Run the profile's install statement once, under a savepoint so a rival's earlier install is benign."""
        async with self.session_factory() as session:
            conn = await session.connection()
            try:
                async with conn.begin_nested():
                    await conn.exec_driver_sql(install)
            except IntegrityError:
                pass
            await session.commit()

    async def _probe_vector_function(self, function: VectorFunction) -> ResultError | None:
        """Prove the engine's cosine distance function is present; refuse the mount naming the fix when it is not.

        The function is a precondition first touch never installs:
        sqlite-vec rides every connection but an interpreter built
        without extension loading drops it silently at the hook, and
        pgvector is installed once by a superuser or through the explicit
        install verb. The probe fails when the engine answers no row or
        raises a permanent error — SQLite's "no such function" carries
        only the generic result code, so no engine-neutral code names
        the missing function itself; a scalar answer is the function's
        version, kept for the tiers that gate on it. A raise the retry
        policy would restart, or one that cost the connection, is not a
        verdict on the function and propagates to the caller's retry
        and classifier, so a busy or dropped engine is never reported
        as a missing extension.
        """
        async with self.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_no_begin": True})
            try:
                raw = (await conn.exec_driver_sql(function.probe)).scalar_one_or_none()
            except DBAPIError as exc:
                if exc.connection_invalidated or is_retryable(self.profile, exc):
                    raise
                raw = None
        if raw is None:
            return classified(ErrorKind.unavailable, detail=function.missing)
        self.vector_version = _version_tuple(str(raw))
        return None

    async def _verify_or_provision(self) -> ResultError | None:
        meta = self.tables.meta
        version_and_identity = select(
            meta.c.schema_format_version, meta.c.mount_identity, meta.c.embedding_model, meta.c.embedding_dimension
        )
        async with self.session_factory() as session:
            # First touch is a topology mutation: writer marker (SQLite's
            # BEGIN IMMEDIATE) plus the declared topology-isolation pin.
            conn = await session.connection(execution_options=topology_execution_options(self.profile))
            await self._serialization_point(conn)
            # An existing mount is verified, never repaired: its meta row is
            # the contract. A fresh one is provisioned, DDL joining the
            # serialized transaction where the engine keeps DDL transactional.
            if not await conn.run_sync(self._has_meta_table):
                await conn.run_sync(self.tables.metadata.create_all, checkfirst=True)
            row = (await conn.execute(version_and_identity)).one_or_none()
            if row is None:
                try:
                    # Designed race: a rival's first touch winning here is a
                    # benign already-provisioned outcome, recovered via savepoint.
                    async with conn.begin_nested():
                        await self._provision(conn)
                except IntegrityError:
                    pass
                row = (await conn.execute(version_and_identity)).one_or_none()
            if row is None:
                # The unique violation was NOT the designed meta race: rows
                # conflict with provisioning yet no schema-version row exists.
                outcome: ResultError | None = classified(
                    ErrorKind.unavailable,
                    detail=(
                        "the database is inconsistently provisioned: existing rows conflict with "
                        "first touch but no schema-version row is present; repair or re-provision the mount"
                    ),
                )
            else:
                outcome = self._adopt(row)
            await session.commit()
            return outcome

    async def _provision(self, conn: AsyncConnection) -> None:
        now = datetime.now(UTC)
        await conn.execute(
            insert(self.tables.meta).values(
                id=1,
                schema_format_version=SCHEMA_FORMAT_VERSION,
                mount_identity=str(ULID()),
                grant_revision=0,
                created_at=now,
            )
        )
        await conn.execute(insert(self.tables.index_state).values(id=1))
        await conn.execute(insert(self.tables.lock).values(id=1))
        await conn.execute(insert(self.tables.grants).values(**posture_row(self.posture, now)))
        await conn.execute(insert(self.tables.principal_revisions).values(principal_id=EVERYONE_NAME, revision=0))
        await conn.execute(
            insert(self.tables.entry).values(
                entry_id=str(ULID()),
                parent_id=None,
                path="/",
                # "/" is un-typable as a segment name; an engine that folds '' to
                # NULL would see the NOT NULL name column rightly refuse it.
                name="/",
                kind="directory",
                version=1,
                # The root is created as every other directory is.
                encoded=encoded_at_creation("directory"),
                everyone_level=LEVEL_RANK[self.posture],
                created_at=now,
                updated_at=now,
            )
        )

    async def _serialization_point(self, conn: AsyncConnection) -> None:
        # SQLite serializes via the writer BEGIN IMMEDIATE the listener
        # already emitted; engines without a declared point rely on the
        # unique-violation arbitration.
        if self.profile.name == "postgresql":
            await conn.execute(select(func.pg_advisory_xact_lock(self._table_key)))

    def _has_meta_table(self, connection: Connection) -> bool:
        meta = self.tables.meta
        return inspect(connection).has_table(meta.name, schema=meta.schema)

    async def _read_in_memory(self) -> bool:
        """Whether the mount's schema is held in memory: ``database_list`` gives it an empty file name.

        Keyed on the database, never the pool class: a queue pool holds
        ``file::memory:?cache=shared`` too, and replacing the last
        connection to any in-memory database drops it.
        """
        schema = self.tables.entry.schema or "main"
        async with self.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_no_begin": True})
            rows = (await conn.exec_driver_sql(f"PRAGMA {self._statistics_schema()}.database_list")).all()
        return any(str(row[1]) == schema and not row[2] for row in rows)

    def _statistics_schema(self) -> str:
        """The quoted schema the mount's tables live in, as SQLite's own listing spells it."""
        quote = self._dialect.identifier_preparer.quote_identifier
        return quote(self.tables.entry.schema or "main")

    def _listing(self) -> str:
        listing = self.profile.statistics_listing
        assert listing is not None
        return listing.format(schema=self._statistics_schema())

    def _own_statements(self) -> dict[str, str]:
        """Each own table's ``ANALYZE`` statement as SQLite prints it, so a listed statement compares whole.

        The database can hold tables that are not the mount's, and
        the listing names every due table in the schema;
        comparing whole statements built with the dialect's own quoting
        acts on the mount's tables and nothing else, with no parsing.
        """
        quote = self._dialect.identifier_preparer.quote_identifier
        schema = self._statistics_schema()
        return {f"ANALYZE {schema}.{quote(table.name)}": table.name for table in self.tables.metadata.tables.values()}

    async def _has_index(self, conn: AsyncConnection, table: str) -> bool:
        cached = self._indexed.get(table)
        if cached is None:
            quote = self._dialect.identifier_preparer.quote_identifier
            rows = (await conn.exec_driver_sql(f"PRAGMA {self._statistics_schema()}.index_list({quote(table)})")).all()
            cached = self._indexed[table] = bool(rows)
        return cached

    def _fingerprint_statement(self) -> str:
        """The one statement that reads the statistics fingerprint, for the read and for naming it in an advisory."""
        return STATISTICS_FINGERPRINT.format(schema=self._statistics_schema())

    async def _fingerprint(self, conn: AsyncConnection) -> str:
        try:
            value = (await conn.exec_driver_sql(self._fingerprint_statement())).scalar()
        except OperationalError as exc:
            if "sqlite_stat1" not in str(exc):
                raise
            return ""
        return str(value or "")

    async def _reload_if_moved(self, conn: AsyncConnection) -> None:
        """Bring *conn*'s in-memory statistics back to the file's when the fingerprint moved, inside its lock.

        A later ``ANALYZE`` changes no schema, so an open connection
        never reloads the statistics on its own; ``ANALYZE`` of the
        schema table does, and is free under a write lock already held.
        A record with no fingerprint yet reloads too when the file holds
        statistics, since the connection may have been opened before them.
        """
        info = _record_of(conn).info
        fingerprint = await self._fingerprint(conn)
        recorded = info.get(STATISTICS_NAME, _FRESH)
        moved = fingerprint != "" if recorded is _FRESH else recorded != fingerprint
        if moved:
            await conn.exec_driver_sql(f"ANALYZE {self._statistics_schema()}.sqlite_schema")
        info[STATISTICS_NAME] = fingerprint

    def _replace_stale(self, dbapi_connection: Any, record: Any, _proxy: Any) -> None:
        """The checkout listener of a database in a file: replace a connection whose statistics moved.

        A lock-free read of the fingerprint, compared with the one the
        record recorded when the connection last loaded statistics;
        a stale or unknown connection is discarded through SQLAlchemy's
        own checkout pattern, ``DisconnectionError``, and the pool hands
        out a fresh one that loads the file's statistics with its first
        statement. A fresh record only records. A fingerprint read that
        fails leaves the connection in service and marks it unknown, so
        the next checkout replaces it; the checkout itself never fails
        here. Nothing is replaced before first touch has read whether
        the database is in memory, or when the step is off.
        """
        if self.in_memory is not False or not self.statistics_enabled:
            return
        recorded = record.info.get(STATISTICS_NAME, _FRESH)
        if recorded is None:
            raise DisconnectionError("the connection's planner statistics are unknown")
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(self._fingerprint_statement())
            row = cursor.fetchone()
            fingerprint = str((row[0] if row else None) or "")
        except sqlite3.Error as exc:
            if "sqlite_stat1" not in str(exc):
                record.info[STATISTICS_NAME] = None
                return
            fingerprint = ""
        finally:
            cursor.close()
        if recorded is not _FRESH and recorded != fingerprint:
            raise DisconnectionError("the file's planner statistics moved since this connection loaded them")
        record.info[STATISTICS_NAME] = fingerprint

    async def _analyze(self) -> None:
        """The analysis task: one pass at a time while a crossing was requested during the last."""
        while True:
            self._again = False
            await self._analysis_pass()
            if not self._again:
                return

    async def _analysis_pass(self) -> None:
        """One pass, its SQL in a task of its own, so a cancellation reaches the driver before it reaches SQLAlchemy.

        A cancellation alone does not stop a running statement: the
        driver's thread runs it to its end and holds the write lock
        meanwhile. Worse, SQLAlchemy treats a cancellation inside a
        statement as an exit, invalidates the connection, and the
        driver's graceful close then waits for that statement to end.
        So the transaction runs in an inner task this task never
        cancels. When this task is cancelled it interrupts the driver,
        every millisecond until the inner task ends (the first interrupt
        can land before the statement has started), then starts one
        statement there, and only then re-raises: SQLite keeps an
        interrupt that finds nothing running until a statement starts,
        and the last close's checkpoint would honour it and leave the
        log behind. The interrupted statement fails inside the inner task
        with the driver's own error, which rolls the pass back as any
        failure would, without holding an advisory. No awaiter forwards
        a second cancellation into this loop (:meth:`stop_analysis`
        shields its wait), so the loop always outlives the inner task.

        A close cut short by its caller replaces the pool under a running
        pass, and nothing else closes the one the pass returns to, so the
        pass disposes it once its last statement has run.
        """
        state = _AnalysisPass()
        inner = asyncio.create_task(self._analysis_transaction(state), name=f"{STATISTICS_NAME}-pass")
        try:
            await asyncio.shield(inner)
        except asyncio.CancelledError:
            state.interrupted = True
            while not inner.done():
                if state.driver is not None:
                    with suppress(sqlite3.Error, ValueError):
                        await state.driver.interrupt()
                await asyncio.sleep(0.001)
            if state.driver is not None:
                with suppress(sqlite3.Error, ValueError):
                    cursor = await state.driver.execute(STATISTICS_CLEAR)
                    await cursor.close()
            raise
        finally:
            if state.pool is not None and state.pool is not self.engine.sync_engine.pool:
                await greenlet_spawn(state.pool.dispose)

    async def _analysis_transaction(self, state: _AnalysisPass) -> None:
        """One analysis transaction: the lock once, a reload if the fingerprint moved, the listing, the due analyses.

        Passes serialize on the write lock across hosts and processes;
        the one that runs second finds the fingerprint moved, reloads,
        and its re-listing names nothing, so a crossing is analyzed once
        however many writers detected it. A driver failure rolls the
        pass back, leaves the table due and the connection's fingerprint
        unknown, and is held as an advisory for the next public verb,
        unless the owning task interrupted the pass on purpose.
        """
        statement = f"BEGIN IMMEDIATE /* {STATISTICS_NAME} */"
        pooled: PoolProxiedConnection | None = None
        try:
            async with self.session_factory() as session:
                state.pool = self.engine.sync_engine.pool
                conn = await session.connection(execution_options={"vfs_writer": True, STATISTICS_NAME: True})
                pooled = _record_of(conn)
                state.driver = pooled.dbapi_connection._connection  # ty: ignore[unresolved-attribute]
                await self._reload_if_moved(conn)
                statement = self._listing()
                listed = [str(row[0]) for row in (await conn.exec_driver_sql(statement)).all()]
                own = self._own_statements()
                for statement in listed:
                    table = own.get(statement)
                    if table is not None and await self._has_index(conn, table):
                        await conn.exec_driver_sql(statement)
                pooled.info[STATISTICS_NAME] = await self._fingerprint(conn)
                statement = "COMMIT"
                await session.commit()
        except (SQLAlchemyError, OSError) as exc:
            if pooled is not None:
                pooled.info[STATISTICS_NAME] = None
            if state.interrupted:
                return
            failed = _failed_statement(exc, statement)
            detail = (
                f"a background planner-statistics pass after an earlier write failed at {failed!r}: "
                f"{driver_origin(exc)}; that write is committed, this call is unaffected, and the next crossing "
                "write retries the pass"
            )
            self._advisories.append(classified(ErrorKind.unavailable, severity=Severity.warning, detail=detail))

    def _adopt(self, row: Any) -> ResultError | None:
        """Verify the meta row and adopt its identities; a refusal names the mismatch.

        A stored embedding space of another width than a **native**
        column refuses outright: the column physically cannot hold the
        configured vectors, and the fix is DDL, out of every verb's
        reach. A stored *model* mismatch is not refused here — the
        vector leg declines it per call and ``rebuild`` migrates.
        """
        if row.schema_format_version != SCHEMA_FORMAT_VERSION:
            return classified(
                ErrorKind.schema_mismatch,
                detail=(
                    f"the database schema format is {row.schema_format_version}; this build expects "
                    f"{SCHEMA_FORMAT_VERSION}; re-provision the mount"
                ),
                data={"found": row.schema_format_version, "expected": SCHEMA_FORMAT_VERSION},
            )
        stored = (
            (row.embedding_model, row.embedding_dimension)
            if row.embedding_model is not None and row.embedding_dimension is not None
            else None
        )
        native = self.native_embedding
        if stored is not None and native is not None and stored[1] != native.dimension:
            return classified(
                ErrorKind.invalid,
                detail=(
                    f"the mount's native vector column is {native.dimension} wide but its stored embeddings "
                    f"are {stored[0]!r} at {stored[1]}; re-provision the mount or restore the matching embedder"
                ),
            )
        self.mount_identity = row.mount_identity
        self.embedding_identity = stored
        return None


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _install_sqlite_transaction_control(sync_engine: Engine, profile: DialectProfile) -> None:
    """Take over BEGIN emission and stamp session settings at checkout.

    The documented SQLAlchemy recipe: the driver's deferred implicit
    BEGIN is disabled so the begin event controls transaction start —
    writers (``vfs_writer`` execution option) get ``BEGIN IMMEDIATE``.
    Session settings are connection state applied at every pool checkout
    (op-session start).
    """

    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(dbapi_connection, _record, _proxy) -> None:  # noqa: ANN001
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        # A connection already carrying the function skips the load.
        if not has_sqlite_vec(cursor):
            load_sqlite_vec(dbapi_connection)
        for statement in profile.session_settings:
            cursor.execute(statement)
        cursor.close()

    @event.listens_for(sync_engine, "begin")
    def _on_begin(conn) -> None:  # noqa: ANN001
        options = conn.get_execution_options()
        if options.get("vfs_no_begin"):
            return
        mode = "BEGIN IMMEDIATE" if options.get("vfs_writer") else "BEGIN"
        if options.get(STATISTICS_NAME):
            # The analysis pass's own transaction, told apart from a verb's in any statement trace.
            mode = f"{mode} /* {STATISTICS_NAME} */"
        conn.exec_driver_sql(mode)


def _record_of(conn: AsyncConnection) -> PoolProxiedConnection:
    """The pooled connection behind *conn*, whose ``info`` records the statistics it plans from."""
    sync_connection = conn.sync_connection
    assert sync_connection is not None
    return sync_connection.connection


def _failed_statement(exc: BaseException, fallback: str) -> str:
    """The SQL that failed, from SQLAlchemy's own record of it when the error carries one, else *fallback*.

    A statement error names the statement it ran, rewritten or not, so an
    advisory never names a statement vfs did not issue; an ``OSError`` has
    no such record and the caller's last-known statement stands in.
    """
    statement = getattr(exc, "statement", None)
    return fallback if statement is None else str(statement)


def _version_tuple(raw: str) -> tuple[int, ...]:
    """A version string's numeric components: ``"0.8.1"`` and sqlite-vec's ``"v0.1.6"`` both parse."""
    return tuple(int(part) for part in raw.lstrip("v").split(".") if part.isdigit())
