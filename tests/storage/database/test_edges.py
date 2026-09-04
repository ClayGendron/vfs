"""The fs mirror and the authored-edge cascade — the write-path battery.

The mirror invariant: after every verb, the fs edge rows equal the
``parent_id`` pointers of every stored entry — every kind, trash
included — one row per non-root entry, ``provenance='system'``, payload
NULL. Authored edges die in exactly two ways: removed by triple, or an
endpoint is deleted — soft delete included. The battery drives the
public verbs and asserts both after each step; the reindex tests seed
drift directly and prove the re-convergence repairs it loudly.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, insert, select
from ulid import ULID

from tests.support.database_helpers import _url
from vfs.models import Edge, Entry, Observation
from vfs.paths import Path
from vfs.results import Severity
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.edges import (
    EdgeRebuildState,
    collect_edge_drift,
    mkedge_rows,
    repair_edge_drift,
)
from vfs.storage.backends.database.seams import installed
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def storage(tmp_path) -> AsyncIterator[DatabaseStorage]:
    mount = DatabaseStorage(url=_url(tmp_path))
    yield mount
    await mount.close()


async def _mirror_sets(storage: DatabaseStorage) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(stored fs pairs, recomputed truth) as ``(parent_id, entry_id)`` pairs.

    Also asserts the row shape: system provenance, NULL payload, and at
    most one fs in-edge per entry.
    """
    tables = storage._host.tables
    entry, edges = tables.entry, tables.edges
    async with storage._host.session_factory() as session:
        entries = (await session.execute(select(entry.c.entry_id, entry.c.parent_id))).all()
        fs_rows = (await session.execute(select(edges).where(edges.c.edge_type == "fs"))).mappings().all()
    truth = {(row.parent_id, row.entry_id) for row in entries if row.parent_id is not None}
    assert all(r["provenance"] == "system" and r["weight"] is None and r["distance"] is None for r in fs_rows)
    targets = [r["target_id"] for r in fs_rows]
    assert len(targets) == len(set(targets))
    return {(r["source_id"], r["target_id"]) for r in fs_rows}, truth


async def _assert_mirror(storage: DatabaseStorage) -> None:
    stored, truth = await _mirror_sets(storage)
    assert stored == truth


async def _seed_edge(storage: DatabaseStorage, source: str, target: str, *, edge_type: str = "ref") -> None:
    """Plant one authored edge at the row layer, bypassing ``mkedge``."""
    tables = storage._host.tables
    entry = tables.entry
    async with storage._host.session_factory() as session:
        rows = (
            await session.execute(select(entry.c.path, entry.c.entry_id).where(entry.c.path.in_([source, target])))
        ).all()
        ids = {row.path: row.entry_id for row in rows}
        await session.execute(
            insert(tables.edges).values(
                source_id=ids[source], target_id=ids[target], edge_type=edge_type, provenance="user"
            )
        )
        await session.commit()


