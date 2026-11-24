"""Dialect policy and membership chunking.

The generic floor, retryable classification, and the budgets that keep
every statement bounded — no membership predicate, bulk insert, or glob
pattern fan may grow with batch size, on any engine.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, event, insert, select
from sqlalchemy.dialects import postgresql as postgresql_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from tests.support.database_helpers import _SqliteError, _url, begin_as_writer
from tests.support.statements import is_statistics_statement
from vfs.models import Edge, Entry, Observation
from vfs.models.rows import build_vfs_tables
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results import ErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, dialects
from vfs.storage.backends.database.dialects import (
    GENERIC,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    BulkInsertMode,
    DialectProfile,
    ShareLock,
    arm_budget,
    bulk_insert,
    is_permanent_defect,
    is_retryable,
    is_unique_violation,
    is_value_too_large,
    lock_rows,
    membership_budget,
    op_execution_options,
    profile_for,
    rows_per_statement,
    upsert_constructor,
)
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.labels import hold_postures, open_relabel, watch_postures
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


class TestDialectPolicy:
    def test_unknown_dialect_serves_on_the_generic_floor(self) -> None:
        profile = profile_for("duckdb")
        assert profile.name == "duckdb"
        assert profile.key_byte_budget == GENERIC.key_byte_budget
        assert profile.arbitration == "catch_retry"

    def test_the_tuned_profiles_are_sqlite_and_postgres_alone(self) -> None:
        assert set(PROFILES) == {"sqlite", "postgresql"}

    @pytest.mark.parametrize("name", ["mysql", "mariadb", "mssql", "oracle"])
    def test_a_dropped_engine_is_served_by_the_floor_under_its_own_name(self, name: str) -> None:
        assert profile_for(name) == replace(GENERIC, name=name)

    def test_the_floor_keeps_the_sqlstate_arm_and_reads_no_driver_number(self) -> None:
        """Guards the floor's SQLSTATE arm: ``args[0]`` classifies, and a bare class 23 is no unique violation."""
        assert is_retryable(GENERIC, Exception("40001", "deadlock victim")) is True
        assert is_unique_violation(Exception("23000", "Violation of UNIQUE KEY constraint (2627)")) is False
        assert is_unique_violation(Exception(1062, "Duplicate entry")) is False

    def test_sqlite_busy_is_retryable_but_busy_snapshot_is_not(self) -> None:
        assert is_retryable(SQLITE, _SqliteError(5)) is True
        assert is_retryable(SQLITE, _SqliteError(517)) is False

    def test_only_sqlite_declares_a_statistics_listing(self) -> None:
        """Guards: a statistics listing on a server engine, which maintains its own statistics."""
        assert SQLITE.statistics_listing is not None
        assert "PRAGMA" in SQLITE.statistics_listing and "optimize" in SQLITE.statistics_listing
        assert [p.statistics_listing for p in (POSTGRESQL, GENERIC)] == [None] * 2

    def test_only_sqlite_declares_a_rarity_hint(self) -> None:
        """Guards: a planner hint sent to an engine that has no such function, or SQLite losing the overlay seek."""
        assert SQLITE.rarity_hint == "unlikely"
        assert [p.rarity_hint for p in (POSTGRESQL, GENERIC)] == [None] * 2

    def test_the_entry_probe_is_declared_on_sqlite_only(self) -> None:
        """Guards: SQLite's chunk pages joining the entry table, a Bloom filter rebuilt on every page, or an
        engine whose planner serves the join, Postgres JIT-compiling the probe, sent the probe unmeasured."""
        assert SQLITE.probe_entry_filter is True
        assert [p.probe_entry_filter for p in (POSTGRESQL, GENERIC)] == [False] * 2

    def test_the_stored_length_is_the_function_that_reads_no_body(self) -> None:
        """Guards: Postgres sizing a stored rendering with ``length``, which detoasts it, where ``octet_length``
        reads none."""
        assert POSTGRESQL.stored_length == "octet_length"
        assert [p.stored_length for p in (SQLITE, GENERIC)] == ["length"] * 2

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

    def test_the_range_join_keyword_and_hints_are_the_measured_ones(self) -> None:
        # Each planner misreads the everyone-level term its own way; the profile carries the keyword it needs.
        assert SQLITE.range_join == "CROSS JOIN"
        assert POSTGRESQL.range_join == "JOIN" and POSTGRESQL.range_settings == ("SET LOCAL jit = off",)
        assert GENERIC.range_source is None and GENERIC.range_join == "JOIN"
        assert all(p.range_settings == () for p in (SQLITE, GENERIC))
        assert SQLITE.range_fence == "MATERIALIZED"
        assert all(p.range_fence is None for p in (POSTGRESQL, GENERIC))

    def test_the_relabel_row_cap_is_the_measured_fifty_thousand_on_every_profile(self) -> None:
        # The chunk size one relabel transaction writes: SQLAlchemy models
        # no such cap, and 50,000 was safe on every engine measured.
        for profile in (SQLITE, POSTGRESQL, GENERIC):
            assert profile.relabel_rows == 50_000, profile.name

    def test_every_tuned_profile_declares_a_distance_function(self) -> None:
        for profile in PROFILES.values():
            assert profile.vector_distance in ("exact", "ann"), profile.name
        assert GENERIC.vector_distance == "none" and SQLITE.vector_distance == "exact"

    def test_every_lawful_path_fits_every_declared_key_budget(self) -> None:
        # The contract is byte-denominated, so the worst-case index key is
        # MAX_PATH_LENGTH bytes — the budget↔DDL gap closes by construction.
        for profile in (*PROFILES.values(), GENERIC):
            assert profile.key_byte_budget >= MAX_PATH_LENGTH

    def test_content_bytes_is_sqlite_only_until_audited(self) -> None:
        # The cast must return the column's UTF-8 bytes as a cheap
        # reinterpretation — proven only on sqlite; servers await audit.
        assert SQLITE.content_bytes is True
        for profile in (POSTGRESQL, GENERIC):
            assert profile.content_bytes is False

    def test_values_join_is_declared_only_where_proven(self) -> None:
        # SQLite rejects the column-aliased VALUES join despite declaring
        # update_returning — the bit is earned per engine, floor stays off.
        assert POSTGRESQL.values_join
        assert not SQLITE.values_join and not GENERIC.values_join

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
        write = await storage.write(entries=[Entry(path=Path("/g.txt"), content="y")])
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
        assert error.kind == ErrorKind.unavailable
        assert error.retryable is True
        await storage.close()

    async def test_a_disconnect_classifies_backend_unavailable(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        monkeypatch.setattr(host._dialect, "is_disconnect", lambda *args: True)
        error = host.classify_failure(DBAPIError("SELECT 1", None, _SqliteError(5)), context="stat")
        assert error.kind == ErrorKind.backend_unavailable
        assert error.retryable is True
        await storage.close()

    async def test_a_statement_defect_classifies_internal_and_not_retryable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        exc = ProgrammingError("SELECT EXISTS (SELECT 1)", None, Exception("42000", "Incorrect syntax"))
        error = storage._host.classify_failure(exc, context="rebuild")
        assert error.kind == ErrorKind.internal
        assert error.retryable is False
        await storage.close()


def _sqlite_integrity_errors() -> list[sqlite3.IntegrityError]:
    """Real SQLite failures, in order: a unique key repeated, a primary key repeated, a NOT NULL refused."""
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, k INTEGER NOT NULL UNIQUE)")
    connection.execute("INSERT INTO t VALUES (1, 1)")
    raised: list[sqlite3.IntegrityError] = []
    for row in ((2, 1), (1, 2), (3, None)):
        try:
            connection.execute("INSERT INTO t VALUES (?, ?)", row)
        except sqlite3.IntegrityError as exc:
            raised.append(exc)
    connection.close()
    return raised


