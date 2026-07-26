"""DatabaseStorage lifecycle tests — construction, first touch, retry, close.

The conformance suite covers verb behavior once families land; this file
holds the DB-specific contract: the construction XOR (built url vs
borrowed session factory — never a bare engine), idempotent provisioning
under the serialization point, schema-version verification, restart
rebind, cross-loop first touch, borrowed-sessions close, and the dialect
policy layer (generic floor, deferred resolution, retryable
classification).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from sqlalchemy import Select, create_engine, delete, event, insert, select, text, update
from sqlalchemy.dialects import mssql, postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from ulid import ULID

from vfs.models import Entry, Observation
from vfs.models.rows import MAX_TABLE_NAME_LENGTH, SCHEMA_FORMAT_VERSION, ULID_LENGTH, build_vfs_tables
from vfs.paths import MAX_PATH_LENGTH, ObjectKind, Path, byte_length
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.results.projection import OBSERVATION_FIELDS
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, ResolvedPair, StorageBackend, SupportsClose, SupportsTraits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MSSQL,
    MYSQL,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    StaleSnapshot,
    fan_budget,
    is_retryable,
    membership_budget,
    op_execution_options,
    profile_for,
    rows_per_statement,
    statement_budget,
    topology_execution_options,
)
from vfs.storage.backends.database.engine import EngineHost, _install_sqlite_transaction_control, advisory_key
from vfs.storage.backends.database.reads import ENTRY_OBSERVATION_FIELDS
from vfs.storage.backends.database.seams import clear, install, installed, seam
from vfs.storage.backends.database.staging import StagedEntry, WritePlan
from vfs.storage.backends.database.topology import (
    _claim,
    _purge_subtree,
    _serialize,
    _TrashChain,
    delete_rows,
    restore_rows,
    sweep_rows,
    transfer_rows,
)
from vfs.storage.backends.database.writes import (
    _CLOBBER_COLUMNS,
    _bump_by_values,
    _bump_parents,
    _bump_values_stmt,
    _catch_retry_layer,
    _classify_arbitration_loss,
    _classify_guard_misses,
    _entry_values,
    _fetch_committed,
    _finish,
    _material_values,
    _resolve_rows,
    _update_materials,
    _upsert_constructor,
    _upsert_layer,
    _values_update_stmt,
    edit_rows,
    write_rows,
)
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncConnection

    from vfs.storage.backends.database.staging import PersistenceState


def _url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite"


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
# Dialect policy — generic floor and retryable classification
# ---------------------------------------------------------------------------


class _SqliteError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("locked")
        self.sqlite_errorcode = code


class _PgError(Exception):
    def __init__(self, state: str) -> None:
        super().__init__("serialization")
        self.sqlstate = state


class _MySQLError(Exception):
    """PyMySQL-shaped: args lead with the errno; the server's SQLSTATE rides on ``sqlstate``."""

    _SQLSTATES: ClassVar[dict[int, str]] = {1213: "40001", 1205: "HY000", 1062: "23000"}

    def __init__(self, errno: int) -> None:
        super().__init__(errno, "deadlock found when trying to get lock")
        self.sqlstate = self._SQLSTATES.get(errno, "HY000")


class _OracleErrorValue:
    """The ``_Error`` object python-oracledb packs as the sole argument."""

    def __init__(self, code: int) -> None:
        self.code = code
        self.message = f"ORA-{code:05d}: fault"


class _OracleError(Exception):
    """python-oracledb-shaped: ``args = (_Error,)``, errno on ``.code``, no sqlstate."""

    def __init__(self, code: int) -> None:
        super().__init__(_OracleErrorValue(code))


