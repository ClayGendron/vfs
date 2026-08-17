"""Write mechanics beyond the conformance suite.

The conformance suite proves the verbs; this file holds the write-side
DB contract: one transaction per batch with statements bounded by tables
rather than entries, both arbitration arms (catch-retry and upsert)
resolving conflicts the plan could not see, the guarded-attribution
ladder past what SQLite executes natively, and trash as an ordinary
write target with no trash-specific arm.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import Select, event, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from ulid import ULID

from tests.support.database_helpers import _ReturningSession, _staged_material, _url
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import ObjectKind, Path
from vfs.results import ResultError, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import POSTGRESQL, SQLITE, StaleSnapshot
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
from vfs.storage.protocol import ResolvedPair
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Mutation core — DB-specific contract beyond the conformance suite
# ---------------------------------------------------------------------------


class TestWriteMechanics:
    """One transaction per batch, bounded statements, per-entry versions."""

    def test_material_values_and_clobber_columns_stay_in_lockstep(self) -> None:
        # Two encodings of the material-column set, one invariant: a key
        # added to either alone silently diverges create vs overwrite.
        staged = StagedEntry(
            path=Path("/f.txt"), parent=Path("/"), kind="file", persistence="insert", entry_id=str(ULID()), content="x"
        )
        material = _material_values(staged, "someone", datetime.now(UTC))
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
        # BEGIN + session PRAGMAs + plan select + one insert chunk +
        # content delete/insert + parent bump — O(tables), never O(entries).
        assert len(statements) <= 12, statements
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
            return [s for s in statements if not s.startswith(control)]

        created = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="a")])
        assert created.success is True
        # The round-trip budget is a contract: fetch, insert, content
        # delete + insert, parent bump.
        assert len(mutations()) == 5, mutations()
        statements.clear()
        overwritten = await storage.write(entries=[Entry(path=Path("/pin.txt"), content="b")])
        assert overwritten.success is True
        # Fetch, guarded update, content delete + insert — the update is
        # attributed from its own statement, so no read-back appears.
        assert len(mutations()) == 4, mutations()
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

    async def test_overwrite_restamps_the_owner(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="a")], user_id="alice")
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="b")], user_id="bob")
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            owner = (await conn.execute(select(entry.c.owner_id).where(entry.c.path == "/f.txt"))).scalar_one()
        assert owner == "bob"
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

    async def test_over_key_byte_budget_classifies_unaddressable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        storage._host._profile = replace(storage._host.profile, key_byte_budget=32)
        long_path = Path("/" + "x" * 60 + ".txt")
        written = await storage.write(entries=[Entry(path=long_path, content="x")])
        assert written.success is False
        assert written.errors[0].kind == VFSErrorKind.unaddressable
        made = await storage.mkdir(path=Path("/" + "d" * 60))
        assert made.success is False
        assert made.errors[0].kind == VFSErrorKind.unaddressable
        await storage.close()

    async def test_edit_of_a_missing_target_classifies_at_the_failing_component(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        result = await storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/ghost/a.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
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
        plan = WritePlan({}, user_id=None, budget=SQLITE.key_byte_budget)
        target = Path("/f.txt")
        plan.stage_create(target, kind="file", content="one", content_hash="h1", size_bytes=3, lines=1)
        minted = plan.staged[target].entry_id
        plan.stage_create(target, kind="file", content="two", content_hash="h2", size_bytes=3, lines=1)
        assert list(plan.staged) == [target]
        assert plan.staged[target].entry_id == minted
        assert plan.staged[target].persistence == "insert"
        assert (plan.staged[target].content, plan.staged[target].content_hash) == ("two", "h2")


class TestTrashWritability:
    """Trash is an ordinary write target: standard gates, no trash-specific arm."""

    async def test_write_into_trash_mints_the_bucket_chain_and_reads_back(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        target = Path("/.vfs/trash/2026-07-18-10/x.txt")
        written = await storage.write(entries=[Entry(path=target, kind="file", content="x")], parents=True)
        assert written.success is True
        assert written.observations[0].status == "created"
        assert (await storage.read(path=target)).observations[0].content == "x"
        bucket = (await storage.stat(path=target.parent_dir)).observations[0]
        assert bucket.kind == "directory"
        listing = await storage.ls(path=target.parent_dir)
        assert [o.path for o in listing.observations] == [str(target)]
        await storage.close()

    async def test_mkdir_and_edit_under_trash_take_the_ordinary_paths(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        bucket = Path("/.vfs/trash/2026-07-18-10")
        assert (await storage.mkdir(path=bucket, parents=True)).success is True
        target = bucket / "x.txt"
        await storage.write(entries=[Entry(path=target, kind="file", content="old text")])
        edited = await storage.edit(path=target, edits=[EditOperation(old="old", new="new")])
        assert edited.success is True
        assert (await storage.read(path=target)).observations[0].content == "new text"
        await storage.close()

    async def test_trash_writes_fail_through_the_standard_error_arms(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        target = Path("/.vfs/trash/2026-07-18-10/x.txt")
        await storage.write(entries=[Entry(path=target, kind="file", content="x")], parents=True)
        taken = await storage.write(entries=[Entry(path=target, kind="file", content="y")], overwrite=False)
        assert taken.errors[0].kind == VFSErrorKind.exists
        through_file = await storage.mkdir(path=target / "sub", parents=True)
        assert through_file.errors[0].kind == VFSErrorKind.wrong_kind
        assert through_file.errors[0].path == str(target)
        orphan = Entry(path=Path("/.vfs/trash/GHOST/y.txt"), kind="file", content="y")
        no_parents = await storage.write(entries=[orphan])
        assert no_parents.errors[0].kind == VFSErrorKind.not_found
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
        # "Nothing read back" is a pin: one plan-fetch SELECT, three
        # depth-layer inserts, the segment-posting insert riding the
        # creates, content delete + insert, parent bump.
        shapes = [s.split(None, 1)[0] for s in statements if not s.startswith(("BEGIN", "SAVEPOINT", "RELEASE"))]
        assert shapes == ["SELECT", "INSERT", "INSERT", "INSERT", "INSERT", "DELETE", "INSERT", "UPDATE"], statements
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
            rows = [_entry_values(s, root_key, None, now) for s in layer]
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
            rows = [_entry_values(s, root_key, None, now) for s in layer]
            errors = await _catch_retry_layer(session, entry, layer, rows, 4, overwrite=False)
        # Rivals sit in chunks 1 and 3: both classify — errors accumulate
        # across conflicted chunks, the last chunk never wins alone.
        assert sorted((e.kind, str(e.path)) for e in errors) == [
            (VFSErrorKind.exists, "/f001.txt"),
            (VFSErrorKind.exists, "/f009.txt"),
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
                session, entry, [clobber], [_entry_values(clobber, root_key, None, now)], overwrite=True
            )
            assert errors == []
            assert clobber.persistence == "absorb" and clobber.entry_id == rival_key

            # overwrite=False over a rival file: a definite exists outcome.
            refused = staged_for("/f.txt", "file")
            errors = await _resolve_rows(
                session, entry, [refused], [_entry_values(refused, root_key, None, now)], overwrite=False
            )
            assert [e.kind for e in errors] == [VFSErrorKind.exists]

            # overwrite=True where the rival is a directory: wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await _resolve_rows(
                session, entry, [blocked], [_entry_values(blocked, root_key, None, now)], overwrite=True
            )
            assert [e.kind for e in errors] == [VFSErrorKind.wrong_kind]

            # a directory create losing to a directory at the matching
            # address adopts it: mkdir-p forgiveness, no error.
            dir_key = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/dir"))).scalar_one()
            dir_adopt = staged_for("/dir", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_adopt], [_entry_values(dir_adopt, root_key, None, now)], overwrite=True
            )
            assert errors == []
            assert dir_adopt.persistence == "adopt" and dir_adopt.entry_id == dir_key

            # a directory create losing to a file occupant: exists.
            dir_loss = staged_for("/f.txt", "directory")
            errors = await _resolve_rows(
                session, entry, [dir_loss], [_entry_values(dir_loss, root_key, None, now)], overwrite=False
            )
            assert [e.kind for e in errors] == [VFSErrorKind.exists]
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
                    [_entry_values(phantom, dir_key, None, datetime.now(UTC))],
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
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=profile.key_byte_budget)
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
        await storage.close()

    async def test_upsert_clobber_stays_insert_through_apply(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        assert host.profile.arbitration == "upsert"
        target = Path("/f.txt")

        # Snapshot and plan while the site is vacant: a routine create.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=host.profile.key_byte_budget)
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
                rows = [_entry_values(s, root_key, None, now) for s in layer]
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
            assert [e.kind for e in errors] == [VFSErrorKind.exists]

            # overwrite=True where the rival is a directory: the clobber's
            # kind guard refuses to update it — wrong_kind.
            blocked = staged_for("/dir", "file")
            errors = await run([blocked], overwrite=True)
            assert [e.kind for e in errors] == [VFSErrorKind.wrong_kind]

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
            assert [e.kind for e in errors] == [VFSErrorKind.exists]
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
                user_id=None,
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert errors[0].retryable is True
        assert "Concurrent modification" in errors[0].message
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
                    user_id=None,
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
                    user_id=None,
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
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=profile.key_byte_budget)
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
        assert [e.kind for e in result.errors] == [VFSErrorKind.exists]
        assert (await storage.read(path=target)).observations[0].content == "rival"
        await storage.close()

    async def test_guarded_update_losing_its_row_fails_the_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/f.txt"), content="v1")])
        host = storage._host
        target = Path("/f.txt")

        # Snapshot at version 1 and stage a guarded update over it.
        async with host.session_factory() as reader:
            committed = await _fetch_committed(reader, host.tables, host.membership_budget, {target})
        mine = Entry(path=target, content="mine")
        plan = WritePlan(committed, user_id=None, budget=host.profile.key_byte_budget)
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
        assert [e.kind for e in result.errors] == [VFSErrorKind.conflict]
        assert result.errors[0].retryable is True
        assert "Concurrent modification" in result.errors[0].message
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
        tables = build_vfs_tables(table_name="vfs")
        won = _staged_material("/won.txt", str(ULID()))
        lost = _staged_material("/lost.txt", str(ULID()))
        # The re-probe finds the lost row present: an honest conflict.
        double = _ReturningSession([{"entry_id": won.entry_id, "version": 2}], probed=[{"entry_id": lost.entry_id}])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [won, lost],
            user_id=None,
            now=datetime.now(UTC),
        )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert str(lost.path) in errors[0].message
        updates = [s for s in double.statements if not isinstance(s, Select)]
        assert len(updates) == 1  # both rows rode one chunk

    async def test_returning_arm_guard_miss_reprobes_a_vanished_row_to_not_found(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        gone = _staged_material("/gone.txt", str(ULID()))
        double = _ReturningSession([], probed=[])
        errors = await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [gone],
            user_id=None,
            now=datetime.now(UTC),
        )
        assert [e.kind for e in errors] == [VFSErrorKind.not_found]
        assert str(gone.path) in errors[0].message

    async def test_returning_arm_statement_is_a_guarded_values_join(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        staged = _staged_material("/f.txt", str(ULID()))
        double = _ReturningSession([{"entry_id": staged.entry_id, "version": 2}])
        await _update_materials(
            cast("AsyncSession", double),
            tables.entry,
            POSTGRESQL,
            32_000,
            900,
            [staged],
            user_id=None,
            now=datetime.now(UTC),
        )
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "FROM (VALUES" in sql
        assert "RETURNING" in sql
        assert "incoming.v_base" in sql  # the version guard joins the VALUES row

    async def test_returning_arm_absorb_learns_returned_version_or_redrives(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
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
                user_id=None,
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
        tables = build_vfs_tables(table_name="vfs")
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
            user_id=None,
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
                user_id=None,
                now=datetime.now(UTC),
            )
            after = await session.execute(select(entry.c.path, entry.c.version))
            versions = {m["path"]: m["version"] for m in after.mappings()}
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert str(stale.path) in errors[0].message
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
                user_id=None,
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [VFSErrorKind.conflict]
        assert str(stale.path) in errors[0].message
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
                user_id=None,
                now=datetime.now(UTC),
            )
        assert [e.kind for e in errors] == [VFSErrorKind.unsupported]
        assert "cannot be verified" in errors[0].message
        await storage.close()
