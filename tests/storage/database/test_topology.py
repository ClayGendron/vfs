"""Topology infrastructure — the plumbing every topology verb rides on.

Four concerns: the execution options a topology connection carries (the
writer marker, and the isolation pin where a dialect declares one), the
advisory-lock key and the mount identity it keys on, the serialization
point each engine takes as the verb's first statement, and the named
seams that let a test stage a rival mid-window.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from ulid import ULID

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MSSQL,
    MYSQL,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    op_execution_options,
    topology_execution_options,
)
from vfs.storage.backends.database.engine import EngineHost, advisory_key
from vfs.storage.backends.database.seams import clear, install, installed, seam
from vfs.storage.backends.database.topology import _serialize

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
