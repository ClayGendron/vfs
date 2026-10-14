"""Topology infrastructure — the plumbing every topology verb rides on.

Four concerns: the execution options a topology connection carries (the
writer marker, and the isolation pin where a dialect declares one), the
advisory-lock key and the mount identity it keys on, the serialization
point each engine takes as the verb's first statement, and the named
seams that let a test stage a rival mid-window.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.engine.default import DefaultDialect

from tests.support.database_helpers import _url
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MARIADB,
    MSSQL,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    op_execution_options,
    topology_execution_options,
)
from vfs.storage.backends.database.engine import EngineHost, advisory_key
from vfs.storage.backends.database.seams import clear, install, installed, seam
from vfs.storage.backends.database.serialized import serialize
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


ANN = Authority.of(Principal("ann"))


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
        for profile in (POSTGRESQL, MARIADB, PROFILES["mariadb"]):
            options = topology_execution_options(profile)
            assert options == {"vfs_writer": True, "isolation_level": "READ COMMITTED"}

    def test_topology_pin_never_borrows_the_op_pin(self) -> None:
        # MySQL ops run REPEATABLE READ; its topology pin must differ.
        assert op_execution_options(MARIADB, writer=True)["isolation_level"] == "REPEATABLE READ"
        assert topology_execution_options(MARIADB)["isolation_level"] == "READ COMMITTED"


class TestAdvisoryKey:
    """First touch's provisioning lock keys on the table name, per schema."""

    def test_advisory_key_is_stable_and_signed_64(self) -> None:
        key = advisory_key("vfs")
        assert key == advisory_key("vfs")
        assert -(2**63) <= key < 2**63
        assert key != advisory_key("other")

    def test_the_table_key_differs_per_schema(self) -> None:
        tenant = EngineHost(url="sqlite+aiosqlite:///:memory:", schema="tenant")
        other = EngineHost(url="sqlite+aiosqlite:///:memory:", schema="other")
        assert tenant._table_key == advisory_key("tenant.vfs_entries")
        assert tenant._table_key != other._table_key


class _StatementCapture:
    """Session double capturing executed statement objects; the test compiles each against a dialect."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, stmt: Any, params: Any = None) -> SimpleNamespace:
        self.statements.append(stmt)
        return SimpleNamespace(scalar_one=lambda: 0)


_SPELLINGS = [
    pytest.param(SQLITE, sqlite.dialect(), None, id="sqlite"),
    pytest.param(POSTGRESQL, postgresql.dialect(), "FOR UPDATE", id="postgresql"),
    pytest.param(MARIADB, mysql.dialect(), "FOR UPDATE", id="mariadb"),
    pytest.param(MSSQL, mssql.dialect(), "WITH (UPDLOCK, FORCESEEK)", id="mssql"),
    pytest.param(PROFILES["oracle"], oracle.dialect(), "FOR UPDATE", id="oracle"),
    pytest.param(GENERIC, DefaultDialect(), "FOR UPDATE", id="generic"),
]


class TestSerializationPoint:
    """The point is one locking read of the lock row on every engine, and nothing else reads that row."""

    @pytest.mark.parametrize(("profile", "dialect", "spelling"), _SPELLINGS)
    async def test_one_locking_read_of_the_lock_row(self, profile, dialect, spelling) -> None:
        capture = _StatementCapture()
        await serialize(cast("AsyncSession", capture), profile, build_vfs_tables().lock)
        [stmt] = capture.statements
        sql = str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        assert sql.lstrip().startswith("SELECT") and "vfs_lock" in sql and "vfs_meta" not in sql
        if spelling is None:
            assert "FOR UPDATE" not in sql  # the writer transaction is the lock
        else:
            assert spelling in sql, sql

    async def test_no_hot_path_statement_touches_the_lock_row(self, tmp_path) -> None:
        # The tables an overwrite, an edit, an attributed write and a grep
        # touch never include the one the serialized verbs lock, so no such
        # call can wait behind a delete, restore, sweep, move or copy.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])).success is True
        seen: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            seen.append(statement)

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="two")])).success is True
            edits = [EditOperation(old="two", new="three")]
            assert (await storage.edit(path=Path("/a.txt"), edits=edits)).success is True
            assert (await storage.write(entries=[Entry(path=Path("/b.txt"), content="b")], authority=ANN)).success
            assert (await storage.grep(pattern="three")).success is True
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        touched = {name for statement in seen for name in re.findall(r"\bvfs_\w+", statement)}
        assert "vfs_meta" in touched  # the revision and epoch reads are real reads of the meta row
        assert "vfs_lock" not in touched
        await storage.close()


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
