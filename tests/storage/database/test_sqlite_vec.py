"""sqlite-vec on every SQLite connection, the first-touch probe, and the capability gate
that withholds ranked search from a dialect with no distance function."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import text

from tests.support.database_helpers import _url
from tests.support.server_schemas import server_storage
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import GENERIC, SQLITE, is_insufficient_privilege
from vfs.storage.backends.memory import InMemoryStorage


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
        absent = replace(SQLITE, vector_probe="SELECT NULL WHERE 1 = 0", vector_missing="install the function")
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
        declared = replace(SQLITE, vector_install="CREATE EXTENSION IF NOT EXISTS vector")
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        storage = DatabaseStorage(url=url)
        result = await storage.install_extensions()
        assert result.success is False
        [refusal] = result.errors
        assert refusal.kind is not ErrorKind.permission_denied
        await storage.close()

    async def test_a_role_that_may_not_install_is_permission_denied_naming_the_fix(
        self, tmp_path: Any, monkeypatch
    ) -> None:
        url = _url(tmp_path)
        declared = replace(SQLITE, vector_install="CREATE EXTENSION IF NOT EXISTS vector", vector_missing="ask a DBA")
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        monkeypatch.setattr(engine_module, "is_insufficient_privilege", lambda exc: True)
        storage = DatabaseStorage(url=url)
        result = await storage.install_extensions()
        [refusal] = result.errors
        assert refusal.kind == ErrorKind.permission_denied and "ask a DBA" in refusal.message
        await storage.close()

    async def test_a_rival_installing_first_is_benign(self, tmp_path: Any, monkeypatch) -> None:
        # The IF NOT EXISTS race: the install statement's unique violation is swallowed and the probe decides.
        url = _url(tmp_path)
        declared = replace(SQLITE, vector_install="INSERT INTO vfs_meta (id) VALUES (1)")
        monkeypatch.setattr(engine_module, "profile_for", lambda name: declared)
        storage = DatabaseStorage(url=url)
        result = await storage.install_extensions()
        assert result.success is True, result.errors
        await storage.close()

    async def test_a_dialect_with_nothing_declared_succeeds_without_probing(self, tmp_path: Any, monkeypatch) -> None:
        url = _url(tmp_path)
        declared = replace(SQLITE, vector_probe=None, vector_install=None)
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