def test_a_unique_violation_is_told_from_every_other_integrity_failure() -> None:
    """Guards: a dialect's unique-violation code dropped from the classifier, or a non-unique code added,
    so a rival chunk pass's collision is mistaken for a defect or a defect redrives as a collision."""
    unique, primary, not_null = _sqlite_integrity_errors()
    pairs = [
        (unique, not_null),
        (primary, not_null),
        (_PgError("23505"), _PgError("23502")),
    ]
    for violation, other in pairs:
        assert dialects.is_unique_violation(IntegrityError("INSERT", None, violation)) is True, violation
        assert dialects.is_unique_violation(IntegrityError("INSERT", None, other)) is False, other


# ---------------------------------------------------------------------------
# Row locks — the guard read's spelling per dialect
# ---------------------------------------------------------------------------


def _lock_sql(dialect: Dialect) -> str:
    table = Table("entry", MetaData(), Column("entry_id", String), Column("path", String))
    stmt = select(table.c.entry_id).where(table.c.path.in_(["/a"]))
    return " ".join(str(lock_rows(stmt).compile(dialect=dialect)).split())


class TestLockRows:
    def test_for_update_renders_where_the_compiler_has_it(self) -> None:
        assert _lock_sql(postgresql_dialect.dialect()).endswith("FOR UPDATE")

    def test_sqlite_renders_no_clause_the_writer_transaction_is_the_lock(self) -> None:
        sql = _lock_sql(sqlite_dialect.dialect())
        assert "FOR UPDATE" not in sql
        assert "WITH (" not in sql


