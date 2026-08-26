"""Segment postings mirror the path column — the write-path battery.

The mirror invariant: after every verb, the segment posting table
equals the recomputed ancestor segments of every stored path — every
kind, trash included. The battery drives the public verbs and asserts
the invariant after each step; the reindex tests seed drift directly
and prove the re-convergence repairs it loudly, under path guards that
skip any row a concurrent writer owns.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, insert, select
from ulid import ULID

from tests.support.database_helpers import _url
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database.segments import (
    EntryDelta,
    SegmentRebuildState,
    path_segments,
    repair_segment_drift,
    segment_rows,
)
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def storage(tmp_path) -> AsyncIterator[DatabaseStorage]:
    mount = DatabaseStorage(url=_url(tmp_path))
    yield mount
    await mount.close()


async def _mirror_sets(storage: DatabaseStorage) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(stored postings, recomputed truth) over every entry row of every kind."""
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        entries = (await session.execute(select(tables.entry.c.entry_id, tables.entry.c.path))).all()
        postings = (await session.execute(select(tables.segments.c.segment, tables.segments.c.entry_id))).all()
    truth = {(segment, entry_id) for entry_id, path in entries for segment in path_segments(path)}
    return {(row.segment, row.entry_id) for row in postings}, truth


async def _assert_mirror(storage: DatabaseStorage) -> None:
    stored, truth = await _mirror_sets(storage)
    assert stored == truth


# ---------------------------------------------------------------------------
# Segment derivation — the pure function
# ---------------------------------------------------------------------------


class TestPathSegments:
    def test_leaf_is_excluded_and_ancestors_dedupe(self) -> None:
        assert path_segments("/a/b/c.txt") == {"a", "b"}
        assert path_segments("/a/a/a.txt") == {"a"}
        assert path_segments("/a/b/a/c/a") == {"a", "b", "c"}

    def test_root_level_paths_have_no_segments(self) -> None:
        assert path_segments("/") == frozenset()
        assert path_segments("/x.txt") == frozenset()
        assert path_segments("/dir") == frozenset()

    def test_segments_are_verbatim_and_case_sensitive(self) -> None:
        assert path_segments("/Docs/docs/f.txt") == {"Docs", "docs"}
        assert path_segments("/über/naïve/f.txt") == {"über", "naïve"}

    def test_trash_paths_carry_the_meta_chain(self) -> None:
        assert path_segments("/.vfs/trash/2026-08-17-10/x-f.txt") == {".vfs", "trash", "2026-08-17-10"}

    def test_segment_rows_are_sorted_and_keyed(self) -> None:
        rows = segment_rows("01ARZ3", "/b/a/f.txt")
        assert rows == [{"segment": "a", "entry_id": "01ARZ3"}, {"segment": "b", "entry_id": "01ARZ3"}]
        assert segment_rows("01ARZ3", "/f.txt") == []


# ---------------------------------------------------------------------------
# The mirror battery — every verb, postings == recomputed segments
# ---------------------------------------------------------------------------


class TestWriteFamilyMirror:
    async def test_batch_writes_and_root_level_rows(self, storage: DatabaseStorage) -> None:
        entries = [
            Entry(path=Path("/top.txt"), content="root level"),
            Entry(path=Path("/src/app/main.py"), content="deep"),
            Entry(path=Path("/src/app/util/helpers.py"), content="deeper"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True
        stored, truth = await _mirror_sets(storage)
        assert stored == truth
        # A root-level file stores no posting rows; the deep ones do.
        assert not any(s == "top.txt" for s, _ in stored)
        assert {s for s, _ in stored} == {"src", "app", "util"}

    async def test_overwrite_is_a_posting_no_op(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="v1")], parents=True)).success
        before, _ = await _mirror_sets(storage)
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="v2")])).success
        after, truth = await _mirror_sets(storage)
        assert after == before == truth

    async def test_mkdir_parents_mirror(self, storage: DatabaseStorage) -> None:
        assert (await storage.mkdir(path=Path("/a/b/c"), parents=True)).success is True
        await _assert_mirror(storage)

    async def test_edit_touches_no_postings(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="one two")], parents=True)).success
        edits = [EditOperation(old="one", new="three")]
        assert (await storage.edit(edits=edits, path=Path("/d/f.txt"))).success is True
        await _assert_mirror(storage)


