"""Dialect policy and membership chunking.

The generic floor, retryable classification, and the budgets that keep
every statement bounded — no membership predicate, bulk insert, or glob
pattern fan may grow with batch size, on any engine.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.dialects import mysql as mysql_dialect
from sqlalchemy.dialects import oracle as oracle_dialect
from sqlalchemy.dialects import postgresql as postgresql_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from tests.support.database_helpers import _SqliteError, _url
from vfs.models import Entry, Observation
from vfs.models.rows import build_vfs_tables
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results import VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, dialects
from vfs.storage.backends.database.descent import escape_like
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MSSQL,
    MYSQL,
    ORACLE,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    BulkInsertMode,
    ByteBatcher,
    arm_budget,
    bulk_insert,
    byte_chunked,
    is_permanent_defect,
    is_retryable,
    membership_budget,
    op_execution_options,
    profile_for,
    rows_per_statement,
)
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Sequence

    from sqlalchemy.engine import Dialect


# ---------------------------------------------------------------------------
# Dialect policy — generic floor and retryable classification
# ---------------------------------------------------------------------------


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

    def test_syntax_class_sqlstates_are_permanent_defects(self) -> None:
        assert is_permanent_defect(DBAPIError("SELECT", None, Exception("42000", "bad syntax"))) is True
        assert is_permanent_defect(DBAPIError("SELECT", None, _PgError("42601"))) is True

    def test_programming_error_is_a_permanent_defect_without_a_sqlstate(self) -> None:
        assert is_permanent_defect(ProgrammingError("SELECT", None, Exception(1064, "syntax"))) is True

    def test_dynamic_sql_class_sqlstates_are_permanent_defects(self) -> None:
        # 07002 (COUNT field incorrect) is a bind-shape defect: a
        # statement no retry can clear, never an operating condition.
        assert is_permanent_defect(DBAPIError("SELECT", None, Exception("07002", "count field incorrect"))) is True

    def test_sqlite_generic_error_stays_an_operating_condition(self) -> None:
        # SQLITE_ERROR (1) covers missing-schema conditions and
        # statement defects alike — indistinguishable by code, so it
        # never classifies permanent.
        assert is_permanent_defect(DBAPIError("SELECT", None, _SqliteError(1))) is False

    def test_operational_faults_are_not_permanent_defects(self) -> None:
        assert is_permanent_defect(DBAPIError("SELECT 1", None, _SqliteError(5))) is False
        assert is_permanent_defect(DBAPIError("SELECT", None, _PgError("40001"))) is False

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

    def test_the_bracket_class_escape_is_mssql_only(self) -> None:
        # T-SQL LIKE reads [...] as a class; escaping "[" anywhere else
        # is itself an error (ORA-01424 on Oracle), so the escape is a
        # declared profile fact, off on every other engine and the floor.
        assert MSSQL.like_bracket_class is True
        for profile in (SQLITE, POSTGRESQL, MYSQL, ORACLE, GENERIC):
            assert profile.like_bracket_class is False
        assert escape_like("/a[1]b_c%", MSSQL) == "/a\\[1]b\\_c\\%"
        assert escape_like("/a[1]b_c%", ORACLE) == "/a[1]b\\_c\\%"

    def test_content_bytes_is_sqlite_only_until_audited(self) -> None:
        # The cast must return the column's UTF-8 bytes as a cheap
        # reinterpretation — proven only on sqlite; servers await audit.
        assert SQLITE.content_bytes is True
        for profile in (POSTGRESQL, MSSQL, MYSQL, ORACLE, GENERIC):
            assert profile.content_bytes is False

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

    async def test_a_disconnect_classifies_backend_unavailable(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        monkeypatch.setattr(host._dialect, "is_disconnect", lambda *args: True)
        error = host.classify_failure(DBAPIError("SELECT 1", None, _SqliteError(5)), context="stat")
        assert error.kind == VFSErrorKind.backend_unavailable
        assert error.retryable is True
        await storage.close()

    async def test_a_statement_defect_classifies_internal_and_not_retryable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        exc = ProgrammingError("SELECT EXISTS (SELECT 1)", None, Exception("42000", "Incorrect syntax"))
        error = storage._host.classify_failure(exc, context="reindex")
        assert error.kind == VFSErrorKind.internal
        assert error.retryable is False
        await storage.close()


# ---------------------------------------------------------------------------
# Membership chunking — bounded statements at batch scale
# ---------------------------------------------------------------------------


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

    def test_arm_budget_honors_bind_depth_and_ceiling_caps(self) -> None:
        # The measured ceiling binds first on generous budgets: the
        # OR-fan win saturates by ~200 arms and 200 clears every cap.
        assert arm_budget(SQLITE, 100_000, 6) == 200
        assert arm_budget(GENERIC, 100_000, 6) == 166  # 1,000-element IN floor // 6
        # Bind-capped: a squeezed parameter budget wins over the ceiling.
        assert arm_budget(SQLITE, 48, 6) == 2
        # Depth-capped: a depth budget under the reserve still progresses.
        assert arm_budget(replace(SQLITE, expression_depth_budget=70), 100_000, 6) == 6
        # Degenerate budgets never chunk below one arm.
        assert arm_budget(GENERIC, 0, 6) == 1

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
        # pattern fan chunks: 60 composed arms across many statements.
        misses = await storage.stat(observations=[Observation(path=Path(f"/ghost/g{i}.txt")) for i in range(40)])
        assert len(misses.errors) == 40
        assert {e.kind for e in misses.errors} == {VFSErrorKind.not_found}
        scoped = await storage.glob(patterns=tuple(f"{p.parent_dir}/**/*.txt" for p in paths))
        assert len(scoped.observations) == 60
        # Batch ls spans chunk boundaries: 60 anchors at 16 per statement,
        # each parent's single child arriving whole through the merge.
        listing = await storage.ls(observations=[Observation(path=p.parent_dir) for p in paths])
        assert listing.success is True
        assert sorted(str(o.path) for o in listing.observations) == sorted(str(p) for p in paths)
        await storage.close()

    async def test_wide_pattern_fan_survives_the_expression_depth_cap(self, tmp_path) -> None:
        # 1,100 composed pattern arms — past the point where SQLite's
        # default SQLITE_MAX_EXPR_DEPTH kills an unchunked OR fan — so
        # the arms must chunk; dead arms match nothing and the healthy
        # arm's rows still serve.
        storage = DatabaseStorage(url=_url(tmp_path))
        written = await storage.write(entries=[Entry(path=Path("/d/a.txt"), content="x")], parents=True)
        assert written.success is True
        composed = ("/d/**/*", *(f"/ghost{i:04}/**/*" for i in range(1_099)))
        result = await storage.glob(patterns=composed)
        assert result.success is True
        assert [str(o.path) for o in result.observations] == ["/d/a.txt"]
        await storage.close()

    async def test_nested_root_patterns_dedupe_across_chunks(self, tmp_path, monkeypatch) -> None:
        # Budget 48 → tiny arm chunks: /top's composed pattern lands in
        # the first chunk and every nested pattern re-matches its rows in
        # later chunks, so each row must appear exactly once post-merge.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        files = [Path(f"/top/d{i:02}/f.txt") for i in range(20)]
        written = await storage.write(entries=[Entry(path=p, content="x") for p in files], parents=True)
        assert written.success is True, written.errors
        composed = ("/top/**/*", *(f"{p.parent_dir}/**/*" for p in files))
        result = await storage.glob(patterns=composed)
        expected = sorted([*(str(p.parent_dir) for p in files), *(str(p) for p in files)])
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


class TestByteChunked:
    """The byte-bounded batcher's laws — one owner for every batching site."""

    def test_items_emit_exactly_once_in_order(self) -> None:
        items = ["aa", "bbb", "c", "dddd", "ee", "f"]
        batches = list(byte_chunked(items, len, 5))
        assert [item for batch in batches for item in batch] == items

    def test_multi_item_batches_respect_the_budget(self) -> None:
        items = ["aa", "bbb", "c", "dddd", "ee", "f"]
        for batch in byte_chunked(items, len, 5):
            if len(batch) > 1:
                assert sum(len(item) for item in batch) <= 5

    def test_an_oversized_item_rides_alone(self) -> None:
        items = ["aa", "way-over-budget", "bb"]
        batches = list(byte_chunked(items, len, 4))
        assert ["way-over-budget"] in batches
        assert all(sum(len(i) for i in b) <= 4 for b in batches if b != ["way-over-budget"])

    def test_the_flush_is_pre_add_never_post_add(self) -> None:
        # Post-add would pack ["aaa", "bb"] (5 > 4) into one batch before
        # flushing; the pre-add law flushes ["aaa"] and starts fresh.
        assert list(byte_chunked(["aaa", "bb"], len, 4)) == [["aaa"], ["bb"]]

    def test_the_tail_batch_is_emitted(self) -> None:
        assert list(byte_chunked(["aaa", "b"], len, 3)) == [["aaa"], ["b"]]

    def test_empty_items_yield_no_batches(self) -> None:
        assert list(byte_chunked([], len, 4)) == []

    def test_the_incremental_form_agrees_with_the_generator(self) -> None:
        # One flush law, two doors: a streaming producer feeding
        # ByteBatcher sees the same batches byte_chunked yields.
        items = ["aa", "bbb", "c", "dddd", "ee", "f", "gggggg"]
        batcher = ByteBatcher(len, 5)
        streamed = [full for item in items if (full := batcher.add(item)) is not None]
        if (final := batcher.flush()) is not None:
            streamed.append(final)
        assert streamed == list(byte_chunked(items, len, 5))


