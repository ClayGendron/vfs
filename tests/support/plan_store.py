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
dialect, and reads the engine's plan: ``EXPLAIN QUERY PLAN`` on SQLite
and ``EXPLAIN`` on Postgres. A plan is judged by operator on the path
index, never by time.

The store also holds 200 long text files under ``/chunks``, rebuilt
before the statistics step: about 2,200 chunk rows, so the chunk pages
the index build and the embed step read plan over a filled chunk table.
SQLite's planner builds a per-page filter on the join only above about
four to five chunks per entry, a ratio the store's 56,000 short rows
keep it far below; the statistics pins build that ratio on a store of
their own from the same 200 bodies.

Every file's body is one the gram index encodes, so after the rebuild
no content row awaits the index; the build asserts it. A body the index
never encodes (a sub-trigram one, say) stays ``NOT encoded`` for good,
and a store of them would put nine tenths of its rows behind the
dirty-row seek, where a planner rightly walks another index instead.

Last, once every other reading is taken, the store turns private: the
root posture ``none``, one principal granted ``read`` on the first 300
roots and another on the first 1,000 (about half the rows), one file
written since the index pass, so exactly one content row awaits the
index (asserted), and the statistics step again. The scan tier's
statements for one grep by the system actor and for one by each
principal are recorded as the nominator built them, spelled with literal
values and planned, so a pin can hold the partial callers' accesses to
the entries table (:func:`entry_access`) to the whole caller's.

After those, a root of its own takes a thousand files, ineligible and
trashed shares among them, and a refresh's four selection reads are
planned over it (:func:`refresh_readings`).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast
from unittest import mock

from sqlalchemy import event, func, select, text
from ulid import ULID

from tests.support.partial_callers import RecordingSession
from tests.support.server_schemas import server_schema
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.models.rows import ULIDKey, build_vfs_tables
from vfs.paths import Path
from vfs.pattern_matching import ScopeChannel
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database import maintenance as maintenance_module
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.embed import EMBED_PAGE_ROWS, pass_unembedded, select_pass_page, unembedded_page
from vfs.storage.backends.database.lexical import _SCAN_PAGE_ROWS, lexical_scan_page
from vfs.storage.backends.database.pages import covered_chunk_page
from vfs.storage.backends.database.reads import (
    ENTRY_OBSERVATION_FIELDS,
    NO_SCOPE_FACTS,
    kind_membership,
    scope_facts,
    scope_fan,
)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from sqlalchemy import Select, Table
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.storage.backends.database.embed import RefusalKey

PLAN_ROOTS: tuple[str, ...] = tuple(f"/d{i:05}" for i in range(2_000))
PLAN_ARMS: tuple[str, ...] = ("*.py", "*.ts", "a/*.md", "b/*.txt", "*.rs", "f0*", "a/f1*.py", "b/*.ts")
PLAN_EXTENSIONS: tuple[str, ...] = ("py", "ts", "md", "txt", "rs")
PLAN_BODY = "plan body"
"""Every plan file's body: past the gram size, so the rebuild encodes the file and the overlay holds none of them."""

# The path index's name as every engine reports it, case aside.
PATH_INDEX = "ix_vfs_entries_path"

# The indexes it may seek on an equality alone: the caller's own rows (the owner floor) and paths.
EQUALITY_INDEXES = frozenset({"ix_vfs_entries_owner_id", PATH_INDEX})

# Each entries index's leading column: a seek bounds it, or it walks the index.
LEADING_COLUMNS: Final[dict[str, str]] = {
    index.name.lower(): next(iter(index.columns)).name for index in build_vfs_tables().entry.indexes if index.name
}


def dirty_indexes(table: Table) -> frozenset[str]:
    """*table*'s indexes led by ``encoded``, case aside: a seek bounding that column reads the rows awaiting the index.

    An index holding ``encoded`` past its first column is not one: it seeks
    on its leading column, and a seek there reads whatever that column holds.
    """
    return frozenset(index.name.lower() for index in table.indexes if index.name and index.columns[0].name == "encoded")


