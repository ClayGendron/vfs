"""sqlite-vec on every SQLite connection, the first-touch probe, and the capability gate
that withholds ranked search from a dialect with no distance function."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text

from tests.support.database_helpers import _url
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import GENERIC
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
        monkeypatch.setattr(engine_module, "_EXTENSIONS_LOADABLE", False)
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.first_touch()
        assert result.success is False
        [refusal] = result.errors
        assert refusal.kind == VFSErrorKind.unavailable and "enable_load_extension" in refusal.message
        assert (await storage.stat(path=Path("/"))).success is False  # the latch never set
        await storage.close()

    def test_the_loader_ignores_a_connection_it_does_not_recognise(self) -> None:
        engine_module._load_sqlite_vec(object())  # no aiosqlite inner connection: nothing to load


class TestPgvectorVersion:
    async def test_the_version_parses_and_absence_is_none(self) -> None:
        class Conn:
            def __init__(self, raw: str | None) -> None:
                self.raw = raw

            async def execute(self, statement: Any) -> Any:
                assert str(statement) == engine_module.PGVECTOR_VERSION_PROBE
                raw = self.raw
                return SimpleNamespace(scalar_one_or_none=lambda: raw)

        assert await engine_module._pgvector_version(Conn("0.8.1")) == (0, 8, 1)  # ty: ignore[invalid-argument-type]
        assert await engine_module._pgvector_version(Conn(None)) is None  # ty: ignore[invalid-argument-type]


class TestCapabilityGate:
    def test_an_unknown_dialect_serves_the_core_verbs_and_withholds_glean(self, tmp_path: Any, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert "glean" in storage.capabilities()
        monkeypatch.setattr(storage._host, "_profile", replace(GENERIC, name="exotic"))
        capabilities = storage.capabilities()
        assert "glean" not in capabilities
        assert {"read", "write", "delete", "move", "glob", "grep"} <= capabilities
