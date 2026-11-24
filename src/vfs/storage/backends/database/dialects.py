"""Per-dialect policy — the decisions SQLAlchemy deliberately leaves to us.

Facts SQLAlchemy models are read off the live ``Dialect`` object, never
copied here: the parameter budget is ``dialect.insertmanyvalues_max_parameters``
(SQLAlchemy trusts it for its own insert batching on every dialect), and
transport-down classification is ``dialect.is_disconnect()``.  What this
module declares is only what SQLAlchemy takes no position on: retryable
SQLSTATEs, connection/file settings, isolation pins, index-key byte
budgets, create-arbitration mode, the shared-lock spelling, and the
vector-distance facts.

The two supported engines, sqlite and postgresql, carry tuned policy;
**any other SQLAlchemy dialect resolves to a conservative generic
profile** — the backend serves it the core verbs, degrading to safe
defaults rather than refusing, and withholds the ranked verbs the floor
cannot vouch for. No engine leg tests the floor; it is fit for testing.

    profile = profile_for(engine.dialect.name)
    if is_retryable(profile, exc): ...

Retryability is classified by SQLSTATE or SQLite extended error code —
never by message text.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, TypeVar, cast

from sqlalchemy import Table, bindparam, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import ColumnDefault

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from sqlalchemy import Select
    from sqlalchemy.dialects.postgresql import Insert as PostgresInsert
    from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
    from sqlalchemy.engine import Dialect
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ClauseElement
    from sqlalchemy.sql.compiler import SQLCompiler

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
VectorDistance = Literal["none", "exact", "ann"]
RangeSource = Literal["json_each", "unnest"]

RELABEL_ROWS: Final = 50_000
"""Entry rows per relabel chunk, the default every profile declares: the
bound measured safe on every engine vfs has run (see ``relabel_rows``)."""

# Bytes of body per bulk blob statement: every engine holds the page in client memory.
BLOB_PAGE_BYTES: Final = 8 * 1024 * 1024


class VectorFunction(NamedTuple):
    """An engine's cosine distance function as a precondition: proved, named, and installed only on request.

    ``probe`` is the statement that proves the function is present; it
    fails when the engine raises a permanent error or answers no row,
    and a scalar answer is read as the function's version. ``missing``
    is the fix the refusal names when the probe fails. ``install`` is
    the statement the explicit ``install_extensions`` verb runs where a
    sufficiently privileged role could install the function, and
    ``None`` where nothing is installable. Grouping the three keeps a
    probe from refusing with no fix named and an install from
    succeeding with nothing proved.
    """

    probe: str
    missing: str
    install: str | None = None


class ShareLock(NamedTuple):
    """How a mint shares the lock on the everyone stamp, which a posture write takes whole.

    ``form`` is ``"row"`` for a shared row lock and ``"exclusive"`` for the floor's
    ``FOR UPDATE``. ``door`` has a posture write lock the table first, where a later
    sharer would otherwise pass it.
    """

    form: Literal["row", "exclusive"] = "row"
    door: bool = False


ROW_SHARE: Final = ShareLock()


@dataclass(frozen=True)
class DialectProfile:
    """One engine's declared policy.

    ``key_byte_budget`` caps index-key bytes on path/name columns (a
    lawful path over it classifies at the backend); ``in_list_budget``
    caps elements per ``IN`` expression list — a limit SQLAlchemy does
    not model and some engines enforce independently of bind-parameter
    count (the generic floor's 1,000 is the tightest vfs has met);
    ``arbitration`` names how concurrent create resolves (native upsert
    vs catch-and-retry — the portable fallback). ``session_settings``
    run at every checkout of a connection (state that each connection
    must carry); ``file_settings`` run once at first
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
    the spelling) but takes no position on acceptance: some engines have
    no row constructors in ``IN``, and the generic floor claims nothing.

    ``content_bytes`` declares that casting the content column to the
    engine's bytes type returns exactly the column's UTF-8 bytes, cheaply
    — true where TEXT is stored as UTF-8 and the cast is a
    reinterpretation (sqlite: TEXT and BLOB share storage). Grep fetches
    bodies as bytes where declared, skipping the driver's decode and the
    matcher seam's re-encode; everywhere else bodies stay ``str``. Never
    declare it where the cast transcodes or where the database character
    set may not be UTF-8 — wrong bytes match nothing, silently.

    ``bulk_insert`` declares how a bulk insert reaches the engine —
    ``"core"`` (SQLAlchemy's executemany, paged as multirow statements),
    ``"driver"`` (the DBAPI's own executemany on the session's
    connection), or ``"copy"`` (asyncpg's binary ``COPY`` of records on
    that connection). Which one wins is a per-driver fact SQLAlchemy
    takes no position on (asyncpg pipelines one execute per row but
    streams a COPY; sqlite3 has no round trips to lose), so the value is
    read from the bulk-insert benchmark and the engine legs; the generic
    floor never assumes an unknown driver's executemany is a batch.

    ``vector_distance`` declares the engine's server-side cosine:
    ``exact`` (a distance function, no usable ANN index — SQLite through
    the sqlite-vec extension vfs loads), ``ann`` (a distance function and
    an index the planner may use — pgvector), or ``none`` — only the
    generic floor, which therefore serves no ranked verb. Facts
    SQLAlchemy takes no position on. ``ann_honours_scope`` declares that
    a scoped query can still use the ANN index.

    ``range_source`` declares the table function that unpacks one bound
    list of path ranges into rows, so a partial caller's rights join the
    ``path`` index with statement text that never changes with its
    grants: ``json_each`` (SQLite) or ``unnest`` of arrays (Postgres).
    SQLAlchemy takes no position on it. ``None`` keeps the literal OR of
    pieces — the generic floor.

    ``range_join`` declares the join keyword between the unpacked
    ranges and the entry table in a range branch — SQLAlchemy models
    only ``JOIN`` and its outer forms. Measured with the everyone level
    on the row: SQLite's planner otherwise seeks ``everyone_level < :r``
    on the composite index and scans the ranges per row (90 ms against
    1 ms at 1,000 users), so it takes ``CROSS JOIN`` with the ranges
    driving; Postgres plans the plain ``JOIN`` correctly.
    ``range_settings`` are statements issued in the
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
    on Postgres.

    ``share_lock`` declares the shared lock a mint proves its label under
    (:class:`ShareLock`).

    ``guard_miss`` declares what a zero-row guarded UPDATE means on this
    engine — knowledge SQLAlchemy takes no position on. ``reprobe``:
    reads and guarded updates judge the same committed state, so a
    re-probe of the missed row classifies the miss honestly
    (``not_found`` vs ``conflict``). ``redrive``: the two disagree — an
    UPDATE that current-reads past the snapshot the probe would report —
    so the only honest move is :class:`StaleSnapshot`, retrying the
    whole method from fresh state. The generic floor declares
    ``redrive``: never classify off a probe an unknown engine may
    contradict.

    ``relabel_rows`` caps the entry rows one relabel chunk rewrites — a
    posture change's ``UPDATE`` over its subtree, one chunk per
    transaction. SQLAlchemy models no such thing: the bind budgets bound
    a statement's text, not the rows it touches, and what this bounds is
    the time one chunk holds its row locks and the admin lock, so a
    posture change over millions of rows never parks every reader and
    rival admin write behind one transaction. 50,000 rows per statement,
    one transaction per statement, was measured safe on every engine
    vfs has run, and is kept until it is measured on Postgres alone;
    the value is the same on every profile because no engine measured a
    reason to differ.

    ``vector_function`` declares the engine's cosine distance function
    as a precondition first touch proves and never installs on its own:
    the probe statement, the fix a refusal names, and the statement the
    explicit ``install_extensions`` verb runs where a sufficiently
    privileged role could install it. A mount whose probe fails refuses
    ``unavailable`` naming the fix. SQLite probes sqlite-vec (loaded on
    every connection, missing only where the interpreter cannot load
    extensions) and PostgreSQL probes the pgvector catalog row, with
    pgvector's ``CREATE EXTENSION`` as the install. The generic floor
    declares none.

    ``scope_facts_beside_fan`` declares that the engine keeps an
    index-served OR of scope root clauses (each a strict-descendant
    ``LIKE`` on the path index) when one OR of the arms' leaf-name and
    extension facts rides beside it as a conjunct — a plan-quality fact
    SQLAlchemy takes no position on, and one a planner could break by
    making the facts the access path. A profile declares it only where
    the engine's two plan pins pass on a store with statistics (the
    roots-alone statement and the statement with the facts beside it,
    each read by plan operator on the path index); elsewhere the scope
    fan sends the roots alone, fetching more candidates and the same rows.

    ``statistics_listing`` declares the engine's own growth check for
    planner statistics, which the engine host runs inside every committed
    mutation and acts on in one background pass: SQLite's ``PRAGMA
    optimize`` listing with the check-every-table, consider-``ANALYZE``
    and list-only bits set and no cap bit, formatted with the quoted
    schema the mount's tables live in. SQLAlchemy takes no position on
    maintaining statistics, and Postgres needs none of ours: its
    autovacuum analyzes a table after 50 rows plus a tenth of it change
    and scales stored estimates to the live size. So only SQLite fills
    it, and the generic floor runs no step. The pass holds the write
    lock for one crossing's analysis, measured at 0.9 to 1.5 s at a
    million entry rows and about 9 to 15 s inferred at ten million,
    once per sevenfold to tenfold growth; past about five million rows
    a rival writer may need a second attempt during it, and the named
    direction, one table per pass above a declared size, has no cap.

    ``rarity_hint`` names the engine's planner hint for a term that is
    rarely true, a function wrapping the term that costs nothing to
    evaluate — SQLite's ``unlikely()``. The overlay fetch's ``NOT
    encoded`` term takes it where it is declared: ``sqlite_stat1`` keeps
    one average per index column and cannot say that the rows awaiting
    the index are few among the many encoded ones, so with statistics
    the planner would walk the path index for them, linear in the store,
    where the hint keeps the seek on the (encoded, kind) index. The
    server engines keep the plain term; a partial index over the rows
    awaiting the index is the direction that serves every engine.

    ``probe_entry_filter`` declares that a keyset page over the chunk
    table spells its entry filter as a correlated probe on the entry
    table, a scalar subquery compared to a constant, instead of a join
    — a plan-shape fact SQLAlchemy takes no position on. SQLite's
    planner, given statistics and several chunks per entry, puts a Bloom
    filter on the join's entry side, sized by an estimate that ignores
    the ``LIMIT`` and rebuilt over every entry row on each execution, so
    a scan of many pages pays a cost that grows with the entry count on
    every page; the probe is one unique-index lookup per chunk row and
    builds nothing. Postgres keeps the join: it was measured to serve it
    as a memoized index probe and to JIT-compile the probe into a
    regression. A SQLite planner that took the ``LIMIT`` into its filter
    estimate would let the join come back.

    ``live_index_hint`` is the table hint, ``{index}`` in it the index's
    name, that holds a live listing page to the partial index over the
    live rows — a plan pin SQLAlchemy takes no position on. SQLite's
    planner costs that index by its statistics, and a delete changes no
    row count, so the statistics vfs keeps are not refreshed by one: after
    a mass delete they still count the tombstones in the live index, and
    the planner then reads the full path index with every tombstone in
    the page's range. Postgres takes no hint and keeps its own statistics,
    through autovacuum, which counts a tombstone as a change. SQLAlchemy's
    SQLite compiler drops every table hint, so :func:`_indexed_by` renders
    this one, and only an ``INDEXED BY`` hint.

    ``attempts_out_of_reach`` declares that a try of a call's transaction
    runs out of its caller's reach, because SQLAlchemy throws away a
    connection a cancellation reached: on SQLite, the database or its lock.
    """

    name: str
    key_byte_budget: int
    in_list_budget: int
    arbitration: Literal["upsert", "catch_retry"]
    guard_miss: Literal["reprobe", "redrive"] = "redrive"
    share_lock: ShareLock = ROW_SHARE
    op_isolation: str | None = None
    topology_isolation: str | None = None
    session_settings: tuple[str, ...] = ()
    file_settings: tuple[str, ...] = ()
    retryable_sqlstates: frozenset[str] = frozenset({"40001", "40P01"})
    retryable_sqlite_codes: frozenset[int] = frozenset()
    expression_depth_budget: int = 1_000
    values_join: bool = False
    tuple_in: bool = False
    content_bytes: bool = False
    bulk_insert: BulkInsertMode = "core"
    vector_distance: VectorDistance = "none"
    ann_honours_scope: bool = False
    range_source: RangeSource | None = None
    range_join: str = "JOIN"
    range_settings: tuple[str, ...] = ()
    range_fence: str | None = None
    relabel_rows: int = RELABEL_ROWS
    vector_function: VectorFunction | None = None
    scope_facts_beside_fan: bool = False
    statistics_listing: str | None = None
    rarity_hint: str | None = None
    probe_entry_filter: bool = False
    live_index_hint: str | None = None
    # The ``sqlalchemy.func`` name that sizes a stored body without reading it, which SQLAlchemy does not model:
    # encoding bytes on Postgres, characters elsewhere (the floor's ``length``).
    stored_length: str = "length"
    attempts_out_of_reach: bool = False


SQLITE_VEC_PROBE: Final = "SELECT vec_version()"
"""Proves sqlite-vec is loaded in the connection; its answer is the extension's version."""

