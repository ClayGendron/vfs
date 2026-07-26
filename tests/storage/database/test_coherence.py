"""Write-vs-topology coherence — the two-sided guards on the parent row.

Seam-staged one-shot repros for every closed window: each test stages a
rival effect on the verb's own session at a named seam, then asserts the
guard that owns that window either aborts the batch or refuses the row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Select, delete, insert, select, update
from sqlalchemy.dialects import mssql, postgresql
from sqlalchemy.exc import IntegrityError
from ulid import ULID

from tests.support.database_helpers import _ReturningSession, _staged_material, _url
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results import Result, Severity, VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import (
    GENERIC,
    MYSQL,
    POSTGRESQL,
    PROFILES,
    SQLITE,
    StaleSnapshot,
    profile_for,
    statement_budget,
)
from vfs.storage.backends.database.seams import clear, installed
from vfs.storage.backends.database.staging import StagedEntry, WritePlan
from vfs.storage.backends.database.topology import (
    _claim,
    delete_rows,
    restore_rows,
    sweep_rows,
    transfer_rows,
)
from vfs.storage.backends.database.writes import (
    _CLOBBER_COLUMNS,
    _bump_by_values,
    _bump_parents,
    _bump_values_stmt,
    _classify_arbitration_loss,
    _classify_guard_misses,
    _entry_values,
    _resolve_rows,
    _update_materials,
    _upsert_layer,
    _values_update_stmt,
    edit_rows,
    write_rows,
)
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Write-vs-topology coherence — the two-sided guards on the parent row
# ---------------------------------------------------------------------------


class TestWriteVsTopologyCoherence:
    """Seam-staged one-shot repros for every closed window.

    Handlers run on the verb's own session, so their effects are exactly
    what the guards' current reads would see from a committed rival —
    SQLite's single-writer lock rules out a genuine second connection,
    which is what the engine-leg race suite is for.
    """

    async def test_bump_guard_aborts_when_a_parent_relocates_mid_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                stmt = update(entry).where(entry.c.path == "/d").values(path="/d-moved", name="d-moved")
                await session.execute(stmt)

            with installed("write:before-apply", rival), pytest.raises(StaleSnapshot):
                await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/d/f.txt"), content="x")],
                    overwrite=True,
                    parents=False,
                    user_id=None,
                )
            await session.rollback()
        # Nothing committed: no torn child, and the parent stands untouched.
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        assert (await storage.stat(path=Path("/d"))).success is True
        await storage.close()

    async def test_bump_guard_aborts_when_a_parent_is_destroyed_mid_batch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                await session.execute(delete(entry).where(entry.c.path == "/d"))

            with installed("write:before-apply", rival), pytest.raises(StaleSnapshot):
                await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/d/f.txt"), content="x")],
                    overwrite=True,
                    parents=False,
                    user_id=None,
                )
            await session.rollback()
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        await storage.close()

    async def test_backend_redrives_a_stale_snapshot_and_classifies_exhaustion(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        fired = 0

        async def once() -> None:
            nonlocal fired
            fired += 1
            if fired == 1:
                raise StaleSnapshot("staged miss")

        with installed("write:before-apply", once):
            result = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        assert result.success is True
        assert fired == 2  # attempt one raised, the redrive landed

        async def always() -> None:
            raise StaleSnapshot("staged miss")

        with installed("write:before-apply", always):
            exhausted = await storage.write(entries=[Entry(path=Path("/d/g.txt"), content="x")])
        assert exhausted.success is False
        [error] = exhausted.errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        await storage.close()

    async def test_edit_conflicts_when_an_ancestor_relocated_mid_window(self, tmp_path) -> None:
        # A subtree rewrite moves descendant paths without bumping their
        # versions — the path predicate, not the version, must miss.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="old")], parents=True)
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                stmt = update(entry).where(entry.c.path == "/d/f.txt").values(path="/gone/f.txt")
                await session.execute(stmt)

            with installed("write:before-apply", rival):
                result = await edit_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    edits=[EditOperation(old="old", new="new")],
                    targets=[Path("/d/f.txt")],
                    user_id=None,
                )
            await session.rollback()
        assert result.success is False
        [error] = result.errors
        assert error.kind == VFSErrorKind.conflict
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "old"
        await storage.close()

    async def test_write_never_adopts_a_row_whose_stored_path_disagrees(self, tmp_path) -> None:
        # The ghost name-squat: a row matched by (parent_id, name) whose
        # stored path contradicts the requested address absorbs nothing.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        ghost_id = str(ULID())
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            d_id = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            await conn.execute(
                insert(entry).values(
                    entry_id=ghost_id,
                    parent_id=d_id,
                    path="/elsewhere/late.txt",
                    name="late.txt",
                    kind="file",
                    version=5,
                    size_bytes=4,
                    lines=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        result = await storage.write(entries=[Entry(path=Path("/d/late.txt"), content="mine")], overwrite=True)
        assert result.success is False
        [error] = result.errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        async with host.session_factory() as session:
            conn = await session.connection()
            row = (await conn.execute(select(entry.c.version, entry.c.path).where(entry.c.entry_id == ghost_id))).one()
        assert (row.version, row.path) == (5, "/elsewhere/late.txt")
        await storage.close()

    async def test_copy_stamps_metadata_and_body_from_one_observation(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/src.txt"), content="original body")])
        expected_hash = Entry(path=Path("/src.txt"), content="original body").content_hash
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                src = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/src.txt"))).scalar_one()
                await session.execute(
                    update(entry).where(entry.c.entry_id == src).values(content_hash="rival-hash", size_bytes=10)
                )
                await session.execute(delete(tables.content).where(tables.content.c.entry_id == src))
                await session.execute(
                    insert(tables.content).values(entry_id=src, created_at=datetime.now(UTC), content="rival body")
                )

            with installed("transfer:post-collect", rival):
                result = await transfer_rows(
                    session,
                    tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="copy",
                    operations=[ResolvedPair(src=Path("/src.txt"), dest=Path("/copy.txt"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            assert result.success is True
            copied = (
                await session.execute(select(entry.c.entry_id, entry.c.content_hash).where(entry.c.path == "/copy.txt"))
            ).one()
            body_query = select(tables.content.c.content).where(tables.content.c.entry_id == copied.entry_id)
            body = (await session.execute(body_query)).scalar_one()
            await session.rollback()
        # Metadata and body ride one read: the pre-rival pair, coherent.
        assert copied.content_hash == expected_hash
        assert body == "original body"
        await storage.close()

    async def test_delete_claim_misses_when_a_rival_lands_post_collect(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                # A rival create's parent bump: the descendant list is stale.
                stmt = update(entry).where(entry.c.path == "/d").values(version=entry.c.version + 1)
                await session.execute(stmt)

            with installed("delete:post-collect", rival), pytest.raises(StaleSnapshot):
                await delete_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d")],
                    cascade=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        # The verb redrives clean once the rival is out of the window.
        assert (await storage.delete(path=Path("/d"))).success is True
        await storage.close()

    async def test_move_claim_misses_when_a_rival_lands_post_collect(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                stmt = update(entry).where(entry.c.path == "/d").values(version=entry.c.version + 1)
                await session.execute(stmt)

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="move",
                    operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))])).success is True
        await storage.close()

    async def test_restore_address_race_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        assert (await storage.delete(path=Path("/d/f.txt"))).success is True
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                # An unserialized write claims the destination after the ladder ran.
                d_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=d_id,
                        path="/d/f.txt",
                        name="f.txt",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("restore:post-resolve", rival), pytest.raises(StaleSnapshot):
                await restore_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d/f.txt")],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_purge_deletes_entries_first_so_a_rival_body_cannot_leak(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            f_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d/f.txt"))).scalar_one()

            async def rival() -> None:
                clear("purge:pre-entry-delete")
                # The rival's content replace: delete-then-insert of the body.
                await session.execute(delete(tables.content).where(tables.content.c.entry_id == f_id))
                await session.execute(
                    insert(tables.content).values(entry_id=f_id, created_at=datetime.now(UTC), content="fresh")
                )

            with installed("purge:pre-entry-delete", rival):
                result = await sweep_rows(
                    session,
                    tables,
                    host.profile,
                    host.membership_budget,
                    path=Path("/d"),
                    trash_days=90,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            assert result.success is True
            leftovers = (await session.execute(select(tables.content.c.entry_id))).all()
            await session.rollback()
        # The side-table pass ran after the entry delete over the same ids:
        # the rival's fresh body rode out with the subtree.
        assert leftovers == []
        await storage.close()

    async def test_sweep_reclaims_only_aged_orphan_content(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        host = storage._host
        tables = host.tables
        old_id, young_id = str(ULID()), str(ULID())
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(
                insert(tables.content).values(
                    entry_id=old_id, created_at=datetime.now(UTC) - timedelta(hours=25), content="old orphan"
                )
            )
            await conn.execute(
                insert(tables.content).values(
                    entry_id=young_id, created_at=datetime.now(UTC) - timedelta(hours=1), content="young orphan"
                )
            )
            await session.commit()
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True  # reclaims are warnings, not failures
        warnings = [e for e in result.errors if e.severity == Severity.warning]
        assert [w.data["entry_id"] for w in warnings if w.data] == [old_id]
        assert warnings[0].kind == VFSErrorKind.internal
        async with host.session_factory() as session:
            conn = await session.connection()
            remaining = {row.entry_id for row in await conn.execute(select(tables.content.c.entry_id))}
        assert remaining == {young_id}
        await storage.close()

    async def test_a_trash_root_squatter_never_blocks_orphan_reclaim(self, tmp_path) -> None:
        # The squatter skips the bucket walk; the reclaim pass is
        # unconditional — sweep is the only drain for orphaned bodies.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/.vfs/trash"), content="squat")], parents=True)
        host = storage._host
        tables = host.tables
        old_id = str(ULID())
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            await conn.execute(
                insert(tables.content).values(
                    entry_id=old_id, created_at=datetime.now(UTC) - timedelta(hours=25), content="old orphan"
                )
            )
            await session.commit()
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert result.observations == []
        assert result.errors[0].path == "/.vfs/trash"  # the squatter skip still surfaces first
        reclaims = [e for e in result.errors if e.data and "entry_id" in e.data]
        assert [w.data["entry_id"] for w in reclaims if w.data] == [old_id]
        async with host.session_factory() as session:
            conn = await session.connection()
            remaining = {row.entry_id for row in await conn.execute(select(tables.content.c.entry_id))}
        assert old_id not in remaining
        assert (await storage.read(path=Path("/.vfs/trash"))).observations[0].content == "squat"
        await storage.close()

    async def test_bump_values_arm_is_a_guarded_join_and_verifies_the_count(self) -> None:
        # The set-based arm SQLite cannot execute (postgres/mssql): the
        # statement joins (entry_id, path) and the RETURNING count is the
        # proof — one short row raises for the whole batch.
        tables = build_vfs_tables(table_name="vfs")
        pairs = [("A" * 26, "/a"), ("B" * 26, "/b")]
        double = _ReturningSession([{"entry_id": pairs[0][0]}])
        with pytest.raises(StaleSnapshot):
            await _bump_by_values(cast("AsyncSession", double), tables.entry, 32_000, 900, pairs)
        sql = str(double.statements[0].compile(dialect=postgresql.dialect()))
        assert "FROM (VALUES" in sql
        assert "incoming.v_path" in sql  # the address guard joins the VALUES row
        assert "RETURNING" in sql

    async def test_guard_miss_mode_is_declared_per_dialect(self) -> None:
        assert PROFILES["mysql"].guard_miss == "redrive"
        assert PROFILES["mariadb"].guard_miss == "redrive"
        assert GENERIC.guard_miss == "redrive"
        for name in ("sqlite", "postgresql", "mssql", "oracle"):
            assert PROFILES[name].guard_miss == "reprobe"
        # Unknown dialects inherit the conservative floor.
        assert profile_for("exotic").guard_miss == "redrive"

    async def test_redrive_mode_raises_instead_of_classifying_off_the_probe(self, tmp_path) -> None:
        # The mysql-family declaration through the live aggregate arm: a
        # zero-row guard must not be blamed off a probe the isolation
        # level would falsify — the whole method retries instead.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            found = await session.execute(select(entry.c.entry_id, entry.c.version).where(entry.c.path == "/a.txt"))
            row = found.one()
            stale = StagedEntry(
                path=Path("/a.txt"),
                parent=Path("/"),
                kind="file",
                persistence="update",
                entry_id=row.entry_id,
                content="a2",
                base_version=999_999,
                version=1_000_000,
            )
            with pytest.raises(StaleSnapshot):
                await _update_materials(
                    session,
                    entry,
                    MYSQL,  # redrive-mode profile over the live sqlite session
                    host.parameter_budget,
                    host.membership_budget,
                    [stale],
                    user_id=None,
                    now=datetime.now(UTC),
                )
            await session.rollback()
        await storage.close()

    async def test_move_address_race_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/e",
                        name="e",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="move",
                    operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_copy_address_race_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/src.txt"), content="x")])
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/copy.txt",
                        name="copy.txt",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="copy",
                    operations=[ResolvedPair(src=Path("/src.txt"), dest=Path("/copy.txt"))],
                    overwrite=False,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_purge_raises_when_a_collected_row_vanishes(self, tmp_path) -> None:
        # Collected entries cannot lawfully vanish under the serialization
        # point — a shortfall on the entry delete is a stale list, redriven.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(
            entries=[Entry(path=Path("/d/a.txt"), content="a"), Entry(path=Path("/d/b.txt"), content="b")],
            parents=True,
        )
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                clear("purge:pre-entry-delete")
                await session.execute(delete(entry).where(entry.c.path == "/d/a.txt"))

            with installed("purge:pre-entry-delete", rival), pytest.raises(StaleSnapshot):
                await sweep_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    path=Path("/d"),
                    trash_days=90,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_ghost_at_the_original_site_blocks_restore_with_retryable_conflict(self, tmp_path) -> None:
        # The claim collides on (parent_id, name) with a ghost whose stored
        # path is elsewhere: the destination probe finds nothing, and the
        # loss classifies as a retryable conflict — never raw driver text.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        assert (await storage.delete(path=Path("/d/f.txt"))).success is True
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            d_id = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            await conn.execute(
                insert(entry).values(
                    entry_id=str(ULID()),
                    parent_id=d_id,
                    path="/elsewhere/f.txt",
                    name="f.txt",
                    kind="file",
                    version=1,
                    size_bytes=0,
                    lines=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        result = await storage.restore(path=Path("/d/f.txt"))
        assert result.success is False
        [error] = result.errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "UNIQUE" not in error.message
        await storage.close()

    async def test_upsert_path_index_escape_redrives(self, tmp_path) -> None:
        # A rival claims the path with a different (parent_id, name): the
        # declared arbitration index never fires, the raw unique violation
        # is caught at the chunk savepoint, and the row-wise redrive blames
        # the exact row with the ladder's own conflict.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/d/late.txt",
                        name="squatter",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("write:before-apply", rival), pytest.raises(StaleSnapshot):
                await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/d/late.txt"), content="mine")],
                    overwrite=True,
                    parents=False,
                    user_id=None,
                )
            await session.rollback()
        await storage.close()

    async def test_resolve_rows_refuses_a_ghost_instead_of_absorbing(self, tmp_path) -> None:
        # The catch-retry arm's occupant probe: the matched row's stored
        # path contradicts the request — never absorbed, retryable conflict.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            conn = await session.connection(execution_options={"vfs_writer": True})
            d_id = (await conn.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()
            await conn.execute(
                insert(entry).values(
                    entry_id=str(ULID()),
                    parent_id=d_id,
                    path="/elsewhere/late.txt",
                    name="late.txt",
                    kind="file",
                    version=1,
                    size_bytes=0,
                    lines=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            staged = StagedEntry(
                path=Path("/d/late.txt"),
                parent=Path("/d"),
                kind="file",
                persistence="insert",
                entry_id=str(ULID()),
                content="mine",
            )
            rows = [_entry_values(staged, d_id, None, now)]
            errors = await _resolve_rows(session, entry, [staged], rows, overwrite=True)
            await session.rollback()
        [error] = errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert staged.persistence == "insert"  # never rewritten to absorb
        await storage.close()

    async def test_arbitration_loss_with_a_vanished_occupant_redrives(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        async with host.session_factory() as session:
            await session.connection()
            staged = _staged_material("/x.txt", str(ULID()))
            with pytest.raises(StaleSnapshot):
                await _classify_arbitration_loss(
                    session, host.tables.entry, staged, {"parent_id": str(ULID()), "name": "x.txt"}, clobber=False
                )
        await storage.close()

    async def test_classifier_redrive_mode_raises_for_any_miss(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        staged = _staged_material("/x.txt", str(ULID()))
        double = _ReturningSession([])
        with pytest.raises(StaleSnapshot):
            await _classify_guard_misses(cast("AsyncSession", double), tables.entry, MYSQL, 900, [staged])

    async def test_bump_parents_dispatches_by_declared_capability(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        parent_id = "D" * 26

        def plan() -> WritePlan:
            built = WritePlan({"/d": {"entry_id": parent_id, "path": "/d"}}, user_id=None, budget=4_096)  # ty: ignore[invalid-argument-type]
            built.stage_create(Path("/d/f.txt"), kind="file", content="x")
            return built

        # The set-based arm: a guarded VALUES join, verified by RETURNING.
        values_double = _ReturningSession([{"entry_id": parent_id}])
        errors = await _bump_parents(cast("AsyncSession", values_double), tables.entry, POSTGRESQL, 32_000, 900, plan())
        assert errors == []
        assert "FROM (VALUES" in str(values_double.statements[0].compile(dialect=postgresql.dialect()))
        # The per-row floor: no sane aggregate, each statement's own rowcount.
        floor_double = _ReturningSession([{"entry_id": parent_id}])
        errors = await _bump_parents(cast("AsyncSession", floor_double), tables.entry, SQLITE, 32_000, 900, plan())
        assert errors == []
        # Nothing verifiable: the classified refusal, never a blind bump.
        blind = _ReturningSession([])
        blind.get_bind = lambda: SimpleNamespace(  # ty: ignore[invalid-assignment]
            dialect=SimpleNamespace(
                update_returning=False,
                update_returning_multifrom=False,
                supports_sane_rowcount=False,
                supports_sane_multi_rowcount=False,
            )
        )
        errors = await _bump_parents(cast("AsyncSession", blind), tables.entry, GENERIC, 32_000, 900, plan())
        assert [e.kind for e in errors] == [VFSErrorKind.unsupported]

    async def test_new_seams_fire_inside_their_verbs(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(
            entries=[Entry(path=Path("/d/f.txt"), content="x"), Entry(path=Path("/m.txt"), content="y")],
            parents=True,
        )
        fired: list[str] = []

        def recorder(name: str):
            async def handler() -> None:
                fired.append(name)

            return handler

        with installed("delete:post-collect", recorder("delete:post-collect")):
            assert (await storage.delete(path=Path("/d"))).success is True
        with installed("transfer:post-collect", recorder("transfer:post-collect")):
            assert (await storage.move(operations=[ResolvedPair(src=Path("/m.txt"), dest=Path("/n.txt"))])).success
        with installed("restore:post-resolve", recorder("restore:post-resolve")):
            assert (await storage.restore(path=Path("/d"))).success is True
        with installed("purge:pre-entry-delete", recorder("purge:pre-entry-delete")):
            assert (await storage.sweep(path=Path("/n.txt"))).success is True
        assert fired == [
            "delete:post-collect",
            "transfer:post-collect",
            "restore:post-resolve",
            "purge:pre-entry-delete",
        ]
        await storage.close()

    async def test_claim_verifies_by_returning_when_rowcount_is_insane(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        entry = tables.entry
        stmt = update(entry).where(entry.c.entry_id == "X" * 26, entry.c.version == 1).values(version=2)

        def insane_bind(*, returning: bool) -> SimpleNamespace:
            dialect = SimpleNamespace(
                supports_sane_rowcount=False, update_returning=returning, delete_returning=returning
            )
            return SimpleNamespace(dialect=dialect)

        proven = _ReturningSession([{"entry_id": "X" * 26}])
        proven.get_bind = lambda: insane_bind(returning=True)  # ty: ignore[invalid-assignment]
        assert await _claim(cast("AsyncSession", proven), GENERIC, stmt, entry.c.entry_id, miss="m") is None
        missed = _ReturningSession([])
        missed.get_bind = lambda: insane_bind(returning=True)  # ty: ignore[invalid-assignment]
        with pytest.raises(StaleSnapshot):
            await _claim(cast("AsyncSession", missed), GENERIC, stmt, entry.c.entry_id, miss="m")
        # Nothing verifiable: the classified refusal, never a blind claim —
        # for the DELETE shape too, which consults delete_returning.
        blind = _ReturningSession([])
        blind.get_bind = lambda: insane_bind(returning=False)  # ty: ignore[invalid-assignment]
        refused = await _claim(cast("AsyncSession", blind), GENERIC, stmt, entry.c.entry_id, miss="m")
        assert refused is not None and refused.kind == VFSErrorKind.unsupported
        destroy = delete(entry).where(entry.c.entry_id == "X" * 26)
        refused = await _claim(cast("AsyncSession", blind), GENERIC, destroy, entry.c.entry_id, miss="m")
        assert refused is not None and refused.kind == VFSErrorKind.unsupported

    async def test_unverifiable_claims_refuse_the_topology_verbs(self, tmp_path, monkeypatch) -> None:
        # An insane-rowcount, no-RETURNING dialect must refuse each claim
        # site with unsupported — never pass a guard it cannot prove.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        await storage.mkdir(path=Path("/b"))
        await storage.mkdir(path=Path("/d"))
        assert (await storage.write(entries=[Entry(path=Path("/t.txt"), content="y")])).success
        assert (await storage.delete(path=Path("/t.txt"))).success
        host = storage._host
        dialect = host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        monkeypatch.setattr(dialect, "update_returning", False)
        monkeypatch.setattr(dialect, "delete_returning", False)
        # The delete reparent claim (its trash chain pre-minted above).
        result = await storage.delete(path=Path("/a.txt"))
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        # The move source claim, no occupant in the way.
        result = await storage.move(operations=[ResolvedPair(src=Path("/a.txt"), dest=Path("/c.txt"))])
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        # The overwrite fence on a directory occupant needs a directory
        # source; the refusal fires at the fence, before any purge.
        result = await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/b"))], overwrite=True)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        # The restore claim, through the shared executor.
        result = await storage.restore(path=Path("/t.txt"))
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        await storage.close()

    async def test_delete_recollects_rewrites_after_its_claim(self, tmp_path) -> None:
        # The depth-2 window: a rival lands under a subdirectory after the
        # pre-claim collection; the post-claim re-collection carries it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/sub/keep.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                sub_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d/sub"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=sub_id,
                        path="/d/sub/new.txt",
                        name="new.txt",
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("delete:post-collect", rival):
                result = await delete_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d")],
                    cascade=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            assert result.success is True, result.errors
            stranded = (await session.execute(select(entry.c.path).where(entry.c.path.like("/d/%")))).scalars().all()
            moved = (await session.execute(select(entry.c.path).where(entry.c.name == "new.txt"))).scalar_one()
            await session.rollback()
        # The late row rode the re-collection into trash with its subtree.
        assert stranded == []
        assert moved.startswith("/.vfs/trash/")
        await storage.close()

    async def test_late_arrival_over_the_byte_budget_redrives_the_delete(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/d/sub/keep.txt"), content="x")], parents=True)
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        # Fits as a live path; overflows once the trash prefix lands on /d.
        long_tail = "/d/sub/" + "x" * (MAX_PATH_LENGTH - len("/d/sub/") - 10)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                sub_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d/sub"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=sub_id,
                        path=long_tail,
                        name=long_tail.rsplit("/", 1)[-1],
                        kind="file",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("delete:post-collect", rival), pytest.raises(StaleSnapshot):
                await delete_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.membership_budget,
                    targets=[Path("/d")],
                    cascade=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_overwrite_fence_redrives_when_the_occupant_was_bumped(self, tmp_path) -> None:
        # The silent-destruction window: a rival's committed child bumps
        # the occupant after the emptiness check — the fence must flip.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/a"))
        await storage.mkdir(path=Path("/b"))
        host = storage._host
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})

            async def rival() -> None:
                await session.execute(update(entry).where(entry.c.path == "/b").values(version=entry.c.version + 1))

            with installed("transfer:post-collect", rival), pytest.raises(StaleSnapshot):
                await transfer_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    op="move",
                    operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))],
                    overwrite=True,
                    user_id=None,
                    lock_key=host.topology_key,
                )
            await session.rollback()
        await storage.close()

    async def test_directory_adopting_its_rival_reports_unchanged(self, tmp_path) -> None:
        # Concurrent ancestor minting: the loser adopts the standing
        # directory and the batch converges to success, mkdir -p parity.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            rival_id = str(ULID())

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=rival_id,
                        parent_id=root_id,
                        path="/x",
                        name="x",
                        kind="directory",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("write:before-apply", rival):
                result = await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[
                        Entry(path=Path("/x"), kind="directory"),
                        Entry(path=Path("/x/f.txt"), content="mine"),
                    ],
                    overwrite=False,
                    parents=True,
                    user_id=None,
                )
            stored = (await session.execute(select(entry.c.version).where(entry.c.path == "/x"))).scalar_one()
            await session.rollback()
        assert result.success is True, result.errors
        by_path = {str(o.path): o for o in result.observations}
        assert by_path["/x"].status == "unchanged"
        assert by_path["/x/f.txt"].status == "created"
        # The adopted parent is affirmed: attaching f.txt bumped the
        # rival's row, and the observation equals the stored state.
        assert stored == 2
        assert by_path["/x"].version == 2
        await storage.close()

    async def test_adopting_without_attaching_children_bumps_nothing(self, tmp_path) -> None:
        # An adopted create that changed no membership registers no bump:
        # neither the rival's row nor the grandparent moves — the same
        # versions a sequential exist_ok mkdir would leave.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        host = storage._host
        entry = host.tables.entry
        now = datetime.now(UTC)
        async with host.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True})
            root_before = (await session.execute(select(entry.c.version).where(entry.c.path == "/"))).scalar_one()

            async def rival() -> None:
                root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=root_id,
                        path="/x",
                        name="x",
                        kind="directory",
                        version=1,
                        size_bytes=0,
                        lines=0,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("write:before-apply", rival):
                result = await write_rows(
                    session,
                    host.tables,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    entries=[Entry(path=Path("/x"), kind="directory")],
                    overwrite=False,
                    parents=False,
                    user_id=None,
                )
            root_after = (await session.execute(select(entry.c.version).where(entry.c.path == "/"))).scalar_one()
            adopted = (await session.execute(select(entry.c.version).where(entry.c.path == "/x"))).scalar_one()
            await session.rollback()
        assert result.success is True, result.errors
        assert result.observations[0].status == "unchanged"
        assert result.observations[0].version == 1
        assert adopted == 1
        assert root_after == root_before
        await storage.close()

    async def test_write_refuses_when_the_parent_bump_cannot_be_verified(self, tmp_path, monkeypatch) -> None:
        # The writes-side twin of the topology capability test: a dialect
        # that can prove nothing refuses the whole write — never a child
        # committed under an unaffirmed parent.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.mkdir(path=Path("/d"))).success
        parent_version = (await storage.stat(path=Path("/d"))).observations[0].version
        dialect = storage._host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        monkeypatch.setattr(dialect, "supports_sane_multi_rowcount", False)
        result = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.unsupported]
        monkeypatch.undo()
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        assert (await storage.stat(path=Path("/d"))).observations[0].version == parent_version
        await storage.close()

    async def test_read_retry_exhaustion_classifies_conflict(self, tmp_path, monkeypatch) -> None:
        # Both retry channels exhaust identically on the read path too:
        # a retryable conflict with clean text, never raw driver output.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()

        async def exhausted(fn: object) -> Result:
            raise StaleSnapshot("a retryable engine conflict outlived 3 attempts")

        monkeypatch.setattr(storage._host, "with_retry", exhausted)
        result = await storage.stat(path=Path("/"))
        assert result.success is False
        error = result.errors[0]
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "outlived 3 attempts" in error.message
        await storage.close()

    async def test_first_touch_retry_exhaustion_classifies_conflict(self, tmp_path, monkeypatch) -> None:
        # The third with_retry caller: exhaustion during lazy first touch
        # is the same classified conflict, never a raw internal raise.
        storage = DatabaseStorage(url=_url(tmp_path))

        async def exhausted(fn: object) -> Result:
            raise StaleSnapshot("a retryable engine conflict outlived 3 attempts")

        monkeypatch.setattr(storage._host, "with_retry", exhausted)
        result = await storage.stat(path=Path("/"))
        assert result.success is False
        error = result.errors[0]
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "First touch kept losing to concurrent changes" in error.message
        assert "outlived 3 attempts" in error.message
        monkeypatch.undo()
        recovered = await storage.stat(path=Path("/"))
        assert recovered.success is True  # exhaustion never wedged readiness
        await storage.close()

    def test_statement_budget_measures_fixed_binds_and_caps_width(self) -> None:
        # The bump statement carries one fixed bind (the SQL-side
        # increment); the helper measures it off the compiled statement
        # and keeps the reserve clear of the engine cap.
        tables = build_vfs_tables(table_name="vfs")
        entry = tables.entry
        pair = ("A" * 26, "/a")
        dialect = mssql.dialect()
        rows = statement_budget(
            lambda probe: _bump_values_stmt(entry, probe),
            pair,
            dialect,
            parameter_budget=2_099,
            row_width=2,
        )
        assert rows == (2_099 - 1 - 8) // 2
        assert rows * 2 + 1 <= 2_099 - 8
        # An even budget distinguishes the fixed-bind subtraction the
        # odd 2,099 pin arithmetically absorbs (1,045 vs 1,046).
        even = statement_budget(
            lambda probe: _bump_values_stmt(entry, probe),
            pair,
            dialect,
            parameter_budget=2_100,
            row_width=2,
        )
        assert even == (2_100 - 1 - 8) // 2
        capped = statement_budget(
            lambda probe: _bump_values_stmt(entry, probe),
            pair,
            dialect,
            parameter_budget=2_099,
            row_width=2,
            row_cap=100,
        )
        assert capped == 100
        # An understated width is drift: it must fail loudly at the
        # helper, never at row N of a production batch.
        with pytest.raises(AssertionError, match="row width"):
            statement_budget(
                lambda probe: _bump_values_stmt(entry, probe),
                pair,
                dialect,
                parameter_budget=2_099,
                row_width=1,
            )

    def test_statement_budget_charges_sparse_rows_at_the_declared_width(self) -> None:
        # NULL cells compile inline, so a sparse probe row measures a
        # smaller delta; the chunk is charged at the declared ceiling
        # regardless, or a mixed batch overflows the engine cap mid-run.
        tables = build_vfs_tables(table_name="vfs")
        entry = tables.entry
        dialect = mssql.dialect()
        width = len(_CLOBBER_COLUMNS) + 4
        now = datetime.now(UTC)
        full = (str(ULID()), 1, 2, "/full.txt", "file", "h" * 64, "text/plain", "txt", 1, 4, "O" * 26, now)
        sparse = (str(ULID()), 1, 2, "/sparse", "file", None, None, None, 0, 0, None, now)

        def budget(row: tuple[object, ...]) -> int:
            return statement_budget(
                lambda probe: _values_update_stmt(entry, probe, guard=True),
                row,
                dialect,
                parameter_budget=2_099,
                row_width=width,
            )

        # The premise: the sparse probe really undershoots the ceiling.
        one = len(_values_update_stmt(entry, [sparse], guard=True).compile(dialect=dialect).bind_names)
        two = len(_values_update_stmt(entry, [sparse, sparse], guard=True).compile(dialect=dialect).bind_names)
        assert two - one < width
        assert budget(sparse) == budget(full)

    async def test_upsert_escape_that_classifies_keeps_the_chunk_loop_going(self) -> None:
        # An IntegrityError escaping ON CONFLICT re-drives row-wise; when
        # the probe classifies (a ghost refusal, not a vanished occupant)
        # the layer keeps its errors and moves to the next chunk.
        tables = build_vfs_tables(table_name="vfs")
        staged = StagedEntry(
            path=Path("/d/late.txt"),
            parent=Path("/d"),
            kind="file",
            persistence="insert",
            entry_id=str(ULID()),
            content="mine",
        )
        rows = [_entry_values(staged, "P" * 26, None, datetime.now(UTC))]
        ghost = SimpleNamespace(entry_id="G" * 26, kind="file", path="/elsewhere/late.txt", version=1)

        class _Nested:
            async def __aenter__(self) -> _Nested:
                return self

            async def __aexit__(self, *exc: object) -> bool:
                return False

        class _ProbeResult:
            def one_or_none(self) -> SimpleNamespace:
                return ghost

        class _EscapeSession:
            def begin_nested(self) -> _Nested:
                return _Nested()

            async def execute(self, stmt: Any, params: Any = None) -> _ProbeResult:
                if isinstance(stmt, Select):
                    return _ProbeResult()
                raise IntegrityError("stmt", None, Exception("duplicate"))

        errors = await _upsert_layer(
            cast("AsyncSession", _EscapeSession()), tables.entry, SQLITE, [staged], rows, 50, overwrite=True
        )
        [error] = errors
        assert error.kind == VFSErrorKind.conflict
        assert error.retryable is True
        assert "may not adopt" in error.message
        assert error.data == {"target": "/d/late.txt"}  # distinct refusals stay distinct facts
        assert staged.persistence == "insert"  # the ghost was never absorbed
