"""The plan pins' store: 50,000 files under 2,000 roots, statistics gathered, plans read by operator.

The scope fan may carry one conjunct beside its OR of root clauses, the
arms' leaf-name and extension facts, only where the engine keeps the
root OR as an index-served access path with it there. A cost-based
planner scans a table of a few pages whatever its WHERE says, so the
pins plan over a store the size the measurements used: 2,000
directories ``/dNNNNN``, each with 25 files over ``a/`` and ``b/`` in
five extensions — 50,000 files and 56,001 rows, 6,001 directories with
the root, and 54,000 rows strictly beneath the 2,000 roots. It is
written through the backend in batches of 10,000, and the engine's own
statistics step runs before any plan is read.

Each pin builds a statement the way the backend does
(:func:`~vfs.storage.backends.database.reads.scope_fan` over the first
chunk of roots), spells it with literal values on the engine's own
dialect, and reads the engine's plan: ``EXPLAIN QUERY PLAN`` on SQLite,
``EXPLAIN`` on Postgres and MariaDB, the showplan XML on SQL Server and
``DBMS_XPLAN`` on Oracle. A plan is judged by operator on the path
index, never by time.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import event, select, text

from tests.support.server_schemas import server_schema
from vfs.models import Entry
from vfs.paths import Path
from vfs.pattern_matching import ScopeChannel
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.reads import (
    ENTRY_OBSERVATION_FIELDS,
    NO_SCOPE_FACTS,
    scope_facts,
    scope_fan,
)

if TYPE_CHECKING:
    import pathlib

    from sqlalchemy.ext.asyncio import AsyncSession

PLAN_ROOTS: tuple[str, ...] = tuple(f"/d{i:05}" for i in range(2_000))
PLAN_ARMS: tuple[str, ...] = ("*.py", "*.ts", "a/*.md", "b/*.txt", "*.rs", "f0*", "a/f1*.py", "b/*.ts")
PLAN_EXTENSIONS: tuple[str, ...] = ("py", "ts", "md", "txt", "rs")

# The path index's name as every engine reports it, case aside.
PATH_INDEX = "ix_vfs_entries_path"

# The arms' facts beside the root OR, as any dialect spells them: a name or ext test.
FACTS_CONJUNCT = re.compile(r"\bvfs_entries\.(name|ext)\s*(=|LIKE)", re.IGNORECASE)

# A scope statement's root clause, as any dialect spells it: the path's strict-descendant LIKE.
ROOT_CLAUSE = re.compile(r"\bvfs_entries\.path\s+LIKE", re.IGNORECASE)

_BATCH = 10_000


class PlanReading(NamedTuple):
    """One statement's plan as the engine printed it, and whether the root OR is index-served on the path index."""

    served: bool
    plan: str


async def build_plan_store(storage: DatabaseStorage) -> None:
    """The store, written in batches of 10,000, then the engine's statistics step."""
    entries = [
        Entry(path=Path(f"{root}/{side}/f{index:02}.{PLAN_EXTENSIONS[index % 5]}"), content="x")
        for root in PLAN_ROOTS
        for index in range(25)
        for side in ("a" if index < 13 else "b",)
    ]
    for start in range(0, len(entries), _BATCH):
        written = await storage.write(entries=entries[start : start + _BATCH], parents=True)
        assert written.success is True, written.errors
    async with storage._host.session_factory() as session:
        for statement in _statistics(storage):
            await session.execute(text(statement))
        await session.commit()


async def read_plan(storage: DatabaseStorage, *, facts: bool) -> PlanReading:
    """The plan of the scope fan's first statement over the store, the roots alone or with the arms' facts beside."""
    host = storage._host
    entry = host.tables.entry
    profile = host.profile
    beside = NO_SCOPE_FACTS
    if facts:
        licensed = replace(profile, scope_facts_beside_fan=True)
        beside = scope_facts(entry, licensed, host.parameter_budget, host.membership_budget, PLAN_ARMS)
        assert beside.predicate is not None
    roots = [Path(root) for root in PLAN_ROOTS]
    [first, *_rest] = scope_fan(
        entry, profile, host.parameter_budget, host.membership_budget, roots, beside, frozenset()
    )
    columns = [entry.c[field] for field in sorted(ENTRY_OBSERVATION_FIELDS | {"name", "ext"})]
    statement = select(*columns).where(first)
    dialect = host.engine.sync_engine.dialect
    literal = str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    async with host.session_factory() as session:
        return await _READERS[profile.name](session, literal)


async def scope_statements(storage: DatabaseStorage) -> list[str]:
    """The root-clause statements the backend itself issues for a glob of the store's 2,000 roots and 8 arms."""
    recorded: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        recorded.append(statement)

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        scope = ScopeChannel(roots=tuple(Path(root) for root in PLAN_ROOTS), arms=PLAN_ARMS)
        result = await storage.glob(patterns=(), scope=scope)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert result.success is True, result.errors
    return [statement for statement in recorded if ROOT_CLAUSE.search(statement)]


class PlanBackend(NamedTuple):
    """Where one conformance leg's plan store lives: a SQLite file of its own, or a schema on a server.

    ``key`` names the leg in the session's shared builds; ``env_var`` is
    the server URL's variable, or ``None`` for a SQLite file.
    """

    key: str
    env_var: str | None = None


class PlanReadings(NamedTuple):
    """Everything the plan pins judge, read once per leg from one store.

    ``declares`` is the leg profile's ``scope_facts_beside_fan``;
    ``statements`` are the root-clause statements the backend itself
    issued for the store's 2,000 roots and 8 arms.
    """

    declares: bool
    roots_alone: PlanReading
    with_facts: PlanReading
    statements: list[str]


