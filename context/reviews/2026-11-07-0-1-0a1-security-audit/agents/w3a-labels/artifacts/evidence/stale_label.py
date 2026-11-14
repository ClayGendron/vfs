"""Stale everyone_level at mint: a write/move/copy whose posture read predates a tightening.

SQLite's writer BEGIN IMMEDIATE forbids the real interleaving, so experiment 1
shows that blocker through the real seam, and experiments 2-4 emulate a
REPEATABLE READ (or READ COMMITTED) snapshot read of the posture rows by handing
the mint the labels/postures the real functions computed before the posture commit.
"""

import asyncio
import json
import os
import sys

from sqlalchemy import select

import vfs.storage.backends.database.topology as topology
import vfs.storage.backends.database.writes as writes
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database.labels import labels_for, posture_beneath, rebuild_labels

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))
ANON = Authority.anonymous()
SCRATCH = os.path.dirname(os.path.abspath(__file__))
OUT: dict = {}


def errs(result):
    return [(e.kind.value if hasattr(e.kind, "value") else str(e.kind), e.message[:200]) for e in result.errors]


async def fresh(name: str) -> DatabaseStorage:
    db = os.path.join(SCRATCH, f"{name}.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db + suffix):
            os.remove(db + suffix)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}", name=name)
    assert (await storage.posture(path=Path("/"), posture="read", authority=SYSTEM)).success
    assert (await storage.mkdir(path=Path("/eng"), parents=True, authority=SYSTEM)).success
    assert (await storage.mkdir(path=Path("/tmp"), parents=True, authority=SYSTEM)).success
    assert (await storage.grant(path=Path("/"), principal="alice", level="read_write", authority=SYSTEM)).success
    return storage


async def state(storage: DatabaseStorage, path: str) -> dict:
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        marks = [r.path_prefix for r in await session.execute(select(tables.relabels.c.path_prefix))]
        row = (
            await session.execute(
                select(tables.entry.c.everyone_level, tables.entry.c.owner_id).where(tables.entry.c.path == path)
            )
        ).first()
        postures = {
            r.path_prefix: r.level
            for r in await session.execute(
                select(tables.grants.c.path_prefix, tables.grants.c.level).where(tables.grants.c.principal_id == "*")
            )
        }
    return {
        "pending_relabel_marks": marks,
        "row_everyone_level": None if row is None else row.everyone_level,
        "row_owner": None if row is None else row.owner_id,
        "everyone_postures": postures,
    }


async def probes(storage: DatabaseStorage, path: str) -> dict:
    bob_read = await storage.read(path=Path(path), authority=BOB)
    anon_read = await storage.read(path=Path(path), authority=ANON)
    anon_grep = await storage.grep(pattern="TOPSECRET", allow_scan=True, authority=ANON)
    bob_grep = await storage.grep(pattern="TOPSECRET", allow_scan=True, authority=BOB)
    anon_glob = await storage.glob(patterns=("/eng/**",), authority=ANON)
    bob_edit = await storage.write(entries=[Entry(path=Path(path), content="bob overwrote")], authority=BOB)
    return {
        "bob_read_success": bob_read.success,
        "bob_read_content": [getattr(o, "content", None) for o in bob_read.observations],
        "bob_read_errors": errs(bob_read),
        "anon_read_success": anon_read.success,
        "anon_read_errors": errs(anon_read),
        "anon_grep_paths": sorted({str(o.path) for o in anon_grep.observations}),
        "anon_grep_errors": errs(anon_grep),
        "bob_grep_paths": sorted({str(o.path) for o in bob_grep.observations}),
        "anon_glob_paths": sorted({str(o.path) for o in anon_glob.observations}),
        "bob_overwrite_success": bob_edit.success,
        "bob_overwrite_errors": errs(bob_edit),
    }


async def tighten(storage: DatabaseStorage, path: str) -> dict:
    result = await storage.posture(path=Path(path), posture="none", authority=SYSTEM)
    extra = result.model_extra or {}
    return {"success": result.success, "relabel": extra.get("relabel"), "errors": errs(result)}