async def _entry_ids(storage: DatabaseStorage) -> dict[str, str]:
    """Every stored ``path → entry id`` — fetched before trash rewrites paths."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(entry.c.path, entry.c.entry_id))).all()
    return {row.path: row.entry_id for row in rows}


async def _plant_stray(storage: DatabaseStorage, source_id: str, target_id: str) -> None:
    """Plant one authored edge by raw ids — the row-layer bug the reclaim heals."""
    edges = storage._host.tables.edges
    async with storage._host.session_factory() as session:
        await session.execute(
            insert(edges).values(source_id=source_id, target_id=target_id, edge_type="ref", provenance="user")
        )
        await session.commit()


async def _authored(storage: DatabaseStorage) -> set[tuple[str, str, str]]:
    """Every non-fs edge as ``(source_id, target_id, edge_type)``."""
    edges = storage._host.tables.edges
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(edges).where(edges.c.edge_type != "fs"))).mappings().all()
    return {(r["source_id"], r["target_id"], r["edge_type"]) for r in rows}


# ---------------------------------------------------------------------------
# The mirror battery — every verb, fs rows == parent_id
# ---------------------------------------------------------------------------


class TestWriteFamilyMirror:
    async def test_batch_writes_mint_one_row_per_entry(self, storage: DatabaseStorage) -> None:
        entries = [
            Entry(path=Path("/top.txt"), content="root level"),
            Entry(path=Path("/src/app/main.py"), content="deep"),
            Entry(path=Path("/src/app/util/helpers.py"), content="deeper"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True
        stored, truth = await _mirror_sets(storage)
        assert stored == truth
        # Six entries (three files, three minted dirs), six fs rows.
        assert len(stored) == 6

    async def test_overwrite_is_a_mirror_no_op(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="v1")], parents=True)).success
        before, _ = await _mirror_sets(storage)
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="v2")])).success
        after, truth = await _mirror_sets(storage)
        assert after == before == truth

    async def test_mkdir_parents_mirror(self, storage: DatabaseStorage) -> None:
        assert (await storage.mkdir(path=Path("/a/b/c"), parents=True)).success is True
        await _assert_mirror(storage)

    async def test_edit_touches_no_edges(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="one two")], parents=True)).success
        assert (await storage.edit(edits=[EditOperation(old="one", new="three")], path=Path("/d/f.txt"))).success
        await _assert_mirror(storage)


class TestTopologyMirror:
    async def _tree(self, storage: DatabaseStorage) -> None:
        entries = [
            Entry(path=Path("/a/x/a/f.txt"), content="recurring name"),
            Entry(path=Path("/a/x/g.txt"), content="plain"),
            Entry(path=Path("/a/y/h.txt"), content="sibling"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True

    async def test_move_repoints_the_root_only(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        edges = storage._host.tables.edges
        async with storage._host.session_factory() as session:
            before = {r["id"]: r for r in (await session.execute(select(edges))).mappings()}
        assert (await storage.move(operations=[ResolvedPair(src=Path("/a/x"), dest=Path("/moved"))])).success is True
        await _assert_mirror(storage)
        async with storage._host.session_factory() as session:
            after = {r["id"]: r for r in (await session.execute(select(edges))).mappings()}
        # The same rows survive — one changed source, no mint, no delete.
        assert set(after) == set(before)
        changed = [i for i in after if dict(after[i]) != dict(before[i])]
        assert len(changed) == 1

    async def test_a_batch_move_mirrors_every_pair(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        pairs = [
            ResolvedPair(src=Path("/a/x"), dest=Path("/m1")),
            ResolvedPair(src=Path("/a/y"), dest=Path("/m2")),
        ]
        assert (await storage.move(operations=pairs)).success is True
        await _assert_mirror(storage)

    async def test_copy_mints_rows_for_the_fresh_tree(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/a"), dest=Path("/copy"))])).success is True
        await _assert_mirror(storage)

    async def test_copy_never_copies_authored_edges(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        await _seed_edge(storage, "/a/x/g.txt", "/a/y/h.txt")
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/a"), dest=Path("/copy"))])).success is True
        await _assert_mirror(storage)
        assert len(await _authored(storage)) == 1

    async def test_delete_keeps_the_mirror_through_trash(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.delete(path=Path("/a"))).success is True
        # The trashed root re-sourced to the bucket; descendants, the
        # chain, and the bucket dirs all mirror parent_id uniformly.
        await _assert_mirror(storage)

    async def test_restore_returns_the_mirror_home(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.delete(path=Path("/a/x"))).success is True
        assert (await storage.restore(path=Path("/a/x"))).success is True
        await _assert_mirror(storage)

    async def test_sweep_purge_drops_the_subtree_rows(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        await _seed_edge(storage, "/a/x/g.txt", "/a/y/h.txt")
        assert (await storage.sweep(path=Path("/a"))).success is True
        await _assert_mirror(storage)
        assert await _authored(storage) == set()

    async def test_sweep_at_the_trash_root_keeps_the_mirror(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.delete(path=Path("/a/y"))).success is True
        assert (await storage.sweep(path=Path("/.vfs/trash"))).success is True
        await _assert_mirror(storage)


# ---------------------------------------------------------------------------
# Authored-edge lifetime — removed by triple or endpoint deletion, soft included
# ---------------------------------------------------------------------------


class TestAuthoredEdgeLifetime:
    async def _corpus(self, storage: DatabaseStorage) -> None:
        entries = [
            Entry(path=Path("/proj/inner/a.md"), content="a"),
            Entry(path=Path("/proj/inner/b.md"), content="b"),
            Entry(path=Path("/proj/c.md"), content="c"),
            Entry(path=Path("/other/d.md"), content="d"),
            Entry(path=Path("/other/e.md"), content="e"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True

    async def test_soft_delete_cascades_every_direction(self, storage: DatabaseStorage) -> None:
        await self._corpus(storage)
        await _seed_edge(storage, "/proj/inner/a.md", "/proj/inner/b.md")  # internal
        await _seed_edge(storage, "/other/d.md", "/proj/inner/a.md")  # inbound
        await _seed_edge(storage, "/proj/inner/b.md", "/other/d.md")  # outbound
        await _seed_edge(storage, "/other/d.md", "/other/e.md")  # unrelated
        assert (await storage.delete(path=Path("/proj/inner"))).success is True
        await _assert_mirror(storage)
        survivors = await _authored(storage)
        assert len(survivors) == 1  # only the unrelated edge lives on
        assert next(iter(survivors))[2] == "ref"

    async def test_a_file_delete_cascades_its_own_edges(self, storage: DatabaseStorage) -> None:
        await self._corpus(storage)
        await _seed_edge(storage, "/proj/c.md", "/other/d.md")
        assert (await storage.delete(path=Path("/proj/c.md"))).success is True
        await _assert_mirror(storage)
        assert await _authored(storage) == set()

    async def test_restore_never_re_mints_authored_edges(self, storage: DatabaseStorage) -> None:
        await self._corpus(storage)
        await _seed_edge(storage, "/proj/inner/a.md", "/other/d.md")
        assert (await storage.delete(path=Path("/proj/inner"))).success is True
        assert (await storage.restore(path=Path("/proj/inner"))).success is True
        await _assert_mirror(storage)
        assert await _authored(storage) == set()

    async def test_a_move_is_not_a_delete(self, storage: DatabaseStorage) -> None:
        await self._corpus(storage)
        await _seed_edge(storage, "/proj/inner/a.md", "/other/d.md")
        assert (await storage.move(operations=[ResolvedPair(src=Path("/proj"), dest=Path("/renamed"))])).success
        await _assert_mirror(storage)
        assert len(await _authored(storage)) == 1


class TestMkedgeArbitration:
    """A racing duplicate create redrives and lands as the touch it raced."""

    async def test_a_racing_duplicate_create_lands_as_a_touch(self, storage: DatabaseStorage) -> None:
        entries = [Entry(path=Path("/a.md"), content="a"), Entry(path=Path("/b.md"), content="b")]
        assert (await storage.write(entries=entries, parents=True)).success is True
        tables = storage._host.tables
        edge = Edge(source=Path("/a.md"), target=Path("/b.md"), edge_type="ref", weight=1.0)
        async with storage._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            entry = tables.entry
            rows = (
                await session.execute(
                    select(entry.c.path, entry.c.entry_id).where(entry.c.path.in_(["/a.md", "/b.md"]))
                )
            ).all()
            ids = {row.path: row.entry_id for row in rows}

            async def rival() -> None:
                await session.execute(
                    insert(tables.edges).values(
                        source_id=ids["/a.md"],
                        target_id=ids["/b.md"],
                        edge_type="ref",
                        provenance="user",
                        weight=9.0,
                    )
                )

            with installed("mkedge:before-insert", rival):
                result = await mkedge_rows(
                    session,
                    tables,
                    storage._host.profile,
                    storage._host.membership_budget,
                    edges=[edge],
                    provenance="system",
                    user_id=None,
                )
            await session.commit()
        assert result.success is True
        assert result.observations[0].status == "updated"
        assert await _authored(storage) == {(ids["/a.md"], ids["/b.md"], "ref")}
        await _assert_mirror(storage)


class TestEndpointLocks:
    """A rival delete serializes behind mkedge's endpoint resolve."""

    async def test_a_rival_delete_converges_after_the_window(self, storage: DatabaseStorage, tmp_path) -> None:
        # The rival launches mid-window and must not commit inside it;
        # after mkedge commits, its cascade sweeps the fresh edge.
        entries = [Entry(path=Path("/src.py"), content="x"), Entry(path=Path("/dst.py"), content="x")]
        assert (await storage.write(entries=entries)).success is True
        rival = DatabaseStorage(url=_url(tmp_path))
        pending: dict[str, asyncio.Task] = {}

        async def handler() -> None:
            pending["delete"] = asyncio.ensure_future(rival.delete(path=Path("/dst.py")))
            done, _ = await asyncio.wait([pending["delete"]], timeout=0.5)
            assert not done, "the rival delete committed inside mkedge's window"

        edge = Edge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
        try:
            with installed("mkedge:before-insert", handler):
                created = await storage.mkedge(edges=[edge])
            assert created.success is True
            assert created.observations[0].status == "created"
            deleted = await asyncio.wait_for(pending["delete"], timeout=30)
            assert deleted.success is True
        finally:
            await rival.close()
        assert await _authored(storage) == set()
        await _assert_mirror(storage)