class TestDialectPolicy:
    def test_unknown_dialect_serves_on_the_generic_floor(self) -> None:
        profile = profile_for("duckdb")
        assert profile.name == "duckdb"
        assert profile.key_byte_budget == GENERIC.key_byte_budget
        assert profile.arbitration == "catch_retry"

    def test_sqlite_busy_is_retryable_but_busy_snapshot_is_not(self) -> None:
        assert is_retryable(SQLITE, _SqliteError(5)) is True
        assert is_retryable(SQLITE, _SqliteError(517)) is False

    def test_serialization_sqlstates_are_retryable(self) -> None:
        assert is_retryable(POSTGRESQL, _PgError("40001")) is True
        assert is_retryable(POSTGRESQL, _PgError("40P01")) is True

    def test_unique_violation_is_never_retryable(self) -> None:
        assert is_retryable(POSTGRESQL, _PgError("23505")) is False

    def test_pyodbc_style_sqlstate_in_args_classifies(self) -> None:
        exc = Exception("40001", "deadlock victim")
        assert is_retryable(GENERIC, exc) is True

    def test_an_exception_with_no_sqlstate_is_not_retryable(self) -> None:
        assert is_retryable(GENERIC, Exception()) is False

    def test_mysql_family_is_tuned_not_generic(self) -> None:
        for name in ("mysql", "mariadb"):
            profile = profile_for(name)
            assert profile.name == name
            assert profile.key_byte_budget == MYSQL.key_byte_budget
            assert profile.arbitration == "catch_retry"
            assert profile.op_isolation == "REPEATABLE READ"

    def test_mysql_deadlock_and_lock_wait_errnos_are_retryable(self) -> None:
        assert is_retryable(MYSQL, _MySQLError(1213)) is True
        # 1205 ships under the HY000 catch-all: the sqlstate rung must
        # defer to the errno, or the declared code set is dead on MySQL.
        assert is_retryable(MYSQL, _MySQLError(1205)) is True
        # Duplicate entry is a definite exists-outcome, never retried.
        assert is_retryable(MYSQL, _MySQLError(1062)) is False
        # The errno rung is profile-scoped: the floor declares no errnos.
        assert is_retryable(GENERIC, _MySQLError(1205)) is False

    def test_oracle_is_tuned_for_retry_classification(self) -> None:
        # Budgets stay at the floor Oracle itself defines (ORA-01795);
        # the tuning is the driver-code rung — oracledb exposes no
        # sqlstate, and its errno rides args[0].code, not args[0].
        profile = profile_for("oracle")
        assert profile.name == "oracle"
        assert profile.in_list_budget == GENERIC.in_list_budget
        assert profile.key_byte_budget == GENERIC.key_byte_budget
        assert is_retryable(profile, _OracleError(60)) is True  # deadlock
        assert is_retryable(profile, _OracleError(8177)) is True  # serialization
        assert is_retryable(profile, _OracleError(1400)) is False  # NOT NULL
        assert is_retryable(GENERIC, _OracleError(60)) is False

    def test_every_lawful_path_fits_every_declared_key_budget(self) -> None:
        # The contract is byte-denominated, so the worst-case index key is
        # MAX_PATH_LENGTH bytes — the budget↔DDL gap closes by construction.
        for profile in (*PROFILES.values(), GENERIC):
            assert profile.key_byte_budget >= MAX_PATH_LENGTH

    def test_values_join_is_declared_only_where_proven(self) -> None:
        # SQLite rejects the column-aliased VALUES join despite declaring
        # update_returning — the bit is earned per engine, floor stays off.
        assert POSTGRESQL.values_join and MSSQL.values_join
        assert not SQLITE.values_join and not MYSQL.values_join and not GENERIC.values_join

    def test_parameter_budget_is_read_from_sqlalchemy(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        host = storage._host
        assert host.parameter_budget == host.engine.dialect.insertmanyvalues_max_parameters
        assert host.parameter_budget >= 999

    def test_op_execution_options_stamp_the_declared_isolation_pin(self) -> None:
        assert op_execution_options(POSTGRESQL, writer=False) == {"isolation_level": "REPEATABLE READ"}
        assert op_execution_options(POSTGRESQL, writer=True) == {
            "vfs_writer": True,
            "isolation_level": "REPEATABLE READ",
        }
        # No pin declared: readers keep the empty-options lazy checkout.
        assert op_execution_options(SQLITE, writer=False) == {}
        assert op_execution_options(SQLITE, writer=True) == {"vfs_writer": True}
        assert op_execution_options(GENERIC, writer=False) == {}

    async def test_ops_apply_a_declared_op_isolation_pin(self, tmp_path, monkeypatch) -> None:
        # SERIALIZABLE is a level the SQLite dialect accepts, so the
        # stamped connection exercises the same wiring a Postgres pin takes.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        host = storage._host
        monkeypatch.setattr(host, "_profile", replace(host.profile, op_isolation="SERIALIZABLE"))
        stamped: list[dict[str, object]] = []
        original = AsyncSession.connection

        async def spy(self: AsyncSession, **kwargs: object) -> AsyncConnection:
            stamped.append(dict(cast("dict[str, object]", kwargs.get("execution_options") or {})))
            return await original(self, **kwargs)  # ty: ignore[invalid-argument-type]

        monkeypatch.setattr(AsyncSession, "connection", spy)
        read = await storage.read(path=Path("/f.txt"))
        assert read.observations[0].content == "x"
        write = await storage.write(entries=[Entry(path=Path("/g.txt"), content="y")], overwrite=True)
        assert write.success is True
        assert {"isolation_level": "SERIALIZABLE"} in stamped  # the read op
        assert {"vfs_writer": True, "isolation_level": "SERIALIZABLE"} in stamped  # the write op
        await storage.close()

    async def test_classify_failure_survives_a_raising_is_disconnect(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host

        def broken(*args: object) -> bool:
            raise RuntimeError("driver probe blew up")

        monkeypatch.setattr(host._dialect, "is_disconnect", broken)
        error = host.classify_failure(DBAPIError("SELECT 1", None, _SqliteError(5)), context="stat")
        assert error.kind == VFSErrorKind.unavailable
        assert error.retryable is True
        await storage.close()


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
# Read family + glob — seeded directly through Core (writes land later)
# ---------------------------------------------------------------------------


async def _seed(storage: DatabaseStorage, rows: list[tuple[str, str, str | None]]) -> None:
    """Plant rows the way the write slices later will: entries + content.

    Reads land before mutations, so tests seed through Core directly —
    ancestors are minted as directories, files get a content row, and
    every row gets a distinct version.
    """
    assert (await storage.first_touch()).success is True
    tables = storage._host.tables
    now = datetime.now(UTC)
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_writer": True})
        root_key = (await conn.execute(select(tables.entry.c.entry_id).where(tables.entry.c.path == "/"))).scalar_one()
        ids: dict[str, str] = {"/": root_key}
        version = 0

        async def ensure(path: str, kind: str, content: str | None) -> None:
            nonlocal version
            if path in ids:
                return
            parent = path.rsplit("/", 1)[0] or "/"
            if parent not in ids:
                await ensure(parent, "directory", None)
            version += 1
            entry_key = str(ULID())
            await conn.execute(
                insert(tables.entry).values(
                    entry_id=entry_key,
                    parent_id=ids[parent],
                    path=path,
                    name=path.rsplit("/", 1)[1],
                    kind=kind,
                    version=version,
                    size_bytes=len(content.encode()) if content is not None else 0,
                    lines=content.count("\n") + 1 if content else 0,
                    created_at=now,
                    updated_at=now,
                )
            )
            ids[path] = entry_key
            if content is not None:
                await conn.execute(insert(tables.content).values(entry_id=entry_key, created_at=now, content=content))

        for path, kind, content in rows:
            await ensure(path, kind, content)
        await session.commit()


class TestReadFamily:
    """Verb behavior over seeded rows — the slice's own verification.

    The conformance suite exercises these paths in full once the write
    slice lands (its fixtures are built through the mutation verbs);
    until then these tests are what proves the read family.
    """

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(
            storage,
            [
                ("/top.txt", "file", "hello world"),
                ("/docs/Zed.txt", "file", "zulu"),
                ("/docs/a.txt", "file", "alpha"),
                ("/docs/b.md", "file", "bravo"),
                ("/docs/sub/c.txt", "file", "charlie"),
            ],
        )
        yield storage
        await storage.close()

    async def test_read_returns_content(self, storage: DatabaseStorage) -> None:
        result = await storage.read(path=Path("/docs/a.txt"))
        assert result.success is True
        row = result.observations[0]
        assert row.content == "alpha"
        assert row.kind == "file"
        assert row.version is not None
        assert "content" in row.populated

    async def test_read_on_a_directory_is_wrong_kind(self, storage: DatabaseStorage) -> None:
        result = await storage.read(path=Path("/docs"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert "Is a directory" in result.errors[0].message

    async def test_read_batch_keeps_good_rows_and_classifies_misses(self, storage: DatabaseStorage) -> None:
        targets = [Observation(path=Path("/docs/a.txt")), Observation(path=Path("/missing.txt"))]
        result = await storage.read(observations=targets)
        assert result.success is False
        assert [o.path for o in result.observations] == ["/docs/a.txt"]
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert (result.errors[0].data or {})["target"] == "/missing.txt"

    async def test_stat_shapes_and_mask(self, storage: DatabaseStorage) -> None:
        file_row = (await storage.stat(path=Path("/docs/a.txt"))).observations[0]
        assert file_row.kind == "file"
        assert file_row.size_bytes == len(b"alpha")
        assert file_row.content is None
        assert {"path", "kind", "version"} <= file_row.populated

        dir_row = (await storage.stat(path=Path("/docs"))).observations[0]
        assert dir_row.kind == "directory"
        assert dir_row.size_bytes is None  # the NOT NULL 0 never reads as a size
        assert "size_bytes" in dir_row.populated  # fetched-and-null stays masked

    async def test_missing_ancestor_classifies_not_found_at_that_component(self, storage: DatabaseStorage) -> None:
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/ghost/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.not_found
            assert result.errors[0].path == "/ghost"

    async def test_file_ancestor_classifies_wrong_kind_at_that_component(self, storage: DatabaseStorage) -> None:
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/top.txt/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.wrong_kind
            assert result.errors[0].path == "/top.txt"

    async def test_sibling_misses_under_one_dead_ancestor_stay_distinct(self, storage: DatabaseStorage) -> None:
        targets = [Observation(path=Path("/dead/x")), Observation(path=Path("/dead/y"))]
        result = await storage.stat(observations=targets)
        assert len(result.errors) == 2
        assert {(e.data or {}).get("target") for e in result.errors} == {"/dead/x", "/dead/y"}

    async def test_ls_orders_children_by_byte_value(self, storage: DatabaseStorage) -> None:
        result = await storage.ls(path=Path("/docs"))
        assert [o.path for o in result.observations] == [
            "/docs/Zed.txt",  # Z (0x5A) sorts before a (0x61) under binary collation
            "/docs/a.txt",
            "/docs/b.md",
            "/docs/sub",
        ]

    async def test_ls_defaults_to_the_root(self, storage: DatabaseStorage) -> None:
        result = await storage.ls()
        assert [o.path for o in result.observations] == ["/docs", "/top.txt"]

    async def test_ls_file_target_lists_itself(self, storage: DatabaseStorage) -> None:
        result = await storage.ls(path=Path("/top.txt"))
        assert [o.path for o in result.observations] == ["/top.txt"]

    async def test_tree_orders_by_path_and_budgets_depth(self, storage: DatabaseStorage) -> None:
        full = await storage.tree(path=Path("/docs"))
        assert [o.path for o in full.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/b.md",
            "/docs/sub",
            "/docs/sub/c.txt",
        ]
        shallow = await storage.tree(path=Path("/docs"), max_depth=1)
        assert [o.path for o in shallow.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/b.md",
            "/docs/sub",
        ]

    async def test_tree_from_the_root_excludes_the_root_row(self, storage: DatabaseStorage) -> None:
        result = await storage.tree(path=Path("/"), max_depth=1)
        assert [o.path for o in result.observations] == ["/docs", "/top.txt"]

    async def test_tree_on_a_file_returns_just_that_row(self, storage: DatabaseStorage) -> None:
        result = await storage.tree(path=Path("/top.txt"))
        assert [o.path for o in result.observations] == ["/top.txt"]

    async def test_tree_rejects_a_sub_one_max_depth_without_touching_the_database(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.tree(path=Path("/"), max_depth=0)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert storage.mount_identity is None  # refused before first touch
        await storage.close()

    async def test_projection_narrows_the_select_and_stamps_the_mask(self, storage: DatabaseStorage) -> None:
        result = await storage.stat(path=Path("/docs/a.txt"), columns=frozenset({"size_bytes", "mime_type"}))
        row = result.observations[0]
        assert row.populated == {"path", "kind", "version", "size_bytes", "mime_type"}
        assert row.mime_type is None  # fetched, and null
        assert row.content_hash is None
        assert "content_hash" not in row.populated  # not fetched

    async def test_read_projection_controls_the_content_fetch(self, storage: DatabaseStorage) -> None:
        without = (await storage.read(path=Path("/docs/a.txt"), columns=frozenset({"path"}))).observations[0]
        assert without.content is None
        assert "content" not in without.populated
        with_content = (await storage.read(path=Path("/docs/a.txt"), columns=frozenset({"content"}))).observations[0]
        assert with_content.content == "alpha"
        assert "content" in with_content.populated

    async def test_projection_of_an_unbacked_field_serves_identity_only(self, storage: DatabaseStorage) -> None:
        # A requested field with no entries-table column is dropped from
        # the mask, never a raw column lookup that would raise past _execute.
        result = await storage.stat(path=Path("/docs/a.txt"), columns=frozenset({"score", "content"}))
        assert result.success is True
        assert result.observations[0].populated == {"path", "kind", "version"}

    def test_entry_observation_fields_track_the_column_vocabulary(self) -> None:
        # Drift pin: the servable set is exactly the Observation fields
        # the entries table backs — a new mirrored column must land here.
        cols = {c.name for c in build_vfs_tables(table_name="vfs").entry.columns}
        assert OBSERVATION_FIELDS & cols == ENTRY_OBSERVATION_FIELDS

    async def test_glob_matches_names_and_full_paths(self, storage: DatabaseStorage) -> None:
        by_name = await storage.glob(pattern="*.txt")
        assert [o.path for o in by_name.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/sub/c.txt",
            "/top.txt",
        ]
        by_path = await storage.glob(pattern="/docs/*.txt")
        assert [o.path for o in by_path.observations] == ["/docs/Zed.txt", "/docs/a.txt", "/docs/sub/c.txt"]

    async def test_glob_scope_ext_and_max_count(self, storage: DatabaseStorage) -> None:
        scoped = await storage.glob(pattern="*", paths=(Path("/docs"),))
        assert all(str(o.path).startswith("/docs") for o in scoped.observations)
        by_ext = await storage.glob(pattern="*", ext=("md",))
        assert [o.path for o in by_ext.observations] == ["/docs/b.md"]
        capped = await storage.glob(pattern="*.txt", max_count=2)
        assert len(capped.observations) == 2

    async def test_glob_character_class_falls_back_to_fnmatch(self, storage: DatabaseStorage) -> None:
        result = await storage.glob(pattern="[ab]*.txt")
        assert [o.path for o in result.observations] == ["/docs/a.txt"]

    async def test_glob_escapes_like_metacharacters(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/da_a.txt", "file", "x"), ("/daxa.txt", "file", "x")])
        result = await storage.glob(pattern="da_a.txt")
        assert [o.path for o in result.observations] == ["/da_a.txt"]
        await storage.close()

    async def test_read_family_emits_selects_only_and_ls_keys_on_parent_id(self, tmp_path) -> None:
        # The module docstring's statement-shape promises, pinned the way
        # the write family pins its counts: SELECTs only, and ls children
        # come from parent_id equality — never a path prefix scan.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/docs/a.txt", "file", "alpha")])
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        assert (await storage.read(path=Path("/docs/a.txt"))).success is True
        assert (await storage.stat(path=Path("/docs/a.txt"))).success is True
        assert (await storage.ls(path=Path("/docs"))).success is True
        assert (await storage.tree(path=Path("/"))).success is True
        assert (await storage.glob(pattern="*.txt")).success is True
        queries = [s for s in statements if not s.startswith(("BEGIN", "COMMIT", "ROLLBACK", "PRAGMA"))]
        assert queries and all(s.lstrip().startswith("SELECT") for s in queries), queries
        children = [s for s in queries if "parent_id IN" in s]
        assert children, queries
        await storage.close()

    async def test_anchor_escaping_bounds_tree_and_scoped_glob(self, tmp_path) -> None:
        # The anchor-side LIKE is the sole subtree filter for both verbs:
        # a metacharacter in a directory name must not widen the scope.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/da_a/x.txt", "file", "in"), ("/daxa/y.txt", "file", "out")])
        subtree = await storage.tree(path=Path("/da_a"))
        assert [str(o.path) for o in subtree.observations] == ["/da_a/x.txt"]
        scoped = await storage.glob(pattern="*", paths=(Path("/da_a"),))
        assert [str(o.path) for o in scoped.observations] == ["/da_a", "/da_a/x.txt"]
        await storage.close()


class TestNamespaceScopes:
    """The meta-scope liveness filter: hidden by default, served when anchored."""

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(
            storage,
            [
                ("/real.txt", "file", "needle in the open"),
                ("/.vfs/docs/a.txt", "file", "meta doc text"),
                ("/.vfs/trash/bucket/01ARZ", "file", "needle in the trash"),
            ],
        )
        yield storage
        await storage.close()

    async def test_enumeration_hides_the_meta_subtree(self, storage: DatabaseStorage) -> None:
        assert [o.path for o in (await storage.ls(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.tree(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.glob(pattern="*")).observations] == ["/real.txt"]

    async def test_direct_meta_address_bypasses_the_meta_exclusion(self, storage: DatabaseStorage) -> None:
        doc = Path("/.vfs/docs/a.txt")
        stat = await storage.stat(path=doc)
        assert stat.success is True
        assert stat.observations[0].kind == "file"
        read = await storage.read(path=doc)
        assert read.observations[0].content == "meta doc text"
        listing = await storage.ls(path=doc.parent_dir)
        assert [o.path for o in listing.observations] == [str(doc)]

    async def test_batch_ls_keeps_liveness_scopes_apart(self, storage: DatabaseStorage) -> None:
        # One batch, both liveness classes: the meta anchor serves its
        # children while the non-meta parent's listing stays meta-free.
        batch = [Observation(path=Path("/")), Observation(path=Path("/.vfs"))]
        listing = await storage.ls(observations=batch)
        assert listing.success is True
        assert [str(o.path) for o in listing.observations] == ["/real.txt", "/.vfs/docs", "/.vfs/trash"]

    async def test_glob_meta_bypass_is_per_anchor_not_query_wide(self, storage: DatabaseStorage) -> None:
        # ROOT plus a meta anchor: the meta arm serves only its own
        # subtree — /.vfs itself and sibling meta trees stay hidden.
        result = await storage.glob(pattern="*", paths=(Path("/"), Path("/.vfs/trash")))
        assert [str(o.path) for o in result.observations] == [
            "/.vfs/trash",
            "/.vfs/trash/bucket",
            "/.vfs/trash/bucket/01ARZ",
            "/real.txt",
        ]

    async def test_trash_serves_beside_other_meta_children_when_anchored(self, storage: DatabaseStorage) -> None:
        # Trash is an ordinary meta subtree: an ls of /.vfs lists it.
        listing = await storage.ls(path=Path("/.vfs"))
        assert [o.path for o in listing.observations] == ["/.vfs/docs", "/.vfs/trash"]
        subtree = await storage.tree(path=Path("/.vfs"))
        assert "/.vfs/trash/bucket/01ARZ" in [str(o.path) for o in subtree.observations]

    async def test_a_trash_side_path_serves_through_every_read_verb(self, storage: DatabaseStorage) -> None:
        trashed = Path("/.vfs/trash/bucket/01ARZ")
        assert (await storage.read(path=trashed)).observations[0].content == "needle in the trash"
        assert (await storage.stat(path=trashed)).observations[0].kind == "file"
        listing = await storage.ls(path=trashed.parent_dir)
        assert [o.path for o in listing.observations] == [str(trashed)]
        scoped = await storage.glob(pattern="*", paths=(Path("/.vfs/trash"),))
        assert str(trashed) in [str(o.path) for o in scoped.observations]

    async def test_descent_through_a_trash_side_file_takes_the_standard_ladder(self, storage: DatabaseStorage) -> None:
        # A child under a trash-side FILE classifies wrong_kind naming the
        # file — identical to descent anywhere else in the namespace.
        result = await storage.read(path=Path("/.vfs/trash/bucket/01ARZ/child"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/.vfs/trash/bucket/01ARZ"

    async def test_trash_misses_classify_at_their_first_failing_component(self, storage: DatabaseStorage) -> None:
        # The standard descent ladder, not a uniform concealment shape:
        # each miss names its own first missing ancestor.
        under_real_bucket = await storage.stat(path=Path("/.vfs/trash/bucket/GHOST/x"))
        assert under_real_bucket.errors[0].kind == VFSErrorKind.not_found
        assert under_real_bucket.errors[0].path == "/.vfs/trash/bucket/GHOST"
        under_no_bucket = await storage.stat(path=Path("/.vfs/trash/NOBUCKET/x"))
        assert under_no_bucket.errors[0].kind == VFSErrorKind.not_found
        assert under_no_bucket.errors[0].path == "/.vfs/trash/NOBUCKET"


class TestReadFailureHandling:
    """Driver failures classify; retryable outcomes restart the method."""

    async def test_read_failure_classifies_unavailable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.begin() as conn:
            await conn.exec_driver_sql("DROP TABLE vfs")
        result = await storage.stat(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()

    async def test_with_retry_restarts_on_a_retryable_error(self, tmp_path) -> None:
        host = EngineHost(url=_url(tmp_path), retry_base_delay=0.001)
        calls = 0

        async def flaky() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise DBAPIError("SELECT 1", None, _SqliteError(5))
            return "served"

        assert await host.with_retry(flaky) == "served"
        assert calls == 2
        await host.close()

    async def test_with_retry_gives_up_after_the_attempt_budget(self, tmp_path) -> None:
        # Exhaustion has one channel: a retryable engine outcome leaves as
        # StaleSnapshot with the native error as its cause, never raw.
        host = EngineHost(url=_url(tmp_path), retry_attempts=2, retry_base_delay=0.001)

        async def always_busy() -> None:
            raise DBAPIError("SELECT 1", None, _SqliteError(5))

        with pytest.raises(StaleSnapshot) as caught:
            await host.with_retry(always_busy)
        assert isinstance(caught.value.__cause__, DBAPIError)
        assert "outlived 2 attempts" in caught.value.context

        async def never_retryable() -> None:
            raise DBAPIError("SELECT 1", None, _SqliteError(1))

        with pytest.raises(DBAPIError):
            await host.with_retry(never_retryable)
        await host.close()

    async def test_write_failure_classifies_unavailable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.begin() as conn:
            await conn.exec_driver_sql("DROP TABLE vfs")
        result = await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()

    async def test_unreachable_database_refuses_stub_verbs_classified(self, tmp_path) -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/absent/vfs.sqlite")
        result = await storage.grep(pattern="x")  # a stub verb still gates on first touch
        assert result.ops == ("grep",)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert "First touch failed" in result.errors[0].message
        await storage.close()


class TestUnlandedVerbStubs:
    """Every undeclared verb refuses classified; capabilities stay honest."""

    async def test_unlanded_verbs_refuse_as_unsupported(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        calls = [
            storage.grep(pattern="x"),
            storage.mkedge(source=Path("/a"), target=Path("/b"), edge_type="imports"),
        ]
        for call in calls:
            result = await call
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.unsupported
        stubbed = {"grep", "mkedge"}
        assert storage.capabilities() == {
            "read",
            "stat",
            "ls",
            "tree",
            "glob",
            "write",
            "edit",
            "mkdir",
            "delete",
            "restore",
            "sweep",
            "move",
            "copy",
        }
        assert storage.capabilities().isdisjoint(stubbed)
        await storage.close()

    async def test_mutation_verbs_surface_the_first_touch_refusal(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        result = await stale.write(entries=[Entry(path=Path("/a"), content="x")])
        assert result.errors[0].kind == VFSErrorKind.schema_mismatch
        await stale.close()

    async def test_reads_with_no_targets_return_an_empty_success(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.read()
        assert result.success is True
        assert result.observations == []
        await storage.close()


class TestUnicodeAndCollation:
    """Binary collation over non-ASCII names — ordering and case sensitivity."""

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        # Case pair as siblings plus ASCII/Greek/CJK/emoji names — distinct
        # rows must coexist and order by UTF-8 byte value.
        self.names = ["A.txt", "a.txt", "Z.txt", "é.txt", "Ω.txt", "中.txt", "😀.txt"]
        await _seed(storage, [(f"/dir/{name}", "file", "x") for name in self.names])
        yield storage
        await storage.close()

    async def test_ls_orders_unicode_names_like_python_codepoint_sort(self, storage: DatabaseStorage) -> None:
        # UTF-8 byte order equals codepoint order, so the binary-collated
        # column must reproduce Python's str sort exactly.
        result = await storage.ls(path=Path("/dir"))
        assert [o.path.name for o in result.observations] == sorted(self.names)

    async def test_case_pair_siblings_are_distinct_rows(self, storage: DatabaseStorage) -> None:
        upper = await storage.stat(path=Path("/dir/A.txt"))
        lower = await storage.stat(path=Path("/dir/a.txt"))
        assert upper.success is True and lower.success is True
        assert upper.observations[0].version != lower.observations[0].version

    async def test_glob_stays_case_sensitive_through_the_pool(self, storage: DatabaseStorage) -> None:
        # The LIKE prefilter must not case-fold: case_sensitive_like=ON is
        # stamped per checkout, and fnmatchcase is the authority.
        result = await storage.glob(pattern="A*")
        assert [o.path.name for o in result.observations] == ["A.txt"]

    async def test_point_read_misses_on_case_difference(self, storage: DatabaseStorage) -> None:
        result = await storage.stat(path=Path("/dir/a.TXT"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found


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


# ---------------------------------------------------------------------------
# Mutation core — DB-specific contract beyond the conformance suite
# ---------------------------------------------------------------------------


class TestWriteMechanics:
    """One transaction per batch, bounded statements, per-entry versions."""

    def test_material_values_and_clobber_columns_stay_in_lockstep(self) -> None:
        # Two encodings of the material-column set, one invariant: a key
        # added to either alone silently diverges create vs overwrite.
        staged = StagedEntry(
            path=Path("/f.txt"), parent=Path("/"), kind="file", persistence="insert", entry_id=str(ULID()), content="x"
        )
        material = _material_values(staged, "someone", datetime.now(UTC))
        assert set(material) == set(_CLOBBER_COLUMNS)

    async def test_failed_batch_commits_nothing(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        good = await storage.write(entries=[Entry(path=Path("/keep.txt"), content="x")])
        assert good.success is True
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            rows_before = len((await conn.execute(select(tables.entry.c.id))).all())
        bad = await storage.write(
            entries=[Entry(path=Path("/new.txt"), content="y"), Entry(path=Path("/ghost/deep.txt"), content="z")]
        )
        assert bad.success is False
        async with storage._host.engine.connect() as conn:
            rows_after = len((await conn.execute(select(tables.entry.c.id))).all())
            orphans = (await conn.execute(select(tables.content.c.entry_id))).all()
        assert rows_after == rows_before
        assert len(orphans) == 1  # /keep.txt only
        await storage.close()

    async def test_batch_statement_count_is_bounded_by_tables_not_entries(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        entries = [Entry(path=Path(f"/f{i:03}.txt"), content=f"body {i}") for i in range(100)]
        result = await storage.write(entries=entries)
        assert result.success is True
        assert len(result.observations) == 100
        # BEGIN + session PRAGMAs + plan select + one insert chunk +
        # content delete/insert + parent bump — O(tables), never O(entries).
        assert len(statements) <= 12, statements
        await storage.close()

    async def test_write_statement_counts_are_pinned(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        def mutations() -> list[str]:
            control = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE")
            return [s for s in statements if not s.startswith(control)]

        created = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="a")])
        assert created.success is True
        # The round-trip budget is a contract: fetch, insert, content
        # delete + insert, parent bump.
        assert len(mutations()) == 5, mutations()
        statements.clear()
        overwritten = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="b")])
        assert overwritten.success is True
        # Fetch, guarded update, content delete + insert — the update is
        # attributed from its own statement, so no read-back appears.
        assert len(mutations()) == 4, mutations()
        await storage.close()

    async def test_revisions_are_per_entry_and_survive_restart(self, tmp_path) -> None:
        first = DatabaseStorage(url=_url(tmp_path))
        created = await first.write(entries=[Entry(path=Path("/docs/a.txt"), content="1")], parents=True)
        assert created.observations[0].version == 1
        minted = (await first.stat(path=Path("/docs"))).observations[0]
        assert minted.version == 1  # minted ancestors are fresh rows too
        await first.close()
        second = DatabaseStorage(url=_url(tmp_path))
        overwritten = await second.write(entries=[Entry(path=Path("/docs/a.txt"), content="2")])
        assert overwritten.observations[0].version == 2  # base + 1 off the row, no mount state
        await second.close()

    async def test_unchanged_directory_reports_the_sibling_bump(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/docs"))
        result = await storage.write(
            entries=[Entry(path=Path("/docs"), kind="directory"), Entry(path=Path("/docs/new.txt"), content="x")]
        )
        assert result.success is True
        by_path = {str(o.path): o for o in result.observations}
        assert by_path["/docs"].status == "unchanged"
        stat = (await storage.stat(path=Path("/docs"))).observations[0]
        assert by_path["/docs"].version == stat.version
        await storage.close()

    async def test_overwrite_restamps_the_owner(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")], user_id="alice")
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="b")], user_id="bob")
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            owner = (await conn.execute(select(entry.c.owner_id).where(entry.c.path == "/f.txt"))).scalar_one()
        assert owner == "bob"
        await storage.close()

    async def test_overwrite_preserves_entry_identity(self, tmp_path) -> None:
        # Durable references (versions, chunks, edges) hang off entry_id:
        # an overwrite must update the row in place, never re-mint it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")])
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            minted = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).scalar_one()
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="b")])).success is True
        async with storage._host.engine.connect() as conn:
            rows = (await conn.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == "/f.txt"))).all()
        assert rows == [(minted, 2)]  # same row, only the version moved
        await storage.close()

    async def test_over_key_byte_budget_classifies_unaddressable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, key_byte_budget=32)
        long_path = Path("/" + "x" * 60 + ".txt")
        written = await storage.write(entries=[Entry(path=long_path, content="x")])
        assert written.success is False
        assert written.errors[0].kind == VFSErrorKind.unaddressable
        made = await storage.mkdir(path=Path("/" + "d" * 60))
        assert made.success is False
        assert made.errors[0].kind == VFSErrorKind.unaddressable
        await storage.close()

    async def test_edit_of_a_missing_target_classifies_at_the_failing_component(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        result = await storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/ghost/a.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert result.errors[0].path == "/ghost"
        await storage.close()

    async def test_unchanged_directory_observation_reads_back_its_bump(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        result = await storage.write(
            entries=[Entry(path=Path("/d"), kind="directory"), Entry(path=Path("/d/f.txt"), content="x")]
        )
        assert result.success is True
        observed = {str(o.path): o for o in result.observations}
        assert observed["/d"].status == "unchanged"
        stat = await storage.stat(path=Path("/d"))
        assert observed["/d"].version == stat.observations[0].version == 2
        await storage.close()

    def test_stage_create_folds_a_repeat_target_into_one_row(self) -> None:
        plan = WritePlan({}, user_id=None, budget=SQLITE.key_byte_budget)
        target = Path("/f.txt")
        plan.stage_create(target, kind="file", content="one", content_hash="h1", size_bytes=3, lines=1)
        minted = plan.staged[target].entry_id
        plan.stage_create(target, kind="file", content="two", content_hash="h2", size_bytes=3, lines=1)
        assert list(plan.staged) == [target]
        assert plan.staged[target].entry_id == minted
        assert plan.staged[target].persistence == "insert"
        assert (plan.staged[target].content, plan.staged[target].content_hash) == ("two", "h2")


class TestTrashWritability:
    """Trash is an ordinary write target: standard gates, no trash-specific arm."""

    async def test_write_into_trash_mints_the_bucket_chain_and_reads_back(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        target = Path("/.vfs/trash/2026-07-18-10/x.txt")
        written = await storage.write(entries=[Entry(path=target, kind="file", content="x")], parents=True)
        assert written.success is True
        assert written.observations[0].status == "created"
        assert (await storage.read(path=target)).observations[0].content == "x"
        bucket = (await storage.stat(path=target.parent_dir)).observations[0]
        assert bucket.kind == "directory"
        listing = await storage.ls(path=target.parent_dir)
        assert [o.path for o in listing.observations] == [str(target)]
        await storage.close()

    async def test_mkdir_and_edit_under_trash_take_the_ordinary_paths(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        bucket = Path("/.vfs/trash/2026-07-18-10")
        assert (await storage.mkdir(path=bucket, parents=True)).success is True
        target = bucket / "x.txt"
        await storage.write(entries=[Entry(path=target, kind="file", content="old text")])
        edited = await storage.edit(path=target, edits=[EditOperation(old="old", new="new")])
        assert edited.success is True
        assert (await storage.read(path=target)).observations[0].content == "new text"
        await storage.close()

    async def test_trash_writes_fail_through_the_standard_error_arms(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        target = Path("/.vfs/trash/2026-07-18-10/x.txt")
        await storage.write(entries=[Entry(path=target, kind="file", content="x")], parents=True)
        taken = await storage.write(entries=[Entry(path=target, kind="file", content="y")], overwrite=False)
        assert taken.errors[0].kind == VFSErrorKind.exists
        through_file = await storage.mkdir(path=target / "sub", parents=True)
        assert through_file.errors[0].kind == VFSErrorKind.wrong_kind
        assert through_file.errors[0].path == str(target)
        orphan = Entry(path=Path("/.vfs/trash/GHOST/y.txt"), kind="file", content="y")
        no_parents = await storage.write(entries=[orphan])
        assert no_parents.errors[0].kind == VFSErrorKind.not_found
        await storage.close()

    async def test_meta_paths_beside_trash_still_write(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        doc = Path("/.vfs/docs/a.txt")
        result = await storage.write(entries=[Entry(path=doc, kind="file", content="v1")], parents=True)
        assert result.success is True
        assert (await storage.read(path=doc)).observations[0].content == "v1"
        await storage.close()


class TestArbitration:
    """Both arbitration arms resolve conflicts the plan could not see."""

    async def test_catch_retry_arm_serves_the_write_family(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, arbitration="catch_retry")
        result = await storage.write(
            entries=[Entry(path=Path("/d"), kind="directory"), Entry(path=Path("/d/f.txt"), content="x")]
        )
        assert result.success is True
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "x"
        again = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="y")])
        assert again.observations[0].status == "updated"
        await storage.close()

    async def test_catch_retry_serves_engines_without_multirow_insert(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, arbitration="catch_retry")
        # Oracle's posture: no multirow VALUES — the insert must take
        # driver executemany; identity is minted at staging, nothing read back.
        monkeypatch.setattr(storage._host.engine.sync_engine.dialect, "supports_multivalues_insert", False)
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        entries = [Entry(path=Path(f"/bulk/d{i // 10}/f{i:03}.txt"), content=f"v{i}") for i in range(50)]
        written = await storage.write(entries=entries, parents=True)
        assert written.success is True, written.errors[:3]
        created = [o for o in written.observations if str(o.path).endswith(".txt")]
        assert len(created) == 50
        # "Nothing read back" is a pin: one plan-fetch SELECT, then three
        # depth-layer inserts, content delete + insert, parent bump.
        shapes = [s.split(None, 1)[0] for s in statements if not s.startswith(("BEGIN", "SAVEPOINT", "RELEASE"))]
        assert shapes == ["SELECT", "INSERT", "INSERT", "INSERT", "DELETE", "INSERT", "UPDATE"], statements
        assert (await storage.read(path=Path("/bulk/d0/f007.txt"))).observations[0].content == "v7"
        again = await storage.write(entries=[Entry(path=Path("/bulk/d0/f007.txt"), content="y")])
        assert again.observations[0].status == "updated"
        await storage.close()

    async def test_conflicted_chunk_resolves_alone_not_the_layer(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f005.txt"), content="rival")])
        entry = storage._host.tables.entry
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            rival_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f005.txt"))).scalar_one()
            now = datetime.now(UTC)
            layer = [
                StagedEntry(
                    path=Path(f"/f{i:03}.txt"),
                    parent=Path("/"),
                    kind="file",
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )
                for i in range(12)
            ]
            rows = [_entry_values(s, root_key, None, now) for s in layer]
            statements.clear()
            errors = await _catch_retry_layer(session, entry, layer, rows, 4, overwrite=True)
        assert errors == []
        assert layer[5].persistence == "absorb" and layer[5].entry_id == rival_key  # rival's row absorbed the write
        assert all(s.persistence == "insert" for i, s in enumerate(layer) if i != 5)
        # One conflict re-drives its own 4-row chunk, never the 12-row layer:
        # three chunk inserts, four row retries, one occupant probe.
        inserts = [s for s in statements if s.startswith("INSERT INTO")]
        probes = [s for s in statements if s.lstrip().startswith("SELECT")]
        assert len(inserts) == 3 + 4, statements
        assert len(probes) == 1, statements
        await storage.close()

    async def test_conflicts_in_separate_chunks_all_classify(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(
            entries=[Entry(path=Path("/f001.txt"), content="rival"), Entry(path=Path("/f009.txt"), content="rival")]
        )
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            now = datetime.now(UTC)
            layer = [
                StagedEntry(
                    path=Path(f"/f{i:03}.txt"),
                    parent=Path("/"),
                    kind="file",
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )
                for i in range(12)
            ]
            rows = [_entry_values(s, root_key, None, now) for s in layer]
            errors = await _catch_retry_layer(session, entry, layer, rows, 4, overwrite=False)
        # Rivals sit in chunks 1 and 3: both classify — errors accumulate
        # across conflicted chunks, the last chunk never wins alone.
        assert sorted((e.kind, str(e.path)) for e in errors) == [
            (VFSErrorKind.exists, "/f001.txt"),
            (VFSErrorKind.exists, "/f009.txt"),
        ]
        await storage.close()

    async def test_resolve_rows_converts_or_classifies_per_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="rival")])
        await storage.mkdir(path=Path("/dir"))
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            rival_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).scalar_one()
            now = datetime.now(UTC)

            def staged_for(path: str, kind: ObjectKind) -> StagedEntry:
                return StagedEntry(
                    path=Path(path),
                    parent=Path("/"),
                    kind=kind,
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )

            # overwrite=True over a rival file: converted to a clobbering
            # update that adopts the rival row's identity.
            clobber = staged_for("/f.txt", "file")
            errors = await _resolve_rows(
                session, entry, [clobber], [_entry_values(clobber, root_key, None, now)], overwrite=True
            )
            assert errors == []
            assert clobber.persistence == "absorb" and clobber.entry_id == rival_key

            # overwrite=False over a rival file: a definite exists outcome.
            refused = staged_for("/f.txt", "file")
            errors = await _resolve_rows(
                session, entry, [refused], [_entry_values(refused, root_key, None, now)], overwrite=False
            )
            assert [e.kind for e in errors] == [VFSErrorKind.exists]

            # overwrite=True where the rival is a directory: wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await _resolve_rows(
                session, entry, [blocked], [_entry_values(blocked, root_key, None, now)], overwrite=True
            )
            assert [e.kind for e in errors] == [VFSErrorKind.wrong_kind]

            # a directory create losing to a directory at the matching
            # address adopts it: mkdir-p forgiveness, no error.
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            dir_adopt = staged_for("/dir", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_adopt], [_entry_values(dir_adopt, root_key, None, now)], overwrite=True
            )
            assert errors == []
            assert dir_adopt.persistence == "adopt" and dir_adopt.entry_id == dir_key

            # a directory create losing to a file occupant: exists.
            dir_loss = staged_for("/f.txt", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_loss], [_entry_values(dir_loss, root_key, None, now)], overwrite=False
            )
            assert [e.kind for e in errors] == [VFSErrorKind.exists]
        await storage.close()

    async def test_resolve_rows_redrives_when_no_occupant_is_observable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="rival")])
        await storage.mkdir(path=Path("/dir"))
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            # The unique path index collides while (parent_id, name) is
            # vacant: the insert fails yet the occupant probe sees nothing.
            phantom = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/dir"),
                kind="file",
                persistence="insert",
                entry_id=str(ULID()),
                content="mine",
            )
            minted = phantom.entry_id
            with pytest.raises(StaleSnapshot):
                await _resolve_rows(
                    session,
                    entry,
                    [phantom],
                    [_entry_values(phantom, dir_key, None, datetime.now(UTC))],
                    overwrite=True,
                )
        assert phantom.persistence == "insert" and phantom.entry_id == minted  # no conversion happened
        await storage.close()

    async def test_create_to_clobber_conversion_flows_through_apply(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        profile = replace(host.profile, arbitration="catch_retry")
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            ext=mine.ext,
            mime_type=mine.mime_type,
            overwrite=True,
            parents=False,
        )
        assert status == "created" and plan.errors == []
        plan.pending.append((target, status))

        # A rival lands between the snapshot and execution.
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success is True
        entry = host.tables.entry
        async with host.session_factory() as peek:
            rival_key = (await peek.execute(select(entry.c.entry_id).where(entry.c.path == str(target)))).scalar_one()

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=True,
            )
            await writer.commit()

        # The losing create clobbered the rival's row: identity kept, the
        # version advanced SQL-side, and the observation equals a stat.
        assert result.success is True
        assert [(o.status, o.version) for o in result.observations] == [("created", 2)]
        async with host.session_factory() as peek:
            rows = (
                await peek.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == str(target)))
            ).all()
        assert rows == [(rival_key, 2)]
        assert (await storage.read(path=target)).observations[0].content == "mine"
        await storage.close()

    async def test_upsert_clobber_stays_insert_through_apply(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        assert host.profile.arbitration == "upsert"
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=host.profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            ext=mine.ext,
            mime_type=mine.mime_type,
            overwrite=True,
            parents=False,
        )
        assert status == "created" and plan.errors == []
        plan.pending.append((target, status))

        # A rival lands between the snapshot and execution.
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success is True
        entry = host.tables.entry
        async with host.session_factory() as peek:
            rival_key = (await peek.execute(select(entry.c.entry_id).where(entry.c.path == str(target)))).scalar_one()

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=True,
            )
            await writer.commit()

        # The upsert clobber already wrote the final row, so the staged
        # entry stays "insert" and no update pass bumps it a second time.
        assert result.success is True
        assert [(o.status, o.version) for o in result.observations] == [("created", 2)]
        staged = plan.staged[target]
        assert staged.persistence == "insert" and staged.entry_id == rival_key
        async with host.session_factory() as peek:
            rows = (
                await peek.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == str(target)))
            ).all()
        assert rows == [(rival_key, 2)]
        assert (await storage.read(path=target)).observations[0].content == "mine"
        await storage.close()

    async def test_upsert_layer_adopts_identity_or_classifies_per_rival(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="rival")])
        await storage.mkdir(path=Path("/dir"))
        entry = storage._host.tables.entry
        profile = storage._host.profile
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            rival = (
                await conn.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == "/f.txt"))
            ).one()
            now = datetime.now(UTC)

            def staged_for(path: str, kind: ObjectKind) -> StagedEntry:
                return StagedEntry(
                    path=Path(path),
                    parent=Path("/"),
                    kind=kind,
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )

            async def run(layer: list[StagedEntry], *, overwrite: bool) -> list[ResultError]:
                rows = [_entry_values(s, root_key, None, now) for s in layer]
                return await _upsert_layer(session, entry, profile, layer, rows, 50, overwrite=overwrite)

            # overwrite=True over a rival file: the clobber lands on the
            # rival's row and adopts its identity and bumped version...
            clobber = staged_for("/f.txt", "file")
            fresh = staged_for("/new.txt", "file")
            minted = fresh.entry_id
            errors = await run([clobber, fresh], overwrite=True)
            assert errors == []
            assert clobber.entry_id == rival.entry_id
            assert clobber.version == rival.version + 1
            # The clobber stays "insert": the upsert already wrote its final
            # row, so the update passes must never see it again.
            assert clobber.persistence == "insert"
            # ...while the non-conflicted winner in the same statement
            # keeps its staged-minted identity untouched.
            assert fresh.entry_id == minted and fresh.version == 1
            assert fresh.persistence == "insert"

            # overwrite=False over a rival file: DO NOTHING, a definite exists.
            refused = staged_for("/f.txt", "file")
            errors = await run([refused], overwrite=False)
            assert [e.kind for e in errors] == [VFSErrorKind.exists]

            # overwrite=True where the rival is a directory: the clobber's
            # kind guard refuses to update it — wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await run([blocked], overwrite=True)
            assert [e.kind for e in errors] == [VFSErrorKind.wrong_kind]

            # a directory create losing to a directory at the matching
            # address adopts it — no clobber, no error.
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            dir_adopt = staged_for("/dir", "directory")
            errors = await run([dir_adopt], overwrite=True)
            assert errors == []
            assert dir_adopt.persistence == "adopt" and dir_adopt.entry_id == dir_key

            # a directory create losing to a file occupant never clobbers: exists.
            dir_loss = staged_for("/f.txt", "directory")
            errors = await run([dir_loss], overwrite=False)
            assert [e.kind for e in errors] == [VFSErrorKind.exists]
        await storage.close()

    async def test_stale_guard_classifies_conflict(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")])
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            row = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).one()
            stale = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=row.entry_id,
                content="b",
                base_version=999_999,  # a rival moved the row past our snapshot
                version=1_000_000,
            )
            host = storage._host
            errors = await _update_materials(
                session,
                entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [stale],
                user_id=None,
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert errors[0].retryable is True
        assert "Concurrent modification" in errors[0].message
        await storage.close()

    async def test_absorb_row_relocated_before_version_learning_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="theirs")])).success
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            row_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).scalar_one()
            # A rival relocation rewrote the row's address mid-window: the
            # absorb's read-back must catch the mismatch and redrive.
            relocate = update(entry).where(entry.c.entry_id == row_id).values(path="/moved.txt", name="moved.txt")
            await session.execute(relocate)
            relocated = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/"),
                kind="file",
                persistence="absorb",
                entry_id=row_id,
                content="mine",
            )
            with pytest.raises(StaleSnapshot):
                await _update_materials(
                    session,
                    entry,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    [relocated],
                    user_id=None,
                    now=datetime.now(UTC),
                )
            await session.rollback()
        await storage.close()

    async def test_absorb_row_vanishing_before_version_learning_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            # An absorb row whose adopted rival vanished before its
            # version learning: the address proof fails and redrives.
            vanished = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/"),
                kind="file",
                persistence="absorb",
                entry_id=str(ULID()),
                content="mine",
            )
            host = storage._host
            with pytest.raises(StaleSnapshot):
                await _update_materials(
                    session,
                    entry,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    [vanished],
                    user_id=None,
                    now=datetime.now(UTC),
                )
        await storage.close()

    async def test_losing_create_without_overwrite_fails_the_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        profile = replace(host.profile, arbitration="catch_retry")
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            ext=mine.ext,
            mime_type=mine.mime_type,
            overwrite=False,
            parents=False,
        )
        assert status == "created" and plan.errors == []
        plan.pending.append((target, status))

        # A rival lands between the snapshot and execution; without
        # overwrite the losing create cannot clobber — the batch fails.
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success is True

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=False,
            )
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.exists]
        assert (await storage.read(path=target)).observations[0].content == "rival"
        await storage.close()

    async def test_guarded_update_losing_its_row_fails_the_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="v1")])
        host = storage._host
        target = Path("/f.txt")

        # Snapshot at version 1 and stage a guarded update over it.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=host.profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            ext=mine.ext,
            mime_type=mine.mime_type,
            overwrite=True,
            parents=False,
        )
        assert status == "updated" and plan.errors == []
        plan.pending.append((target, status))

        # Two rival writes move the row past base + 1, so the read-back
        # can attribute the guarded update's miss unambiguously.
        assert (await storage.write(entries=[Entry(path=target, content="v2")])).success is True
        assert (await storage.write(entries=[Entry(path=target, content="v3")])).success is True

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=True,
            )
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.conflict]
        assert result.errors[0].retryable is True
        assert "Concurrent modification" in result.errors[0].message
        assert (await storage.read(path=target)).observations[0].content == "v3"
        await storage.close()

    def test_upsert_constructor_is_dialect_bound(self) -> None:
        assert _upsert_constructor(SQLITE) is sqlite_insert
        assert _upsert_constructor(POSTGRESQL) is pg_insert


