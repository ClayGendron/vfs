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
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from typing import Any, ClassVar, NamedTuple

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from ulid import ULID

from tests.support.commit_worlds import (
    ALICE,
    ANONYMOUS,
    BOB,
    CAROL,
    EVE,
    SYSTEM,
    attempts,
    copy_world,
    dest_world,
    drop_world,
    grant_world,
    label_world,
    paths_under,
    row_at,
    version_count,
)
from tests.support.database_helpers import _url
from tests.support.oracles.postings import decode_postings
from tests.support.server_schemas import ENGINE_LEGS, server_storage, sibling
from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, dialects, indexing, seams
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import maintenance as maintenance_module
from vfs.storage.backends.database import search as search_module
from vfs.storage.backends.database.labels import labels_for
from vfs.storage.backends.database.revision import hold_revision
from vfs.storage.grants import LEVEL_RANK, Posture
from vfs.storage.replace import EditOperation

# Kinds that may lawfully surface from a lost race; anything else — above
# all ``unavailable`` with raw driver text — is a classification defect.
_RACE_KINDS = frozenset({ErrorKind.not_found, ErrorKind.conflict, ErrorKind.exists, ErrorKind.invalid})

# On the engines that lock index keys: a session's own id, and whether that session now waits on a row lock.
_SESSION_ID = {"mariadb": "SELECT CONNECTION_ID()", "mssql": "SELECT @@SPID"}
_LOCK_WAIT = {
    "mariadb": "SELECT COUNT(*) FROM information_schema.INNODB_TRX WHERE trx_mysql_thread_id = :id"
    " AND trx_state = 'LOCK WAIT'",
    "mssql": "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id = :id AND wait_type LIKE 'LCK_M_%'",
}


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
        async with server_storage(env_var) as storage:
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
    @pytest.mark.parametrize("verb", ["write", "edit"])
    async def test_an_overwrite_under_a_deleted_parent_never_revives_the_child(self, env_var: str, verb: str) -> None:
        # A delete rewrites no path and bumps no descendant, so only the
        # tombstone term in the update's guard can notice the parent went.
        async with server_storage(env_var, trash_days=0) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="old")], parents=True)).success

            handler, rival_results = _self_clearing("write:before-apply", lambda: storage.delete(path=Path("/d")))
            with seams.installed("write:before-apply", handler):
                if verb == "write":
                    victim = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="mine")], overwrite=True)
                else:
                    victim = await storage.edit(edits=[EditOperation(old="old", new="mine")], path=Path("/d/f.txt"))
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            assert {e.kind for e in victim.errors} <= _RACE_KINDS
            assert (await storage.stat(path=Path("/d/f.txt"))).success is False
            assert (await storage.read(path=Path("/.vfs/trash/d/f.txt"))).observations[0].content == "old"
            # Retention purges the root's whole set: no child survives its parent.
            assert (await storage.sweep(path=Path("/.vfs/trash"))).success is True
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_revive_racing_a_restore_leaves_one_live_row(self, env_var: str) -> None:
        # The victim writes at a deleted file's path (the revive) while the
        # rival restores it mid-window: one row, live once, never torn.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="old")], parents=True)).success
            assert (await storage.delete(path=Path("/d/f.txt"))).success is True

            handler, rival_results = _self_clearing(
                "write:before-apply", lambda: storage.restore(path=Path("/d/f.txt"))
            )
            with seams.installed("write:before-apply", handler):
                victim = await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="mine")])
            assert rival_results and rival_results[0].success is True
            # The guard flipped: the redrive overwrote the restored row, or refused honestly.
            if not victim.success:
                assert {e.kind for e in victim.errors} <= _RACE_KINDS
            body = (await storage.read(path=Path("/d/f.txt"))).observations[0].content
            assert body == ("mine" if victim.success else "old")
            assert (await storage.ls(path=Path("/.vfs/trash"))).observations == []
            await _audit(storage)


class TestMkedgeEndpointLocks:
    """The insert-side liveness lock: a rival delete cannot commit mid-window."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_rival_delete_serializes_behind_the_locked_resolve(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            entries = [Entry(path=Path("/src.py"), content="x"), Entry(path=Path("/dst.py"), content="x")]
            assert (await storage.write(entries=entries)).success is True
            pending: dict[str, asyncio.Task[Result]] = {}

            async def handler() -> None:
                pending["delete"] = asyncio.ensure_future(storage.delete(path=Path("/dst.py")))
                done, _ = await asyncio.wait([pending["delete"]], timeout=1.0)
                assert not done, "the rival delete slipped past the endpoint locks"

            edge = Edge(source=Path("/src.py"), target=Path("/dst.py"), edge_type="imports")
            with seams.installed("mkedge:before-insert", handler):
                created = await storage.mkedge(edges=[edge])
            assert created.success is True
            assert created.observations[0].status == "created"
            deleted = await asyncio.wait_for(pending["delete"], timeout=60)
            assert deleted.success is True
            # Converged: the cascade swept the edge the lock let land first,
            # proven by absence through the public verb.
            gone = await storage.rmedge(edges=[edge])
            assert gone.observations == []
            assert gone.errors[0].kind == ErrorKind.not_found
            await _audit(storage)

    @pytest.mark.slow
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_mkedge_bursts_against_deletes_leave_no_stray(self, env_var: str) -> None:
        # Natural timing: edge batches lock endpoints in sorted order while
        # rival deletes claim them in their own; every deadlock must ride
        # the retry channel, and the reclaim must find nothing afterward.
        rounds = int(os.environ.get("VFS_RACE_STORM_ROUNDS", "10"))
        batch = int(os.environ.get("VFS_RACE_STORM_N", "300"))
        rng = random.Random(int(os.environ.get("VFS_RACE_STORM_SEED", "4242")))
        async with server_storage(env_var) as writer:
            rival = sibling(env_var, writer)
            try:
                assert (await rival.first_touch()).success is True
                for round_no in range(rounds):
                    base = f"/storm{round_no}"
                    spokes = [Path(f"{base}/s{i:04d}.py") for i in range(batch)]
                    hub = Path(f"{base}/hub.py")
                    assert (await writer.mkdir(path=Path(base), parents=True)).success
                    entries = [Entry(path=hub, content="h")] + [Entry(path=spoke, content="s") for spoke in spokes]
                    assert (await writer.write(entries=entries)).success

                    async def edge_burst(edges: list[Edge]) -> Result:
                        await asyncio.sleep(rng.uniform(0, 0.02))
                        return await writer.mkedge(edges=edges)

                    async def topology_hit(path: Path) -> Result:
                        await asyncio.sleep(rng.uniform(0, 0.05))
                        return await rival.delete(path=path)

                    outward = [Edge(source=hub, target=spoke, edge_type="imports") for spoke in spokes]
                    inward = [Edge(source=spoke, target=hub, edge_type="ref") for spoke in reversed(spokes)]
                    victims = rng.sample(spokes, 3)
                    results = await asyncio.gather(
                        edge_burst(outward),
                        edge_burst(inward),
                        *(topology_hit(victim) for victim in victims),
                        topology_hit(Path(base)),
                    )
                    for result in results:
                        for error in result.errors:
                            assert error.kind in _RACE_KINDS, (
                                f"round {round_no}: unclassified race outcome {error.kind}: {error.message}"
                            )
                    rebuilt = await writer.rebuild()
                    assert rebuilt.success is True
                    strays = [error.message for error in rebuilt.errors if "touching trashed" in error.message]
                    assert strays == [], f"round {round_no}: {strays}"
                    await _audit(writer)
            finally:
                await rival.close()


# ---------------------------------------------------------------------------
# Reverse ordering — a rival write between collection and claim
# ---------------------------------------------------------------------------


class TestReverseOrdering:
    """The claim guard: a stale descendant list can never commit — Postgres included."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_delete_recollects_a_child_committed_post_collect(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success

            handler, rival_results = _self_clearing(
                "delete:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/d/late.txt"), content="rival")]),
            )
            with seams.installed("delete:post-collect", handler):
                victim = await storage.delete(path=Path("/d"))
            assert rival_results and rival_results[0].success is True
            # The guard flipped, the verb redrove, and the cascade marked
            # the late child with its parent.
            assert victim.success is True, victim.errors
            assert (await storage.stat(path=Path("/.vfs/trash/d/late.txt"))).success is True
            assert (await storage.stat(path=Path("/d/late.txt"))).success is False
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_move_recollects_a_child_committed_post_collect(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
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
        async with server_storage(env_var) as storage:
            assert (
                await storage.write(entries=[Entry(path=Path("/d/sub/keep.txt"), content="x")], parents=True)
            ).success

            handler, rival_results = _self_clearing(
                "delete:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/d/sub/new.txt"), content="precious")]),
            )
            with seams.installed("delete:post-collect", handler):
                victim = await storage.delete(path=Path("/d"))
            assert rival_results and rival_results[0].success is True
            assert victim.success is True, victim.errors
            assert (await storage.stat(path=Path("/.vfs/trash/d/sub/new.txt"))).success is True
            assert (await storage.stat(path=Path("/d/sub/new.txt"))).success is False
            await _audit(storage)


# ---------------------------------------------------------------------------
# Overwrite fence — a rival's committed file is never silently destroyed
# ---------------------------------------------------------------------------


