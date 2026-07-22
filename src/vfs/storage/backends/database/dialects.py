"""Per-dialect policy — the decisions SQLAlchemy deliberately leaves to us.

Facts SQLAlchemy models are read off the live ``Dialect`` object, never
copied here: the parameter budget is ``dialect.insertmanyvalues_max_parameters``
(SQLAlchemy trusts it for its own insert batching on every dialect), and
transport-down classification is ``dialect.is_disconnect()``.  What this
module declares is only what SQLAlchemy takes no position on: retryable
SQLSTATEs, connection/file settings, isolation pins, index-key byte
budgets, and create-arbitration mode.

Known engines (sqlite, postgresql, mssql) carry tuned policy; **any other
SQLAlchemy dialect resolves to a conservative generic profile** — the
backend runs on any SQLAlchemy-compatible database, degrading to safe
defaults rather than refusing.

    profile = profile_for(engine.dialect.name)
    if is_retryable(profile, exc): ...

Retryability is classified by SQLSTATE / SQLite extended error code only,
never by message text.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

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
    """

    name: str
    key_byte_budget: int
    in_list_budget: int
    arbitration: Literal["upsert", "catch_retry"]
    op_isolation: str | None = None
    topology_isolation: str | None = None
    session_settings: tuple[str, ...] = ()
    file_settings: tuple[str, ...] = ()
    retryable_sqlstates: frozenset[str] = frozenset({"40001", "40P01"})
    retryable_sqlite_codes: frozenset[int] = frozenset()


SQLITE: Final = DialectProfile(
    name="sqlite",
    key_byte_budget=4_096,
    in_list_budget=32_766,
    arbitration="upsert",
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
    op_isolation="REPEATABLE READ",
    topology_isolation="READ COMMITTED",
)

MSSQL: Final = DialectProfile(
    name="mssql",
    key_byte_budget=1_700,
    in_list_budget=2_100,
    arbitration="catch_retry",
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


# ---------------------------------------------------------------------------
# Statement chunking — membership predicates never outgrow an engine
# ---------------------------------------------------------------------------

# Bind params held back from each membership chunk for a statement's
# fixed predicates (the liveness filter, projection, depth caps).
_FILTER_BIND_RESERVE: Final = 32


def membership_budget(profile: DialectProfile, parameter_budget: int) -> int:
    """Elements per ``IN``-list chunk: the element cap net of fixed binds.

    Every membership predicate (``path IN``, ``id IN``, glob's anchor
    fan) chunks by this and merges results, so batch size never reaches
    an engine limit — the ETL contract that 10,000+-entry batches serve
    on every dialect.
    """
    return max(1, min(profile.in_list_budget, parameter_budget - _FILTER_BIND_RESERVE))


def chunked[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Slices of *items* at most *size* long, in order."""
    step = max(1, size)
    for index in range(0, len(items), step):
        yield items[index : index + step]


def rows_per_statement(parameter_budget: int, rows: Sequence[Mapping[str, object]]) -> int:
    """Rows one multi-row statement may carry: the budget over the widest row.

    The floor of one row keeps a pathological budget (narrower than a
    single row) making progress instead of stalling ``chunked``.
    """
    return max(1, parameter_budget // max(len(row) for row in rows))


# ---------------------------------------------------------------------------
# Retryable-error classification
# ---------------------------------------------------------------------------


def is_retryable(profile: DialectProfile, exc: BaseException) -> bool:
    """Whether *exc* is a transient outcome a whole-method restart can clear.

    Classifies by SQLite extended error code or SQLSTATE, never message
    text. Unique violations (23505) are definite exists-outcomes after
    arbitration and are never in any profile's retryable set.
    """
    origin = getattr(exc, "orig", None) or exc
    sqlite_code = getattr(origin, "sqlite_errorcode", None)
    if sqlite_code is not None:
        return sqlite_code in profile.retryable_sqlite_codes
    return _sqlstate_of(origin) in profile.retryable_sqlstates


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