class _Recorder:
    """A session that compiles each statement for one dialect and answers every read with a stamp of zero."""

    rowcount = 1

    def __init__(self, dialect: Dialect) -> None:
        self.dialect = dialect
        self.info: dict[str, object] = {}
        self.seen: list[str] = []

    def get_bind(self) -> _Recorder:
        return self

    async def execute(self, statement: Any) -> _Recorder:
        self.seen.append(" ".join(str(statement.compile(dialect=self.dialect)).split()))
        return self

    def scalar_one_or_none(self) -> int:
        return 0


# Each profile, the dialect that renders it, and what its hold must issue after the plain watch.
_HOLDS: list[tuple[DialectProfile, Dialect, tuple[str, ...]]] = [
    (SQLITE, sqlite_dialect.dialect(), ("WHERE vfs_principal_revisions.principal_id = ?",)),
    (POSTGRESQL, postgresql_dialect.dialect(), ("FOR SHARE",)),
    (GENERIC, postgresql_dialect.dialect(), ("FOR UPDATE",)),
]


def test_sqlite_alone_declares_that_its_attempts_run_out_of_reach() -> None:
    """Guards the declaration: on any other engine an attempt runs in its caller's task, the generic floor's too."""
    declared = {name for name, profile in PROFILES.items() if profile.attempts_out_of_reach}
    assert declared == {"sqlite"}
    assert (GENERIC.attempts_out_of_reach, profile_for("duckdb").attempts_out_of_reach) == (False, False)


def test_each_profile_declares_how_a_mint_shares_the_stamp_lock() -> None:
    """The shared form is one profile fact: a row lock by default, and what each other engine needs spelled."""
    assert SQLITE.share_lock == ShareLock()
    assert POSTGRESQL.share_lock == ShareLock(door=True)
    assert GENERIC.share_lock == profile_for("duckdb").share_lock == ShareLock(form="exclusive")


@pytest.mark.parametrize(("profile", "dialect", "hold"), _HOLDS, ids=[row[0].name for row in _HOLDS])
async def test_the_hold_renders_each_profiles_shared_form(
    profile: DialectProfile, dialect: Dialect, hold: tuple[str, ...]
) -> None:
    """The watch is a plain read on every engine; the hold is that read under the profile's shared lock.

    Guards each arm of the hold's spelling: a hold that read plainly
    would prove nothing a rival's commit could not undo before the mint's own.
    """
    recorder = _Recorder(dialect)
    session, tables = cast("AsyncSession", recorder), build_vfs_tables()
    await watch_postures(session, tables)
    await hold_postures(session, tables, profile)
    watch, *held = recorder.seen
    assert not any(word in watch for word in ("FOR SHARE", "FOR UPDATE", "LOCK ", "WITH ("))
    assert len(held) == len(hold)
    for statement, fragment in zip(held, hold, strict=True):
        assert fragment in statement, statement
    locking = ("FOR SHARE", "FOR UPDATE", "LOCK IN SHARE MODE", "WITH (")
    if profile is SQLITE:
        assert not any(word in held[-1] for word in locking), held[-1]