class TestTransferCollision:
    """A rival lands under the destination mid-window: the redriven ladder refuses honestly."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_copy_child_collision_redrives_to_the_honest_refusal(self, env_var: str) -> None:
        # A rival mints the destination and a child at addresses the copy
        # is about to mint: the unique violation redrives, and the fresh
        # ladder refuses the now-occupied root honestly — a classified
        # `exists`, never a driver error leaking across the seam.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/src/a.txt"), content="x")], parents=True)).success

            handler, rival_results = _self_clearing(
                "transfer:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/dest/a.txt"), content="rival")], parents=True),
            )
            with seams.installed("transfer:post-collect", handler):
                victim = await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/dest"))])
            assert rival_results and rival_results[0].success is True
            assert victim.success is False
            [error] = victim.errors
            assert error.kind == ErrorKind.exists
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
        async with server_storage(env_var) as writer:
            rival = sibling(env_var, writer)
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
    _EXPECTED: ClassVar[dict[str, ErrorKind]] = {
        "VFS_TEST_POSTGRES_URL": ErrorKind.not_found,
        "VFS_TEST_MARIADB_URL": ErrorKind.not_found,
        "VFS_TEST_MSSQL_URL": ErrorKind.conflict,
        "VFS_TEST_ORACLE_URL": ErrorKind.conflict,
    }

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_edit_never_reports_success_at_a_moved_address(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
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
            if victim.errors[0].kind == ErrorKind.conflict:
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
        async with server_storage(env_var) as storage:
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
                        everyone_level=LEVEL_RANK["read_write"],
                        size_bytes=4,
                        lines=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.commit()
            victim = await storage.write(entries=[Entry(path=Path("/d/late.txt"), content="mine")], overwrite=True)
            assert victim.success is False
            assert all(e.kind == ErrorKind.conflict and e.retryable for e in victim.errors)
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
    async def test_restore_losing_to_a_revive_classifies_exists(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
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
            assert error.kind in {ErrorKind.exists, ErrorKind.conflict}
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
    async def test_a_revive_mid_retention_sweep_survives(self, env_var: str) -> None:
        # The retention arm's lost-update window: the revive lands between the
        # collect and the entry delete; the tombstone proof misses and the redrive spares it.
        async with server_storage(env_var, trash_days=0) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)).success
            assert (await storage.delete(path=Path("/d/f.txt"))).success

            handler, rival_results = _self_clearing(
                "purge:post-collect",
                lambda: storage.write(entries=[Entry(path=Path("/d/f.txt"), content="revived")]),
            )
            with seams.installed("purge:post-collect", handler):
                victim = await storage.sweep(path=Path("/.vfs/trash"))
            assert rival_results and rival_results[0].success is True
            assert victim.success is True, victim.errors
            assert victim.observations == []
            assert (await storage.read(path=Path("/d/f.txt"))).observations[0].content == "revived"
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_rival_body_replace_mid_purge_leaves_no_orphan(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
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
        async with server_storage(env_var) as storage:
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
        async with server_storage(env_var) as writer:
            rival = sibling(env_var, writer)
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
        async with server_storage(env_var) as writer:
            rival = sibling(env_var, writer)
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
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/hot.txt"), content="0")])).success
            instances = [sibling(env_var, storage) for _ in range(writers)]
            try:
                for instance in instances:
                    assert (await instance.first_touch()).success is True
                    # Two attempts, not four: a write that loses twice has exhausted, so every storm has conflicts.
                    instance._host._retry_attempts = 2

                async def hammer(instance: DatabaseStorage, tag: int) -> list[Result]:
                    outcomes = []
                    for n in range(per_writer):
                        entries = [Entry(path=Path("/hot.txt"), content=f"{tag}-{n}")]
                        outcomes.append(await instance.write(entries=entries, overwrite=True))
                    return outcomes

                rounds = await asyncio.gather(*(hammer(instance, k) for k, instance in enumerate(instances)))
                conflicts = 0
                for result in (r for burst in rounds for r in burst):
                    for error in result.errors:
                        # The kind and the retry class are the fact; the message is composed from them.
                        assert error.kind == ErrorKind.conflict, (error.kind, error.message)
                        assert error.retryable is True
                        conflicts += 1
                assert conflicts >= 1  # a stormless storm pins nothing
                await _audit(storage)
            finally:
                for instance in instances:
                    await instance.close()


# ---------------------------------------------------------------------------
# Grep epoch consistency — a mid-call publish+reclaim never empties a call
# ---------------------------------------------------------------------------


class TestGrepEpochConsistency:
    """The epoch-reread ladder: old or new, never a mix, on every engine."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_grep_racing_a_publish_and_reclaim_serves_every_row(self, env_var: str) -> None:
        # The pre-fix defect: grep reads pointer N, the rival publishes
        # N+1 and reclaims N, and both tiers come back empty with
        # success=True. The re-read must redrive instead.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/old.txt"), content="needle old")])).success
            assert (await storage.rebuild()).success is True
            assert (await storage.write(entries=[Entry(path=Path("/new.txt"), content="needle new")])).success

            handler, rival_results = _self_clearing("grep:after-pointer-read", storage.rebuild)
            with seams.installed("grep:after-pointer-read", handler):
                raced = await storage.grep(pattern="needle")
            assert rival_results and rival_results[0].success is True
            assert raced.success is True, raced.errors
            assert sorted(str(o.path) for o in raced.observations) == ["/new.txt", "/old.txt"]
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_rival_demotion_mid_grep_never_hides_the_row(self, env_var: str) -> None:
        # The unpinned-engine exposure: a rival write demotes an indexed
        # row between grep's advisory verdict and its candidate fetch.
        # The authoritative post-fetch read must route the row to the
        # scan tier — never a silent false empty.
        async with server_storage(env_var) as storage:
            for path, content in (("/a.txt", "needle alpha"), ("/b.txt", "needle beta"), ("/c.txt", "needle gamma")):
                assert (await storage.write(entries=[Entry(path=Path(path), content=content)])).success
            assert (await storage.rebuild()).success is True

            async def demote() -> Result:
                entries = [Entry(path=Path("/b.txt"), content="needle beta v2")]
                return await storage.write(entries=entries, overwrite=True)

            handler, rival_results = _self_clearing("grep:after-pointer-read", demote)
            with seams.installed("grep:after-pointer-read", handler):
                raced = await storage.grep(pattern="needle")
            assert rival_results and rival_results[0].success is True, rival_results
            assert raced.success is True, raced.errors
            assert sorted(str(o.path) for o in raced.observations) == ["/a.txt", "/b.txt", "/c.txt"]
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_second_rebuild_refuses_while_one_runs(self, env_var: str) -> None:
        # The single-runner lease: the rival's claim misses while the
        # first run holds it, and the refusal names the live run.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle body")])).success

            handler, rival_results = _self_clearing("rebuild:before-publish", storage.rebuild)
            with seams.installed("rebuild:before-publish", handler):
                first = await storage.rebuild()
            assert first.success is True, first.errors
            assert rival_results and rival_results[0].success is False
            [error] = rival_results[0].errors
            assert error.kind == ErrorKind.conflict
            assert error.retryable is True
            assert "already running" in error.message
            await _audit(storage)


class TestSearchChunkConsistency:
    """A chunk row removed between a search's ranking and its text read: answered, never raised.

    Where each statement reads the latest commit (no ``op_isolation``
    pin) the rival's commit is seen: a purged entry runs the call again
    and a re-split one answers from its live body. Under a pinned
    snapshot the rival is invisible and the old answer stands.
    """

    FILES: ClassVar[dict[str, str]] = {
        "/docs/tokens.md": "Tokens are produced by the lexer and consumed by the parser.\n",
        "/notes.txt": "A stream of tokens, tokens, tokens.\n",
        "/src/lexer.py": "def lex(stream):\n    tokens = split(stream)\n    return tokens\n",
        "/src/parser.py": "def parse_tokens(stream):\n    return tokens_from(stream)\n",
    }

    @pytest.mark.parametrize("rival", ["sweep", "rewrite"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_chunk_removed_before_its_text_read_never_raises(
        self, env_var: str, rival: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the live-body answer or the redrive lost, so a rival's purge or re-split of a
        ranked entry, committed before the text read, raises out of the search."""
        async with server_storage(env_var) as storage:
            entries = [Entry(path=Path(path), content=body) for path, body in self.FILES.items()]
            assert (await storage.write(entries=entries, parents=True)).success
            assert (await storage.rebuild()).success is True

            async def commit_rival() -> Result:
                if rival == "sweep":
                    return await storage.sweep(path=Path("/notes.txt"))
                rewritten = [Entry(path=Path("/notes.txt"), content="A stream of tokens, rewritten.\n")]
                written = await storage.write(entries=rewritten, overwrite=True)
                return written if not written.success else await storage.rebuild()

            real = search_module._chunk_texts
            reads: list[int] = []

            async def counted(session, tables, chunk_ids, profile, membership_budget):
                reads.append(len(chunk_ids))
                return await real(session, tables, chunk_ids, profile, membership_budget)

            monkeypatch.setattr(search_module, "_chunk_texts", counted)
            handler, rival_results = _self_clearing("search:before-chunk-texts", commit_rival)
            with seams.installed("search:before-chunk-texts", handler):
                raced = await storage.search(query="tokens")
            assert rival_results and rival_results[0].success is True, rival_results
            assert raced.success is True, raced.errors
            answered = sorted(str(o.path) for o in raced.observations)
            if storage._host.profile.op_isolation is not None:
                assert (answered, len(reads)) == (sorted(self.FILES), 1)  # the snapshot hides the rival
            elif rival == "sweep":
                assert (answered, len(reads)) == (sorted(set(self.FILES) - {"/notes.txt"}), 2)
            else:
                assert (answered, len(reads)) == (sorted(self.FILES), 1)
                [notes] = [o for o in raced.observations if str(o.path) == "/notes.txt"]
                [match] = notes.matches or []
                assert match.content is None and match.preview == "A stream of **tokens**, rewritten."
            await _audit(storage)


# ---------------------------------------------------------------------------
# The index publishes only what its build read — the feed, the flip, the lease
# ---------------------------------------------------------------------------


async def _entry_id(storage: DatabaseStorage, path: str) -> str:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry.c.entry_id).where(entry.c.path == path))).scalar_one()


async def _epoch(storage: DatabaseStorage) -> int | None:
    index_state = storage._host.tables.index_state
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(index_state.c.current_gram_epoch))).scalar_one()


async def _chunk_ids(storage: DatabaseStorage, path: str) -> set[int]:
    chunks = storage._host.tables.chunks
    stmt = select(chunks.c.id).where(chunks.c.entry_id == await _entry_id(storage, path))
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _lexical_chunk_ids(storage: DatabaseStorage, path: str) -> set[int]:
    """The chunk ids the published epoch's ``vfs_lex_docs`` names for *path*."""
    docs = storage._host.tables.lex_docs
    entry_id, epoch = await _entry_id(storage, path), await _epoch(storage)
    stmt = select(docs.c.chunk_id).where(docs.c.epoch == epoch, docs.c.entry_id == entry_id)
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _lexical_entries(storage: DatabaseStorage) -> set[str]:
    docs = storage._host.tables.lex_docs
    stmt = select(docs.c.entry_id).where(docs.c.epoch == await _epoch(storage)).distinct()
    async with storage._host.engine.connect() as conn:
        return set((await conn.execute(stmt)).scalars())


async def _row(storage: DatabaseStorage, path: str) -> Any:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry).where(entry.c.path == path))).one()


