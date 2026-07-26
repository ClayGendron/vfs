"""Write-vs-topology races against real database servers — the race pin family.

Two legs. **Seam-staged one-shots**: each closed window is re-staged
through the declared seams with genuine second transactions — the
forward ordering (a write creating under a concurrently relocated or
destroyed parent, all four carriers), the reverse ordering (a rival
write committing between a topology verb's descendant collection and
its claim), the edit/overwrite false success, the ghost name-squat, the
destination-address race, and the purge residual window. **Natural
timing**: a two-instance storm with no seams, seeded jitter, and the
campaign's integrity audit after every round — torn path caches and
orphan content rows fail the leg.

Every test skips locally: the ``VFS_TEST_<ENGINE>_URL`` variables select
the legs, served by ``docker/compose.test.yml`` (the db_test cycle).
Storm scale is CI-sized by default and env-tunable — the campaign-scale
run is ``VFS_RACE_STORM_ROUNDS=30 VFS_RACE_STORM_N=2000``; defaults
below that are a deliberate, documented cap, not full campaign coverage.
"""

from __future__ import annotations

import asyncio
import os
import random
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine
from ulid import ULID

from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, seams

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from vfs.results import Result

ENGINE_LEGS = [
    pytest.param("VFS_TEST_POSTGRES_URL", marks=pytest.mark.postgres, id="postgres"),
    pytest.param("VFS_TEST_MYSQL_URL", marks=pytest.mark.mysql, id="mysql"),
    pytest.param("VFS_TEST_MSSQL_URL", marks=pytest.mark.mssql, id="mssql"),
    pytest.param("VFS_TEST_ORACLE_URL", marks=pytest.mark.oracle, id="oracle"),
]

# Kinds that may lawfully surface from a lost race; anything else — above
# all ``unavailable`` with raw driver text — is a classification defect.
_RACE_KINDS = frozenset({VFSErrorKind.not_found, VFSErrorKind.conflict, VFSErrorKind.exists, VFSErrorKind.invalid})


@asynccontextmanager
async def _server_storage(env_var: str) -> AsyncIterator[DatabaseStorage]:
    """A fresh backend on the server named by *env_var*, tables reset."""
    url = os.environ.get(env_var)
    if url is None:
        pytest.skip(f"{env_var} is not set")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(build_vfs_tables(table_name="vfs").metadata.drop_all)
    finally:
        await engine.dispose()
    storage = DatabaseStorage(url=url)
    try:
        yield storage
    finally:
        await storage.close()


async def _audit(storage: DatabaseStorage) -> None:
    """The campaign's integrity audit: path caches coherent, no orphan bodies."""
    tables = storage._host.tables
    entry = tables.entry
    async with storage._host.session_factory() as session:
        found = await session.execute(select(entry.c.entry_id, entry.c.parent_id, entry.c.path, entry.c.name))
        rows = found.all()
        bodies = {row.entry_id for row in await session.execute(select(tables.content.c.entry_id))}
    by_id = {row.entry_id: row for row in rows}
    for row in rows:
        if row.parent_id is None:
            assert row.path == "/", f"rootless row: {row.path}"
            continue
        parent = by_id.get(row.parent_id)
        assert parent is not None, f"dangling parent_id: {row.path}"
        prefix = "" if parent.path == "/" else parent.path
        assert row.path == f"{prefix}/{row.name}", f"torn path cache: {row.path} under {parent.path}"
    leaked = bodies - set(by_id)
    assert not leaked, f"orphan content rows: {leaked}"


def _self_clearing(name: str, storage_call):
    """A seam handler that uninstalls itself, then drives the rival verb."""

    results: list[Result] = []

    async def handler() -> None:
        seams.clear(name)
        results.append(await storage_call())

    return handler, results


# ---------------------------------------------------------------------------
# Forward ordering — a write under a concurrently relocated/destroyed parent
# ---------------------------------------------------------------------------


