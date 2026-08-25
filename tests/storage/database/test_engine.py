"""EngineHost lifecycle — the construction XOR, first touch, loops and close, and pool exhaustion.

The construction XOR (built url vs borrowed session factory — never a bare
engine), idempotent provisioning under the serialization point,
schema-version verification, restart rebind, cross-loop first touch,
borrowed-sessions close, the single-connection host (serialized sessions,
re-minted connections re-arming first touch), and pool exhaustion
classified rather than raised.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import QueuePool
from ulid import ULID

from tests.support.database_helpers import _url
from vfs.models.rows import MAX_TABLE_NAME_LENGTH, SCHEMA_FORMAT_VERSION, ULID_LENGTH, build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, StorageBackend, SupportsClose, SupportsTraits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import POSTGRESQL, PROFILES, SQLITE, profile_for
from vfs.storage.backends.database.engine import (
    EngineHost,
    _engine_kwargs,
    _install_sqlite_transaction_control,
    _SerializedSession,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession


# ---------------------------------------------------------------------------
# Construction XOR
# ---------------------------------------------------------------------------


class TestConstruction:
    async def test_url_and_session_factory_together_are_refused(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        with pytest.raises(ValueError, match="exactly one"):
            DatabaseStorage(url=_url(tmp_path), session_factory=factory)
        await engine.dispose()

    def test_neither_url_nor_session_factory_is_refused(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            DatabaseStorage()

    def test_over_budget_table_name_is_refused_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="63-char"):
            DatabaseStorage(url=_url(tmp_path), table_name="x" * (MAX_TABLE_NAME_LENGTH + 1))

    def test_satisfies_the_storage_protocols(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert isinstance(storage, StorageBackend)
        assert isinstance(storage, SupportsClose)
        assert isinstance(storage, SupportsTraits)

    def test_traits_stay_within_the_vocabulary(self, tmp_path) -> None:
        traits = DatabaseStorage(url=_url(tmp_path)).traits()
        assert set(traits) <= TRAIT_KEYS
        assert all(value in TRAIT_VALUES[key] for key, value in traits.items())

    def test_an_mssql_url_disables_setinputsizes(self, tmp_path) -> None:
        # pyodbc's ANSI setinputsizes mangles non-Latin1 bytes; only the
        # mssql built path carries the lossless override.
        assert _engine_kwargs("mssql+aioodbc://sa:pw@host/db") == {"use_setinputsizes": False}
        assert _engine_kwargs(_url(tmp_path)) == {}

    def test_durability_full_is_declared_per_tuned_profile(self, tmp_path, monkeypatch) -> None:
        # Durability is a contract a caller must be able to read: every
        # tuned profile declares it full; the generic floor never does.
        storage = DatabaseStorage(url=_url(tmp_path))
        for profile in PROFILES.values():
            monkeypatch.setattr(EngineHost, "profile", property(lambda self, p=profile: p))
            traits = storage.traits()
            assert traits["durability"] == "full"
            assert traits["arbitration"] == profile.arbitration
        monkeypatch.setattr(EngineHost, "profile", property(lambda self: profile_for("duckdb")))
        assert "durability" not in storage.traits()


# ---------------------------------------------------------------------------
# First touch — provision, verify, refuse
# ---------------------------------------------------------------------------


class TestFirstTouch:
    async def test_first_touch_applies_a_declared_topology_isolation_pin(self, tmp_path, monkeypatch) -> None:
        # SERIALIZABLE is a level the SQLite dialect accepts, so the pinned
        # provisioning transaction exercises the same wiring a real pin takes.
        pinned = replace(SQLITE, topology_isolation="SERIALIZABLE")
        monkeypatch.setattr(engine_module, "profile_for", lambda _name: pinned)
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        assert storage._host.profile.topology_isolation == "SERIALIZABLE"
        await storage.close()

    async def test_provisions_meta_and_root_rows(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.first_touch()
        assert result.success is True
        assert storage.mount_identity is not None
        assert len(storage.mount_identity) == ULID_LENGTH
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            meta = (await conn.execute(select(tables.meta))).mappings().one()
            root = (await conn.execute(select(tables.entry))).mappings().one()
        assert meta["schema_format_version"] == SCHEMA_FORMAT_VERSION
        assert meta["mount_identity"] == storage.mount_identity
        assert root["path"] == "/"
        # '/' is un-typable as a real segment (Oracle folds '' to NULL).
        assert root["name"] == "/"
        assert root["kind"] == "directory"
        assert root["parent_id"] is None
        await storage.close()

    async def test_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        assert (await storage.first_touch()).success is True
        async with storage._host.engine.connect() as conn:
            count = (await conn.execute(select(storage._host.tables.meta))).all()
        assert len(count) == 1
        await storage.close()

    async def test_applies_database_file_settings(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.connect() as conn:
            journal = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar_one()
            page = (await conn.exec_driver_sql("PRAGMA page_size")).scalar_one()
        assert journal == "wal"
        assert page == 16384
        await storage.close()

    async def test_restart_rebind_keeps_the_mount_identity(self, tmp_path) -> None:
        first = DatabaseStorage(url=_url(tmp_path))
        await first.first_touch()
        identity = first.mount_identity
        await first.close()
        second = DatabaseStorage(url=_url(tmp_path))
        assert (await second.first_touch()).success is True
        assert second.mount_identity == identity
        await second.close()

    async def test_version_mismatch_refuses_loudly(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        result = await stale.first_touch()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.schema_mismatch
        assert stale.mount_identity is None
        await stale.close()

    async def test_the_first_routed_op_triggers_first_touch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.stat(path=Path("/"))
        assert result.success is True
        assert result.observations[0].kind == "directory"
        assert storage.mount_identity is not None
        await storage.close()

    async def test_ops_surface_the_mismatch_refusal(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        result = await stale.stat(path=Path("/"))
        assert result.errors[0].kind == VFSErrorKind.schema_mismatch
        await stale.close()

    async def test_half_provisioned_database_refuses_with_a_classified_error(self, tmp_path) -> None:
        # Root entry present but no meta row: the provision IntegrityError
        # is NOT the designed meta race and must classify, never leak raw.
        tables = build_vfs_tables(table_name="vfs")
        seed = create_async_engine(_url(tmp_path))
        now = datetime.now(UTC)
        async with seed.begin() as conn:
            await conn.run_sync(tables.metadata.create_all)
            await conn.execute(
                insert(tables.entry).values(
                    entry_id=str(ULID()),
                    parent_id=None,
                    path="/",
                    name="/",
                    kind="directory",
                    version=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        await seed.dispose()
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.first_touch()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert "inconsistently provisioned" in result.errors[0].message
        assert storage.mount_identity is None
        await storage.close()

    async def test_two_instances_first_touch_concurrently(self, tmp_path) -> None:
        a = DatabaseStorage(url=_url(tmp_path))
        b = DatabaseStorage(url=_url(tmp_path))
        first, second = await asyncio.gather(a.first_touch(), b.first_touch())
        assert first.success is True
        assert second.success is True
        assert a.mount_identity == b.mount_identity
        async with a._host.engine.connect() as conn:
            rows = (await conn.execute(select(a._host.tables.meta))).all()
        assert len(rows) == 1
        await a.close()
        await b.close()

    async def test_concurrent_ensure_ready_on_one_host_serves_both_waiters(self, tmp_path) -> None:
        host = EngineHost(url=_url(tmp_path))
        first, second = await asyncio.gather(host.ensure_ready(), host.ensure_ready())
        assert first is None and second is None
        assert host.mount_identity is not None
        await host.close()

    async def test_serialization_point_takes_the_postgres_advisory_lock(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host

        class _RecordingConn:
            def __init__(self) -> None:
                self.statements: list[object] = []

            async def execute(self, statement: object) -> None:
                self.statements.append(statement)

        conn = _RecordingConn()
        await host._serialization_point(cast("AsyncConnection", conn))
        assert conn.statements == []  # sqlite serializes via BEGIN IMMEDIATE, not a lock statement
        host._profile = POSTGRESQL
        await host._serialization_point(cast("AsyncConnection", conn))
        assert len(conn.statements) == 1
        assert "pg_advisory_xact_lock" in str(conn.statements[0])
        await storage.close()


# ---------------------------------------------------------------------------
# Loops and close
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_construct_on_one_loop_first_touch_on_another(self, tmp_path) -> None:
        async def construct() -> DatabaseStorage:
            return DatabaseStorage(url=_url(tmp_path))

        loop = asyncio.new_event_loop()
        try:
            storage = loop.run_until_complete(construct())
        finally:
            loop.close()

        async def touch_and_close() -> str | None:
            assert (await storage.first_touch()).success is True
            identity = storage.mount_identity
            await storage.close()
            return identity

        assert asyncio.run(touch_and_close()) is not None

    async def test_borrowed_pool_pre_existing_connections_get_session_settings(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        # Pool a connection BEFORE the borrow; checkout must still stamp it.
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        assert (await storage.first_touch()).success is True
        async with engine.connect() as conn:  # the app's own pool is stamped too
            like = (await conn.exec_driver_sql("SELECT 'A' LIKE 'a'")).scalar_one()
            timeout = (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar_one()
        assert like == 0  # case_sensitive_like = ON
        assert timeout == 5000
        await storage.close()
        await engine.dispose()

    async def test_borrowed_close_never_disposes(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        assert (await storage.first_touch()).success is True
        await storage.close()
        async with engine.connect() as conn:  # the pool must still serve
            assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
        await engine.dispose()

    async def test_a_borrowed_host_never_holds_an_engine(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        with pytest.raises(RuntimeError, match="borrowed host"):
            _ = storage._host.engine
        await engine.dispose()

    async def test_borrowed_dialect_policy_defers_to_first_use(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        calls = 0

        def factory() -> AsyncSession:
            nonlocal calls
            calls += 1
            return maker()

        storage = DatabaseStorage(session_factory=factory)
        assert calls == 0  # construction makes no dialect decision
        assert storage._host.profile.name == "sqlite"
        assert calls == 1  # resolved from the first session's bind
        assert (await storage.first_touch()).success is True
        await storage.close()
        await engine.dispose()

    async def test_built_close_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        await storage.close()
        await storage.close()

    async def test_every_close_releases_what_revival_re_minted(self, tmp_path) -> None:
        # close → verb → close: the revived verb re-mints connections,
        # and the second close must release them — close is never one-shot.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        await storage.close()
        result = await storage.stat(path=Path("/"))
        assert result.success is True
        pool = storage._host.engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.checkedin() >= 1
        await storage.close()
        assert pool.checkedin() == 0

    async def test_a_cancelled_close_retry_finishes_the_job(self, tmp_path) -> None:
        # A close cancelled mid-dispose records nothing as torn down:
        # the documented recovery — close again — must reclaim the pool.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        host = storage._host
        pool = host.engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.checkedin() >= 1
        parked = asyncio.Event()

        class _ParkedEngine:
            async def dispose(self) -> None:
                parked.set()
                await asyncio.sleep(60)

        real_engine = host._engine
        host._engine = cast("AsyncEngine", _ParkedEngine())
        closing = asyncio.ensure_future(storage.close())
        await parked.wait()
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        host._engine = real_engine
        await storage.close()
        assert pool.checkedin() == 0

    def test_sqlite_transaction_control_installs_once_per_engine(self) -> None:
        # Two hosts borrowing one bind: the second install must be a no-op.
        engine = create_engine("sqlite://")
        _install_sqlite_transaction_control(engine, SQLITE)
        installed = len(engine.pool.dispatch.checkout)  # ty: ignore[unresolved-attribute]
        _install_sqlite_transaction_control(engine, SQLITE)
        assert getattr(engine, "_vfs_sqlite_control", False) is True
        assert len(engine.pool.dispatch.checkout) == installed  # ty: ignore[unresolved-attribute]
        engine.dispose()


# ---------------------------------------------------------------------------
# Single-connection host — serialized sessions, re-minted connections
# ---------------------------------------------------------------------------


class TestSingleConnectionHost:
    async def test_failed_session_enter_releases_the_host_lock(self) -> None:
        # A session whose enter fails must not leave the host lock held —
        # that would deadlock every later op on the storage.
        class _ExplodingSession:
            async def __aenter__(self) -> AsyncSession:
                raise RuntimeError("enter failed")

            async def __aexit__(self, *exc_info: object) -> None: ...

        lock = asyncio.Lock()
        session = _SerializedSession(cast("AsyncSession", _ExplodingSession()), lock)
        with pytest.raises(RuntimeError, match="enter failed"):
            async with session:
                pass
        assert lock.locked() is False

    async def test_replacement_connection_re_arms_first_touch(self) -> None:
        # A :memory: database lives inside its one connection: a re-minted
        # connection is empty, and serving off the stale latch is a lie.
        storage = DatabaseStorage(url="sqlite+aiosqlite:///:memory:")
        assert (await storage.first_touch()).success is True
        host = storage._host
        assert host._ready is True
        async with host.engine.connect() as conn:
            await conn.invalidate()
        async with host.engine.connect() as conn:  # checkout mints the replacement
            await conn.execute(text("SELECT 1"))
        assert host._ready is False
        result = await storage.stat(path=Path("/"))  # next op re-provisions
        assert result.success is True
        assert result.observations[0].kind == "directory"
        await storage.close()


# ---------------------------------------------------------------------------
# Pool exhaustion
# ---------------------------------------------------------------------------


class TestPoolExhaustion:
    async def test_pool_exhaustion_classifies_instead_of_raising(self, tmp_path) -> None:
        # sqlalchemy.exc.TimeoutError is not a DBAPIError: the verb must
        # still classify it, never leak it raw (the no-raw-raise criterion).
        engine = create_async_engine(_url(tmp_path), pool_size=1, max_overflow=0, pool_timeout=0.2)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        storage = DatabaseStorage(session_factory=maker)
        assert (await storage.first_touch()).success is True
        async with maker() as hog:
            await hog.connection()  # hold the only pooled connection
            result = await storage.stat(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()
        await engine.dispose()