async def _made_stale(storage: DatabaseStorage) -> None:
    """Backdate the running lease past its TTL, as a run stalled past it leaves the row; the holder stays."""
    index_state = storage._host.tables.index_state
    stale = maintenance_module._now_ms() - maintenance_module.INDEX_LEASE_TTL_MS - 1_000
    async with storage._host.engine.begin() as conn:
        await conn.execute(update(index_state).values(lease_heartbeat=stale))


async def _beat(beater: DatabaseStorage) -> None:
    """Commit the running lease's own heartbeat from *beater*, a second handle on the mount."""
    tables = beater._host.tables
    async with beater._host.engine.connect() as conn:
        token = (await conn.execute(select(tables.index_state.c.lease_holder))).scalar_one()
    beat = await beater._execute_maintenance(
        "rebuild", lambda s: maintenance_module.heartbeat_index_lease(s, tables, token)
    )
    assert beat.success, beat.errors


def _counted(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    """Count the backend's calls of the phase function *name*; the list holds one item per call."""
    calls: list[int] = []
    real = getattr(maintenance_module, name)

    async def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(len(calls))
        return await real(*args, **kwargs)

    monkeypatch.setattr(maintenance_module, name, counted)
    return calls


def _eligible(assignments: dict[str, Any]) -> bool:
    """Whether a flip is the chunk pass's eligible stamp (the publish's sets ``encoded`` alone)."""
    return assignments.get("indexable") is True


class TestBuildAgreement:
    """The lexical feed takes exactly the entries the posting scan covered, whatever commits between the reads."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_write_between_the_two_reads_never_splits_an_entry(self, env_var: str, monkeypatch) -> None:
        # No snapshot spans the build on SQL Server and Oracle: a write committed between the posting
        # scan and the lexical pages changes what a second read of the entry flags would choose.
        async with server_storage(env_var) as storage:
            words = {"/d/x.txt": "xylophone", "/a.txt": "alpha", "/b.txt": "bravo"}
            entries = [Entry(path=Path(path), content=f"{word} body") for path, word in words.items()]
            assert (await storage.write(entries=entries, parents=True)).success
            assert (await storage.delete(path=Path("/b.txt"))).success
            rival = sibling(env_var, storage)
            outcomes: list[bool] = []

            async def between_the_reads() -> None:
                seams.clear("rebuild:before-lexical")
                outcomes.append((await rival.delete(path=Path("/d"))).success)
                same = Entry(path=Path("/a.txt"), content="alpha body")
                outcomes.append((await rival.write(entries=[same], overwrite=True)).success)
                outcomes.append((await rival.restore(path=Path("/b.txt"))).success)

            received: dict[str, int] = {}
            real_publish = maintenance_module.publish_epoch

            async def capturing(session: Any, *args: Any) -> Result:
                received.update(args[-1].covered)
                return await real_publish(session, *args)

            monkeypatch.setattr(maintenance_module, "publish_epoch", capturing)
            try:
                with seams.installed("rebuild:before-lexical", between_the_reads):
                    assert (await storage.rebuild()).success is True
            finally:
                await rival.close()
            assert outcomes == [True, True, True]
            lexical = await _lexical_entries(storage)
            for path in words:
                entry_id = await _entry_id(storage, path)
                assert (entry_id in received) == (entry_id in lexical), path
            entry = storage._host.tables.entry
            async with storage._host.engine.connect() as conn:
                stmt = select(entry.c.entry_id).where(entry.c.encoded, entry.c.kind != "directory")
                encoded = set((await conn.execute(stmt)).scalars())
            assert encoded <= set(received) & lexical
            # Covered and fed, so only its flag can show a flip that landed on a tombstoned row.
            assert (await _row(storage, "/d/x.txt")).encoded is False
            assert (await storage.restore(path=Path("/d"))).success
            for path, word in words.items():
                assert [str(o.path) for o in (await storage.grep(pattern=word)).observations] == [path], word
                assert [str(o.path) for o in (await storage.search(query=word)).observations] == [path], word
            await _audit(storage)


class TestLeaseFence:
    """Every lease-held commit lands only while its run holds the lease, and none cycles with an admin write."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_lapsed_chunk_pass_never_strands_the_holders_epoch(self, env_var: str) -> None:
        # The lapsed run read its dirty set before the holder chunked and built the same entry;
        # its chunk rows must never replace the ones the holder's epoch names.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/n.txt"), content="narwhal body")])).success
            holder = sibling(env_var, storage)
            split, released, holding = asyncio.Event(), asyncio.Event(), asyncio.Event()
            published = asyncio.Event()
            arrivals: list[str] = []

            async def lapsed_at_the_split() -> None:
                if not split.is_set():
                    split.set()
                    await released.wait()

            async def at_the_publish() -> None:
                arrivals.append("lapsed" if released.is_set() else "holder")
                if not released.is_set():
                    holding.set()
                    await published.wait()

            try:
                with (
                    seams.installed("rebuild:before-chunk-split", lapsed_at_the_split),
                    seams.installed("rebuild:before-publish", at_the_publish),
                ):
                    first = asyncio.create_task(storage.rebuild())
                    await split.wait()
                    await _made_stale(storage)
                    second = asyncio.create_task(holder.rebuild())
                    await holding.wait()
                    released.set()
                    lapsed = await first
                    published.set()
                    won = await second
            finally:
                await holder.close()
            assert maintenance_module.lease_lost(lapsed), lapsed.errors
            assert arrivals == ["holder"]
            assert won.success is True, won.errors
            row = await _row(storage, "/n.txt")
            assert (row.chunked, row.encoded) == (True, True)
            assert await _lexical_chunk_ids(storage, "/n.txt") == await _chunk_ids(storage, "/n.txt")
            assert [str(o.path) for o in (await storage.search(query="narwhal")).observations] == ["/n.txt"]
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_run_whose_lease_was_taken_publishes_nothing(self, env_var: str, monkeypatch) -> None:
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/e.txt"), content="echo body")])).success
            assert (await storage.rebuild()).success is True
            assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="foxtrot body")])).success
            holder = sibling(env_var, storage)
            arrived, released = [asyncio.Event(), asyncio.Event()], [asyncio.Event(), asyncio.Event()]

            async def hold() -> None:
                for arrival, release in zip(arrived, released, strict=True):
                    if not arrival.is_set():
                        arrival.set()
                        await release.wait()
                        return

            try:
                with seams.installed("rebuild:before-publish", hold):
                    first = asyncio.create_task(storage.rebuild())
                    await arrived[0].wait()
                    await _made_stale(storage)
                    # A newer chunker: the holder re-splits every entry with no version bump.
                    monkeypatch.setattr(indexing, "chunk_generation", lambda: "a-newer-chunker")
                    second = asyncio.create_task(holder.rebuild())
                    await arrived[1].wait()
                    released[0].set()
                    lost = await first
                    released[1].set()
                    won = await second
            finally:
                await holder.close()
            [error] = lost.errors
            assert (error.kind, error.retryable) == (ErrorKind.conflict, False)
            assert error.message.endswith("rebuild lost the index publish race for epoch 2"), error.message
            assert won.success is True, won.errors
            assert await _epoch(storage) == 3
            assert await _lexical_chunk_ids(storage, "/e.txt") == await _chunk_ids(storage, "/e.txt")
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_heartbeat_inside_the_publish_never_fails_it(self, env_var: str, monkeypatch) -> None:
        # Under a snapshot isolation the compare-and-set updates a row the run's own beat changed.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
            beater = sibling(env_var, storage)
            publishes = _counted(monkeypatch, "publish_epoch")
            real_flip = indexing._flip_flags

            async def beaten(session: Any, *args: Any, assignments: dict[str, Any], **stamp: Any) -> None:
                await real_flip(session, *args, assignments=assignments, **stamp)
                if assignments == {"encoded": True}:
                    await _beat(beater)

            monkeypatch.setattr(indexing, "_flip_flags", beaten)
            try:
                result = await storage.rebuild()
            finally:
                await beater.close()
            assert result.success is True, result.errors
            assert len(publishes) == 1
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_heartbeat_inside_the_chunk_pass_never_fails_its_fence(self, env_var: str, monkeypatch) -> None:
        # Under a snapshot isolation the fence updates a row the run's own beat changed after the pass's reads.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
            beater = sibling(env_var, storage)
            passes = _counted(monkeypatch, "chunk_dirty")
            real_flip = indexing._flip_flags

            async def beaten(session: Any, *args: Any, assignments: dict[str, Any], **stamp: Any) -> None:
                await real_flip(session, *args, assignments=assignments, **stamp)
                if _eligible(assignments):
                    await _beat(beater)

            monkeypatch.setattr(indexing, "_flip_flags", beaten)
            try:
                result = await storage.rebuild()
            finally:
                await beater.close()
            assert result.success is True, result.errors
            assert len(passes) == 1
            await _audit(storage)

    @pytest.mark.parametrize("phase", ["chunk", "publish"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_an_admin_lock_never_deadlocks_a_lease_held_commit(
        self, env_var: str, phase: str, monkeypatch
    ) -> None:
        # A relabel step takes the admin lock first and entry rows after it; a lease-held commit takes
        # entry rows first and must never then ask for the admin lock's row.
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/x.txt"), content="xray body")])).success
            writer = sibling(env_var, storage)
            target, level = await _entry_id(storage, "/x.txt"), LEVEL_RANK["list"]
            attempts = _counted(monkeypatch, "chunk_dirty" if phase == "chunk" else "publish_epoch")
            relabels: list[int] = []
            holding = asyncio.Event()
            started: list[asyncio.Task[Result]] = []
            engine, sessions = storage._host.profile.name, []
            watcher = sibling(env_var, storage)

            async def relabel(session: Any) -> Result:
                relabels.append(len(relabels))
                tables = writer._host.tables
                await hold_revision(session, tables)
                if engine in _SESSION_ID:
                    sessions.append((await session.execute(text(_SESSION_ID[engine]))).scalar_one())
                holding.set()
                stmt = update(tables.entry).where(tables.entry.c.entry_id == target).values(everyone_level=level)
                await session.execute(stmt)
                return Result(ops=("set_posture",))

            real_flip = indexing._flip_flags

            async def crossed(session: Any, *args: Any, assignments: dict[str, Any], **stamp: Any) -> None:
                await real_flip(session, *args, assignments=assignments, **stamp)
                ours = _eligible(assignments) if phase == "chunk" else assignments == {"encoded": True}
                if ours and not started:
                    started.append(asyncio.create_task(writer._execute_topology("set_posture", relabel)))
                    await _arrived(holding, started[0])
                    if sessions:  # the relabel parked on the slice's row, holding whatever key it sought
                        await asyncio.wait_for(_lock_waiting(watcher, engine, sessions[0]), 30)

            monkeypatch.setattr(indexing, "_flip_flags", crossed)
            try:
                result = await storage.rebuild()
                written = await started[0]
            finally:
                await writer.close()
                await watcher.close()
            assert result.success is True, result.errors
            assert written.success is True, written.errors
            assert (len(attempts), len(relabels)) == (1, 1)
            row = await _row(storage, "/x.txt")
            assert (row.chunked, row.encoded, row.everyone_level) == (True, True, level)
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_an_entry_row_interleaving_lands_each_writer_once_within_the_retry_budget(
        self, env_var: str, monkeypatch
    ) -> None:
        # Two writers each updating two entry rows in opposite orders: whether a cycle closes and
        # which side the engine aborts are the engine's; each side's work lands once either way.
        async with server_storage(env_var) as storage:
            bodies = {"/x.txt": "xray body", "/y.txt": "yankee body"}
            assert (await storage.write(entries=[Entry(path=Path(p), content=c) for p, c in bodies.items()])).success
            writer = sibling(env_var, storage)
            ids = {path: await _entry_id(storage, path) for path in bodies}
            level = LEVEL_RANK["list"]
            passes = _counted(monkeypatch, "chunk_dirty")
            writes: list[int] = []
            holding = asyncio.Event()
            started: list[asyncio.Task[Result]] = []

            async def crossing(session: Any) -> Result:
                writes.append(len(writes))
                entry = writer._host.tables.entry
                relabelled = update(entry).values(everyone_level=level)
                await session.execute(relabelled.where(entry.c.entry_id == ids["/y.txt"]))
                holding.set()
                await session.execute(relabelled.where(entry.c.entry_id == ids["/x.txt"]))
                return Result(ops=("write",))

            real_flip = indexing._flip_flags

            async def split(
                session: Any,
                entry: Any,
                profile: Any,
                parameter_budget: int,
                membership_budget: int,
                pairs: list[tuple[str, int]],
                *,
                assignments: dict[str, Any],
                **stamp: Any,
            ) -> None:
                flip = partial(real_flip, session, entry, profile, parameter_budget, membership_budget)
                if not _eligible(assignments):
                    await flip(pairs, assignments=assignments, **stamp)
                    return
                if not started:
                    started.append(asyncio.create_task(writer._execute_topology("write", crossing)))
                await holding.wait()
                for path in ("/x.txt", "/y.txt"):
                    await flip([pair for pair in pairs if pair[0] == ids[path]], assignments=assignments)

            monkeypatch.setattr(indexing, "_flip_flags", split)
            try:
                result = await storage.rebuild()
                written = await started[0]
            finally:
                await writer.close()
            assert result.success is True, result.errors
            assert written.success is True, written.errors
            assert len(passes) + len(writes) <= 3 and max(len(passes), len(writes)) <= 4
            assert not [e for e in [*result.errors, *written.errors] if e.kind == ErrorKind.unavailable]
            for path in bodies:
                row = await _row(storage, path)
                assert (row.chunked, row.everyone_level) == (True, level), path
                assert await _chunk_ids(storage, path), path
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_chunk_row_collision_is_recognised_from_the_engines_own_error(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
            assert (await storage.rebuild()).success is True
            chunks = storage._host.tables.chunks
            columns = [chunks.c[name] for name in ("entry_id", "chunk_index", "line_start", "line_end")]
            columns += [chunks.c.content_hash, chunks.c.encoded, chunks.c.content]
            async with storage._host.engine.connect() as conn:
                existing = dict((await conn.execute(select(*columns))).mappings().one())
            for row, unique in ((existing, True), ({**existing, "entry_id": None}, False)):
                async with storage._host.session_factory() as session:
                    await session.connection(execution_options={"vfs_writer": True})
                    with pytest.raises(IntegrityError) as raised:
                        await dialects.bulk_insert(session, chunks, [row])
                    assert dialects.is_unique_violation(raised.value) is unique, raised.value
                    await session.rollback()


@pytest.mark.mariadb
class TestGenerationRedirtyLockScope:
    """The probe-guarded re-dirty: a settled store's chunk pass locks nothing.

    REPEATABLE READ scan-locks every row an unindexed UPDATE reads, so an
    unguarded generation re-dirty — matching zero rows on every rebuild
    after the first — parks every rival entry write on next-key locks
    until the rebuild transaction commits (measured: a single-row rival
    UPDATE blocked 3 s to lock-wait timeout at 20k rows). The probe skips
    the UPDATE in the steady state, so the rival commits immediately.
    """

    async def test_a_rival_row_update_passes_during_the_chunk_pass(self) -> None:
        async with server_storage("VFS_TEST_MARIADB_URL") as storage:
            settled = [Entry(path=Path(f"/f{i:03}.txt"), content=f"settled body {i:03}") for i in range(50)]
            assert (await storage.write(entries=settled)).success is True
            assert (await storage.rebuild()).success is True
            # One fresh body keeps the chunk pass busy enough to reach the
            # seam with its transaction open; every settled row stays clean.
            assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="fresh body")])).success

            entry = storage._host.tables.entry
            rival_engine = create_async_engine(os.environ["VFS_TEST_MARIADB_URL"])
            served: list[bool] = []

            async def rival() -> None:
                seams.clear("rebuild:before-chunk-flip")
                async with rival_engine.begin() as conn:
                    await conn.execute(text("SET SESSION innodb_lock_wait_timeout = 3"))
                    await conn.execute(update(entry).where(entry.c.path == "/f000.txt").values(name=entry.c.name))
                served.append(True)

            try:
                with seams.installed("rebuild:before-chunk-flip", rival):
                    assert (await storage.rebuild()).success is True
            finally:
                await rival_engine.dispose()
            assert served == [True]
            await _audit(storage)