class TestForwardOrdering:
    """The bump guard: no carrier may let a create commit a torn path."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    @pytest.mark.parametrize("carrier", ["delete", "move", "sweep"])
    async def test_write_under_a_relocating_parent_never_tears(self, env_var: str, carrier: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.mkdir(path=Path("/d"), parents=True)).success

            async def rival() -> Result:
                if carrier == "delete":
                    return await storage.delete(path=Path("/d"))
                if carrier == "move":
                    return await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/m"))])
                return await storage.sweep(path=Path("/d"))

            handler, rival_results = _self_clearing("write:before-apply", rival)
            with seams.installed("write:before-apply", handler):
                victim = await storage.write(entries=[Entry(path=Path("/d/late.txt"), content="mine")])
            assert rival_results and rival_results[0].success is True
            # The redrive judged fresh state: the parent is gone from the
            # address, so the write refuses honestly — never a torn child.
            assert victim.success is False
            assert {e.kind for e in victim.errors} <= _RACE_KINDS
            assert (await storage.stat(path=Path("/d/late.txt"))).success is False
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_write_under_a_restoring_trash_parent_never_tears(self, env_var: str) -> None:
        # The restore carrier: the victim writes under the trash-side
        # address while the rival restores it back to its original site.
        async with _server_storage(env_var) as storage:
            assert (await storage.mkdir(path=Path("/d"), parents=True)).success
            deleted = await storage.delete(path=Path("/d"))
            assert deleted.success is True
            trash_dir = deleted.observations[0].trash_path
            assert trash_dir is not None

            handler, rival_results = _self_clearing("write:before-apply", lambda: storage.restore(path=Path("/d")))
            with seams.installed("write:before-apply", handler):
                victim = await storage.write(entries=[Entry(path=Path(f"{trash_dir}/late.txt"), content="mine")])
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            assert {e.kind for e in victim.errors} <= _RACE_KINDS
            assert (await storage.stat(path=Path(f"{trash_dir}/late.txt"))).success is False
            await _audit(storage)


# ---------------------------------------------------------------------------
# Reverse ordering — a rival write between collection and claim
# ---------------------------------------------------------------------------


class TestReverseOrdering:
    """The claim guard: a stale descendant list can never commit — Postgres included."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_delete_recollects_a_child_committed_post_collect(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success
            # Pre-mint the trash chain: a first-ever delete creates /.vfs
            # and bumps the root row, and on MSSQL's locking READ
            # COMMITTED that uncommitted root lock parks every rival
            # write's snapshot read — the staged interleaving is only
            # reachable in the steady state, so stage it there.
            assert (await storage.write(entries=[Entry(path=Path("/sacrifice.txt"), content="x")])).success
            assert (await storage.delete(path=Path("/sacrifice.txt"))).success

            handler, rival_results = _self_clearing(
                "delete:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/d/late.txt"), content="rival")]),
            )
            with seams.installed("delete:post-collect", handler):
                victim = await storage.delete(path=Path("/d"))
            assert rival_results and rival_results[0].success is True
            # The guard flipped, the verb redrove, and the re-collection
            # carried the late child into trash with its parent.
            assert victim.success is True, victim.errors
            trash_dir = victim.observations[0].trash_path
            assert trash_dir is not None
            assert (await storage.stat(path=Path(f"{trash_dir}/late.txt"))).success is True
            assert (await storage.stat(path=Path("/d/late.txt"))).success is False
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_move_recollects_a_child_committed_post_collect(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success

            handler, rival_results = _self_clearing(
                "transfer:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/d/late.txt"), content="rival")]),
            )
            with seams.installed("transfer:post-collect", handler):
                victim = await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))])
            assert rival_results and rival_results[0].success is True
            assert victim.success is True, victim.errors
            assert (await storage.stat(path=Path("/e/late.txt"))).success is True
            assert (await storage.stat(path=Path("/d/late.txt"))).success is False
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_delete_recollects_a_depth_two_child_committed_post_collect(self, env_var: str) -> None:
        # The depth-2 window: the rival's guarded bump touches only its
        # direct parent (/d/sub), never the delete target (/d), so neither
        # side's guard flips — only the post-claim re-collection can carry
        # the late child. The depth-1 twin above cannot see this window.
        async with _server_storage(env_var) as storage:
            assert (
                await storage.write(entries=[Entry(path=Path("/d/sub/keep.txt"), content="x")], parents=True)
            ).success
            # Steady-state staging: pre-mint the trash chain (see the
            # depth-1 twin for the MSSQL locking-RC rationale).
            assert (await storage.write(entries=[Entry(path=Path("/sacrifice.txt"), content="x")])).success
            assert (await storage.delete(path=Path("/sacrifice.txt"))).success

            handler, rival_results = _self_clearing(
                "delete:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/d/sub/new.txt"), content="precious")]),
            )
            with seams.installed("delete:post-collect", handler):
                victim = await storage.delete(path=Path("/d"))
            assert rival_results and rival_results[0].success is True
            assert victim.success is True, victim.errors
            trash_dir = victim.observations[0].trash_path
            assert trash_dir is not None
            assert (await storage.stat(path=Path(f"{trash_dir}/sub/new.txt"))).success is True
            assert (await storage.stat(path=Path("/d/sub/new.txt"))).success is False
            await _audit(storage)