@pytest.mark.parametrize(("profile", "dialect", "hold"), _HOLDS, ids=[row[0].name for row in _HOLDS])
async def test_only_the_postgres_posture_write_locks_the_stamps_table_first(
    profile: DialectProfile, dialect: Dialect, hold: tuple[str, ...]
) -> None:
    """On Postgres a later mint's shared read passes a waiting posture write unless the table is locked first."""
    recorder = _Recorder(dialect)
    await open_relabel(cast("AsyncSession", recorder), build_vfs_tables(), profile, "/p", 7)
    doors = [statement for statement in recorder.seen if statement.startswith("LOCK TABLE")]
    if profile is POSTGRESQL:
        assert recorder.seen[0] == "LOCK TABLE vfs_principal_revisions IN EXCLUSIVE MODE"
        assert len(doors) == 1
    else:
        assert doors == []
    assert "UPDATE vfs_principal_revisions" in recorder.seen[len(doors)]


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Membership chunking — bounded statements at batch scale
# ---------------------------------------------------------------------------


# The declared contract is 10k rows in one call; the default run pins the
# same paging at a size that still pages, and the slow tier pins the contract.
BATCH_SIZES = [pytest.param(2_500, id="2500"), pytest.param(10_000, id="10k", marks=pytest.mark.slow)]


def _count_inserts(storage: DatabaseStorage, table: str) -> Callable[[], int]:
    """A counter of INSERT statements issued against *table* on *storage*'s engine."""
    seen = 0

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        nonlocal seen
        if statement.lstrip().upper().startswith(f"INSERT INTO {table.upper()}"):
            seen += 1

    return lambda: seen


class TestMembershipChunking:
    """No statement grows unboundedly with batch size — the ETL contract.

    Every membership predicate (``path IN``, ``id IN``, glob's anchor
    fan) chunks by ``membership_budget`` and merges, so a batch's SQL
    stays within every engine's limits (the floor's 1,000-element IN
    list, SQLAlchemy's 32,700 bind params) regardless of N.
    """

    def test_membership_budget_honors_both_caps(self) -> None:
        # The generic floor's 1,000-element IN-list cap binds first.
        assert membership_budget(GENERIC, 32_700) == 1_000
        # A parameter-capped engine binds through the tighter budget.
        assert membership_budget(replace(GENERIC, in_list_budget=65_535), 2_099) == 2_099 - 32
        # Both tuned engines bind through SQLAlchemy's parameter budget.
        assert membership_budget(SQLITE, 32_700) == membership_budget(POSTGRESQL, 32_700) == 32_668
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
        assert {e.kind for e in misses.errors} == {ErrorKind.not_found}
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

    @pytest.mark.parametrize("batch", BATCH_SIZES)
    async def test_a_large_entry_batch_round_trips(self, tmp_path, batch: int) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        inserts = _count_inserts(storage, "vfs_entries")
        entries = [
            Entry(path=Path(f"/lake/d{i // 500:02}/r{i:05}.json"), content=f'{{"row": {i}}}') for i in range(batch)
        ]
        written = await storage.write(entries=entries, parents=True)
        assert written.success is True, written.errors[:3]
        created = [o for o in written.observations if str(o.path).endswith(".json")]
        assert len(created) == batch
        assert all(o.status == "created" for o in created)
        assert inserts() >= 2  # the batch paged the bulk insert; one page would prove nothing
        stats = await storage.stat(observations=created)
        assert stats.success is True, stats.errors[:3]
        assert len(stats.observations) == batch
        await storage.close()

    @pytest.mark.parametrize("batch", BATCH_SIZES)
    async def test_a_large_edge_batch_round_trips(self, tmp_path, batch: int) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        inserts = _count_inserts(storage, "vfs_edges")
        entries = [Entry(path=Path("/hub.py"), content="hub")] + [
            Entry(path=Path(f"/spokes/s{i:05}.py"), content=f"s{i}") for i in range(batch)
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True
        edges = [
            Edge(source=Path("/hub.py"), target=Path(f"/spokes/s{i:05}.py"), edge_type="imports") for i in range(batch)
        ]
        created = await storage.mkedge(edges=edges)
        assert created.success is True, created.errors[:3]
        assert len(created.observations) == batch
        assert inserts() >= 2  # the batch paged the bulk insert
        assert all(o.status == "created" for o in created.observations)
        touched = await storage.mkedge(edges=edges)
        assert touched.success is True, touched.errors[:3]
        assert all(o.status == "updated" for o in touched.observations)
        removed = await storage.rmedge(edges=edges)
        assert removed.success is True, removed.errors[:3]
        assert all(o.status == "deleted" for o in removed.observations)
        await storage.close()


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
        "everyone_level": 2,
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
            if not is_statistics_statement(statement):  # the warming write's pass may land in the window
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
            if not is_statistics_statement(statement):
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
            await begin_as_writer(session)
            await session.execute(insert(tables.entry), [_entry_row(_ULID_A, "/a")])
        self._pin_mode(monkeypatch, mode)
        async with storage._host.session_factory() as session, session.begin():
            await begin_as_writer(session)
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
            await begin_as_writer(session)
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
        async with storage._host.session_factory() as session:
            await begin_as_writer(session)
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(page + 329))
            await session.commit()
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
        async with storage._host.session_factory() as session:
            await begin_as_writer(session)
            await bulk_insert(session, storage._host.tables.lex_postings, _block_rows(3))
            await session.commit()
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
        # can stand in for a named-paramstyle driver: dicts, not tuples, reach it.
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
            await begin_as_writer(session)
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
        tables = build_vfs_tables()
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
            (
                lambda: postgresql_dialect.dialect(paramstyle="format"),
                "VALUES (%s, %s, %s)",
                ("epoch", "term", "block_no"),
            ),
            (lambda: sqlite_dialect.dialect(paramstyle="named"), "VALUES (:epoch, :term, :block_no)", None),
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

    @pytest.mark.parametrize(
        "make",
        [sqlite_dialect.dialect, postgresql_dialect.dialect],
        ids=["sqlite", "postgresql"],
    )
    def test_the_bulk_statement_never_returns_the_identity_key(self, make: Callable[[], Dialect]) -> None:
        # A one-row insert into an identity-keyed table can pick up the dialect's
        # implicit RETURNING; under a parameter array that is one pending result per row.
        entry = build_vfs_tables().entry
        keys = tuple(column.key for column in entry.columns if column.key != "id")
        statement = dialects._bulk_statement(make(), entry, keys)
        assert "OUTPUT" not in statement.sql
        assert "RETURNING" not in statement.sql

    def test_profiles_pin_the_measured_mode(self) -> None:
        # Read from the before/after benchmark on each engine; GENERIC never
        # assumes an unknown driver's executemany is a batch.
        assert GENERIC.bulk_insert == "core"
        assert {p.name: p.bulk_insert for p in (SQLITE, POSTGRESQL)} == {"sqlite": "driver", "postgresql": "copy"}