# ---------------------------------------------------------------------------
# Bulk inserts — one owner, the dialect's mode, the parameter guard
# ---------------------------------------------------------------------------


_ULID_A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
_ULID_B = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
_BLOCK_KEYS = ("epoch", "term", "block_no", "doc_count", "doc_ids", "tfs", "dls")


def _block_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "epoch": 1,
            "term": f"t{i:06d}",
            "block_no": 0,
            "doc_count": 1,
            "doc_ids": b"\x01\x02",
            "tfs": b"\x01",
            "dls": b"\x03",
        }
        for i in range(count)
    ]


def _entry_row(entry_id: str, path: str) -> dict[str, object]:
    stamp = datetime(2026, 8, 26, 12, 0, 0, 123456, tzinfo=UTC)
    return {
        "entry_id": entry_id,
        "parent_id": None,
        "path": path,
        "name": path[1:],
        "kind": "file",
        "version": 1,
        "content_hash": "h",
        "mime_type": "text/plain",
        "chunked": True,
        "created_at": stamp,
        "updated_at": stamp,
        "deleted_at": None,
    }


class TestBulkInsert:
    """Every bulk insert that learns nothing back goes through one owner.

    ``"core"`` is SQLAlchemy's executemany; ``"driver"`` is the driver's
    own executemany on the session's connection, rendered once per
    dialect with Core's bind processors applied per row — so the rows
    that land are the same either way, and the parameter guard pages
    driver calls exactly as Core would have paged one statement.
    """

    @staticmethod
    def _pin_mode(monkeypatch: pytest.MonkeyPatch, mode: BulkInsertMode) -> None:
        pinned = replace(SQLITE, bulk_insert=mode)
        monkeypatch.setattr(dialects, "profile_for", lambda _name: pinned)

    @staticmethod
    def _spy_driver(monkeypatch: pytest.MonkeyPatch) -> list[int]:
        calls: list[int] = []
        original = AsyncConnection.exec_driver_sql

        async def spy(
            self: AsyncConnection,
            statement: str,
            parameters: Sequence[Sequence[Any]] | None = None,
            execution_options: dict[str, object] | None = None,
        ) -> Any:
            calls.append(len(parameters or ()))
            return await original(self, statement, parameters, execution_options)

        monkeypatch.setattr(AsyncConnection, "exec_driver_sql", spy)
        return calls

    @staticmethod
    def _spy_statements(monkeypatch: pytest.MonkeyPatch) -> list[str]:
        statements: list[str] = []
        original = AsyncConnection.exec_driver_sql

        async def spy(
            self: AsyncConnection,
            statement: str,
            parameters: Sequence[Any] | None = None,
            execution_options: dict[str, object] | None = None,
        ) -> Any:
            statements.append(statement)
            return await original(self, statement, parameters, execution_options)

        monkeypatch.setattr(AsyncConnection, "exec_driver_sql", spy)
        return statements

    async def _landed(self, storage: DatabaseStorage, table: str) -> list[tuple[object, ...]]:
        tables = storage._host.tables
        target = tables.lex_postings if table == "lex_postings" else tables.entry
        async with storage._host.session_factory() as session:
            rows = (await session.execute(select(target).order_by(*target.primary_key.columns))).all()
        return [tuple(row) for row in rows]

    @pytest.mark.parametrize("mode", ["core", "driver"])
    async def test_rows_land_identically_under_either_mode(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, mode: BulkInsertMode
    ) -> None:
        # A ULID TypeDecorator, a Boolean, DateTimes and omitted scalar
        # defaults: the driver path must send what Core's processors send.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        tables = storage._host.tables
        async with storage._host.session_factory() as session, session.begin():
            await session.execute(insert(tables.entry), [_entry_row(_ULID_A, "/a")])
        self._pin_mode(monkeypatch, mode)
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, tables.entry, [_entry_row(_ULID_B, "/b")])
        core_row, bulk_row = [row for row in await self._landed(storage, "entry") if row[4] in ("/a", "/b")]
        columns = [c.key for c in tables.entry.columns]
        differing = {k for k, x, y in zip(columns, core_row, bulk_row, strict=True) if x != y}
        assert differing == {"id", "entry_id", "path", "name"}
        await storage.close()

    async def test_core_mode_never_touches_the_driver(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "core")
        calls = self._spy_driver(monkeypatch)
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(5))
        assert calls == []
        assert len(await self._landed(storage, "lex_postings")) == 5
        await storage.close()

    async def test_driver_mode_pages_by_the_parameter_budget(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Declared-value referee: no monkeypatched budget — sqlite's own
        # 32,700 over seven columns is 4,671 rows, so 5,000 rows are two calls.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "driver")
        calls = self._spy_driver(monkeypatch)
        budget = storage._host.parameter_budget
        page = rows_per_statement(budget, [dict.fromkeys(_BLOCK_KEYS)])
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(page + 329))
        assert calls == [page, 329]
        assert len(await self._landed(storage, "lex_postings")) == page + 329
        await storage.close()

    async def test_driver_mode_under_a_squeezed_budget_still_progresses(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spy referee: a budget narrower than one row pages one row per call.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "driver")
        calls = self._spy_driver(monkeypatch)
        dialect = storage._host.engine.dialect
        monkeypatch.setattr(dialect, "insertmanyvalues_max_parameters", 3)
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(3))
        assert calls == [1, 1, 1]
        await storage.close()

    async def test_copy_mode_streams_records_on_the_raw_connection(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No asyncpg here: a stub raw connection records what COPY would
        # receive — rows in column order, paged by the parameter budget.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "copy")
        copies: list[tuple[str, list[str], int, str | None]] = []

        class _Driver:
            async def copy_records_to_table(
                self, name: str, *, records: list[tuple[object, ...]], columns: list[str], schema_name: str | None
            ) -> None:
                copies.append((name, columns, len(records), schema_name))

        class _Raw:
            driver_connection = _Driver()

        async def raw(_self: AsyncConnection) -> _Raw:
            return _Raw()

        monkeypatch.setattr(AsyncConnection, "get_raw_connection", raw)
        statements = self._spy_statements(monkeypatch)
        dialect = storage._host.engine.dialect
        monkeypatch.setattr(dialect, "insertmanyvalues_max_parameters", 14)
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(3))
        # The adapter opens its transaction on a statement, so one precedes the raw COPY.
        assert statements == ["SELECT 1"]
        assert copies == [
            ("vfs_lex_postings", list(_BLOCK_KEYS), 2, None),
            ("vfs_lex_postings", list(_BLOCK_KEYS), 1, None),
        ]
        await storage.close()

    async def test_driver_mode_hands_a_named_dialect_dicts(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # sqlite3 also speaks the named paramstyle, so the live dialect
        # can stand in for oracledb/pyodbc: dicts, not tuples, reach the driver.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "driver")
        dialect = storage._host.engine.dialect
        monkeypatch.setattr(dialect, "positional", False)
        monkeypatch.setattr(dialect, "paramstyle", "named")
        handed: list[object] = []
        original = AsyncConnection.exec_driver_sql

        async def spy(
            self: AsyncConnection,
            statement: str,
            parameters: Sequence[Any] | None = None,
            execution_options: dict[str, object] | None = None,
        ) -> Any:
            handed.extend(parameters or ())
            return await original(self, statement, parameters, execution_options)

        monkeypatch.setattr(AsyncConnection, "exec_driver_sql", spy)
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(2))
        assert all(isinstance(row, dict) and set(row) == set(_BLOCK_KEYS) for row in handed)
        assert len(await self._landed(storage, "lex_postings")) == 2
        await storage.close()

    @pytest.mark.parametrize(
        ("sqlstate", "expected", "retryable"),
        [("23505", IntegrityError, False), ("40001", DBAPIError, True), (None, DBAPIError, False)],
    )
    async def test_copy_mode_restores_the_classes_callers_catch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        sqlstate: str | None,
        expected: type[DBAPIError],
        retryable: bool,
    ) -> None:
        # A raw driver call bypasses SQLAlchemy's wrapping: an integrity
        # class lands as IntegrityError (the savepoint re-drive's key), the
        # rest as DBAPIError carrying the origin the retry ladder classifies.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "copy")

        class _DriverError(Exception):
            def __init__(self) -> None:
                super().__init__("copy failed")
                self.sqlstate = sqlstate

        class _Driver:
            async def copy_records_to_table(self, name: str, **_kwargs: object) -> None:
                raise _DriverError

        class _Raw:
            driver_connection = _Driver()

        async def raw(_self: AsyncConnection) -> _Raw:
            return _Raw()

        monkeypatch.setattr(AsyncConnection, "get_raw_connection", raw)
        async with storage._host.session_factory() as session, session.begin():
            with pytest.raises(expected) as caught:
                await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(1))
        assert type(caught.value) is expected
        assert isinstance(caught.value.orig, _DriverError)
        assert is_retryable(POSTGRESQL, caught.value) is retryable
        await storage.close()

    async def test_empty_rows_is_a_noop(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "driver")
        calls = self._spy_driver(monkeypatch)
        async with storage._host.session_factory() as session, session.begin():
            await bulk_insert(session, storage._host.tables.lex_postings, [])
        assert calls == []
        await storage.close()

    async def test_mixed_key_sets_are_refused(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "driver")
        rows = _block_rows(2)
        del rows[1]["dls"]
        async with storage._host.session_factory() as session, session.begin():
            with pytest.raises(TypeError, match="one key set"):
                await bulk_insert(session, storage._host.tables.lex_postings, rows)
        await storage.close()

    async def test_callable_defaults_are_refused(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/warm"))
        self._pin_mode(monkeypatch, "driver")
        table = Table(
            "t_callable",
            MetaData(),
            Column("k", Integer, primary_key=True),
            Column("stamp", Integer, default=lambda: 1),
        )
        async with storage._host.session_factory() as session, session.begin():
            with pytest.raises(TypeError, match="scalar Python-side default"):
                await bulk_insert(session, table, [{"k": 1}])
        await storage.close()

    def test_no_bulk_table_declares_a_callable_default(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        callables = [
            f"{table.name}.{column.key}"
            for table in tables.metadata.tables.values()
            for column in table.columns
            if column.default is not None and not column.default.is_scalar
        ]
        assert callables == []

    @pytest.mark.parametrize(
        ("make", "expected_sql", "positional"),
        [
            (lambda: sqlite_dialect.dialect(paramstyle="qmark"), "VALUES (?, ?, ?)", ("epoch", "term", "block_no")),
            (
                lambda: postgresql_dialect.dialect(paramstyle="numeric_dollar"),
                "VALUES ($1, $2, $3)",
                ("epoch", "term", "block_no"),
            ),
            (lambda: mysql_dialect.dialect(paramstyle="format"), "VALUES (%s, %s, %s)", ("epoch", "term", "block_no")),
            (lambda: oracle_dialect.dialect(paramstyle="named"), "VALUES (:epoch, :term, :block_no)", None),
        ],
    )
    def test_rendering_follows_the_dialects_paramstyle(
        self, make: Callable[[], Dialect], expected_sql: str, positional: tuple[str, ...] | None
    ) -> None:
        table = Table(
            "t_render",
            MetaData(),
            Column("epoch", Integer, primary_key=True),
            Column("term", String(8)),
            Column("block_no", Integer),
        )
        statement = dialects._bulk_statement(make(), table, ("epoch", "term", "block_no"))
        assert statement.sql.endswith(expected_sql)
        assert statement.positional == positional

    def test_profiles_pin_the_measured_mode(self) -> None:
        # Read from the before/after benchmark on each engine; GENERIC never
        # assumes an unknown driver's executemany is a batch.
        assert GENERIC.bulk_insert == "core"
        assert {p.name: p.bulk_insert for p in (SQLITE, POSTGRESQL, MYSQL, MSSQL, ORACLE)} == {
            "sqlite": "driver",
            "postgresql": "copy",
            "mysql": "driver",
            "mssql": "core",
            "oracle": "core",
        }