# ---------------------------------------------------------------------------
# Overwrite fence — a rival's committed file is never silently destroyed
# ---------------------------------------------------------------------------


class TestOverwriteFence:
    """The occupant destroy is guarded: the rival's row survives or the verb refuses."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_move_overwrite_never_destroys_a_rival_child(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.mkdir(path=Path("/a"))).success
            assert (await storage.mkdir(path=Path("/b"))).success

            handler, rival_results = _self_clearing(
                "transfer:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/b/f.txt"), content="precious")]),
            )
            with seams.installed("transfer:post-collect", handler):
                victim = await storage.move(operations=[ResolvedPair(src=Path("/a"), dest=Path("/b"))], overwrite=True)
            assert rival_results and rival_results[0].success is True
            # The fence flipped and the redriven ladder refused honestly —
            # the rival's committed file is intact, never purged.
            assert victim.success is False
            assert [e.kind for e in victim.errors] == [VFSErrorKind.not_empty]
            assert (await storage.read(path=Path("/b/f.txt"))).observations[0].content == "precious"
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_restore_overwrite_never_destroys_a_rival_child(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.mkdir(path=Path("/r"))).success
            assert (await storage.delete(path=Path("/r"))).success
            assert (await storage.mkdir(path=Path("/r"))).success

            handler, rival_results = _self_clearing(
                "restore:post-resolve",
                lambda: storage.write(entries=[Entry(path=Path("/r/f.txt"), content="precious")]),
            )
            with seams.installed("restore:post-resolve", handler):
                victim = await storage.restore(path=Path("/r"), overwrite=True)
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            assert [e.kind for e in victim.errors] == [VFSErrorKind.not_empty]
            assert (await storage.read(path=Path("/r/f.txt"))).observations[0].content == "precious"
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_copy_child_collision_redrives_to_the_honest_refusal(self, env_var: str) -> None:
        # A rival lands a child at an address the copy is about to mint:
        # the unique violation redrives, and the fresh ladder blames the
        # occupant honestly — never `exists` at an already-granted root.
        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/src/a.txt"), content="x")], parents=True)).success
            assert (await storage.mkdir(path=Path("/dest"))).success

            handler, rival_results = _self_clearing(
                "transfer:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/dest/a.txt"), content="rival")]),
            )
            with seams.installed("transfer:post-collect", handler):
                victim = await storage.copy(
                    operations=[ResolvedPair(src=Path("/src"), dest=Path("/dest"))], overwrite=True
                )
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            [error] = victim.errors
            assert error.kind == VFSErrorKind.not_empty
            lowered = error.message.lower()
            assert not any(t in lowered for t in ("unique", "duplicate", "ora-", "sqlstate", "constraint"))
            assert (await storage.read(path=Path("/dest/a.txt"))).observations[0].content == "rival"
            await _audit(storage)


# ---------------------------------------------------------------------------
# Concurrent ancestor minting — mkdir -p parity under genuine concurrency
# ---------------------------------------------------------------------------


class TestAncestorMintConvergence:
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_concurrent_parents_writes_both_succeed(self, env_var: str) -> None:
        # Two instances race parents=True writes under the same fresh
        # directory: the loser adopts the winner's mint and both succeed —
        # sequential execution succeeds, so a hard-failed loser is a defect.
        rounds = int(os.environ.get("VFS_MINT_ROUNDS", "20"))
        async with _server_storage(env_var) as writer:
            rival = DatabaseStorage(url=os.environ[env_var])
            try:
                assert (await rival.first_touch()).success is True
                for i in range(rounds):
                    left, right = await asyncio.gather(
                        writer.write(entries=[Entry(path=Path(f"/g{i}/f1.txt"), content="l")], parents=True),
                        rival.write(entries=[Entry(path=Path(f"/g{i}/f2.txt"), content="r")], parents=True),
                    )
                    assert left.success is True, (i, left.errors)
                    assert right.success is True, (i, right.errors)
                    assert (await writer.stat(path=Path(f"/g{i}/f1.txt"))).success is True
                    assert (await writer.stat(path=Path(f"/g{i}/f2.txt"))).success is True
                    # The adopted parent is affirmed: the minter leaves 1,
                    # the adopter's attach bumps exactly once — parity.
                    parent = await writer.stat(path=Path(f"/g{i}"))
                    assert parent.observations[0].version == 2, (i, parent.observations)
                await _audit(writer)
            finally:
                await rival.close()


# ---------------------------------------------------------------------------
# Observation honesty — edit/overwrite under ancestor relocation
# ---------------------------------------------------------------------------


class TestObservationHonesty:
    """No success may name an address the post-commit parent chain contradicts."""

    # Per-engine pins for the same staged race: the reprobe engines
    # classify the definite conflict; the redrive engines re-execute
    # against fresh state and report what a fresh attempt finds.
    _EXPECTED: ClassVar[dict[str, VFSErrorKind]] = {
        "VFS_TEST_POSTGRES_URL": VFSErrorKind.not_found,
        "VFS_TEST_MYSQL_URL": VFSErrorKind.not_found,
        "VFS_TEST_MSSQL_URL": VFSErrorKind.conflict,
        "VFS_TEST_ORACLE_URL": VFSErrorKind.conflict,
    }

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_edit_never_reports_success_at_a_moved_address(self, env_var: str) -> None:
        from vfs.storage.replace import EditOperation

        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="old")], parents=True)).success

            handler, rival_results = _self_clearing(
                "write:before-apply",
                lambda: storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/e"))]),
            )
            with seams.installed("write:before-apply", handler):
                victim = await storage.edit(edits=[EditOperation(old="old", new="new")], path=Path("/d/f.txt"))
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            assert [e.kind for e in victim.errors] == [self._EXPECTED[env_var]]
            if victim.errors[0].kind == VFSErrorKind.conflict:
                assert victim.errors[0].retryable is True
            # The relocated row is untouched at its real address.
            after = await storage.read(path=Path("/e/f.txt"))
            assert after.observations[0].content == "old"
            await _audit(storage)


# ---------------------------------------------------------------------------
# Ghost name-squat — arbitration refuses incoherent rows
# ---------------------------------------------------------------------------


class TestGhostRefusal:
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_write_never_adopts_an_incoherent_row(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.mkdir(path=Path("/d"))).success
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
            victim = await storage.write(entries=[Entry(path=Path("/d/late.txt"), content="mine")], overwrite=True)
            assert victim.success is False
            assert all(e.kind == VFSErrorKind.conflict and e.retryable for e in victim.errors)
            async with host.session_factory() as session:
                conn = await session.connection()
                found = await conn.execute(select(entry.c.version, entry.c.path).where(entry.c.entry_id == ghost_id))
                row = found.one()
            assert (row.version, row.path) == (5, "/elsewhere/late.txt")


# ---------------------------------------------------------------------------
# Destination-address races — classification at the seam
# ---------------------------------------------------------------------------


class TestAddressRaceClassification:
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_restore_losing_the_address_classifies_exists(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success
            assert (await storage.delete(path=Path("/d/f.txt"))).success

            handler, rival_results = _self_clearing(
                "restore:post-resolve",
                lambda: storage.write(entries=[Entry(path=Path("/d/f.txt"), content="rival")]),
            )
            with seams.installed("restore:post-resolve", handler):
                victim = await storage.restore(path=Path("/d/f.txt"))
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            [error] = victim.errors
            assert error.kind in {VFSErrorKind.exists, VFSErrorKind.conflict}
            # No raw driver text on the public surface; detail is machine data.
            lowered = error.message.lower()
            assert not any(t in lowered for t in ("unique", "duplicate", "ora-", "sqlstate", "constraint"))
            assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "rival"
            await _audit(storage)


# ---------------------------------------------------------------------------
# Purge windows — entry-first ordering under a mid-purge rival
# ---------------------------------------------------------------------------


class TestPurgeWindows:
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_rival_body_replace_mid_purge_leaves_no_orphan(self, env_var: str) -> None:
        from vfs.storage.replace import EditOperation

        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success

            handler, rival_results = _self_clearing(
                "purge:pre-entry-delete",
                lambda: storage.edit(edits=[EditOperation(old="x", new="fresh")], path=Path("/d/f.txt")),
            )
            with seams.installed("purge:pre-entry-delete", handler):
                victim = await storage.sweep(path=Path("/d"))
            assert victim.success is True, victim.errors
            # Whatever the rival managed, no body may outlive its entry.
            assert rival_results
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_rival_create_mid_purge_is_swept_or_refused(self, env_var: str) -> None:
        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success

            handler, rival_results = _self_clearing(
                "purge:pre-entry-delete",
                lambda: storage.write(entries=[Entry(path=Path("/d/late.txt"), content="rival")]),
            )
            with seams.installed("purge:pre-entry-delete", handler):
                victim = await storage.sweep(path=Path("/d"))
            assert victim.success is True, victim.errors
            assert rival_results
            # Landed before the entry delete → re-collected and swept;
            # landed after → the bump guard refused it. Either way: gone.
            assert (await storage.stat(path=Path("/d/late.txt"))).success is False
            await _audit(storage)


# ---------------------------------------------------------------------------
# Natural-timing storm — two instances, no seams, seeded jitter
# ---------------------------------------------------------------------------


class TestNaturalTimingStorm:
    @pytest.mark.slow
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_storm_rounds_hold_the_integrity_audit(self, env_var: str) -> None:
        rounds = int(os.environ.get("VFS_RACE_STORM_ROUNDS", "10"))
        batch = int(os.environ.get("VFS_RACE_STORM_N", "300"))
        seed = int(os.environ.get("VFS_RACE_STORM_SEED", "4242"))
        rng = random.Random(seed)
        async with _server_storage(env_var) as writer:
            rival = DatabaseStorage(url=os.environ[env_var])
            try:
                # Warm both instances before the storm: a cold MSSQL first
                # touch blocks unboundedly behind an in-flight rival
                # transaction — a filed open question this family does not
                # own, and the documented deployment posture is warm pools.
                assert (await rival.first_touch()).success is True
                for round_no in range(rounds):
                    base = f"/storm{round_no}"
                    assert (await writer.mkdir(path=Path(base), parents=True)).success

                    async def write_burst(base: str = base, round_no: int = round_no) -> Result:
                        await asyncio.sleep(rng.uniform(0, 0.02))
                        entries = [
                            Entry(path=Path(f"{base}/f{i:04d}.txt"), content=f"body {round_no}/{i}")
                            for i in range(batch)
                        ]
                        return await writer.write(entries=entries)

                    async def topology_hit(base: str = base) -> Result:
                        await asyncio.sleep(rng.uniform(0, 0.02))
                        return await rival.delete(path=Path(base))

                    write_result, delete_result = await asyncio.gather(write_burst(), topology_hit())
                    for result in (write_result, delete_result):
                        for error in result.errors:
                            assert error.kind in _RACE_KINDS, (
                                f"round {round_no}: unclassified race outcome {error.kind}: {error.message}"
                            )
                    await _audit(writer)
            finally:
                await rival.close()


# ---------------------------------------------------------------------------
# Adopt affirmation — an adopting write arbitrates with topology
# ---------------------------------------------------------------------------


class TestAdoptAffirmation:
    """A child can never commit under a parent a rival concurrently trashed."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_adopting_write_never_lands_under_a_trashed_parent(self, env_var: str) -> None:
        # Natural timing, no seams: write(parents=True) races mkdir+delete
        # of the same fresh directory. The adopted parent's affirming bump
        # forces the write and the delete's claim to arbitrate — a child
        # standing under a trashed parent is the torn state the audit fails.
        rounds = int(os.environ.get("VFS_ADOPT_ROUNDS", "15"))
        async with _server_storage(env_var) as writer:
            rival = DatabaseStorage(url=os.environ[env_var])
            try:
                assert (await rival.first_touch()).success is True
                # Pre-mint the trash chain: a fresh-DB delete would take the
                # root lock ladder mid-storm (the campaign's known trap).
                assert (await rival.write(entries=[Entry(path=Path("/warm.txt"), content="w")])).success
                assert (await rival.delete(path=Path("/warm.txt"))).success
                for i in range(rounds):

                    async def churn(i: int = i) -> None:
                        await rival.mkdir(path=Path(f"/z{i}"))
                        await rival.delete(path=Path(f"/z{i}"))

                    await asyncio.gather(
                        writer.write(entries=[Entry(path=Path(f"/z{i}/a.txt"), content="x")], parents=True),
                        churn(),
                    )
                    # Every interleaving is lawful except a torn namespace:
                    # a live child's parent chain must resolve.
                    child = await writer.stat(path=Path(f"/z{i}/a.txt"))
                    if child.success:
                        listing = await writer.ls(path=Path(f"/z{i}"))
                        assert listing.success is True, (i, listing.errors)
                        assert any(str(o.path) == f"/z{i}/a.txt" for o in listing.observations), i
                    await _audit(writer)
            finally:
                await rival.close()


