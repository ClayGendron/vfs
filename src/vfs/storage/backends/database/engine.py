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
caller's loop: database-file settings, the profile's vector probe (the
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
import importlib.util
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar, cast

from sqlalchemy import Engine, event, func, insert, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.util.concurrency import await_only
from ulid import ULID

from vfs.models.rows import SCHEMA_FORMAT_VERSION, build_vfs_tables
from vfs.models.vector import NativeEmbeddingConfig
from vfs.results import ErrorKind, ResultError, classified
from vfs.storage.backends.database.dialects import (
    SQLITE_VEC_PROBE,
    DialectProfile,
    StaleSnapshot,
    ValueCap,
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
from vfs.storage.backends.database.offload import OFFLOAD_WORKERS
from vfs.storage.backends.database.rights import posture_row
from vfs.storage.grants import LEVEL_RANK

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.engine import Connection, Dialect
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

    from vfs.embedding import EmbeddingProvider
    from vfs.models.rows import VFSTables
    from vfs.storage.grants import Posture

T = TypeVar("T")

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


def advisory_key(text: str) -> int:
    """Stable signed-64 advisory-lock key derived from *text*.

    Every rival instance hashing the same handle — the durable mount
    identity once adopted, the schema-qualified table name before it exists —
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
        schema: str | None = None,
        embedder: EmbeddingProvider | None = None,
        native_embedding: NativeEmbeddingConfig | None = None,
        posture: Posture = "read_write",
        retry_attempts: int = 4,
        retry_base_delay: float = 0.05,
    ) -> None:
        if (url is None) == (session_factory is None):
            raise ValueError(
                "DatabaseStorage takes exactly one of url= (built: the backend owns the engine) "
                "or session_factory= (borrowed: injected sessions; close() never touches the pool)"
            )
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
        # The engine's single-value cap where it is a server setting (the
        # MySQL family's packet); read at first touch, ``None`` elsewhere.
        self.value_cap: ValueCap | None = None
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
    def embedding_stale(self) -> bool:
        """Whether the stored vectors belong to a space other than the configured embedder's.

        ``False`` with no embedder or no stored identity: nothing to
        compare. A stale space is served lexical-only and migrated by
        the next ``reindex``.
        """
        if self.embedder is None or self.embedding_identity is None:
            return False
        return self.embedding_identity != (self.embedder.model_id, self.embedder.dimension)

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
        """
        function = self._policy().profile.vector_function
        if function is None:
            return None
        try:
            if function.install is not None:
                await self._install_vector_function(function.install)
            return await self._probe_vector_function(function)
        except DBAPIError as exc:
            origin = driver_origin(exc)
            if is_insufficient_privilege(origin):
                detail = f"this role may not install the extension ({origin}); {function.missing}"
                return classified(ErrorKind.permission_denied, detail=detail)
            return self.classify_failure(exc, context="Install extensions")

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
        origin = driver_origin(exc)
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
            return classified(ErrorKind.backend_unavailable, retryable=True, detail=f"{context} failed: {origin}")
        if is_value_too_large(exc):
            # The engine's own single-value cap, named by the engine: not a vfs ceiling.
            detail = f"{context} exceeded this engine's single-value limit: {origin}"
            return classified(ErrorKind.unsupported, detail=detail)
        if is_permanent_defect(exc):
            return classified(ErrorKind.internal, detail=f"{context} hit a permanent statement defect: {origin}")
        return classified(ErrorKind.unavailable, retryable=True, detail=f"{context} failed: {origin}")

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
        if profile.value_cap_query is not None and profile.value_cap_setting is not None:
            self.value_cap = await self._read_value_cap(profile.value_cap_query, profile.value_cap_setting)
        if profile.vector_function is not None:
            refusal = await self._probe_vector_function(profile.vector_function)
            if refusal is not None:
                return refusal
        refusal = await self._verify_or_provision()
        if refusal is None:
            self._ready = True
        return refusal

    async def _read_value_cap(self, query: str, setting: str) -> ValueCap:
        """The server's single-value cap, so an oversized body is refused before it is sent."""
        async with self.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_no_begin": True})
            limit = (await conn.exec_driver_sql(query)).scalar_one()
        return ValueCap(int(limit), setting)

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
        await conn.execute(insert(self.tables.lock).values(id=1))
        await conn.execute(insert(self.tables.grants).values(**posture_row(self.posture, now)))
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

    def _adopt(self, row: Any) -> ResultError | None:
        """Verify the meta row and adopt its identities; a refusal names the mismatch.

        A stored embedding space of another width than a **native**
        column refuses outright: the column physically cannot hold the
        configured vectors, and the fix is DDL, out of every verb's
        reach. A stored *model* mismatch is not refused here — the
        vector leg declines it per call and ``reindex`` migrates.
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


def _engine_kwargs(url: str) -> dict[str, bool]:
    """Per-driver engine arguments the lossless byte contract requires.

    SQLAlchemy's pyodbc dialect declares ``String`` binds as ANSI
    ``SQL_VARCHAR`` via setinputsizes, and the server squeezes those
    through the database codepage before they reach a UTF-8 column —
    mangling non-Latin1 to ``?``. Disabling setinputsizes restores
    pyodbc's Unicode default (``SQL_WVARCHAR``), whose conversion into
    the UTF-8 collation is lossless. pyodbc's ``fast_executemany`` is
    deliberately *not* set: engine-wide it rewrites UPDATE executemany,
    whose rowcount the guarded bumps verify, and as a bulk-insert mode it
    is still one RPC per row, slower than Core's pages on wide rows —
    SQL Server's bulk inserts take Core's pages. Borrowed session
    factories carry their builder's engine and must apply this themselves.
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
        # Checkout, not connect: a borrowed pool's pre-existing connections
        # never fire connect. A connection already carrying the function skips the load.
        if not _has_sqlite_vec(cursor):
            _load_sqlite_vec(dbapi_connection)
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


def _version_tuple(raw: str) -> tuple[int, ...]:
    """A version string's numeric components: ``"0.8.1"`` and sqlite-vec's ``"v0.1.6"`` both parse."""
    return tuple(int(part) for part in raw.lstrip("v").split(".") if part.isdigit())


def _has_sqlite_vec(cursor: Any) -> bool:
    """Whether this connection already answers the extension's version function."""
    try:
        cursor.execute(SQLITE_VEC_PROBE)
    except sqlite3.OperationalError:
        return False
    cursor.fetchall()
    return True


def _load_sqlite_vec(dbapi_connection: Any) -> None:
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
