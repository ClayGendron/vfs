"""Probe 07: what the entry table's keys say about tombstones, and what a listing of a directory full of tombstones costs.

Cost is counted, never timed: SQLite's progress handler fires once per
virtual-machine instruction, so the count is the work the statement did.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from probe_common import ALICE, SYSTEM, StatementCounter, make
from vfs.models import Entry


class Steps:
    def __init__(self) -> None:
        self.count = 0

    def tick(self) -> int:
        self.count += 1
        return 0


async def driver_connection(storage):  # noqa: ANN001, ANN201
    async with storage._host.session_factory() as session:
        conn = await session.connection()
        raw = await conn.get_raw_connection()
        return raw.driver_connection


async def counted(storage, label: str, call) -> None:  # noqa: ANN001
    steps = Steps()
    driver = await driver_connection(storage)
    await driver.set_progress_handler(steps.tick, 1)
    with StatementCounter(storage) as counter:
        result = await call()
    await driver.set_progress_handler(None, 1)
    assert not result.errors, result.errors
    print(f"  {label}: rows returned={len(result.observations)} statements={counter.statements} vm_steps={steps.count}")
    return counter


async def main() -> None:
    fs, storage = make()
    await fs.stat("/", authority=SYSTEM)  # first touch provisions the tables
    print("== 1. the keys and indexes on vfs_entries, as SQLite holds them")
    async with storage._host.session_factory() as session:
        for row in await session.execute(text("SELECT name, sql FROM sqlite_master WHERE tbl_name='vfs_entries' ORDER BY name")):
            if row.sql is None:
                print(f"  {row.name}: (automatic index for a UNIQUE constraint)")
            elif row.name == "vfs_entries":
                for line in row.sql.splitlines():
                    if "UNIQUE" in line or "CONSTRAINT" in line or "PRIMARY" in line:
                        print(f"  table: {line.strip()}")
            else:
                print(f"  {row.sql}")
        for row in await session.execute(text("PRAGMA index_list('vfs_entries')")):
            print(f"  index_list: name={row.name} unique={row.unique} origin={row.origin} partial={row.partial}")

    print("\n== 2. a listing of a directory holding 10 live files and N tombstones")
    for dead in (0, 1000, 2000, 4000):
        root = f"/dir{dead}"
        batch = [Entry(path=f"{root}/live{i:02d}.txt", content="live\n") for i in range(10)]
        batch += [Entry(path=f"{root}/dead{i:05d}.txt", content="dead\n") for i in range(dead)]
        result = await fs.write(batch, parents=True, authority=ALICE)
        assert not result.errors, result.errors
        if dead:
            targets = (await fs.glob(f"{root}/dead*", authority=SYSTEM)).observations
            result = await fs.delete(observations=list(targets), authority=SYSTEM)
            assert not result.errors, result.errors
        print(f" -- {root}: 10 live, {dead} tombstoned")
        counter = await counted(storage, f"ls {root} as system", lambda root=root: fs.ls(root, authority=SYSTEM))
        await counted(storage, f"ls {root} as alice", lambda root=root: fs.ls(root, authority=ALICE))
        await counted(storage, f"stat {root}/live00.txt", lambda root=root: fs.stat(f"{root}/live00.txt", authority=SYSTEM))
        await counted(storage, f"glob {root}/live* ", lambda root=root: fs.glob(f"{root}/live*", authority=SYSTEM))
        await counted(storage, f"delete {root}/live09.txt cascade=False", lambda root=root: fs.delete(f"{root}/live09.txt", cascade=False, authority=SYSTEM))
        await counted(storage, f"restore {root}/live09.txt", lambda root=root: fs.restore(f"{root}/live09.txt", authority=SYSTEM))
        if dead == 4000:
            print("  the statements of that system ls, with SQLite's plan for each SELECT on vfs_entries:")
            listing = [s for s in counter.samples if s.startswith("SELECT") and "vfs_entries" in s]
            for sample in listing:
                print(f"      {sample}")
    print("\n== 3. the plan SQLite picks for a children listing with the liveness term")
    async with storage._host.session_factory() as session:
        entry_id = (await session.execute(text("SELECT entry_id FROM vfs_entries WHERE path='/dir4000'"))).scalar_one()
        for label, sql in (
            ("children of one parent, live only, by name", "SELECT path FROM vfs_entries WHERE parent_id = :p AND deleted_at IS NULL ORDER BY name LIMIT 50"),
            ("children of one parent, tombstoned only", "SELECT path FROM vfs_entries WHERE parent_id = :p AND deleted_at IS NOT NULL ORDER BY name LIMIT 50"),
            ("every tombstoned root", "SELECT path FROM vfs_entries WHERE trash_root_id = entry_id ORDER BY path LIMIT 50"),
            ("every tombstoned root, as the retention sweep asks", "SELECT path FROM vfs_entries WHERE deleted_at < :cut AND trash_root_id = entry_id ORDER BY path"),
        ):
            params = {"p": entry_id} if ":p" in sql else ({"cut": "2030-01-01"} if ":cut" in sql else {})
            plan = [row[3] for row in await session.execute(text("EXPLAIN QUERY PLAN " + sql), params)]
            print(f"  {label}: {plan}")
    print("\n== 4. the trash view over 7,000 tombstoned roots")
    await counted(storage, "ls /.vfs/trash as system", lambda: fs.ls("/.vfs/trash", authority=SYSTEM))
    await fs.close()


asyncio.run(main())
