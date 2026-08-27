"""Per-dialect policy — the decisions SQLAlchemy deliberately leaves to us.

Facts SQLAlchemy models are read off the live ``Dialect`` object, never
copied here: the parameter budget is ``dialect.insertmanyvalues_max_parameters``
(SQLAlchemy trusts it for its own insert batching on every dialect), and
transport-down classification is ``dialect.is_disconnect()``.  What this
module declares is only what SQLAlchemy takes no position on: retryable
SQLSTATEs, connection/file settings, isolation pins, index-key byte
budgets, and create-arbitration mode.

Known engines (sqlite, postgresql, mssql, oracle, and the mysql/mariadb
family) carry tuned policy; **any other SQLAlchemy dialect resolves to
a conservative generic profile** — the backend runs on any
SQLAlchemy-compatible database, degrading to safe defaults rather than
refusing.

    profile = profile_for(engine.dialect.name)
    if is_retryable(profile, exc): ...

Retryability is classified by SQLSTATE, SQLite extended error code, or
integer driver error number — never by message text.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final, Generic, Literal, NamedTuple, TypeVar, cast

from sqlalchemy import bindparam, insert
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.schema import ColumnDefault

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from sqlalchemy import Table
    from sqlalchemy.engine import Dialect
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ClauseElement

# ---------------------------------------------------------------------------
# Stale-snapshot signal
# ---------------------------------------------------------------------------


class StaleSnapshot(Exception):  # noqa: N818 — a control-flow signal, not an error condition
    """A guarded statement missed: the snapshot it staged from is stale.

    Raised by write/topology builders when a rowcount-verified guard
    matches fewer rows than it staged — the world moved between the
    snapshot read and the mutation. The retry layer treats it exactly
    like a retryable driver outcome: discard the session (the whole
    transaction rolls back, staged inserts included) and redrive the
    method from a fresh snapshot. An exhausted redrive classifies as a
    retryable ``conflict`` on the public ``Result``.
    """

    def __init__(self, context: str) -> None:
        super().__init__(context)
        self.context = context


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


BulkInsertMode = Literal["driver", "copy", "core"]


@dataclass(frozen=True)
class DialectProfile:
    """One engine's declared policy.

    ``key_byte_budget`` caps index-key bytes on path/name columns (a
    lawful path over it classifies at the backend); ``in_list_budget``
    caps elements per ``IN`` expression list — a limit SQLAlchemy does
    not model and some engines enforce independently of bind-parameter
    count (Oracle's ORA-01795 at 1,000 is the generic floor);
    ``arbitration`` names how concurrent create resolves (native upsert
    vs catch-and-retry — the portable fallback). ``session_settings``
    run at every op-session start (connection state a borrowed pool
    cannot be assumed to carry); ``file_settings`` run once at first
    touch (database-file state). Isolation pins are ``None`` where the
    engine's default is the declared choice.

    ``expression_depth_budget`` caps the parse depth of one statement's
    expression tree — a left-deep ``OR`` chain's depth tracks its term
    count, independent of bind-parameter count. The default is SQLite's
    ``SQLITE_MAX_EXPR_DEPTH`` default (1,000), the tightest known cap;
    raise it per engine only with measurement.

    ``values_join`` declares whether the engine accepts a ``VALUES``
    table as an UPDATE join source in the column-aliased form SQLAlchemy
    renders (``(VALUES ...) AS name (col, ...)``) — a capability
    SQLAlchemy does not model: SQLite declares ``update_returning`` yet
    rejects that alias syntax. Guarded updates take the set-based
    RETURNING arm only where this is declared.

    ``tuple_in`` declares whether the engine accepts a row-value
    constructor inside an ``IN`` list (``(a, b) IN ((:x, :y), ...)``) —
    SQLAlchemy renders the form on request (``tuple_in_values`` picks
    the spelling) but takes no position on acceptance: T-SQL has no row
    constructors in ``IN``, and the generic floor claims nothing.

    ``like_bracket_class`` declares that the engine's ``LIKE`` treats
    ``[...]`` as a character class (the T-SQL family) — SQLAlchemy takes
    no position, and the fix cannot be unconditional: escaping ``[`` on
    engines without the class raises ORA-01424 on Oracle.
    :func:`~vfs.storage.backends.database.descent.escape_like` escapes
    ``[`` exactly where this is declared.

    ``content_bytes`` declares that casting the content column to the
    engine's bytes type returns exactly the column's UTF-8 bytes, cheaply
    — true where TEXT is stored as UTF-8 and the cast is a
    reinterpretation (sqlite: TEXT and BLOB share storage). Grep fetches
    bodies as bytes where declared, skipping the driver's decode and the
    matcher seam's re-encode; everywhere else bodies stay ``str``. Never
    declare it where the cast transcodes (NVARCHAR's UTF-16) or where
    the database character set may not be UTF-8 — wrong bytes match
    nothing, silently.

    ``bulk_insert`` declares how a bulk insert reaches the engine —
    ``"core"`` (SQLAlchemy's executemany, paged as multirow statements),
    ``"driver"`` (the DBAPI's own executemany on the session's
    connection), or ``"copy"`` (asyncpg's binary ``COPY`` of records on
    that connection). Which one wins is a per-driver fact SQLAlchemy
    takes no position on (asyncpg pipelines one execute per row but
    streams a COPY; sqlite3 has no round trips to lose; pyodbc round
    trips per row, and its parameter-array mode measured faster but
    dropped rows silently), so the value is read from the bulk-insert
    benchmark and the engine legs; the generic floor never assumes an
    unknown driver's executemany is a batch.

    ``guard_miss`` declares what a zero-row guarded UPDATE means on this
    engine — knowledge SQLAlchemy takes no position on. ``reprobe``:
    reads and guarded updates judge the same committed state, so a
    re-probe of the missed row classifies the miss honestly
    (``not_found`` vs ``conflict``). ``redrive``: the two disagree — on
    the mysql family at REPEATABLE READ the UPDATE current-reads past
    the snapshot the probe would report — so the only honest move is
    :class:`StaleSnapshot`, retrying the whole method from fresh state.
    The generic floor declares ``redrive``: never classify off a probe
    an unknown engine may contradict.
    """

    name: str
    key_byte_budget: int
    in_list_budget: int
    arbitration: Literal["upsert", "catch_retry"]
    guard_miss: Literal["reprobe", "redrive"] = "redrive"
    op_isolation: str | None = None
    topology_isolation: str | None = None
    session_settings: tuple[str, ...] = ()
    file_settings: tuple[str, ...] = ()
    retryable_sqlstates: frozenset[str] = frozenset({"40001", "40P01"})
    retryable_sqlite_codes: frozenset[int] = frozenset()
    # Integer driver error numbers, for drivers that lead with an errno
    # instead of a SQLSTATE (the MySQL family: PyMySQL/aiomysql args[0]).
    retryable_driver_codes: frozenset[int] = frozenset()
    expression_depth_budget: int = 1_000
    values_join: bool = False
    tuple_in: bool = False
    like_bracket_class: bool = False
    content_bytes: bool = False
    # How bulk_insert reaches the engine: Core's executemany, or the
    # driver's own on the session's connection — measured per engine.
    bulk_insert: BulkInsertMode = "core"


SQLITE: Final = DialectProfile(
    name="sqlite",
    key_byte_budget=4_096,
    in_list_budget=32_766,
    arbitration="upsert",
    guard_miss="reprobe",
    # mmap_size serves content reads from mapped pages (measured ~20%
    # off body fetch on the linux store); cache_size is 256 MiB in KiB.
    session_settings=(
        "PRAGMA busy_timeout = 5000",
        "PRAGMA synchronous = FULL",
        "PRAGMA case_sensitive_like = ON",
        "PRAGMA mmap_size = 8589934592",
        "PRAGMA cache_size = -262144",
    ),
    # page_size must precede WAL: a WAL database's page size is frozen.
    file_settings=(
        "PRAGMA page_size = 16384",
        "PRAGMA journal_mode = WAL",
    ),
    # SQLITE_BUSY (5) restarts the method; BUSY_SNAPSHOT (517) is a
    # discipline bug classified loudly, deliberately NOT retryable.
    retryable_sqlite_codes=frozenset({5}),
    tuple_in=True,
    content_bytes=True,
    # sqlite3.executemany: no round trips to lose, only Core's per-row work (1.9 vs 6.7 µs).
    bulk_insert="driver",
)

POSTGRESQL: Final = DialectProfile(
    name="postgresql",
    key_byte_budget=2_704,
    in_list_budget=65_535,
    arbitration="upsert",
    guard_miss="reprobe",
    op_isolation="REPEATABLE READ",
    topology_isolation="READ COMMITTED",
    values_join=True,
    tuple_in=True,
    # asyncpg pipelines one execute per row; binary COPY halves Core's pages (4.3 vs 9.1 µs).
    bulk_insert="copy",
)

MSSQL: Final = DialectProfile(
    name="mssql",
    key_byte_budget=1_700,
    in_list_budget=2_100,
    arbitration="catch_retry",
    guard_miss="reprobe",
    values_join=True,
    # T-SQL LIKE treats [...] as a character class; escape_like must
    # quote "[" here or a bracketed path silently misses its subtree.
    like_bracket_class=True,
    # pyodbc round-trips per row (560 µs); its parameter-array mode measured
    # 31 µs but silently dropped entry rows (203 of 300) — Core's pages stay.
    bulk_insert="core",
)

# catch_retry, not upsert: ON DUPLICATE KEY UPDATE takes no conflict
# target and fires on ANY unique index — unsafe beside two unique keys.
MYSQL: Final = DialectProfile(
    name="mysql",
    key_byte_budget=3_072,
    in_list_budget=65_535,
    arbitration="catch_retry",
    # A zero-row guard at REPEATABLE READ is ambiguous: the UPDATE
    # current-reads past the snapshot any re-probe would report.
    guard_miss="redrive",
    op_isolation="REPEATABLE READ",
    # Topology reads must see post-rival state per statement; REPEATABLE
    # READ would pin a pre-lock snapshot. Mirrors the Postgres pin.
    topology_isolation="READ COMMITTED",
    # Deadlock (1213) also carries SQLSTATE 40001; lock-wait timeout
    # (1205) ships under the HY000 catch-all, so only its errno classifies.
    retryable_driver_codes=frozenset({1213, 1205}),
    tuple_in=True,
    # aiomysql renders executemany as one multirow statement client-side (44 vs 51 µs).
    bulk_insert="driver",
)

MARIADB: Final = replace(MYSQL, name="mariadb")

# Budgets stay at the floor Oracle itself defines (ORA-01795's 1,000
# IN-list cap; the conservative key budget) — the tuning here is retry
# classification: python-oracledb exposes no SQLSTATE, so deadlock
# (ORA-00060) and serialization failure (ORA-08177, reachable only
# under a future isolation pin) ride the driver-code rung.
ORACLE: Final = DialectProfile(
    name="oracle",
    key_byte_budget=1_700,
    in_list_budget=1_000,
    arbitration="catch_retry",
    guard_miss="reprobe",
    retryable_driver_codes=frozenset({60, 8177}),
    tuple_in=True,
    # Core already issues array DML here; the bare driver path loses the
    # setinputsizes typing (DATE binds drop microseconds) — 179 leg failures.
    bulk_insert="core",
)

# The floor for engines this project has not measured: the tightest known
# key and IN-list budgets, no settings, serialization-failure SQLSTATEs only.
GENERIC: Final = DialectProfile(
    name="generic",
    key_byte_budget=1_700,
    in_list_budget=1_000,
    arbitration="catch_retry",
)

PROFILES: Final[dict[str, DialectProfile]] = {
    SQLITE.name: SQLITE,
    POSTGRESQL.name: POSTGRESQL,
    MSSQL.name: MSSQL,
    MYSQL.name: MYSQL,
    MARIADB.name: MARIADB,
    ORACLE.name: ORACLE,
}


def profile_for(dialect_name: str) -> DialectProfile:
    """The declared policy for *dialect_name*, or the generic floor.

    Unknown dialects are served, not refused: they get the generic
    profile stamped with their own name so classification and messages
    stay honest about what is running.
    """
    known = PROFILES.get(dialect_name)
    if known is not None:
        return known
    return replace(GENERIC, name=dialect_name)


def op_execution_options(profile: DialectProfile, *, writer: bool) -> dict[str, str | bool]:
    """Execution options for one op's connection: writer marker, isolation pin.

    Multi-statement verbs must observe a single committed snapshot, so a
    declared ``op_isolation`` is stamped on every op connection. Empty
    when nothing is declared — read ops on engines whose default is the
    declared choice keep their lazy connection checkout.
    """
    options: dict[str, str | bool] = {}
    if writer:
        options["vfs_writer"] = True
    if profile.op_isolation is not None:
        options["isolation_level"] = profile.op_isolation
    return options


def topology_execution_options(profile: DialectProfile) -> dict[str, str | bool]:
    """Execution options for a topology verb's connection: writer marker, topology pin.

    Topology verbs trade the op snapshot for the serialization point:
    a declared ``topology_isolation`` — never ``op_isolation`` — stamps
    the connection, because every refusal check must judge post-rival
    state read *after* the point is taken, and a repeatable snapshot
    would freeze the world at the lock call itself.
    """
    options: dict[str, str | bool] = {"vfs_writer": True}
    if profile.topology_isolation is not None:
        options["isolation_level"] = profile.topology_isolation
    return options


# ---------------------------------------------------------------------------
# Statement chunking — membership predicates never outgrow an engine
# ---------------------------------------------------------------------------

# Bind params held back from each membership chunk for a statement's
# fixed predicates (the liveness filter, projection, depth caps).
_FILTER_BIND_RESERVE: Final = 32

# Depth units held back from each OR-fan chunk for the fixed predicates
# AND-chained above the fan.
_EXPRESSION_DEPTH_RESERVE: Final = 64


def membership_budget(profile: DialectProfile, parameter_budget: int) -> int:
    """Elements per ``IN``-list chunk: the element cap net of fixed binds.

    Every membership predicate (``path IN``, ``id IN``) chunks by this
    and merges results, so batch size never reaches an engine limit —
    the ETL contract that 10,000+-entry batches serve on every dialect.
    """
    return max(1, min(profile.in_list_budget, parameter_budget - _FILTER_BIND_RESERVE))


# Measured OR-fan sweet spot: the win saturates by ~200 arms/statement,
# and 200 clears every known engine's bind, IN-list, and depth caps.
_PATTERN_ARM_CEILING: Final = 200


def arm_budget(profile: DialectProfile, parameter_budget: int, arm_binds: int) -> int:
    """Pattern arms per glob OR-fan chunk: the tightest cap, floored at one.

    Each arm spends *arm_binds* bind slots and roughly one depth unit in
    the left-deep ``OR`` chain (the arm's own conjuncts ride under the
    depth reserve). The measured ceiling binds before either engine cap
    on every profiled dialect.
    """
    by_binds = membership_budget(profile, parameter_budget) // max(1, arm_binds)
    by_depth = profile.expression_depth_budget - _EXPRESSION_DEPTH_RESERVE
    return max(1, min(_PATTERN_ARM_CEILING, by_binds, by_depth))


# Spelled pre-PEP-695: type-parameter syntax is 3.12+, above the floor.
T = TypeVar("T")


def chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Slices of *items* at most *size* long, in order."""
    step = max(1, size)
    for index in range(0, len(items), step):
        yield items[index : index + step]


class ByteBatcher(Generic[T]):
    """Byte-bounded singleton-exempt accumulator — the flush law's one owner.

    Items accumulate until adding the next would exceed *budget*, at
    which point the full batch flushes *before* the add (bound =
    ``max(budget, one item)``): one oversized item rides alone, so the
    budget shapes transient residency, never eligibility or results.
    *size_of* is the caller's declared metering — exact bytes where it
    has them, chars-as-proxy where it declares one. This incremental
    form serves streaming producers (an async row scan cannot feed a
    sync generator); sequence callers use :func:`byte_chunked`.
    """

    def __init__(self, size_of: Callable[[T], int], budget: int) -> None:
        self._size_of = size_of
        self._budget = budget
        self._batch: list[T] = []
        self._total = 0

    def add(self, item: T) -> list[T] | None:
        """Accumulate *item*; return the batch the flush law completed, if any."""
        size = self._size_of(item)
        full = None
        if self._batch and self._total + size > self._budget:
            full = self._batch
            self._batch, self._total = [], 0
        self._batch.append(item)
        self._total += size
        return full

    def flush(self) -> list[T] | None:
        """Return the final partial batch, or ``None`` when nothing is held."""
        batch = self._batch or None
        self._batch, self._total = [], 0
        return batch


def byte_chunked(items: Iterable[T], size_of: Callable[[T], int], budget: int) -> Iterator[list[T]]:
    """Slices of *items* whose summed *size_of* fits *budget*, in order.

    The byte-bounded twin of :func:`chunked`: every item is emitted in
    exactly one batch, concatenation preserves order, and the
    :class:`ByteBatcher` flush law bounds each batch at
    ``max(budget, one item)``.
    """
    batcher: ByteBatcher[T] = ByteBatcher(size_of, budget)
    for item in items:
        full = batcher.add(item)
        if full is not None:
            yield full
    final = batcher.flush()
    if final is not None:
        yield final


def rows_per_statement(parameter_budget: int, rows: Sequence[Mapping[str, object]]) -> int:
    """Rows one multi-row statement may carry: the budget over the widest row.

    Requires non-empty *rows* — no caller builds a statement that carries
    zero rows. The floor of one row keeps a pathological budget (narrower
    than a single row) making progress instead of stalling ``chunked``.
    """
    return max(1, parameter_budget // max(len(row) for row in rows))


# Bind slots held back from every measured multi-row statement: driver
# wrappers (ODBC's sp_prepexec among them) spend from the same server cap.
_STATEMENT_BIND_RESERVE: Final = 8


R = TypeVar("R")


def statement_budget(
    build: Callable[[Sequence[R]], ClauseElement[Any]],
    probe_row: R,
    dialect: Dialect,
    *,
    parameter_budget: int,
    row_width: int,
    row_cap: int | None = None,
) -> int:
    """Rows per multi-row statement, measured off the compiled bind registry.

    *build(rows)* returns the statement carrying *rows*; the helper
    compiles it over one and two copies of *probe_row*, so duplication —
    what makes the arithmetic exact — is owned here, never re-remembered
    per caller: the bind-count delta of a duplicated row is that row's
    true per-row cost, and the remainder of the one-row count is the
    statement's fixed overhead — a bind outside the per-row tuple (a
    compiled literal, a fixed predicate) can never escape the
    arithmetic. The declared *row_width* is the all-bind ceiling the
    chunk is charged at (``NULL`` cells compile inline, so the measured
    delta may undershoot it); a delta *exceeding* the declaration is
    drift and fails loudly here, never at an engine's cap. *row_cap* is
    an optional additional ceiling (the membership budget, where a
    caller also bounds row count).
    """
    one = len(build([probe_row]).compile(dialect=dialect).bind_names)
    two = len(build([probe_row, probe_row]).compile(dialect=dialect).bind_names)
    per_row = two - one
    if per_row > row_width:
        raise AssertionError(f"declared row width {row_width} < compiled per-row bind delta {per_row}")
    fixed = one - per_row
    rows = max(1, (parameter_budget - fixed - _STATEMENT_BIND_RESERVE) // max(1, row_width))
    return rows if row_cap is None else max(1, min(row_cap, rows))


def supports_values_update(profile: DialectProfile, dialect: Dialect) -> bool:
    """Whether the set-based ``VALUES``-join ``UPDATE … RETURNING`` can run.

    The profile declares the join form (a decision SQLAlchemy takes no
    position on); the live dialect must model RETURNING on a
    multi-FROM UPDATE. Callers that fail this arbitrate down their own
    fallback ladder — executemany with verification, or a classified
    ``unsupported``.
    """
    return bool(profile.values_join and dialect.update_returning and dialect.update_returning_multifrom)


# ---------------------------------------------------------------------------
# Bulk inserts
# ---------------------------------------------------------------------------


class _BulkStatement(NamedTuple):
    """One dialect's rendering of a table insert over a fixed key set."""

    sql: str
    names: tuple[str, ...]
    positional: tuple[str, ...] | None
    processors: tuple[Callable[[Any], Any] | None, ...]
    defaults: dict[str, object]


# A statement the adapter must see before a raw COPY (see bulk_insert).
_COPY_PROLOGUE: Final = "SELECT 1"

# ISO 9075 class 23: integrity constraint violation — the class the
# savepoint re-drives key on when a raw driver call raises it.
_SQLSTATE_INTEGRITY_CLASS: Final = "23"

# Compiled once per (dialect facts, table, key set); bounded by the product
# of live dialects, mounts and bulk sites, never by rows.
_BULK_STATEMENTS: dict[tuple[str, str, str, Table, tuple[str, ...]], _BulkStatement] = {}


async def bulk_insert(session: AsyncSession, table: Table, rows: Sequence[Mapping[str, object]]) -> None:
    """Insert *rows* into *table* by the dialect's declared bulk mode.

    The one owner of every bulk insert that learns nothing back — no
    ``RETURNING``, no rowcount verification. ``"core"`` issues
    SQLAlchemy's executemany (its insertmanyvalues pages); ``"copy"``
    streams the rows as a binary ``COPY`` on this session's connection
    and transaction (asyncpg); ``"driver"`` hands the driver its own
    executemany there, with the statement compiled once per dialect,
    table and key set, Core's own bind processors applied per column,
    and Python-side scalar defaults filled for omitted columns — so the
    driver receives exactly the values Core would have sent, minus
    Core's per-row processing. Driver calls are paged by
    :func:`rows_per_statement` under the live parameter budget, so a
    driver that renders executemany as one multirow statement never
    builds one Core would not have. Every row carries the first row's
    keys; a callable Python-side default is refused (no bulk table
    declares one). Empty *rows* is a no-op.
    """
    if not rows:
        return
    dialect = session.get_bind().dialect
    mode = profile_for(dialect.name).bulk_insert
    if mode == "core":
        await session.execute(insert(table), list(rows))
        return
    keys = frozenset(rows[0])
    statement = _bulk_statement(dialect, table, tuple(rows[0]))
    processed = [_bulk_values(statement, row, keys) for row in rows]
    page = rows_per_statement(dialect.insertmanyvalues_max_parameters, [dict.fromkeys(statement.names)])
    connection = await session.connection()
    if mode == "copy":
        # The adapter opens the driver transaction lazily on its first
        # statement; a raw COPY before that would run in autocommit.
        await connection.exec_driver_sql(_COPY_PROLOGUE)
        driver = (await connection.get_raw_connection()).driver_connection
        assert driver is not None
        for chunk in chunked([tuple(values[n] for n in statement.names) for values in processed], page):
            try:
                await driver.copy_records_to_table(
                    table.name, records=list(chunk), columns=list(statement.names), schema_name=table.schema
                )
            except Exception as exc:
                raise _wrap_driver_error(table, exc) from exc
        return
    params: list[tuple[Any, ...]] | list[dict[str, Any]]
    if statement.positional is None:
        params = processed
    else:
        params = [tuple(values[n] for n in statement.positional) for values in processed]
    for chunk in chunked(params, page):
        await connection.exec_driver_sql(statement.sql, list(chunk))


# ---------------------------------------------------------------------------
# Retryable-error classification
# ---------------------------------------------------------------------------


# ISO 9075's vendor catch-all: it says "look elsewhere", so classification
# falls through to the driver errno instead of judging by it.
_SQLSTATE_GENERAL_ERROR: Final = "HY000"


def is_retryable(profile: DialectProfile, exc: BaseException) -> bool:
    """Whether *exc* is a transient outcome a whole-method restart can clear.

    Classifies by SQLite extended error code, SQLSTATE, or integer driver
    error number — never message text. A ``HY000`` SQLSTATE carries no
    classification by definition and defers to the driver errno (MySQL
    ships lock-wait timeout 1205 under it). Unique violations (23505)
    are definite exists-outcomes after arbitration and are never in any
    profile's retryable set.
    """
    origin = getattr(exc, "orig", None) or exc
    sqlite_code = getattr(origin, "sqlite_errorcode", None)
    if sqlite_code is not None:
        return sqlite_code in profile.retryable_sqlite_codes
    state = _sqlstate_of(origin)
    if state is not None and state != _SQLSTATE_GENERAL_ERROR:
        return state in profile.retryable_sqlstates
    return _driver_code_of(origin) in profile.retryable_driver_codes


def is_permanent_defect(exc: BaseException) -> bool:
    """Whether *exc* reports a statement defect no retry can clear.

    SQLSTATE class 42 (syntax error or access rule violation) and
    class 07 (dynamic SQL error — bind-count and descriptor
    mismatches) mean the statement itself is wrong: a vfs bug to
    surface loudly, never an operating condition to keep retrying.
    DBAPI ``ProgrammingError`` covers drivers that expose no SQLSTATE.
    SQLite's generic result code is deliberately not classified here:
    it covers statement defects and missing-schema operating
    conditions alike, indistinguishable by code. Classification is by
    code and exception type — never message text.
    """
    origin = getattr(exc, "orig", None) or exc
    state = _sqlstate_of(origin)
    if state is not None and state[:2] in _SQLSTATE_DEFECT_CLASSES:
        return True
    return isinstance(exc, ProgrammingError)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# ISO 9075 classes 42 (syntax/access-rule violation) and 07 (dynamic
# SQL error): the statement itself is defective, never transient.
_SQLSTATE_DEFECT_CLASSES: Final = frozenset({"42", "07"})


# SQLSTATE codes are exactly five characters (ISO/IEC 9075).
_SQLSTATE_LENGTH: Final = 5


def _sqlstate_of(origin: object) -> str | None:
    """The SQLSTATE of a driver exception, if it carries one.

    asyncpg and psycopg expose ``sqlstate``, psycopg2 ``pgcode``; pyodbc
    puts the SQLSTATE (not text) first in ``args``.
    """
    state = getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None)
    if isinstance(state, str):
        return state
    first = next(iter(getattr(origin, "args", ())), None)
    if isinstance(first, str) and len(first) == _SQLSTATE_LENGTH:
        return first
    return None


def _driver_code_of(origin: object) -> int | None:
    """The integer driver error number, where the driver leads with one.

    The MySQL family (PyMySQL, aiomysql, asyncmy) raises with
    ``args = (errno, message)``; python-oracledb raises with a single
    ``_Error`` argument whose errno lives on ``.code``. Neither exposes
    a SQLSTATE attribute.
    """
    first = next(iter(getattr(origin, "args", ())), None)
    if isinstance(first, int):
        return first
    code = getattr(first, "code", None)
    return code if isinstance(code, int) else None


def _bulk_statement(dialect: Dialect, table: Table, keys: tuple[str, ...]) -> _BulkStatement:
    cache_key = (dialect.name, dialect.driver, dialect.paramstyle, table, keys)
    cached = _BULK_STATEMENTS.get(cache_key)
    if cached is not None:
        return cached
    defaults: dict[str, object] = {}
    for column in table.columns:
        default = column.default
        if column.key in keys or default is None:
            continue
        if not isinstance(default, ColumnDefault) or not default.is_scalar:
            raise TypeError(f"{table.name}.{column.key}: only a scalar Python-side default can ride a bulk insert")
        defaults[column.key] = default.arg
    names = keys + tuple(defaults)
    compiled = insert(table).values({name: bindparam(name) for name in names}).compile(dialect=dialect)
    processors = tuple(table.c[name].type.dialect_impl(dialect).bind_processor(dialect) for name in names)
    positional = tuple(compiled.positiontup or ()) if dialect.positional else None
    statement = _BulkStatement(str(compiled), names, positional, processors, defaults)
    _BULK_STATEMENTS[cache_key] = statement
    return statement


def _wrap_driver_error(table: Table, exc: BaseException) -> DBAPIError:
    """A raw driver call bypasses SQLAlchemy's wrapping; restore the classes callers catch."""
    statement = f"bulk insert {table.name}"
    if (_sqlstate_of(exc) or "").startswith(_SQLSTATE_INTEGRITY_CLASS):
        return IntegrityError(statement, None, cast("Exception", exc))
    return DBAPIError(statement, None, cast("Exception", exc))


def _bulk_values(statement: _BulkStatement, row: Mapping[str, object], keys: frozenset[str]) -> dict[str, Any]:
    if row.keys() != keys:
        raise TypeError(f"bulk insert rows must share one key set: {sorted(row)} != {sorted(keys)}")
    values = {**statement.defaults, **row}
    return {
        name: (values[name] if processor is None else processor(values[name]))
        for name, processor in zip(statement.names, statement.processors, strict=True)
    }
