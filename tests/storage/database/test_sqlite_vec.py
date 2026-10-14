"""sqlite-vec on every SQLite connection, the first-touch probe, and the capability gate
that withholds ranked search from a dialect with no distance function."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Final

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.support.database_helpers import _url
from tests.support.server_schemas import server_storage
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import (
    GENERIC,
    SQLITE,
    SQLITE_VEC_PROBE,
    VectorFunction,
    is_insufficient_privilege,
)
from vfs.storage.backends.memory import InMemoryStorage

INSTALL: Final = "CREATE EXTENSION IF NOT EXISTS vector"


def _postgres_denies_create_extension(statement: str) -> ProgrammingError:
    """The exact shape a refused CREATE EXTENSION reaches vfs in: SQLAlchemy's asyncpg adapter error, wrapped."""
    origin = AsyncAdapt_asyncpg_dbapi.ProgrammingError(
        "<class 'asyncpg.exceptions.InsufficientPrivilegeError'>: permission denied to create extension \"vector\""
    )
    origin.pgcode = origin.sqlstate = "42501"  # ty: ignore[unresolved-attribute]
    return ProgrammingError(statement, None, origin)


def _raising_for(monkeypatch: pytest.MonkeyPatch, statement: str, error: Exception) -> None:
    """Every connection raises *error* for *statement* and serves everything else."""
    real = AsyncConnection.exec_driver_sql

    async def exec_driver_sql(self: AsyncConnection, sql: str, *args: Any, **kwargs: Any) -> Any:
        if sql == statement:
            raise error
        return await real(self, sql, *args, **kwargs)

    monkeypatch.setattr(AsyncConnection, "exec_driver_sql", exec_driver_sql)


class TestSqliteVec:
    async def test_the_extension_is_loaded_on_every_connection(self, tmp_path: Any) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        async with storage._host.session_factory() as session:
            version = (await session.execute(text(engine_module.SQLITE_VEC_PROBE))).scalar_one()
            assert version.startswith("v")
            packed = (await session.execute(text("SELECT vec_f32('[1.0, 0.0]')"))).scalar_one()
            distance = (
                await session.execute(text("SELECT vec_distance_cosine(:a, :b)"), {"a": packed, "b": packed})
            ).scalar_one()
            assert distance == 0.0
        await storage.close()

    async def test_the_in_memory_store_loads_it_too(self) -> None:
        storage = InMemoryStorage()
        assert (await storage.first_touch()).success is True
        async with storage._host.session_factory() as session:
            assert (await session.execute(text(engine_module.SQLITE_VEC_PROBE))).scalar_one().startswith("v")
        await storage.close()

    async def test_an_interpreter_without_extension_loading_refuses_at_first_touch(
        self, tmp_path: Any, monkeypatch
    ) -> None:
        # The URL helper provisions this worker's template on first use; take it before the patch.
        url = _url(tmp_path)
        monkeypatch.setattr(engine_module, "_EXTENSIONS_LOADABLE", False)
        storage = DatabaseStorage(url=url)
        result = await storage.first_touch()
        assert result.success is False
        [refusal] = result.errors
        assert refusal.kind == ErrorKind.unavailable and "enable_load_extension" in refusal.message
        assert (await storage.stat(path=Path("/"))).success is False  # the latch never set
        await storage.close()

    def test_the_loader_ignores_a_connection_it_does_not_recognise(self) -> None:
        engine_module._load_sqlite_vec(object())  # no aiosqlite inner connection: nothing to load


class TestVectorProbe:
    def test_the_version_parses_both_spellings(self) -> None:
        assert engine_module._version_tuple("0.8.1") == (0, 8, 1)  # pgvector's catalog row
        assert engine_module._version_tuple("v0.1.6") == (0, 1, 6)  # sqlite-vec's vec_version()

    async def test_first_touch_keeps_the_probed_version(self, tmp_path: Any) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        assert storage._host.vector_version is not None and len(storage._host.vector_version) == 3
        await storage.close()

    async def test_a_probe_answering_no_row_refuses_naming_the_fix(self, tmp_path: Any, monkeypatch) -> None:
        # The pgvector shape: the catalog query returns no row when the extension is absent.
        url = _url(tmp_path)
        absent = replace(SQLITE, vector_function=VectorFunction("SELECT NULL WHERE 1 = 0", "install the function"))
        monkeypatch.setattr(engine_module, "profile_for", lambda name: absent)
        storage = DatabaseStorage(url=url)
        result = await storage.first_touch()
        assert result.success is False
        [refusal] = result.errors
        assert refusal.kind == ErrorKind.unavailable and "install the function" in refusal.message
        await storage.close()


