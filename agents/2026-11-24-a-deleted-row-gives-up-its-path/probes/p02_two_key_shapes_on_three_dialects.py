"""Probe 02: the two key shapes that let a deleted row give up its name, on SQLite, Postgres and an untuned dialect.

For each engine and each shape it prints the DDL the one declaration compiles to, then runs the sequence
the design needs: delete a file, make a new one at its name, do it again, restore the oldest onto the live
one, and arbitrate a create against a live rival and against a name that holds only deleted rows.
On Postgres it also holds a rival create open and counts what the second create returns.

The generic floor has no engine to run on: the test dialect under ``tests/support/floor_dialect.py`` loses
its SQLite type variants and fails at the first insert. So the floor is shown two ways. The DDL is compiled
for MySQL, a dialect no profile tunes, and the ``live_only`` shape is run on SQLite with its keys built
whole, as that DDL builds them.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path as FsPath

from sqlalchemy import MetaData, func, insert, select, text, update
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateIndex

sys.path.insert(0, str(FsPath(__file__).parent))

from harness import LIVE, POSTGRES_URL, SQLITE_URL, entries

SHAPES = ("live_only", "generation")


def values(n: int, **more: object) -> dict[str, object]:
    return {"entry_id": f"E{n:025d}", "parent_id": "D" * 26, "path": "/d/f", "name": "f", "kind": "file", **more}


async def attempt(conn, label: str, statement, *, counted: bool = False) -> str:
    try:
        async with conn.begin_nested():
            result = await conn.execute(statement)
            rows = result.fetchall() if counted else None
    except DBAPIError as exc:
        outcome = f"refused: {type(exc.orig).__name__ if exc.orig else type(exc).__name__}"
    else:
        outcome = "ok" if rows is None else f"ok, {len(rows)} row(s) returned"
    print(f"    {label}: {outcome}")
    return outcome


async def run(dialect: str, url: str, shape: str, *, whole: bool = False) -> None:
    engine = create_async_engine(url)
    meta = MetaData()
    table = entries(meta, shape, name=f"probe_{shape}")
    if whole:
        for index in table.indexes:
            index.dialect_options["sqlite"]["where"] = None
    tombstone: dict[str, object] = {"deleted_at": datetime.now(UTC), "trash_root_id": table.c.entry_id}
    revive: dict[str, object] = {"deleted_at": None, "trash_root_id": None}
    if shape == "generation":
        tombstone["name_generation"] = table.c.id
        revive["name_generation"] = 0
    upsert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    target = (
        {"index_elements": ["parent_id", "name"], "index_where": LIVE}
        if shape == "live_only"
        else {"index_elements": ["parent_id", "name_generation", "name"]}
    )
    by_id = lambda n: table.c.entry_id == values(n)["entry_id"]  # noqa: E731
    print(f"\n== {dialect}, shape {shape}")
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
        await conn.run_sync(meta.create_all)
        for constraint in sorted(table.constraints, key=lambda c: str(c.name)):
            if constraint.name and str(constraint.name).startswith(("uq_", "ck_")):
                print(f"    declared in the table: {constraint.name}")
        for index in sorted(table.indexes, key=lambda i: str(i.name)):
            ddl = " ".join(str(CreateIndex(index).compile(dialect=engine.dialect)).split())
            if "uq_" in ddl or "trashed" in ddl:
                print(f"    {ddl}")
            if "uq_" in ddl and not whole:
                untuned = " ".join(str(CreateIndex(index).compile(dialect=mysql.dialect())).split())
                print(f"      as an untuned dialect compiles it: {untuned}")
        await conn.execute(insert(table).values(entry_id="D" * 26, path="/d", name="d", kind="directory"))
        await attempt(conn, "create /d/f (entry 1)", insert(table).values(values(1)))
        await attempt(conn, "delete entry 1", update(table).where(by_id(1)).values(tombstone))
        again = insert(table).values(values(2))
        await attempt(conn, "create /d/f again (entry 2), the name holding one deleted row", again)
        await attempt(conn, "delete entry 2", update(table).where(by_id(2)).values(tombstone))
        await attempt(conn, "create /d/f a third time (entry 3)", insert(table).values(values(3)))
        at_path = select(func.count()).select_from(table).where(table.c.path == "/d/f")
        total = (await conn.execute(at_path)).scalar()
        live = (await conn.execute(at_path.where(LIVE))).scalar()
        print(f"    rows at /d/f: {total}, live: {live}")
        await attempt(conn, "restore entry 1 while entry 3 is live", update(table).where(by_id(1)).values(revive))
        if not whole:
            arbitrated = upsert(table).values(values(4)).on_conflict_do_nothing(**target).returning(table.c.entry_id)
            await attempt(conn, "arbitrated create against the live entry 3", arbitrated, counted=True)
            await attempt(conn, "delete entry 3", update(table).where(by_id(3)).values(tombstone))
            label = "arbitrated create at the name holding three deleted rows"
            await attempt(conn, label, arbitrated, counted=True)
            if shape == "live_only":
                bare = upsert(table).values(values(5)).on_conflict_do_nothing(index_elements=["parent_id", "name"])
                await attempt(conn, "the tree's conflict target as written today, with no predicate", bare)
    if engine.dialect.name == "postgresql":
        await rivals(engine, table, upsert, target)
    await engine.dispose()


async def rivals(engine, table, upsert, target) -> None:
    """One create held open, a second arriving behind it: what the second waits for and what it returns."""
    row = {"entry_id": "G" * 26, "parent_id": "D" * 26, "path": "/d/g", "name": "g", "kind": "file"}
    rival = {**row, "entry_id": "H" * 26}
    first = await engine.connect()
    second = await engine.connect()
    await first.execute(insert(table).values(row))
    arbitrated = upsert(table).values(rival).on_conflict_do_nothing(**target).returning(table.c.entry_id)
    pending = asyncio.ensure_future(second.execute(arbitrated))
    await asyncio.sleep(0.5)
    waited = not pending.done()
    await first.commit()
    returned = len((await pending).fetchall())
    await second.commit()
    live_at = select(func.count()).select_from(table).where(table.c.path == "/d/g", LIVE)
    async with engine.connect() as conn:
        live = (await conn.execute(live_at)).scalar()
        level = (await conn.execute(text("SHOW transaction_isolation"))).scalar()
    print(
        f"    two creates of /d/g at {level}: the second waited={waited}, returned {returned} row(s);"
        f" live rows at /d/g: {live}"
    )
    await first.close()
    await second.close()


async def main() -> None:
    legs = [("SQLite", SQLITE_URL)]
    if POSTGRES_URL:
        legs.append(("Postgres", POSTGRES_URL))
    else:
        print("VFS_PROBE_POSTGRES_URL is unset: the Postgres leg is skipped")
    for dialect, url in legs:
        for shape in SHAPES:
            await run(dialect, url, shape)
    whole = "SQLite with the live_only keys built whole, as an untuned dialect builds them"
    await run(whole, SQLITE_URL, "live_only", whole=True)


asyncio.run(main())
