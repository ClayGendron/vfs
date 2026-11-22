"""Conformance-suite instantiations — one subclass per backend.

The contract itself lives in ``tests.support.storage_contract.StorageContract``;
this file only wires backends in. The memory leg is ``InMemoryStorage``
— ``DatabaseStorage`` over in-memory SQLite — so it runs the same
families as the sqlite-file leg, trash arc included; capability gating
skips only what a backend leaves undeclared.

Every leg carries the hashing embedder — no key, no download — so the
rebuild embed step runs on every engine. Real-server legs activate when
their ``VFS_TEST_<ENGINE>_URL`` variable is set and skip otherwise, so a
plain run never needs Docker. Servers come from
``docker/compose.test.yml`` (same file CI uses); each test gets a clean
slate in a schema of its own (``tests.support.server_schemas``) —
created before the backend's first touch, dropped at teardown — because
the server outlives the test where sqlite's tmp file does not. Schemas
make the legs reentrant: concurrent runs against one engine never tear
each other down, and a crashed run's leftover ``vfs_t_*`` schemas are
residue on an ephemeral-data stack, cleared by ``compose down``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.ranking.pins import assert_top10_pin
from tests.support.cursor_contract import CursorContract
from tests.support.grants_contract import GrantsContract
from tests.support.lexical_fidelity import assert_lexical_fidelity, assert_two_round_fidelity
from tests.support.plan_store import PlanBackend
from tests.support.server_schemas import server_storage
from tests.support.statements import is_statistics_statement
from tests.support.storage_contract import StorageContract
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database.dialects import bulk_insert
from vfs.storage.backends.database.segments import path_segments
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.backends.sqlite import SQLiteStorage

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy import Connection

    from vfs.results import Result


@pytest.mark.slow
class TestMemoryConformance(StorageContract, GrantsContract, CursorContract):
    """The contract on the in-memory backend, in the slow tier.

    It is the same ``DatabaseStorage`` over ``sqlite+aiosqlite:///:memory:``
    with a static pool, and every question here is asked of the file-backed
    class too; the default run proves the contract once and CI proves the
    pool shape.
    """

    engine_proven_by = "TestSqliteConformance"

    @pytest.fixture
    async def storage(self) -> AsyncIterator[InMemoryStorage]:
        storage = InMemoryStorage()
        yield storage
        await storage.close()


@pytest.fixture(scope="session")
def sqlite_template(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A provisioned sqlite file, built once per worker and copied under every file-backed storage.

    The contract proves the verbs, not provisioning; `test_engine.py`
    proves first touch from nothing. Copying costs 0.2 ms where the schema
    build cost 94 statements per test.
    """
    path = tmp_path_factory.mktemp("template") / "vfs.sqlite"

    async def build() -> None:
        storage = SQLiteStorage(path=path, embedder=HashEmbeddingProvider())
        assert (await storage.first_touch()).success, "the template must provision cleanly"
        await storage.close()

    asyncio.run(build())
    return path


class TestSqliteConformance(StorageContract, GrantsContract, CursorContract):
    plan_backend = PlanBackend("sqlite")

    @pytest.fixture
    async def storage(self, tmp_path: pathlib.Path, sqlite_template: pathlib.Path) -> AsyncIterator[DatabaseStorage]:
        db = tmp_path / "vfs.sqlite"
        shutil.copy(sqlite_template, db)
        storage = SQLiteStorage(path=db, embedder=HashEmbeddingProvider())
        yield storage
        await storage.close()


def _server_storage(env_var: str) -> AbstractAsyncContextManager[DatabaseStorage]:
    """A backend on *env_var*'s server, in a schema of its own, configured for this file."""
    return server_storage(env_var, embedder=HashEmbeddingProvider())