PGVECTOR_ITERATIVE_SCAN: Final = "SET LOCAL hnsw.iterative_scan = relaxed_order"
"""pgvector 0.8+: keep scanning the HNSW index until a scoped query's window fills."""

PGVECTOR_PROBE: Final = "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
"""Proves pgvector is installed in the database; no row means it is not, and the answer is its version."""


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
        # Uncapped: a sampled analysis understates the low-cardinality columns the trap is about.
        "PRAGMA analysis_limit = 0",
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
    vector_function=VectorFunction(
        probe=SQLITE_VEC_PROBE,
        missing=(
            "sqlite-vec did not load: this interpreter's sqlite3 cannot load extensions "
            "(enable_load_extension is missing); use a Python built with extension loading"
        ),
    ),
    range_source="json_each",
    range_join="CROSS JOIN",
    range_fence="MATERIALIZED",
    # Plan-pinned: after ANALYZE every root clause still seeks the path index with the facts beside the OR.
    scope_facts_beside_fan=True,
    # Every table checked, ANALYZE considered, list only, no cap bit: SQLite names what grew tenfold.
    statistics_listing="PRAGMA {schema}.optimize = 0x10003",
    rarity_hint="unlikely",
    # Plan-pinned: the chunk pages' entry probe plans no per-page Bloom filter where the join builds one.
    probe_entry_filter=True,
    # Plan-pinned: a live listing page reads its partial index on statistics that predate a mass delete.
    live_index_hint="INDEXED BY {index}",
    attempts_out_of_reach=True,
)