class _CannedReturning:
    """Result double: canned RETURNING mappings, iterable as row objects."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows

    def all(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(**row) for row in self._rows]

    def __iter__(self) -> Iterator[SimpleNamespace]:
        return iter(SimpleNamespace(**row) for row in self._rows)

    @property
    def rowcount(self) -> int:
        return len(self._rows)


class _ReturningSession:
    """Session double for the VALUES-join arm SQLite cannot execute.

    UPDATE statements answer with the canned RETURNING rows; the guard
    miss re-probe (a SELECT) answers with *probed*.
    """

    def __init__(self, returned: list[dict[str, object]], probed: list[dict[str, object]] | None = None) -> None:
        self.returned = returned
        self.probed = probed if probed is not None else []
        self.statements: list[Any] = []

    def get_bind(self) -> SimpleNamespace:
        # A real dialect so probe statements compile; flags declared as
        # the double intends, independent of the driver's own defaults.
        dialect = postgresql.dialect()
        dialect.update_returning = True
        dialect.update_returning_multifrom = True
        dialect.supports_sane_rowcount = True
        dialect.supports_sane_multi_rowcount = False
        return SimpleNamespace(dialect=dialect)

    async def execute(self, stmt: Any, params: Any = None) -> _CannedReturning:
        self.statements.append(stmt)
        if isinstance(stmt, Select):
            return _CannedReturning(self.probed)
        return _CannedReturning(self.returned)


def _staged_material(path: str, entry_id: str, *, persistence: PersistenceState = "update") -> StagedEntry:
    return StagedEntry(
        path=Path(path),
        parent=Path("/"),
        kind="file",
        persistence=persistence,
        entry_id=entry_id,
        content="mine",
        base_version=1,
        version=2,
    )


class TestGuardedAttribution:
    """The statement-attribution ladder beyond what SQLite executes natively.

    The default suite drives the aggregate fast path and its per-row
    fallback on every guarded overwrite; these tests cover the set-based
    RETURNING arm through a session double — SQLite rejects the
    column-aliased VALUES join, which is why ``values_join`` is a
    declared profile bit — plus the forced per-row floor and the
    classified refusal. The VALUES arm itself is proven live by the
    postgres and mssql conformance legs.
    """

    async def test_returning_arm_attributes_guarded_success_by_membership(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        won = _staged_material("/won.txt", str(ULID()))
        lost = _staged_material("/lost.txt", str(ULID()))
        # The re-probe finds the lost row present: an honest conflict.
        double = _ReturningSession([{"entry_id": won.entry_id, "version": 2}], probed=[{"entry_id": lost.entry_id}])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [won, lost],
            user_id=None,
            now=datetime.now(UTC),
        )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert str(lost.path) in errors[0].message
        updates = [s for s in double.statements if not isinstance(s, Select)]
        assert len(updates) == 1  # both rows rode one chunk

    async def test_returning_arm_guard_miss_reprobes_a_vanished_row_to_not_found(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        gone = _staged_material("/gone.txt", str(ULID()))
        double = _ReturningSession([], probed=[])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [gone],
            user_id=None,
            now=datetime.now(UTC),
        )
        assert [e.kind for e in errors] == [VFSErrorKind.not_found]
        assert str(gone.path) in errors[0].message

    async def test_returning_arm_statement_is_a_guarded_values_join(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        staged = _staged_material("/f.txt", str(ULID()))
        double = _ReturningSession([{"entry_id": staged.entry_id, "version": 2}])
        await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [staged],
            user_id=None,
            now=datetime.now(UTC),
        )
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "FROM (VALUES" in sql
        assert "RETURNING" in sql
        assert "incoming.v_base" in sql  # the version guard joins the VALUES row

    async def test_returning_arm_absorb_learns_returned_version_or_redrives(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        absorbed = _staged_material("/won.txt", str(ULID()), persistence="absorb")
        vanished = _staged_material("/gone.txt", str(ULID()), persistence="absorb")
        double = _ReturningSession([{"entry_id": absorbed.entry_id, "version": 7}])
        with pytest.raises(StaleSnapshot):
            await _update_materials(
                cast("AsyncSession", double),
                tables.entry,
                POSTGRESQL,
                32_000,
                900,
                [absorbed, vanished],
                user_id=None,
                now=datetime.now(UTC),
            )
        assert absorbed.version == 7  # the statement reported the version it assigned
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "incoming.v_base" not in sql  # no version guard: increments SQL-side
        assert "incoming.v_path" in sql  # the address proof joins the VALUES row

    async def test_values_arm_chunks_by_parameter_budget_and_merges_attribution(self) -> None:
        # A budget of 2*width - 1 fits exactly one VALUES tuple per statement:
        # three staged rows must ride three statements, and attribution
        # must merge across the chunks — statement size never grows with
        # batch size.
        tables = build_vfs_tables(table_name="vfs")
        staged = [_staged_material(f"/f{i}.txt", str(ULID())) for i in range(3)]
        width = len(_CLOBBER_COLUMNS) + 4
        double = _ReturningSession([{"entry_id": s.entry_id, "version": 2} for s in staged])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            2 * width - 1,
            900,
            staged,
            user_id=None,
            now=datetime.now(UTC),
        )
        assert errors == []
        assert len(double.statements) == 3

    async def test_aggregate_arm_rolls_back_before_the_per_row_redrive(self, tmp_path) -> None:
        # A mixed batch through the NATURAL aggregate arm: without the
        # savepoint rollback the re-drive would judge already-applied
        # state, and the fresh row would false-conflict beside the stale.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a"), Entry(path=Path("/b.txt"), content="b")])
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            found = await session.execute(select(entry.c.entry_id, entry.c.path, entry.c.version))
            rows = {m["path"]: m for m in found.mappings()}
            fresh = StagedEntry(
                path=Path("/a.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/a.txt"]["entry_id"],
                content="a2",
                base_version=rows["/a.txt"]["version"],
                version=rows["/a.txt"]["version"] + 1,
            )
            stale = StagedEntry(
                path=Path("/b.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/b.txt"]["entry_id"],
                content="b2",
                base_version=999_999,
                version=1_000_000,
            )
            errors = await _update_materials(
                session,
                entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [fresh, stale],
                user_id=None,
                now=datetime.now(UTC),
            )
            after = await session.execute(select(entry.c.path, entry.c.version))
            versions = {m["path"]: m["version"] for m in after.mappings()}
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert str(stale.path) in errors[0].message
        # The fresh row applied exactly once; the stale row never moved.
        assert versions["/a.txt"] == rows["/a.txt"]["version"] + 1
        assert versions["/b.txt"] == rows["/b.txt"]["version"]
        await storage.close()

    async def test_forced_per_row_floor_attributes_each_rowcount(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a"), Entry(path=Path("/b.txt"), content="b")])
        host = storage._host
        entry = host.tables.entry
        # No sane aggregate: the ladder must land on per-row rowcounts.
        monkeypatch.setattr(host.engine.sync_engine.dialect, "supports_sane_multi_rowcount", False)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            found = await session.execute(select(entry.c.entry_id, entry.c.path, entry.c.version))
            rows = {m["path"]: m for m in found.mappings()}
            fresh = StagedEntry(
                path=Path("/a.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/a.txt"]["entry_id"],
                content="a2",
                base_version=rows["/a.txt"]["version"],
                version=rows["/a.txt"]["version"] + 1,
            )
            stale = StagedEntry(
                path=Path("/b.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/b.txt"]["entry_id"],
                content="b2",
                base_version=999_999,
                version=1_000_000,
            )
            errors = await _update_materials(
                session,
                entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [fresh, stale],
                user_id=None,
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert str(stale.path) in errors[0].message
        await storage.close()

    async def test_unverifiable_guard_classifies_instead_of_guessing(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        dialect = host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_multi_rowcount", False)
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        staged = _staged_material("/f.txt", str(ULID()))
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            errors = await _update_materials(
                session,
                host.tables.entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [staged],
                user_id=None,
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [VFSErrorKind.unsupported]
        assert "cannot be verified" in errors[0].message
        await storage.close()


class TestMembershipChunking:
    """No statement grows unboundedly with batch size — the ETL contract.

    Every membership predicate (``path IN``, ``id IN``, glob's anchor
    fan) chunks by ``membership_budget`` and merges, so a batch's SQL
    stays within every engine's limits (Oracle's 1,000-element IN floor,
    MSSQL's 2,100 bind params) regardless of N.
    """

    def test_membership_budget_honors_both_caps(self) -> None:
        # The generic floor is Oracle's 1,000-element IN-list cap.
        assert membership_budget(GENERIC, 32_700) == 1_000
        # A parameter-capped engine binds through the tighter budget.
        assert membership_budget(MSSQL, 2_099) == 2_099 - 32
        # Degenerate budgets never chunk below one element.
        assert membership_budget(GENERIC, 8) == 1

    def test_fan_budget_honors_bind_and_depth_caps(self) -> None:
        # Depth-capped: an OR chain parses left-deep, so SQLite's huge
        # bind budget still yields (1,000 - reserve) // 2 anchors.
        assert fan_budget(SQLITE, 100_000) == 468
        assert fan_budget(GENERIC, 100_000) == 468  # the unknown-engine floor
        # Bind-capped: a squeezed parameter budget wins over depth.
        assert fan_budget(SQLITE, 48) == 8
        # Degenerate budgets never chunk below one anchor.
        assert fan_budget(GENERIC, 0) == 1

    def test_rows_per_statement_divides_by_the_widest_row(self) -> None:
        narrow = {"entry_id": "e1", "path": "/a"}
        wide = narrow | {"kind": "file", "version": 1}
        assert rows_per_statement(100, [narrow, wide]) == 100 // len(wide)
        # A budget narrower than one row still makes progress row-wise.
        assert rows_per_statement(2, [wide]) == 1

    async def test_tiny_budget_batch_survives_every_verb(self, tmp_path, monkeypatch) -> None:
        # Budget 48 → membership 16: far below the batch size, so every
        # membership site must chunk-and-merge to serve correctly.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        paths = [Path(f"/etl/part{i:02}/f{i:03}.txt") for i in range(60)]
        written = await storage.write(
            entries=[Entry(path=p, content=f"row {i}") for i, p in enumerate(paths)], parents=True
        )
        assert written.success is True, written.errors
        stats = await storage.stat(observations=written.observations)
        assert {str(o.path) for o in stats.observations} >= {str(p) for p in paths}
        edited = await storage.edit(
            edits=[EditOperation(old="row", new="line")],
            observations=[o for o in written.observations if o.path in paths],
        )
        assert edited.success is True, edited.errors
        reread = await storage.read(path=paths[0])
        assert reread.observations[0].content == "line 0"
        # Misses beyond the budget still classify per-target, and glob's
        # scope fan chunks: 60 anchors at 8 per statement.
        misses = await storage.stat(observations=[Observation(path=Path(f"/ghost/g{i}.txt")) for i in range(40)])
        assert len(misses.errors) == 40
        assert {e.kind for e in misses.errors} == {VFSErrorKind.not_found}
        scoped = await storage.glob(pattern="*.txt", paths=tuple(p.parent_dir for p in paths))
        assert len(scoped.observations) == 60
        # Batch ls spans chunk boundaries: 60 anchors at 16 per statement,
        # each parent's single child arriving whole through the merge.
        listing = await storage.ls(observations=[Observation(path=p.parent_dir) for p in paths])
        assert listing.success is True
        assert sorted(str(o.path) for o in listing.observations) == sorted(str(p) for p in paths)
        await storage.close()

    async def test_wide_scope_glob_survives_the_expression_depth_cap(self, tmp_path) -> None:
        # 1,100 anchors: past the 499-anchor point where SQLite's default
        # SQLITE_MAX_EXPR_DEPTH kills an unchunked fan, and enough to
        # span multiple fan chunks at the depth-capped budget. Ghost
        # anchors classify per-anchor (find parity), rows still serve.
        storage = DatabaseStorage(url=_url(tmp_path))
        written = await storage.write(entries=[Entry(path=Path("/d/a.txt"), content="x")], parents=True)
        assert written.success is True
        scope = (Path("/d"), *(Path(f"/ghost{i:04}") for i in range(1_099)))
        result = await storage.glob(pattern="*", paths=scope)
        assert [str(o.path) for o in result.observations] == ["/d", "/d/a.txt"]
        assert result.success is False
        assert len(result.errors) == 1_099
        assert {e.kind for e in result.errors} == {VFSErrorKind.not_found}
        await storage.close()

    async def test_nested_glob_anchors_dedupe_across_chunks(self, tmp_path, monkeypatch) -> None:
        # Budget 48 → fan chunks of 8 anchors: /top lands in the first
        # chunk and every nested anchor re-matches its rows in later
        # chunks, so each row must appear exactly once after the merge.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        files = [Path(f"/top/d{i:02}/f.txt") for i in range(20)]
        written = await storage.write(entries=[Entry(path=p, content="x") for p in files], parents=True)
        assert written.success is True, written.errors
        result = await storage.glob(pattern="*", paths=(Path("/top"), *(p.parent_dir for p in files)))
        expected = sorted(["/top", *(str(p.parent_dir) for p in files), *(str(p) for p in files)])
        assert [str(o.path) for o in result.observations] == expected
        await storage.close()

    async def test_tiny_budget_topology_verbs_cross_chunk_boundaries(self, tmp_path, monkeypatch) -> None:
        # Budget 48 → membership 16: the snapshot fetch, copy's entry and
        # content passes, the final re-read, and the purge all chunk, so
        # every merge must reassemble correctly across boundaries.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        files = [Path(f"/src/f{i:02}.txt") for i in range(40)]
        written = await storage.write(
            entries=[Entry(path=p, content=f"c{i}") for i, p in enumerate(files)], parents=True
        )
        assert written.success is True, written.errors
        copied = await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/dst"))])
        assert copied.success is True, copied.errors
        for i in (0, 17, 39):
            assert (await storage.read(path=Path(f"/dst/f{i:02}.txt"))).observations[0].content == f"c{i}"
        pairs = [ResolvedPair(src=Path(f"/dst/f{i:02}.txt"), dest=Path(f"/dst/m{i:02}.txt")) for i in range(20)]
        moved = await storage.move(operations=pairs)
        assert moved.success is True, moved.errors
        assert all(o.status == "created" for o in moved.observations)
        deleted = await storage.delete(observations=[Observation(path=p) for p in files])
        assert deleted.success is True, deleted.errors
        assert len(deleted.observations) == 40
        assert (await storage.ls(path=Path("/src"))).observations == []
        purged = await storage.sweep(path=Path("/dst"))
        assert purged.success is True, purged.errors
        assert (await storage.stat(path=Path("/dst"))).success is False
        await storage.close()

    async def test_ten_thousand_entry_batch_round_trips(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [
            Entry(path=Path(f"/lake/d{i // 500:02}/r{i:05}.json"), content=f'{{"row": {i}}}') for i in range(10_000)
        ]
        written = await storage.write(entries=entries, parents=True)
        assert written.success is True, written.errors[:3]
        created = [o for o in written.observations if str(o.path).endswith(".json")]
        assert len(created) == 10_000
        assert all(o.status == "created" for o in created)
        stats = await storage.stat(observations=created)
        assert stats.success is True, stats.errors[:3]
        assert len(stats.observations) == 10_000
        await storage.close()


# ---------------------------------------------------------------------------
# Topology infrastructure — options, keys, serialization point, seams
# ---------------------------------------------------------------------------


class TestTopologyOptions:
    """Topology connections trade the op snapshot for the serialization point."""

    def test_topology_options_carry_the_writer_marker_only_on_unpinned_engines(self) -> None:
        assert topology_execution_options(SQLITE) == {"vfs_writer": True}
        assert topology_execution_options(MSSQL) == {"vfs_writer": True}
        assert topology_execution_options(GENERIC) == {"vfs_writer": True}

    def test_topology_options_pin_read_committed_where_declared(self) -> None:
        for profile in (POSTGRESQL, MYSQL, PROFILES["mariadb"]):
            options = topology_execution_options(profile)
            assert options == {"vfs_writer": True, "isolation_level": "READ COMMITTED"}

    def test_topology_pin_never_borrows_the_op_pin(self) -> None:
        # MySQL ops run REPEATABLE READ; its topology pin must differ.
        assert op_execution_options(MYSQL, writer=True)["isolation_level"] == "REPEATABLE READ"
        assert topology_execution_options(MYSQL)["isolation_level"] == "READ COMMITTED"


class TestTopologyKey:
    """Topology locks key on the durable mount identity, never the mount path."""

    def test_advisory_key_is_stable_and_signed_64(self) -> None:
        key = advisory_key("vfs")
        assert key == advisory_key("vfs")
        assert -(2**63) <= key < 2**63
        assert key != advisory_key("other")

    def test_topology_key_falls_back_to_the_table_key_before_adoption(self) -> None:
        host = EngineHost(url="sqlite+aiosqlite:///:memory:", table_name="vfs")
        assert host.topology_key == advisory_key("vfs")

    def test_topology_key_prefers_the_adopted_mount_identity(self) -> None:
        host = EngineHost(url="sqlite+aiosqlite:///:memory:", table_name="vfs")
        host.mount_identity = str(ULID())
        assert host.topology_key == advisory_key(host.mount_identity)


class _StatementRecorder:
    """Session double capturing executed statements as compiled SQL text."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, stmt: Any, params: Any = None) -> SimpleNamespace:
        self.statements.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        return SimpleNamespace(scalar_one=lambda: 0)