async def exp1_sqlite_blocks_the_interleaving() -> None:
    """The real seam: a posture commit staged inside a write's window cannot take SQLite's write lock."""
    storage = await fresh("exp1")
    rival: list = []

    async def handler() -> None:
        seams.clear("write:before-apply")
        rival.append(await asyncio.wait_for(tighten(storage, "/eng/secret.md"), timeout=40))

    with seams.installed("write:before-apply", handler):
        try:
            victim = await storage.write(
                entries=[Entry(path=Path("/eng/secret.md"), content="TOPSECRET payroll")], authority=ALICE
            )
            victim_out = {"success": victim.success, "errors": errs(victim)}
        except Exception as exc:  # noqa: BLE001
            victim_out = {"raised": repr(exc)[:300]}
            if not rival:
                rival.append({"raised": "handler timed out or raised"})
    OUT["exp1_sqlite_seam"] = {
        "rival_posture_inside_write_window": rival,
        "victim_write": victim_out,
        "after": await state(storage, "/eng/secret.md"),
    }
    await storage.close()


async def exp2_write_with_presnapshot_labels(control: bool) -> None:
    key = "exp2_control_fresh_labels" if control else "exp2_write_presnapshot_labels"
    storage = await fresh("exp2c" if control else "exp2")
    host = storage._host
    async with host.session_factory() as session:
        snapshot = await labels_for(session, host.tables, host.profile, host.membership_budget, ["/eng/secret.md"])
    posture = await tighten(storage, "/eng/secret.md")
    after_posture = await state(storage, "/eng/secret.md")
    real = writes.labels_for

    async def stale(session, tables, profile, budget, paths):
        return {p: snapshot[p] for p in paths}

    if not control:
        writes.labels_for = stale
    try:
        written = await storage.write(
            entries=[Entry(path=Path("/eng/secret.md"), content="TOPSECRET payroll")], authority=ALICE
        )
    finally:
        writes.labels_for = real
    OUT[key] = {
        "presnapshot_labels": snapshot,
        "posture_none_result": posture,
        "after_posture_settled": after_posture,
        "write_success": written.success,
        "after_write": await state(storage, "/eng/secret.md"),
        "probes": await probes(storage, "/eng/secret.md"),
    }
    if not control:
        async with host.session_factory() as session:
            await rebuild_labels(session, host.tables, host.profile, host.membership_budget)
            await session.commit()
        OUT[key]["after_rebuild_labels"] = await state(storage, "/eng/secret.md")
        bob = await storage.read(path=Path("/eng/secret.md"), authority=BOB)
        OUT[key]["bob_read_after_rebuild"] = {"success": bob.success, "errors": errs(bob)}
    await storage.close()


async def exp3_transfer_with_presnapshot_postures(op: str) -> None:
    storage = await fresh(f"exp3{op}")
    host = storage._host
    assert (await storage.write(entries=[Entry(path=Path("<tmp>/draft.md"), content="TOPSECRET draft")], authority=ALICE)).success
    async with host.session_factory() as session:
        snapshot = await posture_beneath(session, host.tables, host.profile, host.membership_budget, "/eng/secret.md")
    posture = await tighten(storage, "/eng/secret.md")
    real = topology.posture_beneath

    async def stale(session, tables, profile, budget, root):
        return dict(snapshot)

    topology.posture_beneath = stale
    try:
        pair = ResolvedPair(src=Path("<tmp>/draft.md"), dest=Path("/eng/secret.md"))
        moved = await getattr(storage, op)(operations=[pair], authority=ALICE)
    finally:
        topology.posture_beneath = real
    OUT[f"exp3_{op}_presnapshot_postures"] = {
        "presnapshot_postures": snapshot,
        "posture_none_result": posture,
        "transfer_success": moved.success,
        "transfer_errors": errs(moved),
        "after_transfer": await state(storage, "/eng/secret.md"),
        "probes": await probes(storage, "/eng/secret.md"),
    }
    await storage.close()


async def main() -> None:
    await exp2_write_with_presnapshot_labels(control=True)
    await exp2_write_with_presnapshot_labels(control=False)
    await exp3_transfer_with_presnapshot_postures("move")
    await exp3_transfer_with_presnapshot_postures("copy")
    if "--seam" in sys.argv:
        await exp1_sqlite_blocks_the_interleaving()
    print(json.dumps(OUT, indent=1, default=str))


asyncio.run(main())
