"""Tests for the ranking-signal phase and probe — ``storage/backends/database/signals.py``.

The phase collects the live graph, computes each declared prior off the
event loop, and publishes it under a fresh generation; glean probes the
stored values for its candidates and multiplies the fused score. The
engine legs run the same loop against the four servers.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from tests.support.database_helpers import _url
from vfs.models import Edge, Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import signals as phase
from vfs.storage.backends.database.signals import collect_graph, signal_factors, signal_values
from vfs.storage.ranking import Log1p, PageRank, PathShape, Ranker, Signal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

ENGINE_LEGS = [
    pytest.param("VFS_TEST_POSTGRES_URL", marks=pytest.mark.postgres, id="postgres"),
    pytest.param("VFS_TEST_MARIADB_URL", marks=pytest.mark.mariadb, id="mariadb"),
    pytest.param("VFS_TEST_MSSQL_URL", marks=pytest.mark.mssql, id="mssql"),
    pytest.param("VFS_TEST_ORACLE_URL", marks=pytest.mark.oracle, id="oracle"),
]

CENTRALITY = Signal("centrality", weight=0.5)

# Three files, all matching "needle"; b is referenced by a and c.
ENTRIES = [
    Entry(path=Path("/a.md"), content="needle alpha"),
    Entry(path=Path("/deep/b.md"), content="needle beta"),
    Entry(path=Path("/deep/c.md"), content="needle gamma"),
]
EDGES = [
    Edge(source=Path("/a.md"), target=Path("/deep/b.md"), edge_type="ref"),
    Edge(source=Path("/deep/c.md"), target=Path("/deep/b.md"), edge_type="ref"),
]


def _mount(tmp_path, ranker: Ranker | None = None) -> DatabaseStorage:
    return DatabaseStorage(url=_url(tmp_path), ranker=ranker or Ranker(signals=(CENTRALITY,)))


async def _seed(storage: DatabaseStorage, *, edges: bool = True) -> None:
    assert (await storage.write(entries=ENTRIES, parents=True)).success is True
    if edges:
        assert (await storage.mkedge(edges=EDGES)).success is True


async def _stored(storage: DatabaseStorage) -> dict[tuple[str, str], float]:
    """Every stored row as ``(signal, path) → value``."""
    tables = storage._host.tables
    entry, table = tables.entry, tables.signals
    async with storage._host.session_factory() as session:
        rows = (
            await session.execute(
                select(table.c.signal, entry.c.path, table.c.value).join(entry, entry.c.entry_id == table.c.entry_id)
            )
        ).all()
    return {(row.signal, row.path): row.value for row in rows}


async def _pointers(storage: DatabaseStorage) -> dict[str, tuple[str, str, int]]:
    epochs = storage._host.tables.signal_epochs
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(epochs))).all()
    return {row.signal: (row.generation, row.options_hash, row.row_count) for row in rows}


async def _count(storage: DatabaseStorage, table) -> int:
    async with storage._host.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(table))).scalar_one()


def _order(result) -> list[str]:
    return [str(row.path) for row in result.observations]


def _legs(result) -> dict:
    assert result.model_extra is not None
    return result.model_extra["legs"]


def _signal_records(result) -> list[str]:
    return [error.data["signal"] for error in result.errors if error.data and error.data.get("leg") == "signal"]


# ---------------------------------------------------------------------------
# The phase
# ---------------------------------------------------------------------------


class TestPhase:
    async def test_reindex_stores_the_prior_sparse_and_points_at_its_generation(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        stored = await _stored(storage)
        assert stored[("centrality", "/deep/b.md")] == 1.0
        # a and c earn a smoothed share; every stored value is above zero.
        assert all(0.0 < value <= 1.0 for value in stored.values())
        pointers = await _pointers(storage)
        assert set(pointers) == {"centrality"}
        assert pointers["centrality"][1:] == (CENTRALITY.options_hash(), len(stored))
        await storage.close()

    async def test_a_second_reindex_replaces_the_generation_whole(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        first = (await _pointers(storage))["centrality"][0]
        assert (await storage.rmedge(edges=EDGES[:1])).success is True
        assert (await storage.reindex()).success is True
        second = (await _pointers(storage))["centrality"][0]
        assert second != first
        table = storage._host.tables.signals
        async with storage._host.session_factory() as session:
            generations = set((await session.execute(select(table.c.generation))).scalars())
        assert generations == {second}
        await storage.close()

    async def test_undeclared_signals_are_swept(self, tmp_path) -> None:
        storage = _mount(tmp_path, Ranker(signals=(CENTRALITY, Signal("shape", measure=PathShape()))))
        await _seed(storage)
        assert (await storage.reindex()).success is True
        assert set(await _pointers(storage)) == {"centrality", "shape"}
        await storage.close()
        narrowed = _mount(tmp_path, Ranker(signals=(CENTRALITY,)))
        assert (await narrowed.reindex()).success is True
        assert set(await _pointers(narrowed)) == {"centrality"}
        assert {signal for signal, _ in await _stored(narrowed)} == {"centrality"}
        await narrowed.close()
        plain = _mount(tmp_path, Ranker())
        assert (await plain.reindex()).success is True
        assert await _pointers(plain) == {} and await _count(plain, plain._host.tables.signals) == 0
        await plain.close()

    async def test_a_zero_edge_mount_writes_no_rows_but_a_pointer(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage, edges=False)
        assert (await storage.reindex()).success is True
        assert await _stored(storage) == {}
        assert (await _pointers(storage))["centrality"][2] == 0
        await storage.close()

    async def test_the_collect_pass_pages_and_skips_edges_off_the_live_set(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(phase, "SCAN_PAGE_ROWS", 2)
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.delete(path=Path("/a.md"))).success is True
        async with storage._host.session_factory() as session:
            graph = await collect_graph(session, storage._host.tables)
        # b and c are the live files (the trash scaffolding is live directories);
        # a is trashed, and its edge went with it.
        assert graph.files.count(True) == 2 and len(graph.entry_ids) > 4
        assert len(graph.sources) == 1
        assert graph.parents.count(phase.NO_PARENT) == 1
        await storage.close()

    async def test_path_shape_favours_the_shallow_by_default(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage, edges=False)
        async with storage._host.session_factory() as session:
            graph = await collect_graph(session, storage._host.tables)
        shallow = signal_values(graph, Signal("shape", measure=PathShape()))
        deep = signal_values(graph, Signal("shape", measure=PathShape(sign=1)))
        by_path = dict(zip(graph.entry_ids, graph.depths, strict=True))
        assert len(shallow) == 1 and by_path[next(iter(shallow))] == 1
        assert len(deep) == 2 and all(by_path[entry_id] == 2 for entry_id in deep)
        assert signal_values(graph, Signal("centrality")) == {}
        await storage.close()

    async def test_path_shape_is_empty_without_files_or_without_a_range(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        assert (await storage.mkdir(path=Path("/only"))).success is True
        async with storage._host.session_factory() as session:
            graph = await collect_graph(session, storage._host.tables)
        assert signal_values(graph, Signal("shape", measure=PathShape())) == {}
        assert (await storage.write(entries=[Entry(path=Path("/flat.md"), content="x")])).success is True
        async with storage._host.session_factory() as session:
            graph = await collect_graph(session, storage._host.tables)
        assert signal_values(graph, Signal("shape", measure=PathShape())) == {}
        await storage.close()

    async def test_a_failed_publish_fails_the_reindex(self, tmp_path, monkeypatch) -> None:
        async def broken(session, tables, signal, generation, values) -> Result:
            return Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.internal, message="publish broke")])

        monkeypatch.setattr(backend_module, "publish_signal", broken)
        storage = _mount(tmp_path)
        await _seed(storage)
        result = await storage.reindex()
        assert result.success is False and result.errors[0].message == "publish broke"
        assert await _pointers(storage) == {}
        await storage.close()

    async def test_a_lost_lease_stops_before_the_next_signal(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        lost = asyncio.Event()
        lost.set()
        outcome = await storage._signal_phase(storage._host.tables, lost)
        assert outcome is not None and outcome.success is False
        assert outcome.errors[0].kind is VFSErrorKind.conflict
        assert await _pointers(storage) == {}
        await storage.close()


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------


class TestProbe:
    async def test_the_prior_reorders_glean_and_explains_itself(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        before = await storage.glean(query="needle")
        assert _order(before) == ["/a.md", "/deep/b.md", "/deep/c.md"]
        assert _signal_records(before) == ["centrality"]
        assert _legs(before)["signals"]["centrality"]["applied"] is False
        assert (await storage.reindex()).success is True
        after = await storage.glean(query="needle")
        assert _order(after)[0] == "/deep/b.md" and after.observations[0].score == 1.0
        assert _signal_records(after) == []
        explain = _legs(after)["signals"]["centrality"]
        # The lowest file scales to zero and stores no row: two of three carry a factor.
        assert explain["applied"] is True and explain["entries"] == 2 and explain["weight"] == 0.5
        assert _legs(after)["fused"] == "client"
        await storage.close()

    async def test_a_signal_computed_under_other_options_is_dropped_with_a_record(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage)
        assert (await storage.reindex()).success is True
        await storage.close()
        changed = _mount(tmp_path, Ranker(signals=(Signal("centrality", measure=PageRank()),)))
        result = await changed.glean(query="needle")
        records = [error for error in result.errors if error.data and error.data.get("leg") == "signal"]
        assert len(records) == 1 and records[0].severity is Severity.warning
        assert records[0].kind is VFSErrorKind.unavailable and "other options" in records[0].message
        assert _order(result) == ["/a.md", "/deep/b.md", "/deep/c.md"]
        await changed.close()

    async def test_a_signal_with_no_rows_is_dropped_with_a_record(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _seed(storage, edges=False)
        assert (await storage.reindex()).success is True
        result = await storage.glean(query="needle")
        assert _signal_records(result) == ["centrality"]
        assert "no entry earned" in _legs(result)["signals"]["centrality"]["reason"]
        await storage.close()

    async def test_a_uniform_prior_never_reorders(self, tmp_path) -> None:
        # Every file referenced once: the prior is uniform, no row is stored, the order is the lexical one.
        storage = _mount(tmp_path, Ranker(signals=(Signal("centrality", smoothing=0.0),)))
        await _seed(storage, edges=False)
        ring = [
            Edge(source=Path("/a.md"), target=Path("/deep/b.md"), edge_type="ref"),
            Edge(source=Path("/deep/b.md"), target=Path("/deep/c.md"), edge_type="ref"),
            Edge(source=Path("/deep/c.md"), target=Path("/a.md"), edge_type="ref"),
        ]
        assert (await storage.mkedge(edges=ring)).success is True
        assert (await storage.reindex()).success is True
        result = await storage.glean(query="needle")
        assert _order(result) == ["/a.md", "/deep/b.md", "/deep/c.md"]
        assert [row.score for row in result.observations] == [1.0, 1.0, 1.0]
        await storage.close()

    async def test_the_probe_is_chunked_and_applies_the_transform(self, tmp_path) -> None:
        storage = _mount(tmp_path, Ranker(signals=(Signal("centrality", transform=Log1p(), weight=1.0),)))
        await _seed(storage)
        assert (await storage.reindex()).success is True
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            ids = list((await session.execute(select(tables.entry.c.entry_id))).scalars())
            answer = await signal_factors(session, tables, storage._host.profile, 3, storage._ranker, ids)
        stored = await _stored(storage)
        assert answer.factors and len(answer.factors) == len(stored)
        assert max(answer.factors.values()) == pytest.approx(1.0 + Log1p().apply(1.0))
        async with storage._host.session_factory() as session:
            empty = await signal_factors(session, tables, storage._host.profile, 3, storage._ranker, [])
        assert empty.factors == {} and empty.records == [] and empty.explain == {}
        await storage.close()


# ---------------------------------------------------------------------------
# The engine legs
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _server_storage(env_var: str) -> AsyncIterator[DatabaseStorage]:
    url = os.environ.get(env_var)
    if url is None:
        pytest.skip(f"{env_var} is not set")
    table_name = f"vfs_{uuid4().hex[:10]}"
    storage = DatabaseStorage(url=url, table_name=table_name, ranker=Ranker(signals=(CENTRALITY,)))
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


class TestEngineLegs:
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_the_prior_is_stored_and_reorders_on_every_engine(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            await _seed(storage)
            assert (await storage.reindex()).success is True
            stored = await _stored(storage)
            assert stored[("centrality", "/deep/b.md")] == 1.0
            result = await storage.glean(query="needle")
            assert _order(result)[0] == "/deep/b.md" and _signal_records(result) == []
            assert (await storage.reindex()).success is True
            assert len(await _pointers(storage)) == 1