class TestStatisticsStatements:
    """The planner-statistics step is SQLite's alone: Postgres maintains its own."""

    @pytest.mark.parametrize(
        "leg",
        [
            pytest.param("sqlite", id="sqlite"),
            pytest.param("VFS_TEST_POSTGRES_URL", id="postgres", marks=pytest.mark.postgres),
        ],
    )
    async def test_a_write_issues_only_its_profiles_statistics_statements(
        self, leg: str, tmp_path: pathlib.Path, sqlite_template: pathlib.Path
    ) -> None:
        """Guards: a statistics statement reaching a server engine, whose profile declares no listing."""
        if leg == "sqlite":
            db = tmp_path / "vfs.sqlite"
            shutil.copy(sqlite_template, db)
            storage_cm = _closing(SQLiteStorage(path=db, embedder=HashEmbeddingProvider()))
        else:
            storage_cm = _server_storage(leg)
        async with storage_cm as storage:
            assert (await storage.first_touch()).success is True
            traced: list[tuple[str, str]] = []
            sync = storage._host.engine.sync_engine

            @event.listens_for(sync, "before_cursor_execute")
            def record(conn, cursor, statement, parameters, context, executemany) -> None:
                traced.append(("statement", statement))

            @event.listens_for(sync, "begin")
            def begun(conn) -> None:
                traced.append(("begin", ""))

            @event.listens_for(sync, "commit")
            def committed(conn) -> None:
                traced.append(("commit", ""))

            assert (await storage.write(entries=[Entry(path=Path("/one.txt"), content="x")])).success is True
            # The write's own statements: a crossing's pass runs after it returns and is pinned elsewhere.
            statistics = [
                index
                for index, (kind, sql) in enumerate(traced)
                if kind == "statement" and is_statistics_statement(sql)
            ]
            await storage._host.settle_statistics()
            if leg != "sqlite":
                assert statistics == []
                return
            assert len(statistics) >= 3
            begin = next(index for index, (kind, _sql) in enumerate(traced) if kind == "begin")
            commit = next(index for index, (kind, _sql) in enumerate(traced) if kind == "commit")
            assert all(begin < index < commit for index in statistics), traced


@asynccontextmanager
async def _closing(storage: DatabaseStorage) -> AsyncIterator[DatabaseStorage]:
    try:
        yield storage
    finally:
        await storage.close()


@pytest.mark.postgres
class TestPostgresConformance(StorageContract, GrantsContract, CursorContract):
    plan_backend = PlanBackend("postgres", "VFS_TEST_POSTGRES_URL")

    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            yield storage


@pytest.mark.postgres
class TestPostgresBulkInsertTransaction:
    """COPY rides the session's transaction — never asyncpg's autocommit.

    The adapter opens its driver transaction on the first statement, so
    a raw COPY issued first would land outside the rollback; the helper
    issues a statement before it. A duplicate under a savepoint surfaces
    as ``IntegrityError`` and leaves the outer transaction usable.
    """

    @staticmethod
    def _rows(count: int) -> list[dict[str, object]]:
        return [
            {
                "epoch": 1,
                "term": f"t{i:04d}",
                "block_no": 0,
                "doc_count": 1,
                "doc_ids": b"\x01",
                "tfs": b"\x01",
                "dls": b"\x02",
            }
            for i in range(count)
        ]

    async def test_a_first_statement_bulk_insert_rolls_back(self) -> None:
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            await storage.mkdir(path=Path("/warm"))
            postings = storage._host.tables.lex_postings
            async with storage._host.session_factory() as session:
                await bulk_insert(session, postings, self._rows(3))
                await session.rollback()
            async with storage._host.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(postings))
            assert count == 0

    async def test_a_duplicate_under_a_savepoint_leaves_the_transaction_usable(self) -> None:
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            await storage.mkdir(path=Path("/warm"))
            postings = storage._host.tables.lex_postings
            async with storage._host.session_factory() as session, session.begin():
                await bulk_insert(session, postings, self._rows(2))
                with pytest.raises(IntegrityError):
                    async with session.begin_nested():
                        await bulk_insert(session, postings, self._rows(1))
                await bulk_insert(session, postings, self._rows(3)[2:])
            async with storage._host.session_factory() as session:
                count = await session.scalar(select(func.count()).select_from(postings))
            assert count == 3


async def _one_increment_race(storage: DatabaseStorage) -> Result:
    """Stage a rival one increment ahead inside the guard's window.

    The rival lands through the write path's declared seam — after the
    snapshot read and staging, before any mutation statement — and the
    victim is the real public verb, so retry and classification run
    live; nothing is mirrored. Post-image inference cannot see this
    rival: the row lands on exactly the version the victim staged, so
    only statement-native attribution can fail the batch. The handler
    uninstalls itself so the rival's own write (and any retry of the
    victim) passes the seam untouched.
    """
    target = Path("/race.txt")
    assert (await storage.write(entries=[Entry(path=target, content="base")])).success

    async def rival() -> None:
        seams.clear("write:before-apply")
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success

    with seams.installed("write:before-apply", rival):
        return await storage.write(entries=[Entry(path=target, content="mine")])


@pytest.mark.postgres
class TestPostgresRivalRedrive:
    async def test_one_increment_rival_redrives_to_success(self) -> None:
        """REPEATABLE READ surfaces the rival as 40001 and the method redrives.

        The staged race resolves to a clean success: the whole method
        restarts from a fresh snapshot and lands on top of the rival's
        version, never a torn row.
        """
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is True
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "version"}))
            after = read.observations[0]
            assert after.content == "mine"
            assert after.version == 3