class TestInstallExtensions:
    async def test_nothing_to_install_is_a_success_that_proves_the_function(self, tmp_path: Any) -> None:
        # SQLite: sqlite-vec ships with vfs, so the verb installs nothing and runs the probe.
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.install_extensions()
        assert result.success is True and result.observations == []
        assert storage._host.vector_version is not None
        assert (await storage.first_touch()).success is True
        await storage.close()

    async def test_an_install_the_engine_refuses_classifies_and_never_raises(self, tmp_path: Any, monkeypatch) -> None:
        url = _url(tmp_path)
        declared = replace(SQLITE, vector_function=VectorFunction(SQLITE_VEC_PROBE, "ask a DBA", install=INSTALL))
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        storage = DatabaseStorage(url=url)
        result = await storage.install_extensions()
        assert result.success is False
        [refusal] = result.errors
        # SQLite's syntax error carries only the generic result code, so it
        # classifies as first touch's would: retryable unavailable, no fix named.
        assert refusal.kind == ErrorKind.unavailable and refusal.retryable is True
        assert "ask a DBA" not in refusal.message
        await storage.close()

    async def test_a_role_that_may_not_install_is_permission_denied_naming_the_fix(
        self, tmp_path: Any, monkeypatch
    ) -> None:
        # The SQLSTATE rides on the driver exception behind SQLAlchemy's wrapper, as asyncpg's refusal arrives.
        url = _url(tmp_path)
        declared = replace(SQLITE, vector_function=VectorFunction(SQLITE_VEC_PROBE, "ask a DBA", install=INSTALL))
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        _raising_for(monkeypatch, INSTALL, _postgres_denies_create_extension(INSTALL))
        storage = DatabaseStorage(url=url)
        result = await storage.install_extensions()
        [refusal] = result.errors
        assert refusal.kind == ErrorKind.permission_denied and "ask a DBA" in refusal.message
        assert "permission denied to create extension" in refusal.message
        await storage.close()

    async def test_a_rival_installing_first_is_benign(self, tmp_path: Any, monkeypatch) -> None:
        # The IF NOT EXISTS race: the install statement's integrity violation is swallowed and the probe decides.
        # The single-row check on vfs_meta refuses id 2 whatever the template already holds.
        url = _url(tmp_path)
        clash = "INSERT INTO vfs_meta (id, schema_format_version, mount_identity, grant_revision) VALUES (2, 0, 'x', 0)"
        rival = VectorFunction(SQLITE_VEC_PROBE, "ask a DBA", install=clash)
        declared = replace(SQLITE, vector_function=rival)
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        storage = DatabaseStorage(url=url)
        result = await storage.install_extensions()
        assert result.success is True, result.errors
        await storage.close()

    async def test_a_dialect_with_nothing_declared_succeeds_without_probing(self, tmp_path: Any, monkeypatch) -> None:
        url = _url(tmp_path)
        declared = replace(SQLITE, vector_function=None)
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        storage = DatabaseStorage(url=url)
        assert (await storage.install_extensions()).success is True
        assert storage._host.vector_version is None
        await storage.close()

    def test_insufficient_privilege_is_read_from_the_sqlstate(self) -> None:
        class DeniedError(Exception):
            sqlstate = "42501"

        class SyntaxDefectError(Exception):
            sqlstate = "42601"

        assert is_insufficient_privilege(DeniedError()) is True
        assert is_insufficient_privilege(SyntaxDefectError()) is False
        assert is_insufficient_privilege(RuntimeError("no state")) is False

    def test_insufficient_privilege_is_read_through_sqlalchemy_wrapper_as_asyncpg_raises_it(self) -> None:
        denied = _postgres_denies_create_extension(INSTALL)
        assert is_insufficient_privilege(denied) is True
        assert is_insufficient_privilege(denied.orig) is True  # ty: ignore[invalid-argument-type]
        assert is_insufficient_privilege(ProgrammingError(INSTALL, None, Exception("42601", "syntax"))) is False

    async def test_a_transient_probe_failure_is_classified_and_never_read_as_missing(
        self, tmp_path: Any, monkeypatch
    ) -> None:
        # A raise the retry policy would restart is no verdict on the function: it names the real error.
        url = _url(tmp_path)
        transient = VectorFunction("SELECT * FROM no_such_table", "install the function")
        monkeypatch.setattr(engine_module, "profile_for", lambda name: replace(SQLITE, vector_function=transient))
        monkeypatch.setattr(engine_module, "is_retryable", lambda profile, exc: True)
        storage = DatabaseStorage(url=url)
        [refusal] = (await storage.install_extensions()).errors
        assert refusal.kind == ErrorKind.unavailable and "no_such_table" in refusal.message
        assert "install the function" not in refusal.message
        assert storage._host.vector_version is None
        await storage.close()

    async def test_a_probe_that_cost_the_connection_is_classified_and_never_read_as_missing(
        self, tmp_path: Any, monkeypatch
    ) -> None:
        url = _url(tmp_path)
        gone = DBAPIError(SQLITE_VEC_PROBE, None, Exception("connection gone"), connection_invalidated=True)
        _raising_for(monkeypatch, SQLITE_VEC_PROBE, gone)
        storage = DatabaseStorage(url=url)
        [refusal] = (await storage.install_extensions()).errors
        assert refusal.kind == ErrorKind.unavailable and "connection gone" in refusal.message
        assert "enable_load_extension" not in refusal.message
        await storage.close()

    @pytest.mark.parametrize(
        "env_var", [pytest.param("VFS_TEST_POSTGRES_URL", marks=pytest.mark.postgres, id="postgres")]
    )
    async def test_on_postgres_the_install_is_idempotent_and_first_touch_follows(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            installed = await storage.install_extensions()
            assert installed.success is True, installed.errors
            assert storage._host.vector_version is not None and storage._host.vector_version >= (0, 5)
            assert (await storage.first_touch()).success is True


class TestCapabilityGate:
    def test_an_unknown_dialect_serves_the_core_verbs_and_withholds_glean(self, tmp_path: Any, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert "glean" in storage.capabilities()
        monkeypatch.setattr(storage._host, "_profile", replace(GENERIC, name="exotic"))
        capabilities = storage.capabilities()
        assert "glean" not in capabilities
        assert {"read", "write", "delete", "move", "glob", "grep"} <= capabilities