# ---------------------------------------------------------------------------
# Generation consistency — a refresh's commits against a running read
# ---------------------------------------------------------------------------


def _unpinned(storage: DatabaseStorage) -> bool:
    """Whether each statement of a read attempt sees the latest commit: no snapshot pin on the profile."""
    return storage._host.profile.op_isolation is None


async def _generation(storage: DatabaseStorage) -> tuple[int | None, int]:
    index_state = storage._host.tables.index_state
    async with storage._host.engine.connect() as conn:
        row = (await conn.execute(select(index_state.c.current_gram_epoch, index_state.c.index_generation))).one()
    return row._tuple()


async def _live_epochs(storage: DatabaseStorage) -> tuple[int, ...]:
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        return await indexing.live_set(session, tables, await indexing.current_epoch(session, tables))


async def _segments_of(storage: DatabaseStorage, path: str) -> set[int]:
    """The live segments whose ``vfs_lex_docs`` name *path*'s chunks."""
    docs = storage._host.tables.lex_docs
    live = await _live_epochs(storage)
    entry_id = await _entry_id(storage, path)
    async with storage._host.engine.connect() as conn:
        epochs = set((await conn.execute(select(docs.c.epoch).where(docs.c.entry_id == entry_id))).scalars())
    return epochs & set(live)


async def _gram_posted(storage: DatabaseStorage, path: str, epoch: int) -> bool:
    surrogate = (await _row(storage, path)).id
    postings = storage._host.tables.posting_list
    async with storage._host.engine.connect() as conn:
        blobs = (await conn.execute(select(postings.c.postings).where(postings.c.epoch == epoch))).scalars()
        return any(surrogate in decode_postings(bytes(blob)) for blob in blobs)