# ---------------------------------------------------------------------------
# Exhaustion classification — one channel on every engine
# ---------------------------------------------------------------------------


class TestExhaustionClassification:
    """A lost race is a retryable conflict everywhere — never unavailable,
    never raw driver text, however it exhausted."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_hot_row_storm_reports_only_clean_conflicts(self, env_var: str) -> None:
        writers, per_writer = 8, 6
        async with _server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/hot.txt"), content="0")])).success
            instances = [DatabaseStorage(url=os.environ[env_var]) for _ in range(writers)]
            try:
                for instance in instances:
                    assert (await instance.first_touch()).success is True

                async def hammer(instance: DatabaseStorage, tag: int) -> list[Result]:
                    outcomes = []
                    for n in range(per_writer):
                        entries = [Entry(path=Path("/hot.txt"), content=f"{tag}-{n}")]
                        outcomes.append(await instance.write(entries=entries, overwrite=True))
                    return outcomes

                rounds = await asyncio.gather(*(hammer(instance, k) for k, instance in enumerate(instances)))
                clean = ("kept losing to concurrent changes", "Concurrent modification", "missed their snapshot")
                conflicts = 0
                for result in (r for burst in rounds for r in burst):
                    for error in result.errors:
                        assert error.kind == VFSErrorKind.conflict, (error.kind, error.message)
                        assert error.retryable is True
                        assert any(template in error.message for template in clean), error.message
                        conflicts += 1
                assert conflicts >= 1  # a stormless storm pins nothing
                await _audit(storage)
            finally:
                for instance in instances:
                    await instance.close()
