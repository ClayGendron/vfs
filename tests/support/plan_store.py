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

The store also holds 200 long text files under ``/chunks``, reindexed
before the statistics step: about 2,200 chunk rows, so the chunk pages
the index build and the embed step read plan over a filled chunk table.
SQLite's planner builds a per-page filter on the join only above about
four to five chunks per entry, a ratio the store's 56,000 short rows
keep it far below; the statistics pins build that ratio on a store of
their own from the same 200 bodies.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import event, select, text

from tests.support.server_schemas import server_schema
from vfs.models import Entry
from vfs.paths import Path
from vfs.pattern_matching import ScopeChannel
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.embed import EMBED_PAGE_ROWS, unembedded_page
from vfs.storage.backends.database.lexical import lexical_scan_page
from vfs.storage.backends.database.reads import (
    ENTRY_OBSERVATION_FIELDS,
    NO_SCOPE_FACTS,
    scope_facts,
    scope_fan,
)

if TYPE_CHECKING:
    import pathlib

    from sqlalchemy import Select, Table
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.storage.backends.database.embed import RefusalKey

PLAN_ROOTS: tuple[str, ...] = tuple(f"/d{i:05}" for i in range(2_000))
PLAN_ARMS: tuple[str, ...] = ("*.py", "*.ts", "a/*.md", "b/*.txt", "*.rs", "f0*", "a/f1*.py", "b/*.ts")
PLAN_EXTENSIONS: tuple[str, ...] = ("py", "ts", "md", "txt", "rs")

# The path index's name as every engine reports it, case aside.
PATH_INDEX = "ix_vfs_entries_path"

# The arms' facts beside the root OR, as any dialect spells them: a name or ext test.
FACTS_CONJUNCT = re.compile(r"\bvfs_entries\.(name|ext)\s*(=|LIKE)", re.IGNORECASE)

# A scope statement's root clause, as any dialect spells it: the path's strict-descendant LIKE.
ROOT_CLAUSE = re.compile(r"\bvfs_entries\.path\s+LIKE", re.IGNORECASE)

# A chunk page's join to the entry table, as any dialect spells it, schema-qualified or not.
ENTRY_JOIN = re.compile(r"\bJOIN\s+(?:\w+\.)?vfs_entries\b", re.IGNORECASE)

_BATCH = 10_000

CHUNK_ROOT = "/chunks"
"""Where the long text files live: outside every plan root, so no scope pin reads them."""

CHUNK_FILES = 200
CHUNK_BODY_CHARS = 20_480
"""Ten times the chunker's 2,048-character cut, so each body cuts about ten chunks, the reference ratio."""

_CHUNK_WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau "

# Any refusal key: the plan store embeds nothing, so the refusal term matches no row.
_PLAN_REFUSAL_KEY: Final[RefusalKey] = ("plan-store", -1, -1)


class PlanReading(NamedTuple):
    """One statement's plan as the engine printed it, and whether the root OR is index-served on the path index."""

    served: bool
    plan: str