class TestRandomizedMirror:
    async def test_a_seeded_verb_sequence_never_breaks_the_mirror(self, storage: DatabaseStorage) -> None:
        rng = random.Random(11)
        names = ["alpha", "beta", "gamma", "delta"]
        step = 0
        for _ in range(30):
            verb = rng.choice(["write", "mkdir", "move", "copy", "delete", "restore"])
            source = "/" + "/".join(rng.sample(names, rng.randint(1, 3)))
            dest = "/" + "/".join(rng.sample(names, rng.randint(1, 3)))
            if verb == "write":
                step += 1
                entry = Entry(path=Path(f"{source}/f{step}.txt"), content=f"body {step}")
                await storage.write(entries=[entry], parents=True)
            elif verb == "mkdir":
                await storage.mkdir(path=Path(source), parents=True, exist_ok=True)
            elif verb == "move" and source != dest:
                await storage.move(operations=[ResolvedPair(src=Path(source), dest=Path(dest))])
            elif verb == "copy" and source != dest:
                await storage.copy(operations=[ResolvedPair(src=Path(source), dest=Path(dest))])
            elif verb == "delete":
                targets = [Observation(path=Path(source))]
                if rng.random() < 0.4 and dest != source:
                    targets.append(Observation(path=Path(dest)))
                await storage.delete(observations=targets)
            elif verb == "restore":
                await storage.restore(path=Path(source))
            await _assert_mirror(storage)