# The indexes of the rows awaiting the index, which a scan-tier statement may seek on any bound of their leading column.
DIRTY_INDEXES: Final = dirty_indexes(build_vfs_tables().entry)

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

OVERLAY_ROOTS = 300
"""The roots the partial caller reads: rights that compile to more than one packed group on every engine."""

OVERLAY_HALF_ROOTS = 1_000
"""The roots the half caller reads: about half the store's rows, the shape that most tempts a planner to its grants."""

REFRESH_ROOT = "/refresh"
REFRESH_FILES = 1_000
"""The refresh readings' files: outside every plan root, a fifth of them too short to index, a tenth then trashed."""

REFUSED_TEXTS = 2_000
"""Refusal rows per model the refresh readings' store holds: hundreds of times one pass's chunk rows."""

# Either chunk index led by ``entry_id`` serves the embed step's read.
_CHUNK_ENTRY_KEYS: Final = "(?:ix_vfs_chunks_entry_id|uq_vfs_chunks_entry_index)"
# A primary key as each engine names it: SQLite's row id or its key index, then Postgres.
_CHUNK_KEY: Final = r"(?:INTEGER PRIMARY KEY|vfs_chunks_pkey)"
_REFUSAL_KEY: Final = r"(?:sqlite_autoindex_vfs_embed_refusals_1|vfs_embed_refusals_pkey)"
REFRESH_INDEXES: Final[dict[str, tuple[str, str]]] = {
    "render": ("vfs_entries", "ix_vfs_entries_render_status"),
    "slice": ("vfs_entries", "ix_vfs_entries_index_pending"),
    "posting": ("vfs_entries", "ix_vfs_entries_index_pending"),
    "kept": ("vfs_entries", "ix_vfs_entries_index_pending"),
    "embed": ("vfs_chunks", _CHUNK_ENTRY_KEYS),
    "refusals": ("vfs_embed_refusals", _REFUSAL_KEY),
    "page": ("vfs_chunks", _CHUNK_KEY),
}
"""Each refresh reading's table and the index it must seek there, as every engine reports it, case aside."""

OVERLAY_READER = "plan-reader"
OVERLAY_HALF_READER = "plan-half-reader"
OVERLAY_WORD = "lantern"
OVERLAY_FILE = f"{PLAN_ROOTS[0]}/a/late.md"
"""The partial callers, and the one file written after the index pass, inside their first root, holding the word."""

# A compiled clause's term, as any dialect spells it: the everyone level, the owner, or a path bound or point.
RIGHTS_TERM = re.compile(r"\b(?:everyone_level\s*>=|owner_id\s*=|path\s*[<>=]\s)", re.IGNORECASE)


class PlanReading(NamedTuple):
    """One statement's plan as the engine printed it, and whether the root OR is index-served on the path index."""

    served: bool
    plan: str


class EntryAccess(NamedTuple):
    """One access a plan makes to the entries table, as the engine names it.

    ``operation`` is the engine's own word for it, ``index`` the index it
    reads (``None`` for the table itself), ``seeks`` whether it seeks on a
    condition rather than walking, and ``equality`` whether every bound of
    that seek is an equality. A fetch of the table's rows by the locators
    an index access returned is no access of its own: it visits only
    those rows.
    """

    operation: str
    index: str | None
    seeks: bool
    equality: bool


