"""Per-dialect policy — the decisions SQLAlchemy deliberately leaves to us.

Facts SQLAlchemy models are read off the live ``Dialect`` object, never
copied here: the parameter budget is ``dialect.insertmanyvalues_max_parameters``
(SQLAlchemy trusts it for its own insert batching on every dialect), and
transport-down classification is ``dialect.is_disconnect()``.  What this
module declares is only what SQLAlchemy takes no position on: retryable
SQLSTATEs, connection/file settings, isolation pins, index-key byte
budgets, create-arbitration mode, the row-lock and membership
spellings, and the vector-distance facts.

Known engines (sqlite, postgresql, mssql, oracle, mariadb) carry tuned
policy; **any other SQLAlchemy dialect resolves to a conservative
generic profile** — the backend serves the core verbs on any
SQLAlchemy-compatible database, degrading to safe defaults rather than
refusing, and withholds the ranked verbs the floor cannot vouch for.

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

    from sqlalchemy import Select, Table
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
MembershipForm = Literal["in_list", "values"]
VectorDistance = Literal["none", "exact", "ann"]
RangeSource = Literal["json_each", "unnest", "openjson", "json_table", "json_table_clob"]


class RangeHints(NamedTuple):
    """Optimizer hints the range join's statements carry, as ``str.format`` templates; empty where none is needed.

    ``everyone`` prefixes the everyone branch (``{entry}`` the table,
    ``{index}`` the ``(everyone_level, path)`` index); ``ranges`` prefixes
    each range branch (``{source}`` the unpacked ranges' alias,
    ``{count}`` its row count); ``derived`` prefixes a statement that
    joins the visible set as a derived table (``{visible}`` its alias,
    ``{table}`` the chunk-side table, ``{index}`` its entry index);
    ``relabel`` prefixes the literal-``OR`` relabel ``UPDATE``.
    """

    everyone: str = ""
    ranges: str = ""
    derived: str = ""
    relabel: str = ""


NO_RANGE_HINTS: Final = RangeHints()

RELABEL_ROWS: Final = 50_000
"""Entry rows per relabel chunk, the default every profile declares: the
measured safe statement size on every engine (see ``relabel_rows``)."""


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
    trips per row, and its parameter-array mode is still one RPC per
    row, slower than Core's pages on wide rows), so the value is read
    from the bulk-insert benchmark and the engine legs; the generic
    floor never assumes an unknown driver's executemany is a batch.

    ``vector_distance`` declares the engine's server-side cosine:
    ``exact`` (a distance function, no usable ANN index — SQL Server
    2025, whose DiskANN makes the table read-only; SQLite through the
    sqlite-vec extension vfs loads), ``ann`` (a distance function and an
    index the planner may use), or ``none`` — only the generic floor,
    which therefore serves no ranked verb. Facts SQLAlchemy takes no
    position on, read from the engine matrix.
    ``vector_dimension_cap`` is the widest native column the engine
    creates (pgvector 16,000; SQL Server 1,998; MariaDB 16,383 — its
    65,535-byte row cap binds first; Oracle 65,535); ``ann_dimension_cap``
    the widest an ANN index accepts (pgvector's HNSW 2,000).
    ``ann_honours_scope`` declares that a scoped query can still use the
    ANN index (pgvector filters inside the index scan; MariaDB and
    Oracle drop to an exact scan the moment a predicate appears).

    ``range_source`` declares the table function that unpacks one bound
    list of path ranges into rows, so a partial caller's rights join the
    ``path`` index with statement text that never changes with its
    grants: ``json_each`` (SQLite), ``unnest`` of arrays (Postgres),
    ``OPENJSON`` (SQL Server), ``JSON_TABLE`` (MariaDB, the bound list
    cast to bytes), ``json_table_clob`` (Oracle: ``JSON_TABLE`` over a
    CLOB bind, so any number of ranges travels). SQLAlchemy takes no
    position on it. ``None`` keeps the literal OR of pieces — the
    generic floor.

    ``range_join`` declares the join keyword between the unpacked
    ranges and the entry table in a range branch — SQLAlchemy models
    only ``JOIN`` and its outer forms. Measured on five engines with
    the everyone level on the row: SQLite's planner otherwise seeks
    ``everyone_level < :r`` on the composite index and scans the ranges
    per row (90 ms against 1 ms at 1,000 users), so it takes ``CROSS
    JOIN`` with the ranges driving; MariaDB otherwise scans the
    composite with a block nested loop over the ranges (745 ms against
    50 at 10,000), so it takes ``STRAIGHT_JOIN`` with the ranges first
    and ``FORCE INDEX`` on the path index (``range_entry_hint``); SQL
    Server rewrites the plain join into a semi-join driven by a scan
    of the entry table (3.2 s against 64 ms), so it takes ``INNER LOOP
    JOIN`` with the ranges outer; Postgres and Oracle plan the plain
    ``JOIN`` correctly. ``range_hints`` carries Oracle's optimizer
    hints, the only dialect whose spelling takes a number from the
    caller: without ``CARDINALITY`` on the unpacked ranges it estimates
    them at 8,168 rows and hash-joins a full scan; without the index
    hint on the everyone branch it full-scans; without the derived
    hints the chunk index drives and the visible set is re-evaluated
    per chunk row. ``range_settings`` are statements issued in the
    transaction before a partial caller's read: Postgres turns JIT off
    for it, because the range branch is misestimated by orders of
    magnitude and JIT compilation then costs a hundred milliseconds a
    statement. ``range_fence`` names the common-table-expression prefix
    that keeps the visible set from being pushed down into the statement
    that joins it: SQLite otherwise pushes the outer table into every
    branch of the union and drives each from it, scanning the unpacked
    ranges once per outer row (3.9 s against 35 ms for a 52,000-row
    tree at 10,000 users); ``MATERIALIZED`` computes the union once,
    every piece a seek, and the outer statement probes it. ``None``
    joins the visible set as a plain derived table, the measured shape
    on the other engines.

    ``row_lock_hint`` declares how a guard read locks the rows it
    addresses. SQLAlchemy models ``FOR UPDATE`` yet its T-SQL compiler
    renders ``with_for_update()`` as a bare SELECT (the clause exists
    only on cursors there), so SQL Server spells the lock as a table
    hint: ``UPDLOCK`` alone — update locks on the addressed keys, held
    to commit, exactly what ``FOR UPDATE`` means elsewhere; ``HOLDLOCK``
    is not taken, its key-range locks guard phantoms the guard never
    reads. ``None`` means ``FOR UPDATE`` as the compiler renders it —
    also nothing on SQLite, lawfully: the writer transaction is the
    lock there. :func:`lock_rows` applies the declared spelling. SQL
    Server's hint also names ``FORCESEEK``: under the ``values``
    membership form a locking read that the optimizer plans as a scan
    takes an update lock on every row and escalates to a table lock,
    so the seek is forced where the lock is held (measured: two key
    locks per row, never a table lock, at 40,000 rows in one
    transaction).

    ``membership`` declares how a chunked membership predicate
    (``column IN (...)``) reaches the engine — a plan-quality decision
    SQLAlchemy takes no position on. ``in_list`` is the expanding bind
    list every compiler renders. ``values`` joins a ``VALUES`` derived
    table of the keys instead: SQL Server plans a long ``IN`` list as a
    clustered scan on small tables and converts every ``nvarchar`` bind
    against a ``varchar`` key (one non-Latin path makes the seek range
    swallow the table), while the derived table seeks at every table
    size and casts the keys once, server-side, in the column's own
    collation. :mod:`~vfs.storage.backends.database.membership` spells
    both. ``in_list_budget`` doubles as the lock budget there: two key
    locks per row under ``UPDLOCK``, kept under the 5,000-lock
    escalation trigger per statement.

    ``guard_miss`` declares what a zero-row guarded UPDATE means on this
    engine — knowledge SQLAlchemy takes no position on. ``reprobe``:
    reads and guarded updates judge the same committed state, so a
    re-probe of the missed row classifies the miss honestly
    (``not_found`` vs ``conflict``). ``redrive``: the two disagree — on
    MariaDB at REPEATABLE READ the UPDATE current-reads past
    the snapshot the probe would report — so the only honest move is
    :class:`StaleSnapshot`, retrying the whole method from fresh state.
    The generic floor declares ``redrive``: never classify off a probe
    an unknown engine may contradict.

    ``relabel_rows`` caps the entry rows one relabel chunk rewrites — a
    posture change's ``UPDATE`` over its subtree, one chunk per
    transaction. SQLAlchemy models no such thing: the bind budgets bound
    a statement's text, not the rows it touches, and what this bounds is
    the time one chunk holds its row locks and the admin lock, so a
    posture change over millions of rows never parks every reader and
    rival admin write behind one transaction. Measured on all five
    engines: 50,000 rows per statement, one transaction per statement,
    was safe everywhere (the slowest, SQL Server at 38 µs a row, holds a
    chunk under two seconds); the value is the same on every profile
    because no engine measured a reason to differ.
    """

    name: str
    key_byte_budget: int
    in_list_budget: int
    arbitration: Literal["upsert", "catch_retry"]
    guard_miss: Literal["reprobe", "redrive"] = "redrive"
    row_lock_hint: str | None = None
    membership: MembershipForm = "in_list"
    op_isolation: str | None = None
    topology_isolation: str | None = None
    session_settings: tuple[str, ...] = ()
    file_settings: tuple[str, ...] = ()
    retryable_sqlstates: frozenset[str] = frozenset({"40001", "40P01"})
    retryable_sqlite_codes: frozenset[int] = frozenset()
    # Integer driver error numbers, for drivers that lead with an errno
    # instead of a SQLSTATE (the MySQL family's drivers: aiomysql args[0]).
    retryable_driver_codes: frozenset[int] = frozenset()
    expression_depth_budget: int = 1_000
    values_join: bool = False
    tuple_in: bool = False
    like_bracket_class: bool = False
    content_bytes: bool = False
    # How bulk_insert reaches the engine: Core's executemany, or the
    # driver's own on the session's connection — measured per engine.
    bulk_insert: BulkInsertMode = "core"
    vector_distance: VectorDistance = "none"
    vector_dimension_cap: int | None = None
    ann_dimension_cap: int | None = None
    ann_honours_scope: bool = False
    range_source: RangeSource | None = None
    range_join: str = "JOIN"
    range_entry_hint: str | None = None
    range_hints: RangeHints = NO_RANGE_HINTS
    range_settings: tuple[str, ...] = ()
    range_fence: str | None = None
    relabel_rows: int = RELABEL_ROWS


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
    # vec_distance_cosine from sqlite-vec, loaded on every connection; brute force, exact.
    vector_distance="exact",
    range_source="json_each",
    range_join="CROSS JOIN",
    range_fence="MATERIALIZED",
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
    vector_distance="ann",
    range_source="unnest",
    range_settings=("SET LOCAL jit = off",),
    vector_dimension_cap=16_000,
    ann_dimension_cap=2_000,
    ann_honours_scope=True,
)