async def _purge_sweeps_a_mid_purge_rival(env_var: str) -> None:
    """A rival write landing inside the purge window is swept, not orphaned.

    Writes are not serialized with topology, so a rival can commit a new
    child between the purge's id collection and its deletes. The purge's
    re-collection must sweep it with the subtree — the stale-id-list
    alternative left a permanent orphan row on every real engine.
    """
    async with _server_storage(env_var) as storage:
        assert (await storage.mkdir(path=Path("/d"))).success
        assert (await storage.write(entries=[Entry(path=Path("/d/base.txt"), content="x")])).success
        rival_results: list[Result] = []

        async def rival() -> None:
            seams.clear("purge:post-collect")
            rival_results.append(await storage.write(entries=[Entry(path=Path("/d/fresh.txt"), content="rival")]))

        with seams.installed("purge:post-collect", rival):
            victim = await storage.sweep(path=Path("/d"))
        assert victim.success is True, victim.errors
        assert rival_results and rival_results[0].success is True
        assert (await storage.stat(path=Path("/d/fresh.txt"))).success is False
        assert (await storage.stat(path=Path("/d"))).success is False
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            subtree = (entry.c.path == "/d") | entry.c.path.like("/d/%")
            leftovers = (await session.execute(select(entry.c.path).where(subtree))).scalars().all()
        assert leftovers == []


async def _serialization_point_blocks_a_rival_topology_verb(env_var: str) -> None:
    """A rival topology verb launched mid-window waits out the point.

    The rival move is spawned — never awaited — inside the delete's
    post-snapshot window, and the window stays open until the move waits
    on a lock or ends. With the point it waits, runs only after the victim
    commits, and finds its source already trashed. Without the point it
    commits mid-window, and the delete misses its own target.
    """
    async with _server_storage(env_var) as storage:
        assert (await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])).success
        tasks: list[asyncio.Task[Result]] = []

        async def rival() -> None:
            seams.clear("delete:post-snapshot")
            backends: list[int] = []

            def writer_reached(conn: Connection, options: dict[str, object]) -> None:
                driver = conn.connection.driver_connection
                if options.get("vfs_writer") and driver is not None:
                    backends.append(driver.get_server_pid())

            event.listen(storage._host.engine.sync_engine, "set_connection_execution_options", writer_reached)
            move = storage.move(operations=[ResolvedPair(src=Path("/x.txt"), dest=Path("/y.txt"))])
            tasks.append(asyncio.ensure_future(move))
            await _waits_on_a_lock_or_ends(storage, backends, tasks[0])

        with seams.installed("delete:post-snapshot", rival):
            victim = await storage.delete(path=Path("/x.txt"))
        rival_result = await tasks[0]
        assert victim.success is True, victim.errors
        assert rival_result.success is False
        assert rival_result.errors[0].kind == ErrorKind.not_found
        assert (await storage.stat(path=Path("/y.txt"))).success is False


_WAITING = text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid")
"""What the backend with ``:pid`` waits on; ``Lock`` while it queues behind another transaction's lock."""


async def _waits_on_a_lock_or_ends(storage: DatabaseStorage, backends: list[int], task: asyncio.Task[Result]) -> None:
    """Return once *task* has ended or the server backend it writes on waits for a lock, whichever comes first."""
    async with storage._host.engine.connect() as probe:
        await probe.execution_options(isolation_level="AUTOCOMMIT")
        while not task.done():
            if backends and (await probe.execute(_WAITING, {"pid": backends[0]})).scalar() == "Lock":
                return
            await asyncio.sleep(0)


@pytest.mark.postgres
class TestPostgresTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_POSTGRES_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_POSTGRES_URL")


async def _segment_postings_mirror(storage: DatabaseStorage) -> None:
    """Postings == recomputed segments of every stored path, every kind."""
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        entries = (await session.execute(select(tables.entry.c.entry_id, tables.entry.c.path))).all()
        postings = (await session.execute(select(tables.segments.c.segment, tables.segments.c.entry_id))).all()
    truth = {(segment, entry_id) for entry_id, path in entries for segment in path_segments(path)}
    assert {(row.segment, row.entry_id) for row in postings} == truth


