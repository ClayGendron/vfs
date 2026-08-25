"""Engine lifecycle — construction XOR, first touch, retry, close.

:class:`EngineHost` owns one mount's database connectivity in exactly
one of two ways, loudly: **built** (a URL in — the host creates the
engine, wraps it in its own sessionmaker, and disposes it at
``close()``) or **borrowed** (an injected session factory yielding
fresh, independent sessions — the host never creates an engine and
``close()`` never touches the pool). You own what you build; a host
never holds an engine it did not make. A caller holding a live engine
wraps it in ``async_sessionmaker(engine)`` — one line that states the
ownership it means. The borrowed path is single-loop by intent; in
notebooks and sync-client pipelines, use the built path, which binds
nothing to a loop until first touch.

Dialect-dependent work stays out of construction: policy resolves from
the session bind at first use, so no dialect decision is made before
the first session exists. First touch is idempotent and lazy, on the
caller's loop: database-file settings, then — under the topology
serialization point (``BEGIN IMMEDIATE`` on SQLite via the installed
transaction control; a per-mount advisory lock on Postgres; a plain
transaction elsewhere, where the unique-violation arbitration is the
correctness backstop) — ``create_all`` and the schema-version row. An
existing row is verified: benign match serves and adopts the durable
mount identity; a mismatch refuses loudly as ``vfs.unavailable.schema``,
never PRAGMA/catalog sniffing.

Facts SQLAlchemy models are read from the dialect, never redeclared:
the parameter budget is ``dialect.insertmanyvalues_max_parameters`` and
transport-down classification uses ``dialect.is_disconnect()``. On a
borrowed SQLite bind the transaction-control listeners are installed
once (marker-guarded); session settings stamp every pool checkout — so
connections pooled before the borrow are covered too — and other users
of that engine see explicit ``BEGIN`` at transaction start instead of
the driver's deferred implicit one — same semantics, earlier lock
acquisition for writers only.
"""

from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar, cast

from sqlalchemy import Engine, event, func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from ulid import ULID

from vfs.models.rows import SCHEMA_FORMAT_VERSION, build_vfs_tables
from vfs.results import ResultError, VFSErrorKind
from vfs.storage.backends.database.dialects import (
    DialectProfile,
    StaleSnapshot,
    is_permanent_defect,
    is_retryable,
    membership_budget,
    profile_for,
    topology_execution_options,
)
from vfs.storage.backends.database.offload import OFFLOAD_WORKERS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.engine import Dialect
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

    from vfs.models.rows import VFSTables

T = TypeVar("T")