def plan_readings(backend: PlanBackend, workdir: pathlib.Path) -> dict[str, Any]:
    """Build the store on *backend* and read both plans and the backend's own statements, as JSON-ready data.

    A SQLite store is a file under *workdir*; a server store is a schema
    of its own, dropped once read. Each runs on an event loop of its own,
    so a session-wide build never binds to a test's loop.
    """
    if backend.env_var is None:
        return asyncio.run(_measured(f"sqlite+aiosqlite:///{workdir}/plan.sqlite", None))
    with server_schema(backend.env_var) as (url, schema):
        return asyncio.run(_measured(url, schema))


def decoded(data: dict[str, Any]) -> PlanReadings:
    """:class:`PlanReadings` back from :func:`plan_readings`' JSON-ready data."""
    return PlanReadings(
        data["declares"], PlanReading(*data["roots_alone"]), PlanReading(*data["with_facts"]), data["statements"]
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _measured(url: str, schema: str | None) -> dict[str, Any]:
    """One store built and read: both plans, the profile's declaration, and the backend's own statements."""
    storage = DatabaseStorage(url=url, schema=schema)
    try:
        await build_plan_store(storage)
        return {
            "declares": storage._host.profile.scope_facts_beside_fan,
            "roots_alone": list(await read_plan(storage, facts=False)),
            "with_facts": list(await read_plan(storage, facts=True)),
            "statements": await scope_statements(storage),
        }
    finally:
        await storage.close()


def _statistics(storage: DatabaseStorage) -> list[str]:
    """The engine's own command that gathers the entries table's planner statistics."""
    entry = storage._host.tables.entry
    schema = entry.schema
    qualified = entry.name if schema is None else f"{schema}.{entry.name}"
    match storage._host.profile.name:
        case "sqlite":
            return ["ANALYZE"]
        case "postgresql":
            return [f"ANALYZE {qualified}"]
        case "mariadb":
            return [f"ANALYZE TABLE {qualified}"]
        case "mssql":
            return [f"UPDATE STATISTICS {qualified} WITH FULLSCAN"]
        case _:
            # Unquoted USER is the session user, the owner of an unqualified table.
            owner = "USER" if schema is None else f"'{schema.upper()}'"
            return [f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname => {owner}, tabname => 'VFS_ENTRIES'); END;"]


async def _sqlite_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``EXPLAIN QUERY PLAN``: a multi-index OR, no scan, every branch a search of the path index."""
    rows = (await session.execute(text("EXPLAIN QUERY PLAN " + literal))).all()
    details = [str(row[-1]) for row in rows]
    branches = [detail for detail in details if detail.startswith("SEARCH")]
    served = (
        any("MULTI-INDEX OR" in detail for detail in details)
        and not any(detail.startswith("SCAN") for detail in details)
        and bool(branches)
        and all(PATH_INDEX in detail for detail in branches)
    )
    return PlanReading(served, "\n".join(details))


async def _postgres_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``EXPLAIN``: a ``BitmapOr`` of ``Bitmap Index Scan`` nodes on the path index, and no sequential scan."""
    lines = [str(row[0]) for row in (await session.execute(text("EXPLAIN " + literal))).all()]
    plan = "\n".join(lines)
    scans = [line for line in lines if "Bitmap Index Scan" in line]
    served = "BitmapOr" in plan and bool(scans) and all(PATH_INDEX in line for line in scans) and "Seq Scan" not in plan
    return PlanReading(served, plan)


async def _mariadb_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``EXPLAIN``: a ``range`` or ``index_merge`` access whose key is the path index."""
    result = await session.execute(text("EXPLAIN " + literal))
    rows = [dict(row) for row in result.mappings().all()]
    served = bool(rows) and all(
        row["type"] in ("range", "index_merge") and PATH_INDEX in str(row["key"]) for row in rows
    )
    return PlanReading(served, "\n".join(str(row) for row in rows))


async def _mssql_plan(session: AsyncSession, literal: str) -> PlanReading:
    """The showplan XML: an ``Index Seek`` on the path index, and no scan of the entries table."""
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    driver = raw.driver_connection
    assert driver is not None
    cursor = await driver.cursor()
    try:
        await cursor.execute("SET SHOWPLAN_XML ON")
        await cursor.execute(literal)
        plan = "".join(str(row[0]) for row in await cursor.fetchall())
        await cursor.execute("SET SHOWPLAN_XML OFF")
    finally:
        await cursor.close()
    operators = re.findall(r'PhysicalOp="([^"]+)"[^>]*>', plan)
    seeks = re.findall(r'PhysicalOp="Index Seek".*?Index="\[([^\]]+)\]"', plan, flags=re.DOTALL)
    served = (
        "Index Seek" in operators
        and any(PATH_INDEX in seek for seek in seeks)
        and not any(op in ("Clustered Index Scan", "Table Scan", "Index Scan") for op in operators)
    )
    return PlanReading(served, plan)


async def _oracle_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``DBMS_XPLAN``: an ``INDEX RANGE SCAN`` of the path index, and no full scan of the entries table."""
    await session.execute(text("EXPLAIN PLAN FOR " + literal))
    rows = (await session.execute(text("SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())"))).all()
    plan = "\n".join(str(row[0]) for row in rows)
    upper = plan.upper()
    served = "INDEX RANGE SCAN" in upper and PATH_INDEX.upper() in upper and "TABLE ACCESS FULL" not in upper
    return PlanReading(served, plan)


_READERS = {
    "sqlite": _sqlite_plan,
    "postgresql": _postgres_plan,
    "mariadb": _mariadb_plan,
    "mssql": _mssql_plan,
    "oracle": _oracle_plan,
}
