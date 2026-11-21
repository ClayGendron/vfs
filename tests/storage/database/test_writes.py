"""Write mechanics beyond the conformance suite.

The conformance suite proves the verbs; this file holds the write-side
DB contract: one transaction per batch with statements bounded by tables
rather than entries, both arbitration arms (catch-retry and upsert)
resolving conflicts the plan could not see, the guarded-attribution
ladder past what SQLite executes natively, and trash as an ordinary
write target with no trash-specific arm.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import Select, event, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from ulid import ULID

from tests.support.commit_worlds import (
    BOB,
    CAROL,
    attempts,
    clearing,
    drop_world,
    label_world,
    land,
    row_at,
    version_count,
)
from tests.support.commit_worlds import replace as replace_row
from tests.support.database_helpers import _ReturningSession, _staged_material, _url
from tests.support.server_schemas import ENGINE_LEGS, server_storage
from tests.support.statements import is_statistics_statement
from vfs.authority import Authority, Principal
from vfs.models import MEASURED_BODY, BodyMetrics, Entry, measure_bytes
from vfs.models.rows import build_vfs_tables
from vfs.paths import ObjectKind, Path
from vfs.results import ErrorKind, ResultError
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import writes as writes_module
from vfs.storage.backends.database.dialects import POSTGRESQL, SQLITE, StaleSnapshot
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.seams import installed
from vfs.storage.backends.database.staging import StagedEntry, WritePlan
from vfs.storage.backends.database.writes import (
    _CLOBBER_COLUMNS,
    _catch_retry_layer,
    _entry_values,
    _fetch_committed,
    _finish,
    _material_values,
    _resolve_rows,
    _update_materials,
    _upsert_constructor,
    _upsert_layer,
)
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.protocol import ResolvedPair
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
    from pathlib import Path as FsPath
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.results import Result


# ---------------------------------------------------------------------------
# Mutation core — DB-specific contract beyond the conformance suite
# ---------------------------------------------------------------------------


SYSTEM = Authority.system()


class TestWriteMechanics:
    """One transaction per batch, bounded statements, per-entry versions."""

    def test_material_values_and_clobber_columns_stay_in_lockstep(self) -> None:
        # Two encodings of the material-column set, one invariant: a key
        # added to either alone silently diverges create vs overwrite.
        staged = StagedEntry(
            path=Path("/f.txt"), parent=Path("/"), kind="file", persistence="insert", entry_id=str(ULID()), content="x"
        )
        material = _material_values(staged, datetime.now(UTC))
        assert set(material) == set(_CLOBBER_COLUMNS)

    async def test_failed_batch_commits_nothing(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        good = await storage.write(entries=[Entry(path=Path("/keep.txt"), content="x")])
        assert good.success is True
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            rows_before = len((await conn.execute(select(tables.entry.c.id))).all())
        bad = await storage.write(
            entries=[Entry(path=Path("/new.txt"), content="y"), Entry(path=Path("/ghost/deep.txt"), content="z")]
        )
        assert bad.success is False
        async with storage._host.engine.connect() as conn:
            rows_after = len((await conn.execute(select(tables.entry.c.id))).all())
            orphans = (await conn.execute(select(tables.content.c.entry_id))).all()
        assert rows_after == rows_before
        assert len(orphans) == 1  # /keep.txt only
        await storage.close()

    async def test_batch_statement_count_is_bounded_by_tables_not_entries(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        entries = [Entry(path=Path(f"/f{i:03}.txt"), content=f"body {i}") for i in range(100)]
        result = await storage.write(entries=entries)
        assert result.success is True
        assert len(result.observations) == 100
        await storage._host.settle_statistics()
        # BEGIN + session PRAGMAs + plan select + the stamp watch + one insert
        # chunk + content insert + parent bump + the stamp hold — O(tables),
        # never O(entries).
        own = [statement for statement in statements if not is_statistics_statement(statement)]
        assert len(own) <= 12, own
        await storage.close()

    async def test_write_statement_counts_are_pinned(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        def mutations() -> list[str]:
            control = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE")
            return [s for s in statements if not s.startswith(control) and not is_statistics_statement(s)]

        created = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="a")])
        assert created.success is True
        # The round-trip budget is a contract: fetch, the stamp watch, the
        # posture rows read for the label, insert, fs mirror insert, content
        # insert, parent bump, the stamp hold. A fresh row has no body to
        # clear, so no delete runs.
        assert len(mutations()) == 8, mutations()
        assert not [s for s in mutations() if s.startswith("DELETE")], mutations()
        statements.clear()
        overwritten = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="b")])
        assert overwritten.success is True
        # Fetch, guarded update, the version mint (the revision read, the
        # body read, the version insert), the two body deletes + content
        # insert — the update is attributed from its own statement, so no
        # read-back appears.
        assert len(mutations()) == 8, mutations()
        await storage.close()

    async def test_an_identical_rewrite_runs_the_snapshot_and_nothing_else(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])).success is True
        await storage._host.settle_statistics()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        again = await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])
        assert [(o.status, o.version) for o in again.observations] == [("unchanged", 1)]
        control = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")
        own = [s for s in statements if not s.startswith(control) and not is_statistics_statement(s)]
        # The snapshot is the whole call: no guarded update, no mint, no body read, no body replaced.
        assert len(own) == 1 and own[0].startswith("SELECT"), own
        versions = storage._host.tables.versions
        async with storage._host.session_factory() as peek:
            assert (await peek.execute(select(versions.c.entry_id))).all() == []
        await storage.close()

    async def test_an_unchanged_row_keeps_its_index_marks(self, tmp_path) -> None:
        # A rewrite clears the marks the index passes set, which sends the
        # file through the index again. An unchanged row must not.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])).success is True
        entry = storage._host.tables.entry
        marks = select(entry.c.chunked, entry.c.encoded, entry.c.indexable).where(entry.c.path == "/a.txt")
        async with storage._host.session_factory() as session:
            await session.execute(update(entry).where(entry.c.path == "/a.txt").values(chunked=True, encoded=True))
            await session.commit()
            indexed = (await session.execute(marks)).one()
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])).success is True
        async with storage._host.session_factory() as peek:
            assert (await peek.execute(marks)).one() == indexed
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="two")])).success is True
        async with storage._host.session_factory() as peek:
            assert (await peek.execute(marks)).one() != indexed
        await storage.close()

    @pytest.mark.parametrize("files", [100, pytest.param(10_000, marks=pytest.mark.slow)])
    async def test_an_identical_batch_rewrite_writes_no_row(self, files: int, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        entries = [Entry(path=Path(f"/f{i:05}.txt"), content=f"body {i}") for i in range(files)]
        assert (await storage.write(entries=entries)).success is True
        await storage._host.settle_statistics()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        again = await storage.write(entries=entries)
        assert again.success is True
        assert {(o.status, o.version) for o in again.observations} == {("unchanged", 1)}
        assert len(again.observations) == files
        written = [s for s in statements if s.startswith(("INSERT", "UPDATE", "DELETE"))]
        assert written == [], written[:3]
        await storage.close()

    async def test_edit_statement_count_is_pinned_and_probes_no_misses(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        assert (await storage.write(entries=[Entry(path=Path("/docs/b.md"), content="xyz")], parents=True)).success
        statements: list[tuple[str, object]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if not is_statistics_statement(statement):  # the write's pass may land in the window
                statements.append((statement, parameters))

        edited = await storage.edit(path=Path("/docs/b.md"), edits=[EditOperation(old="y", new="z")])
        assert edited.success is True
        control = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE")
        mutations = [(s, p) for s, p in statements if not s.startswith(control)]
        # Snapshot with content, guarded update, the version mint (revision
        # read, version insert), two body deletes, content insert. When
        # every target is found no miss probe runs, and the mint keeps the
        # snapshot's body instead of reading it again: two SELECTs in all.
        assert len(mutations) == 7, [s for s, _ in mutations]
        assert len([s for s, _ in mutations if s.startswith("SELECT")]) == 2, [s for s, _ in mutations]
        assert not [p for s, p in mutations if s.startswith("SELECT") and p == ("/",)], mutations
        # The version row is the body the snapshot saw, measured by the one law.
        versions = storage._host.tables.versions
        async with storage._host.session_factory() as peek:
            kept = (
                await peek.execute(select(versions.c.version_number, versions.c.content, versions.c.content_hash))
            ).all()
        assert kept == [(1, "xyz", hashlib.sha256(b"xyz").hexdigest())]
        await storage.close()

    async def test_entry_rows_are_addressed_in_path_order(self, tmp_path) -> None:
        # One lock order for every pass: a batch given its rows in any
        # order inserts and updates them sorted by path, so two batches
        # that meet on the same rows cannot each hold what the other wants.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        await storage.mkdir(path=Path("/d"))
        await storage.mkdir(path=Path("/e"))
        addressed: list[list[str]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            head = " ".join(statement.split())[:24]
            if not head.startswith(("INSERT INTO vfs_entries", "UPDATE vfs_entries")):
                return
            rows = parameters if executemany else [parameters]
            paths = [v for row in rows for v in row if isinstance(v, str) and v.startswith("/") and v.count("/") > 1]
            if paths:
                addressed.append(paths)

        scrambled = ["/d/c.txt", "/e/z.txt", "/d/a.txt", "/e/y.txt", "/d/b.txt"]
        created = await storage.write(entries=[Entry(path=Path(p), content="v1") for p in scrambled])
        assert created.success is True
        assert addressed, "no entry insert was observed"
        assert all(paths == sorted(paths) for paths in addressed), addressed
        addressed.clear()
        overwritten = await storage.write(entries=[Entry(path=Path(p), content="v2") for p in scrambled])
        assert overwritten.success is True
        assert addressed, "no guarded update was observed"
        assert all(paths == sorted(paths) for paths in addressed), addressed
        await storage.close()

    async def test_revisions_are_per_entry_and_survive_restart(self, tmp_path) -> None:
        first = DatabaseStorage(url=_url(tmp_path))
        created = await first.write(entries=[Entry(path=Path("/docs/a.txt"), content="1")], parents=True)
        assert created.observations[0].version == 1
        minted = (await first.stat(path=Path("/docs"))).observations[0]
        assert minted.version == 1  # minted ancestors are fresh rows too
        await first.close()
        second = DatabaseStorage(url=_url(tmp_path))
        overwritten = await second.write(entries=[Entry(path=Path("/docs/a.txt"), content="2")])
        assert overwritten.observations[0].version == 2  # base + 1 off the row, no mount state
        await second.close()

    async def test_unchanged_directory_reports_the_sibling_bump(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/docs"))
        result = await storage.write(
            entries=[Entry(path=Path("/docs"), kind="directory"), Entry(path=Path("/docs/new.txt"), content="x")]
        )
        assert result.success is True
        by_path = {str(o.path): o for o in result.observations}
        assert by_path["/docs"].status == "unchanged"
        stat = (await storage.stat(path=Path("/docs"))).observations[0]
        assert by_path["/docs"].version == stat.version
        await storage.close()

    async def test_overwrite_keeps_the_owner(self, tmp_path) -> None:
        # A later writer contributes to the row; the floor stays with its
        # creator, so a contributor never turns an overwrite into a trash.
        storage = DatabaseStorage(url=_url(tmp_path))
        alice, bob = Authority.of(Principal("alice")), Authority.of(Principal("bob"))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")], authority=alice)
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="b")], authority=bob)
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            owner = (await conn.execute(select(entry.c.owner_id).where(entry.c.path == "/f.txt"))).scalar_one()
        assert owner == "alice"
        await storage.close()

    async def test_ownership_derives_from_the_authority_not_the_payload(self, tmp_path) -> None:
        # One subject owns what it makes and the payload's owner_id is
        # ignored; a set owns nothing (the container governs); the system
        # actor — named, or implied by a direct call naming no authority —
        # stamps whatever the payload declared; an edit keeps the owner.
        storage = DatabaseStorage(url=_url(tmp_path))
        alice = Authority.of(Principal("alice"))
        room = Authority.on_behalf_of({Principal("alice"), Principal("bob")}, actor=Principal("bot", kind="service"))
        await storage.write(entries=[Entry(path=Path("/mine.txt"), content="a", owner_id="mallory")], authority=alice)
        await storage.write(entries=[Entry(path=Path("/ours.txt"), content="a", owner_id="alice")], authority=room)
        await storage.write(entries=[Entry(path=Path("/etl.txt"), content="a", owner_id="carol")], authority=SYSTEM)
        await storage.write(entries=[Entry(path=Path("/direct.txt"), content="a", owner_id="carol")])
        await storage.write(entries=[Entry(path=Path("/bare.txt"), content="a")], authority=SYSTEM)
        await storage.write(entries=[Entry(path=Path("/anon.txt"), content="a")], authority=Authority.anonymous())
        await storage.mkdir(path=Path("/shared"), authority=room)
        await storage.edit(path=Path("/etl.txt"), edits=[EditOperation(old="a", new="b")], authority=alice)
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            rows = (await conn.execute(select(entry.c.path, entry.c.owner_id))).all()
        owners = {row.path: row.owner_id for row in rows}
        assert owners["/mine.txt"] == "alice"
        assert owners["/ours.txt"] is None
        assert owners["/etl.txt"] == "carol"  # alice's edit left carol's row carol's
        assert owners["/direct.txt"] == "carol"
        assert owners["/bare.txt"] is None
        assert owners["/anon.txt"] is None
        assert owners["/shared"] is None
        await storage.close()

    async def test_overwrite_preserves_entry_identity(self, tmp_path) -> None:
        # Durable references (versions, chunks, edges) hang off entry_id:
        # an overwrite must update the row in place, never re-mint it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")])
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            minted = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).scalar_one()
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="b")])).success is True
        async with storage._host.engine.connect() as conn:
            rows = (await conn.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == "/f.txt"))).all()
        assert rows == [(minted, 2)]  # same row, only the version moved
        await storage.close()

    async def test_content_writes_reset_the_index_flags(self, tmp_path) -> None:
        # The grep overlay's dirty set: new rows start unindexed, and
        # every content write (overwrite, edit) resets both flags.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")])
        entry = storage._host.tables.entry
        flags = select(entry.c.chunked, entry.c.encoded).where(entry.c.path == "/f.txt")

        async def flags_now() -> tuple[bool, bool]:
            async with storage._host.engine.connect() as conn:
                return (await conn.execute(flags)).one()._tuple()

        async def mark_indexed() -> None:
            async with storage._host.engine.begin() as conn:
                await conn.execute(update(entry).values(chunked=True, encoded=True))

        assert await flags_now() == (False, False)
        await mark_indexed()
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="b")])).success is True
        assert await flags_now() == (False, False)
        await mark_indexed()
        edited = await storage.edit(edits=[EditOperation(old="b", new="c")], path=Path("/f.txt"))
        assert edited.success is True
        assert await flags_now() == (False, False)
        await storage.close()

    async def test_move_preserves_the_index_flags(self, tmp_path) -> None:
        # Doc ids key on chunk identity, never path: a rename
        # invalidates nothing and must not re-dirty the row.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        entry = storage._host.tables.entry
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(entry).values(chunked=True, encoded=True))
        moved = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt"))])
        assert moved.success is True
        async with storage._host.engine.connect() as conn:
            row = (await conn.execute(select(entry.c.chunked, entry.c.encoded).where(entry.c.path == "/b.txt"))).one()
        assert row._tuple() == (True, True)
        await storage.close()

    async def test_a_directory_is_created_encoded(self, tmp_path) -> None:
        # The flag means "nothing of this row awaits the gram index": true
        # of every directory from its creation, the provisioned root included.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        entry = storage._host.tables.entry

        async def encoded() -> dict[str, bool]:
            async with storage._host.engine.connect() as conn:
                rows = await conn.execute(select(entry.c.path, entry.c.encoded))
                return {row.path: row.encoded for row in rows}

        assert await encoded() == {"/": True}
        assert (await storage.mkdir(path=Path("/d"))).success is True
        written = await storage.write(entries=[Entry(path=Path("/e/f.txt"), content="x")], parents=True)
        assert written.success is True
        assert await encoded() == {"/": True, "/d": True, "/e": True, "/e/f.txt": False}
        await storage.close()

    async def test_over_key_byte_budget_classifies_unaddressable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, key_byte_budget=32)
        long_path = Path("/" + "x" * 60 + ".txt")
        written = await storage.write(entries=[Entry(path=long_path, content="x")])
        assert written.success is False
        assert written.errors[0].kind == ErrorKind.unaddressable
        made = await storage.mkdir(path=Path("/" + "d" * 60))
        assert made.success is False
        assert made.errors[0].kind == ErrorKind.unaddressable
        await storage.close()

    async def test_edit_of_a_missing_target_classifies_at_the_failing_component(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        result = await storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/ghost/a.txt"))
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.not_found
        assert result.errors[0].path == "/ghost"
        await storage.close()

    async def test_unchanged_directory_observation_reads_back_its_bump(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        result = await storage.write(
            entries=[Entry(path=Path("/d"), kind="directory"), Entry(path=Path("/d/f.txt"), content="x")]
        )
        assert result.success is True
        observed = {str(o.path): o for o in result.observations}
        assert observed["/d"].status == "unchanged"
        stat = await storage.stat(path=Path("/d"))
        assert observed["/d"].version == stat.observations[0].version == 2
        await storage.close()

    def test_stage_create_folds_a_repeat_target_into_one_row(self) -> None:
        plan = WritePlan({}, authority=None, budget=SQLITE.key_byte_budget)
        target = Path("/f.txt")
        plan.stage_create(target, kind="file", content="one", content_hash="h1", size_bytes=3, lines=1)
        minted = plan.staged[target].entry_id
        plan.stage_create(target, kind="file", content="two", content_hash="h2", size_bytes=3, lines=1)
        assert list(plan.staged) == [target]
        assert plan.staged[target].entry_id == minted
        assert plan.staged[target].persistence == "insert"
        assert (plan.staged[target].content, plan.staged[target].content_hash) == ("two", "h2")


class TestTrashWritability:
    """The trash view is read-only grammar: nothing is written into it; meta paths beside it write as ever."""

    async def test_nothing_is_written_into_the_trash_view(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        for target in (Path("/.vfs/trash"), Path("/.vfs/trash/x.txt"), Path("/.vfs/trash/d/y.txt")):
            written = await storage.write(entries=[Entry(path=target, kind="file", content="x")], parents=True)
            assert written.success is False
            assert written.errors[0].kind == ErrorKind.invalid and written.errors[0].path == target
            made = await storage.mkdir(path=target, parents=True)
            assert made.success is False and made.errors[0].kind == ErrorKind.invalid
        assert (await storage.stat(path=Path("/.vfs"))).success is False
        await storage.close()

    async def test_meta_paths_beside_trash_still_write(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        doc = Path("/.vfs/docs/a.txt")
        result = await storage.write(entries=[Entry(path=doc, kind="file", content="v1")], parents=True)
        assert result.success is True
        assert (await storage.read(path=doc)).observations[0].content == "v1"
        await storage.close()


class TestArbitration:
    """Both arbitration arms resolve conflicts the plan could not see."""

    async def test_catch_retry_arm_serves_the_write_family(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, arbitration="catch_retry")
        result = await storage.write(
            entries=[Entry(path=Path("/d"), kind="directory"), Entry(path=Path("/d/f.txt"), content="x")]
        )
        assert result.success is True
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "x"
        again = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="y")])
        assert again.observations[0].status == "updated"
        await storage.close()

    async def test_catch_retry_serves_engines_without_multirow_insert(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, arbitration="catch_retry")
        # Oracle's posture: no multirow VALUES — the insert must take
        # driver executemany; identity is minted at staging, nothing read back.
        monkeypatch.setattr(storage._host.engine.sync_engine.dialect, "supports_multivalues_insert", False)
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        entries = [Entry(path=Path(f"/bulk/d{i // 10}/f{i:03}.txt"), content=f"v{i}") for i in range(50)]
        written = await storage.write(entries=entries, parents=True)
        assert written.success is True, written.errors[:3]
        created = [o for o in written.observations if str(o.path).endswith(".txt")]
        assert len(created) == 50
        # "Nothing read back" is a pin: one plan-fetch SELECT, the stamp watch
        # and the posture rows SELECT that label the creates, three depth-layer
        # inserts, the segment-posting and fs-mirror inserts riding the creates,
        # the content insert (fresh rows clear no bodies), parent bump, and the
        # stamp hold that proves the labels, last.
        own = [s for s in statements if not s.startswith(("BEGIN", "SAVEPOINT", "RELEASE"))]
        shapes = [s.split(None, 1)[0] for s in own if not is_statistics_statement(s)]
        expected = ["SELECT", "SELECT", "SELECT", "INSERT", "INSERT", "INSERT", "INSERT", "INSERT", "INSERT"]
        expected.extend(["UPDATE", "SELECT"])
        assert shapes == expected, statements
        assert (await storage.read(path=Path("/bulk/d0/f007.txt"))).observations[0].content == "v7"
        again = await storage.write(entries=[Entry(path=Path("/bulk/d0/f007.txt"), content="y")])
        assert again.observations[0].status == "updated"
        await storage.close()

    async def test_conflicted_chunk_resolves_alone_not_the_layer(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f005.txt"), content="rival")])
        entry = storage._host.tables.entry
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            rival_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f005.txt"))).scalar_one()
            now = datetime.now(UTC)
            layer = [
                StagedEntry(
                    path=Path(f"/f{i:03}.txt"),
                    parent=Path("/"),
                    kind="file",
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )
                for i in range(12)
            ]
            rows = [_entry_values(s, root_key, None, now, 2) for s in layer]
            statements.clear()
            errors = await _catch_retry_layer(session, entry, layer, rows, 4, overwrite=True)
        assert errors == []
        assert layer[5].persistence == "absorb" and layer[5].entry_id == rival_key  # rival's row absorbed the write
        assert all(s.persistence == "insert" for i, s in enumerate(layer) if i != 5)
        # One conflict re-drives its own 4-row chunk, never the 12-row layer:
        # three chunk inserts, four row retries, one occupant probe.
        inserts = [s for s in statements if s.startswith("INSERT INTO")]
        probes = [s for s in statements if s.lstrip().startswith("SELECT")]
        assert len(inserts) == 3 + 4, statements
        assert len(probes) == 1, statements
        await storage.close()

    async def test_conflicts_in_separate_chunks_all_classify(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(
            entries=[Entry(path=Path("/f001.txt"), content="rival"), Entry(path=Path("/f009.txt"), content="rival")]
        )
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            now = datetime.now(UTC)
            layer = [
                StagedEntry(
                    path=Path(f"/f{i:03}.txt"),
                    parent=Path("/"),
                    kind="file",
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )
                for i in range(12)
            ]
            rows = [_entry_values(s, root_key, None, now, 2) for s in layer]
            errors = await _catch_retry_layer(session, entry, layer, rows, 4, overwrite=False)
        # Rivals sit in chunks 1 and 3: both classify — errors accumulate
        # across conflicted chunks, the last chunk never wins alone.
        assert sorted((e.kind, str(e.path)) for e in errors) == [
            (ErrorKind.exists, "/f001.txt"),
            (ErrorKind.exists, "/f009.txt"),
        ]
        await storage.close()

    async def test_resolve_rows_converts_or_classifies_per_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="rival")])
        await storage.mkdir(path=Path("/dir"))
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            rival_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).scalar_one()
            now = datetime.now(UTC)

            def staged_for(path: str, kind: ObjectKind) -> StagedEntry:
                return StagedEntry(
                    path=Path(path),
                    parent=Path("/"),
                    kind=kind,
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )

            # overwrite=True over a rival file: converted to a clobbering
            # update that adopts the rival row's identity.
            clobber = staged_for("/f.txt", "file")
            errors = await _resolve_rows(
                session, entry, [clobber], [_entry_values(clobber, root_key, None, now, 2)], overwrite=True
            )
            assert errors == []
            assert clobber.persistence == "absorb" and clobber.entry_id == rival_key

            # overwrite=False over a rival file: a definite exists outcome.
            refused = staged_for("/f.txt", "file")
            errors = await _resolve_rows(
                session, entry, [refused], [_entry_values(refused, root_key, None, now, 2)], overwrite=False
            )
            assert [e.kind for e in errors] == [ErrorKind.exists]

            # overwrite=True where the rival is a directory: wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await _resolve_rows(
                session, entry, [blocked], [_entry_values(blocked, root_key, None, now, 2)], overwrite=True
            )
            assert [e.kind for e in errors] == [ErrorKind.wrong_kind]

            # a directory create losing to a directory at the matching
            # address adopts it: mkdir-p forgiveness, no error.
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            dir_adopt = staged_for("/dir", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_adopt], [_entry_values(dir_adopt, root_key, None, now, 2)], overwrite=True
            )
            assert errors == []
            assert dir_adopt.persistence == "adopt" and dir_adopt.entry_id == dir_key

            # a directory create losing to a file occupant: exists.
            dir_loss = staged_for("/f.txt", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_loss], [_entry_values(dir_loss, root_key, None, now, 2)], overwrite=False
            )
            assert [e.kind for e in errors] == [ErrorKind.exists]
        await storage.close()

    async def test_resolve_rows_redrives_when_no_occupant_is_observable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="rival")])
        await storage.mkdir(path=Path("/dir"))
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            # The unique path index collides while (parent_id, name) is
            # vacant: the insert fails yet the occupant probe sees nothing.
            phantom = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/dir"),
                kind="file",
                persistence="insert",
                entry_id=str(ULID()),
                content="mine",
            )
            minted = phantom.entry_id
            with pytest.raises(StaleSnapshot):
                await _resolve_rows(
                    session,
                    entry,
                    [phantom],
                    [_entry_values(phantom, dir_key, None, datetime.now(UTC), 2)],
                    overwrite=True,
                )
        assert phantom.persistence == "insert" and phantom.entry_id == minted  # no conversion happened
        await storage.close()

    async def test_create_to_clobber_conversion_flows_through_apply(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        profile = replace(host.profile, arbitration="catch_retry")
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.profile, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, authority=None, budget=profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            mime_type=mine.mime_type,
            overwrite=True,
            parents=False,
        )
        assert status == "created" and plan.errors == []
        plan.pending.append((target, status))

        # A rival lands between the snapshot and execution.
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success is True
        entry = host.tables.entry
        async with host.session_factory() as peek:
            rival_key = (await peek.execute(select(entry.c.entry_id).where(entry.c.path == str(target)))).scalar_one()

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=True,
            )
            await writer.commit()

        # The losing create clobbered the rival's row: identity kept, the
        # version advanced SQL-side, and the observation equals a stat.
        assert result.success is True
        assert [(o.status, o.version) for o in result.observations] == [("created", 2)]
        async with host.session_factory() as peek:
            rows = (
                await peek.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == str(target)))
            ).all()
        assert rows == [(rival_key, 2)]
        assert (await storage.read(path=target)).observations[0].content == "mine"
        # The clobber replaced the rival's body, so it kept that body as the one version.
        versions = host.tables.versions
        async with host.session_factory() as peek:
            kept = (
                await peek.execute(
                    select(versions.c.version_number, versions.c.content, versions.c.is_snapshot).where(
                        versions.c.entry_id == rival_key
                    )
                )
            ).all()
        assert kept == [(1, "rival", True)]
        await storage.close()

    async def test_upsert_clobber_stays_insert_through_apply(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        assert host.profile.arbitration == "upsert"
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.profile, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, authority=None, budget=host.profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            mime_type=mine.mime_type,
            overwrite=True,
            parents=False,
        )
        assert status == "created" and plan.errors == []
        plan.pending.append((target, status))

        # A rival lands between the snapshot and execution.
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success is True
        entry = host.tables.entry
        async with host.session_factory() as peek:
            rival_key = (await peek.execute(select(entry.c.entry_id).where(entry.c.path == str(target)))).scalar_one()

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=True,
            )
            await writer.commit()

        # The upsert clobber already wrote the final row, so the staged
        # entry stays "insert" and no update pass bumps it a second time.
        assert result.success is True
        assert [(o.status, o.version) for o in result.observations] == [("created", 2)]
        staged = plan.staged[target]
        assert staged.persistence == "insert" and staged.entry_id == rival_key
        async with host.session_factory() as peek:
            rows = (
                await peek.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == str(target)))
            ).all()
        assert rows == [(rival_key, 2)]
        assert (await storage.read(path=target)).observations[0].content == "mine"
        # The clobber replaced the rival's body, so it kept that body as the one version.
        versions = host.tables.versions
        async with host.session_factory() as peek:
            kept = (
                await peek.execute(
                    select(versions.c.version_number, versions.c.content, versions.c.is_snapshot).where(
                        versions.c.entry_id == rival_key
                    )
                )
            ).all()
        assert kept == [(1, "rival", True)]
        await storage.close()

    async def test_upsert_layer_adopts_identity_or_classifies_per_rival(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="rival")])
        await storage.mkdir(path=Path("/dir"))
        entry = storage._host.tables.entry
        profile = storage._host.profile
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            root_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            rival = (
                await conn.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == "/f.txt"))
            ).one()
            now = datetime.now(UTC)

            def staged_for(path: str, kind: ObjectKind) -> StagedEntry:
                return StagedEntry(
                    path=Path(path),
                    parent=Path("/"),
                    kind=kind,
                    persistence="insert",
                    entry_id=str(ULID()),
                    content="mine",
                )

            async def run(layer: list[StagedEntry], *, overwrite: bool) -> list[ResultError]:
                rows = [_entry_values(s, root_key, None, now, 2) for s in layer]
                return await _upsert_layer(session, entry, profile, layer, rows, 50, overwrite=overwrite)

            # overwrite=True over a rival file: the clobber lands on the
            # rival's row and adopts its identity and bumped version...
            clobber = staged_for("/f.txt", "file")
            fresh = staged_for("/new.txt", "file")
            minted = fresh.entry_id
            errors = await run([clobber, fresh], overwrite=True)
            assert errors == []
            assert clobber.entry_id == rival.entry_id
            assert clobber.version == rival.version + 1
            # The clobber stays "insert": the upsert already wrote its final
            # row, so the update passes must never see it again.
            assert clobber.persistence == "insert"
            # ...while the non-conflicted winner in the same statement
            # keeps its staged-minted identity untouched.
            assert fresh.entry_id == minted and fresh.version == 1
            assert fresh.persistence == "insert"

            # overwrite=False over a rival file: DO NOTHING, a definite exists.
            refused = staged_for("/f.txt", "file")
            errors = await run([refused], overwrite=False)
            assert [e.kind for e in errors] == [ErrorKind.exists]

            # overwrite=True where the rival is a directory: the clobber's
            # kind guard refuses to update it — wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await run([blocked], overwrite=True)
            assert [e.kind for e in errors] == [ErrorKind.wrong_kind]

            # a directory create losing to a directory at the matching
            # address adopts it — no clobber, no error.
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            dir_adopt = staged_for("/dir", "directory")
            errors = await run([dir_adopt], overwrite=True)
            assert errors == []
            assert dir_adopt.persistence == "adopt" and dir_adopt.entry_id == dir_key

            # a directory create losing to a file occupant never clobbers: exists.
            dir_loss = staged_for("/f.txt", "directory")
            errors = await run([dir_loss], overwrite=False)
            assert [e.kind for e in errors] == [ErrorKind.exists]
        await storage.close()

    async def test_stale_guard_classifies_conflict(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")])
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            row = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).one()
            stale = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=row.entry_id,
                content="b",
                base_version=999_999,  # a rival moved the row past our snapshot
                version=1_000_000,
            )
            host = storage._host
            errors = await _update_materials(
                session,
                entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [stale],
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [ErrorKind.conflict]
        assert errors[0].retryable is True
        assert errors[0].message == "Conflict: concurrent modification"
        await storage.close()

    async def test_absorb_row_relocated_before_version_learning_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="theirs")])).success
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            row_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/f.txt"))).scalar_one()
            # A rival relocation rewrote the row's address mid-window: the
            # absorb's read-back must catch the mismatch and redrive.
            relocate = update(entry).where(entry.c.entry_id == row_id).values(path="/moved.txt", name="moved.txt")
            await session.execute(relocate)
            relocated = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/"),
                kind="file",
                persistence="absorb",
                entry_id=row_id,
                content="mine",
            )
            with pytest.raises(StaleSnapshot):
                await _update_materials(
                    session,
                    entry,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    [relocated],
                    now=datetime.now(UTC),
                )
            await session.rollback()
        await storage.close()

    async def test_absorb_row_vanishing_before_version_learning_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            # An absorb row whose adopted rival vanished before its
            # version learning: the address proof fails and redrives.
            vanished = StagedEntry(
                path=Path("/f.txt"),
                parent=Path("/"),
                kind="file",
                persistence="absorb",
                entry_id=str(ULID()),
                content="mine",
            )
            host = storage._host
            with pytest.raises(StaleSnapshot):
                await _update_materials(
                    session,
                    entry,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    [vanished],
                    now=datetime.now(UTC),
                )
        await storage.close()

    async def test_losing_create_without_overwrite_fails_the_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        profile = replace(host.profile, arbitration="catch_retry")
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.profile, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, authority=None, budget=profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            mime_type=mine.mime_type,
            overwrite=False,
            parents=False,
        )
        assert status == "created" and plan.errors == []
        plan.pending.append((target, status))

        # A rival lands between the snapshot and execution; without
        # overwrite the losing create cannot clobber — the batch fails.
        assert (await storage.write(entries=[Entry(path=target, content="rival")])).success is True

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=False,
            )
        assert result.success is False
        assert [e.kind for e in result.errors] == [ErrorKind.exists]
        assert (await storage.read(path=target)).observations[0].content == "rival"
        await storage.close()

    async def test_guarded_update_losing_its_row_fails_the_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="v1")])
        host = storage._host
        target = Path("/f.txt")

        # Snapshot at version 1 and stage a guarded update over it.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.profile, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, authority=None, budget=host.profile.key_byte_budget)
        status = plan.put_file(
            target,
            kind=mine.kind,
            content=mine.content,
            content_hash=mine.content_hash,
            size_bytes=mine.size_bytes,
            lines=mine.lines,
            mime_type=mine.mime_type,
            overwrite=True,
            parents=False,
        )
        assert status == "updated" and plan.errors == []
        plan.pending.append((target, status))

        # Two rival writes move the row past base + 1, so the read-back
        # can attribute the guarded update's miss unambiguously.
        assert (await storage.write(entries=[Entry(path=target, content="v2")])).success is True
        assert (await storage.write(entries=[Entry(path=target, content="v3")])).success is True

        async with host.session_factory() as writer:
            await writer.connection(execution_options={"vfs_writer": True})
            result = await _finish(
                writer,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                plan,
                op="write",
                overwrite=True,
            )
        assert result.success is False
        assert [e.kind for e in result.errors] == [ErrorKind.conflict]
        assert result.errors[0].retryable is True
        assert result.errors[0].message == "Conflict: concurrent modification"
        assert (await storage.read(path=target)).observations[0].content == "v3"
        await storage.close()

    def test_upsert_constructor_is_dialect_bound(self) -> None:
        assert _upsert_constructor(SQLITE) is sqlite_insert
        assert _upsert_constructor(POSTGRESQL) is pg_insert


class TestGuardedAttribution:
    """The statement-attribution ladder beyond what SQLite executes natively.

    The default suite drives the aggregate fast path and its per-row
    fallback on every guarded overwrite; these tests cover the set-based
    RETURNING arm through a session double — SQLite rejects the
    column-aliased VALUES join, which is why ``values_join`` is a
    declared profile bit — plus the forced per-row floor and the
    classified refusal. The VALUES arm itself is proven live by the
    postgres and mssql conformance legs.
    """

    async def test_returning_arm_attributes_guarded_success_by_membership(self) -> None:
        tables = build_vfs_tables()
        won = _staged_material("/won.txt", str(ULID()))
        lost = _staged_material("/lost.txt", str(ULID()))
        # The re-probe finds the lost row present: an honest conflict.
        probed: list[dict[str, object]] = [
            {"entry_id": lost.entry_id, "path": "/lost.txt", "version": 3, "content_hash": "a rival's body"}
        ]
        double = _ReturningSession([{"entry_id": won.entry_id, "version": 2}], probed=probed)
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [won, lost],
            now=datetime.now(UTC),
        )
        assert [e.kind for e in errors] == [ErrorKind.conflict]
        assert errors[0].path == lost.path
        updates = [s for s in double.statements if not isinstance(s, Select)]
        assert len(updates) == 1  # both rows rode one chunk

    async def test_returning_arm_guard_miss_reprobes_a_vanished_row_to_not_found(self) -> None:
        tables = build_vfs_tables()
        gone = _staged_material("/gone.txt", str(ULID()))
        double = _ReturningSession([], probed=[])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [gone],
            now=datetime.now(UTC),
        )
        assert [e.kind for e in errors] == [ErrorKind.not_found]
        assert errors[0].path == gone.path

    async def test_returning_arm_statement_is_a_guarded_values_join(self) -> None:
        tables = build_vfs_tables()
        staged = _staged_material("/f.txt", str(ULID()))
        double = _ReturningSession([{"entry_id": staged.entry_id, "version": 2}])
        await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [staged],
            now=datetime.now(UTC),
        )
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "FROM (VALUES" in sql
        assert "RETURNING" in sql
        assert "incoming.v_base" in sql  # the version guard joins the VALUES row

    async def test_returning_arm_absorb_learns_returned_version_or_redrives(self) -> None:
        tables = build_vfs_tables()
        absorbed = _staged_material("/won.txt", str(ULID()), persistence="absorb")
        vanished = _staged_material("/gone.txt", str(ULID()), persistence="absorb")
        double = _ReturningSession([{"entry_id": absorbed.entry_id, "version": 7}])
        with pytest.raises(StaleSnapshot):
            await _update_materials(
                cast("AsyncSession", double),
                tables.entry,
                POSTGRESQL,
                32_000,
                900,
                [absorbed, vanished],
                now=datetime.now(UTC),
            )
        assert absorbed.version == 7  # the statement reported the version it assigned
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "incoming.v_base" not in sql  # no version guard: increments SQL-side
        assert "incoming.v_path" in sql  # the address proof joins the VALUES row

    async def test_values_arm_chunks_by_parameter_budget_and_merges_attribution(self) -> None:
        # A budget of 2*width - 1 fits exactly one VALUES tuple per statement:
        # three staged rows must ride three statements, and attribution
        # must merge across the chunks — statement size never grows with
        # batch size.
        tables = build_vfs_tables()
        staged = [_staged_material(f"/f{i}.txt", str(ULID())) for i in range(3)]
        width = len(_CLOBBER_COLUMNS) + 4
        double = _ReturningSession([{"entry_id": s.entry_id, "version": 2} for s in staged])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            2 * width - 1,
            900,
            staged,
            now=datetime.now(UTC),
        )
        assert errors == []
        assert len(double.statements) == 3

    async def test_aggregate_arm_rolls_back_before_the_per_row_redrive(self, tmp_path) -> None:
        # A mixed batch through the NATURAL aggregate arm: without the
        # savepoint rollback the re-drive would judge already-applied
        # state, and the fresh row would false-conflict beside the stale.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a"), Entry(path=Path("/b.txt"), content="b")])
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            found = await session.execute(select(entry.c.entry_id, entry.c.path, entry.c.version))
            rows = {m["path"]: m for m in found.mappings()}
            fresh = StagedEntry(
                path=Path("/a.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/a.txt"]["entry_id"],
                content="a2",
                base_version=rows["/a.txt"]["version"],
                version=rows["/a.txt"]["version"] + 1,
            )
            stale = StagedEntry(
                path=Path("/b.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/b.txt"]["entry_id"],
                content="b2",
                base_version=999_999,
                version=1_000_000,
            )
            errors = await _update_materials(
                session,
                entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [fresh, stale],
                now=datetime.now(UTC),
            )
            after = await session.execute(select(entry.c.path, entry.c.version))
            versions = {m["path"]: m["version"] for m in after.mappings()}
        assert [e.kind for e in errors] == [ErrorKind.conflict]
        assert errors[0].path == stale.path
        # The fresh row applied exactly once; the stale row never moved.
        assert versions["/a.txt"] == rows["/a.txt"]["version"] + 1
        assert versions["/b.txt"] == rows["/b.txt"]["version"]
        await storage.close()

    async def test_forced_per_row_floor_attributes_each_rowcount(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a"), Entry(path=Path("/b.txt"), content="b")])
        host = storage._host
        entry = host.tables.entry
        # No sane aggregate: the ladder must land on per-row rowcounts.
        monkeypatch.setattr(host.engine.sync_engine.dialect, "supports_sane_multi_rowcount", False)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            found = await session.execute(select(entry.c.entry_id, entry.c.path, entry.c.version))
            rows = {m["path"]: m for m in found.mappings()}
            fresh = StagedEntry(
                path=Path("/a.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/a.txt"]["entry_id"],
                content="a2",
                base_version=rows["/a.txt"]["version"],
                version=rows["/a.txt"]["version"] + 1,
            )
            stale = StagedEntry(
                path=Path("/b.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=rows["/b.txt"]["entry_id"],
                content="b2",
                base_version=999_999,
                version=1_000_000,
            )
            errors = await _update_materials(
                session,
                entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [fresh, stale],
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [ErrorKind.conflict]
        assert errors[0].path == stale.path
        await storage.close()

    async def test_unverifiable_guard_classifies_instead_of_guessing(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        dialect = host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_multi_rowcount", False)
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        staged = _staged_material("/f.txt", str(ULID()))
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            errors = await _update_materials(
                session,
                host.tables.entry,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                [staged],
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [ErrorKind.unsupported]
        assert "cannot be verified" in errors[0].message
        await storage.close()


# ---------------------------------------------------------------------------
# Bytes bodies — the blob row, the source switch, the render stamp
# ---------------------------------------------------------------------------


class TestBytesBodies:
    """A bytes write lands a blob row and a pending stamp; text and bytes never share a row."""

    async def test_a_bytes_write_lands_the_blob_and_no_content_row(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        body = b"%PDF-1.4\x00\xff" * 100
        written = await storage.write(entries=[Entry(path=Path("/r.pdf"), data=body)])
        assert written.success is True
        assert written.observations[0].size_bytes == len(body)
        inserts = [s for s in statements if s.startswith("INSERT INTO vfs_")]
        assert any("vfs_blobs" in s for s in inserts) and not any("vfs_content" in s for s in inserts)
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            blob = (await session.execute(select(tables.blobs.c.data))).scalar_one()
            texts = (await session.execute(select(tables.content.c.entry_id))).all()
            row = (await session.execute(select(tables.entry).where(tables.entry.c.path == "/r.pdf"))).one()
        assert blob == body and texts == []
        assert (row.source, row.render_status, row.render_source_hash, row.render_generation) == (
            "bytes",
            "pending",
            None,
            None,
        )
        assert row.mime_type == "application/pdf" and row.lines == 0
        await storage.close()

    async def test_switching_the_source_leaves_one_body_and_clears_the_other(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        tables = storage._host.tables

        async def bodies() -> tuple[list[str], list[bytes]]:
            async with storage._host.session_factory() as session:
                texts = (await session.execute(select(tables.content.c.content))).scalars().all()
                blobs = (await session.execute(select(tables.blobs.c.data))).scalars().all()
            return list(texts), list(blobs)

        assert (await storage.write(entries=[Entry(path=Path("/f"), content="text")])).success is True
        assert await bodies() == (["text"], [])
        assert (await storage.write(entries=[Entry(path=Path("/f"), data=b"\x00bytes")])).success is True
        assert await bodies() == ([], [b"\x00bytes"])
        stat = (await storage.stat(path=Path("/f"))).observations[0]
        assert (stat.source, stat.render_status, stat.version) == ("bytes", "pending", 2)
        assert (await storage.write(entries=[Entry(path=Path("/f"), content="again")])).success is True
        assert await bodies() == (["again"], [])
        stat = (await storage.stat(path=Path("/f"))).observations[0]
        assert (stat.source, stat.render_status, stat.version) == ("text", None, 3)
        await storage.close()

    async def test_overwriting_bytes_drops_the_rendering_and_restarts_the_stamp(self, tmp_path) -> None:
        # Slice B writes the rendering and the stamp; a later write of new
        # bytes must leave neither behind, or a stale text would be served.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/r.pdf"), data=b"%PDF-1")])).success is True
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            key = (
                await conn.execute(select(tables.entry.c.entry_id).where(tables.entry.c.path == "/r.pdf"))
            ).scalar_one()
            await conn.execute(
                update(tables.entry)
                .where(tables.entry.c.entry_id == key)
                .values(render_status="ok", render_source_hash="h" * 64, render_generation="pdf/1", lines=3)
            )
            await conn.execute(insert(tables.content).values(entry_id=key, created_at=datetime.now(UTC), content="x"))
            await session.commit()
        assert (await storage.read(path=Path("/r.pdf"))).observations[0].content == "x"
        assert (await storage.write(entries=[Entry(path=Path("/r.pdf"), data=b"%PDF-2")])).success is True
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(tables.entry).where(tables.entry.c.path == "/r.pdf"))).one()
            texts = (await session.execute(select(tables.content.c.entry_id))).all()
        assert (row.render_status, row.render_source_hash, row.render_generation, row.lines) == (
            "pending",
            None,
            None,
            0,
        )
        assert texts == []
        await storage.close()

    async def test_blob_inserts_page_by_bytes_in_flight(self, tmp_path, monkeypatch) -> None:
        # Ten 1 KB bodies under a 2.5 KB page budget land in five statements;
        # a body past the budget rides alone (the flush law's singleton rule).
        monkeypatch.setattr(writes_module, "BLOB_PAGE_BYTES", 2500)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        entries = [Entry(path=Path(f"/b{i}.bin"), data=bytes([i]) * 1000) for i in range(10)]
        entries.append(Entry(path=Path("/huge.bin"), data=b"\xff" * 9000))
        written = await storage.write(entries=entries)
        assert written.success is True
        assert sum(1 for s in statements if s.startswith("INSERT INTO vfs_blobs")) == 6
        read = await storage.read(path=Path("/huge.bin"), columns=frozenset({"data"}))
        assert read.observations[0].data == b"\xff" * 9000
        await storage.close()

    async def test_edit_refuses_a_bytes_sourced_row(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/r.pdf"), data=b"%PDF-1")])).success is True
        result = await storage.edit(path=Path("/r.pdf"), edits=[EditOperation(old="a", new="b")])
        assert result.success is False
        assert result.errors[0].kind is ErrorKind.wrong_kind
        assert result.errors[0].message == "Wrong kind: binary body; replace the bytes through write"
        assert result.errors[0].path == "/r.pdf"
        await storage.close()

    async def test_a_body_past_the_engines_value_cap_classifies_unsupported(self, tmp_path) -> None:
        # SQLite's length limit lowered on the live connection: the engine's
        # own cap, named by the engine, never a vfs ceiling.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.session_factory() as session:
            raw = await (await session.connection()).get_raw_connection()
            driver = cast("Any", raw.driver_connection)
            driver._conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4096)
        result = await storage.write(entries=[Entry(path=Path("/big.bin"), data=b"x" * 10_000)])
        assert result.success is False
        assert result.errors[0].kind is ErrorKind.unsupported
        assert "single-value limit" in result.errors[0].message
        assert result.errors[0].retryable is False
        small = await storage.write(entries=[Entry(path=Path("/small.bin"), data=b"x" * 100)])
        assert small.success is True
        await storage.close()


async def test_a_vouched_line_count_is_replaced_by_the_stored_bodys(tmp_path) -> None:
    storage = DatabaseStorage(url=_url(tmp_path))
    try:
        vouched = Entry.model_validate(
            {"path": "/two.txt", "content": "one\ntwo"}, context={MEASURED_BODY: BodyMetrics("0" * 64, 1, 7)}
        )
        assert (await storage.write(entries=[vouched])).success is True
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            lines = (await session.execute(select(entry.c.lines).where(entry.c.path == "/two.txt"))).scalar_one()
        assert lines == 2
    finally:
        await storage.close()


async def test_large_bodies_are_measured_in_one_offloaded_hop(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    hops: list[int] = []
    real = writes_module.call_offloaded

    async def counted(executor: Any, work: Any) -> Any:
        hops.append(1)
        return await real(executor, work)

    monkeypatch.setattr(writes_module, "call_offloaded", counted)
    storage = DatabaseStorage(url=_url(tmp_path))
    try:
        batches = {
            "large": [b"a" * 150_000, b"b" * 150_000, b"c" * 10],
            "small": [bytes([n]) * 1_000 for n in range(10)],
            "many": [n.to_bytes(2, "big") * 49 + b"z" for n in range(2_000)],
            "at_total": [bytes([n]) * 10_000 for n in range(10)],
            "under_total": [bytes([n]) * 9_999 for n in range(10)] + [b"\xff" * 9],
        }
        expected = {"large": 1, "small": 0, "many": 1, "at_total": 1, "under_total": 0}
        for name, bodies in batches.items():
            hops.clear()
            entries = [Entry(path=Path(f"/{name}/{n:05}.bin"), data=body) for n, body in enumerate(bodies)]
            assert (await storage.write(entries=entries, parents=True)).success is True
            assert len(hops) == expected[name], name
            for entry, body in zip(entries, bodies, strict=True):
                row = (await storage.stat(path=entry.path)).one()
                assert row.content_hash == measure_bytes(body).content_hash
    finally:
        await storage.close()


async def test_a_body_changed_during_the_hop_is_never_stored_under_another_hash(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The call totals past the inline cap, so it hops; one entry's body is
    # swapped as the hop starts and another carries a forged measurement.
    public = b"public body " * 10_000
    target = Entry(path=Path("/eve/handbook.bin"), data=public)
    forged = Entry(path=Path("/eve/forged.bin"), data=b"forged " * 20)
    forged.content_hash = "b" * 64
    forged.size_bytes = 1
    real = writes_module.call_offloaded

    async def swapping(executor: Any, work: Any) -> Any:
        target.data = b"swapped body"
        return await real(executor, work)

    monkeypatch.setattr(writes_module, "call_offloaded", swapping)
    storage = DatabaseStorage(url=_url(tmp_path))
    try:
        assert (await storage.write(entries=[target, forged], parents=True)).success is True
        for path in ("/eve/handbook.bin", "/eve/forged.bin"):
            stored = (await storage.read(path=Path(path), columns=frozenset({"data"}))).one().data
            row = (await storage.stat(path=Path(path))).one()
            assert stored is not None
            assert (row.content_hash, row.size_bytes) == (measure_bytes(stored).content_hash, len(stored))
        handbook = await storage.read(path=Path("/eve/handbook.bin"), columns=frozenset({"data"}))
        assert handbook.one().data == public
    finally:
        await storage.close()


async def test_an_edit_call_matches_in_one_hop_with_a_budget_per_match(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    hops: list[int] = []
    real = writes_module.call_offloaded

    async def counted(executor: Any, work: Any) -> Any:
        hops.append(1)
        return await real(executor, work)

    storage = DatabaseStorage(url=_url(tmp_path))
    try:
        # ten near-misses of about 500,000 cells each: each fits its own budget
        body = "a\n" + "x" * 707 + "\nb\n"
        entries = [Entry(path=Path(f"/e/{n}.txt"), content=body) for n in range(10)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        monkeypatch.setattr(writes_module, "call_offloaded", counted)
        edit = EditOperation(old="a\n" + "x" * 706 + "y" + "\nb", new="done")
        result = await storage.edit(edits=[edit], observations=[e.to_observation() for e in entries])
        assert result.success is True, result.errors
        assert len(hops) == 1
        for entry in entries:
            assert (await storage.read(path=entry.path)).one().content == "done\n"
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# Rights at the rows a write acts on
# ---------------------------------------------------------------------------


def _arm(monkeypatch: pytest.MonkeyPatch, storage: DatabaseStorage, arm: str) -> None:
    """Run *storage*'s creates through arbitration arm *arm*, whatever its engine declares."""
    monkeypatch.setattr(storage._host, "_profile", replace(storage._host.profile, arbitration=arm))