def chunk_entries() -> list[Entry]:
    """The 200 long text files under :data:`CHUNK_ROOT`, each body word text of :data:`CHUNK_BODY_CHARS`."""
    words = _CHUNK_WORDS * (CHUNK_BODY_CHARS // len(_CHUNK_WORDS) + 1)
    return [
        Entry(path=Path(f"{CHUNK_ROOT}/f{index:03}.md"), content=f"file {index} {words}"[:CHUNK_BODY_CHARS])
        for index in range(CHUNK_FILES)
    ]


async def build_plan_store(storage: DatabaseStorage) -> None:
    """The store written in batches of 10,000, the long text files beside it, a reindex, then the statistics step.

    The reindex runs over every file, so each entry is chunked and the
    chunk pages' entry filter admits every chunk, as on a rebuilt store.
    """
    entries = [
        Entry(path=Path(f"{root}/{side}/f{index:02}.{PLAN_EXTENSIONS[index % 5]}"), content="x")
        for root in PLAN_ROOTS
        for index in range(25)
        for side in ("a" if index < 13 else "b",)
    ]
    for start in range(0, len(entries), _BATCH):
        written = await storage.write(entries=entries[start : start + _BATCH], parents=True)
        assert written.success is True, written.errors
    written = await storage.write(entries=chunk_entries(), parents=True)
    assert written.success is True, written.errors
    reindexed = await storage.reindex()
    assert reindexed.success is True, reindexed.errors
    # SQLite's statistics are vfs's own step, settled here; the server engines take their own command.
    await storage._host.settle_statistics()
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
    literal = _literal(storage, statement)
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


async def chunk_page_statements(storage: DatabaseStorage) -> dict[str, str]:
    """The build's and the embed step's chunk pages as the backend builds them, at the store's median chunk id.

    Spelled with literal values on the engine's own dialect, keyed
    ``build`` and ``embed``.
    """
    host = storage._host
    after = await _median_chunk_id(storage)
    pages = {
        "build": lexical_scan_page(host.tables, host.profile, after=after),
        "embed": unembedded_page(host.tables, after, EMBED_PAGE_ROWS, _PLAN_REFUSAL_KEY, host.profile),
    }
    return {page: _literal(storage, statement) for page, statement in pages.items()}


async def chunk_page_plans(storage: DatabaseStorage) -> dict[str, str]:
    """The engine's plan text of each chunk page of :func:`chunk_page_statements`, keyed the same."""
    statements = await chunk_page_statements(storage)
    return {page: await _plan_text(storage, statement) for page, statement in statements.items()}


async def shipped_join_plan(storage: DatabaseStorage) -> str:
    """The plan text of the build's chunk page spelled as the join to the entry table, at the median chunk id.

    The join is what every engine but SQLite runs, and what SQLite ran
    before its profile declared the probe: the red the SQLite pins read.
    """
    host = storage._host
    joined = replace(host.profile, probe_entry_filter=False)
    page = lexical_scan_page(host.tables, joined, after=await _median_chunk_id(storage))
    return await _plan_text(storage, _literal(storage, page))


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
    issued for the store's 2,000 roots and 8 arms. ``engine`` is the leg
    profile's name and ``probes`` its ``probe_entry_filter``;
    ``chunk_pages`` holds the plan text of the build's and the embed
    step's chunk pages, and ``chunk_statements`` the literal statements
    they plan, both keyed ``build`` and ``embed``.
    """

    declares: bool
    roots_alone: PlanReading
    with_facts: PlanReading
    statements: list[str]
    engine: str
    probes: bool
    chunk_pages: dict[str, str]
    chunk_statements: dict[str, str]


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
        data["declares"],
        PlanReading(*data["roots_alone"]),
        PlanReading(*data["with_facts"]),
        data["statements"],
        data["engine"],
        data["probes"],
        data["chunk_pages"],
        data["chunk_statements"],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _measured(url: str, schema: str | None) -> dict[str, Any]:
    """One store built and read: both plans, the declaration, the backend's own statements, the chunk pages."""
    storage = DatabaseStorage(url=url, schema=schema)
    try:
        await build_plan_store(storage)
        return {
            "declares": storage._host.profile.scope_facts_beside_fan,
            "roots_alone": list(await read_plan(storage, facts=False)),
            "with_facts": list(await read_plan(storage, facts=True)),
            "statements": await scope_statements(storage),
            "engine": storage._host.profile.name,
            "probes": storage._host.profile.probe_entry_filter,
            "chunk_pages": await chunk_page_plans(storage),
            "chunk_statements": await chunk_page_statements(storage),
        }
    finally:
        await storage.close()


def _statistics(storage: DatabaseStorage) -> list[str]:
    """The engine's own command that gathers the entries and chunk tables' planner statistics."""
    tables = storage._host.tables
    return [statement for table in (tables.entry, tables.chunks) for statement in _table_statistics(storage, table)]


def _table_statistics(storage: DatabaseStorage, table: Table) -> list[str]:
    """The engine's own command that gathers one table's planner statistics."""
    schema = table.schema
    qualified = table.name if schema is None else f"{schema}.{table.name}"
    match storage._host.profile.name:
        case "sqlite":
            return []
        case "postgresql":
            return [f"ANALYZE {qualified}"]
        case "mariadb":
            return [f"ANALYZE TABLE {qualified}"]
        case "mssql":
            return [f"UPDATE STATISTICS {qualified} WITH FULLSCAN"]
        case _:
            # Unquoted USER is the session user, the owner of an unqualified table.
            owner = "USER" if schema is None else f"'{schema.upper()}'"
            name = table.name.upper()
            return [f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname => {owner}, tabname => '{name}'); END;"]


async def _median_chunk_id(storage: DatabaseStorage) -> int:
    """The middle chunk id of the store, ascending: where a page of a full scan typically starts."""
    chunks = storage._host.tables.chunks
    async with storage._host.session_factory() as session:
        ids = (await session.execute(select(chunks.c.id).order_by(chunks.c.id))).scalars().all()
    assert ids, "the store holds no chunk rows to plan a chunk page over"
    return ids[len(ids) // 2]


def _literal(storage: DatabaseStorage, statement: Select[Any]) -> str:
    """*statement* spelled with literal values on the store's own dialect."""
    dialect = storage._host.engine.sync_engine.dialect
    return str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


async def _plan_text(storage: DatabaseStorage, literal: str) -> str:
    """The engine's plan of *literal* as it printed it, read on a session of the store's own."""
    async with storage._host.session_factory() as session:
        return await _PLAN_TEXTS[storage._host.profile.name](session, literal)


async def _sqlite_plan_text(session: AsyncSession, literal: str) -> str:
    """``EXPLAIN QUERY PLAN``'s detail column, one line a plan step."""
    rows = (await session.execute(text("EXPLAIN QUERY PLAN " + literal))).all()
    return "\n".join(str(row[-1]) for row in rows)


async def _sqlite_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``EXPLAIN QUERY PLAN``: a multi-index OR, no scan, every branch a search of the path index."""
    plan = await _sqlite_plan_text(session, literal)
    details = plan.splitlines()
    branches = [detail for detail in details if detail.startswith("SEARCH")]
    served = (
        any("MULTI-INDEX OR" in detail for detail in details)
        and not any(detail.startswith("SCAN") for detail in details)
        and bool(branches)
        and all(PATH_INDEX in detail for detail in branches)
    )
    return PlanReading(served, plan)


async def _postgres_plan_text(session: AsyncSession, literal: str) -> str:
    """``EXPLAIN``'s plan lines."""
    return "\n".join(str(row[0]) for row in (await session.execute(text("EXPLAIN " + literal))).all())


async def _postgres_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``EXPLAIN``: a ``BitmapOr`` of ``Bitmap Index Scan`` nodes on the path index, and no sequential scan."""
    plan = await _postgres_plan_text(session, literal)
    scans = [line for line in plan.splitlines() if "Bitmap Index Scan" in line]
    served = "BitmapOr" in plan and bool(scans) and all(PATH_INDEX in line for line in scans) and "Seq Scan" not in plan
    return PlanReading(served, plan)


async def _mariadb_rows(session: AsyncSession, literal: str) -> list[dict[str, Any]]:
    """``EXPLAIN``'s rows, one a table access, as column-keyed mappings."""
    result = await session.execute(text("EXPLAIN " + literal))
    return [dict(row) for row in result.mappings().all()]


async def _mariadb_plan_text(session: AsyncSession, literal: str) -> str:
    """``EXPLAIN``'s rows, one line a table access."""
    return "\n".join(str(row) for row in await _mariadb_rows(session, literal))


async def _mariadb_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``EXPLAIN``: a ``range`` or ``index_merge`` access whose key is the path index."""
    rows = await _mariadb_rows(session, literal)
    served = bool(rows) and all(
        row["type"] in ("range", "index_merge") and PATH_INDEX in str(row["key"]) for row in rows
    )
    return PlanReading(served, "\n".join(str(row) for row in rows))


async def _mssql_plan_text(session: AsyncSession, literal: str) -> str:
    """The showplan XML, read on the driver's own cursor with ``SHOWPLAN_XML`` on."""
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
    return plan


async def _mssql_plan(session: AsyncSession, literal: str) -> PlanReading:
    """The showplan XML: an ``Index Seek`` on the path index, and no scan of the entries table."""
    plan = await _mssql_plan_text(session, literal)
    operators = re.findall(r'PhysicalOp="([^"]+)"[^>]*>', plan)
    seeks = re.findall(r'PhysicalOp="Index Seek".*?Index="\[([^\]]+)\]"', plan, flags=re.DOTALL)
    served = (
        "Index Seek" in operators
        and any(PATH_INDEX in seek for seek in seeks)
        and not any(op in ("Clustered Index Scan", "Table Scan", "Index Scan") for op in operators)
    )
    return PlanReading(served, plan)


async def _oracle_plan_text(session: AsyncSession, literal: str) -> str:
    """``DBMS_XPLAN.DISPLAY``'s lines for the statement just explained."""
    await session.execute(text("EXPLAIN PLAN FOR " + literal))
    rows = (await session.execute(text("SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())"))).all()
    return "\n".join(str(row[0]) for row in rows)


async def _oracle_plan(session: AsyncSession, literal: str) -> PlanReading:
    """``DBMS_XPLAN``: an ``INDEX RANGE SCAN`` of the path index, and no full scan of the entries table."""
    plan = await _oracle_plan_text(session, literal)
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

_PLAN_TEXTS = {
    "sqlite": _sqlite_plan_text,
    "postgresql": _postgres_plan_text,
    "mariadb": _mariadb_plan_text,
    "mssql": _mssql_plan_text,
    "oracle": _oracle_plan_text,
}
