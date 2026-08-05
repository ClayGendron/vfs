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
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from sqlalchemy.engine import Dialect
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


SQLITE: Final = DialectProfile(
    name="sqlite",
    key_byte_budget=4_096,
    in_list_budget=32_766,
    arbitration="upsert",
    guard_miss="reprobe",
    session_settings=(
        "PRAGMA busy_timeout = 5000",
        "PRAGMA synchronous = FULL",
        "PRAGMA case_sensitive_like = ON",
    ),
    # page_size must precede WAL: a WAL database's page size is frozen.
    file_settings=(
        "PRAGMA page_size = 16384",
        "PRAGMA journal_mode = WAL",
    ),
    # SQLITE_BUSY (5) restarts the method; BUSY_SNAPSHOT (517) is a
    # discipline bug classified loudly, deliberately NOT retryable.
    retryable_sqlite_codes=frozenset({5}),
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
)

MSSQL: Final = DialectProfile(
    name="mssql",
    key_byte_budget=1_700,
    in_list_budget=2_100,
    arbitration="catch_retry",
    guard_miss="reprobe",
    values_join=True,
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


def chunked[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Slices of *items* at most *size* long, in order."""
    step = max(1, size)
    for index in range(0, len(items), step):
        yield items[index : index + step]


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


def statement_budget[R](
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