MSSQL: Final = DialectProfile(
    name="mssql",
    key_byte_budget=1_700,
    # A lock budget as much as a bind budget (2,100): two key locks per
    # row under UPDLOCK stay under the 5,000-lock escalation trigger.
    in_list_budget=2_000,
    arbitration="catch_retry",
    guard_miss="reprobe",
    # with_for_update() renders as a bare SELECT on T-SQL; the guard read
    # locks through this hint, and seeks, or the lock is a table lock.
    row_lock_hint="UPDLOCK, FORCESEEK",
    membership="values",
    values_join=True,
    # T-SQL LIKE treats [...] as a character class; escape_like must
    # quote "[" here or a bracketed path silently misses its subtree.
    like_bracket_class=True,
    # pyodbc round-trips per row (560 µs); its parameter-array mode is still
    # one RPC per row — slower than Core's multirow pages on entry-wide rows.
    bulk_insert="core",
    vector_distance="exact",
    range_source="openjson",
    range_join="INNER LOOP JOIN",
    vector_dimension_cap=1_998,
)

# catch_retry, not upsert: ON DUPLICATE KEY UPDATE takes no conflict
# target and fires on ANY unique index — unsafe beside two unique keys.
# MariaDB is the MySQL family's supported member: community MySQL has
# the VECTOR type but no distance function and no extension vfs can
# install, so it is served as an unknown dialect.
MARIADB: Final = DialectProfile(
    name="mariadb",
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
    # (1205) ships under the HY000 catch-all, so only its errno classifies;
    # 1020 is the snapshot-isolation conflict (11.6+ default), a restart.
    retryable_driver_codes=frozenset({1213, 1205, 1020}),
    tuple_in=True,
    # aiomysql renders executemany as one multirow statement client-side (44 vs 51 µs).
    bulk_insert="driver",
    # VEC_DISTANCE_COSINE and an MHNSW index the planner uses only on an
    # unscoped ORDER BY … LIMIT; the InnoDB row cap binds before 16,383.
    vector_distance="ann",
    range_source="json_table",
    range_join="STRAIGHT_JOIN",
    range_entry_hint="FORCE INDEX ({index})",
    vector_dimension_cap=16_383,
)

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
    vector_distance="ann",
    vector_dimension_cap=65_535,
    range_source="json_table_clob",
    range_hints=RangeHints(
        everyone="/*+ INDEX({entry} {index}) */",
        ranges="/*+ CARDINALITY({source} {count}) */",
        derived="/*+ NO_MERGE({visible}) LEADING({visible}) USE_NL({table}) INDEX({table} {index}) */",
        relabel="/*+ USE_CONCAT */",
    ),
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
# Row locks — the guard read's spelling
# ---------------------------------------------------------------------------