class TestLandingJudgment:
    """A create that arbitration turns into a change of a standing row is judged on that row."""

    @pytest.mark.parametrize("arm", ["upsert", "catch_retry"])
    async def test_a_create_that_lands_on_a_row_beyond_the_callers_rung_redrives(self, monkeypatch, arm) -> None:
        """A rival's row at the path absorbs bob's create only if bob may contribute to it.

        Guards the landing read in ``_apply``: deleted, or judged at the
        create slot, the clobber lands bob's body on alice's row in one attempt.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        _arm(monkeypatch, storage, arm)
        sessions = attempts(monkeypatch, storage)
        tables = storage._host.tables
        rival = clearing("write:before-apply", lambda: land(sessions[-1], tables, "/drop/x.txt", "alice", "add"))
        with installed("write:before-apply", rival):
            result = await storage.write(entries=[Entry(path=Path("/drop/x.txt"), content="bob")], authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        row = await row_at(storage, "/drop/x.txt")
        assert row is not None
        assert (row["owner_id"], row["version"], row["content"]) == ("bob", 1, "bob")
        assert await version_count(storage, row["entry_id"]) == 0

    @pytest.mark.parametrize("arm", ["upsert", "catch_retry"])
    async def test_a_create_that_lands_on_the_callers_own_row_absorbs_it(self, monkeypatch, arm) -> None:
        """The owner floor admits a landing on the caller's own row: no redrive, the row kept and bumped."""
        storage = InMemoryStorage()
        await drop_world(storage)
        _arm(monkeypatch, storage, arm)
        sessions = attempts(monkeypatch, storage)
        landed: list[str] = []

        async def act() -> None:
            landed.append(await land(sessions[-1], storage._host.tables, "/drop/x.txt", "bob", "add"))

        with installed("write:before-apply", clearing("write:before-apply", act)):
            result = await storage.write(entries=[Entry(path=Path("/drop/x.txt"), content="bob")], authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 1
        row = await row_at(storage, "/drop/x.txt")
        assert row is not None
        assert (row["entry_id"], row["version"], row["owner_id"], row["content"]) == (landed[0], 2, "bob", "bob")

    @pytest.mark.parametrize("arm", ["upsert", "catch_retry"])
    async def test_a_create_that_lands_where_the_caller_may_contribute_absorbs_it(self, monkeypatch, arm) -> None:
        """``contribute`` admits a landing on another owner's row: the row keeps its id and owner."""
        storage = InMemoryStorage()
        await drop_world(storage)
        granted = await storage.grant(path=Path("/drop"), principal="carol", level="contribute", authority=SYSTEM)
        assert granted.success is True
        _arm(monkeypatch, storage, arm)
        sessions = attempts(monkeypatch, storage)
        landed: list[str] = []

        async def act() -> None:
            landed.append(await land(sessions[-1], storage._host.tables, "/drop/x.txt", "alice", "add"))

        with installed("write:before-apply", clearing("write:before-apply", act)):
            result = await storage.write(entries=[Entry(path=Path("/drop/x.txt"), content="carol")], authority=CAROL)
        assert result.success is True, result.errors
        assert len(sessions) == 1
        row = await row_at(storage, "/drop/x.txt")
        assert row is not None
        assert (row["entry_id"], row["owner_id"], row["version"], row["content"]) == (landed[0], "alice", 2, "carol")

    async def test_a_landed_row_carries_the_side_rows_a_written_one_does(self) -> None:
        """The rival helper builds what a create builds: one fs mirror row and one segment posting per row."""
        storage = InMemoryStorage()
        await drop_world(storage)
        tables = storage._host.tables
        assert (await storage.write(entries=[Entry(path=Path("/drop/w.txt"), content="w")], authority=BOB)).success
        async with storage._host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            await land(session, tables, "/drop/l.txt", "alice", "add")
            await session.commit()
        counts = []
        for path in ("/drop/w.txt", "/drop/l.txt"):
            row = await row_at(storage, path)
            assert row is not None
            async with storage._host.session_factory() as session:
                edges = tables.edges.select().where(tables.edges.c.target_id == row["entry_id"])
                segments = tables.segments.select().where(tables.segments.c.entry_id == row["entry_id"])
                counts.append((len((await session.execute(edges)).all()), len((await session.execute(segments)).all())))
        assert counts[0] == counts[1] == (1, counts[0][1]) and counts[0][1] > 0


class TestStagedRowsAreJudged:
    """The rows the plan's own read stages an update or a revive over are judged from that read."""

    async def test_a_row_that_appears_before_the_plan_reads_is_judged(self, monkeypatch) -> None:
        """A row landed after the gate saw the path empty turns bob's create into an update he may not make.

        Guards ``admit_staged`` in ``_finish``: deleted, the plan's update
        branch rewrites alice's row with bob's body in one attempt.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        sessions = attempts(monkeypatch, storage)
        tables = storage._host.tables
        act = clearing("write:before-snapshot", lambda: land(sessions[-1], tables, "/drop/x.txt", "alice", "add"))
        with installed("write:before-snapshot", act):
            result = await storage.write(entries=[Entry(path=Path("/drop/x.txt"), content="bob")], authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        row = await row_at(storage, "/drop/x.txt")
        assert row is not None
        assert (row["owner_id"], row["version"], row["content"]) == ("bob", 1, "bob")

    async def test_an_edit_target_replaced_before_the_plan_reads_is_judged(self, monkeypatch) -> None:
        """An edit whose target was replaced by another owner's row after the gate edits nothing of it.

        Guards ``admit_staged`` on edit's update: deleted, alice's row is edited in one attempt.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        original = await row_at(storage, "/drop/b.txt")
        assert original is not None
        sessions = attempts(monkeypatch, storage)
        tables = storage._host.tables
        name = "write:before-snapshot"
        act = clearing(name, lambda: replace_row(sessions[-1], tables, "/drop/b.txt", "alice", "add"))
        edit = EditOperation(old="text", new="edited")
        with installed("write:before-snapshot", act):
            result = await storage.edit(edits=[edit], path=Path("/drop/b.txt"), authority=BOB)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        row = await row_at(storage, "/drop/b.txt")
        assert row is not None
        assert (row["entry_id"], row["owner_id"], row["content"]) == (original["entry_id"], "bob", "bob edited\n")

    @pytest.mark.parametrize(
        ("body", "shape"),
        [("text alpha\ntext beta\n", "two-matches"), ("nothing alpha\n", "no-match")],
        ids=["two-matches", "no-match"],
    )
    async def test_an_edit_never_answers_from_a_replaced_row_it_may_not_read(self, monkeypatch, body, shape) -> None:
        """An edit judges every live target row its plan read before matching any, so no error is built from one.

        Guards ``admit_targets`` in ``edit_rows``: deleted, an old text the
        unreadable replacement holds twice answers with that row's lines in the
        message, and one it lacks answers that the file does not hold it.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        sessions = attempts(monkeypatch, storage)
        tables, name = storage._host.tables, "write:before-snapshot"
        act = clearing(name, lambda: replace_row(sessions[-1], tables, "/drop/b.txt", "alice", "none", body=body))
        edit = EditOperation(old="text", new="edited")
        with installed(name, act):
            result = await storage.edit(edits=[edit], path=Path("/drop/b.txt"), authority=BOB)
        assert len(sessions) == 2, shape
        assert not any("alpha" in error.message for error in result.errors)
        assert result.success is True, result.errors
        row = await row_at(storage, "/drop/b.txt")
        assert row is not None and (row["owner_id"], row["content"]) == ("bob", "bob edited\n")

    async def test_an_errored_plan_is_judged_before_it_answers(self, monkeypatch) -> None:
        """A batch whose plan errors and also stages an update over a row its gate never saw redrives before answering.

        Guards ``admit_staged``'s place ahead of the ``plan.errors`` return:
        after it, the errored plan answers in one attempt from an unjudged row.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        sessions = attempts(monkeypatch, storage)
        tables, name = storage._host.tables, "write:before-snapshot"
        act = clearing(name, lambda: land(sessions[-1], tables, "/drop/x.txt", "alice", "add"))
        entries = [Entry(path=Path("/drop/x.txt"), content="bob"), Entry(path=Path("/drop/b.txt/c.txt"), content="c")]
        with installed(name, act):
            result = await storage.write(entries=entries, authority=BOB)
        assert len(sessions) == 2
        assert [(error.kind, error.path) for error in result.errors] == [(ErrorKind.wrong_kind, "/drop/b.txt")]

    async def test_a_revive_the_plan_stages_is_judged_at_the_restore_rung(self, monkeypatch) -> None:
        """A tombstoned row landed after the gate is revived only at ``read_write``, restore's rung.

        Guards the revive's rung in ``admit_staged``: judged at the
        verb's ``contribute``, carol revives alice's deleted row in one attempt.
        """
        storage = InMemoryStorage()
        await drop_world(storage)
        granted = await storage.grant(path=Path("/drop"), principal="carol", level="contribute", authority=SYSTEM)
        assert granted.success is True
        sessions = attempts(monkeypatch, storage)

        async def act() -> None:
            await land(sessions[-1], storage._host.tables, "/drop/y.txt", "alice", "add", deleted=True)

        with installed("write:before-snapshot", clearing("write:before-snapshot", act)):
            result = await storage.write(entries=[Entry(path=Path("/drop/y.txt"), content="carol")], authority=CAROL)
        assert result.success is True, result.errors
        assert len(sessions) == 2
        row = await row_at(storage, "/drop/y.txt")
        assert row is not None
        assert (row["owner_id"], row["deleted_at"], row["version"]) == ("carol", None, 1)


# ---------------------------------------------------------------------------
# What a mint's label proof costs — two statements a call that creates a row
# ---------------------------------------------------------------------------

# Statements a driver issues around the body that are no part of it.
_CONTROL = ("BEGIN", "SAVEPOINT", "RELEASE", "COMMIT", "ROLLBACK", "PRAGMA", "SAVE TRANSACTION", "SET ")


def _body(statements: list[str]) -> list[str]:
    """The statements a call's body issued: no transaction control, no statistics detection."""
    return [s for s in statements if not s.lstrip().upper().startswith(_CONTROL) and not is_statistics_statement(s)]


def _is_stamp_read(statement: str) -> bool:
    """A read of one stamp row, the watch or the hold: never the fence's maximum over the caller's ids."""
    lowered = statement.lstrip().lower()
    return lowered.startswith("select") and "principal_revisions" in lowered and "max(" not in lowered


@asynccontextmanager
async def _label_store(env_var: str | None, tmp_path: FsPath) -> AsyncIterator[DatabaseStorage]:
    """The label world on SQLite, or on the server leg *env_var* names, with bob granted ``read_write`` at ``/p``."""
    if env_var is None:
        storage = DatabaseStorage(url=_url(tmp_path))
        try:
            await _label_world_with_bob(storage)
            yield storage
        finally:
            await storage.close()
        return
    async with server_storage(env_var, posture="none") as served:
        await _label_world_with_bob(served)
        yield served


async def _label_world_with_bob(storage: DatabaseStorage) -> None:
    await label_world(storage)
    assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True


def _mints(
    storage: DatabaseStorage, who: str, minter: Authority | None, files: int
) -> dict[str, Callable[[], Awaitable[Result]]]:
    """Each call that creates a row, by *minter*: one file, a batch with parents, a move and a copy."""
    one, moved, copied = (Path(f"/p/{name}-{who}.txt") for name in ("one", "moved", "copied"))
    batch = [Entry(path=Path(f"/p/b-{who}/d{n % 100}/f{n}.txt"), content="x") for n in range(files)]
    return {
        "one file": lambda: storage.write(entries=[Entry(path=one, content="x")], authority=minter),
        "batch": lambda: storage.write(entries=batch, parents=True, authority=minter),
        "move": lambda: storage.move(operations=[ResolvedPair(src=one, dest=moved)], authority=minter),
        "copy": lambda: storage.copy(operations=[ResolvedPair(src=moved, dest=copied)], authority=minter),
    }


class TestLabelCost:
    """A call that creates a row reads the everyone stamp before its labels and holds it last; no other call does."""

    @pytest.mark.parametrize("files", [100, pytest.param(10_000, marks=pytest.mark.slow)])
    @pytest.mark.parametrize("env_var", [pytest.param(None, id="sqlite"), *ENGINE_LEGS])
    async def test_a_mint_proves_its_label_in_two_statements(
        self, env_var: str | None, files: int, tmp_path: FsPath
    ) -> None:
        """One watch before the first posture read and one hold as the body's last statement, at any batch size.

        Guards the proof's cost and its order: a watch after the posture
        read could be newer than the labels it vouches for, and a hold
        that is not last would keep its lock through the rest of the body.
        """
        async with _label_store(env_var, tmp_path) as storage:
            for minter in (None, BOB):
                warm = [Entry(path=Path(f"/p/warm-{minter is None}.txt"), content="w")]
                assert (await storage.write(entries=warm, authority=minter)).success is True
            statements: list[str] = []
            engine = storage._host.engine.sync_engine
            event.listen(engine, "before_cursor_execute", lambda conn, cursor, sql, *rest: statements.append(sql))
            table_lock = storage._host.profile.share_lock.form == "table"
            for who, minter in (("system", None), ("granted", BOB)):
                for name, call in _mints(storage, who, minter, files).items():
                    statements.clear()
                    result = await call()
                    assert result.success is True, (name, who, result.errors)
                    body = _body(statements)
                    stamps = [n for n, sql in enumerate(body) if _is_stamp_read(sql)]
                    locks = [n for n, sql in enumerate(body) if sql.lstrip().upper().startswith("LOCK TABLE")]
                    assert len(stamps) == 2, (name, who, body)
                    # The label's own read of the posture rows is the statement the watch precedes.
                    assert "vfs_grants" in body[stamps[0] + 1], (name, who, body[stamps[0] : stamps[0] + 2])
                    assert stamps[1] == len(body) - 1, (name, who, body[-3:])
                    assert locks == ([stamps[1] - 1] if table_lock else []), (name, who, body[-3:])
                statements.clear()
                rewrite = [Entry(path=Path(f"/p/copied-{who}.txt"), content="again")]
                assert (await storage.write(entries=rewrite, authority=minter)).success is True
                assert not [sql for sql in _body(statements) if _is_stamp_read(sql)]


class TestExpectedVersion:
    """A write that states the version it expects costs what a plain write costs, and a stale one writes nothing."""

    async def test_a_stale_expected_version_runs_the_snapshot_and_no_write(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        for body in ("one", "two"):
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content=body)])).success is True
        await storage._host.settle_statistics()
        statements = _statements_of(storage)
        stale = await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")], if_versions={Path("/a.txt"): 1})
        assert [(e.kind, e.data, e.retryable) for e in stale.errors] == [(ErrorKind.conflict, {"version": 2}, False)]
        # The snapshot is the whole call: nothing is updated, minted or replaced.
        own = _own(statements)
        assert len(own) == 1 and own[0].startswith("SELECT"), own
        await storage.close()

    @pytest.mark.parametrize("files", [100, pytest.param(10_000, marks=pytest.mark.slow)])
    async def test_a_key_for_every_row_adds_no_statement(self, files: int, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        narrowed = replace(storage._host.profile, in_list_budget=1_000)
        monkeypatch.setattr(EngineHost, "profile", property(lambda _self: narrowed))
        plain = [Path(f"/p/f{i:05}.txt") for i in range(files)]
        keyed = [Path(f"/k/f{i:05}.txt") for i in range(files)]
        seeded = [Entry(path=path, content="old") for path in (*plain, *keyed)]
        assert (await storage.write(entries=seeded, parents=True)).success is True
        await storage._host.settle_statistics()
        statements = _statements_of(storage)
        assert (await storage.write(entries=[Entry(path=path, content="new") for path in plain])).success is True
        without = [statement.split()[0] for statement in _own(statements)]
        statements.clear()
        expecting = dict.fromkeys(keyed, 1)
        written = await storage.write(
            entries=[Entry(path=path, content="new") for path in keyed], if_versions=expecting
        )
        assert written.success is True, written.errors
        assert [statement.split()[0] for statement in _own(statements)] == without
        # One row moved on: the batch is refused whole, and no statement writes.
        assert (await storage.write(entries=[Entry(path=keyed[0], content="rival")])).success is True
        await storage._host.settle_statistics()
        statements.clear()
        stale = await storage.write(
            entries=[Entry(path=path, content="newer") for path in keyed], if_versions=dict.fromkeys(keyed, 2)
        )
        assert [(e.kind, e.path, e.data) for e in stale.errors] == [(ErrorKind.conflict, keyed[0], {"version": 3})]
        assert [s for s in statements if s.startswith(("INSERT", "UPDATE", "DELETE"))] == []
        await storage.close()

    @pytest.mark.parametrize("keyed", [True, False], ids=["expected", "plain"])
    async def test_a_row_that_lost_its_guard_names_the_version_it_is_at(
        self, keyed: bool, tmp_path, monkeypatch
    ) -> None:
        # A second writer cannot commit inside an attempt on SQLite, so the
        # rival's commit is staged on the attempt's own session at the seam.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="one")])).success is True
        sessions = attempts(monkeypatch, storage)
        entry = storage._host.tables.entry

        async def rival() -> None:
            moved = update(entry).where(entry.c.path == "/a.txt").values(version=5, content_hash="another body")
            await sessions[-1].execute(moved)

        with installed("write:before-apply", clearing("write:before-apply", rival)):
            lost = await storage.write(
                entries=[Entry(path=Path("/a.txt"), content="two")],
                if_versions={Path("/a.txt"): 1} if keyed else None,
            )
        # Only a caller that expected no version may send the same call again.
        assert [(e.kind, e.data, e.retryable) for e in lost.errors] == [(ErrorKind.conflict, {"version": 5}, not keyed)]
        assert len(sessions) == 1
        await storage.close()

    async def test_a_guard_lost_to_a_rival_that_wrote_the_same_body_runs_again(self) -> None:
        tables = build_vfs_tables()
        lost = _staged_material("/lost.txt", str(ULID()))
        lost.content_hash = "the staged body"
        probed: list[dict[str, object]] = [
            {"entry_id": lost.entry_id, "path": "/lost.txt", "version": 2, "content_hash": "the staged body"}
        ]
        double = _ReturningSession([], probed=probed)
        with pytest.raises(StaleSnapshot):
            await _update_materials(
                cast("AsyncSession", double), tables.entry, POSTGRESQL, 32_000, 900, [lost], now=datetime.now(UTC)
            )

    async def test_a_guard_lost_to_a_row_that_moved_is_a_conflict_whatever_its_body(self) -> None:
        tables = build_vfs_tables()
        lost = _staged_material("/lost.txt", str(ULID()))
        lost.content_hash = "the staged body"
        probed: list[dict[str, object]] = [
            {"entry_id": lost.entry_id, "path": "/moved.txt", "version": 2, "content_hash": "the staged body"}
        ]
        double = _ReturningSession([], probed=probed)
        errors = await _update_materials(
            cast("AsyncSession", double), tables.entry, POSTGRESQL, 32_000, 900, [lost], now=datetime.now(UTC)
        )
        assert [(e.kind, e.path, e.data, e.retryable) for e in errors] == [
            (ErrorKind.conflict, "/lost.txt", {"version": 2}, True)
        ]


def _statements_of(storage: DatabaseStorage) -> list[str]:
    """A list that fills with every statement *storage* sends from now on, the statistics pass's left out."""
    statements: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if not is_statistics_statement(statement):
            statements.append(statement)

    return statements


def _own(statements: list[str]) -> list[str]:
    """*statements* without the ones that open, close or configure a transaction."""
    control = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")
    return [statement for statement in statements if not statement.startswith(control)]