POSTGRESQL: Final = DialectProfile(
    name="postgresql",
    key_byte_budget=2_704,
    in_list_budget=65_535,
    arbitration="upsert",
    guard_miss="reprobe",
    share_lock=ShareLock(door=True),
    op_isolation="REPEATABLE READ",
    topology_isolation="READ COMMITTED",
    values_join=True,
    tuple_in=True,
    # asyncpg pipelines one execute per row; binary COPY halves Core's pages (4.3 vs 9.1 µs).
    bulk_insert="copy",
    vector_distance="ann",
    # pgvector is a precondition first touch never installs: it is an
    # untrusted extension, so CREATE EXTENSION takes a superuser.
    vector_function=VectorFunction(
        probe=PGVECTOR_PROBE,
        missing=(
            "the pgvector extension is not installed in this database; run "
            "CREATE EXTENSION vector once as a superuser (pgvector is not a trusted "
            "extension; on a managed server, the provider's privileged role, e.g. "
            "rds_superuser or cloudsqlsuperuser), or call install_extensions() under one"
        ),
        install="CREATE EXTENSION IF NOT EXISTS vector",
    ),
    range_source="unnest",
    range_settings=("SET LOCAL jit = off",),
    ann_honours_scope=True,
    # Plan-pinned: a BitmapOr of path-index scans with the facts beside the OR, as without them.
    scope_facts_beside_fan=True,
    stored_length="octet_length",
)

