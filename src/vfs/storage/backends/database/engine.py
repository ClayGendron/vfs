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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, NamedTuple, TypeVar

from sqlalchemy import Engine, event, func, insert, select
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ulid import ULID

from vfs.models.rows import SCHEMA_FORMAT_VERSION, build_vfs_tables
from vfs.results import ResultError, VFSErrorKind
from vfs.storage.backends.database.dialects import DialectProfile, is_retryable, profile_for

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.engine import Dialect
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

    from vfs.models.rows import VFSTables

T = TypeVar("T")


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
            engine = create_async_engine(str(url))
            self._engine = engine
            self.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        # Dialect policy defers to first use: a borrowed host cannot
        # know its dialect before its first session exists.
        self._profile: DialectProfile | None = None
        self._dialect: Dialect | None = None
        self._advisory_key = _advisory_key(table_name)
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self.mount_identity: str | None = None
        self._ready = False
        self._closed = False
        # Created lazily on the caller's loop — construction must stay
        # loop-free so construct-here, first-touch-elsewhere works.
        self._lock: asyncio.Lock | None = None

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
            except (SQLAlchemyError, OSError) as exc:
                # SQLAlchemyError, not just DBAPIError: pool exhaustion
                # (TimeoutError) is an operating condition, never a raise.
                return self.classify_failure(exc, context="First touch")

    async def with_retry(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run *fn*, restarting whole on a retryable outcome, with backoff."""
        delay = self._retry_base_delay
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await fn()
            except DBAPIError as exc:
                if attempt >= self._retry_attempts or not is_retryable(self.profile, exc):
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")  # pragma: no cover

    def classify_failure(self, exc: BaseException, *, context: str) -> ResultError:
        """Classify a driver failure that escaped retry — always a Result, never a raise."""
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
        kind = VFSErrorKind.backend_unavailable if disconnected else VFSErrorKind.unavailable
        return ResultError(kind=kind, message=f"{context} failed: {origin}", retryable=True)

    async def close(self) -> None:
        """Dispose iff built; idempotent; borrowed connectivity is never touched."""
        if self._closed:
            return
        self._closed = True
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
            # Writers carry the vfs_writer option: SQLite's begin listener
            # upgrades their BEGIN to IMMEDIATE (the W7 lock discipline).
            conn = await session.connection(execution_options={"vfs_writer": True})
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
                node_id=str(ULID()),
                parent_id=None,
                path="/",
                name="",
                kind="directory",
                revision=0,
                created_at=now,
                updated_at=now,
            )
        )

    async def _serialization_point(self, conn: AsyncConnection) -> None:
        # SQLite serializes via the writer BEGIN IMMEDIATE the listener
        # already emitted; engines without a declared point rely on the
        # unique-violation arbitration.
        if self.profile.name == "postgresql":
            await conn.execute(select(func.pg_advisory_xact_lock(self._advisory_key)))

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


def _advisory_key(table_name: str) -> int:
    """Stable signed-64 advisory-lock key for first touch.

    The spec keys topology locks by the durable mount identity, which
    does not exist until first touch completes — the per-mount table
    prefix is the handle every rival instance shares before then.
    """
    digest = hashlib.blake2b(table_name.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


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