async def _segment_cascades_hold_the_mirror(env_var: str) -> None:
    """The segment cascade statements on a real engine, verb by verb.

    The rename fast-path UPDATE, the per-segment delete+insert general
    path, the purge delete, and the trash-chain mint all run under the
    engine's own dialect arms; the mirror is re-derived after every verb,
    and a final rebuild must find zero drift.
    """
    async with _server_storage(env_var) as storage:
        entries = [
            Entry(path=Path("/a/x/a/f.txt"), content="recurring name"),
            Entry(path=Path("/a/x/g.txt"), content="plain"),
            Entry(path=Path("/a/y/h.txt"), content="sibling"),
            Entry(path=Path("/a2/z/i.txt"), content="second tree"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True
        await _segment_postings_mirror(storage)
        # Batch shapes throughout: width is a pinned dimension of the
        # maintenance statements, not a single-target convention.
        moves = [ResolvedPair(src=Path("/a"), dest=Path("/b")), ResolvedPair(src=Path("/a2"), dest=Path("/b2"))]
        assert (await storage.move(operations=moves)).success is True
        await _segment_postings_mirror(storage)
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/b/x"), dest=Path("/c"))])).success is True
        await _segment_postings_mirror(storage)
        targets = [Observation(path=Path("/b")), Observation(path=Path("/b2"))]
        assert (await storage.delete(observations=targets)).success is True
        await _segment_postings_mirror(storage)
        assert (await storage.restore(observations=targets)).success is True
        await _segment_postings_mirror(storage)
        assert (await storage.sweep(path=Path("/c"))).success is True
        await _segment_postings_mirror(storage)
        rebuilt = await storage.rebuild()
        assert rebuilt.success is True
        assert rebuilt.errors == []


@pytest.mark.postgres
class TestPostgresSegmentCascades:
    async def test_cascades_hold_the_mirror(self) -> None:
        await _segment_cascades_hold_the_mirror("VFS_TEST_POSTGRES_URL")


async def _encoded_kind_index_serves_the_overlay(env_var: str) -> None:
    """The composite (encoded, kind) index on a real engine, both flag states.

    Grep must find fresh writes through the scan-tier overlay (encoded=0
    rows seek through the composite) and the same rows post-rebuild
    (encoded flipped); reflection pins the index shape the engine built.
    """
    async with _server_storage(env_var) as storage:
        entries = [Entry(path=Path(f"/src/f{i}.txt"), content=f"needle_{i} haystack") for i in range(3)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        fresh = await storage.grep(pattern="haystack")
        assert sum(len(o.matches or ()) for o in fresh.observations) == 3
        assert (await storage.rebuild()).success is True
        encoded = await storage.grep(pattern="haystack")
        assert sum(len(o.matches or ()) for o in encoded.observations) == 3
        # Reflection runs inside the schema's lifetime, before teardown drops it.
        table = storage._host.tables.entry
        engine = create_async_engine(os.environ[env_var])
        try:
            async with engine.connect() as conn:
                indexes = await conn.run_sync(lambda sync: inspect(sync).get_indexes(table.name, schema=table.schema))
        finally:
            await engine.dispose()
        by_name = {str(index["name"]).lower(): index for index in indexes}
        columns = by_name["ix_vfs_entries_encoded_kind"]["column_names"]
        assert [c.lower() for c in columns if c is not None] == ["encoded", "kind"]
        assert "ix_vfs_entries_encoded" not in by_name


@pytest.mark.postgres
class TestPostgresEncodedKindIndex:
    async def test_index_serves_the_overlay(self) -> None:
        await _encoded_kind_index_serves_the_overlay("VFS_TEST_POSTGRES_URL")


async def _a_directory_is_never_awaiting_the_index(storage: DatabaseStorage) -> None:
    """A directory row holds ``encoded`` true through mkdir, copy, delete and restore on this engine.

    The flag means nothing of the row awaits the gram index, which is
    true of every directory; the delete's ``CASE`` keeps it so on an
    engine with no boolean value expression.
    """
    entry = storage._host.tables.entry

    async def encoded(path: str) -> bool:
        async with storage._host.session_factory() as session:
            return (await session.execute(select(entry.c.encoded).where(entry.c.path == path))).scalar_one()

    assert (await storage.mkdir(path=Path("/d"))).success is True
    assert await encoded("/d") is True
    assert (await storage.copy(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))])).success is True
    assert await encoded("/e") is True
    assert (await storage.delete(path=Path("/d"))).success is True
    assert await encoded("/d") is True
    assert (await storage.restore(path=Path("/d"))).success is True
    assert await encoded("/d") is True


async def test_a_directory_is_never_awaiting_the_index_on_sqlite(
    tmp_path: pathlib.Path, sqlite_template: pathlib.Path
) -> None:
    db = tmp_path / "vfs.sqlite"
    shutil.copy(sqlite_template, db)
    async with _closing(SQLiteStorage(path=db, embedder=HashEmbeddingProvider())) as storage:
        await _a_directory_is_never_awaiting_the_index(storage)