class TestGenerationConsistency:
    """A refresh moves the generation, never the pointer; readers redrive on it exactly where an engine shows it."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_delta_publish_mid_call_redrives_grep_and_search(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="quokka alpha")])).success
            assert (await storage.rebuild()).success is True
            rival = sibling(env_var, storage)
            try:
                for verb in ("grep", "search"):
                    path = f"/{verb}.txt"
                    assert (await storage.write(entries=[Entry(path=Path(path), content="wombat fresh")])).success
                    before = await _generation(storage)
                    seen, refreshed_once = _refreshing_once(rival)
                    with seams.installed(f"{verb}:after-pointer-read", refreshed_once):
                        found = storage.grep(pattern="wombat") if verb == "grep" else storage.search(query="wombat")
                        result = await found
                    after = await _generation(storage)
                    assert (after[0], after[1]) == (before[0], before[1] + 1)
                    assert len(seen) == (2 if _unpinned(storage) else 1), verb
                    assert path in [str(o.path) for o in result.observations], verb
            finally:
                await rival.close()

    async def test_a_delta_published_mid_full_build_fails_the_full_publish(self, tmp_path) -> None:
        url = _url(tmp_path)
        storage, rival = DatabaseStorage(url=url), DatabaseStorage(url=url)
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
        assert (await storage.rebuild()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/x.txt"), content="xylophone body")])).success
        arrived, released = asyncio.Event(), asyncio.Event()

        async def hold() -> None:
            arrived.set()
            await released.wait()

        try:
            with seams.installed("rebuild:before-publish", hold):
                full = asyncio.create_task(storage.rebuild())
                await _arrived(arrived, full)
                built = (await _gram_rows(storage))[-1]
                await _made_stale(storage)
                assert (await rival.refresh()).success is True
                released.set()
                lost = await full
        finally:
            await rival.close()
        [error] = lost.errors
        assert (error.kind, error.retryable) == (ErrorKind.conflict, False)
        assert error.message.endswith(f"rebuild lost the index publish race for epoch {built}"), error.message
        assert all(epoch != built for epoch in await _gram_rows(storage))
        live = await _live_epochs(storage)
        for path in ("/a.txt", "/x.txt"):
            assert (await _row(storage, path)).encoded is True
            assert any([await _gram_posted(storage, path, epoch) for epoch in live]), path
        await storage.close()

    async def test_a_write_during_a_publish_keeps_one_posting(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
        assert (await storage.rebuild()).success is True
        for verb, path in (("refresh", "/p.txt"), ("rebuild", "/q.txt")):
            entries = [Entry(path=Path(path), content=f"{path} body words")]
            assert (await storage.write(entries=entries)).success
            with seams.installed(f"{verb}:before-publish", _written_once(storage, f"{verb}:before-publish", entries)):
                assert (await getattr(storage, verb)()).success is True
            row = await _row(storage, path)
            assert row.encoded is False and row.indexed_epoch == max(await _live_epochs(storage))
            epochs = await _gram_rows(storage)
            assert (await storage.refresh()).success is True
            assert await _gram_rows(storage) == epochs
            assert (await _row(storage, path)).encoded is True
            assert len(await _segments_of(storage, path)) == 1
        await storage.close()

    @pytest.mark.parametrize("case", ["a", "b", "c"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_refresh_redrives_a_search_as_decision_30_counts(self, env_var: str, case: str) -> None:
        files = {
            "/notes.txt": "tokens tokens tokens here",
            "/a.txt": "tokens tokens in a",
            "/b.txt": "tokens in b",
            "/c.txt": "tokens in c",
        }
        async with server_storage(env_var) as storage:
            entries = [Entry(path=Path(p), content=c) for p, c in files.items()]
            assert (await storage.write(entries=entries)).success
            assert (await storage.rebuild()).success is True
            storage._host._retry_base_delay = 0.0
            rival = sibling(env_var, storage)
            attempts: list[int] = []
            held, release = asyncio.Event(), asyncio.Event()
            background: list[asyncio.Task[Result]] = []
            windows: list[int] = []

            async def at_pointer() -> None:
                attempts.append(len(attempts))
                if case == "c":
                    fresh = [Entry(path=Path(f"/n{len(attempts)}.txt"), content="tokens fresh")]
                    assert (await rival.write(entries=fresh)).success
                    assert (await rival.refresh()).success is True
                elif case == "b" and background and not release.is_set():
                    release.set()
                    assert (await background[0]).success is True

            async def at_texts() -> None:
                if windows:
                    return
                windows.append(1)
                if case == "a":
                    rewritten = [Entry(path=Path("/notes.txt"), content="tokens rewritten")]
                    assert (await rival.write(entries=rewritten)).success
                    assert (await rival.refresh()).success is True
                elif case == "b":
                    overwritten = [Entry(path=Path("/notes.txt"), data=b"\x01\x02bytes")]
                    assert (await rival.write(entries=overwritten)).success
                    assert (await rival.write(entries=[Entry(path=Path("/new.txt"), content="tokens new")])).success
                    background.append(asyncio.create_task(rival.refresh()))
                    await held.wait()

            async def at_publish() -> None:
                held.set()
                await release.wait()

            try:
                with (
                    seams.installed("search:after-pointer-read", at_pointer),
                    seams.installed("search:before-chunk-texts", at_texts),
                    seams.installed("refresh:before-publish", at_publish if case == "b" else _noop),
                ):
                    result = await storage.search(query="tokens")
                    release.set()
                    for task in background:
                        await task
            finally:
                await rival.close()
            paths = [str(o.path) for o in result.observations]
            if not _unpinned(storage):
                assert len(attempts) == 1, (case, attempts)
            elif case == "a":
                assert len(attempts) == 1 and result.success, result.errors
                [notes] = [o for o in result.observations if str(o.path) == "/notes.txt"]
                assert len(notes.matches or []) == 1 and (notes.matches or [])[0].content is None
            elif case == "b":
                assert len(attempts) == 3 and "/notes.txt" not in paths and "/new.txt" in paths, (attempts, paths)
            else:
                assert len(attempts) == 4 and result.success is False
                [error] = result.errors
                assert (error.kind, error.retryable) == (ErrorKind.conflict, True)
                ending = "search kept losing to concurrent changes: the index generation moved mid-search"
                assert error.message.endswith(ending), error.message

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_lapsed_refresh_chunk_pass_never_strands_the_holders_delta(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
            assert (await storage.rebuild()).success is True
            assert (await storage.write(entries=[Entry(path=Path("/n.txt"), content="narwhal body")])).success
            holder = sibling(env_var, storage)
            split, released, holding, published = asyncio.Event(), asyncio.Event(), asyncio.Event(), asyncio.Event()
            arrivals: list[str] = []

            async def lapsed_at_the_split() -> None:
                if not split.is_set():
                    split.set()
                    await released.wait()

            async def at_the_publish() -> None:
                arrivals.append("lapsed" if released.is_set() else "holder")
                if not released.is_set():
                    holding.set()
                    await published.wait()

            try:
                with (
                    seams.installed("refresh:before-chunk-split", lapsed_at_the_split),
                    seams.installed("refresh:before-publish", at_the_publish),
                ):
                    first = asyncio.create_task(storage.refresh())
                    await _arrived(split, first)
                    await _made_stale(storage)
                    second = asyncio.create_task(holder.refresh())
                    await _arrived(holding, second)
                    released.set()
                    lapsed = await first
                    published.set()
                    won = await second
            finally:
                await holder.close()
            assert maintenance_module.lease_lost(lapsed), lapsed.errors
            assert arrivals == ["holder"]
            assert won.success is True, won.errors
            delta = max(await _live_epochs(storage))
            assert (await _row(storage, "/n.txt")).indexed_epoch == delta
            docs = storage._host.tables.lex_docs
            entry_id = await _entry_id(storage, "/n.txt")
            stmt = select(docs.c.chunk_id).where(docs.c.entry_id == entry_id, docs.c.epoch == delta)
            async with storage._host.engine.connect() as conn:
                named = set((await conn.execute(stmt)).scalars())
            assert named == await _chunk_ids(storage, "/n.txt")
            assert [str(o.path) for o in (await storage.search(query="narwhal")).observations] == ["/n.txt"]
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_write_between_a_refreshs_two_reads_never_splits_an_entry(self, env_var: str) -> None:
        async with server_storage(env_var) as storage:
            files = {"/a.txt": "apricot body", "/b.txt": "bravo body", "/d/x.txt": "xylophone body"}
            entries = [Entry(path=Path(p), content=c) for p, c in files.items()]
            assert (await storage.write(entries=entries, parents=True)).success
            assert (await storage.rebuild()).success is True
            changed = [
                Entry(path=Path("/a.txt"), content="apricot changed"),
                Entry(path=Path("/d/x.txt"), content="xylophone changed"),
            ]
            assert (await storage.write(entries=changed)).success
            assert (await storage.delete(path=Path("/b.txt"))).success
            rival = sibling(env_var, storage)

            async def rivals() -> None:
                seams.clear("refresh:before-lexical")
                assert (await rival.write(entries=[Entry(path=Path("/a.txt"), content="apricot changed")])).success
                assert (await rival.restore(path=Path("/b.txt"))).success
                assert (await rival.delete(path=Path("/d"))).success

            try:
                with seams.installed("refresh:before-lexical", rivals):
                    assert (await storage.refresh()).success is True
            finally:
                await rival.close()
            delta = max(await _live_epochs(storage))
            docs = storage._host.tables.lex_docs
            for path in ("/a.txt", "/b.txt", "/d/x.txt"):
                entry_id = await _entry_id(storage, path)
                async with storage._host.engine.connect() as conn:
                    stmt = select(docs.c.chunk_id).where(docs.c.entry_id == entry_id, docs.c.epoch == delta)
                    lexical = bool((await conn.execute(stmt)).first())
                grams = await _gram_posted(storage, path, delta)
                assert grams == lexical, path
                if (await _row(storage, path)).encoded:
                    assert grams and lexical, path
            assert (await storage.refresh()).success is True
            assert len(await _segments_of(storage, "/b.txt")) == 1
            assert [str(o.path) for o in (await storage.search(query="apricot")).observations] == ["/a.txt"]
            assert (await storage.restore(path=Path("/d"))).success
            assert (await storage.refresh()).success is True
            assert [str(o.path) for o in (await storage.search(query="xylophone")).observations] == ["/d/x.txt"]
            assert [str(o.path) for o in (await storage.grep(pattern="xylophone")).observations] == ["/d/x.txt"]
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_heartbeat_inside_the_delta_publish_never_fails_it(self, env_var: str, monkeypatch) -> None:
        async with server_storage(env_var) as storage:
            assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha body")])).success
            assert (await storage.rebuild()).success is True
            assert (await storage.write(entries=[Entry(path=Path("/b.txt"), content="bravo body")])).success
            beater = sibling(env_var, storage)
            publishes = _counted(monkeypatch, "publish_delta")
            real_flip = indexing._flip_flags

            async def beaten(session: Any, *args: Any, assignments: dict[str, Any], **stamp: Any) -> None:
                await real_flip(session, *args, assignments=assignments, **stamp)
                if assignments == {"encoded": True}:
                    await _beat(beater)

            monkeypatch.setattr(indexing, "_flip_flags", beaten)
            try:
                result = await storage.refresh()
            finally:
                await beater.close()
            assert result.success is True, result.errors
            assert len(publishes) == 1
            assert (await _row(storage, "/b.txt")).encoded is True


async def _noop() -> None:
    return None


async def _lock_waiting(watcher: DatabaseStorage, engine: str, session_id: int) -> None:
    """Return once the server reports *session_id* waiting on a row lock, read on *watcher*'s own connection."""
    query = text(_LOCK_WAIT[engine])
    async with watcher._host.engine.connect() as conn:
        while not (await conn.execute(query, {"id": session_id})).scalar_one():
            await conn.rollback()  # each poll reads the server's live lock table, never a held snapshot


async def _arrived(event: asyncio.Event, *running: asyncio.Task[Any]) -> None:
    """Wait for *event*; fail at once, never hang, when a task in *running* ends before it is set."""
    waiter = asyncio.ensure_future(event.wait())
    done, _pending = await asyncio.wait({waiter, *running}, return_when=asyncio.FIRST_COMPLETED)
    if waiter not in done:
        waiter.cancel()
        ended = [task.result() for task in running if task.done()]
        raise AssertionError(f"a run ended before it reached its seam: {ended}")


def _refreshing_once(rival: DatabaseStorage) -> tuple[list[int], Any]:
    """A seam handler counting its arrivals that runs one refresh on *rival* at the first; the count."""
    seen: list[int] = []

    async def refreshed_once() -> None:
        seen.append(len(seen))
        if len(seen) == 1:
            assert (await rival.refresh()).success is True

    return seen, refreshed_once


def _written_once(storage: DatabaseStorage, name: str, entries: list[Entry]) -> Any:
    """A seam handler that uninstalls itself and writes *entries* through *storage*."""

    async def written() -> None:
        seams.clear(name)
        assert (await storage.write(entries=entries)).success

    return written


async def _gram_rows(storage: DatabaseStorage) -> list[int]:
    epochs = storage._host.tables.gram_epochs
    async with storage._host.engine.connect() as conn:
        return sorted((await conn.execute(select(epochs.c.epoch))).scalars())


