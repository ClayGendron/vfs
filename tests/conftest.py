"""Shared test helpers for Grover v2 tests."""

from __future__ import annotations

import os
import subprocess
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from grover.backends.database import DatabaseFileSystem
from grover.backends.mssql import MSSQLFileSystem
from grover.base import GroverFileSystem
from grover.models import GroverObjectBase
from grover.results import Candidate

if TYPE_CHECKING:
    from grover.results import GroverResult

# ------------------------------------------------------------------
# --postgres / --mssql CLI flags
# ------------------------------------------------------------------

_PG_DB = "grover_test"
_PG_URL = f"postgresql+asyncpg://localhost/{_PG_DB}"

_MSSQL_DEFAULT_URL = (
    "mssql+aioodbc://sa:Strong!Passw0rd@localhost:1433/grover_test"
    "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="Run database tests against a local PostgreSQL instance instead of SQLite.",
    )
    parser.addoption(
        "--mssql",
        action="store_true",
        default=False,
        help=(
            "Run database tests against a local SQL Server / Azure SQL instance "
            "instead of SQLite. Override the connection URL with GROVER_MSSQL_URL."
        ),
    )
    parser.addoption(
        "--scale",
        type=int,
        default=1_000,
        help="Row count for batch/pressure tests (default: 1000).",
    )


# ------------------------------------------------------------------
# Database fixtures (shared by test_database.py, test_write_pressure.py)
# ------------------------------------------------------------------


async def _provision_mssql_fulltext(eng) -> None:
    """Test-only: provision the full-text index that ``MSSQLFileSystem`` requires.

    Production code never creates these — they're a deployment concern.
    Tests need them to exercise the CONTAINSTABLE / REGEXP_LIKE paths,
    so the fixture provisions them after ``create_all``.

    Idempotent and uses AUTOCOMMIT — full-text DDL on SQL Server cannot
    run inside a user transaction.

    Full-text key index: we use the table's primary key (on ``id``, a
    36-char UUID string = 72 bytes) rather than the unique index on
    ``path`` (NVARCHAR(4096) = 8192 bytes declared max). SQL Server's
    Full-Text Search rejects any key index whose column's declared max
    size exceeds 900 bytes, and that limit is on the schema definition,
    not the actual row data. The ``id`` PK satisfies all five FTS key
    requirements (unique, non-null, single-column, deterministic, ≤900
    bytes) out of the box, and ``MSSQLFileSystem`` joins ``CONTAINSTABLE``
    results back to the table on ``o.id = ct.[KEY]`` to match.
    """
    from sqlalchemy import text

    from grover.models import GroverObject

    table = GroverObject.__tablename__
    catalog = "grover_test_ftcat"

    async with eng.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        pk_row = (
            await conn.execute(
                text(f"""
                SELECT name FROM sys.indexes
                WHERE object_id = OBJECT_ID(N'{table}')
                  AND is_primary_key = 1
                """)
            )
        ).first()
        if pk_row is None:
            msg = f"No primary key index found on {table}; cannot provision FTS"
            raise RuntimeError(msg)
        key_index = pk_row[0]

        await conn.execute(
            text(f"""
            IF NOT EXISTS (
                SELECT 1 FROM sys.fulltext_catalogs WHERE name = '{catalog}'
            )
            CREATE FULLTEXT CATALOG {catalog}
            """)
        )
        await conn.execute(
            text(f"""
            IF NOT EXISTS (
                SELECT 1 FROM sys.fulltext_indexes
                WHERE object_id = OBJECT_ID(N'{table}')
            )
            CREATE FULLTEXT INDEX ON {table}(content LANGUAGE 1033)
            KEY INDEX {key_index}
            ON {catalog}
            WITH CHANGE_TRACKING AUTO
            """)
        )


@pytest.fixture
async def engine(request: pytest.FixtureRequest):
    use_pg = request.config.getoption("--postgres")
    use_mssql = request.config.getoption("--mssql")
    if use_pg and use_mssql:
        msg = "--postgres and --mssql are mutually exclusive"
        raise pytest.UsageError(msg)

    if use_pg:
        subprocess.run(["createdb", _PG_DB], check=False)
        eng = create_async_engine(_PG_URL)
    elif use_mssql:
        url = os.environ.get("GROVER_MSSQL_URL", _MSSQL_DEFAULT_URL)
        eng = create_async_engine(url)
    else:
        eng = create_async_engine(
            "sqlite+aiosqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    if use_mssql:
        await _provision_mssql_fulltext(eng)

    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await eng.dispose()

    if use_pg:
        subprocess.run(["dropdb", _PG_DB], check=False)


@pytest.fixture
async def db(request: pytest.FixtureRequest, engine):
    if request.config.getoption("--mssql"):
        return MSSQLFileSystem(engine=engine)
    return DatabaseFileSystem(engine=engine)


@pytest.fixture
def scale(request: pytest.FixtureRequest) -> int:
    """Row count for batch/pressure tests. Override with ``--scale 100000``."""
    return request.config.getoption("--scale")


class DummySession:
    """Minimal session stub that tracks commit/rollback calls."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def dummy_session_factory():
    """Return an async-context-manager that yields a fresh DummySession."""

    @asynccontextmanager
    async def _factory():
        yield DummySession()

    return _factory


def tracking_session_factory():
    """Return (factory, sessions_list) where sessions_list collects every session created."""
    sessions: list[DummySession] = []

    @asynccontextmanager
    async def _factory():
        s = DummySession()
        sessions.append(s)
        yield s

    return _factory, sessions


def candidate(path: str, *, content: str | None = None) -> Candidate:
    """Create a minimal Candidate for test assertions."""
    return Candidate(path=path, content=content)


def make_fs(name: str = "test") -> GroverFileSystem:
    """Create a GroverFileSystem with a dummy session factory for routing tests."""
    from unittest.mock import AsyncMock

    fs = GroverFileSystem(session_factory=AsyncMock())
    fs._name = name
    return fs


def require_file(result: GroverResult) -> Candidate:
    """Return the first candidate, asserting it exists for type narrowing."""
    assert result.file is not None
    return result.file


def require_object[T: GroverObjectBase](obj: T | None) -> T:
    """Assert an object exists and return the narrowed value."""
    assert obj is not None
    return obj


def require_text(text: str | None) -> str:
    """Assert a text field is present and return the narrowed value."""
    assert text is not None
    return text


def set_parameter_budget(db: DatabaseFileSystem, fallback: int) -> None:
    """Override the budget on one test instance without touching the class type."""
    cast("Any", db).DIALECT_PARAMETER_BUDGETS = {}
    db.PARAMETER_BUDGET_FALLBACK = fallback
