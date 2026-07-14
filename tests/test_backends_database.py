"""DatabaseStorage lifecycle tests — construction, first touch, retry, close.

The conformance suite covers verb behavior once families land; this file
holds the DB-specific contract: the construction XOR, idempotent
provisioning under the serialization point, schema-version verification,
restart rebind, cross-loop first touch, borrowed-pool close, and the
dialect policy layer (generic floor, retryable classification).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import create_async_engine
from ulid import ULID

from vfs.models.rows import MAX_TABLE_NAME_LENGTH, SCHEMA_FORMAT_VERSION, ULID_LENGTH, build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, StorageBackend, SupportsClose, SupportsTraits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import (
    GENERIC,
    POSTGRESQL,
    SQLITE,
    is_retryable,
    profile_for,
)


def _url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite"


# ---------------------------------------------------------------------------
# Construction XOR
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_url_and_engine_together_are_refused(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        with pytest.raises(ValueError, match="exactly one"):
            DatabaseStorage(url=_url(tmp_path), engine=engine)

    def test_neither_url_nor_engine_is_refused(self) -> None:
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

    def test_parameter_budget_is_read_from_sqlalchemy(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        host = storage._host
        assert host.parameter_budget == host.engine.dialect.insertmanyvalues_max_parameters
        assert host.parameter_budget >= 999


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
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unsupported
        assert storage.mount_identity is not None  # provisioning happened anyway
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
        storage = DatabaseStorage(engine=engine)
        assert (await storage.first_touch()).success is True
        async with storage._host._writer_engine.begin() as conn:
            like = (await conn.exec_driver_sql("SELECT 'A' LIKE 'a'")).scalar_one()
            timeout = (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar_one()
        assert like == 0  # case_sensitive_like = ON
        assert timeout == 5000
        await storage.close()
        await engine.dispose()

    async def test_borrowed_engine_close_never_disposes(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        storage = DatabaseStorage(engine=engine)
        assert (await storage.first_touch()).success is True
        await storage.close()
        async with engine.connect() as conn:  # the pool must still serve
            assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
        await engine.dispose()

    async def test_built_close_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        await storage.close()
        await storage.close()