# ---------------------------------------------------------------------------
# Rights at the commit point — genuine rivals inside a mutation's window
# ---------------------------------------------------------------------------


async def _liveness(storage: DatabaseStorage) -> dict[str, bool]:
    """Every row's path and whether it is live: the world as the system actor reads it."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        found = await session.execute(select(entry.c.path, entry.c.deleted_at))
        return {row.path: row.deleted_at is None for row in found}


def _kinds_and_paths(result: Result) -> list[tuple[str, str | None]]:
    return [(error.kind, error.path) for error in result.errors]


# The seam each topology verb's rival commits at: after the collection, before the act.
_TOPOLOGY_SEAMS = {
    "delete": "delete:post-collect",
    "move": "transfer:post-collect",
    "sweep": "purge:post-collect",
    "copy": "transfer:post-snapshot",
}


def _snapshot_writes(storage: DatabaseStorage) -> bool:
    """Whether the profile pins a repeatable snapshot for writes, so a write's commit point is its first statement."""
    return storage._host.profile.op_isolation is not None


class _Change(NamedTuple):
    """Where a rival changes everyone's posture, the file a write creates, and every row that write mints."""

    posture: str
    target: str
    minted: tuple[str, ...]


# At the created path, at a directory the same write creates, and at the existing parent the write bumps.
_CHANGES = {
    "at-path": _Change("/p/new.txt", "/p/new.txt", ("/p/new.txt",)),
    "at-minted-parent": _Change("/p/n", "/p/n/new.txt", ("/p/n", "/p/n/new.txt")),
    "at-existing-parent": _Change("/p", "/p/new.txt", ("/p/new.txt",)),
}

# The writer granted read_write on /p by name, and the system actor, which no fence runs over.
_MINTERS: dict[str, Authority | None] = {"granted": BOB, "system": None}

# Before the label read, where a snapshot engine's window opens, and after it, where every engine's does.
_MINT_SEAMS = ("write:before-apply", "write:after-labels")

# A member of a group that holds nothing at /p: refused there exactly as a caller with no grant is.
DAVE = Authority.of(Principal("dave"))

# Every row a transfer of /p/d into /p/q creates or moves, and the file a reader is refused.
_TRANSFERRED = ("/p/q/d", "/p/q/d/f.txt", "/p/q/d/sub", "/p/q/d/sub/g.txt")
_TRANSFERRED_FILE = "/p/q/d/f.txt"

# What a mint that lost to a posture change may answer: refused where it now may not write, or a retryable conflict.
_REFUSED_MINT = frozenset({(ErrorKind.permission_denied, False), (ErrorKind.conflict, True)})


async def _relabel_marks(storage: DatabaseStorage) -> int:
    """How many relabels stand in flight: zero once every posture change has settled."""
    relabels = storage._host.tables.relabels
    async with storage._host.session_factory() as session:
        return int((await session.execute(select(func.count()).select_from(relabels))).scalar_one())


async def _standing_labels(storage: DatabaseStorage, paths: tuple[str, ...]) -> dict[str, int]:
    """The everyone level the posture rows as they now stand give each of *paths*."""
    host = storage._host
    async with host.session_factory() as session:
        return await labels_for(session, host.tables, host.profile, host.membership_budget, paths)


async def _stored_labels(storage: DatabaseStorage, paths: tuple[str, ...]) -> dict[str, int | None]:
    """The everyone level each of *paths*' rows carries, ``None`` where no row stands."""
    rows = {path: await row_at(storage, path) for path in paths}
    return {path: None if row is None else row["everyone_level"] for path, row in rows.items()}


async def _minted_under_the_standing_posture(
    storage: DatabaseStorage, result: Result, minted: tuple[str, ...], target: str, level: int
) -> bool:
    """Whether *result* minted: refused lawfully and left no row, or every row carries the standing posture's label."""
    leg = storage._host.profile.name
    assert await _relabel_marks(storage) == 0
    standing = await _standing_labels(storage, minted)
    assert standing == dict.fromkeys(minted, level), standing
    stored = await _stored_labels(storage, minted)
    if stored[target] is None:
        assert result.success is False
        assert {(error.kind, error.retryable) for error in result.errors} <= _REFUSED_MINT, result.errors
        assert all(label is None for label in stored.values()), stored
        return False
    assert result.success is True, result.errors
    assert stored == standing, f"{leg}: stored labels {stored}, standing posture {standing}"
    return True


async def _hidden_from(storage: DatabaseStorage, reader: Authority, target: str, minted: tuple[str, ...]) -> None:
    """*reader* is refused *target* and finds none of *minted* by glob or grep under ``/p``."""
    leg = storage._host.profile.name
    read = await storage.read(path=Path(target), authority=reader)
    assert read.success is False, f"{leg}: {reader} read {target}"
    globbed = await storage.glob(patterns=("/p/**",), authority=reader)
    found = await storage.grep(pattern="minted probe", globs=("/p/**",), allow_scan=True, authority=reader)
    # Anonymous is refused a scope everyone holds nothing at; that refusal hides the row too.
    hidden = {ErrorKind.not_found, ErrorKind.unauthenticated}
    assert {error.kind for error in (*globbed.errors, *found.errors)} <= hidden, globbed.errors
    seen = {str(row.path) for row in (*globbed.observations, *found.observations)}
    assert not seen & set(minted), f"{leg}: {reader} found {sorted(seen & set(minted))}"