class TestTopologyMirror:
    async def _tree(self, storage: DatabaseStorage) -> None:
        entries = [
            Entry(path=Path("/a/x/a/f.txt"), content="recurring name"),
            Entry(path=Path("/a/x/g.txt"), content="plain"),
            Entry(path=Path("/a/y/h.txt"), content="sibling"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True

    async def test_pure_rename_with_recurring_segment(self, storage: DatabaseStorage) -> None:
        # /a/x/a/f.txt keeps its inner "a" segment when /a becomes /b —
        # the fast-path UPDATE must not fire for that row.
        await self._tree(storage)
        assert (await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))])).success is True
        await _assert_mirror(storage)
        stored, _ = await _mirror_sets(storage)
        assert any(segment == "a" for segment, _ in stored)

    async def test_rename_onto_a_name_already_in_the_chain(self, storage: DatabaseStorage) -> None:
        # /a/x -> /a/a: the descendants' added set is empty (the "a"
        # segment already holds), so the general path must run.
        await self._tree(storage)
        assert (await storage.move(operations=[ResolvedPair(src=Path("/a/x"), dest=Path("/a/a"))])).success is True
        await _assert_mirror(storage)

    async def test_reparent_into_a_deeper_chain(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.mkdir(path=Path("/c/d"), parents=True)).success is True
        assert (await storage.move(operations=[ResolvedPair(src=Path("/a/x"), dest=Path("/c/d/e"))])).success is True
        await _assert_mirror(storage)

    async def test_move_onto_an_occupant_refuses_and_keeps_the_mirror(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.write(entries=[Entry(path=Path("/a/y/g.txt"), content="keeper")])).success is True
        pair = ResolvedPair(src=Path("/a/x/g.txt"), dest=Path("/a/y/g.txt"))
        refused = await storage.move(operations=[pair])
        assert [e.kind for e in refused.errors] == [VFSErrorKind.exists]
        await _assert_mirror(storage)

    async def test_copy_mints_postings_for_the_fresh_tree(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/a"), dest=Path("/copy"))])).success is True
        await _assert_mirror(storage)

    async def test_copy_onto_an_occupant_refuses_and_keeps_the_mirror(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.write(entries=[Entry(path=Path("/dest.txt"), content="old")])).success is True
        pair = ResolvedPair(src=Path("/a/x/g.txt"), dest=Path("/dest.txt"))
        refused = await storage.copy(operations=[pair])
        assert [e.kind for e in refused.errors] == [VFSErrorKind.exists]
        await _assert_mirror(storage)

    async def test_delete_mirrors_the_trash_side(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.delete(path=Path("/a"))).success is True
        await _assert_mirror(storage)
        stored, _ = await _mirror_sets(storage)
        # Trash rows carry postings too: the chain and the bucket are segments.
        assert any(segment == "trash" for segment, _ in stored)

    async def test_restore_returns_the_postings_home(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        deleted = await storage.delete(path=Path("/a/x"))
        assert deleted.success is True
        assert (await storage.restore(path=Path("/a/x"))).success is True
        await _assert_mirror(storage)

    async def test_a_batch_delete_flushes_every_targets_postings(self, storage: DatabaseStorage) -> None:
        # Two targets under distinct roots in one call: every accumulated
        # posting delta must flush, never just the batch's last one.
        await self._tree(storage)
        targets = [Observation(path=Path("/a/x")), Observation(path=Path("/a/y"))]
        assert (await storage.delete(observations=targets)).success is True
        await _assert_mirror(storage)

    async def test_a_batch_move_mirrors_every_pair(self, storage: DatabaseStorage) -> None:
        # Two pairs in one call: each pair's root reparent must land its
        # own posting delta, not only the last pair's.
        await self._tree(storage)
        pairs = [
            ResolvedPair(src=Path("/a/x"), dest=Path("/m1")),
            ResolvedPair(src=Path("/a/y"), dest=Path("/m2")),
        ]
        assert (await storage.move(operations=pairs)).success is True
        await _assert_mirror(storage)

    async def test_a_batch_restore_returns_every_targets_postings(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        targets = [Observation(path=Path("/a/x")), Observation(path=Path("/a/y"))]
        assert (await storage.delete(observations=targets)).success is True
        restored = await storage.restore(observations=targets)
        assert restored.success is True
        await _assert_mirror(storage)

    async def test_sweep_purge_drops_the_subtree_postings(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.sweep(path=Path("/a/x"))).success is True
        await _assert_mirror(storage)

    async def test_sweep_at_the_trash_root_keeps_the_mirror(self, storage: DatabaseStorage) -> None:
        await self._tree(storage)
        assert (await storage.delete(path=Path("/a/y"))).success is True
        assert (await storage.sweep(path=Path("/.vfs/trash"))).success is True
        await _assert_mirror(storage)


class TestRandomizedMirror:
    async def test_a_seeded_verb_sequence_never_breaks_the_mirror(self, storage: DatabaseStorage) -> None:
        rng = random.Random(7)
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
                pairs = [ResolvedPair(src=Path(source), dest=Path(dest))]
                extra = "/" + "/".join(rng.sample(names, rng.randint(1, 3)))
                # Sometimes a second pair rides the same call: batch width
                # is a pinned dimension, not a single-pair convention.
                if rng.random() < 0.4 and extra not in (source, dest):
                    pairs.append(ResolvedPair(src=Path(extra), dest=Path(extra + "-moved")))
                await storage.move(operations=pairs)
            elif verb == "copy" and source != dest:
                await storage.copy(operations=[ResolvedPair(src=Path(source), dest=Path(dest))])
            elif verb == "delete":
                targets = [Observation(path=Path(source))]
                if rng.random() < 0.4 and dest != source:
                    targets.append(Observation(path=Path(dest)))
                await storage.delete(observations=targets)
            elif verb == "restore":
                if rng.random() < 0.4 and dest != source:
                    await storage.restore(observations=[Observation(path=Path(source)), Observation(path=Path(dest))])
                else:
                    await storage.restore(path=Path(source))
            await _assert_mirror(storage)


# ---------------------------------------------------------------------------
# Reindex re-convergence — drift repaired loudly, guards honored
# ---------------------------------------------------------------------------


class TestSegmentRebuild:
    async def test_a_clean_store_reindexes_without_warnings(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        result = await storage.reindex()
        assert result.success is True
        assert result.errors == []
        await _assert_mirror(storage)

    async def test_seeded_drift_is_repaired_and_reported(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        tables = storage._host.tables
        entry = tables.entry
        async with storage._host.session_factory() as session:
            victim = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a/b/f.txt"))).scalar_one()
            ghost_host = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a/b"))).scalar_one()
            # Three drift shapes: a missing posting, an excess posting,
            # and orphan postings naming an entry id with no entry row.
            await session.execute(
                delete(tables.segments).where(tables.segments.c.segment == "b", tables.segments.c.entry_id == victim)
            )
            await session.execute(insert(tables.segments), [{"segment": "ghost", "entry_id": ghost_host}])
            await session.execute(insert(tables.segments), [{"segment": "gone", "entry_id": str(ULID())}])
            await session.commit()
        result = await storage.reindex()
        assert result.success is True
        warnings = [error for error in result.errors if error.severity == Severity.warning]
        assert len(warnings) == 3
        messages = " | ".join(w.message for w in warnings)
        assert "repaired segment postings" in messages
        assert "orphaned segment posting" in messages
        await _assert_mirror(storage)

    async def test_a_second_reindex_after_repair_is_quiet(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        async with storage._host.session_factory() as session:
            await session.execute(delete(storage._host.tables.segments))
            await session.commit()
        assert (await storage.reindex()).success is True
        second = await storage.reindex()
        assert second.success is True
        assert second.errors == []
        await _assert_mirror(storage)

    async def test_a_guard_miss_skips_the_row_silently(self, storage: DatabaseStorage) -> None:
        # The delta claims a path the row no longer holds: the concurrent
        # writer's synchronous maintenance is the truth, so no repair runs.
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            entry = tables.entry
            victim = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a/b/f.txt"))).scalar_one()
            state = SegmentRebuildState(
                deltas=[EntryDelta(entry_id=victim, path="/z/b/f.txt", missing=["z"], excess=["a"])]
            )
            result = await repair_segment_drift(session, tables, storage._host.membership_budget, state)
            await session.commit()
        assert result.success is True
        assert result.errors == []
        await _assert_mirror(storage)

    async def test_a_matching_guard_applies_the_delta(self, storage: DatabaseStorage) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/b/f.txt"), content="x")], parents=True)).success
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            entry = tables.entry
            victim = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/a/b/f.txt"))).scalar_one()
            await session.execute(
                delete(tables.segments).where(tables.segments.c.segment == "b", tables.segments.c.entry_id == victim)
            )
            state = SegmentRebuildState(
                deltas=[EntryDelta(entry_id=victim, path="/a/b/f.txt", missing=["b"], excess=[])]
            )
            result = await repair_segment_drift(session, tables, storage._host.membership_budget, state)
            await session.commit()
        assert result.success is True
        assert len(result.errors) == 1
        assert result.errors[0].severity == Severity.warning
        await _assert_mirror(storage)


class TestSegmentPhaseBoundaries:
    """The reindex segment phases' failure and lease arms."""

    async def test_a_failed_collect_returns_its_classification(self, storage: DatabaseStorage, monkeypatch) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")], parents=True)).success
        failed = Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.internal, message="collect broke")])

        async def broken(session, tables, state) -> Result:
            return failed

        monkeypatch.setattr(backend_module, "collect_segment_drift", broken)
        result = await storage.reindex()
        assert result.success is False
        assert result.errors[0].message == "collect broke"

    async def test_a_lease_lost_after_collect_stops_before_the_repair(
        self, storage: DatabaseStorage, monkeypatch
    ) -> None:
        # The beat proves the lease taken while collect runs: the rival
        # owns the rebuild now, so this run stops at the boundary.
        assert (await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")], parents=True)).success
        lost = asyncio.Event()

        async def poisoned(session, tables, state) -> Result:
            state.orphans = {str(ULID()): ["ghost"]}
            lost.set()
            return Result(ops=("reindex",))

        monkeypatch.setattr(backend_module, "collect_segment_drift", poisoned)
        result = await storage._reindex_phases(storage._host.tables, lost)
        assert result.success is False
        assert "expired mid-run" in result.errors[0].message
        # The drift was left untouched — no repair transaction ran.
        stored, truth = await _mirror_sets(storage)
        assert stored == truth

    async def test_a_failed_repair_returns_its_classification(self, storage: DatabaseStorage, monkeypatch) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a/f.txt"), content="x")], parents=True)).success
        async with storage._host.session_factory() as session:
            await session.execute(insert(storage._host.tables.segments), [{"segment": "gone", "entry_id": str(ULID())}])
            await session.commit()
        failed = Result(ops=("reindex",), errors=[ResultError(kind=VFSErrorKind.internal, message="repair broke")])

        async def broken(session, tables, membership_budget, state) -> Result:
            return failed

        monkeypatch.setattr(backend_module, "repair_segment_drift", broken)
        result = await storage.reindex()
        assert result.success is False
        assert result.errors[0].message == "repair broke"