def advisory_key(text: str) -> int:
    """Stable signed-64 advisory-lock key derived from *text*.

    Every rival instance hashing the same handle — the durable mount
    identity once adopted, the per-mount table prefix before it exists —
    lands on the same key, and the signed range is what Postgres's
    ``pg_advisory_xact_lock(bigint)`` accepts.
    """
    digest = hashlib.blake2b(text.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class _ResolvedPolicy(NamedTuple):
    """Declared dialect policy and the live dialect it was read from."""

    profile: DialectProfile
    dialect: Dialect


class EngineHost:
    """One mount's connectivity, tables, dialect policy, and first-touch state."""

    def __init__(
        self,
        *,
        url: str | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
        table_name: str = "vfs",
        schema: str | None = None,
        retry_attempts: int = 4,
        retry_base_delay: float = 0.05,
    ) -> None:
        if (url is None) == (session_factory is None):
            raise ValueError(
                "DatabaseStorage takes exactly one of url= (built: the backend owns the engine) "
                "or session_factory= (borrowed: injected sessions; close() never touches the pool)"
            )
        self.tables: VFSTables = build_vfs_tables(table_name=table_name, schema=schema)
        self._engine: AsyncEngine | None
        self.session_factory: Callable[[], AsyncSession]
        if session_factory is not None:
            self._engine = None
            self.session_factory = session_factory
        else:
            engine = create_async_engine(str(url), **_engine_kwargs(str(url)))
            self._engine = engine
            factory = async_sessionmaker(engine, expire_on_commit=False)
            # One shared DBAPI connection cannot overlap transactions: ops
            # serialize, and a re-minted connection re-arms first touch.
            if isinstance(engine.sync_engine.pool, StaticPool):
                self.session_factory = _SerializedSessions(factory)
                _rearm_on_fresh_connection(engine.sync_engine, self)
            else:
                self.session_factory = factory
        # Dialect policy defers to first use: a borrowed host cannot
        # know its dialect before its first session exists.
        self._profile: DialectProfile | None = None
        self._dialect: Dialect | None = None
        self._table_key = advisory_key(table_name)
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self.mount_identity: str | None = None
        self._ready = False
        # Created lazily on the caller's loop — construction must stay
        # loop-free so construct-here, first-touch-elsewhere works.
        self._lock: asyncio.Lock | None = None
        # Owned either way (built or borrowed) — connectivity etiquette
        # never applies to the host's own offload pool.
        self._offload_executor: ThreadPoolExecutor | None = None

    @property
    def engine(self) -> AsyncEngine:
        """The built engine; a borrowed host never holds one."""
        if self._engine is None:
            raise RuntimeError("borrowed host: connectivity belongs to the injected session factory")
        return self._engine

    @property
    def profile(self) -> DialectProfile:
        """Declared dialect policy, resolved from the session bind at first use."""
        return self._policy().profile

    @property
    def parameter_budget(self) -> int:
        """Bind params per statement — SQLAlchemy's own declared datum."""
        return self._policy().dialect.insertmanyvalues_max_parameters

    @property
    def membership_budget(self) -> int:
        """Elements per ``IN``-list chunk under this dialect's budgets."""
        return membership_budget(self.profile, self.parameter_budget)

    @property
    def offload_executor(self) -> ThreadPoolExecutor:
        """The CPU offload pool — lazy on first use, shut and cleared at close.

        Serves every offloaded stage (grep verify, reindex's chunk and
        posting passes). Cleared, not just shut: a call after close
        re-mints a fresh pool and serves, the same transparent
        re-establishment every sibling verb already has; any re-minted
        pool is shut by the next close.
        """
        if self._offload_executor is None:
            self._offload_executor = ThreadPoolExecutor(max_workers=OFFLOAD_WORKERS, thread_name_prefix="vfs-offload")
        return self._offload_executor

    @property
    def topology_key(self) -> int:
        """Advisory key for topology serialization — keyed on identity, never path.

        The durable mount identity once first touch has adopted it; the
        table-name key before then, the only handle rivals share pre-touch.
        """
        identity = self.mount_identity
        return advisory_key(identity) if identity is not None else self._table_key

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
                message = f"First touch kept losing to concurrent changes: {exc.context}"
                return ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)
            except (SQLAlchemyError, OSError) as exc:
                # SQLAlchemyError, not just DBAPIError: pool exhaustion
                # (TimeoutError) is an operating condition, never a raise.
                return self.classify_failure(exc, context="First touch")

    async def with_retry(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run *fn*, restarting whole on a retryable outcome, with backoff.

        A :class:`StaleSnapshot` is always retryable: a guard proved the
        snapshot stale, and a fresh attempt re-derives everything from
        current state. Exhaustion has one channel: it always leaves as
        :class:`StaleSnapshot` — the in-band signal as itself, a native
        serialization error wrapped as the cause — so every caller
        classifies both identically. Only non-retryable failures escape
        raw to the caller's classifier.
        """
        delay = self._retry_base_delay
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await fn()
            except (DBAPIError, StaleSnapshot) as exc:
                if not isinstance(exc, StaleSnapshot) and not is_retryable(self.profile, exc):
                    raise
                if attempt >= self._retry_attempts:
                    if isinstance(exc, StaleSnapshot):
                        raise
                    raise StaleSnapshot(f"a retryable engine conflict outlived {attempt} attempts") from exc
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")  # pragma: no cover

    def classify_failure(self, exc: BaseException, *, context: str) -> ResultError:
        """Classify a driver failure that escaped retry — always a Result, never a raise.

        A statement defect (syntax class) is a vfs bug, classified
        ``internal`` and never retryable — retrying a broken statement
        forever would disguise the bug as an operating condition.
        """
        origin = getattr(exc, "orig", None) or exc
        try:
            # The runtime contract takes any driver exception; the stub's
            # `Error` type is the DBAPI module protocol, not a real class.
            disconnected = isinstance(origin, Exception) and self._policy().dialect.is_disconnect(
                origin,  # ty: ignore[invalid-argument-type]
                None,
                None,
            )
        except Exception:
            disconnected = False
        if disconnected:
            return ResultError(
                kind=VFSErrorKind.backend_unavailable, message=f"{context} failed: {origin}", retryable=True
            )
        if is_permanent_defect(exc):
            message = f"{context} hit a permanent statement defect: {origin}"
            return ResultError(kind=VFSErrorKind.internal, message=message, retryable=False)
        return ResultError(kind=VFSErrorKind.unavailable, message=f"{context} failed: {origin}", retryable=True)

    async def close(self) -> None:
        """Dispose iff built; every close releases; borrowed connectivity is never touched.

        No close is one-shot: verbs revive after close and re-mint
        pools and connections, so each close releases whatever the
        host holds *now*. Idempotence is by cheapness — a second close
        finds empty pools and does nothing — never by flag, matching
        the pools underneath; and nothing records teardown ahead of
        the awaited dispose returning, so a close cancelled mid-dispose
        leaves a retry that finishes the job.

        The offload pool is the host's own either way and every close
        shuts whatever pool exists — without waiting: an abandoned
        worker mid-call finishes into the void rather than holding
        close hostage. Queued work is never cancelled: its callers are
        still awaiting, and a served call beats a poisoned one. The
        slot is cleared so the next offloaded call re-mints (the
        sibling posture: verbs serve after close), owned by whichever
        close comes next.
        """
        if self._offload_executor is not None:
            self._offload_executor.shutdown(wait=False)
            self._offload_executor = None
        # The ready latch falls with its connectivity: the next op re-runs
        # the idempotent first touch instead of serving off a stale latch.
        self._ready = False
        if self._engine is not None:
            await self._engine.dispose()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _policy(self) -> _ResolvedPolicy:
        profile, dialect = self._profile, self._dialect
        if profile is None or dialect is None:
            # Loop-free and IO-free: a fresh session is asked only for
            # its bind, then closed without ever touching a connection.
            session = self.session_factory()
            try:
                bind = session.get_bind()
            finally:
                session.sync_session.close()
            dialect = bind.dialect
            profile = profile_for(dialect.name)
            if profile.name == "sqlite" and isinstance(bind, Engine):
                _install_sqlite_transaction_control(bind, profile)
            self._profile, self._dialect = profile, dialect
        return _ResolvedPolicy(profile=profile, dialect=dialect)

    async def _first_touch(self) -> ResultError | None:
        profile = self._policy().profile
        if profile.file_settings:
            await self._apply_file_settings(profile)
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

    async def _verify_or_provision(self) -> ResultError | None:
        meta = self.tables.meta
        version_and_identity = select(meta.c.schema_format_version, meta.c.mount_identity)
        async with self.session_factory() as session:
            # First touch is a topology mutation: writer marker (SQLite's
            # BEGIN IMMEDIATE) plus the declared topology-isolation pin.
            conn = await session.connection(execution_options=topology_execution_options(self.profile))
            await self._serialization_point(conn)
            # DDL joins the serialized transaction where the engine keeps
            # DDL transactional (SQLite/Postgres/MSSQL); elsewhere the
            # unique-violation arbitration below remains the backstop.
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
                outcome: ResultError | None = ResultError(
                    kind=VFSErrorKind.unavailable,
                    message=(
                        "Database is inconsistently provisioned: existing rows conflict with "
                        "first touch but no schema-version row is present. Repair or re-provision the mount."
                    ),
                )
            else:
                outcome = self._adopt(row.schema_format_version, row.mount_identity)
            await session.commit()
            return outcome

    async def _provision(self, conn: AsyncConnection) -> None:
        now = datetime.now(UTC)
        await conn.execute(
            insert(self.tables.meta).values(
                id=1,
                schema_format_version=SCHEMA_FORMAT_VERSION,
                mount_identity=str(ULID()),
                created_at=now,
            )
        )
        await conn.execute(
            insert(self.tables.entry).values(
                entry_id=str(ULID()),
                parent_id=None,
                path="/",
                # "/" is un-typable as a segment name; Oracle folds '' to
                # NULL, which the NOT NULL name column rightly refuses.
                name="/",
                kind="directory",
                version=1,
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

    def _adopt(self, version: int, identity: str) -> ResultError | None:
        if version != SCHEMA_FORMAT_VERSION:
            return ResultError(
                kind=VFSErrorKind.schema_mismatch,
                message=(
                    f"Database schema format is {version}; this build expects "
                    f"{SCHEMA_FORMAT_VERSION}. Refusing to serve — upgrade or re-provision the mount."
                ),
            )
        self.mount_identity = identity
        return None


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _engine_kwargs(url: str) -> dict[str, bool]:
    """Per-driver engine arguments the lossless byte contract requires.

    SQLAlchemy's pyodbc dialect declares ``String`` binds as ANSI
    ``SQL_VARCHAR`` via setinputsizes, and the server squeezes those
    through the database codepage before they reach a UTF-8 column —
    mangling non-Latin1 to ``?``. Disabling setinputsizes restores
    pyodbc's Unicode default (``SQL_WVARCHAR``), whose conversion into
    the UTF-8 collation is lossless. Borrowed session factories carry
    their builder's engine and must apply this themselves.
    """
    if make_url(url).get_backend_name() == "mssql":
        return {"use_setinputsizes": False}
    return {}


def _install_sqlite_transaction_control(sync_engine: Engine, profile: DialectProfile) -> None:
    """Take over BEGIN emission and stamp session settings at checkout.

    The documented SQLAlchemy recipe: the driver's deferred implicit
    BEGIN is disabled so the begin event controls transaction start —
    writers (``vfs_writer`` execution option) get ``BEGIN IMMEDIATE``.
    Session settings are connection state applied at every pool checkout
    (op-session start) — the checkout event, unlike connect, also covers
    connections a borrowed pool held before this host existed, and
    re-stamps state another borrower may have changed. Marker-guarded so
    two hosts borrowing one bind do not double-install.
    """
    if getattr(sync_engine, "_vfs_sqlite_control", False):
        return
    sync_engine._vfs_sqlite_control = True  # ty: ignore[unresolved-attribute]

    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(dbapi_connection, _record, _proxy) -> None:  # noqa: ANN001
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        for statement in profile.session_settings:
            cursor.execute(statement)
        cursor.close()

    @event.listens_for(sync_engine, "begin")
    def _on_begin(conn) -> None:  # noqa: ANN001
        options = conn.get_execution_options()
        if options.get("vfs_no_begin"):
            return
        mode = "BEGIN IMMEDIATE" if options.get("vfs_writer") else "BEGIN"
        conn.exec_driver_sql(mode)


class _SerializedSession:
    """One serialized session: the host lock spans enter to exit.

    Attribute access proxies to the real session, so an un-entered
    session (the loop-free policy probe) works lock-free.
    """

    def __init__(self, session: AsyncSession, lock: asyncio.Lock) -> None:
        self._session = session
        self._lock = lock

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def __aenter__(self) -> AsyncSession:
        await self._lock.acquire()
        try:
            return await self._session.__aenter__()
        except BaseException:
            self._lock.release()
            raise

    async def __aexit__(self, *exc_info: object) -> None:
        try:
            await self._session.__aexit__(*exc_info)
        finally:
            self._lock.release()


class _SerializedSessions:
    """Session factory for a single-connection pool — one op at a time.

    A ``StaticPool`` engine shares one DBAPI connection, and overlapping
    asyncio tasks collide mid-transaction ("cannot start a transaction
    within a transaction") or park the loop in the driver. Holding the
    host lock for each session's whole context makes the declared
    serialized posture true by construction.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._lock = asyncio.Lock()

    def __call__(self) -> AsyncSession:
        return cast("AsyncSession", _SerializedSession(self._factory(), self._lock))


def _rearm_on_fresh_connection(sync_engine: Engine, host: EngineHost) -> None:
    """Drop the ready latch when a single-connection pool re-mints.

    A ``:memory:`` database lives inside its one connection — a
    replacement connection is a fresh, empty database. Re-arming first
    touch makes the next op re-provision instead of serving misses off
    a stale latch forever.
    """
    fresh = False

    @event.listens_for(sync_engine, "connect")
    def _on_connect(_dbapi_connection, _record) -> None:  # noqa: ANN001
        nonlocal fresh
        if fresh:
            host._ready = False
        fresh = True
