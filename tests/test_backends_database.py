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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import create_engine, event, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from ulid import ULID

from vfs.models import Entry, Observation
from vfs.models.rows import MAX_TABLE_NAME_LENGTH, SCHEMA_FORMAT_VERSION, ULID_LENGTH, build_vfs_tables
from vfs.paths import ObjectKind, Path
from vfs.results import ResultError, VFSErrorKind
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, ResolvedPair, StorageBackend, SupportsClose, SupportsTraits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MSSQL,
    POSTGRESQL,
    SQLITE,
    is_retryable,
    membership_budget,
    profile_for,
)
from vfs.storage.backends.database.engine import EngineHost, _install_sqlite_transaction_control
from vfs.storage.backends.database.staging import StagedEntry, WritePlan
from vfs.storage.backends.database.writes import (
    _CLOBBER_COLUMNS,
    _catch_retry_layer,
    _entry_values,
    _fetch_committed,
    _finish,
    _material_values,
    _resolve_rows,
    _update_materials,
    _upsert_constructor,
    _upsert_layer,
)
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


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

    def test_parameter_budget_is_read_from_sqlalchemy(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        host = storage._host
        assert host.parameter_budget == host.engine.dialect.insertmanyvalues_max_parameters
        assert host.parameter_budget >= 999

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
                    name="",
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
                await conn.execute(insert(tables.content).values(entry_id=entry_key, content=content))

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
        host = EngineHost(url=_url(tmp_path), retry_attempts=2, retry_base_delay=0.001)

        async def always_busy() -> None:
            raise DBAPIError("SELECT 1", None, _SqliteError(5))

        with pytest.raises(DBAPIError):
            await host.with_retry(always_busy)
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
        pair = [ResolvedPair(src=Path("/a"), dest=Path("/b"))]
        calls = [
            storage.grep(pattern="x"),
            storage.delete(path=Path("/a")),
            storage.move(operations=pair),
            storage.copy(operations=pair),
            storage.mkedge(source=Path("/a"), target=Path("/b"), edge_type="imports"),
        ]
        for call in calls:
            result = await call
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.unsupported
        stubbed = {"grep", "delete", "move", "copy", "mkedge"}
        assert storage.capabilities() == {"read", "stat", "ls", "tree", "glob", "write", "edit", "mkdir"}
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
            path=Path("/f.txt"), parent=Path("/"), kind="file", created=True, entry_id=str(ULID()), content="x"
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
            return [s for s in statements if not s.startswith(("BEGIN", "COMMIT", "PRAGMA"))]

        created = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="a")])
        assert created.success is True
        # The round-trip budget is a contract: fetch, insert, content
        # delete + insert, parent bump.
        assert len(mutations()) == 5, mutations()
        statements.clear()
        overwritten = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="b")])
        assert overwritten.success is True
        # Fetch, guarded update, verification read-back, content delete + insert.
        assert len(mutations()) == 5, mutations()
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
        assert plan.staged[target].created is True
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
                    created=True,
                    entry_id=str(ULID()),
                    content="mine",
                )
                for i in range(12)
            ]
            rows = [_entry_values(s, root_key, None, now) for s in layer]
            statements.clear()
            errors = await _catch_retry_layer(session, entry, layer, rows, 4, overwrite=True)
        assert errors == []
        assert layer[5].created is False and layer[5].entry_id == rival_key  # rival's row absorbed the write
        assert all(s.created for i, s in enumerate(layer) if i != 5)
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
                    created=True,
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
                    path=Path(path), parent=Path("/"), kind=kind, created=True, entry_id=str(ULID()), content="mine"
                )

            # overwrite=True over a rival file: converted to a clobbering
            # update that adopts the rival row's identity.
            clobber = staged_for("/f.txt", "file")
            errors = await _resolve_rows(
                session, entry, [clobber], [_entry_values(clobber, root_key, None, now)], overwrite=True
            )
            assert errors == []
            assert clobber.created is False and clobber.entry_id == rival_key and clobber.base_version is None

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

            # a directory create losing to any occupant: exists.
            dir_loss = staged_for("/dir", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_loss], [_entry_values(dir_loss, root_key, None, now)], overwrite=True
            )
            assert [e.kind for e in errors] == [VFSErrorKind.exists]
        await storage.close()

    async def test_resolve_rows_classifies_phantom_conflict_when_no_occupant(self, tmp_path) -> None:
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
                created=True,
                entry_id=str(ULID()),
                content="mine",
            )
            minted = phantom.entry_id
            errors = await _resolve_rows(
                session, entry, [phantom], [_entry_values(phantom, dir_key, None, datetime.now(UTC))], overwrite=True
            )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert "lost arbitration" in errors[0].message
        assert phantom.created is True and phantom.entry_id == minted  # no conversion happened
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
                    path=Path(path), parent=Path("/"), kind=kind, created=True, entry_id=str(ULID()), content="mine"
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
            # ...while the non-conflicted winner in the same statement
            # keeps its staged-minted identity untouched.
            assert fresh.entry_id == minted and fresh.version == 1

            # overwrite=False over a rival file: DO NOTHING, a definite exists.
            refused = staged_for("/f.txt", "file")
            errors = await run([refused], overwrite=False)
            assert [e.kind for e in errors] == [VFSErrorKind.exists]

            # overwrite=True where the rival is a directory: the clobber's
            # kind guard refuses to update it — wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await run([blocked], overwrite=True)
            assert [e.kind for e in errors] == [VFSErrorKind.wrong_kind]

            # a directory create losing to any occupant never clobbers: exists.
            dir_loss = staged_for("/dir", "directory")
            errors = await run([dir_loss], overwrite=True)
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
                created=False,
                entry_id=row.entry_id,
                content="b",
                base_version=999_999,  # a rival moved the row past our snapshot
                version=1_000_000,
            )
            budget = storage._host.membership_budget
            errors = await _update_materials(session, entry, budget, [stale], user_id=None, now=datetime.now(UTC))
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert "Concurrent modification" in errors[0].message
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
        assert "Concurrent modification" in result.errors[0].message
        assert (await storage.read(path=target)).observations[0].content == "v3"
        await storage.close()

    def test_upsert_constructor_is_dialect_bound(self) -> None:
        assert _upsert_constructor(SQLITE) is sqlite_insert
        assert _upsert_constructor(POSTGRESQL) is pg_insert


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