def chunk_entries() -> list[Entry]:
    """The 200 long text files under :data:`CHUNK_ROOT`, each body word text of :data:`CHUNK_BODY_CHARS`."""
    words = _CHUNK_WORDS * (CHUNK_BODY_CHARS // len(_CHUNK_WORDS) + 1)
    return [
        Entry(path=Path(f"{CHUNK_ROOT}/f{index:03}.md"), content=f"file {index} {words}"[:CHUNK_BODY_CHARS])
        for index in range(CHUNK_FILES)
    ]


async def build_plan_store(storage: DatabaseStorage) -> None:
    """The store written in batches of 10,000, the long text files beside it, a rebuild, then the statistics step.

    The rebuild runs over every file, so each entry is chunked and the
    chunk pages' entry filter admits every chunk, as on a rebuilt store.
    """
    entries = [
        Entry(path=Path(f"{root}/{side}/f{index:02}.{PLAN_EXTENSIONS[index % 5]}"), content=PLAN_BODY)
        for root in PLAN_ROOTS
        for index in range(25)
        for side in ("a" if index < 13 else "b",)
    ]
    for start in range(0, len(entries), _BATCH):
        written = await storage.write(entries=entries[start : start + _BATCH], parents=True)
        assert written.success is True, written.errors
    written = await storage.write(entries=chunk_entries(), parents=True)
    assert written.success is True, written.errors
    rebuilt = await storage.rebuild()
    assert rebuilt.success is True, rebuilt.errors
    pending = await pending_content_rows(storage)
    assert pending == 0, f"{pending} content rows still await the index after the rebuild"
    await _gather_statistics(storage)


class OverlayPlans(NamedTuple):
    """The scan tier's ``(statement, plan)`` pairs for the whole caller and each partial one."""

    whole: list[tuple[str, str]]
    partial: list[tuple[str, str]]
    half: list[tuple[str, str]]


async def overlay_readings(storage: DatabaseStorage) -> OverlayPlans:
    """The store turned private, then the scan tier's ``(statement, plan)`` pairs for a whole and two partial callers.

    The whole caller is the system actor; the partial ones read the first
    :data:`OVERLAY_ROOTS` and the first :data:`OVERLAY_HALF_ROOTS` roots.
    Each greps the word the one file written since the index pass holds,
    so the scan tier runs for all three over exactly one row awaiting it.
    """
    system = Authority.system()
    turned = await storage.set_posture(path=Path("/"), posture="none", authority=system)
    assert turned.success is True, turned.errors
    readers = ((OVERLAY_READER, OVERLAY_ROOTS), (OVERLAY_HALF_READER, OVERLAY_HALF_ROOTS))
    for reader, roots in readers:
        for root in PLAN_ROOTS[:roots]:
            granted = await storage.grant(path=Path(root), principal=reader, level="read", authority=system)
            assert granted.success is True, granted.errors
    late = Entry(path=Path(OVERLAY_FILE), content=f"{OVERLAY_WORD} late")
    written = await storage.write(entries=[late], authority=system)
    assert written.success is True, written.errors
    pending = await pending_content_rows(storage)
    assert pending == 1, f"{pending} content rows await the index where the readings mean one"
    await _gather_statistics(storage)
    return OverlayPlans(
        await _scan_tier_plans(storage, system),
        await _scan_tier_plans(storage, Authority.of(Principal(OVERLAY_READER))),
        await _scan_tier_plans(storage, Authority.of(Principal(OVERLAY_HALF_READER))),
    )


async def refresh_readings(storage: DatabaseStorage) -> dict[str, str]:
    """The four reads a refresh issues to find its work, each spelled with literal values and planned.

    Taken last, after the scan tier's readings, so the store's own
    pending-row counts stay what those readings mean: :data:`REFRESH_FILES`
    files under :data:`REFRESH_ROOT`, a fifth too short to index, posted by a
    refresh, a tenth of them then trashed, five more written, the statistics
    step, and one more refresh whose render read, slice read and two delta
    scans are recorded as built.
    """
    system = Authority.system()
    bodies = [
        Entry(path=Path(f"{REFRESH_ROOT}/f{n:04}.txt"), content="ab" if n % 5 == 0 else f"{PLAN_BODY} {n}")
        for n in range(REFRESH_FILES)
    ]
    assert (await storage.write(entries=bodies, parents=True, authority=system)).success is True
    assert (await storage.refresh()).success is True
    for n in range(0, REFRESH_FILES, 10):
        assert (await storage.delete(path=Path(f"{REFRESH_ROOT}/f{n + 1:04}.txt"), authority=system)).success
    later = [Entry(path=Path(f"{REFRESH_ROOT}/late{n}.txt"), content=f"{PLAN_BODY} late {n}") for n in range(5)]
    assert (await storage.write(entries=later, authority=system)).success is True
    await _refused_texts(storage)
    await _gather_statistics(storage)
    recorded: dict[str, Select[Any]] = {}
    real_render, real_size = maintenance_module.select_render_dirty, indexing._size_read
    real_scans = indexing._delta_scans

    async def render(session: Any, *args: Any, **kwargs: Any) -> Any:
        statements: list[Any] = []
        rows = await real_render(cast("AsyncSession", RecordingSession(session, statements)), *args, **kwargs)
        recorded.setdefault("render", statements[0])
        return rows

    def size(*args: Any, **kwargs: Any) -> Select[Any]:
        return recorded.setdefault("slice", real_size(*args, **kwargs))

    def scans(*args: Any, **kwargs: Any) -> tuple[Select[Any], Select[Any]]:
        kept, posting = real_scans(*args, **kwargs)
        recorded.update(kept=kept, posting=posting)
        return kept, posting

    with (
        mock.patch.object(maintenance_module, "select_render_dirty", render),
        mock.patch.object(indexing, "_size_read", size),
        mock.patch.object(indexing, "_delta_scans", scans),
    ):
        assert (await storage.refresh()).success is True
    recorded.update(await _embed_readings(storage, [f"{REFRESH_ROOT}/late{n}.txt" for n in range(5)]))
    return {name: await _plan_text(storage, _literal(storage, statement)) for name, statement in recorded.items()}


async def _refused_texts(storage: DatabaseStorage) -> None:
    """:data:`REFUSED_TEXTS` refusal rows for the plan store's own model and as many for another: a table far
    larger than any one pass's chunk rows, so a plan that walks it shows."""
    refusals = storage._host.tables.embed_refusals
    models = (_PLAN_REFUSAL_KEY, ("plan-store-other", -1, -1))
    rows = [
        {"content_hash": f"{side}{n:063x}", "model_id": model, "max_input_tokens": cap, "max_batch_tokens": batch}
        for side, (model, cap, batch) in enumerate(models)
        for n in range(REFUSED_TEXTS)
    ]
    async with storage._host.session_factory() as session:
        for page in chunked(rows, 500):
            await session.execute(refusals.insert(), page)
        await session.commit()


async def _embed_readings(storage: DatabaseStorage, paths: list[str]) -> dict[str, Any]:
    """A refresh's embed reads over *paths*' entries as the backend issues them: the read of the pass's rows
    without a vector, the probe of their texts' refusals, and the first page of ids."""
    host, entry = storage._host, storage._host.tables.entry
    async with host.session_factory() as session:
        ids = list((await session.execute(select(entry.c.entry_id).where(entry.c.path.in_(paths)))).scalars())
        statements: list[Any] = []
        recording = cast("AsyncSession", RecordingSession(session, statements))
        found = await pass_unembedded(
            recording, host.tables, _PLAN_REFUSAL_KEY, host.profile, host.membership_budget, ids
        )
        await select_pass_page(recording, host.tables, host.profile, found.ids[:EMBED_PAGE_ROWS])
    rows, refusals, page = statements
    return {"embed": rows, "refusals": refusals, "page": page}


async def pending_content_rows(storage: DatabaseStorage) -> int:
    """The live content rows awaiting the index: the rows the scan tier's dirty-row seek returns."""
    entry = storage._host.tables.entry
    stmt = select(func.count()).where(kind_membership(entry).predicate, ~entry.c.encoded, entry.c.deleted_at.is_(None))
    async with storage._host.session_factory() as session:
        return int((await session.execute(stmt)).scalar_one())


def entry_access(engine: str, plan: str) -> list[EntryAccess]:
    """*plan*'s accesses to the entries table, read the way *engine* (a profile name) prints its plans."""
    return _ACCESSES[engine](plan)


def bounded_access(access: EntryAccess) -> bool:
    """Whether *access* is a seek the scan tier's statement means, never a scan of the table or a walk of an index.

    The seek may be of an index led by ``encoded`` (:data:`DIRTY_INDEXES`:
    ``(encoded, kind)``, and the refresh's pending index), the rows awaiting
    the index, or an equality seek of the owner index or the path index,
    the caller's own rows or paths. A range over a path index is refused:
    over a caller who reads half the store it visits half the table. An
    access that names several indexes, comma-separated, qualifies only if
    each does.
    """
    if not access.seeks or access.index is None:
        return False
    names = [name.strip().lower() for name in access.index.split(",")]
    return all(name in DIRTY_INDEXES or (name in EQUALITY_INDEXES and access.equality) for name in names)


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
        "build": lexical_scan_page(host.tables, after=after),
        "embed": unembedded_page(host.tables, after, EMBED_PAGE_ROWS, _PLAN_REFUSAL_KEY, host.profile),
    }
    return {page: _literal(storage, statement) for page, statement in pages.items()}


