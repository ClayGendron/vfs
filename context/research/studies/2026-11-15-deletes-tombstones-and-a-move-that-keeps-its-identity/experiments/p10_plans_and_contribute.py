"""Probe 10: SQLite's plan for the real listing statements; the contribute rung at a live and at a deleted path; key order for a generation."""

from __future__ import annotations

import asyncio
import sqlite3

from sqlalchemy import event, text

from probe_common import ALICE, BOB, SYSTEM, make, show
from vfs.models import Entry


async def plans(fs, storage, label: str, call) -> None:  # noqa: ANN001
    captured: list[tuple[str, object]] = []

    def on(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT") and "vfs_entries" in statement:
            captured.append((statement, parameters))

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", on)
    result = await call()
    event.remove(engine, "before_cursor_execute", on)
    print(f"  {label}: rows returned={len(result.observations)}")
    async with storage._host.session_factory() as session:
        conn = await session.connection()
        for statement, parameters in captured:
            where = " ".join(statement.split())
            where = where[where.index(" FROM ") :][:330]
            found = await conn.exec_driver_sql("EXPLAIN QUERY PLAN " + statement, parameters)
            print(f"    statement: ...{where}")
            print(f"    plan: {[row[3] for row in found]}")


async def main() -> None:
    fs, storage = make()
    batch = [Entry(path=f"/dir/live{i:02d}.txt", content="live\n") for i in range(10)]
    batch += [Entry(path=f"/dir/dead{i:04d}.txt", content="dead\n") for i in range(500)]
    batch += [Entry(path=f"/other/f{i:04d}.txt", content="x\n") for i in range(500)]
    assert not (await fs.write(batch, parents=True, authority=ALICE)).errors
    dead = (await fs.glob("/dir/dead*", authority=SYSTEM)).observations
    assert not (await fs.delete(observations=list(dead), authority=SYSTEM)).errors
    async with storage._host.session_factory() as session:
        await session.execute(text("ANALYZE"))
        await session.commit()
    print("== 1. plans for the real statements (after ANALYZE, so the planner has statistics)")
    await plans(fs, storage, "ls /dir as system", lambda: fs.ls("/dir", authority=SYSTEM))
    await plans(fs, storage, "ls /.vfs/trash as system", lambda: fs.ls("/.vfs/trash", authority=SYSTEM))
    await plans(fs, storage, "ls /.vfs/trash as alice", lambda: fs.ls("/.vfs/trash", authority=ALICE))
    await fs.close()

    print("\n== 2. the contribute rung: overwrite a live file, then write at the same path once it is deleted")
    fs, storage = make()
    await fs.mkdir("/p", authority=SYSTEM)
    await fs.posture("/p", "none", authority=SYSTEM)
    await fs.grant("/p", "alice", "read_write", authority=SYSTEM)
    await fs.grant("/p", "bob", "contribute", authority=SYSTEM)
    await fs.write(path="/p/shared.txt", content="alice v1\n", authority=ALICE)
    show("bob (contribute) overwrites alice's live file", await fs.write(path="/p/shared.txt", content="bob v2\n", authority=BOB))
    show("bob (contribute) edits it", await fs.edit("/p/shared.txt", old="v2", new="v3", authority=BOB))
    show("bob (contribute) deletes it", await fs.delete("/p/shared.txt", authority=BOB))
    show("alice deletes it", await fs.delete("/p/shared.txt", authority=ALICE))
    show("bob (contribute) writes at the deleted path", await fs.write(path="/p/shared.txt", content="bob v4\n", authority=BOB))
    show("bob (contribute) restores it", await fs.restore("/p/shared.txt", authority=BOB))
    await fs.close()

    print("\n== 3. key order for a generation column: which order lets a live listing skip tombstones")
    for order in ("parent_id, name, generation", "parent_id, generation, name"):
        db = sqlite3.connect(":memory:")
        db.execute(f"CREATE TABLE e (id INTEGER PRIMARY KEY, parent_id TEXT, name TEXT, generation INTEGER NOT NULL DEFAULT 0, UNIQUE ({order}))")
        db.executemany("INSERT INTO e (parent_id, name, generation) VALUES ('D', ?, ?)", [(f"dead{i:05d}", i + 1) for i in range(4000)])
        db.executemany("INSERT INTO e (parent_id, name) VALUES ('D', ?)", [(f"live{i:02d}",) for i in range(10)])
        steps = [0]

        def tick(steps=steps) -> int:
            steps[0] += 1
            return 0

        sql = "SELECT name FROM e WHERE parent_id = 'D' AND generation = 0 ORDER BY name"
        plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + sql)]
        db.set_progress_handler(tick, 1)
        rows = db.execute(sql).fetchall()
        db.set_progress_handler(None, 1)
        print(f"  UNIQUE ({order}): rows={len(rows)} vm_steps={steps[0]} plan={plan}")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE e (id INTEGER PRIMARY KEY, parent_id TEXT, name TEXT, deleted_at TEXT)")
    db.execute("CREATE UNIQUE INDEX uq_live ON e (parent_id, name) WHERE deleted_at IS NULL")
    db.executemany("INSERT INTO e (parent_id, name, deleted_at) VALUES ('D', ?, '2026-11-15')", [(f"dead{i:05d}",) for i in range(4000)])
    db.executemany("INSERT INTO e (parent_id, name) VALUES ('D', ?)", [(f"live{i:02d}",) for i in range(10)])
    steps = [0]

    def tick2() -> int:
        steps[0] += 1
        return 0

    sql = "SELECT name FROM e WHERE parent_id = 'D' AND deleted_at IS NULL ORDER BY name"
    plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + sql)]
    db.set_progress_handler(tick2, 1)
    rows = db.execute(sql).fetchall()
    db.set_progress_handler(None, 1)
    print(f"  partial UNIQUE (parent_id, name) WHERE deleted_at IS NULL: rows={len(rows)} vm_steps={steps[0]} plan={plan}")


asyncio.run(main())