# ---------------------------------------------------------------------------
# Reindex re-convergence — drift repaired loudly, guards honored
# ---------------------------------------------------------------------------


class TestEdgeRebuild:
    async def test_a_clean_store_reindexes_without_warnings(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        result = await storage.reindex()
        assert result.success is True
        assert result.errors == []
        await _assert_mirror(storage)

    async def test_seeded_drift_is_repaired_and_reported(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        tables = storage._host.tables
        entry, edges = tables.entry, tables.edges
        async with storage._host.session_factory() as session:
            victim = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a/b/f.txt"))).scalar_one()
            root = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            top = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a"))).scalar_one()
            # Four drift shapes: a missing fs row, a mispointed fs row, an
            # fs row targeting the root, and a dangling authored edge.
            await session.execute(delete(edges).where(edges.c.target_id == victim, edges.c.edge_type == "fs"))
            await session.execute(delete(edges).where(edges.c.target_id == top, edges.c.edge_type == "fs"))
            await session.execute(
                insert(edges).values(source_id=victim, target_id=top, edge_type="fs", provenance="system")
            )
            await session.execute(
                insert(edges).values(source_id=top, target_id=root, edge_type="fs", provenance="system")
            )
            await session.execute(
                insert(edges).values(source_id=victim, target_id=str(ULID()), edge_type="ref", provenance="user")
            )
            await session.commit()
        result = await storage.reindex()
        assert result.success is True
        warnings = [error for error in result.errors if error.severity == Severity.warning]
        messages = " | ".join(w.message for w in warnings)
        assert "repaired the fs mirror" in messages
        assert "no entry row" in messages
        await _assert_mirror(storage)
        # The dangling authored edge is gone with the drift.
        assert await _authored(storage) == set()

    async def test_a_stray_on_a_trashed_entry_is_reclaimed_and_reported(self, storage: DatabaseStorage) -> None:
        # Reachable only from a row-layer writer — the verbs' endpoint
        # locks refuse the interleaving that would mint this.
        assert (await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])).success
        assert (await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])).success
        ids = await _entry_ids(storage)
        assert (await storage.delete(path=Path("/dst.py"))).success
        await _plant_stray(storage, ids["/src.py"], ids["/dst.py"])
        result = await storage.reindex()
        assert result.success is True
        messages = " | ".join(e.message for e in result.errors if e.severity == Severity.warning)
        assert "touching trashed entries" in messages
        assert await _authored(storage) == set()
        await _assert_mirror(storage)

    async def test_a_restore_between_collect_and_repair_wins(self, storage: DatabaseStorage) -> None:
        # The guard: an endpoint restored mid-pass is live truth — the
        # reclaim skips, and the now-lawful edge survives.
        assert (await storage.write(entries=[Entry(path=Path("/src.py"), content="x")])).success
        assert (await storage.write(entries=[Entry(path=Path("/dst.py"), content="x")])).success
        ids = await _entry_ids(storage)
        deleted = await storage.delete(path=Path("/dst.py"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        await _plant_stray(storage, ids["/src.py"], ids["/dst.py"])
        tables = storage._host.tables
        state = EdgeRebuildState()
        async with storage._host.session_factory() as session:
            assert (await collect_edge_drift(session, tables, state)).success is True
        assert state.strays
        assert (await storage.restore(path=trash_path)).success is True
        async with storage._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            repaired = await repair_edge_drift(
                session, tables, storage._host.profile, storage._host.membership_budget, state
            )
            await session.commit()
        assert all("touching trashed" not in e.message for e in repaired.errors)
        assert await _authored(storage) == {(ids["/src.py"], ids["/dst.py"], "ref")}
        await _assert_mirror(storage)

    async def test_a_lease_lost_before_edge_repair_stops_the_run(self, storage: DatabaseStorage) -> None:
        # Segments are clean, edge drift is found, and the lease dies at
        # the gram phases' last boundary: the run stops honestly.
        assert (await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")], parents=True)).success
        tables = storage._host.tables
        entry, edges = tables.entry, tables.edges
        async with storage._host.session_factory() as session:
            victim = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a/f.txt"))).scalar_one()
            await session.execute(delete(edges).where(edges.c.target_id == victim, edges.c.edge_type == "fs"))
            await session.commit()
        lost = asyncio.Event()

        async def flag() -> None:
            lost.set()

        with installed("reindex:before-reclaim", flag):
            result = await storage._reindex_phases(tables, lost)
        assert result.success is False
        assert "expired mid-run" in result.errors[0].message