async def chunk_page_plans(storage: DatabaseStorage) -> dict[str, str]:
    """The engine's plan text of each chunk page of :func:`chunk_page_statements`, keyed the same."""
    statements = await chunk_page_statements(storage)
    return {page: await _plan_text(storage, statement) for page, statement in statements.items()}


async def shipped_join_plan(storage: DatabaseStorage) -> str:
    """The plan text of the build's former chunk page spelled as the join to the entry table, at the median chunk id.

    The join is what every engine but SQLite runs, and what SQLite ran
    before its profile declared the probe: the red the SQLite pins read.
    The build's page has since stopped reading the entry table, so the
    page is spelled here as it stood: the covered entries' chunks.
    """
    host = storage._host
    tables, joined = host.tables, replace(host.profile, probe_entry_filter=False)
    chunks, entry = tables.chunks, tables.entry
    page = covered_chunk_page(
        tables,
        joined,
        [chunks.c.id, chunks.c.entry_id, chunks.c.content],
        [entry.c.chunked, entry.c.indexable, entry.c.deleted_at.is_(None)],
        after=await _median_chunk_id(storage),
        limit=_SCAN_PAGE_ROWS,
    )
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
    they plan, both keyed ``build`` and ``embed``. ``overlay_whole``,
    ``overlay_partial`` and ``overlay_half`` are the scan tier's
    ``(statement, plan)`` pairs for the whole caller's, the 300-root
    caller's and the half caller's grep (:func:`overlay_readings`).
    """

    declares: bool
    roots_alone: PlanReading
    with_facts: PlanReading
    statements: list[str]
    engine: str
    probes: bool
    chunk_pages: dict[str, str]
    chunk_statements: dict[str, str]
    overlay_whole: list[tuple[str, str]]
    overlay_partial: list[tuple[str, str]]
    overlay_half: list[tuple[str, str]]
    refresh_plans: dict[str, str]


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
        [(statement, plan) for statement, plan in data["overlay_whole"]],
        [(statement, plan) for statement, plan in data["overlay_partial"]],
        [(statement, plan) for statement, plan in data["overlay_half"]],
        data["refresh_plans"],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _measured(url: str, schema: str | None) -> dict[str, Any]:
    """One store built and read: both plans, the declaration, the backend's own statements, the chunk pages.

    The scan tier's readings come last, because they turn the store
    private and write to it.
    """
    storage = DatabaseStorage(url=url, schema=schema)
    try:
        await build_plan_store(storage)
        readings: dict[str, Any] = {
            "declares": storage._host.profile.scope_facts_beside_fan,
            "roots_alone": list(await read_plan(storage, facts=False)),
            "with_facts": list(await read_plan(storage, facts=True)),
            "statements": await scope_statements(storage),
            "engine": storage._host.profile.name,
            "probes": storage._host.profile.probe_entry_filter,
            "chunk_pages": await chunk_page_plans(storage),
            "chunk_statements": await chunk_page_statements(storage),
        }
        overlay = await overlay_readings(storage)
        readings.update(overlay_whole=overlay.whole, overlay_partial=overlay.partial, overlay_half=overlay.half)
        readings["refresh_plans"] = await refresh_readings(storage)
        return readings
    finally:
        await storage.close()


async def _gather_statistics(storage: DatabaseStorage) -> None:
    """The planner statistics settled: SQLite's are vfs's own step, the server engines take their own command."""
    await storage._host.settle_statistics()
    async with storage._host.session_factory() as session:
        for statement in _statistics(storage):
            await session.execute(text(statement))
        await session.commit()


async def _scan_tier_plans(storage: DatabaseStorage, authority: Authority) -> list[tuple[str, str]]:
    """The scan tier's statements for one grep by *authority*, each spelled with literal values, with its plan."""
    recorded: list[Select[Any]] = []
    real = grep_module.entries_for_scan

    async def recording(session: Any, *args: Any, **kwargs: Any) -> Any:
        return await real(cast("AsyncSession", RecordingSession(session, recorded)), *args, **kwargs)

    with mock.patch.object(grep_module, "entries_for_scan", recording):
        result = await storage.grep(pattern=OVERLAY_WORD, authority=authority)
    assert result.success is True, result.errors
    literals = [_literal(storage, statement) for statement in recorded]
    return [(literal, await _plan_text(storage, literal)) for literal in literals]