# The floor for every other engine: the tightest key and IN-list caps vfs
# has met, no settings, serialization-failure SQLSTATEs only.
GENERIC: Final = DialectProfile(
    name="generic",
    key_byte_budget=1_700,
    in_list_budget=1_000,
    arbitration="catch_retry",
    share_lock=ShareLock(form="exclusive"),
)

PROFILES: Final[dict[str, DialectProfile]] = {
    SQLITE.name: SQLITE,
    POSTGRESQL.name: POSTGRESQL,
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


def lock_rows(stmt: Select[_Row]) -> Select[_Row]:
    """*stmt* as a locking read of the rows it selects, held to the transaction's end.

    The liveness proof every guard rests on: a row read through here
    cannot be rewritten or deleted by a rival before this transaction
    commits, so the caller's decision stands on the row it read. Spelled
    ``FOR UPDATE``, which SQLite's compiler renders as nothing, lawfully:
    the writer transaction is the lock there. Callers order the rows they
    lock (sorted keys, chunked) so rival batches lock in one order; a
    deadlock against a verb with its own claim order classifies retryable
    and rides the retry channel.
    """
    return stmt.with_for_update()


# ---------------------------------------------------------------------------
# Statement chunking — membership predicates never outgrow an engine
# ---------------------------------------------------------------------------

# Bind params held back from each membership chunk for a statement's
# fixed predicates (the liveness filter, projection, depth caps).
_FILTER_BIND_RESERVE: Final = 32

# Depth units held back from each OR-fan chunk for the fixed predicates AND-chained above the fan.
EXPRESSION_DEPTH_RESERVE: Final = 64


def membership_budget(profile: DialectProfile, parameter_budget: int) -> int:
    """Elements per ``IN``-list chunk: the element cap net of fixed binds.

    Every membership predicate (``path IN``, ``id IN``) chunks by this
    and merges results, so batch size never reaches an engine limit —
    the ETL contract that 10,000+-entry batches serve on every dialect.
    """
    return max(1, min(profile.in_list_budget, parameter_budget - _FILTER_BIND_RESERVE))


# Measured OR-fan sweet spot: the win saturates by ~200 arms/statement,
# and 200 clears SQLite's expression depth of 1,000.
_PATTERN_ARM_CEILING: Final = 200


def arm_budget(profile: DialectProfile, parameter_budget: int, arm_binds: int) -> int:
    """Pattern arms per glob OR-fan chunk: the tightest cap, floored at one.

    Each arm spends *arm_binds* bind slots and roughly one depth unit in
    the left-deep ``OR`` chain (the arm's own conjuncts ride under the
    depth reserve). The measured ceiling binds before either engine cap
    on every profiled dialect.
    """
    by_binds = membership_budget(profile, parameter_budget) // max(1, arm_binds)
    by_depth = profile.expression_depth_budget - EXPRESSION_DEPTH_RESERVE
    return max(1, min(_PATTERN_ARM_CEILING, by_binds, by_depth))


# Spelled pre-PEP-695: type-parameter syntax is 3.12+, above the floor.
T = TypeVar("T")


def chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
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


# Bind slots held back from every measured multi-row statement: room
# under the bind cap for a driver's own parameters.
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

# Compiled once per (dialect facts, table shape, key set): the key holds
# strings only, so no mount's metadata is ever retained by this cache.
_BulkKey = tuple[str, str, str, str | None, str, tuple[tuple[str, str], ...], tuple[str, ...]]
_BULK_STATEMENTS: dict[_BulkKey, _BulkStatement] = {}


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


def upsert_constructor(profile: DialectProfile) -> Callable[[Table], SQLiteInsert | PostgresInsert]:
    """The dialect's ``ON CONFLICT`` insert — only upsert-arbitration engines get here."""
    return sqlite_insert if profile.name == "sqlite" else pg_insert


# ---------------------------------------------------------------------------
# Retryable-error classification
# ---------------------------------------------------------------------------


# ISO 9075's vendor catch-all: it says "look elsewhere", so it classifies nothing.
_SQLSTATE_GENERAL_ERROR: Final = "HY000"

# A unique-key violation by each driver's own code: SQLite's extended codes, and the standard's SQLSTATE.
_SQLITE_UNIQUE_CODES: Final = frozenset({2067, 1555})
_SQLSTATE_UNIQUE_VIOLATION: Final = "23505"

# Exception-context links walked for a transient cause behind an unwind error.
_UNWIND_DEPTH: Final = 4


def driver_origin(exc: BaseException) -> BaseException:
    """The driver exception behind a SQLAlchemy wrapper, or *exc* itself when it is not wrapped.

    SQLAlchemy's ``DBAPIError`` carries the driver's exception as
    ``orig``; the codes every classifier here reads, and the message a
    refusal shows, live on that object. Idempotent: a driver exception
    is its own origin.
    """
    origin = getattr(exc, "orig", None)
    return origin if isinstance(origin, BaseException) else exc


def is_retryable(profile: DialectProfile, exc: BaseException) -> bool:
    """Whether *exc* is a transient outcome a whole-method restart can clear.

    Classifies by SQLite extended error code or SQLSTATE — never message
    text. A ``HY000`` SQLSTATE carries no classification by definition.
    Unique violations (23505) are definite exists-outcomes after
    arbitration and are never in any profile's retryable set. An error
    raised while *unwinding* from a retryable one is retryable too: a
    deadlock aborts the whole transaction, so the savepoint release that
    follows fails with its own error, and the transient cause sits one
    link down the exception's context chain.
    """
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < _UNWIND_DEPTH:
        if _is_retryable_alone(profile, current):
            return True
        current = current.__context__
        seen += 1
    return False


def is_unique_violation(exc: BaseException) -> bool:
    """Whether *exc* is a unique-key violation, told from every other integrity failure by the driver's code.

    SQLite's extended code; else the SQLSTATE. A driver that reports only
    the bare integrity class, or an integer error number, is not read as
    one.
    """
    origin = driver_origin(exc)
    if (sqlite_code := getattr(origin, "sqlite_errorcode", None)) is not None:
        return sqlite_code in _SQLITE_UNIQUE_CODES
    return _sqlstate_of(origin) == _SQLSTATE_UNIQUE_VIOLATION


def _is_retryable_alone(profile: DialectProfile, exc: BaseException) -> bool:
    origin = driver_origin(exc)
    sqlite_code = getattr(origin, "sqlite_errorcode", None)
    if sqlite_code is not None:
        return sqlite_code in profile.retryable_sqlite_codes
    state = _sqlstate_of(origin)
    return state is not None and state != _SQLSTATE_GENERAL_ERROR and state in profile.retryable_sqlstates


def is_value_too_large(exc: BaseException) -> bool:
    """Whether *exc* reports one value past the engine's single-value cap.

    SQLite raises ``DataError`` for a string or blob over its length
    limit; SQLSTATE class 54 is the program-limit class. By code and
    type, never message text.
    """
    origin = driver_origin(exc)
    if isinstance(origin, sqlite3.DataError):
        return True
    state = _sqlstate_of(origin)
    return state is not None and state[:2] == _SQLSTATE_LIMIT_CLASS


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
    state = _sqlstate_of(driver_origin(exc))
    if state is not None and state[:2] in _SQLSTATE_DEFECT_CLASSES:
        return True
    return isinstance(exc, ProgrammingError)


def is_insufficient_privilege(exc: BaseException) -> bool:
    """Whether *exc* reports that the connected role may not do what the statement asked.

    SQLSTATE 42501 is the standard's insufficient-privilege code, the one
    ``CREATE EXTENSION`` raises for a role that is not a superuser when
    the extension is untrusted, as pgvector is. Checked before the defect
    classes: 42501 sits in class 42, and a privilege refusal is the
    caller's condition to fix, never a vfs bug. Takes the SQLAlchemy
    wrapper or the driver exception alike.
    """
    return _sqlstate_of(driver_origin(exc)) == _SQLSTATE_INSUFFICIENT_PRIVILEGE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@compiles(Table, "sqlite")
def _indexed_by(element: Table, compiler: SQLCompiler, **kw: Any) -> str:
    """A table in a FROM clause on SQLite, with the ``INDEXED BY`` hint a statement declares for it.

    SQLAlchemy hands each table its hint and its SQLite compiler renders
    none. This renders an ``INDEXED BY`` hint, the one ``live_index_hint``
    declares, and still drops every other, so a table renders as before
    unless a statement pins it.
    """
    text = compiler.visit_table(element, **kw)
    hint = (kw.get("fromhints") or {}).get(element)
    return f"{text} {hint}" if kw.get("asfrom") and isinstance(hint, str) and hint.startswith("INDEXED BY ") else text


# ISO 9075 classes 42 (syntax/access-rule violation) and 07 (dynamic
# SQL error): the statement itself is defective, never transient.
_SQLSTATE_DEFECT_CLASSES: Final = frozenset({"42", "07"})
_SQLSTATE_LIMIT_CLASS: Final = "54"
_SQLSTATE_INSUFFICIENT_PRIVILEGE: Final = "42501"


# SQLSTATE codes are exactly five characters (ISO/IEC 9075).
_SQLSTATE_LENGTH: Final = 5


def _sqlstate_of(origin: object) -> str | None:
    """The SQLSTATE of a driver exception, if it carries one.

    asyncpg and psycopg expose ``sqlstate``, psycopg2 ``pgcode``; a
    driver may instead put the SQLSTATE (not text) first in ``args``, as
    pyodbc does, and that convention is read for any driver.
    """
    state = getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None)
    if isinstance(state, str):
        return state
    first = next(iter(getattr(origin, "args", ())), None)
    if isinstance(first, str) and len(first) == _SQLSTATE_LENGTH:
        return first
    return None


def _bulk_statement(dialect: Dialect, table: Table, keys: tuple[str, ...]) -> _BulkStatement:
    shape = tuple((column.key, repr(column.type)) for column in table.columns)
    cache_key = (dialect.name, dialect.driver, dialect.paramstyle, table.schema, table.name, shape, keys)
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