class TestSerializationPoint:
    """The point is the verb's first statement; each engine has its declared arm."""

    def _meta(self):
        return build_vfs_tables(table_name="vfs").meta

    async def test_sqlite_needs_no_statement(self) -> None:
        recorder = _StatementRecorder()
        await _serialize(cast("AsyncSession", recorder), SQLITE, self._meta(), lock_key=7)
        assert recorder.statements == []

    async def test_postgres_takes_the_advisory_lock_on_the_key(self) -> None:
        recorder = _StatementRecorder()
        await _serialize(cast("AsyncSession", recorder), POSTGRESQL, self._meta(), lock_key=advisory_key("vfs"))
        assert len(recorder.statements) == 1
        assert "pg_advisory_xact_lock" in recorder.statements[0]
        assert str(advisory_key("vfs")) in recorder.statements[0]

    async def test_other_engines_x_lock_the_meta_row(self) -> None:
        for profile in (MSSQL, MYSQL, PROFILES["oracle"], GENERIC):
            recorder = _StatementRecorder()
            await _serialize(cast("AsyncSession", recorder), profile, self._meta(), lock_key=7)
            assert len(recorder.statements) == 1
            statement = recorder.statements[0]
            assert statement.startswith("UPDATE")
            assert "schema_format_version=" in statement.replace(" ", "")
            assert "id = 1" in statement