class TestUpsertConstructor:
    """The one home of the dialect's ``ON CONFLICT`` insert, which the write path and the kernel's store share."""

    def test_upsert_constructor_is_dialect_bound(self) -> None:
        assert upsert_constructor(SQLITE) is sqlite_insert
        assert upsert_constructor(POSTGRESQL) is pg_insert


class TestValueTooLarge:
    """The engines' own single-value caps, recognised by code and type, never text."""

    def test_sqlite_reports_a_value_past_its_length_limit_as_a_data_error(self) -> None:
        assert is_value_too_large(sqlite3.DataError("string or blob too big")) is True
        assert is_value_too_large(_SqliteError(5)) is False

    def test_the_sqlstate_program_limit_class_counts(self) -> None:
        assert is_value_too_large(_PgError("54000")) is True
        assert is_value_too_large(_PgError("54001")) is True
        assert is_value_too_large(_PgError("23505")) is False

    def test_a_wrapped_driver_error_is_unwrapped_first(self) -> None:
        wrapped = DBAPIError("INSERT", None, sqlite3.DataError("too big"))
        assert is_value_too_large(wrapped) is True
        assert is_value_too_large(RuntimeError("nope")) is False


class TestBulkStatementCache:
    async def test_statements_are_cached_per_shape_and_retain_no_table(self, tmp_path) -> None:
        # Two mounts of one shape compile each bulk statement once between
        # them, and the key holds strings only, so a closed mount's metadata
        # is never pinned by this module.
        sizes: list[int] = []
        for name in ("first", "second"):
            home = tmp_path / name
            home.mkdir()
            storage = DatabaseStorage(url=_url(home))
            try:
                written = await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
                assert written.success is True
            finally:
                await storage.close()
            sizes.append(len(dialects._BULK_STATEMENTS))
        assert sizes[0] == sizes[1]
        for key in dialects._BULK_STATEMENTS:
            assert all(isinstance(part, str | tuple | type(None)) for part in key), key