class TestRightsAtCommit:
    """A mutation's rows and rights as they stand at its commit point, against a genuine committed rival."""

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_create_that_lands_on_another_owners_row_is_refused_below_contribute(self, env_var: str) -> None:
        """A rival's row committed before bob's insert is changed by bob only if he could change it directly."""
        async with server_storage(env_var, posture="none") as storage:
            await drop_world(storage)
            x = Path("/drop/x.txt")
            alices, bobs = [Entry(path=x, content="alice")], [Entry(path=x, content="bob")]
            rival = partial(storage.write, entries=alices, authority=ALICE)
            handler, rivals = _self_clearing("write:before-apply", rival)
            with seams.installed("write:before-apply", handler):
                result = await storage.write(entries=bobs, authority=BOB)
            assert rivals and rivals[0].success is True
            assert result.success is False
            assert _kinds_and_paths(result) == [(ErrorKind.permission_denied, "/drop/x.txt")]
            row = await row_at(storage, "/drop/x.txt")
            assert row is not None and (row["owner_id"], row["version"], row["content"]) == ("alice", 1, "alice")
            assert await version_count(storage, row["entry_id"]) == 0
            assert (await storage.read(path=Path("/drop/x.txt"), authority=BOB)).one().content == "alice"
            await _audit(storage)

    @pytest.mark.parametrize("verb", ["write", "edit", "edit-matching"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_row_that_appears_before_the_plan_reads_is_judged(self, env_var: str, verb: str) -> None:
        """A row committed between the gate's read and the plan's is judged before the plan acts on it.

        The matching edit's rival body holds the text bob's edit replaces, so
        before the fix the edit lands on alice's row; the other edit's does not,
        so it holds the judgment's place ahead of the plan's own errors.
        """
        async with server_storage(env_var, posture="none") as storage:
            await drop_world(storage)
            target = "/drop/x.txt" if verb == "write" else "/drop/b.txt"
            body = "alice text\n" if verb == "edit-matching" else "alice"
            alices = [Entry(path=Path(target), content=body)]

            async def rival() -> Result:
                if verb != "write":
                    assert (await storage.sweep(path=Path(target))).success is True
                return await storage.write(entries=alices, authority=ALICE)

            handler, rivals = _self_clearing("write:before-snapshot", rival)
            with seams.installed("write:before-snapshot", handler):
                if verb == "write":
                    result = await storage.write(entries=[Entry(path=Path(target), content="bob")], authority=BOB)
                else:
                    edit = [EditOperation(old="text", new="edited")]
                    result = await storage.edit(edits=edit, path=Path(target), authority=BOB)
            assert rivals and rivals[0].success is True
            assert result.success is False
            assert _kinds_and_paths(result) == [(ErrorKind.permission_denied, target)]
            row = await row_at(storage, target)
            assert row is not None and (row["owner_id"], row["version"], row["content"]) == ("alice", 1, body)
            await _audit(storage)

    @pytest.mark.parametrize(
        ("verb", "landed"),
        [
            ("delete", "/drop/e/late.txt"),
            ("delete", "/drop/e/sub/late.txt"),
            ("move", "/drop/e/late.txt"),
            ("move", "/drop/e/sub/late.txt"),
            ("sweep", "/drop/e/sub/late.txt"),
            ("copy", "/s/priv/secret.txt"),
        ],
        ids=["delete-1", "delete-2", "move-1", "move-2", "sweep-2", "copy"],
    )
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_row_landed_beneath_a_topology_root_is_never_acted_on_unjudged(
        self, env_var: str, verb: str, landed: str
    ) -> None:
        """A row alice commits beneath eve's root after the gate is never deleted, moved, purged or copied by eve."""
        async with server_storage(env_var, posture="none") as storage:
            await (copy_world if verb == "copy" else drop_world)(storage)
            seam_name = _TOPOLOGY_SEAMS[verb]
            alices = [Entry(path=Path(landed), content="alice")]
            handler, rivals = _self_clearing(seam_name, partial(storage.write, entries=alices, authority=ALICE))
            eves = await _liveness(storage)
            with seams.installed(seam_name, handler):
                if verb == "delete":
                    result = await storage.delete(path=Path("/drop/e"), authority=EVE)
                elif verb == "sweep":
                    result = await storage.sweep(path=Path("/drop/e"), authority=EVE)
                elif verb == "move":
                    moved = [ResolvedPair(src=Path("/drop/e"), dest=Path("/drop/f"))]
                    result = await storage.move(operations=moved, authority=EVE)
                else:
                    copied = [ResolvedPair(src=Path("/s"), dest=Path("/t/s"))]
                    result = await storage.copy(operations=copied, authority=EVE)
            assert rivals and rivals[0].success is True
            assert result.success is False
            assert _kinds_and_paths(result) == [(ErrorKind.permission_denied, "/s" if verb == "copy" else "/drop/e")]
            row = await row_at(storage, landed)
            assert row is not None and (row["owner_id"], row["version"], row["deleted_at"]) == ("alice", 1, None)
            after = await _liveness(storage)
            assert {path: live for path, live in after.items() if path in eves} == eves
            if verb == "copy":
                assert await paths_under(storage, "/t/s") == set()
            await _audit(storage)

    @pytest.mark.parametrize("shape", ["copy", "move", "open-copy", "full-chunk"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_transfer_is_refused_where_a_direct_write_is(self, env_var: str, shape: str, monkeypatch) -> None:
        """A transfer creates beneath its destination only what eve's direct write of each path there could create.

        The full-chunk node runs one probe of ``arm_budget`` arms, 200 on
        every pinned profile, on the engine itself.
        """
        async with server_storage(env_var, posture="none") as storage:
            pair = [ResolvedPair(src=Path("/src"), dest=Path("/dst/c"))]
            if shape == "full-chunk":
                entries = [Entry(path=Path(f"/src/d{n % 10}/f{n}.txt"), content="f") for n in range(10_000)]
                entries.append(Entry(path=Path("/dst"), kind="directory"))
                assert (await storage.write(entries=entries, parents=True)).success is True
                rules: list[tuple[str, Posture]] = [("/", "none"), ("/src", "read_write"), ("/dst", "add")]
                rules.append(("/dst/c/d0", "none"))
                rules += [(f"/dst/c/x{n:03}", "none") for n in range(99)]
                for path, level in rules:
                    assert (await storage.set_posture(path=Path(path), posture=level)).success is True
                recorded: list[str] = []
                counts: list[int] = []
                listen = storage._host.engine.sync_engine

                def record(conn, cursor, statement, parameters, context, executemany) -> None:
                    recorded.append(statement)

                original = backend_module.admit_destinations

                async def counted(*args: Any, **kwargs: Any) -> Any:
                    start = len(recorded)
                    try:
                        return await original(*args, **kwargs)
                    finally:
                        counts.append(len(recorded) - start)

                monkeypatch.setattr(backend_module, "admit_destinations", counted)
                sqlalchemy_event.listen(listen, "before_cursor_execute", record)
                try:
                    copied = await storage.copy(operations=pair, authority=EVE)
                    results = [copied, await storage.move(operations=pair, authority=EVE)]
                finally:
                    sqlalchemy_event.remove(listen, "before_cursor_execute", record)
                refused = [(ErrorKind.permission_denied, "/dst/c/d0")]
                assert [_kinds_and_paths(result) for result in results] == [refused, refused]
                assert counts == [4, 4]
                await _audit(storage)
                return
            await dest_world(storage)
            if shape == "open-copy":
                assert (await storage.set_posture(path=Path("/dst/c/sub"), posture="add")).success is True
            before = await _liveness(storage)
            if shape == "move":
                result = await storage.move(operations=pair, authority=EVE)
            else:
                result = await storage.copy(operations=pair, authority=EVE)
            if shape == "open-copy":
                assert result.success is True, result.errors
                assert await row_at(storage, "/dst/c/sub/f.txt") is not None
            else:
                assert result.success is False
                assert _kinds_and_paths(result) == [(ErrorKind.permission_denied, "/dst/c/sub")]
                assert await paths_under(storage, "/dst") == {"/dst"}
                assert await _liveness(storage) == before
            await _audit(storage)

    @pytest.mark.parametrize("verb", ["write", "delete", "move", "copy", "sweep"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_revoke_committed_inside_the_window_is_seen(self, env_var: str, verb: str) -> None:
        """A revoke of bob committed inside his call's window is seen: the call answers from the later rights.

        Where a write's commit point is its snapshot (a pinned
        ``op_isolation``), the write is ordered before the revoke and stands.
        """
        async with server_storage(env_var, posture="none") as storage:
            await grant_world(storage)
            before = await _liveness(storage)
            seam_name, call = _grant_world_calls(storage)[verb]
            handler, rivals = _self_clearing(seam_name, lambda: storage.revoke(path=Path("/g"), principal="bob"))
            with seams.installed(seam_name, handler):
                result = await call()
            assert rivals and rivals[0].success is True
            if verb == "write" and _snapshot_writes(storage):
                assert result.success is True, result.errors
                assert await row_at(storage, "/g/new.txt") is not None
            else:
                again = await call()
                assert result.success is False
                assert _kinds_and_paths(result) == _kinds_and_paths(again)
                assert await _liveness(storage) == before
            await _audit(storage)

    @pytest.mark.parametrize("verb", ["write", "delete", "move"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_posture_tightening_committed_inside_the_window_is_seen(self, env_var: str, verb: str) -> None:
        """A posture tightened under eve's call and relabelled to its end is seen; a new row's label is not asserted.

        The same refusal on every engine, for two reasons. Where each
        statement reads the latest commit, the fence finds everyone stamped
        and the call redrives. Where a write's commit point is its snapshot
        (Postgres, MariaDB), the relabel rewrote the row of ``/p`` the write
        bumps, so the engine refuses the bump and the write redrives too.
        """
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            before = await _liveness(storage)
            seam_name = "write:before-apply" if verb == "write" else _TOPOLOGY_SEAMS[verb]
            handler, rivals = _self_clearing(seam_name, lambda: storage.set_posture(path=Path("/p"), posture="read"))
            with seams.installed(seam_name, handler):
                if verb == "write":
                    result = await storage.write(entries=[Entry(path=Path("/p/new.txt"), content="n")], authority=EVE)
                elif verb == "delete":
                    result = await storage.delete(path=Path("/p/d"), authority=EVE)
                else:
                    moved = [ResolvedPair(src=Path("/p/d"), dest=Path("/p/m"))]
                    result = await storage.move(operations=moved, authority=EVE)
            assert rivals and rivals[0].success is True
            expected = {"write": ["/p/new.txt"], "delete": ["/p/d"], "move": ["/p/d", "/p/m"]}[verb]
            assert result.success is False
            assert sorted(error.path or "" for error in result.errors) == expected
            assert {error.kind for error in result.errors} == {ErrorKind.permission_denied}
            assert await _liveness(storage) == before
            await _audit(storage)

    @pytest.mark.parametrize("minter", list(_MINTERS))
    @pytest.mark.parametrize("shape", list(_CHANGES))
    @pytest.mark.parametrize("seam", _MINT_SEAMS)
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_row_minted_across_a_posture_tightening_is_no_more_open_than_the_standing_posture(
        self, env_var: str, seam: str, shape: str, minter: str
    ) -> None:
        """A posture tightened and relabelled inside a write's window leaves no row the write mints more open than it.

        Once the relabel settles, readers trust each row's stored label and
        nothing rewrites it. So the write is refused, or every row it mints
        carries the label the standing posture gives and stays hidden from a
        caller holding nothing there, a group's member and anonymous included.
        """
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
            assert (await storage.add_member(group="group:eng", member="dave", authority=SYSTEM)).success is True
            change = _CHANGES[shape]
            second = sibling(env_var, storage)
            handler, rivals = _self_clearing(
                seam, lambda: second.set_posture(path=Path(change.posture), posture="none")
            )
            written = [Entry(path=Path(change.target), content="minted probe\n")]
            try:
                with seams.installed(seam, handler):
                    result = await storage.write(entries=written, parents=True, authority=_MINTERS[minter])
            finally:
                await second.close()
            assert rivals and rivals[0].success is True, rivals[0].errors if rivals else "the rival never ran"
            none = LEVEL_RANK["none"]
            if await _minted_under_the_standing_posture(storage, result, change.minted, change.target, none):
                control = await storage.grep(pattern="minted probe", allow_scan=True)
                assert {str(row.path) for row in control.observations} == {change.target}
                for reader in (CAROL, DAVE, ANONYMOUS):
                    await _hidden_from(storage, reader, change.target, change.minted)
            await _audit(storage)

    @pytest.mark.parametrize("minter", list(_MINTERS))
    @pytest.mark.parametrize("shape", list(_CHANGES))
    @pytest.mark.parametrize("seam", _MINT_SEAMS)
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_row_minted_across_a_posture_loosening_is_no_more_closed_than_the_standing_posture(
        self, env_var: str, seam: str, shape: str, minter: str
    ) -> None:
        """A posture loosened and relabelled inside a write's window leaves no row the write mints hidden from it.

        The other direction of the same property: a row stamped with the old,
        closed label stays invisible to every caller the standing posture admits.
        """
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.set_posture(path=Path("/p"), posture="none")).success is True
            assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
            change = _CHANGES[shape]
            second = sibling(env_var, storage)
            rival = partial(second.set_posture, path=Path(change.posture), posture="read_write")
            handler, rivals = _self_clearing(seam, rival)
            written = [Entry(path=Path(change.target), content="minted probe\n")]
            try:
                with seams.installed(seam, handler):
                    result = await storage.write(entries=written, parents=True, authority=_MINTERS[minter])
            finally:
                await second.close()
            assert rivals and rivals[0].success is True, rivals[0].errors if rivals else "the rival never ran"
            open_to_all = LEVEL_RANK["read_write"]
            if await _minted_under_the_standing_posture(storage, result, change.minted, change.target, open_to_all):
                read = await storage.read(path=Path(change.target), authority=CAROL)
                assert read.success is True, read.errors
            await _audit(storage)

    @pytest.mark.parametrize("direction", ["tightening", "loosening"])
    @pytest.mark.parametrize("minter", list(_MINTERS))
    @pytest.mark.parametrize("verb", ["move", "copy"])
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_row_moved_or_copied_across_a_posture_change_carries_the_standing_postures_label(
        self, env_var: str, verb: str, minter: str, direction: str
    ) -> None:
        """A posture changed at a transfer's destination, after the transfer read it, is not outlived by the old label.

        A move restamps the rows it carries and a copy stamps the rows it
        creates, both from the destination's postures as the transfer read them.
        """
        before, after = ("read_write", "none") if direction == "tightening" else ("none", "read_write")
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.mkdir(path=Path("/p/q"), authority=SYSTEM)).success is True
            assert (await storage.set_posture(path=Path("/p/q"), posture=before)).success is True
            assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
            assert (await storage.add_member(group="group:eng", member="dave", authority=SYSTEM)).success is True
            second = sibling(env_var, storage)
            rival = partial(second.set_posture, path=Path("/p/q"), posture=after)
            handler, rivals = _self_clearing("transfer:after-postures", rival)
            pair = ResolvedPair(src=Path("/p/d"), dest=Path("/p/q/d"))
            try:
                with seams.installed("transfer:after-postures", handler):
                    call = storage.move if verb == "move" else storage.copy
                    result = await call(operations=[pair], authority=_MINTERS[minter])
            finally:
                await second.close()
            assert rivals and rivals[0].success is True, rivals[0].errors if rivals else "the rival never ran"
            landed = await _minted_under_the_standing_posture(
                storage, result, _TRANSFERRED, "/p/q/d", LEVEL_RANK[after]
            )
            if landed and direction == "tightening":
                for reader in (CAROL, DAVE, ANONYMOUS):
                    await _hidden_from(storage, reader, _TRANSFERRED_FILE, _TRANSFERRED)
            await _audit(storage)

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_restored_row_carries_the_label_the_standing_posture_gives(self, env_var: str) -> None:
        """A restore stamps no label: the relabel reached the tombstone where it sat, and the row returns with it."""
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.delete(path=Path("/p/d/f.txt"), authority=SYSTEM)).success is True
            assert (await storage.set_posture(path=Path("/p/d"), posture="none")).success is True
            restored = await storage.restore(path=Path("/p/d/f.txt"), authority=SYSTEM)
            none = LEVEL_RANK["none"]
            assert await _minted_under_the_standing_posture(storage, restored, ("/p/d/f.txt",), "/p/d/f.txt", none)
            await _audit(storage)

    @pytest.mark.parametrize("env_var", [leg for leg in ENGINE_LEGS if leg.id in ("postgres", "mariadb", "oracle")])
    async def test_only_a_create_waits_while_a_posture_write_is_open(self, env_var: str) -> None:
        """While a posture write stands open, calls that create a row wait for it and nothing else waits for it.

        The posture write is stopped with every lock it takes held. A read by
        each kind of caller, a glob, a grep, a search and a rewrite of an
        existing file each run to their end beside it; the two creates have
        not returned when the last of those has. A waiting create holds its
        parent's row, so a delete of a sibling started behind it waits for
        that create, and returns once the posture write commits. An order of
        returns, never a clock.
        """
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
            sibling_file = Path("/p/old.txt")
            assert (await storage.write(entries=[Entry(path=sibling_file, content="old")])).success is True
            admin, callers = sibling(env_var, storage), sibling(env_var, storage)
            existing, other = Path("/p/d/f.txt"), Path("/p/d/sub/g.txt")
            created = ("/p/new-system.txt", "/p/new-granted.txt")
            creates: list[asyncio.Future[Result]] = []
            returned: list[Result] = []
            still_waiting: list[bool] = []

            async def beside_the_open_posture_write() -> Result:
                for path, minter in zip(created, (None, BOB), strict=True):
                    entries = [Entry(path=Path(path), content="minted probe\n")]
                    creates.append(asyncio.ensure_future(callers.write(entries=entries, authority=minter)))
                returned.extend([await callers.read(path=existing, authority=r) for r in (None, BOB, CAROL, ANONYMOUS)])
                returned.append(await callers.glob(patterns=("/p/**",), authority=BOB))
                returned.append(await callers.grep(pattern="f", allow_scan=True, authority=BOB))
                returned.append(await callers.search(query="minted probe", authority=BOB))
                returned.append(await callers.write(entries=[Entry(path=existing, content="f2")]))
                returned.append(await callers.write(entries=[Entry(path=other, content="g2")], authority=BOB))
                still_waiting.extend(not create.done() for create in creates)
                # Behind the waiting creates: a delete beneath the parent whose row they hold.
                creates.append(asyncio.ensure_future(callers.delete(path=sibling_file, authority=BOB)))
                returned.extend([await callers.read(path=existing, authority=r) for r in (None, BOB, CAROL, ANONYMOUS)])
                still_waiting.append(not creates[-1].done())
                return Result(ops=("set_posture",))

            handler, _ = _self_clearing("posture:after-stamp", beside_the_open_posture_write)
            try:
                with seams.installed("posture:after-stamp", handler):
                    changed = await admin.set_posture(path=other.parent_dir, posture="read")
                *minted, deleted = await asyncio.gather(*creates)
            finally:
                await admin.close()
                await callers.close()
            assert changed.success is True, changed.errors
            assert [result.success for result in returned] == [True] * 13, [r.errors for r in returned]
            assert still_waiting == [True, True, True]
            assert [result.success for result in minted] == [True, True], [r.errors for r in minted]
            assert deleted.success is True, deleted.errors
            assert await _relabel_marks(storage) == 0
            assert await _stored_labels(storage, created) == await _standing_labels(storage, created)
            await _audit(storage)

    @pytest.mark.slow
    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_mints_posture_writes_relabel_chunks_and_a_sweep_finish_without_a_deadlock(
        self, env_var: str
    ) -> None:
        """Sixteen writers, three posture writes with their relabels and a sweep run together and none deadlocks.

        A mint's shared stamp lock is the last lock it takes and a posture
        write reads no entry row after it takes the stamp, so neither new
        wait closes a cycle. Outcomes are counted; nothing is timed.
        """
        async with server_storage(env_var, posture="none") as storage:
            await label_world(storage)
            assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
            doomed = [Entry(path=Path(f"/p/doomed/f{i}.txt"), content="x") for i in range(200)]
            assert (await storage.write(entries=doomed, parents=True)).success is True
            assert (await storage.delete(path=Path("/p/doomed"))).success is True
            writers = 16
            handles = [sibling(env_var, storage) for _ in range(writers + 2)]
            outcomes: set[tuple[str, bool]] = set()
            landed: list[bool] = []

            def tally(result: Result) -> None:
                outcomes.update((error.kind, error.retryable) for error in result.errors)

            async def writer(index: int) -> None:
                minter = BOB if index % 2 else None
                for n in range(50):
                    entries = [Entry(path=Path(f"/p/w{index}/f{n}.txt"), content="x")]
                    result = await handles[index].write(entries=entries, parents=True, authority=minter)
                    tally(result)
                    landed.append(result.success)

            async def admin() -> None:
                for level in ("none", "read_write", "none"):
                    await asyncio.sleep(0)
                    tally(await handles[writers].set_posture(path=Path("/p"), posture=level))

            async def sweeper() -> None:
                tally(await handles[writers + 1].sweep(path=Path("/.vfs/trash")))

            # aioodbc runs each driver call on the loop's default executor: more threads than calls in flight.
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(64))
            try:
                await asyncio.gather(*(writer(index) for index in range(writers)), admin(), sweeper())
            finally:
                for handle in handles:
                    await handle.close()
            assert outcomes <= {(ErrorKind.conflict, True)}, outcomes
            # A posture call that lost a chunk leaves its mark for the next call; run what that call would.
            assert (await storage._settled(Result(ops=("set_posture",)))).success is True
            assert await _relabel_marks(storage) == 0
            entry = storage._host.tables.entry
            async with storage._host.session_factory() as session:
                found = await session.execute(
                    select(entry.c.path, entry.c.everyone_level).where(entry.c.path.like("/p/w%"))
                )
                stored = {row.path: row.everyone_level for row in found}
            assert stored == await _standing_labels(storage, tuple(stored))
            # A floor: the run is not one where every mint lost, and every write that landed left its file.
            succeeded = landed.count(True)
            assert succeeded > writers * 50 // 2, succeeded
            assert len([path for path in stored if path.endswith(".txt")]) == succeeded
            await _audit(storage)

    @pytest.mark.parametrize("env_var", [leg for leg in ENGINE_LEGS if leg.id == "mariadb"])
    async def test_the_mariadb_leg_runs_with_snapshot_isolation(self, env_var: str) -> None:
        """The MariaDB leg's server runs with ``innodb_snapshot_isolation`` on, which a write's commit point needs."""
        async with server_storage(env_var) as storage:
            assert (await storage.first_touch()).success is True
            async with storage._host.engine.connect() as conn:
                assert (await conn.execute(text("SELECT @@innodb_snapshot_isolation"))).scalar_one() == 1

    @pytest.mark.parametrize("env_var", ENGINE_LEGS)
    async def test_a_grant_landed_before_an_in_place_refusal_redrives_into_success(
        self, env_var: str, monkeypatch
    ) -> None:
        """A grant committed before an in-place refusal is read by the fence first: the call runs again and succeeds.

        The grant runs on a second handle on the same mount, so the attempt
        count is the copy's alone: the grant's own gate is never counted.
        """
        async with server_storage(env_var, posture="none") as storage:
            await dest_world(storage)
            assert (await storage.write(entries=[Entry(path=Path("/tmp/x"), kind="directory")], parents=True)).success
            assert (await storage.set_posture(path=Path("/tmp"), posture="add")).success is True
            assert (await storage.set_posture(path=Path("/dst/c/in/sub"), posture="none")).success is True
            second = sibling(env_var, storage)
            sessions = attempts(monkeypatch, storage)
            fired: list[int] = []
            granted: list[Result] = []

            async def rival() -> None:
                fired.append(len(sessions))
                if fired == [1, 1]:
                    granted.append(await second.grant(path=Path("/dst/c/in/sub"), principal="eve", level="add"))

            grown = [
                ResolvedPair(src=Path("/src"), dest=Path("/tmp/x/in")),
                ResolvedPair(src=Path("/tmp/x"), dest=Path("/dst/c")),
            ]
            try:
                with seams.installed("transfer:post-collect", rival):
                    result = await storage.copy(operations=grown, authority=EVE)
            finally:
                await second.close()
            assert granted and granted[0].success is True
            assert result.success is True, result.errors
            assert len(sessions) == 2
            row = await row_at(storage, "/dst/c/in/sub/f.txt")
            assert row is not None and row["owner_id"] == "eve"
            await _audit(storage)


def _grant_world_calls(storage: DatabaseStorage) -> dict[str, tuple[str, Any]]:
    """bob's call of each verb in the grant world and the seam its rival commits at."""
    written = [Entry(path=Path("/g/new.txt"), content="n")]

    def transfer(op: str, dest: str) -> Any:
        pair = [ResolvedPair(src=Path("/g/d"), dest=Path(dest))]
        return lambda: (storage.move if op == "move" else storage.copy)(operations=pair, authority=BOB)

    return {
        "write": ("write:before-apply", partial(storage.write, entries=written, authority=BOB)),
        "delete": ("delete:post-collect", lambda: storage.delete(path=Path("/g/d"), authority=BOB)),
        "move": ("transfer:post-collect", transfer("move", "/g/e")),
        "copy": ("transfer:post-collect", transfer("copy", "/g/c")),
        "sweep": ("purge:post-collect", lambda: storage.sweep(path=Path("/g/d"), authority=BOB)),
    }