@pytest.mark.postgres
async def test_a_directory_is_never_awaiting_the_index_on_postgres() -> None:
    async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
        await _a_directory_is_never_awaiting_the_index(storage)


async def _lexical_fidelity(env_var: str) -> None:
    """The lexical build lands and the stored BM25 weights rank as pure BM25 does."""
    async with _server_storage(env_var) as storage:
        await assert_lexical_fidelity(storage)


@pytest.mark.postgres
class TestPostgresLexicalFidelity:
    async def test_stored_weights_rank_as_pure_bm25(self) -> None:
        await _lexical_fidelity("VFS_TEST_POSTGRES_URL")


async def _ranking_pin(env_var: str) -> None:
    """The golden corpus ranks to the same ordered top-10 on this engine as on sqlite."""
    async with _server_storage(env_var) as storage:
        await assert_top10_pin(storage)


@pytest.mark.postgres
class TestPostgresRankingPin:
    async def test_ordered_top10_matches_the_pin(self) -> None:
        await _ranking_pin("VFS_TEST_POSTGRES_URL")


async def _lexical_build_beyond_a_page(env_var: str) -> None:
    """A corpus larger than one scan page builds: the build writes between
    pages on the same connection, which a driver without multiple active
    result sets refuses while a cursor is still open (invisible below one
    page). The same corpus spans blocks, so the two-round fetch is
    refereed here on every engine."""
    async with _server_storage(env_var) as storage:
        await assert_two_round_fidelity(storage, count=600)
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            docs = (await conn.execute(select(func.count()).select_from(tables.lex_docs))).scalar_one()
        assert docs == 600


@pytest.mark.postgres
class TestPostgresLexicalBuildBeyondAPage:
    async def test_a_corpus_larger_than_one_page_builds(self) -> None:
        await _lexical_build_beyond_a_page("VFS_TEST_POSTGRES_URL")


async def _content_bytes_audit(env_var: str, cast_sql: str | None) -> None:
    """The per-engine bytes-cast audit: opt-in evidence, str-arm correctness.

    Every server profile keeps ``content_bytes`` declined until audited.
    The leg pins the live str arm on multi-byte content, then records the
    opt-in precondition where a cheap cast form exists: the cast must
    yield exactly the body's UTF-8 bytes. A failing cast assertion is the
    audit verdict — that engine's cast transcodes, keep it declined.
    """
    body = "hé\nwörld🚀 needle\nplain é\n"
    async with _server_storage(env_var) as storage:
        assert storage._host.profile.content_bytes is False
        assert (await storage.write(entries=[Entry(path=Path("/u.txt"), content=body)], parents=True)).success is True
        result = await storage.grep(pattern="needle", columns=frozenset({"content"}))
        assert [str(o.path) for o in result.observations] == ["/u.txt"]
        assert result.observations[0].content == body
        if cast_sql is not None:
            # The audit SQL names the content table inside the test's schema.
            statement = cast_sql.format(content=storage._host.tables.content.fullname)
            async with storage._host.session_factory() as session:
                fetched = (await session.execute(text(statement))).scalar_one()
            assert bytes(fetched) == body.encode()


@pytest.mark.postgres
class TestPostgresContentBytesAudit:
    async def test_cast_yields_utf8_bytes(self) -> None:
        # convert_to transcodes to UTF-8 regardless of server encoding.
        await _content_bytes_audit("VFS_TEST_POSTGRES_URL", "SELECT convert_to(content, 'UTF8') FROM {content}")


# ---------------------------------------------------------------------------
# The bytes body's column, as each engine's catalog reports it
# ---------------------------------------------------------------------------


async def _blob_column(env_var: str, probe: str) -> tuple[object, ...]:
    """Provision a mount on *env_var*'s server and run *probe* against its catalog."""
    async with _server_storage(env_var) as storage:
        assert (await storage.first_touch()).success is True
        schema = storage._host.tables.blobs.schema
        assert schema is not None
        async with storage._host.session_factory() as session:
            row = (await session.execute(text(probe), {"schema": schema})).one()
    return tuple(row)


@pytest.mark.postgres
class TestPostgresBlobColumn:
    async def test_the_body_is_bytea_stored_external(self) -> None:
        # EXTERNAL: file bytes are pre-compressed, and substring reads a range.
        kind, storage = await _blob_column(
            "VFS_TEST_POSTGRES_URL",
            "SELECT format_type(a.atttypid, a.atttypmod), a.attstorage::text FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relname = 'vfs_blobs' AND a.attname = 'data'",
        )
        assert (kind, storage) == ("bytea", "e")
