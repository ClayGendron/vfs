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
from sqlalchemy import event, select
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.engine.default import DefaultDialect

from tests.support.commit_worlds import (
    ANONYMOUS,
    EVE,
    SYSTEM,
    attempts,
    clearing,
    copy_world,
    dest_world,
    drop_world,
    land,
    paths_under,
    row_at,
    stamp,
)
from tests.support.database_helpers import _url
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind
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
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.protocol import ResolvedPair
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.results import Result
    from vfs.storage.grants import Posture


ANN = Authority.of(Principal("ann"))


# ---------------------------------------------------------------------------
# Copy — the rows a copy mints
# ---------------------------------------------------------------------------


class TestCopy:
    """A copied row starts life like a created one: a directory has nothing awaiting the index, a file does."""

    async def test_a_copied_directory_is_encoded_and_a_copied_file_is_not(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        written = await storage.write(entries=[Entry(path=Path("/src/f.txt"), content="needle body")], parents=True)
        assert written.success is True
        assert (await storage.rebuild()).success is True
        copied = await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/dst"))])
        assert copied.success is True
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            rows = await conn.execute(select(entry.c.path, entry.c.encoded).where(entry.c.path.like("/dst%")))
            flags = {row.path: row.encoded for row in rows}
        assert flags == {"/dst": True, "/dst/f.txt": False}
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


# ---------------------------------------------------------------------------
# Rights at the rows a transfer collects and the paths it creates
# ---------------------------------------------------------------------------


# A direct write of the path a transfer into ``/dst/c`` would mint beneath ``/dst/c/sub``.
_DIRECT = [Entry(path=Path("/dst/c/sub/f.txt"), content="x")]

# The grown call: the second pair carries what the first pair copied under its source.
_GROWN = [
    ResolvedPair(src=Path("/src"), dest=Path("/tmp/x/in")),
    ResolvedPair(src=Path("/tmp/x"), dest=Path("/dst/c")),
]


def _pair(src: str, dest: str) -> list[ResolvedPair]:
    return [ResolvedPair(src=Path(src), dest=Path(dest))]


async def _postures(storage: DatabaseStorage, rows: list[tuple[str, Posture]]) -> None:
    for path, level in rows:
        assert (await storage.posture(path=Path(path), posture=level, authority=SYSTEM)).success is True


async def _transfer(storage: DatabaseStorage, verb: str, pairs: list[ResolvedPair], who: Authority) -> Result:
    if verb == "move":
        return await storage.move(operations=pairs, authority=who)
    return await storage.copy(operations=pairs, authority=who)


class TestCollectedRowsAreJudged:
    """A row landed beneath a transfer's source after its gate is judged where the transfer collects it."""

    @pytest.mark.parametrize("landed", ["/drop/e/late.txt", "/drop/e/sub/late.txt"], ids=["depth1", "depth2"])
    async def test_a_move_redrives_over_a_landed_row_beyond_the_callers_rung(self, monkeypatch, landed) -> None:
        """Alice's row landed under eve's tree is never moved with it: the move runs again without it.

        Guards the ``admit`` call in ``_rewrite_descendants``: deleted, the
        rewrite carries alice's row under ``/drop/f``. The depth-one node is a
        backstop, since a real rival bumps the root and trips its claim.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        sessions = attempts(monkeypatch, storage)
        tables = storage._host.tables
        act = clearing("transfer:post-collect", lambda: land(sessions[-1], tables, landed, "alice", "add"))
        with installed("transfer:post-collect", act):
            result = await storage.move(operations=_pair("/drop/e", "/drop/f"), authority=EVE)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        assert await paths_under(storage, "/drop/f") == {"/drop/f", "/drop/f/f.txt", "/drop/f/sub", "/drop/f/sub/g.txt"}
        moved = "/drop/f" + landed.removeprefix("/drop/e")
        assert await row_at(storage, landed) is None and await row_at(storage, moved) is None

    async def test_a_copy_redrives_over_a_landed_row_the_caller_may_not_read(self, monkeypatch) -> None:
        """A row eve may not read, landed under the source after the gate, is never copied into her tree.

        Guards the copy's ``admit`` call in ``transfer_rows``: deleted, eve owns a copy of alice's secret.
        """
        storage = InMemoryStorage()
        await copy_world(storage)
        sessions = attempts(monkeypatch, storage)
        secret, tables = "/s/priv/secret.txt", storage._host.tables
        act = clearing("transfer:post-snapshot", lambda: land(sessions[-1], tables, secret, "alice", "none"))
        with installed("transfer:post-snapshot", act):
            result = await storage.copy(operations=_pair("/s", "/t/s"), authority=EVE)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        assert await paths_under(storage, "/t/s") == {"/t/s", "/t/s/a.txt", "/t/s/priv"}

    @pytest.mark.parametrize("verb", ["move", "copy"])
    async def test_a_landed_row_the_caller_may_act_on_rides_in_one_attempt(self, monkeypatch, verb: str) -> None:
        """The judgment refuses nothing the caller may do: a landed row eve may move or read rides with the tree."""
        storage = InMemoryStorage()
        tables = storage._host.tables
        await (drop_world if verb == "move" else copy_world)(storage)
        sessions = attempts(monkeypatch, storage)
        if verb == "move":
            seam_name, landed, owner, level = "transfer:post-collect", "/drop/e/sub/late.txt", "eve", "add"
            pair = _pair("/drop/e", "/drop/f")
        else:
            seam_name, landed, owner, level = "transfer:post-snapshot", "/s/b.txt", "alice", "read"
            pair = _pair("/s", "/t/s")
        with installed(seam_name, clearing(seam_name, lambda: land(sessions[-1], tables, landed, owner, level))):
            result = await _transfer(storage, verb, pair, EVE)
        assert result.success is True, result.errors
        assert len(sessions) == 1
        arrived = await row_at(storage, "/drop/f/sub/late.txt" if verb == "move" else "/t/s/b.txt")
        assert arrived is not None and arrived["owner_id"] == "eve"


class TestDestinationsAreJudged:
    """A transfer may create beneath its destination only what a direct write of each path there could."""

    @pytest.mark.parametrize(
        ("backend", "verb", "anonymous"),
        [
            ("memory", "copy", False),
            ("memory", "move", False),
            ("sqlite", "copy", False),
            ("sqlite", "move", False),
            ("memory", "copy", True),
        ],
        ids=["memory-copy", "memory-move", "sqlite-copy", "sqlite-move", "memory-anonymous-copy"],
    )
    async def test_a_transfer_is_refused_where_a_direct_write_is(self, tmp_path, backend, verb, anonymous) -> None:
        """A copy or move into ``/dst/c`` is refused at ``/dst/c/sub``, where eve's direct write of a path beneath is.

        Guards the ``admit_destinations`` call in ``_execute_transfer``'s
        gate: deleted, the transfer mints ``/dst/c/sub`` in a region the
        posture closes to this caller, with no race at all.
        """
        storage = InMemoryStorage() if backend == "memory" else DatabaseStorage(url=_url(tmp_path))
        who = ANONYMOUS if anonymous else EVE
        kind = ErrorKind.unauthenticated if anonymous else ErrorKind.permission_denied
        try:
            await dest_world(storage)
            direct = await storage.write(entries=_DIRECT, parents=True, authority=who)
            assert [error.kind for error in direct.errors] == [kind]
            if not anonymous:
                assert direct.errors[0].path == "/dst/c/sub"
            before = await paths_under(storage, "/src")
            result = await _transfer(storage, verb, _pair("/src", "/dst/c"), who)
            assert result.success is False
            assert [(error.kind, error.path) for error in result.errors] == [(kind, "/dst/c/sub")]
            assert await paths_under(storage, "/dst") == {"/dst"}
            assert await paths_under(storage, "/src") == before
        finally:
            await storage.close()

    @pytest.mark.parametrize("verb", ["copy", "move"])
    @pytest.mark.parametrize("opening", ["open", "granted"])
    async def test_a_transfer_succeeds_where_a_direct_write_does(self, verb: str, opening: str) -> None:
        """Where a direct write of ``/dst/c/sub/f.txt`` succeeds, the transfer creates it.

        The granted nodes guard the caller's spans in the closed region:
        with the ``subtract`` dropped, eve's own grant at ``/dst/c/sub`` is
        ignored and the transfer refused where her direct write is not.
        """
        stores = [InMemoryStorage(), InMemoryStorage()]
        for storage in stores:
            await dest_world(storage)
            if opening == "open":
                assert (await storage.posture(path=Path("/dst/c/sub"), posture="add", authority=SYSTEM)).success
            else:
                granted = await storage.grant(path=Path("/dst/c/sub"), principal="eve", level="add", authority=SYSTEM)
                assert granted.success is True
        direct, transferred = stores
        written = await direct.write(entries=_DIRECT, parents=True, authority=EVE)
        assert written.success is True, written.errors
        result = await _transfer(transferred, verb, _pair("/src", "/dst/c"), EVE)
        assert result.success is True, result.errors
        assert await row_at(transferred, "/dst/c/sub/f.txt") is not None

    @pytest.mark.parametrize("verb", ["copy", "move"])
    async def test_a_source_row_landed_after_the_gate_that_maps_into_a_closed_region_redrives(
        self, monkeypatch, verb: str
    ) -> None:
        """A source row landed after the gate whose mapped path a direct write could not create redrives the call.

        Guards the ``admit_created`` calls in ``transfer_rows`` and
        ``_rewrite_descendants``: deleted, the transfer mints ``/dst/c/closed``.
        """
        storage = InMemoryStorage()
        await dest_world(storage)
        assert (await storage.posture(path=Path("/dst/c/sub"), posture="add", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/dst/c/closed"), posture="none", authority=SYSTEM)).success is True
        sessions = attempts(monkeypatch, storage)
        seam_name = "transfer:post-snapshot" if verb == "copy" else "transfer:post-collect"
        act = clearing(seam_name, lambda: land(sessions[-1], storage._host.tables, "/src/closed", "eve", "read_write"))
        with installed(seam_name, act):
            result = await _transfer(storage, verb, _pair("/src", "/dst/c"), EVE)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        assert await row_at(storage, "/dst/c/closed") is None

    async def _grown_world(self, *, sub: Posture) -> InMemoryStorage:
        storage = InMemoryStorage()
        await dest_world(storage)
        assert (await storage.write(entries=[Entry(path=Path("/tmp/x"), kind="directory")], parents=True)).success
        assert (await storage.posture(path=Path("/tmp"), posture="add", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/dst/c/in/sub"), posture=sub, authority=SYSTEM)).success is True
        return storage

    async def test_a_pair_whose_source_an_earlier_pair_grew_is_refused_in_place(self, monkeypatch) -> None:
        """A later pair carrying rows an earlier pair of the same call made into a closed region is refused once.

        Guards the own-work test in ``admit_created``: dropped, the call
        redrives into a retryable ``conflict`` that no later state can clear.
        """
        storage = await self._grown_world(sub="none")
        sessions = attempts(monkeypatch, storage)
        result = await storage.copy(operations=_GROWN, authority=EVE)
        assert result.success is False
        assert len(sessions) == 1
        assert [(error.kind, error.path, error.retryable) for error in result.errors] == [
            (ErrorKind.permission_denied, "/dst/c/in/sub", False)
        ]
        assert await paths_under(storage, "/dst/c") == set()
        assert await paths_under(storage, "/tmp/x/in") == set()

    async def test_a_move_pair_whose_source_an_earlier_pair_grew_is_refused_in_place(self, monkeypatch) -> None:
        """The grown call as two moves: the rows the first pair moved are the call's own, refused once in place.

        Guards the own-work set a move keeps: its root and the descendants
        it rewrote. Without them the second pair redrives into a conflict.
        """
        storage = await self._grown_world(sub="none")
        assert (await storage.posture(path=Path("/tmp"), posture="read_write", authority=SYSTEM)).success is True
        sessions = attempts(monkeypatch, storage)
        result = await storage.move(operations=_GROWN, authority=EVE)
        assert len(sessions) == 1
        assert [(error.kind, error.path, error.retryable) for error in result.errors] == [
            (ErrorKind.permission_denied, "/dst/c/in/sub", False)
        ]
        assert await paths_under(storage, "/dst/c") == set()
        assert await row_at(storage, "/src/sub/f.txt") is not None

    async def test_a_moved_root_a_later_pair_carries_into_a_closed_region_is_refused_in_place(
        self, monkeypatch
    ) -> None:
        """The root an earlier move pair moved is the call's own work too: refused once, at its mapped path.

        Guards the moved root's id in the own-work set: left out, the second
        pair redrives into a retryable conflict that no later state can clear.
        """
        storage = await self._grown_world(sub="add")
        await _postures(storage, [("/tmp", "read_write"), ("/dst/c/in", "none")])
        sessions = attempts(monkeypatch, storage)
        result = await storage.move(operations=_GROWN, authority=EVE)
        assert len(sessions) == 1
        assert [(error.kind, error.path, error.retryable) for error in result.errors] == [
            (ErrorKind.permission_denied, "/dst/c/in", False)
        ]

    @pytest.mark.parametrize("verb", ["copy", "move"])
    async def test_a_closed_region_holding_only_a_deleted_source_row(self, monkeypatch, verb: str) -> None:
        """A copy leaves a deleted row where it is and succeeds; a move carries it and is refused at the gate.

        Guards the probe's tombstone term per verb: flipped for copy, a row it
        does not copy refuses it; flipped for move, the gate passes and the
        rewrite redrives into a retryable conflict.
        """
        storage = InMemoryStorage()
        await dest_world(storage)
        assert (await storage.write(entries=[Entry(path=Path("/src/ok.txt"), content="o")])).success is True
        assert (await storage.delete(path=Path("/src/sub"), authority=SYSTEM)).success is True
        sessions = attempts(monkeypatch, storage)
        result = await _transfer(storage, verb, _pair("/src", "/dst/c"), EVE)
        assert len(sessions) == 1
        if verb == "copy":
            assert result.success is True, result.errors
            assert await paths_under(storage, "/dst/c") == {"/dst/c", "/dst/c/ok.txt"}
        else:
            refused = [(error.kind, error.path) for error in result.errors]
            assert refused == [(ErrorKind.permission_denied, "/dst/c/sub")]

    async def test_the_same_grown_call_succeeds_where_the_region_is_open(self, monkeypatch) -> None:
        """The grown call's control: with the region open, the same two pairs succeed in one attempt."""
        storage = await self._grown_world(sub="add")
        sessions = attempts(monkeypatch, storage)
        result = await storage.copy(operations=_GROWN, authority=EVE)
        assert result.success is True, result.errors
        assert len(sessions) == 1
        assert await row_at(storage, "/dst/c/in/sub/f.txt") is not None

    async def test_a_moved_basis_redrives_an_in_place_refusal(self, monkeypatch) -> None:
        """An in-place refusal first proves the caller's rights still stand: a moved basis redrives it.

        Guards the ``hold_rights`` before the in-place refusal: without it
        the stamp staged at the second pair is never read, and the call ends in one attempt.
        """
        storage = await self._grown_world(sub="none")
        sessions = attempts(monkeypatch, storage)
        fired: list[int] = []

        async def second_pair_of_the_first_attempt() -> None:
            fired.append(len(sessions))
            if fired == [1, 1]:
                await stamp(sessions[-1], storage._host.tables, "eve")

        with installed("transfer:post-collect", second_pair_of_the_first_attempt):
            result = await storage.copy(operations=_GROWN, authority=EVE)
        assert len(sessions) == 2
        assert [(error.kind, error.path) for error in result.errors] == [(ErrorKind.permission_denied, "/dst/c/in/sub")]
