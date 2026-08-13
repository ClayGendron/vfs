"""Dialect policy and membership chunking.

The generic floor, retryable classification, and the budgets that keep
every statement bounded — no membership predicate, bulk insert, or glob
pattern fan may grow with batch size, on any engine.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, ClassVar, cast

from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.database_helpers import _SqliteError, _url
from vfs.models import Entry, Observation
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results import VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.descent import escape_like
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MSSQL,
    MYSQL,
    ORACLE,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    arm_budget,
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
    from sqlalchemy.ext.asyncio import AsyncConnection


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
