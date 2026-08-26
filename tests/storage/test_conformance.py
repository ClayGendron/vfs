"""Conformance-suite instantiations — one subclass per backend.

The contract itself lives in ``tests.support.storage_contract.StorageContract``;
this file only wires backends in. The memory leg is ``InMemoryStorage``
— ``DatabaseStorage`` over in-memory SQLite — so it runs the same
families as the sqlite-file leg, trash arc included; capability gating
skips only what a backend leaves undeclared.

Real-server legs activate when their ``VFS_TEST_<ENGINE>_URL`` variable
is set and skip otherwise, so a plain run never needs Docker. Servers
come from ``docker/compose.test.yml`` (same file CI uses); each test
gets a clean slate in its own minted table namespace — created by the
backend's own first touch, dropped at teardown — because the server
outlives the test where sqlite's tmp file does not. Namespacing makes
the legs reentrant: concurrent runs against one engine never tear each
other down, and a crashed run's leftover ``vfs_*`` tables are residue
on an ephemeral-data stack, cleared by ``compose down``.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.support.lexical_fidelity import assert_lexical_fidelity
from tests.support.storage_contract import StorageContract
from vfs.models import Entry, Observation
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database.segments import path_segments
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator

    from vfs.results import Result


class TestMemoryConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[InMemoryStorage]:
        storage = InMemoryStorage()
        yield storage
        await storage.close()


class TestSqliteConformance(StorageContract):
    @pytest.fixture
    async def storage(self, tmp_path: pathlib.Path) -> AsyncIterator[DatabaseStorage]:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite")
        yield storage
        await storage.close()


@asynccontextmanager
async def _server_storage(env_var: str) -> AsyncIterator[DatabaseStorage]:
    """A fresh backend on the server named by ``env_var``, in a minted namespace.

    Each run mints its own table namespace, so concurrent runs against
    one engine never tear each other down; teardown drops exactly what
    this run minted. Advisory locks isolate too — the lock key derives
    from the table name.
    """
    url = os.environ.get(env_var)
    if url is None:
        pytest.skip(f"{env_var} is not set")
    table_name = f"vfs_{uuid4().hex[:10]}"
    storage = DatabaseStorage(url=url, table_name=table_name)
    try:
        yield storage
    finally:
        await storage.close()
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(build_vfs_tables(table_name=table_name).metadata.drop_all)
        finally:
            await engine.dispose()


@pytest.mark.postgres
class TestPostgresConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_POSTGRES_URL") as storage:
            yield storage


@pytest.mark.mysql
class TestMySQLConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_MYSQL_URL") as storage:
            yield storage


@pytest.mark.mssql
class TestMSSQLConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            yield storage


@pytest.mark.oracle
class TestOracleConformance(StorageContract):
    @pytest.fixture
    async def storage(self) -> AsyncIterator[DatabaseStorage]:
        async with _server_storage("VFS_TEST_ORACLE_URL") as storage:
            yield storage


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


@pytest.mark.mssql
class TestMSSQLBindBudget:
    async def test_bumping_over_a_thousand_parents_stays_under_the_cap(self) -> None:
        """The steady-state ingest shape: one batch of files under more
        pre-existing parents than a single bump statement may carry —
        chunked under the measured bind budget, never the raw cap."""
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            n = 1_100
            dirs = [Entry(path=Path(f"/p{i:04d}"), kind="directory") for i in range(n)]
            assert (await storage.write(entries=dirs)).success is True
            files = [Entry(path=Path(f"/p{i:04d}/f.txt"), content="x") for i in range(n)]
            result = await storage.write(entries=files)
            assert result.success is True, result.errors[:3]


@pytest.mark.mssql
class TestMSSQLTornRowRegression:
    async def test_one_increment_rival_classifies_conflict(self) -> None:
        """READ COMMITTED cannot redrive: the guard must classify, never tear.

        A false success is a torn row — the rival's entry columns over
        our content rows — which is exactly what the pre-079 read-back
        produced on this engine.
        """
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is False
            assert [e.kind for e in result.errors] == [VFSErrorKind.conflict]
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "content_hash"}))
            after = read.observations[0]
            assert after.content == "rival"
            assert after.content_hash == Entry(path=Path("/race.txt"), content=after.content).content_hash


@pytest.mark.postgres
class TestPostgresRivalRedrive:
    async def test_one_increment_rival_redrives_to_success(self) -> None:
        """REPEATABLE READ surfaces the rival as 40001 and the method redrives.

        The same staged race that must classify ``conflict`` on MSSQL
        resolves to a clean success here: the whole method restarts from
        a fresh snapshot and lands on top of the rival's version.
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
    post-snapshot window: it must block on the serialization point and
    run only after the victim commits, so it finds its source already
    trashed. Without the point the rival would commit mid-window and
    both verbs would report success.
    """
    async with _server_storage(env_var) as storage:
        assert (await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])).success
        tasks: list[asyncio.Task[Result]] = []

        async def rival() -> None:
            seams.clear("delete:post-snapshot")
            move = storage.move(operations=[ResolvedPair(src=Path("/x.txt"), dest=Path("/y.txt"))])
            tasks.append(asyncio.ensure_future(move))
            # Give the rival time to reach — and block on — the point.
            await asyncio.sleep(0.5)

        with seams.installed("delete:post-snapshot", rival):
            victim = await storage.delete(path=Path("/x.txt"))
        rival_result = await asyncio.wait_for(tasks[0], timeout=60)
        assert victim.success is True, victim.errors
        assert rival_result.success is False
        assert rival_result.errors[0].kind == VFSErrorKind.not_found
        assert (await storage.stat(path=Path("/y.txt"))).success is False


@pytest.mark.postgres
class TestPostgresTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_POSTGRES_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_POSTGRES_URL")


@pytest.mark.mysql
class TestMySQLTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_MYSQL_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_MYSQL_URL")


@pytest.mark.mssql
class TestMSSQLTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_MSSQL_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_MSSQL_URL")


@pytest.mark.oracle
class TestOracleTopologyRivals:
    async def test_purge_sweeps_a_mid_purge_rival_write(self) -> None:
        await _purge_sweeps_a_mid_purge_rival("VFS_TEST_ORACLE_URL")

    async def test_the_serialization_point_blocks_a_rival_topology_verb(self) -> None:
        await _serialization_point_blocks_a_rival_topology_verb("VFS_TEST_ORACLE_URL")


@pytest.mark.mysql
class TestMySQLFlagFlipRoundTrips:
    async def test_flag_flips_are_one_statement_per_chunk_not_per_row(self) -> None:
        """No UPDATE…RETURNING on this family: the flips must ride
        row-constructor IN chunks — the per-row executemany fallback is
        one driver round trip per entry, 20k of them at a 10k batch."""
        async with _server_storage("VFS_TEST_MYSQL_URL") as storage:
            entries = [Entry(path=Path(f"/f{i:02}.txt"), content=f"needle body {i:02}") for i in range(10)]
            assert (await storage.write(entries=entries)).success is True
            updates: list[tuple[str, bool]] = []

            def record(conn, cursor, statement, parameters, context, executemany) -> None:
                if statement.startswith("UPDATE") and ("chunked" in statement or "encoded" in statement):
                    updates.append((statement, executemany))

            event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
            assert (await storage.reindex()).success is True
            assert all(many is False for _, many in updates)
            flips = [(s, many) for s, many in updates if "version" in s]
            assert len(flips) == 2  # ten pairs fit one statement per flag
            assert len(updates) == len(flips)  # no stale generations: the probe skips the re-dirty


@pytest.mark.mssql
class TestMSSQLChunkGuardRegression:
    async def test_a_write_racing_the_chunk_window_keeps_the_entry_dirty(self) -> None:
        """READ COMMITTED lets the flip current-read past the dirty scan.

        Only the version guard keeps a raced entry pending: without it
        the flip stamps ``chunked`` over the rival's fresh body, the
        stale chunks encode at the next build, and the fresh content is
        never searchable again — silently.
        """
        async with _server_storage("VFS_TEST_MSSQL_URL") as storage:
            assert (await storage.write(entries=[Entry(path=Path("/r.txt"), content="stale needle")])).success

            async def rival() -> None:
                seams.clear("reindex:before-chunk-flip")
                fresh = Entry(path=Path("/r.txt"), content="fresh needle")
                assert (await storage.write(entries=[fresh], overwrite=True)).success is True

            with seams.installed("reindex:before-chunk-flip", rival):
                assert (await storage.reindex()).success is True
            found = await storage.grep(pattern="fresh")
            assert [o.path for o in found.observations] == ["/r.txt"]
            assert (await storage.reindex()).success is True
            found = await storage.grep(pattern="fresh")
            assert [o.path for o in found.observations] == ["/r.txt"]


@pytest.mark.mysql
class TestMySQLTornRowRegression:
    async def test_one_increment_rival_redrives_to_success(self) -> None:
        """InnoDB's REPEATABLE READ current-reads past the rival — no 40001.

        The guarded UPDATE matches nothing, and at this isolation a
        re-probe would report the stale snapshot rather than the rival —
        so the declared ``guard_miss`` mode redrives the whole method
        from fresh state instead of classifying off a lying probe. The
        outcome converges with the Postgres redrive: a clean success on
        top of the rival's version, never a torn row.
        """
        async with _server_storage("VFS_TEST_MYSQL_URL") as storage:
            result = await _one_increment_race(storage)
            assert result.success is True
            read = await storage.read(path=Path("/race.txt"), columns=frozenset({"content", "content_hash", "version"}))
            after = read.observations[0]
            assert after.content == "mine"
            assert after.version == 3
            assert after.content_hash == Entry(path=Path("/race.txt"), content=after.content).content_hash


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
    and a final reindex must find zero drift.
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
        reindexed = await storage.reindex()
        assert reindexed.success is True
        assert reindexed.errors == []


@pytest.mark.postgres
class TestPostgresSegmentCascades:
    async def test_cascades_hold_the_mirror(self) -> None:
        await _segment_cascades_hold_the_mirror("VFS_TEST_POSTGRES_URL")


@pytest.mark.mysql
class TestMySQLSegmentCascades:
    async def test_cascades_hold_the_mirror(self) -> None:
        await _segment_cascades_hold_the_mirror("VFS_TEST_MYSQL_URL")


@pytest.mark.mssql
class TestMSSQLSegmentCascades:
    async def test_cascades_hold_the_mirror(self) -> None:
        await _segment_cascades_hold_the_mirror("VFS_TEST_MSSQL_URL")


@pytest.mark.oracle
class TestOracleSegmentCascades:
    async def test_cascades_hold_the_mirror(self) -> None:
        await _segment_cascades_hold_the_mirror("VFS_TEST_ORACLE_URL")


async def _encoded_kind_index_serves_the_overlay(env_var: str) -> None:
    """The composite (encoded, kind) index on a real engine, both flag states.

    Grep must find fresh writes through the scan-tier overlay (encoded=0
    rows seek through the composite) and the same rows post-reindex
    (encoded flipped); reflection pins the index shape the engine built.
    """
    async with _server_storage(env_var) as storage:
        entries = [Entry(path=Path(f"/src/f{i}.txt"), content=f"needle_{i} haystack") for i in range(3)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        fresh = await storage.grep(pattern="haystack")
        assert sum(len(o.matches or ()) for o in fresh.observations) == 3
        assert (await storage.reindex()).success is True
        encoded = await storage.grep(pattern="haystack")
        assert sum(len(o.matches or ()) for o in encoded.observations) == 3
        # Reflection runs inside the namespace's lifetime, before teardown
        # drops the minted tables.
        table = storage._host.tables.entry.name
        engine = create_async_engine(os.environ[env_var])
        try:
            async with engine.connect() as conn:
                indexes = await conn.run_sync(lambda sync: inspect(sync).get_indexes(table))
        finally:
            await engine.dispose()
        by_name = {str(index["name"]).lower(): index for index in indexes}
        columns = by_name[f"ix_{table}_encoded_kind"]["column_names"]
        assert [c.lower() for c in columns if c is not None] == ["encoded", "kind"]
        assert f"ix_{table}_encoded" not in by_name


@pytest.mark.postgres
class TestPostgresEncodedKindIndex:
    async def test_index_serves_the_overlay(self) -> None:
        await _encoded_kind_index_serves_the_overlay("VFS_TEST_POSTGRES_URL")


@pytest.mark.mysql
class TestMySQLEncodedKindIndex:
    async def test_index_serves_the_overlay(self) -> None:
        await _encoded_kind_index_serves_the_overlay("VFS_TEST_MYSQL_URL")


@pytest.mark.mssql
class TestMSSQLEncodedKindIndex:
    async def test_index_serves_the_overlay(self) -> None:
        await _encoded_kind_index_serves_the_overlay("VFS_TEST_MSSQL_URL")


@pytest.mark.oracle
class TestOracleEncodedKindIndex:
    async def test_index_serves_the_overlay(self) -> None:
        await _encoded_kind_index_serves_the_overlay("VFS_TEST_ORACLE_URL")


async def _lexical_fidelity(env_var: str) -> None:
    """The lexical build lands and the stored BM25 weights rank as pure BM25 does."""
    async with _server_storage(env_var) as storage:
        await assert_lexical_fidelity(storage)


@pytest.mark.postgres
class TestPostgresLexicalFidelity:
    async def test_stored_weights_rank_as_pure_bm25(self) -> None:
        await _lexical_fidelity("VFS_TEST_POSTGRES_URL")


@pytest.mark.mysql
class TestMySQLLexicalFidelity:
    async def test_stored_weights_rank_as_pure_bm25(self) -> None:
        await _lexical_fidelity("VFS_TEST_MYSQL_URL")


@pytest.mark.mssql
class TestMSSQLLexicalFidelity:
    async def test_stored_weights_rank_as_pure_bm25(self) -> None:
        await _lexical_fidelity("VFS_TEST_MSSQL_URL")


@pytest.mark.oracle
class TestOracleLexicalFidelity:
    async def test_stored_weights_rank_as_pure_bm25(self) -> None:
        await _lexical_fidelity("VFS_TEST_ORACLE_URL")


async def _lexical_build_beyond_a_page(env_var: str) -> None:
    """A corpus larger than one scan page builds: the build writes between
    pages on the same connection, which a driver without multiple active
    result sets refuses while a cursor is still open (caught on SQL Server
    at 2,000 files; invisible below one page)."""
    async with _server_storage(env_var) as storage:
        entries = [Entry(path=Path(f"/p/{i:04}.txt"), content=f"page body {i} term{i % 7}\n") for i in range(600)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        result = await storage.reindex()
        assert result.success is True, result.errors
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            docs = (await conn.execute(select(func.count()).select_from(tables.lex_docs))).scalar_one()
        assert docs == 600


@pytest.mark.postgres
class TestPostgresLexicalBuildBeyondAPage:
    async def test_a_corpus_larger_than_one_page_builds(self) -> None:
        await _lexical_build_beyond_a_page("VFS_TEST_POSTGRES_URL")


@pytest.mark.mysql
class TestMySQLLexicalBuildBeyondAPage:
    async def test_a_corpus_larger_than_one_page_builds(self) -> None:
        await _lexical_build_beyond_a_page("VFS_TEST_MYSQL_URL")


@pytest.mark.mssql
class TestMSSQLLexicalBuildBeyondAPage:
    async def test_a_corpus_larger_than_one_page_builds(self) -> None:
        await _lexical_build_beyond_a_page("VFS_TEST_MSSQL_URL")


@pytest.mark.oracle
class TestOracleLexicalBuildBeyondAPage:
    async def test_a_corpus_larger_than_one_page_builds(self) -> None:
        await _lexical_build_beyond_a_page("VFS_TEST_ORACLE_URL")


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
            # The audit SQL names the minted namespace's content table.
            statement = cast_sql.format(content=storage._host.tables.content.name)
            async with storage._host.session_factory() as session:
                fetched = (await session.execute(text(statement))).scalar_one()
            assert bytes(fetched) == body.encode()


@pytest.mark.postgres
class TestPostgresContentBytesAudit:
    async def test_cast_yields_utf8_bytes(self) -> None:
        # convert_to transcodes to UTF-8 regardless of server encoding.
        await _content_bytes_audit("VFS_TEST_POSTGRES_URL", "SELECT convert_to(content, 'UTF8') FROM {content}")


@pytest.mark.mysql
class TestMySQLContentBytesAudit:
    async def test_cast_yields_utf8_bytes(self) -> None:
        # BINARY yields column-charset bytes: UTF-8 iff the table is utf8mb4.
        await _content_bytes_audit("VFS_TEST_MYSQL_URL", "SELECT CAST(content AS BINARY) FROM {content}")


@pytest.mark.mssql
class TestMSSQLContentBytesAudit:
    async def test_cast_yields_utf8_bytes(self) -> None:
        # The column is VARCHAR(max) under the pinned UTF-8 collation, so
        # VARBINARY reinterprets — NVARCHAR would transcode UTF-16 here.
        await _content_bytes_audit("VFS_TEST_MSSQL_URL", "SELECT CAST(content AS VARBINARY(MAX)) FROM {content}")


@pytest.mark.oracle
class TestOracleContentBytesAudit:
    async def test_no_cheap_cast_form_stays_declined(self) -> None:
        # CLOB reaches bytes only through DBMS_LOB conversion in the
        # database charset — a copy, not a reinterpretation; str arm only.
        await _content_bytes_audit("VFS_TEST_ORACLE_URL", None)
