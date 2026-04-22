"""Shared test helpers for VFS v2 tests."""

from __future__ import annotations

import os
import re
import subprocess
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import event
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from vfs.backends.database import DatabaseFileSystem
from vfs.backends.mssql import MSSQLFileSystem
from vfs.backends.postgres import PostgresFileSystem
from vfs.base import VirtualFileSystem
from vfs.models import VFSObjectBase, postgres_native_vfs_object_model, postgres_vector_column_spec
from vfs.results import Entry

if TYPE_CHECKING:
    from vfs.results import VFSResult

# ------------------------------------------------------------------
# --postgres / --mssql CLI flags
# ------------------------------------------------------------------

_PG_DB = "vfs_test"
_PG_URL = f"postgresql+asyncpg://localhost/{_PG_DB}"
_PG_NATIVE_VECTOR_DIM = 4

_MSSQL_DEFAULT_URL = (
    "mssql+aioodbc://sa:Strong!Passw0rd@localhost:1433/vfs_test"
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

    from vfs.models import VFSObject

    table = VFSObject.__tablename__
    catalog = "vfs_test_ftcat"

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


async def _provision_postgres_fulltext(eng, *, table: str = "vfs_objects") -> None:
    """Test-only: provision the native Postgres search artifacts."""
    async with eng.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(
            sql_text(
                f"""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(content, ''))
                ) STORED
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_search_tsv_gin
                ON {table} USING GIN (search_tsv)
                WHERE content IS NOT NULL
                  AND deleted_at IS NULL
                  AND kind != 'version'
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_path_pattern
                ON {table} (path text_pattern_ops)
                WHERE deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_path_trgm_gin
                ON {table} USING GIN (path gin_trgm_ops)
                WHERE deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_content_trgm_gin
                ON {table} USING GIN (content gin_trgm_ops)
                WHERE kind = 'file'
                  AND content IS NOT NULL
                  AND deleted_at IS NULL
                """
            )
        )


async def _provision_postgres_native_search(eng, model: type[VFSObjectBase]) -> None:
    """Recreate ``vfs_objects`` with a native vector column and indexes."""
    spec = postgres_vector_column_spec(model)
    async with eng.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(sql_text(f"DROP TABLE IF EXISTS {model.__tablename__} CASCADE"))
        await conn.run_sync(model.metadata.create_all)
    await _provision_postgres_fulltext(eng, table=model.__tablename__)
    async with eng.begin() as conn:
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS {spec.index_name}
                ON {model.__tablename__} USING {spec.index_method}
                ({spec.column_name} {spec.operator_class})
                WHERE {spec.column_name} IS NOT NULL
                """
            )
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

    if use_pg:
        await _provision_postgres_fulltext(eng)
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
        fs = MSSQLFileSystem(engine=engine)
        await fs.install_native_graph_schema()
        return fs
    return DatabaseFileSystem(engine=engine)


@pytest.fixture
def postgres_vector_dimension() -> int:
    return _PG_NATIVE_VECTOR_DIM


@pytest.fixture
async def postgres_native_db(request: pytest.FixtureRequest, engine, postgres_vector_dimension: int):
    if not request.config.getoption("--postgres"):
        pytest.skip("requires --postgres flag and a running PostgreSQL instance")
    model = postgres_native_vfs_object_model(dimension=postgres_vector_dimension)
    await _provision_postgres_native_search(engine, model)
    fs = PostgresFileSystem(engine=engine, model=model)
    await fs.install_native_graph_schema()
    return fs


@pytest.fixture
async def postgres_legacy_db(request: pytest.FixtureRequest, engine):
    if not request.config.getoption("--postgres"):
        pytest.skip("requires --postgres flag and a running PostgreSQL instance")
    await _provision_postgres_fulltext(engine)
    fs = PostgresFileSystem(engine=engine)
    await fs.install_native_graph_schema()
    return fs


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


def entry(path: str, *, content: str | None = None) -> Entry:
    """Create a minimal Entry for test assertions."""
    return Entry(path=path, content=content)


def make_fs(name: str = "test") -> VirtualFileSystem:
    """Create a VirtualFileSystem with a dummy session factory for routing tests."""
    from unittest.mock import AsyncMock

    fs = VirtualFileSystem(session_factory=AsyncMock())
    fs._name = name
    return fs


def require_file(result: VFSResult) -> Entry:
    """Return the first entry, asserting it exists for type narrowing."""
    assert result.file is not None
    return result.file


def require_object[T: VFSObjectBase](obj: T | None) -> T:
    """Assert an object exists and return the narrowed value."""
    assert obj is not None
    return obj


def require_text(text: str | None) -> str:
    """Assert a text field is present and return the narrowed value."""
    assert text is not None
    return text


class SQLCapture:
    """Captures every compiled SQL statement issued through an engine.

    Use as the value yielded by the ``sql_capture`` fixture. Statements land in
    ``self.statements`` in execution order. Helpers narrow the list to reads
    against the ``vfs_objects`` table, which is the only thing Phase 4
    narrowing assertions care about.
    """

    _SELECT_OBJECTS_RE = re.compile(
        r"\bFROM\s+vfs_objects\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.statements: list[str] = []

    def reset(self) -> None:
        self.statements.clear()

    def reads_against_objects(self) -> list[str]:
        return [
            s for s in self.statements if s.lstrip().upper().startswith("SELECT") and self._SELECT_OBJECTS_RE.search(s)
        ]

    def assert_no_column(self, column: str) -> None:
        """Assert no read against ``vfs_objects`` selected the given column.

        Matches the SQLAlchemy-rendered ``vfs_objects.<column>`` reference,
        which is how compiled SELECTs name projected columns regardless of
        dialect.
        """
        needle = re.compile(rf"\bvfs_objects\.{re.escape(column)}\b", re.IGNORECASE)
        offenders = [s for s in self.reads_against_objects() if needle.search(s)]
        assert not offenders, (
            f"Expected no SELECTs to project vfs_objects.{column!r} "
            f"but found {len(offenders)}:\n" + "\n---\n".join(offenders)
        )


@pytest.fixture
def sql_capture(engine):
    """Capture compiled SQL statements issued against ``engine``.

    Hooks ``before_cursor_execute`` on the underlying sync engine so the
    fully-rendered SQL (after dialect compilation) is what lands in
    ``capture.statements``. Use ``capture.reset()`` to drop pre-test setup
    statements before exercising the code under test.
    """
    capture = SQLCapture()
    sync_engine = engine.sync_engine

    def _on_execute(_conn, _cursor, statement, _parameters, _context, _executemany):
        capture.statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _on_execute)
    try:
        yield capture
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_execute)


def set_parameter_budget(db: DatabaseFileSystem, fallback: int) -> None:
    """Override the budget on one test instance without touching the class type."""
    cast("Any", db).DIALECT_PARAMETER_BUDGETS = {}
    db.PARAMETER_BUDGET_FALLBACK = fallback