_Row = TypeVar("_Row", bound=tuple[Any, ...])


def lock_rows(stmt: Select[_Row], table: Table, profile: DialectProfile) -> Select[_Row]:
    """*stmt* as a locking read of *table*'s rows, held to the transaction's end.

    The liveness proof every guard rests on: a row read through here
    cannot be rewritten or deleted by a rival before this transaction
    commits, so the caller's decision stands on the row it read. Spelled
    ``FOR UPDATE`` wherever the compiler renders it, and as the
    profile's table hint where it declares one (T-SQL); the hint is
    gated on the profile's dialect name, so it never leaks into another
    engine's SQL. Callers order the rows they lock (sorted keys, chunked)
    so rival batches lock in one order; a deadlock against a verb with
    its own claim order classifies retryable and rides the retry channel.
    """
    if profile.row_lock_hint is None:
        return stmt.with_for_update()
    return stmt.with_hint(table, f"WITH ({profile.row_lock_hint})", dialect_name=profile.name)


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

# Exception-context links walked for a transient cause behind an unwind error.
_UNWIND_DEPTH: Final = 4


def is_retryable(profile: DialectProfile, exc: BaseException) -> bool:
    """Whether *exc* is a transient outcome a whole-method restart can clear.

    Classifies by SQLite extended error code, SQLSTATE, or integer driver
    error number — never message text. A ``HY000`` SQLSTATE carries no
    classification by definition and defers to the driver errno (MySQL
    ships lock-wait timeout 1205 under it). Unique violations (23505)
    are definite exists-outcomes after arbitration and are never in any
    profile's retryable set. An error raised while *unwinding* from a
    retryable one is retryable too: a deadlock rolls the whole
    transaction back on InnoDB, so the savepoint release that follows
    fails with its own error (MariaDB's 1305), and the transient cause
    sits one link down the exception's context chain.
    """
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < _UNWIND_DEPTH:
        if _is_retryable_alone(profile, current):
            return True
        current = current.__context__
        seen += 1
    return False


def _is_retryable_alone(profile: DialectProfile, exc: BaseException) -> bool:
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
    # Inline: a bare one-row insert would pick up the dialect's implicit
    # OUTPUT/RETURNING of the identity key, a pending result per array row.
    compiled = insert(table).inline().values({name: bindparam(name) for name in names}).compile(dialect=dialect)
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