class TestSeams:
    """Named no-op points; a test-installed handler stages a rival mid-window."""

    async def test_a_seam_with_no_handler_is_a_no_op(self) -> None:
        await seam("never-installed")

    async def test_an_installed_handler_fires_and_clears(self) -> None:
        fired: list[str] = []

        async def handler() -> None:
            fired.append("ran")

        install("test-point", handler)
        await seam("test-point")
        clear("test-point")
        await seam("test-point")
        assert fired == ["ran"]

    async def test_installed_context_clears_on_error(self) -> None:
        async def handler() -> None:
            raise AssertionError("must not fire")

        with pytest.raises(RuntimeError), installed("test-point", handler):
            raise RuntimeError("boom")
        await seam("test-point")

    async def test_clearing_an_absent_seam_is_fine(self) -> None:
        clear("never-installed")

    async def test_the_write_seam_fires_inside_the_verb(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        fired: list[str] = []

        async def handler() -> None:
            fired.append("write")

        with installed("write:before-apply", handler):
            assert (await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])).success
        assert fired == ["write"]
        await storage.close()

    async def test_the_delete_seam_fires_after_the_snapshot(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        fired: list[str] = []

        async def handler() -> None:
            fired.append("delete")

        with installed("delete:post-snapshot", handler):
            assert (await storage.delete(path=Path("/x.txt"))).success
        assert fired == ["delete"]
        await storage.close()


# ---------------------------------------------------------------------------
# Delete — the trash arm beyond the conformance rows
# ---------------------------------------------------------------------------


class TestDeleteTrash:
    """The default arm reparents into an hourly bucket; trash is normal fs."""

    async def test_delete_reparents_into_the_hourly_bucket(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="body")])
        deleted = await storage.delete(path=Path("/a.txt"))
        assert deleted.success
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        assert len(buckets.observations) == 1
        bucket = buckets.observations[0]
        listing = await storage.ls(path=bucket.path)
        assert len(listing.observations) == 1
        trashed = listing.observations[0]
        # The in-bucket name is `<ULID>-<original name>`: unique and
        # time-sorted by prefix, self-describing by suffix.
        name = Path(trashed.path).name
        assert len(name) == ULID_LENGTH + len("-a.txt")
        assert name.endswith("-a.txt")
        # The delete result reported exactly this address.
        assert deleted.observations[0].trash_path == trashed.path
        assert "trash_path" in deleted.observations[0].populated
        read = await storage.read(path=trashed.path)
        assert read.observations[0].content == "body"
        await storage.close()

    async def test_trashed_row_records_its_original_site(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/docs"))
        await storage.write(entries=[Entry(path=Path("/docs/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/docs/a.txt"))).success
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(entry).where(entry.c.original_name == "a.txt"))).mappings().one()
        assert row["name"] == f"{row['entry_id']}-a.txt"
        assert row["deleted_at"] is not None
        assert row["original_parent_id"] is not None
        parent = await storage.stat(path=Path("/docs"))
        assert parent.success is True
        await storage.close()

    async def test_descendant_paths_rewrite_under_the_trash_prefix(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/proj/sub"), parents=True)
        await storage.write(entries=[Entry(path=Path("/proj/sub/f.txt"), content="deep")])
        assert (await storage.delete(path=Path("/proj"))).success
        assert (await storage.stat(path=Path("/proj/sub/f.txt"))).success is False
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        bucket_listing = await storage.ls(path=buckets.observations[0].path)
        trashed_root = bucket_listing.observations[0].path
        deep = await storage.read(path=Path(f"{trashed_root}/sub/f.txt"))
        assert deep.observations[0].content == "deep"
        await storage.close()

    async def test_same_named_deletes_never_collide_in_the_bucket(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/a"))
        await storage.mkdir(path=Path("/b"))
        await storage.write(
            entries=[Entry(path=Path("/a/f.txt"), content="1"), Entry(path=Path("/b/f.txt"), content="2")]
        )
        targets = [Observation(path=Path("/a/f.txt")), Observation(path=Path("/b/f.txt"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        listing = await storage.ls(path=buckets.observations[0].path)
        assert len(listing.observations) == 2
        # Both keep the readable suffix; the ULID prefix tells them apart.
        names = [Path(o.path).name for o in listing.observations]
        assert all(n.endswith("-f.txt") for n in names)
        assert len(set(names)) == 2
        await storage.close()

    async def test_delete_batch_observations_all_carry_trash_paths(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(
            entries=[Entry(path=Path("/a.txt"), content="x"), Entry(path=Path("/d/b.txt"), content="y")]
        )
        targets = [Observation(path=Path("/a.txt")), Observation(path=Path("/d"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        assert all(o.trash_path is not None for o in result.observations)
        assert all("trash_path" in o.populated for o in result.observations)
        await storage.close()

    async def test_covered_targets_derive_their_trash_address(self, tmp_path) -> None:
        # The covered child is observed before its covering root is
        # processed; its trash address is derived, not looked up.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/proj/sub"), parents=True)
        await storage.write(entries=[Entry(path=Path("/proj/sub/f.txt"), content="deep")])
        targets = [Observation(path=Path("/proj/sub/f.txt")), Observation(path=Path("/proj"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        by_path = {str(o.path): o for o in result.observations}
        root_trash = by_path["/proj"].trash_path
        assert root_trash is not None
        covered_trash = by_path["/proj/sub/f.txt"].trash_path
        assert covered_trash == Path(f"{root_trash}/sub/f.txt")
        read = await storage.read(path=covered_trash)
        assert read.observations[0].content == "deep"
        await storage.close()

    async def test_a_repeated_target_reports_the_same_trash_address(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        targets = [Observation(path=Path("/a.txt")), Observation(path=Path("/a.txt"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        first, second = result.observations
        assert first.trash_path is not None
        assert second.trash_path == first.trash_path
        await storage.close()

    async def test_a_batch_touching_the_chain_holder_refuses_whole(self, tmp_path) -> None:
        # /.vfs holds the bucket chain: its refusal fails the batch, so
        # the innocent sibling target survives live — nothing commits.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        assert (await storage.delete(path=Path("/x.txt"))).success
        await storage.write(entries=[Entry(path=Path("/y.txt"), content="y")])
        targets = [Observation(path=Path("/y.txt")), Observation(path=Path("/.vfs"))]
        result = await storage.delete(observations=targets)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.invalid]
        assert result.errors[0].message == "Cannot delete /.vfs: contains the active trash chain — sweep reclaims trash"
        assert (await storage.stat(path=Path("/y.txt"))).success is True
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True
        await storage.close()

    async def test_a_covered_chain_target_adds_no_second_error(self, tmp_path) -> None:
        # /.vfs/trash rides inside /.vfs's cascade: the covering holder
        # refuses exactly once; the covered target contributes no error.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        trashed = (await storage.delete(path=Path("/x.txt"))).observations[0].trash_path
        assert trashed is not None
        targets = [Observation(path=Path("/.vfs/trash")), Observation(path=Path("/.vfs"))]
        result = await storage.delete(observations=targets)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.invalid]
        assert result.errors[0].message == "Cannot delete /.vfs: contains the active trash chain — sweep reclaims trash"
        # The refused batch never commits: the previously-trashed row survives.
        assert (await storage.stat(path=trashed)).success is True
        await storage.close()

    async def test_the_trash_name_truncates_at_the_tail_never_the_ulid(self, tmp_path) -> None:
        # 26-byte ULID + hyphen leaves 228 bytes of name tail; the
        # 4-byte emoji straddles the cut and must drop whole.
        storage = DatabaseStorage(url=_url(tmp_path))
        original = "x" * 227 + "🚀"
        await storage.write(entries=[Entry(path=Path(f"/{original}"), content="x")])
        result = await storage.delete(path=Path(f"/{original}"))
        assert result.success is True
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        name = trash_path.name
        assert byte_length(name) == ULID_LENGTH + 1 + 227
        assert "🚀" not in name
        # The row is addressable at the reported path with metadata whole.
        assert (await storage.stat(path=trash_path)).success is True
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            found = (await session.execute(select(entry).where(entry.c.path == str(trash_path)))).mappings().one()
        assert found["original_name"] == original
        await storage.close()

    async def test_a_maximal_name_still_fits_the_path_budget(self, tmp_path) -> None:
        # Worst case root trash path is the bucket prefix plus a 255-byte
        # name — ~281 bytes, comfortably inside the 1,024-byte budget.
        storage = DatabaseStorage(url=_url(tmp_path))
        original = "n" * 255
        await storage.write(entries=[Entry(path=Path(f"/{original}"), content="x")])
        result = await storage.delete(path=Path(f"/{original}"))
        assert result.success is True
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        assert byte_length(str(trash_path)) <= MAX_PATH_LENGTH
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_a_file_squatting_on_the_trash_chain_refuses_wrong_kind(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/.vfs/trash"), content="squatter")], parents=True)
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        result = await storage.delete(path=Path("/x.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/.vfs/trash"
        assert (result.errors[0].data or {}).get("target") == "/x.txt"
        # The batch never commits: the target survives.
        assert (await storage.stat(path=Path("/x.txt"))).success is True
        await storage.close()

    async def test_a_trashed_row_can_be_swept_from_the_trash_side(self, tmp_path) -> None:
        # Per-row reclamation re-homed from the retired permanent flag:
        # sweep of the exact trash address purges just that row.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/gone.txt"), content="x")])
        assert (await storage.delete(path=Path("/gone.txt"))).success
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        listing = await storage.ls(path=buckets.observations[0].path)
        trash_path = listing.observations[0].path
        assert (await storage.sweep(path=Path(trash_path))).success
        assert (await storage.stat(path=Path(trash_path))).success is False
        assert (await storage.stat(path=buckets.observations[0].path)).success is True
        await storage.close()

    async def test_the_bucket_mint_survives_a_rival_write_racing_the_chain(self, tmp_path) -> None:
        # The designed benign race: a rival mints the chain link first;
        # the topology mint loses arbitration and adopts the rival's row.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        entry = storage._host.tables.entry
        host = storage._host
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))
            root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            chain = _TrashChain(entry, root_id=root_id, user_id=None, now=datetime.now(UTC))
            first = await chain.ensure(session, Path("/x.txt"))
            assert isinstance(first, str)
            # A fresh chain re-selects the minted links instead of re-minting.
            rival = _TrashChain(entry, root_id=root_id, user_id=None, now=datetime.now(UTC))
            second = await rival.ensure(session, Path("/x.txt"))
            assert second == first
            # A direct mint against an occupied link takes the
            # IntegrityError arm and adopts the winner's row.
            adopted = await rival._mint(session, "/.vfs", root_id)
            assert adopted.kind == "directory"
            await session.rollback()
        await storage.close()


class TestRestore:
    """Restore arms beyond the conformance rows — identity, corruption, budgets."""

    async def test_restore_clears_the_restore_columns(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        assert (await storage.restore(path=deleted.observations[0].trash_path)).success is True
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(entry).where(entry.c.path == "/a.txt"))).mappings().one()
        assert row["original_parent_id"] is None
        assert row["original_name"] is None
        assert row["deleted_at"] is None
        assert row["name"] == "a.txt"
        await storage.close()

    async def test_restore_follows_a_moved_parent(self, tmp_path) -> None:
        # The trash row holds the parent's identity, not its old path: the
        # row restores to wherever that parent lives now.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        trash_path = deleted.observations[0].trash_path
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))])).success is True
        by_old_site = await storage.restore(path=Path("/d/f.txt"))
        assert by_old_site.success is False
        assert by_old_site.errors[0].kind == VFSErrorKind.not_found
        restored = await storage.restore(path=trash_path)
        assert restored.success is True
        assert restored.observations[0].path == "/e/f.txt"
        assert (await storage.read(path=Path("/e/f.txt"))).observations[0].content == "x"
        await storage.close()

    async def test_restore_refuses_when_the_parent_is_itself_in_trash(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        assert (await storage.delete(path=Path("/d"))).success is True
        result = await storage.restore(path=deleted.observations[0].trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert "restore" in result.errors[0].message
        await storage.close()

    async def test_restore_returns_a_row_to_the_live_hour_bucket(self, tmp_path) -> None:
        # The bucket sits under /.vfs/trash but is live, never trashed:
        # a trash row deleted in place restores back into it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/g.txt"), content="payload")])
        first = (await storage.delete(path=Path("/g.txt"))).observations[0].trash_path
        assert first is not None
        second = (await storage.delete(path=first)).observations[0].trash_path
        assert second is not None
        result = await storage.restore(path=second)
        assert result.success is True
        assert result.observations[0].path == str(first)
        assert (await storage.read(path=first)).observations[0].content == "payload"
        await storage.close()

    async def test_restore_returns_a_row_to_a_live_squatter_under_trash(self, tmp_path) -> None:
        # Trash is an ordinary subtree: a live user directory squatting
        # inside it is a lawful original site, not a trashed parent.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/.vfs/trash/mystuff"), parents=True)
        await storage.write(entries=[Entry(path=Path("/.vfs/trash/mystuff/a.txt"), content="squat")])
        deleted = await storage.delete(path=Path("/.vfs/trash/mystuff/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        result = await storage.restore(path=trash_path)
        assert result.success is True
        assert (await storage.read(path=Path("/.vfs/trash/mystuff/a.txt"))).observations[0].content == "squat"
        await storage.close()

    async def test_restore_refuses_a_corrupted_non_directory_parent(self, tmp_path) -> None:
        # Foreign-state tolerance: a parent row whose kind was mangled
        # out from under the trash contract refuses, never mis-restores.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            await session.execute(update(entry).where(entry.c.path == "/d").values(kind="file"))
            await session.commit()
        result = await storage.restore(path=deleted.observations[0].trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        await storage.close()

    async def test_restore_destination_overflow_refuses_unaddressable(self, tmp_path) -> None:
        # The parent moved deeper since the delete: the computed
        # destination exceeds the byte budget and the row stays in trash.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        name = "n" * 255
        await storage.write(entries=[Entry(path=Path(f"/d/{name}"), content="x")])
        deleted = await storage.delete(path=Path(f"/d/{name}"))
        trash_path = deleted.observations[0].trash_path
        deep = Path("/" + "a" * 255 + "/" + "b" * 255 + "/" + "c" * 255)
        await storage.mkdir(path=deep, parents=True)
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path(f"{deep}/d"))])).success is True
        result = await storage.restore(path=trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_restore_descendant_overflow_refuses_unaddressable(self, tmp_path) -> None:
        # The restored root fits; a descendant rewrite would not.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d/s"), parents=True)
        await storage.write(entries=[Entry(path=Path("/d/s/" + "f" * 255), content="x")])
        deleted = await storage.delete(path=Path("/d/s"))
        trash_path = deleted.observations[0].trash_path
        deep = Path("/" + "a" * 255 + "/" + "b" * 255 + "/" + "c" * 255)
        await storage.mkdir(path=deep, parents=True)
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path(f"{deep}/d"))])).success is True
        result = await storage.restore(path=trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_restore_onto_a_wrong_kind_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        await storage.delete(path=Path("/a.txt"))
        await storage.mkdir(path=Path("/a.txt"))
        result = await storage.restore(path=Path("/a.txt"), overwrite=True)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        await storage.close()

    async def test_restore_onto_a_nonempty_directory_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.delete(path=Path("/d"))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/new.txt"), content="x")])
        result = await storage.restore(path=Path("/d"), overwrite=True)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_empty
        await storage.close()

    async def test_restore_overwrites_an_empty_directory_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="kept")])
        await storage.delete(path=Path("/d"))
        await storage.mkdir(path=Path("/d"))
        result = await storage.restore(path=Path("/d"), overwrite=True)
        assert result.success is True
        assert result.observations[0].status == "updated"
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "kept"
        await storage.close()

    async def test_restore_batch_error_fails_the_batch_whole(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        targets = [Observation(path=trash_path), Observation(path=Path("/ghost.txt"))]
        result = await storage.restore(observations=targets)
        assert result.success is False
        # The refused batch never commits: the good target stays in trash.
        assert (await storage.stat(path=trash_path)).success is True
        assert (await storage.stat(path=Path("/a.txt"))).success is False
        await storage.close()


class TestSweep:
    """Sweep arms beyond the conformance rows — retention boundary, config."""

    async def test_trash_days_zero_expires_only_fully_aged_hours(self, tmp_path) -> None:
        # Retention is a floor: with trash_days=0 the cutoff is now, and
        # the current hour has not fully elapsed — its bucket survives
        # while a two-hour-old bucket drops.
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        old = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d-%H")
        await storage.mkdir(path=Path(f"/.vfs/trash/{old}"))
        result = await storage.sweep(path=Path("/.vfs/trash"))
        if str(trash_path.parent_dir) != f"/.vfs/trash/{datetime.now(UTC).strftime('%Y-%m-%d-%H')}":
            pytest.skip("hour boundary crossed between delete and sweep")
        assert result.success is True
        assert [str(o.path) for o in result.observations] == [f"/.vfs/trash/{old}"]
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_negative_trash_days_refuses_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="trash_days"):
            DatabaseStorage(url=_url(tmp_path), trash_days=-1)

    async def test_sweep_surfaces_a_trash_root_squatter(self, tmp_path) -> None:
        # A user file sitting at /.vfs/trash itself is foreign state: the
        # sweep touches nothing and says so, without failing.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/.vfs/trash"), content="squat")], parents=True)
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert result.observations == []
        assert result.errors[0].severity == Severity.warning
        assert result.errors[0].path == "/.vfs/trash"
        assert (await storage.read(path=Path("/.vfs/trash"))).observations[0].content == "squat"
        await storage.close()

    async def test_sweep_purge_miss_classifies_through_the_descent_ladder(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deep = await storage.sweep(path=Path("/ghost/deep"))
        assert deep.success is False
        assert deep.errors[0].kind == VFSErrorKind.not_found
        assert deep.errors[0].path == "/ghost"
        wrong = await storage.sweep(path=Path("/a.txt/child"))
        assert wrong.success is False
        assert wrong.errors[0].kind == VFSErrorKind.wrong_kind
        assert wrong.errors[0].path == "/a.txt"
        await storage.close()

    async def test_sweep_purge_bumps_the_parent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        before = (await storage.stat(path=Path("/d"))).observations[0].version
        assert before is not None
        assert (await storage.sweep(path=Path("/d/f.txt"))).success
        after = (await storage.stat(path=Path("/d"))).observations[0].version
        assert after == before + 1
        await storage.close()


class TestTransferBehavior:
    """Transfer arms beyond the conformance rows — restore, chains, fallbacks."""

    async def test_move_out_of_trash_is_the_restore_gesture(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/doc.txt"), content="body")])
        assert (await storage.delete(path=Path("/doc.txt"))).success
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        listing = await storage.ls(path=buckets.observations[0].path)
        trash_path = Path(listing.observations[0].path)
        restored = await storage.move(operations=[ResolvedPair(src=trash_path, dest=Path("/doc.txt"))])
        assert restored.success is True
        assert (await storage.read(path=Path("/doc.txt"))).observations[0].content == "body"
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(entry).where(entry.c.path == "/doc.txt"))).mappings().one()
        # A live row carries no trash metadata, and its name is its own again.
        assert row["deleted_at"] is None
        assert row["original_parent_id"] is None
        assert row["original_name"] is None
        assert row["name"] == "doc.txt"
        await storage.close()

    async def test_chained_moves_fall_back_to_the_pair_time_observation(self, tmp_path) -> None:
        # Pair 2 moves pair 1's destination away: the re-read finds no row
        # at /b, so pair 1's observation falls back to its captured values.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.move(
            operations=[
                ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt")),
                ResolvedPair(src=Path("/b.txt"), dest=Path("/c.txt")),
            ]
        )
        assert result.success is True
        first, second = result.observations
        assert str(first.path) == "/b.txt" and first.status == "created"
        assert str(second.path) == "/c.txt" and second.status == "created"
        assert (await storage.stat(path=Path("/b.txt"))).success is False
        assert (await storage.read(path=Path("/c.txt"))).observations[0].content == "x"
        await storage.close()

    async def test_the_transfer_seam_fires_after_the_snapshot(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        fired: list[str] = []

        async def handler() -> None:
            fired.append("transfer")

        with installed("transfer:post-snapshot", handler):
            assert (await storage.copy(operations=[ResolvedPair(src=Path("/x.txt"), dest=Path("/y.txt"))])).success
        assert fired == ["transfer"]
        await storage.close()


class TestSweepPurge:
    """The purge arm sweeps the subtree's rows across every family table."""

    async def test_sweep_purges_family_rows(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/proj"))
        await storage.write(entries=[Entry(path=Path("/proj/f.txt"), content="x")])
        tables = storage._host.tables
        entry = tables.entry
        async with storage._host.session_factory() as session:
            target_id = (
                await session.execute(select(entry.c.entry_id).where(entry.c.path == "/proj/f.txt"))
            ).scalar_one()
            await session.execute(
                insert(tables.versions).values(
                    entry_id=target_id, version_number=1, is_snapshot=True, content_hash="h", content="x"
                )
            )
            await session.execute(
                insert(tables.chunks).values(entry_id=target_id, chunk_index=0, line_start=1, line_end=1, content="x")
            )
            await session.execute(
                insert(tables.edges).values(source_id=target_id, target_id=str(ULID()), edge_type="ref")
            )
            await session.execute(
                insert(tables.edges).values(source_id=str(ULID()), target_id=target_id, edge_type="ref")
            )
            await session.commit()
        assert (await storage.sweep(path=Path("/proj"))).success
        async with storage._host.session_factory() as session:
            for table in (tables.entry, tables.content, tables.versions, tables.chunks):
                remaining = (await session.execute(select(table).where(table.c.entry_id == target_id))).all()
                assert remaining == []
            edges = (
                await session.execute(
                    select(tables.edges).where(
                        (tables.edges.c.source_id == target_id) | (tables.edges.c.target_id == target_id)
                    )
                )
            ).all()
            assert edges == []
        assert (await storage.stat(path=Path("/proj"))).success is False
        # Nothing landed in trash: the purge never mints the bucket chain.
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is False
        await storage.close()


# ---------------------------------------------------------------------------
# Trash-machinery guard, byte-budget refusal, purge hardening
# ---------------------------------------------------------------------------


async def _assert_no_cycles_or_orphans(storage: DatabaseStorage) -> None:
    """Raw invariant sweep: parents exist, no cycles, path caches agree."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(entry.c.entry_id, entry.c.parent_id, entry.c.path, entry.c.name))).all()
    by_id = {row.entry_id: row for row in rows}
    for row in rows:
        if row.path == "/":
            continue
        assert row.parent_id != row.entry_id, f"self-parented row: {row.path}"
        parent = by_id.get(row.parent_id)
        assert parent is not None, f"orphan row: {row.path}"
        prefix = "" if parent.path == "/" else parent.path
        assert row.path == f"{prefix}/{row.name}", f"torn path cache: {row.path}"
        walked: set[str] = set()
        current = row
        while current.path != "/":
            assert current.entry_id not in walked, f"parent cycle through {row.path}"
            walked.add(current.entry_id)
            current = by_id[current.parent_id]


class TestTrashChainRefusal:
    """Deleting the active trash machinery refuses; sweep reclaims it."""

    async def test_deleting_the_trash_root_refuses_and_purges_nothing(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        assert deleted.success
        result = await storage.delete(path=Path("/.vfs/trash"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        expected = "Cannot delete /.vfs/trash: contains the active trash chain — sweep reclaims trash"
        assert result.errors[0].message == expected
        assert (await storage.stat(path=deleted.observations[0].trash_path)).success is True
        await _assert_no_cycles_or_orphans(storage)
        await storage.close()

    async def test_sweeping_the_chain_holder_purges_and_the_chain_reminting_is_clean(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        assert (await storage.sweep(path=Path("/.vfs"))).success is True
        assert (await storage.stat(path=Path("/.vfs"))).success is False
        await _assert_no_cycles_or_orphans(storage)
        # The next delete re-mints a fresh chain cleanly.
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.delete(path=Path("/b.txt"))).success
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True
        await _assert_no_cycles_or_orphans(storage)
        await storage.close()

    async def test_sweeping_the_current_bucket_reclaims_it_without_cycles(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        bucket = (await storage.ls(path=Path("/.vfs/trash"))).observations[0].path
        assert (await storage.sweep(path=Path(bucket))).success is True
        assert (await storage.stat(path=Path(bucket))).success is False
        # The trash root survives; only the bucket subtree was purged.
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True
        await _assert_no_cycles_or_orphans(storage)
        await storage.close()

    def test_chain_inside_matches_ancestors_and_the_bucket_only(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        chain = _TrashChain(tables.entry, root_id="r", user_id=None, now=datetime.now(UTC))
        assert chain.chain_inside(Path("/.vfs")) is True
        assert chain.chain_inside(Path("/.vfs/trash")) is True
        assert chain.chain_inside(Path(chain.bucket_path)) is True
        # A prefix that is not an ancestor, and a bucket from another hour.
        assert chain.chain_inside(Path("/.vfs/tra")) is False
        assert chain.chain_inside(Path("/.vfs/trash/1999-01-01-00")) is False
        assert chain.chain_inside(Path("/docs")) is False

    async def test_trash_delete_refuses_when_a_rewrite_would_overflow(self, tmp_path) -> None:
        # The trash prefix for /d is 54 bytes (25-byte bucket + "/" +
        # 28-byte <ULID>-d), so a descendant fits iff its path ≤ 972.
        storage = DatabaseStorage(url=_url(tmp_path))
        segment = "s" * 255
        fits = Path(f"/d/{segment}/{segment}/{segment}/" + "f" * 201)
        over = Path(f"/e/{segment}/{segment}/{segment}/" + "f" * 202)
        await storage.write(entries=[Entry(path=fits, content="ok")], parents=True)
        assert (await storage.delete(path=Path("/d"))).success is True
        await storage.write(entries=[Entry(path=over, content="deep")], parents=True)
        result = await storage.delete(path=Path("/e"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert result.errors[0].path == "/e"
        # The refused batch never commits: the tree survives whole.
        assert (await storage.stat(path=over)).success is True
        # A covered child of the refusing root derives no address either:
        # the over-budget derivation yields None instead of raising.
        both = await storage.delete(observations=[Observation(path=over), Observation(path=Path("/e"))])
        assert both.success is False
        assert any(e.kind == VFSErrorKind.unaddressable for e in both.errors)
        # The developer-plane sweep stays the lawful removal for such trees.
        assert (await storage.sweep(path=Path("/e"))).success is True
        await storage.close()


class TestPurgeHardening:
    """The purge re-collects until empty and never doubles a chunk's binds."""

    async def test_purge_recollects_rows_committed_after_the_first_collection(self, tmp_path) -> None:
        # The stale-id-list orphan window: a row appearing between the
        # collect and the deletes must be swept by the second pass.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/base.txt"), content="x")])
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))
            parent_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()

            async def straggler() -> None:
                clear("purge:post-collect")
                now = datetime.now(UTC)
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=parent_id,
                        path="/d/straggler.txt",
                        name="straggler.txt",
                        kind="file",
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("purge:post-collect", straggler):
                await _purge_subtree(session, tables, 1_000, "/d")
            subtree = (entry.c.path == "/d") | entry.c.path.like("/d/%")
            remaining = (await session.execute(select(entry.c.path).where(subtree))).all()
            assert remaining == []
            await session.rollback()
        await storage.close()

    async def test_purge_statements_never_double_the_membership_chunk(self, tmp_path, monkeypatch) -> None:
        # Tiny budget → membership 16. Every purge DELETE must carry at
        # most one chunk of binds — the edges statement used to OR two
        # lists together, doubling past the tightest engine's cap.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        paths = [Path(f"/d/f{i:02}.txt") for i in range(40)]
        written = await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)
        assert written.success is True, written.errors
        tables = storage._host.tables
        entry = tables.entry
        async with storage._host.session_factory() as session:
            found = await session.execute(select(entry.c.entry_id).where(entry.c.path.like("/d/%")))
            ids = [row.entry_id for row in found]
            for eid in ids[:20]:
                await session.execute(
                    insert(tables.edges).values(source_id=eid, target_id=str(ULID()), edge_type="ref")
                )
                await session.execute(
                    insert(tables.edges).values(source_id=str(ULID()), target_id=eid, edge_type="ref")
                )
            await session.commit()
        counts: list[int] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement.lstrip().upper().startswith("DELETE"):
                counts.append(statement.count("?"))

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.sweep(path=Path("/d"))).success
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        budget = membership_budget(storage._host.profile, 48)
        assert counts and max(counts) <= budget
        # 41 rows at chunk size 16 → three chunks through all six deletes.
        assert len(counts) >= 18
        await storage.close()


class TestTopologyOptionsStamping:
    """Every topology verb stamps the topology options, never the op pin."""

    async def test_topology_verbs_stamp_the_topology_execution_options(self, tmp_path, monkeypatch) -> None:
        calls: list[object] = []
        real = backend_module.topology_execution_options

        def spy(profile):
            calls.append(profile)
            return real(profile)

        monkeypatch.setattr(backend_module, "topology_execution_options", spy)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.move(operations=[ResolvedPair(src=Path("/b.txt"), dest=Path("/c.txt"))])).success
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/c.txt"), dest=Path("/d.txt"))])).success
        assert calls == [storage._host.profile] * 3
        await storage.close()


class TestTrashBucketBump:
    """The bucket is a directory like any other: gaining a member bumps it."""

    async def test_each_delete_bumps_the_bucket_it_lands_in(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x"), Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        assert (await storage.delete(path=Path("/b.txt"))).success
        buckets = (await storage.ls(path=Path("/.vfs/trash"))).observations
        if len(buckets) != 1:
            pytest.skip("hour boundary crossed between deletes")
        bucket = (await storage.stat(path=buckets[0].path)).observations[0]
        # Minted at 1, bumped once per member gained.
        assert bucket.version == 3
        await storage.close()


# ---------------------------------------------------------------------------
# Write-vs-topology coherence — the two-sided guards on the parent row
# ---------------------------------------------------------------------------


class TestWriteVsTopologyCoherence:
    """Seam-staged one-shot repros for every closed window.

    Handlers run on the verb's own session, so their effects are exactly
    what the guards' current reads would see from a committed rival —
    SQLite's single-writer lock rules out a genuine second connection,
    which is what the engine-leg race suite is for.
    """

    async def test_bump_guard_aborts_when_a_parent_relocates_mid_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                stmt = update(entry).where(entry.c.path == "/d").values(path="/d-moved", name="d-moved")
                await session.execute(stmt)

            with installed("write:before-apply", rival), pytest.raises(StaleSnapshot):
                await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/d/f.txt"), content="x")],
                    overwrite=True,
                    parents=False,
                    user_id=None,
                )
            await session.rollback()
        # Nothing committed: no torn child, and the parent stands untouched.
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        assert (await storage.stat(path=Path("/d"))).success is True
        await storage.close()

    async def test_bump_guard_aborts_when_a_parent_is_destroyed_mid_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                await session.execute(delete(entry).where(entry.c.path == "/d"))

            with installed("write:before-apply", rival), pytest.raises(StaleSnapshot):
                await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/d/f.txt"), content="x")],
                    overwrite=True,
                    parents=False,
                    user_id=None,
                )
            await session.rollback()
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        await storage.close()

    async def test_backend_redrives_a_stale_snapshot_and_classifies_exhaustion(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        fired = 0

        async def once() -> None:
            nonlocal fired
            fired += 1
            if fired == 1:
                raise StaleSnapshot("staged miss")

        with installed("write:before-apply", once):
            result = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        assert result.success is True
        assert fired == 2  # attempt one raised, the redrive landed

        async def always() -> None:
            raise StaleSnapshot("staged miss")

        with installed("write:before-apply", always):
            exhausted = await storage.write(entries=[Entry(path=Path("/d/g.txt"), content="x")])
        assert exhausted.success is False
        [error] = exhausted.errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        await storage.close()

    async def test_edit_conflicts_when_an_ancestor_relocated_mid_window(self, tmp_path) -> None:
        # A subtree rewrite moves descendant paths without bumping their
        # versions — the path predicate, not the version, must miss.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="old")], parents=True)
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                stmt = update(entry).where(entry.c.path == "/d/f.txt").values(path="/gone/f.txt")
                await session.execute(stmt)

            with installed("write:before-apply", rival):
                result = await edit_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    edits=[EditOperation(old="old", new="new")],
                    targets=[Path("/d/f.txt")],
                    user_id=None,
                )
            await session.rollback()
        assert result.success is False
        [error] = result.errors
        assert error.kind == VFSErrorKind.conflict
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "old"
        await storage.close()

    async def test_write_never_adopts_a_row_whose_stored_path_disagrees(self, tmp_path) -> None:
        # The ghost name-squat: a row matched by (parent_id, name) whose
        # stored path contradicts the requested address absorbs nothing.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        ghost_id = str(ULID())
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            d_id = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            await conn.execute(
                insert(entry).values(
                    entry_id=ghost_id,
                    parent_id=d_id,
                    path="/elsewhere/late.txt",
                    name="late.txt",
                    kind="file",
                    version=5,
                    size_bytes=4,
                    lines=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        result = await storage.write(entries=[Entry(path=Path("/d/late.txt"), content="mine")], overwrite=True)
        assert result.success is False
        [error] = result.errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        async with host.session_factory() as session:
            conn = await session.connection()
            row = (await conn.execute(select(entry.c.version, entry.c.path).where(entry.c.entry_id == ghost_id))).one()
        assert (row.version, row.path) == (5, "/elsewhere/late.txt")
        await storage.close()

    async def test_copy_stamps_metadata_and_body_from_one_observation(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/src.txt"), content="original body")])
        expected_hash = Entry(path=Path("/src.txt"), content="original body").content_hash
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                src = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/src.txt"))).scalar_one()
                await session.execute(
                    update(entry).where(entry.c.entry_id == src).values(content_hash="rival-hash", size_bytes=10)
                )
                await session.execute(delete(tables.content).where(tables.content.c.entry_id == src))
                await session.execute(
                    insert(tables.content).values(entry_id=src, created_at=datetime.now(UTC), content="rival body")
                )

            with installed("transfer:post-collect", rival):
                result = await transfer_rows(
                    session,
                    tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="copy",
                    operations=[ResolvedPair(src=Path("/src.txt"), dest=Path("/copy.txt"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            assert result.success is True
            copied = (
                await session.execute(select(entry.c.entry_id, entry.c.content_hash).where(entry.c.path == "/copy.txt"))
            ).one()
            body_query = select(tables.content.c.content).where(tables.content.c.entry_id == copied.entry_id)
            body = (await session.execute(body_query)).scalar_one()
            await session.rollback()
        # Metadata and body ride one read: the pre-rival pair, coherent.
        assert copied.content_hash == expected_hash
        assert body == "original body"
        await storage.close()

    async def test_delete_claim_misses_when_a_rival_lands_post_collect(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                # A rival create's parent bump: the descendant list is stale.
                stmt = update(entry).where(entry.c.path == "/d").values(version=entry.c.version + 1)
                await session.execute(stmt)

            with installed("delete:post-collect", rival), pytest.raises(StaleSnapshot):
                await delete_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d")],
                    cascade=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        # The verb redrives clean once the rival is out of the window.
        assert (await storage.delete(path=Path("/d"))).success is True
        await storage.close()

    async def test_move_claim_misses_when_a_rival_lands_post_collect(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                stmt = update(entry).where(entry.c.path == "/d").values(version=entry.c.version + 1)
                await session.execute(stmt)

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="move",
                    operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))])).success is True
        await storage.close()

    async def test_restore_address_race_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        assert (await storage.delete(path=Path("/d/f.txt"))).success is True
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                # An unserialized write claims the destination after the ladder ran.
                d_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=d_id,
                        path="/d/f.txt",
                        name="f.txt",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("restore:post-resolve", rival), pytest.raises(StaleSnapshot):
                await restore_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d/f.txt")],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_purge_deletes_entries_first_so_a_rival_body_cannot_leak(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            f_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d/f.txt"))).scalar_one()

            async def rival() -> None:
                clear("purge:pre-entry-delete")
                # The rival's content replace: delete-then-insert of the body.
                await session.execute(delete(tables.content).where(tables.content.c.entry_id == f_id))
                await session.execute(
                    insert(tables.content).values(entry_id=f_id, created_at=datetime.now(UTC), content="fresh")
                )

            with installed("purge:pre-entry-delete", rival):
                result = await sweep_rows(
                    session,
                    tables,
                    host.profile,
                    host.membership_budget,
                    path=Path("/d"),
                    trash_days=90,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            assert result.success is True
            leftovers = (await session.execute(select(tables.content.c.entry_id))).all()
            await session.rollback()
        # The side-table pass ran after the entry delete over the same ids:
        # the rival's fresh body rode out with the subtree.
        assert leftovers == []
        await storage.close()

    async def test_sweep_reclaims_only_aged_orphan_content(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        host = storage._host
        tables = host.tables
        old_id, young_id = str(ULID()), str(ULID())
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(
                insert(tables.content).values(
                    entry_id=old_id, created_at=datetime.now(UTC) - timedelta(hours=25), content="old orphan"
                )
            )
            await conn.execute(
                insert(tables.content).values(
                    entry_id=young_id, created_at=datetime.now(UTC) - timedelta(hours=1), content="young orphan"
                )
            )
            await session.commit()
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True  # reclaims are warnings, not failures
        warnings = [e for e in result.errors if e.severity == Severity.warning]
        assert [w.data["entry_id"] for w in warnings if w.data] == [old_id]
        assert warnings[0].kind == VFSErrorKind.internal
        async with host.session_factory() as session:
            conn = await session.connection()
            remaining = {row.entry_id for row in await conn.execute(select(tables.content.c.entry_id))}
        assert remaining == {young_id}
        await storage.close()

    async def test_a_trash_root_squatter_never_blocks_orphan_reclaim(self, tmp_path) -> None:
        # The squatter skips the bucket walk; the reclaim pass is
        # unconditional — sweep is the only drain for orphaned bodies.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/.vfs/trash"), content="squat")], parents=True)
        host = storage._host
        tables = host.tables
        old_id = str(ULID())
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(
                insert(tables.content).values(
                    entry_id=old_id, created_at=datetime.now(UTC) - timedelta(hours=25), content="old orphan"
                )
            )
            await session.commit()
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert result.observations == []
        assert result.errors[0].path == "/.vfs/trash"  # the squatter skip still surfaces first
        reclaims = [e for e in result.errors if e.data and "entry_id" in e.data]
        assert [w.data["entry_id"] for w in reclaims if w.data] == [old_id]
        async with host.session_factory() as session:
            conn = await session.connection()
            remaining = {row.entry_id for row in await conn.execute(select(tables.content.c.entry_id))}
        assert old_id not in remaining
        assert (await storage.read(path=Path("/.vfs/trash"))).observations[0].content == "squat"
        await storage.close()

    async def test_bump_values_arm_is_a_guarded_join_and_verifies_the_count(self) -> None:
        # The set-based arm SQLite cannot execute (postgres/mssql): the
        # statement joins (entry_id, path) and the RETURNING count is the
        # proof — one short row raises for the whole batch.
        tables = build_vfs_tables(table_name="vfs")
        pairs = [("A" * 26, "/a"), ("B" * 26, "/b")]
        double = _ReturningSession([{"entry_id": pairs[0][0]}])
        with pytest.raises(StaleSnapshot):
            await _bump_by_values(cast("AsyncSession", double), tables.entry, 32_000, 900, pairs)
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "FROM (VALUES" in sql
        assert "incoming.v_path" in sql  # the address guard joins the VALUES row
        assert "RETURNING" in sql

    async def test_guard_miss_mode_is_declared_per_dialect(self) -> None:
        assert PROFILES["mysql"].guard_miss == "redrive"
        assert PROFILES["mariadb"].guard_miss == "redrive"
        assert GENERIC.guard_miss == "redrive"
        for name in ("sqlite", "postgresql", "mssql", "oracle"):
            assert PROFILES[name].guard_miss == "reprobe"
        # Unknown dialects inherit the conservative floor.
        assert profile_for("exotic").guard_miss == "redrive"

    async def test_redrive_mode_raises_instead_of_classifying_off_the_probe(self, tmp_path) -> None:
        # The mysql-family declaration through the live aggregate arm: a
        # zero-row guard must not be blamed off a probe the isolation
        # level would falsify — the whole method retries instead.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            found = await session.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == "/a.txt"))
            row = found.one()
            stale = StagedEntry(
                path=Path("/a.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=row.entry_id,
                content="a2",
                base_version=999_999,
                version=1_000_000,
            )
            with pytest.raises(StaleSnapshot):
                await _update_materials(
                    session,
                    entry,
                    MYSQL,  # redrive-mode profile over the live sqlite session
                    host.parameter_budget,
                    host.membership_budget,
                    [stale],
                    user_id=None,
                    now=datetime.now(UTC),
                )
            await session.rollback()
        await storage.close()

    async def test_move_address_race_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/e",
                        name="e",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="move",
                    operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_copy_address_race_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/src.txt"), content="x")])
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/copy.txt",
                        name="copy.txt",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="copy",
                    operations=[ResolvedPair(src=Path("/src.txt"), dest=Path("/copy.txt"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_purge_raises_when_a_collected_row_vanishes(self, tmp_path) -> None:
        # Collected entries cannot lawfully vanish under the serialization
        # point — a shortfall on the entry delete is a stale list, redriven.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(
            entries=[Entry(path=Path("/d/a.txt"), content="a"), Entry(path=Path("/d/b.txt"), content="b")],
            parents=True,
        )
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                clear("purge:pre-entry-delete")
                await session.execute(delete(entry).where(entry.c.path == "/d/a.txt"))

            with installed("purge:pre-entry-delete", rival), pytest.raises(StaleSnapshot):
                await sweep_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    path=Path("/d"),
                    trash_days=90,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_ghost_at_the_original_site_blocks_restore_with_retryable_conflict(self, tmp_path) -> None:
        # The claim collides on (parent_id, name) with a ghost whose stored
        # path is elsewhere: the destination probe finds nothing, and the
        # loss classifies as a retryable conflict — never raw driver text.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        assert (await storage.delete(path=Path("/d/f.txt"))).success is True
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            d_id = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            await conn.execute(
                insert(entry).values(
                    entry_id=str(ULID()),
                    parent_id=d_id,
                    path="/elsewhere/f.txt",
                    name="f.txt",
                    kind="file",
                    version=1,
                    size_bytes=0,
                    lines=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        result = await storage.restore(path=Path("/d/f.txt"))
        assert result.success is False
        [error] = result.errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "UNIQUE" not in error.message
        await storage.close()

    async def test_upsert_path_index_escape_redrives(self, tmp_path) -> None:
        # A rival claims the path with a different (parent_id, name): the
        # declared arbitration index never fires, the raw unique violation
        # is caught at the chunk savepoint, and the row-wise redrive blames
        # the exact row with the ladder's own conflict.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/d/late.txt",
                        name="squatter",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("write:before-apply", rival), pytest.raises(StaleSnapshot):
                await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/d/late.txt"), content="mine")],
                    overwrite=True,
                    parents=False,
                    user_id=None,
                )
            await session.rollback()
        await storage.close()

    async def test_resolve_rows_refuses_a_ghost_instead_of_absorbing(self, tmp_path) -> None:
        # The catch-retry arm's occupant probe: the matched row's stored
        # path contradicts the request — never absorbed, retryable conflict.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            d_id = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            await conn.execute(
                insert(entry).values(
                    entry_id=str(ULID()),
                    parent_id=d_id,
                    path="/elsewhere/late.txt",
                    name="late.txt",
                    kind="file",
                    version=1,
                    size_bytes=0,
                    lines=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            staged = StagedEntry(
                path=Path("/d/late.txt"),
                parent=Path("/d"),
                kind="file",
                persistence="insert",
                entry_id=str(ULID()),
                content="mine",
            )
            rows = [_entry_values(staged, d_id, None, now)]
            errors = await _resolve_rows(session, entry, [staged], rows, overwrite=True)
            await session.rollback()
        [error] = errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert staged.persistence == "insert"  # never rewritten to absorb
        await storage.close()

    async def test_arbitration_loss_with_a_vanished_occupant_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        async with host.session_factory() as session:
            await session.connection()
            staged = _staged_material("/x.txt", str(ULID()))
            with pytest.raises(StaleSnapshot):
                await _classify_arbitration_loss(
                    session, host.tables.entry, staged, {"parent_id": str(ULID()), "name": "x.txt"}, clobber=False
                )
        await storage.close()

    async def test_classifier_redrive_mode_raises_for_any_miss(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        staged = _staged_material("/x.txt", str(ULID()))
        double = _ReturningSession([])
        with pytest.raises(StaleSnapshot):
            await _classify_guard_misses(cast("AsyncSession", double), tables.entry, MYSQL, 900, [staged])

    async def test_bump_parents_dispatches_by_declared_capability(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        parent_id = "D" * 26

        def plan() -> WritePlan:
            built = WritePlan({"/d": {"entry_id": parent_id, "path": "/d"}}, user_id=None, budget=4_096)  # ty: ignore[invalid-argument-type]
            built.stage_create(Path("/d/f.txt"), kind="file", content="x")
            return built

        # The set-based arm: a guarded VALUES join, verified by RETURNING.
        values_double = _ReturningSession([{"entry_id": parent_id}])
        errors = await _bump_parents(cast("AsyncSession", values_double), tables.entry, POSTGRESQL, 32_000, 900, plan())
        assert errors == []
        assert "FROM (VALUES" in str(values_double.statements[0].compile(dialect=postgresql.dialect()))
        # The per-row floor: no sane aggregate, each statement's own rowcount.
        floor_double = _ReturningSession([{"entry_id": parent_id}])
        errors = await _bump_parents(cast("AsyncSession", floor_double), tables.entry, SQLITE, 32_000, 900, plan())
        assert errors == []
        # Nothing verifiable: the classified refusal, never a blind bump.
        blind = _ReturningSession([])
        blind.get_bind = lambda: SimpleNamespace(  # ty: ignore[invalid-assignment]
            dialect=SimpleNamespace(
                update_returning=False,
                update_returning_multifrom=False,
                supports_sane_rowcount=False,
                supports_sane_multi_rowcount=False,
            )
        )
        errors = await _bump_parents(cast("AsyncSession", blind), tables.entry, GENERIC, 32_000, 900, plan())
        assert [e.kind for e in errors] == [VFSErrorKind.unsupported]

    async def test_new_seams_fire_inside_their_verbs(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(
            entries=[Entry(path=Path("/d/f.txt"), content="x"), Entry(path=Path("/m.txt"), content="y")],
            parents=True,
        )
        fired: list[str] = []

        def recorder(name: str):
            async def handler() -> None:
                fired.append(name)

            return handler

        with installed("delete:post-collect", recorder("delete:post-collect")):
            assert (await storage.delete(path=Path("/d"))).success is True
        with installed("transfer:post-collect", recorder("transfer:post-collect")):
            assert (await storage.move(operations=[ResolvedPair(src=Path("/m.txt"), dest=Path("/n.txt"))])).success
        with installed("restore:post-resolve", recorder("restore:post-resolve")):
            assert (await storage.restore(path=Path("/d"))).success is True
        with installed("purge:pre-entry-delete", recorder("purge:pre-entry-delete")):
            assert (await storage.sweep(path=Path("/n.txt"))).success is True
        assert fired == [
            "delete:post-collect",
            "transfer:post-collect",
            "restore:post-resolve",
            "purge:pre-entry-delete",
        ]
        await storage.close()

    async def test_claim_verifies_by_returning_when_rowcount_is_insane(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        entry = tables.entry
        stmt = update(entry).where(entry.c.entry_id == "X" * 26, entry.c.version == 1).values(version=2)

        def insane_bind(*, returning: bool) -> SimpleNamespace:
            dialect = SimpleNamespace(
                supports_sane_rowcount=False, update_returning=returning, delete_returning=returning
            )
            return SimpleNamespace(dialect=dialect)

        proven = _ReturningSession([{"entry_id": "X" * 26}])
        proven.get_bind = lambda: insane_bind(returning=True)  # ty: ignore[invalid-assignment]
        assert await _claim(cast("AsyncSession", proven), GENERIC, stmt, entry.c.entry_id, miss="m") is None
        missed = _ReturningSession([])
        missed.get_bind = lambda: insane_bind(returning=True)  # ty: ignore[invalid-assignment]
        with pytest.raises(StaleSnapshot):
            await _claim(cast("AsyncSession", missed), GENERIC, stmt, entry.c.entry_id, miss="m")
        # Nothing verifiable: the classified refusal, never a blind claim —
        # for the DELETE shape too, which consults delete_returning.
        blind = _ReturningSession([])
        blind.get_bind = lambda: insane_bind(returning=False)  # ty: ignore[invalid-assignment]
        refused = await _claim(cast("AsyncSession", blind), GENERIC, stmt, entry.c.entry_id, miss="m")
        assert refused is not None and refused.kind == VFSErrorKind.unsupported
        destroy = delete(entry).where(entry.c.entry_id == "X" * 26)
        refused = await _claim(cast("AsyncSession", blind), GENERIC, destroy, entry.c.entry_id, miss="m")
        assert refused is not None and refused.kind == VFSErrorKind.unsupported

    async def test_unverifiable_claims_refuse_the_topology_verbs(self, tmp_path, monkeypatch) -> None:
        # An insane-rowcount, no-RETURNING dialect must refuse each claim
        # site with unsupported — never pass a guard it cannot prove.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        await storage.mkdir(path=Path("/b"))
        await storage.mkdir(path=Path("/d"))
        assert (await storage.write(entries=[Entry(path=Path("/t.txt"), content="y")])).success
        assert (await storage.delete(path=Path("/t.txt"))).success
        host = storage._host
        dialect = host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        monkeypatch.setattr(dialect, "update_returning", False)
        monkeypatch.setattr(dialect, "delete_returning", False)
        # The delete reparent claim (its trash chain pre-minted above).
        result = await storage.delete(path=Path("/a.txt"))
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        # The move source claim, no occupant in the way.
        result = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/c.txt"))])
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        # The overwrite fence on a directory occupant needs a directory
        # source; the refusal fires at the fence, before any purge.
        result = await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/b"))], overwrite=True)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        # The restore claim, through the shared executor.
        result = await storage.restore(path=Path("/t.txt"))
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        await storage.close()

    async def test_delete_recollects_rewrites_after_its_claim(self, tmp_path) -> None:
        # The depth-2 window: a rival lands under a subdirectory after the
        # pre-claim collection; the post-claim re-collection carries it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/sub/keep.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                sub_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d/sub"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=sub_id,
                        path="/d/sub/new.txt",
                        name="new.txt",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("delete:post-collect", rival):
                result = await delete_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d")],
                    cascade=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            assert result.success is True, result.errors
            stranded = (await session.execute(select(entry.c.path).where(entry.c.path.like("/d/%")))).scalars().all()
            moved = (await session.execute(select(entry.c.path).where(entry.c.name == "new.txt"))).scalar_one()
            await session.rollback()
        # The late row rode the re-collection into trash with its subtree.
        assert stranded == []
        assert moved.startswith("/.vfs/trash/")
        await storage.close()

    async def test_late_arrival_over_the_byte_budget_redrives_the_delete(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/sub/keep.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        # Fits as a live path; overflows once the trash prefix lands on /d.
        long_tail = "/d/sub/" + "x" * (MAX_PATH_LENGTH - len("/d/sub/") - 10)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                sub_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d/sub"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=sub_id,
                        path=long_tail,
                        name=long_tail.rsplit("/", 1)[-1],
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("delete:post-collect", rival), pytest.raises(StaleSnapshot):
                await delete_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d")],
                    cascade=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_overwrite_fence_redrives_when_the_occupant_was_bumped(self, tmp_path) -> None:
        # The silent-destruction window: a rival's committed child bumps
        # the occupant after the emptiness check — the fence must flip.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/a"))
        await storage.mkdir(path=Path("/b"))
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                await session.execute(update(entry).where(entry.c.path == "/b").values(version=entry.c.version + 1))

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="move",
                    operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))],
                    overwrite=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_directory_adopting_its_rival_reports_unchanged(self, tmp_path) -> None:
        # Concurrent ancestor minting: the loser adopts the standing
        # directory and the batch converges to success, mkdir -p parity.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            rival_id = str(ULID())

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=rival_id,
                        parent_id=root_id,
                        path="/x",
                        name="x",
                        kind="directory",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("write:before-apply", rival):
                result = await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[
                        Entry(path=Path("/x"), kind="directory"),
                        Entry(path=Path("/x/f.txt"), content="mine"),
                    ],
                    overwrite=False,
                    parents=True,
                    user_id=None,
                )
            stored = (await session.execute(select(entry.c.version).where(entry.c.path == "/x"))).scalar_one()
            await session.rollback()
        assert result.success is True, result.errors
        by_path = {str(o.path): o for o in result.observations}
        assert by_path["/x"].status == "unchanged"
        assert by_path["/x/f.txt"].status == "created"
        # The adopted parent is affirmed: attaching f.txt bumped the
        # rival's row, and the observation equals the stored state.
        assert stored == 2
        assert by_path["/x"].version == 2
        await storage.close()

    async def test_adopting_without_attaching_children_bumps_nothing(self, tmp_path) -> None:
        # An adopted create that changed no membership registers no bump:
        # neither the rival's row nor the grandparent moves — the same
        # versions a sequential exist_ok mkdir would leave.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            root_before = (await session.execute(select(entry.c.version).where(entry.c.path == "/"))).scalar_one()

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/x",
                        name="x",
                        kind="directory",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("write:before-apply", rival):
                result = await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/x"), kind="directory")],
                    overwrite=False,
                    parents=False,
                    user_id=None,
                )
            root_after = (await session.execute(select(entry.c.version).where(entry.c.path == "/"))).scalar_one()
            adopted = (await session.execute(select(entry.c.version).where(entry.c.path == "/x"))).scalar_one()
            await session.rollback()
        assert result.success is True, result.errors
        assert result.observations[0].status == "unchanged"
        assert result.observations[0].version == 1
        assert adopted == 1
        assert root_after == root_before
        await storage.close()

    async def test_write_refuses_when_the_parent_bump_cannot_be_verified(self, tmp_path, monkeypatch) -> None:
        # The writes-side twin of the topology capability test: a dialect
        # that can prove nothing refuses the whole write — never a child
        # committed under an unaffirmed parent.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.mkdir(path=Path("/d"))).success
        parent_version = (await storage.stat(path=Path("/d"))).observations[0].version
        dialect = storage._host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        monkeypatch.setattr(dialect, "supports_sane_multi_rowcount", False)
        result = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        monkeypatch.undo()
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        assert (await storage.stat(path=Path("/d"))).observations[0].version == parent_version
        await storage.close()

    async def test_read_retry_exhaustion_classifies_conflict(self, tmp_path, monkeypatch) -> None:
        # Both retry channels exhaust identically on the read path too:
        # a retryable conflict with clean text, never raw driver output.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()

        async def exhausted(fn: object) -> Result:
            raise StaleSnapshot("a retryable engine conflict outlived 3 attempts")

        monkeypatch.setattr(storage._host, "with_retry", exhausted)
        result = await storage.stat(path=Path("/"))
        assert result.success is False
        error = result.errors[0]
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "outlived 3 attempts" in error.message
        await storage.close()

    async def test_first_touch_retry_exhaustion_classifies_conflict(self, tmp_path, monkeypatch) -> None:
        # The third with_retry caller: exhaustion during lazy first touch
        # is the same classified conflict, never a raw internal raise.
        storage = DatabaseStorage(url=_url(tmp_path))

        async def exhausted(fn: object) -> Result:
            raise StaleSnapshot("a retryable engine conflict outlived 3 attempts")

        monkeypatch.setattr(storage._host, "with_retry", exhausted)
        result = await storage.stat(path=Path("/"))
        assert result.success is False
        error = result.errors[0]
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "First touch kept losing to concurrent changes" in error.message
        assert "outlived 3 attempts" in error.message
        monkeypatch.undo()
        recovered = await storage.stat(path=Path("/"))
        assert recovered.success is True  # exhaustion never wedged readiness
        await storage.close()

    def test_statement_budget_measures_fixed_binds_and_caps_width(self) -> None:
        # The bump statement carries one fixed bind (the SQL-side
        # increment); the helper measures it off the compiled statement
        # and keeps the reserve clear of the engine cap.
        tables = build_vfs_tables(table_name="vfs")
        entry = tables.entry
        pair = ("A" * 26, "/a")
        dialect = mssql.dialect()
        rows = statement_budget(
            lambda probe: _bump_values_stmt(entry, probe),
            pair,
            dialect,
            parameter_budget=2_099,
            row_width=2,
        )
        assert rows == (2_099 - 1 - 8) // 2
        assert rows * 2 + 1 <= 2_099 - 8
        # An even budget distinguishes the fixed-bind subtraction the
        # odd 2,099 pin arithmetically absorbs (1,045 vs 1,046).
        even = statement_budget(
            lambda probe: _bump_values_stmt(entry, probe),
            pair,
            dialect,
            parameter_budget=2_100,
            row_width=2,
        )
        assert even == (2_100 - 1 - 8) // 2
        capped = statement_budget(
            lambda probe: _bump_values_stmt(entry, probe),
            pair,
            dialect,
            parameter_budget=2_099,
            row_width=2,
            row_cap=100,
        )
        assert capped == 100
        # An understated width is drift: it must fail loudly at the
        # helper, never at row N of a production batch.
        with pytest.raises(AssertionError, match="row width"):
            statement_budget(
                lambda probe: _bump_values_stmt(entry, probe),
                pair,
                dialect,
                parameter_budget=2_099,
                row_width=1,
            )

    def test_statement_budget_charges_sparse_rows_at_the_declared_width(self) -> None:
        # NULL cells compile inline, so a sparse probe row measures a
        # smaller delta; the chunk is charged at the declared ceiling
        # regardless, or a mixed batch overflows the engine cap mid-run.
        tables = build_vfs_tables(table_name="vfs")
        entry = tables.entry
        dialect = mssql.dialect()
        width = len(_CLOBBER_COLUMNS) + 4
        now = datetime.now(UTC)
        full = (str(ULID()), 1, 2, "/full.txt", "file", "h" * 64, "text/plain", "txt", 1, 4, "O" * 26, now)
        sparse = (str(ULID()), 1, 2, "/sparse", "file", None, None, None, 0, 0, None, now)

        def budget(row: tuple[object, ...]) -> int:
            return statement_budget(
                lambda probe: _values_update_stmt(entry, probe, guard=True),
                row,
                dialect,
                parameter_budget=2_099,
                row_width=width,
            )

        # The premise: the sparse probe really undershoots the ceiling.
        one = len(_values_update_stmt(entry, [sparse], guard=True).compile(dialect=dialect).bind_names)
        two = len(_values_update_stmt(entry, [sparse, sparse], guard=True).compile(dialect=dialect).bind_names)
        assert two - one < width
        assert budget(sparse) == budget(full)

    async def test_upsert_escape_that_classifies_keeps_the_chunk_loop_going(self) -> None:
        # An IntegrityError escaping ON CONFLICT re-drives row-wise; when
        # the probe classifies (a ghost refusal, not a vanished occupant)
        # the layer keeps its errors and moves to the next chunk.
        tables = build_vfs_tables(table_name="vfs")
        staged = StagedEntry(
            path=Path("/d/late.txt"),
            parent=Path("/d"),
            kind="file",
            persistence="insert",
            entry_id=str(ULID()),
            content="mine",
        )
        rows = [_entry_values(staged, "P" * 26, None, datetime.now(UTC))]
        ghost = SimpleNamespace(entry_id="G" * 26, kind="file", path="/elsewhere/late.txt", version=1)

        class _Nested:
            async def __aenter__(self) -> _Nested:
                return self

            async def __aexit__(self, *exc: object) -> bool:
                return False

        class _ProbeResult:
            def one_or_none(self) -> SimpleNamespace:
                return ghost

        class _EscapeSession:
            def begin_nested(self) -> _Nested:
                return _Nested()

            async def execute(self, stmt: Any, params: Any = None) -> _ProbeResult:
                if isinstance(stmt, Select):
                    return _ProbeResult()
                raise IntegrityError("stmt", None, Exception("duplicate"))

        errors = await _upsert_layer(
            cast("AsyncSession", _EscapeSession()), tables.entry, SQLITE, [staged], rows, 50, overwrite=True
        )
        [error] = errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "may not adopt" in error.message
        assert error.data == {"target": "/d/late.txt"}  # distinct refusals stay distinct facts
        assert staged.persistence == "insert"  # the ghost was never absorbed
