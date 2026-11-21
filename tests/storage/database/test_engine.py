"""EngineHost lifecycle — construction, first touch, loops and close, and pool exhaustion.

Construction from a URL and engine arguments, the engine a storage
builds and owns, idempotent provisioning under the serialization point,
schema-version verification, restart rebind, cross-loop first touch,
where an attempt runs, and pool exhaustion classified rather than
raised. The single-connection host (serialized sessions, re-minted
connections re-arming first touch) is in ``test_oneconnection.py``.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool, QueuePool
from ulid import ULID

from tests.support.database_helpers import _fresh_url, writer_engine
from tests.support.server_schemas import ENGINE_LEGS, server_storage
from vfs.authority import EVERYONE_NAME
from vfs.models import Entry
from vfs.models.rows import SCHEMA_FORMAT_VERSION, ULID_LENGTH, build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, StorageBackend, SupportsClose, SupportsTraits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.attempts import AttemptSession
from vfs.storage.backends.database.dialects import POSTGRESQL, PROFILES, SQLITE, StaleSnapshot, profile_for
from vfs.storage.backends.database.drivers import ClosingConnection
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.grants import LEVEL_RANK

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    async def test_a_storage_builds_its_engine_before_first_touch_and_disposes_it_at_close(self, tmp_path) -> None:
        """The engine is there from construction, so a ``do_connect`` hook or tracing can be put on it."""
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        connected: list[object] = []
        event.listen(storage.engine.sync_engine, "do_connect", lambda *connect: connected.append(connect))
        assert (storage.engine is storage._host.engine, storage._host._ready, connected) == (True, False, [])
        assert (await storage.first_touch()).success is True
        pool = storage.engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert (len(connected) >= 1, pool.checkedin() >= 1) == (True, True)
        await storage.close()
        assert pool.checkedin() == 0

    async def test_engine_arguments_reach_the_engine_beside_what_vfs_requires(self, tmp_path) -> None:
        """Guards the merge: an argument of the application that is dropped, or one of VFS's that is lost."""
        storage = DatabaseStorage(
            url=_fresh_url(tmp_path),
            engine_arguments={"pool_size": 2, "max_overflow": 0, "connect_args": {"timeout": 9}},
        )
        pool = storage.engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert (pool.size(), pool._max_overflow) == (2, 0)
        assert (await storage.first_touch()).success is True
        async with storage.engine.connect() as connection:
            driver = (await connection.get_raw_connection()).driver_connection
        assert driver is not None
        assert isinstance(driver._conn, ClosingConnection)
        await storage.close()

    async def test_a_schema_on_sqlite_is_a_database_attached_through_the_engine(self, tmp_path) -> None:
        """A SQLite schema is an attached database, so the application attaches it on each connection of the engine."""
        storage = DatabaseStorage(url=_fresh_url(tmp_path), schema="tenant")

        def attach(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute(f"ATTACH DATABASE '{tmp_path}/tenant.sqlite' AS tenant")
            cursor.close()

        event.listen(storage.engine.sync_engine, "connect", attach)
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])).success is True
        assert (await storage.read(path=Path("/a.txt"))).one().content == "a"
        async with storage.engine.connect() as connection:
            held = "SELECT count(*) FROM {}.sqlite_master WHERE name = 'vfs_entries'"
            tables = [(await connection.exec_driver_sql(held.format(name))).scalar_one() for name in ("tenant", "main")]
        assert tables == [1, 0]
        await storage.close()

    def test_an_engine_argument_that_changes_what_vfs_requires_is_refused_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match=r"engine_arguments\['connect_args'\]\['factory'\]"):
            DatabaseStorage(
                url=_fresh_url(tmp_path), engine_arguments={"connect_args": {"factory": sqlite3.Connection}}
            )

    @pytest.mark.parametrize(
        ("given", "named"),
        [
            ({"poolclass": NullPool}, r"engine_arguments\['poolclass'\]"),
            ({"pool_recycle": 3600}, r"engine_arguments\['pool_recycle'\]"),
            ({"pool": create_engine("sqlite://").pool}, r"engine_arguments\['pool'\]"),
            ({"isolation_level": "AUTOCOMMIT"}, r"engine_arguments\['isolation_level'\]"),
        ],
        ids=["no pool", "a recycle", "a pool of its own", "autocommit"],
    )
    def test_an_in_memory_storage_is_refused_what_would_cost_it_its_database_or_its_transactions(
        self, given, named
    ) -> None:
        with pytest.raises(ValueError, match=named):
            DatabaseStorage(url="sqlite+aiosqlite://", engine_arguments=given)

    async def test_a_storage_in_a_file_takes_no_pool_and_a_recycle(self, tmp_path) -> None:
        """Guards where the refusal stops: with no pool every call opens its own connection to the one file."""
        storage = DatabaseStorage(url=_fresh_url(tmp_path), engine_arguments={"poolclass": NullPool})
        recycled = DatabaseStorage(url=_fresh_url(tmp_path), engine_arguments={"pool_recycle": 3600})
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])).success is True
        assert (await recycled.read(path=Path("/a.txt"))).one().content == "a"
        assert isinstance(storage.engine.sync_engine.pool, NullPool)
        await storage.close()
        await recycled.close()

    def test_a_storage_in_a_file_is_refused_autocommit(self, tmp_path) -> None:
        with pytest.raises(ValueError, match=r"engine_arguments\['isolation_level'\] must not be 'AUTOCOMMIT'"):
            DatabaseStorage(url=_fresh_url(tmp_path), engine_arguments={"isolation_level": "autocommit"})

    def test_the_default_description_names_the_schema_when_one_is_set(self, tmp_path) -> None:
        assert DatabaseStorage(url=_fresh_url(tmp_path)).description == "Database storage"
        assert DatabaseStorage(url=_fresh_url(tmp_path), schema="tenant").description == "Database storage (tenant)"

    def test_satisfies_the_storage_protocols(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        assert isinstance(storage, StorageBackend)
        assert isinstance(storage, SupportsClose)
        assert isinstance(storage, SupportsTraits)

    def test_traits_stay_within_the_vocabulary(self, tmp_path) -> None:
        traits = DatabaseStorage(url=_fresh_url(tmp_path)).traits()
        assert set(traits) <= TRAIT_KEYS
        assert all(value in TRAIT_VALUES[key] for key, value in traits.items())

    def test_durability_full_is_declared_per_tuned_profile(self, tmp_path, monkeypatch) -> None:
        # Durability is a contract a caller must be able to read: every
        # tuned profile declares it full; the generic floor never does.
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
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
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        assert (await storage.first_touch()).success is True
        assert storage._host.profile.topology_isolation == "SERIALIZABLE"
        await storage.close()

    async def test_provisions_meta_and_root_rows(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
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
        # '/' is un-typable as a real segment (an engine may fold '' to NULL).
        assert root["name"] == "/"
        assert root["kind"] == "directory"
        assert root["parent_id"] is None
        await storage.close()

    async def test_an_existing_mount_is_verified_never_repaired(self, tmp_path) -> None:
        # The meta row is the contract: a reopened mount issues no DDL, and a
        # table that went missing since is refused by the verb that needs it,
        # like a schema-version mismatch, rather than silently recreated.
        url = _fresh_url(tmp_path)
        seeded = DatabaseStorage(url=url)
        assert (await seeded.first_touch()).success is True
        await seeded.close()
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(build_vfs_tables().edges.drop)
        await engine.dispose()
        reopened = DatabaseStorage(url=url)
        statements: list[str] = []

        @event.listens_for(reopened._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement.lstrip().upper())

        assert (await reopened.first_touch()).success is True
        assert not [s for s in statements if s.startswith("CREATE")]
        written = await reopened.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        assert written.success is False
        assert written.errors[0].kind == ErrorKind.unavailable
        await reopened.close()

    async def test_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        assert (await storage.first_touch()).success is True
        assert (await storage.first_touch()).success is True
        async with storage._host.engine.connect() as conn:
            count = (await conn.execute(select(storage._host.tables.meta))).all()
        assert len(count) == 1
        await storage.close()

    async def test_applies_database_file_settings(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.connect() as conn:
            journal = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar_one()
            page = (await conn.exec_driver_sql("PRAGMA page_size")).scalar_one()
        assert journal == "wal"
        assert page == 16384
        await storage.close()

    async def test_restart_rebind_keeps_the_mount_identity(self, tmp_path) -> None:
        first = DatabaseStorage(url=_fresh_url(tmp_path))
        await first.first_touch()
        identity = first.mount_identity
        await first.close()
        second = DatabaseStorage(url=_fresh_url(tmp_path))
        assert (await second.first_touch()).success is True
        assert second.mount_identity == identity
        await second.close()

    async def test_version_mismatch_refuses_loudly(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_fresh_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with writer_engine(seeded._host.engine).begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_fresh_url(tmp_path))
        result = await stale.first_touch()
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.schema_mismatch
        # No in-place repair: the refusal says to re-provision, as every format bump before it.
        assert "re-provision the mount" in result.errors[0].message
        assert result.errors[0].data == {"found": SCHEMA_FORMAT_VERSION + 1, "expected": SCHEMA_FORMAT_VERSION}
        assert stale.mount_identity is None
        await stale.close()

    async def test_the_first_routed_op_triggers_first_touch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        result = await storage.stat(path=Path("/"))
        assert result.success is True
        assert result.observations[0].kind == "directory"
        assert storage.mount_identity is not None
        await storage.close()

    async def test_ops_surface_the_mismatch_refusal(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_fresh_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with writer_engine(seeded._host.engine).begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_fresh_url(tmp_path))
        result = await stale.stat(path=Path("/"))
        assert result.errors[0].kind == ErrorKind.schema_mismatch
        await stale.close()

    async def test_half_provisioned_database_refuses_with_a_classified_error(self, tmp_path) -> None:
        # Root entry present but no meta row: the provision IntegrityError
        # is NOT the designed meta race and must classify, never leak raw.
        tables = build_vfs_tables()
        seed = create_async_engine(_fresh_url(tmp_path))
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
                    everyone_level=LEVEL_RANK["read_write"],
                    created_at=now,
                    updated_at=now,
                )
            )
        await seed.dispose()
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        result = await storage.first_touch()
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.unavailable
        assert "inconsistently provisioned" in result.errors[0].message
        assert storage.mount_identity is None
        await storage.close()

    async def test_two_instances_first_touch_concurrently(self, tmp_path) -> None:
        a = DatabaseStorage(url=_fresh_url(tmp_path))
        b = DatabaseStorage(url=_fresh_url(tmp_path))
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
        host = EngineHost(url=_fresh_url(tmp_path))
        first, second = await asyncio.gather(host.ensure_ready(), host.ensure_ready())
        assert first is None and second is None
        assert host.mount_identity is not None
        await host.close()

    async def test_serialization_point_takes_the_postgres_advisory_lock(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
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
            return DatabaseStorage(url=_fresh_url(tmp_path))

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

    async def test_every_checkout_stamps_the_session_settings(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        assert (await storage.first_touch()).success is True
        async with storage.engine.connect() as conn:
            like = (await conn.exec_driver_sql("SELECT 'A' LIKE 'a'")).scalar_one()
            timeout = (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar_one()
        assert like == 0  # case_sensitive_like = ON
        assert timeout == 5000
        await storage.close()

    async def test_the_dialect_policy_is_resolved_at_construction_with_no_connection(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        pool = storage.engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert (storage._host.profile.name, pool.checkedin(), pool.checkedout()) == ("sqlite", 0, 0)
        await storage.close()

    async def test_built_close_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        await storage.first_touch()
        await storage.close()
        await storage.close()

    async def test_every_close_releases_what_revival_re_minted(self, tmp_path) -> None:
        # close → verb → close: the revived verb re-mints connections,
        # and the second close must release them — close is never one-shot.
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        assert (await storage.first_touch()).success is True
        await storage.close()
        result = await storage.stat(path=Path("/"))
        assert result.success is True
        pool = storage._host.engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.checkedin() >= 1
        await storage.close()
        assert pool.checkedin() == 0

    async def test_retry_waits_are_jittered_within_a_doubling_step(self, tmp_path, monkeypatch) -> None:
        # Two rivals that collided must not sleep the same schedule and
        # collide again: each wait is a draw in [step / 2, step], the step
        # doubling per attempt, so the longest possible wait is unchanged.
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        host = storage._host
        monkeypatch.setattr(host, "_retry_attempts", 4)
        monkeypatch.setattr(host, "_retry_base_delay", 0.05)
        slept: list[float] = []
        draws: list[tuple[float, float]] = []

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        def fake_uniform(low: float, high: float) -> float:
            draws.append((low, high))
            return high  # the longest wait the draw allows

        monkeypatch.setattr(engine_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(engine_module.random, "uniform", fake_uniform)
        calls = 0

        async def always_stale() -> None:
            nonlocal calls
            calls += 1
            raise StaleSnapshot("rival")

        with pytest.raises(StaleSnapshot):
            await host.with_retry(always_stale)
        assert calls == 4
        assert draws == [(0.025, 0.05), (0.05, 0.1), (0.1, 0.2)]
        assert slept == [0.05, 0.1, 0.2]
        await storage.close()

    async def test_a_cancelled_close_retry_finishes_the_job(self, tmp_path) -> None:
        # A close cancelled mid-dispose records nothing as torn down:
        # the documented recovery — close again — must reclaim the pool.
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
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

        real_engine = host.engine
        host.engine = cast("AsyncEngine", _ParkedEngine())
        closing = asyncio.ensure_future(storage.close())
        await parked.wait()
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        host.engine = real_engine
        await storage.close()
        assert pool.checkedin() == 0


# ---------------------------------------------------------------------------
# Where an attempt runs
# ---------------------------------------------------------------------------


class TestWhereAnAttemptRuns:
    async def test_on_sqlite_an_attempt_runs_in_a_task_of_its_own_on_sessions_that_refuse(self, tmp_path) -> None:
        """Guards the declaration's two uses: a host that runs in its caller's task, or one whose sessions are plain."""
        host = EngineHost(url=_fresh_url(tmp_path))
        ran: list[asyncio.Task[object] | None] = []

        async def attempt() -> None:
            ran.append(asyncio.current_task())

        await host.with_retry(attempt)
        session = host.session_factory()
        assert ran != [asyncio.current_task()]
        assert (type(session.sync_session), listeners(host.engine.sync_engine)) == (AttemptSession, 1)
        await host.close()

    async def test_off_sqlite_an_attempt_runs_in_its_callers_task_on_plain_sessions(
        self, tmp_path, monkeypatch
    ) -> None:
        """Guards every other engine: nothing of the cancellation rule reaches a dialect that is not SQLite."""
        # An unknown dialect is served on the generic floor under its own name.
        monkeypatch.setattr(engine_module, "profile_for", lambda _name: profile_for("duckdb"))
        host = EngineHost(url=_fresh_url(tmp_path))
        ran: list[asyncio.Task[object] | None] = []

        async def attempt() -> None:
            ran.append(asyncio.current_task())

        await host.with_retry(attempt)
        session = host.session_factory()
        assert ran == [asyncio.current_task()]
        assert (type(session.sync_session), listeners(host.engine.sync_engine)) == (Session, 0)
        await host.close()


def listeners(engine: Engine) -> int:
    """How many listeners *engine* has on the statements its connections send."""
    watched = "before_cursor_execute"
    return len(list(getattr(engine.dispatch, watched)))


# ---------------------------------------------------------------------------
# Pool exhaustion
# ---------------------------------------------------------------------------


class TestPoolExhaustion:
    async def test_pool_exhaustion_classifies_instead_of_raising(self, tmp_path) -> None:
        # sqlalchemy.exc.TimeoutError is not a DBAPIError: the verb must
        # still classify it, never leak it raw (the no-raw-raise criterion).
        arguments = {"pool_size": 1, "max_overflow": 0, "pool_timeout": 0.2}
        storage = DatabaseStorage(url=_fresh_url(tmp_path), engine_arguments=arguments)
        assert (await storage.first_touch()).success is True
        async with storage.engine.connect():  # hold the only pooled connection
            result = await storage.stat(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()


# ---------------------------------------------------------------------------
# A writer behind another writer's lock
# ---------------------------------------------------------------------------


class TestBusyWriter:
    async def test_a_write_behind_a_held_lock_gives_up_after_four_tries_and_changes_nothing(self, tmp_path) -> None:
        """Pins the busy budget the storage docstring states: five seconds a try, four tries, a retryable conflict."""
        assert "PRAGMA busy_timeout = 5000" in SQLITE.session_settings
        url = _fresh_url(tmp_path)
        storage = DatabaseStorage(url=url)
        assert storage._host._retry_attempts == 4
        assert (await storage.first_touch()).success is True
        begins: list[str] = []

        @event.listens_for(storage.engine.sync_engine, "checkout")
        def impatient(dbapi_connection, record, proxy) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout = 0")
            cursor.close()

        @event.listens_for(storage.engine.sync_engine, "before_cursor_execute")
        def begun(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement.startswith("BEGIN IMMEDIATE"):
                begins.append(statement)

        rival = sqlite3.connect(url.removeprefix("sqlite+aiosqlite:///"), isolation_level=None)
        rival.execute("BEGIN IMMEDIATE")
        refused = await storage.write(entries=[Entry(path=Path("/late.txt"), content="x")])
        assert begins == ["BEGIN IMMEDIATE"] * 4
        assert [(error.kind, error.retryable) for error in refused.errors] == [(ErrorKind.conflict, True)]
        rival.execute("COMMIT")
        rival.close()
        assert (await storage.stat(path=Path("/late.txt"))).success is False
        assert (await storage.write(entries=[Entry(path=Path("/late.txt"), content="x")])).success is True
        await storage.close()


async def _stamps(storage: DatabaseStorage) -> list[tuple[str, int]]:
    """Every row of the stamps table once *storage* has made its first touch."""
    assert (await storage.first_touch()).success is True
    revisions = storage._host.tables.principal_revisions
    async with storage._host.session_factory() as session:
        found = await session.execute(select(revisions.c.principal_id, revisions.c.revision))
        return [(row.principal_id, row.revision) for row in found]


@pytest.mark.parametrize("env_var", [pytest.param(None, id="sqlite"), *ENGINE_LEGS])
async def test_provisioning_seeds_the_everyone_stamp(env_var: str | None, tmp_path) -> None:
    """A fresh store holds the everyone stamp at zero: the row a mint's last statement locks must exist to be locked.

    Guards the seed in ``_provision``: without it the first mint on a
    fresh store finds no row to hold and is refused.
    """
    if env_var is None:
        storage = DatabaseStorage(url=_fresh_url(tmp_path))
        assert await _stamps(storage) == [(EVERYONE_NAME, 0)]
        await storage.close()
        return
    async with server_storage(env_var) as served:
        assert await _stamps(served) == [(EVERYONE_NAME, 0)]