def _statistics(storage: DatabaseStorage) -> list[str]:
    """The engine's own command that gathers the entries and chunk tables' planner statistics."""
    tables = storage._host.tables
    return [statement for table in (tables.entry, tables.chunks) for statement in _table_statistics(storage, table)]


def _table_statistics(storage: DatabaseStorage, table: Table) -> list[str]:
    """The engine's own command that gathers one table's planner statistics."""
    schema = table.schema
    qualified = table.name if schema is None else f"{schema}.{table.name}"
    return [] if storage._host.profile.name == "sqlite" else [f"ANALYZE {qualified}"]


async def _median_chunk_id(storage: DatabaseStorage) -> int:
    """The middle chunk id of the store, ascending: where a page of a full scan typically starts."""
    chunks = storage._host.tables.chunks
    async with storage._host.session_factory() as session:
        ids = (await session.execute(select(chunks.c.id).order_by(chunks.c.id))).scalars().all()
    assert ids, "the store holds no chunk rows to plan a chunk page over"
    return ids[len(ids) // 2]


def _literal(storage: DatabaseStorage, statement: Select[Any]) -> str:
    """*statement* spelled with literal values on the store's own dialect, an entry id as the engine's key literal."""
    dialect = storage._host.engine.sync_engine.dialect
    with mock.patch.object(ULIDKey, "literal_processor", _ulid_literal):
        return str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def _ulid_literal(_type: ULIDKey, dialect: Any) -> Callable[[str], str]:
    """An entry id spelled inline as the key the engine stores: a uuid on Postgres, sixteen bytes elsewhere."""

    def spelled(value: str) -> str:
        ulid = ULID.from_str(value)
        if dialect.name == "postgresql":
            return f"'{ulid.to_uuid()}'::uuid"
        return f"X'{ulid.bytes.hex().upper()}'"

    return spelled


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


# A bound that is not an equality, as each engine prints a seek's condition.
_RANGE_BOUND = re.compile(r"[<>]|~~")

# One EXPLAIN QUERY PLAN step on the entries table: its verb, its index, its condition.
_SQLITE_STEP = re.compile(r"^(SEARCH|SCAN) vfs_entries(?: USING (?:COVERING )?INDEX (\w+))?(?: \((.*)\))?")

# One Postgres plan node: its type, the index after ``using``, and what it runs ``on``.
_POSTGRES_NODE = re.compile(
    r"(Seq Scan|Index Only Scan|Index Scan|Bitmap Index Scan|Bitmap Heap Scan)(?: Backward)?(?: using (\S+))? on (\S+)"
)


def _sqlite_access(plan: str) -> list[EntryAccess]:
    """Each ``SEARCH`` or ``SCAN`` step on ``vfs_entries``: a search on a condition seeks, a scan walks.

    A step naming ``vfs_entries`` in any other spelling (``SCAN TABLE``,
    before SQLite 3.36) is read as a scan, never dropped.
    """
    accesses: list[EntryAccess] = []
    for detail in plan.splitlines():
        step = _SQLITE_STEP.match(detail.strip())
        if step is None:
            if re.search(r"\bvfs_entries\b", detail):
                accesses.append(EntryAccess(detail.strip(), None, False, False))
            continue
        verb, index, condition = step.groups()
        seeks = verb == "SEARCH" and condition is not None
        accesses.append(EntryAccess(verb, index, seeks, seeks and not _RANGE_BOUND.search(condition or "")))
    return accesses


def _postgres_access(plan: str) -> list[EntryAccess]:
    """Each index or sequential scan node on ``vfs_entries``, an index scan seeking when its condition bounds the
    index's leading column.

    A plain, an index-only and a bitmap index scan of one index on one
    condition are one access; the bitmap heap scan above a bitmap index
    scan fetches the rows that scan named and is none of its own. An
    index condition on later columns alone reads the whole index, and a
    plan node on ``vfs_entries`` or its indexes of any other type is read
    as a scan, never dropped.
    """
    lines = plan.splitlines()
    accesses: list[EntryAccess] = []
    for position, line in enumerate(lines):
        node = _POSTGRES_NODE.search(line)
        if node is None and "(cost=" in line and re.search(r"\bvfs_entries", line):
            accesses.append(EntryAccess(line.strip(), None, False, False))
        if node is None or node.group(1) == "Bitmap Heap Scan":
            continue
        kind, using, target = node.groups()
        if kind == "Seq Scan":
            if target.split(".")[-1] == "vfs_entries":
                accesses.append(EntryAccess(kind, None, False, False))
            continue
        index = using or target
        if "vfs_entries" not in index:
            continue
        condition = _postgres_condition(lines[position + 1 :])
        seeks = condition is not None and _bounds_leading(index, condition)
        accesses.append(EntryAccess("Index Scan", index, seeks, seeks and not _RANGE_BOUND.search(condition or "")))
    return accesses


def _bounds_leading(index: str, condition: str) -> bool:
    """Whether a Postgres index condition names its index's leading column; on the others alone it walks the index."""
    leading = LEADING_COLUMNS.get(index.lower())
    return leading is None or re.search(rf"\b{leading}\b", condition) is not None


def _postgres_condition(following: list[str]) -> str | None:
    """The ``Index Cond`` of the node whose detail lines are *following*, up to the next node."""
    for line in following:
        if "->" in line:
            return None
        if "Index Cond:" in line:
            return line.split("Index Cond:", 1)[1]
    return None


_READERS = {"sqlite": _sqlite_plan, "postgresql": _postgres_plan}

_PLAN_TEXTS = {"sqlite": _sqlite_plan_text, "postgresql": _postgres_plan_text}

_ACCESSES = {"sqlite": _sqlite_access, "postgresql": _postgres_access}
