"""The trash arm of DatabaseStorage — buckets, restore, sweep, purge.

Delete reparents into an hourly bucket under ``/.vfs/trash``, which is an
ordinary subtree: restore returns a row to its recorded parent, sweep
expires aged buckets and purges family rows, and the chain holder refuses
deletion because sweep is the lawful reclamation. Transfer behavior and
the bucket's own version bumps ride along, since both are visible only
from the trash side.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, insert, select, update
from ulid import ULID

from tests.support.database_helpers import _url
from vfs.models import Entry, Observation
from vfs.models.rows import ULID_LENGTH, build_vfs_tables
from vfs.paths import MAX_PATH_LENGTH, Path, byte_length
from vfs.results import Severity, VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database.dialects import membership_budget, op_execution_options
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.seams import clear, installed
from vfs.storage.backends.database.topology import _purge_subtree, _TrashChain

# ---------------------------------------------------------------------------
# Delete — the trash arm beyond the conformance rows
# ---------------------------------------------------------------------------


class TestDeleteTrash:
    """The default arm reparents into an hourly bucket; trash is normal fs."""

    async def test_delete_reparents_into_the_hourly_bucket(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="body")])
        deleted = await storage.delete(path=Path("/a.txt"))
        assert deleted.success
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        assert len(buckets.observations) == 1
        bucket = buckets.observations[0]
        listing = await storage.ls(path=bucket.path)
        assert len(listing.observations) == 1
        trashed = listing.observations[0]
        # The in-bucket name is `<ULID>-<original name>`: unique and
        # time-sorted by prefix, self-describing by suffix.
        name = Path(trashed.path).name
        assert len(name) == ULID_LENGTH + len("-a.txt")
        assert name.endswith("-a.txt")
        # The delete result reported exactly this address.
        assert deleted.observations[0].trash_path == trashed.path
        assert "trash_path" in deleted.observations[0].populated
        read = await storage.read(path=trashed.path)
        assert read.observations[0].content == "body"
        await storage.close()

    async def test_trashed_row_records_its_original_site(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/docs"))
        await storage.write(entries=[Entry(path=Path("/docs/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/docs/a.txt"))).success
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(entry).where(entry.c.original_name == "a.txt"))).mappings().one()
        assert row["name"] == f"{row['entry_id']}-a.txt"
        assert row["deleted_at"] is not None
        assert row["original_parent_id"] is not None
        parent = await storage.stat(path=Path("/docs"))
        assert parent.success is True
        await storage.close()

    async def test_descendant_paths_rewrite_under_the_trash_prefix(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/proj/sub"), parents=True)
        await storage.write(entries=[Entry(path=Path("/proj/sub/f.txt"), content="deep")])
        assert (await storage.delete(path=Path("/proj"))).success
        assert (await storage.stat(path=Path("/proj/sub/f.txt"))).success is False
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        bucket_listing = await storage.ls(path=buckets.observations[0].path)
        trashed_root = bucket_listing.observations[0].path
        deep = await storage.read(path=Path(f"{trashed_root}/sub/f.txt"))
        assert deep.observations[0].content == "deep"
        await storage.close()

    async def test_same_named_deletes_never_collide_in_the_bucket(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/a"))
        await storage.mkdir(path=Path("/b"))
        await storage.write(
            entries=[Entry(path=Path("/a/f.txt"), content="1"), Entry(path=Path("/b/f.txt"), content="2")]
        )
        targets = [Observation(path=Path("/a/f.txt")), Observation(path=Path("/b/f.txt"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        listing = await storage.ls(path=buckets.observations[0].path)
        assert len(listing.observations) == 2
        # Both keep the readable suffix; the ULID prefix tells them apart.
        names = [Path(o.path).name for o in listing.observations]
        assert all(n.endswith("-f.txt") for n in names)
        assert len(set(names)) == 2
        await storage.close()

    async def test_delete_batch_observations_all_carry_trash_paths(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(
            entries=[Entry(path=Path("/a.txt"), content="x"), Entry(path=Path("/d/b.txt"), content="y")]
        )
        targets = [Observation(path=Path("/a.txt")), Observation(path=Path("/d"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        assert all(o.trash_path is not None for o in result.observations)
        assert all("trash_path" in o.populated for o in result.observations)
        await storage.close()

    async def test_covered_targets_derive_their_trash_address(self, tmp_path) -> None:
        # The covered child is observed before its covering root is
        # processed; its trash address is derived, not looked up.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/proj/sub"), parents=True)
        await storage.write(entries=[Entry(path=Path("/proj/sub/f.txt"), content="deep")])
        targets = [Observation(path=Path("/proj/sub/f.txt")), Observation(path=Path("/proj"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        by_path = {str(o.path): o for o in result.observations}
        root_trash = by_path["/proj"].trash_path
        assert root_trash is not None
        covered_trash = by_path["/proj/sub/f.txt"].trash_path
        assert covered_trash == Path(f"{root_trash}/sub/f.txt")
        read = await storage.read(path=covered_trash)
        assert read.observations[0].content == "deep"
        await storage.close()

    async def test_a_repeated_target_reports_the_same_trash_address(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        targets = [Observation(path=Path("/a.txt")), Observation(path=Path("/a.txt"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        first, second = result.observations
        assert first.trash_path is not None
        assert second.trash_path == first.trash_path
        await storage.close()

    async def test_a_batch_touching_the_chain_holder_refuses_whole(self, tmp_path) -> None:
        # /.vfs holds the bucket chain: its refusal fails the batch, so
        # the innocent sibling target survives live — nothing commits.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        assert (await storage.delete(path=Path("/x.txt"))).success
        await storage.write(entries=[Entry(path=Path("/y.txt"), content="y")])
        targets = [Observation(path=Path("/y.txt")), Observation(path=Path("/.vfs"))]
        result = await storage.delete(observations=targets)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.invalid]
        assert result.errors[0].message == "Cannot delete /.vfs: contains the active trash chain — sweep reclaims trash"
        assert (await storage.stat(path=Path("/y.txt"))).success is True
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True
        await storage.close()

    async def test_a_covered_chain_target_adds_no_second_error(self, tmp_path) -> None:
        # /.vfs/trash rides inside /.vfs's cascade: the covering holder
        # refuses exactly once; the covered target contributes no error.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        trashed = (await storage.delete(path=Path("/x.txt"))).observations[0].trash_path
        assert trashed is not None
        targets = [Observation(path=Path("/.vfs/trash")), Observation(path=Path("/.vfs"))]
        result = await storage.delete(observations=targets)
        assert result.success is False
        assert [e.kind for e in result.errors] == [VFSErrorKind.invalid]
        assert result.errors[0].message == "Cannot delete /.vfs: contains the active trash chain — sweep reclaims trash"
        # The refused batch never commits: the previously-trashed row survives.
        assert (await storage.stat(path=trashed)).success is True
        await storage.close()

    async def test_the_trash_name_truncates_at_the_tail_never_the_ulid(self, tmp_path) -> None:
        # 26-byte ULID + hyphen leaves 228 bytes of name tail; the
        # 4-byte emoji straddles the cut and must drop whole.
        storage = DatabaseStorage(url=_url(tmp_path))
        original = "x" * 227 + "🚀"
        await storage.write(entries=[Entry(path=Path(f"/{original}"), content="x")])
        result = await storage.delete(path=Path(f"/{original}"))
        assert result.success is True
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        name = trash_path.name
        assert byte_length(name) == ULID_LENGTH + 1 + 227
        assert "🚀" not in name
        # The row is addressable at the reported path with metadata whole.
        assert (await storage.stat(path=trash_path)).success is True
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            found = (await session.execute(select(entry).where(entry.c.path == str(trash_path)))).mappings().one()
        assert found["original_name"] == original
        await storage.close()

    async def test_a_maximal_name_still_fits_the_path_budget(self, tmp_path) -> None:
        # Worst case root trash path is the bucket prefix plus a 255-byte
        # name — ~281 bytes, comfortably inside the 1,024-byte budget.
        storage = DatabaseStorage(url=_url(tmp_path))
        original = "n" * 255
        await storage.write(entries=[Entry(path=Path(f"/{original}"), content="x")])
        result = await storage.delete(path=Path(f"/{original}"))
        assert result.success is True
        trash_path = result.observations[0].trash_path
        assert trash_path is not None
        assert byte_length(str(trash_path)) <= MAX_PATH_LENGTH
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_a_file_squatting_on_the_trash_chain_refuses_wrong_kind(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/.vfs/trash"), content="squatter")], parents=True)
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        result = await storage.delete(path=Path("/x.txt"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/.vfs/trash"
        assert (result.errors[0].data or {}).get("target") == "/x.txt"
        # The batch never commits: the target survives.
        assert (await storage.stat(path=Path("/x.txt"))).success is True
        await storage.close()

    async def test_a_trashed_row_can_be_swept_from_the_trash_side(self, tmp_path) -> None:
        # Per-row reclamation re-homed from the retired permanent flag:
        # sweep of the exact trash address purges just that row.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/gone.txt"), content="x")])
        assert (await storage.delete(path=Path("/gone.txt"))).success
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        listing = await storage.ls(path=buckets.observations[0].path)
        trash_path = listing.observations[0].path
        assert (await storage.sweep(path=Path(trash_path))).success
        assert (await storage.stat(path=Path(trash_path))).success is False
        assert (await storage.stat(path=buckets.observations[0].path)).success is True
        await storage.close()

    async def test_the_bucket_mint_survives_a_rival_write_racing_the_chain(self, tmp_path) -> None:
        # The designed benign race: a rival mints the chain link first;
        # the topology mint loses arbitration and adopts the rival's row.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        entry = storage._host.tables.entry
        host = storage._host
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))
            root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
            chain = _TrashChain(entry, root_id=root_id, user_id=None, now=datetime.now(UTC))
            first = await chain.ensure(session, Path("/x.txt"))
            assert isinstance(first, str)
            # A fresh chain re-selects the minted links instead of re-minting.
            rival = _TrashChain(entry, root_id=root_id, user_id=None, now=datetime.now(UTC))
            second = await rival.ensure(session, Path("/x.txt"))
            assert second == first
            # A direct mint against an occupied link takes the
            # IntegrityError arm and adopts the winner's row.
            adopted = await rival._mint(session, "/.vfs", root_id)
            assert adopted.kind == "directory"
            await session.rollback()
        await storage.close()


class TestRestore:
    """Restore arms beyond the conformance rows — identity, corruption, budgets."""

    async def test_restore_clears_the_restore_columns(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        assert (await storage.restore(path=deleted.observations[0].trash_path)).success is True
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(entry).where(entry.c.path == "/a.txt"))).mappings().one()
        assert row["original_parent_id"] is None
        assert row["original_name"] is None
        assert row["deleted_at"] is None
        assert row["name"] == "a.txt"
        await storage.close()

    async def test_restore_follows_a_moved_parent(self, tmp_path) -> None:
        # The trash row holds the parent's identity, not its old path: the
        # row restores to wherever that parent lives now.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        trash_path = deleted.observations[0].trash_path
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))])).success is True
        by_old_site = await storage.restore(path=Path("/d/f.txt"))
        assert by_old_site.success is False
        assert by_old_site.errors[0].kind == VFSErrorKind.not_found
        restored = await storage.restore(path=trash_path)
        assert restored.success is True
        assert restored.observations[0].path == "/e/f.txt"
        assert (await storage.read(path=Path("/e/f.txt"))).observations[0].content == "x"
        await storage.close()

    async def test_restore_refuses_when_the_parent_is_itself_in_trash(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        assert (await storage.delete(path=Path("/d"))).success is True
        result = await storage.restore(path=deleted.observations[0].trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert "restore" in result.errors[0].message
        await storage.close()

    async def test_restore_returns_a_row_to_the_live_hour_bucket(self, tmp_path) -> None:
        # The bucket sits under /.vfs/trash but is live, never trashed:
        # a trash row deleted in place restores back into it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/g.txt"), content="payload")])
        first = (await storage.delete(path=Path("/g.txt"))).observations[0].trash_path
        assert first is not None
        second = (await storage.delete(path=first)).observations[0].trash_path
        assert second is not None
        result = await storage.restore(path=second)
        assert result.success is True
        assert result.observations[0].path == str(first)
        assert (await storage.read(path=first)).observations[0].content == "payload"
        await storage.close()

    async def test_restore_returns_a_row_to_a_live_squatter_under_trash(self, tmp_path) -> None:
        # Trash is an ordinary subtree: a live user directory squatting
        # inside it is a lawful original site, not a trashed parent.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/.vfs/trash/mystuff"), parents=True)
        await storage.write(entries=[Entry(path=Path("/.vfs/trash/mystuff/a.txt"), content="squat")])
        deleted = await storage.delete(path=Path("/.vfs/trash/mystuff/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        result = await storage.restore(path=trash_path)
        assert result.success is True
        assert (await storage.read(path=Path("/.vfs/trash/mystuff/a.txt"))).observations[0].content == "squat"
        await storage.close()

    async def test_restore_refuses_a_corrupted_non_directory_parent(self, tmp_path) -> None:
        # Foreign-state tolerance: a parent row whose kind was mangled
        # out from under the trash contract refuses, never mis-restores.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        deleted = await storage.delete(path=Path("/d/f.txt"))
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            await session.execute(update(entry).where(entry.c.path == "/d").values(kind="file"))
            await session.commit()
        result = await storage.restore(path=deleted.observations[0].trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        await storage.close()

    async def test_restore_destination_overflow_refuses_unaddressable(self, tmp_path) -> None:
        # The parent moved deeper since the delete: the computed
        # destination exceeds the byte budget and the row stays in trash.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        name = "n" * 255
        await storage.write(entries=[Entry(path=Path(f"/d/{name}"), content="x")])
        deleted = await storage.delete(path=Path(f"/d/{name}"))
        trash_path = deleted.observations[0].trash_path
        deep = Path("/" + "a" * 255 + "/" + "b" * 255 + "/" + "c" * 255)
        await storage.mkdir(path=deep, parents=True)
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path(f"{deep}/d"))])).success is True
        result = await storage.restore(path=trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_restore_descendant_overflow_refuses_unaddressable(self, tmp_path) -> None:
        # The restored root fits; a descendant rewrite would not.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d/s"), parents=True)
        await storage.write(entries=[Entry(path=Path("/d/s/" + "f" * 255), content="x")])
        deleted = await storage.delete(path=Path("/d/s"))
        trash_path = deleted.observations[0].trash_path
        deep = Path("/" + "a" * 255 + "/" + "b" * 255 + "/" + "c" * 255)
        await storage.mkdir(path=deep, parents=True)
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path(f"{deep}/d"))])).success is True
        result = await storage.restore(path=trash_path)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_restore_onto_a_wrong_kind_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        await storage.delete(path=Path("/a.txt"))
        await storage.mkdir(path=Path("/a.txt"))
        result = await storage.restore(path=Path("/a.txt"), overwrite=True)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        await storage.close()

    async def test_restore_onto_a_nonempty_directory_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.delete(path=Path("/d"))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/new.txt"), content="x")])
        result = await storage.restore(path=Path("/d"), overwrite=True)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_empty
        await storage.close()

    async def test_restore_overwrites_an_empty_directory_occupant(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="kept")])
        await storage.delete(path=Path("/d"))
        await storage.mkdir(path=Path("/d"))
        result = await storage.restore(path=Path("/d"), overwrite=True)
        assert result.success is True
        assert result.observations[0].status == "updated"
        assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "kept"
        await storage.close()

    async def test_restore_batch_error_fails_the_batch_whole(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        targets = [Observation(path=trash_path), Observation(path=Path("/ghost.txt"))]
        result = await storage.restore(observations=targets)
        assert result.success is False
        # The refused batch never commits: the good target stays in trash.
        assert (await storage.stat(path=trash_path)).success is True
        assert (await storage.stat(path=Path("/a.txt"))).success is False
        await storage.close()


class TestSweep:
    """Sweep arms beyond the conformance rows — retention boundary, config."""

    async def test_trash_days_zero_expires_only_fully_aged_hours(self, tmp_path) -> None:
        # Retention is a floor: with trash_days=0 the cutoff is now, and
        # the current hour has not fully elapsed — its bucket survives
        # while a two-hour-old bucket drops.
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        trash_path = deleted.observations[0].trash_path
        assert trash_path is not None
        old = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d-%H")
        await storage.mkdir(path=Path(f"/.vfs/trash/{old}"))
        result = await storage.sweep(path=Path("/.vfs/trash"))
        if str(trash_path.parent_dir) != f"/.vfs/trash/{datetime.now(UTC).strftime('%Y-%m-%d-%H')}":
            pytest.skip("hour boundary crossed between delete and sweep")
        assert result.success is True
        assert [str(o.path) for o in result.observations] == [f"/.vfs/trash/{old}"]
        assert (await storage.stat(path=trash_path)).success is True
        await storage.close()

    async def test_negative_trash_days_refuses_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="trash_days"):
            DatabaseStorage(url=_url(tmp_path), trash_days=-1)

    async def test_sweep_surfaces_a_trash_root_squatter(self, tmp_path) -> None:
        # A user file sitting at /.vfs/trash itself is foreign state: the
        # sweep touches nothing and says so, without failing.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/.vfs/trash"), content="squat")], parents=True)
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert result.observations == []
        assert result.errors[0].severity == Severity.warning
        assert result.errors[0].path == "/.vfs/trash"
        assert (await storage.read(path=Path("/.vfs/trash"))).observations[0].content == "squat"
        await storage.close()

    async def test_sweep_purge_miss_classifies_through_the_descent_ladder(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deep = await storage.sweep(path=Path("/ghost/deep"))
        assert deep.success is False
        assert deep.errors[0].kind == VFSErrorKind.not_found
        assert deep.errors[0].path == "/ghost"
        wrong = await storage.sweep(path=Path("/a.txt/child"))
        assert wrong.success is False
        assert wrong.errors[0].kind == VFSErrorKind.wrong_kind
        assert wrong.errors[0].path == "/a.txt"
        await storage.close()

    async def test_sweep_purge_bumps_the_parent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        before = (await storage.stat(path=Path("/d"))).observations[0].version
        assert before is not None
        assert (await storage.sweep(path=Path("/d/f.txt"))).success
        after = (await storage.stat(path=Path("/d"))).observations[0].version
        assert after == before + 1
        await storage.close()


class TestTransferBehavior:
    """Transfer arms beyond the conformance rows — restore, chains, fallbacks."""

    async def test_move_out_of_trash_is_the_restore_gesture(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/doc.txt"), content="body")])
        assert (await storage.delete(path=Path("/doc.txt"))).success
        buckets = await storage.ls(path=Path("/.vfs/trash"))
        listing = await storage.ls(path=buckets.observations[0].path)
        trash_path = Path(listing.observations[0].path)
        restored = await storage.move(operations=[ResolvedPair(src=trash_path, dest=Path("/doc.txt"))])
        assert restored.success is True
        assert (await storage.read(path=Path("/doc.txt"))).observations[0].content == "body"
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (await session.execute(select(entry).where(entry.c.path == "/doc.txt"))).mappings().one()
        # A live row carries no trash metadata, and its name is its own again.
        assert row["deleted_at"] is None
        assert row["original_parent_id"] is None
        assert row["original_name"] is None
        assert row["name"] == "doc.txt"
        await storage.close()

    async def test_chained_moves_fall_back_to_the_pair_time_observation(self, tmp_path) -> None:
        # Pair 2 moves pair 1's destination away: the re-read finds no row
        # at /b, so pair 1's observation falls back to its captured values.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.move(
            operations=[
                ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt")),
                ResolvedPair(src=Path("/b.txt"), dest=Path("/c.txt")),
            ]
        )
        assert result.success is True
        first, second = result.observations
        assert str(first.path) == "/b.txt" and first.status == "created"
        assert str(second.path) == "/c.txt" and second.status == "created"
        assert (await storage.stat(path=Path("/b.txt"))).success is False
        assert (await storage.read(path=Path("/c.txt"))).observations[0].content == "x"
        await storage.close()

    async def test_the_transfer_seam_fires_after_the_snapshot(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/x.txt"), content="x")])
        fired: list[str] = []

        async def handler() -> None:
            fired.append("transfer")

        with installed("transfer:post-snapshot", handler):
            assert (await storage.copy(operations=[ResolvedPair(src=Path("/x.txt"), dest=Path("/y.txt"))])).success
        assert fired == ["transfer"]
        await storage.close()


class TestSweepPurge:
    """The purge arm sweeps the subtree's rows across every family table."""

    async def test_sweep_purges_family_rows(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/proj"))
        await storage.write(entries=[Entry(path=Path("/proj/f.txt"), content="x")])
        tables = storage._host.tables
        entry = tables.entry
        async with storage._host.session_factory() as session:
            target_id = (
                await session.execute(select(entry.c.entry_id).where(entry.c.path == "/proj/f.txt"))
            ).scalar_one()
            await session.execute(
                insert(tables.versions).values(
                    entry_id=target_id, version_number=1, is_snapshot=True, content_hash="h", content="x"
                )
            )
            await session.execute(
                insert(tables.chunks).values(entry_id=target_id, chunk_index=0, line_start=1, line_end=1, content="x")
            )
            await session.execute(
                insert(tables.edges).values(source_id=target_id, target_id=str(ULID()), edge_type="ref")
            )
            await session.execute(
                insert(tables.edges).values(source_id=str(ULID()), target_id=target_id, edge_type="ref")
            )
            await session.commit()
        assert (await storage.sweep(path=Path("/proj"))).success
        async with storage._host.session_factory() as session:
            for table in (tables.entry, tables.content, tables.versions, tables.chunks):
                remaining = (await session.execute(select(table).where(table.c.entry_id == target_id))).all()
                assert remaining == []
            edges = (
                await session.execute(
                    select(tables.edges).where(
                        (tables.edges.c.source_id == target_id) | (tables.edges.c.target_id == target_id)
                    )
                )
            ).all()
            assert edges == []
        assert (await storage.stat(path=Path("/proj"))).success is False
        # Nothing landed in trash: the purge never mints the bucket chain.
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is False
        await storage.close()


# ---------------------------------------------------------------------------
# Trash-machinery guard, byte-budget refusal, purge hardening
# ---------------------------------------------------------------------------


async def _assert_no_cycles_or_orphans(storage: DatabaseStorage) -> None:
    """Raw invariant sweep: parents exist, no cycles, path caches agree."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        rows = (await session.execute(select(entry.c.entry_id, entry.c.parent_id, entry.c.path, entry.c.name))).all()
    by_id = {row.entry_id: row for row in rows}
    for row in rows:
        if row.path == "/":
            continue
        assert row.parent_id != row.entry_id, f"self-parented row: {row.path}"
        parent = by_id.get(row.parent_id)
        assert parent is not None, f"orphan row: {row.path}"
        prefix = "" if parent.path == "/" else parent.path
        assert row.path == f"{prefix}/{row.name}", f"torn path cache: {row.path}"
        walked: set[str] = set()
        current = row
        while current.path != "/":
            assert current.entry_id not in walked, f"parent cycle through {row.path}"
            walked.add(current.entry_id)
            current = by_id[current.parent_id]


class TestTrashChainRefusal:
    """Deleting the active trash machinery refuses; sweep reclaims it."""

    async def test_deleting_the_trash_root_refuses_and_purges_nothing(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deleted = await storage.delete(path=Path("/a.txt"))
        assert deleted.success
        result = await storage.delete(path=Path("/.vfs/trash"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        expected = "Cannot delete /.vfs/trash: contains the active trash chain — sweep reclaims trash"
        assert result.errors[0].message == expected
        assert (await storage.stat(path=deleted.observations[0].trash_path)).success is True
        await _assert_no_cycles_or_orphans(storage)
        await storage.close()

    async def test_sweeping_the_chain_holder_purges_and_the_chain_reminting_is_clean(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        assert (await storage.sweep(path=Path("/.vfs"))).success is True
        assert (await storage.stat(path=Path("/.vfs"))).success is False
        await _assert_no_cycles_or_orphans(storage)
        # The next delete re-mints a fresh chain cleanly.
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.delete(path=Path("/b.txt"))).success
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True
        await _assert_no_cycles_or_orphans(storage)
        await storage.close()

    async def test_sweeping_the_current_bucket_reclaims_it_without_cycles(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        bucket = (await storage.ls(path=Path("/.vfs/trash"))).observations[0].path
        assert (await storage.sweep(path=Path(bucket))).success is True
        assert (await storage.stat(path=Path(bucket))).success is False
        # The trash root survives; only the bucket subtree was purged.
        assert (await storage.stat(path=Path("/.vfs/trash"))).success is True
        await _assert_no_cycles_or_orphans(storage)
        await storage.close()

    def test_chain_inside_matches_ancestors_and_the_bucket_only(self) -> None:
        tables = build_vfs_tables(table_name="vfs")
        chain = _TrashChain(tables.entry, root_id="r", user_id=None, now=datetime.now(UTC))
        assert chain.chain_inside(Path("/.vfs")) is True
        assert chain.chain_inside(Path("/.vfs/trash")) is True
        assert chain.chain_inside(Path(chain.bucket_path)) is True
        # A prefix that is not an ancestor, and a bucket from another hour.
        assert chain.chain_inside(Path("/.vfs/tra")) is False
        assert chain.chain_inside(Path("/.vfs/trash/1999-01-01-00")) is False
        assert chain.chain_inside(Path("/docs")) is False

    async def test_trash_delete_refuses_when_a_rewrite_would_overflow(self, tmp_path) -> None:
        # The trash prefix for /d is 54 bytes (25-byte bucket + "/" +
        # 28-byte <ULID>-d), so a descendant fits iff its path ≤ 972.
        storage = DatabaseStorage(url=_url(tmp_path))
        segment = "s" * 255
        fits = Path(f"/d/{segment}/{segment}/{segment}/" + "f" * 201)
        over = Path(f"/e/{segment}/{segment}/{segment}/" + "f" * 202)
        await storage.write(entries=[Entry(path=fits, content="ok")], parents=True)
        assert (await storage.delete(path=Path("/d"))).success is True
        await storage.write(entries=[Entry(path=over, content="deep")], parents=True)
        result = await storage.delete(path=Path("/e"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unaddressable
        assert result.errors[0].path == "/e"
        # The refused batch never commits: the tree survives whole.
        assert (await storage.stat(path=over)).success is True
        # A covered child of the refusing root derives no address either:
        # the over-budget derivation yields None instead of raising.
        both = await storage.delete(observations=[Observation(path=over), Observation(path=Path("/e"))])
        assert both.success is False
        assert any(e.kind == VFSErrorKind.unaddressable for e in both.errors)
        # The developer-plane sweep stays the lawful removal for such trees.
        assert (await storage.sweep(path=Path("/e"))).success is True
        await storage.close()


class TestPurgeHardening:
    """The purge re-collects until empty and never doubles a chunk's binds."""

    async def test_purge_recollects_rows_committed_after_the_first_collection(self, tmp_path) -> None:
        # The stale-id-list orphan window: a row appearing between the
        # collect and the deletes must be swept by the second pass.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/base.txt"), content="x")])
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))
            parent_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()

            async def straggler() -> None:
                clear("purge:post-collect")
                now = datetime.now(UTC)
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=parent_id,
                        path="/d/straggler.txt",
                        name="straggler.txt",
                        kind="file",
                        version=1,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("purge:post-collect", straggler):
                await _purge_subtree(session, tables, 1_000, "/d")
            subtree = (entry.c.path == "/d") | entry.c.path.like("/d/%")
            remaining = (await session.execute(select(entry.c.path).where(subtree))).all()
            assert remaining == []
            await session.rollback()
        await storage.close()

    async def test_purge_statements_never_double_the_membership_chunk(self, tmp_path, monkeypatch) -> None:
        # Tiny budget → membership 16. Every purge DELETE must carry at
        # most one chunk of binds — the edges statement used to OR two
        # lists together, doubling past the tightest engine's cap.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        paths = [Path(f"/d/f{i:02}.txt") for i in range(40)]
        written = await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)
        assert written.success is True, written.errors
        tables = storage._host.tables
        entry = tables.entry
        async with storage._host.session_factory() as session:
            found = await session.execute(select(entry.c.entry_id).where(entry.c.path.like("/d/%")))
            ids = [row.entry_id for row in found]
            for eid in ids[:20]:
                await session.execute(
                    insert(tables.edges).values(source_id=eid, target_id=str(ULID()), edge_type="ref")
                )
                await session.execute(
                    insert(tables.edges).values(source_id=str(ULID()), target_id=eid, edge_type="ref")
                )
            await session.commit()
        counts: list[int] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement.lstrip().upper().startswith("DELETE"):
                counts.append(statement.count("?"))

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.sweep(path=Path("/d"))).success
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        budget = membership_budget(storage._host.profile, 48)
        assert counts and max(counts) <= budget
        # 41 rows at chunk size 16 → three chunks through all six deletes.
        assert len(counts) >= 18
        await storage.close()


class TestTopologyOptionsStamping:
    """Every topology verb stamps the topology options, never the op pin."""

    async def test_topology_verbs_stamp_the_topology_execution_options(self, tmp_path, monkeypatch) -> None:
        calls: list[object] = []
        real = backend_module.topology_execution_options

        def spy(profile):
            calls.append(profile)
            return real(profile)

        monkeypatch.setattr(backend_module, "topology_execution_options", spy)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.move(operations=[ResolvedPair(src=Path("/b.txt"), dest=Path("/c.txt"))])).success
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/c.txt"), dest=Path("/d.txt"))])).success
        assert calls == [storage._host.profile] * 3
        await storage.close()


class TestTrashBucketBump:
    """The bucket is a directory like any other: gaining a member bumps it."""

    async def test_each_delete_bumps_the_bucket_it_lands_in(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x"), Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        assert (await storage.delete(path=Path("/b.txt"))).success
        buckets = (await storage.ls(path=Path("/.vfs/trash"))).observations
        if len(buckets) != 1:
            pytest.skip("hour boundary crossed between deletes")
        bucket = (await storage.stat(path=buckets[0].path)).observations[0]
        # Minted at 1, bumped once per member gained.
        assert bucket.version == 3
        await storage.close()
