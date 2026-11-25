"""The statements the etag spec quotes, sent to a server by hand at the isolation levels it names, beside a rival.

No vfs code runs here. Two connections act on a small table that has the
columns the guards name (``entry_id``, ``parent_id``, ``name``, ``path``,
``version``, ``deleted_at``) and the two unique indexes the entries table
has. For each case the first connection reads (its snapshot), the second
commits a change, and the first sends the guarded statement. The probe
prints what the server answered: an error and its SQLSTATE, or the rows
the statement matched.

Postgres cases:

1. REPEATABLE READ, the write guard over a ``VALUES`` join, rival bumped the version.
2. REPEATABLE READ, the same guard, rival moved the row (changed its path).
3. REPEATABLE READ, the same guard, the rival committed before the first read.
4. READ COMMITTED, the delete claim, rival bumped the version.
5. READ COMMITTED, the move claim, rival bumped the version while the claim waited on its lock.
6. READ COMMITTED, the restore claim, rival revived the row.
7. REPEATABLE READ, ``ON CONFLICT (parent_id, name) DO NOTHING``, rival created the name inside the window.
8. REPEATABLE READ, ``ON CONFLICT ... DO UPDATE``, the same rival.
9. REPEATABLE READ, ``DO NOTHING``, the name was there before the snapshot.
10. READ COMMITTED, ``DO NOTHING``, rival created the name inside the window.

SQLite cases, with the standard library driver: a second ``BEGIN
IMMEDIATE`` while a writer holds the database, and ``ON CONFLICT DO
NOTHING ... RETURNING`` over a name that is held.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p04_the_quoted_statements_at_each_isolation_level.py
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path as OsPath
from uuid import UUID, uuid4

import asyncpg

from harness import POSTGRES_ENV, run

A = UUID("00000000-0000-7000-8000-00000000000a")
PARENT = UUID("00000000-0000-7000-8000-0000000000ff")

WRITE_GUARD = """
UPDATE {t} SET version = incoming.v_ver
FROM (VALUES ($1::uuid, $2::bigint, $3::bigint, $4::text)) AS incoming (v_id, v_base, v_ver, v_path)
WHERE {t}.entry_id = incoming.v_id AND {t}.path = incoming.v_path
  AND {t}.deleted_at IS NULL AND {t}.version = incoming.v_base
RETURNING {t}.entry_id, {t}.version
"""
DELETE_CLAIM = """
UPDATE {t} SET deleted_at = now(), version = {t}.version + 1
FROM (VALUES ($1::uuid, $2::bigint)) AS incoming (v_id, v_ver)
WHERE {t}.entry_id = incoming.v_id AND {t}.version = incoming.v_ver AND {t}.deleted_at IS NULL
RETURNING {t}.entry_id
"""
MOVE_CLAIM = "UPDATE {t} SET path = '/moved', name = 'moved', version = version + 1 WHERE entry_id = $1 AND version = $2 RETURNING entry_id"
RESTORE_CLAIM = """
UPDATE {t} SET deleted_at = NULL, version = {t}.version + 1
FROM (VALUES ($1::uuid, $2::bigint)) AS incoming (v_id, v_ver)
WHERE {t}.entry_id = incoming.v_id AND {t}.version = incoming.v_ver AND {t}.deleted_at IS NOT NULL
RETURNING {t}.entry_id
"""
CREATE_ONLY = """
INSERT INTO {t} (entry_id, parent_id, name, path, version) VALUES ($1, $2, 'new', '/new', 1)
ON CONFLICT (parent_id, name) DO NOTHING RETURNING entry_id, path, version
"""
CLOBBER = """
INSERT INTO {t} (entry_id, parent_id, name, path, version) VALUES ($1, $2, 'new', '/new', 1)
ON CONFLICT (parent_id, name) DO UPDATE SET version = {t}.version + 1 WHERE {t}.path = excluded.path
RETURNING entry_id, path, version
"""


async def answer(conn: asyncpg.Connection, statement: str, *args: object) -> str:
    try:
        rows = await conn.fetch(statement, *args)
    except asyncpg.PostgresError as exc:
        return f"ERROR {exc.sqlstate}: {exc.message}"
    return f"{len(rows)} row(s) {[tuple(r.values()) for r in rows]}"


async def postgres() -> None:
    dsn = os.environ[POSTGRES_ENV].replace("+asyncpg", "")
    schema = f"vfs_t_{uuid4().hex[:12]}"
    t = f"{schema}.e"
    first = await asyncpg.connect(dsn, timeout=10)
    rival = await asyncpg.connect(dsn, timeout=10)
    await first.execute("SET lock_timeout = '10s'")
    await rival.execute("SET lock_timeout = '10s'")
    version = await first.fetchval("SHOW server_version")
    print(f"server {version}")
    await first.execute(f"CREATE SCHEMA {schema}")
    try:
        await first.execute(
            f"CREATE TABLE {t} (entry_id uuid NOT NULL UNIQUE, parent_id uuid, name text NOT NULL, "
            "path text NOT NULL UNIQUE, version bigint, deleted_at timestamptz, UNIQUE (parent_id, name))"
        )

        async def reset(*, deleted: bool = False) -> None:
            await first.execute(f"TRUNCATE {t}")
            stamp = "now()" if deleted else "NULL"
            await first.execute(
                f"INSERT INTO {t} VALUES ($1, $2, 'a', '/a', 1, {stamp})", A, PARENT
            )

        async def case(label: str, level: str, rival_sql: str, statement: str, *args: object, deleted: bool = False,
                       rival_first: bool = False, rival_args: tuple[object, ...] = ()) -> None:
            await reset(deleted=deleted)
            if rival_first:
                await rival.execute(rival_sql.format(t=t), *rival_args)
            await first.execute(f"BEGIN ISOLATION LEVEL {level}")
            seen = await first.fetch(f"SELECT entry_id, version, path, deleted_at IS NOT NULL FROM {t} ORDER BY path")
            if not rival_first:
                await rival.execute(rival_sql.format(t=t), *rival_args)
            got = await answer(first, statement.format(t=t), *args)
            await first.execute("ROLLBACK")
            print(f"-- {label}\n   {level}; the snapshot saw {len(seen)} row(s) at version {[r[1] for r in seen]}\n   -> {got}")

        bump = "UPDATE {t} SET version = version + 1 WHERE path = '/a'"
        await case("1. the write guard, rival bumped the version", "REPEATABLE READ", bump, WRITE_GUARD, A, 1, 2, "/a")
        await case("2. the write guard, rival moved the row", "REPEATABLE READ",
                   "UPDATE {t} SET path = '/b', name = 'b', version = version + 1 WHERE path = '/a'",
                   WRITE_GUARD, A, 1, 2, "/a")  # fmt: skip
        await case("3. the write guard, the rival committed before the first read", "REPEATABLE READ", bump,
                   WRITE_GUARD, A, 1, 2, "/a", rival_first=True)  # fmt: skip
        await case("4. the delete claim, rival bumped the version", "READ COMMITTED", bump, DELETE_CLAIM, A, 1)

        # 5. The rival holds the row lock while the claim is sent, then commits: the claim waits and re-checks.
        await reset()
        await first.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
        await first.fetch(f"SELECT version FROM {t}")
        await rival.execute("BEGIN")
        await rival.execute(bump.format(t=t))
        waiting = asyncio.create_task(answer(first, MOVE_CLAIM.format(t=t), A, 1))
        await asyncio.sleep(0.3)
        was_waiting = not waiting.done()
        await rival.execute("COMMIT")
        got = await asyncio.wait_for(waiting, 15)
        await first.execute("ROLLBACK")
        print(f"-- 5. the move claim, rival committed while the claim waited (waited: {was_waiting})\n   READ COMMITTED\n   -> {got}")

        await case("6. the restore claim, rival revived the row", "READ COMMITTED",
                   "UPDATE {t} SET deleted_at = NULL, version = version + 1 WHERE path = '/a'",
                   RESTORE_CLAIM, A, 1, deleted=True)  # fmt: skip
        insert_rival = "INSERT INTO {t} VALUES ($1, $2, 'new', '/new', 1, NULL)"
        await case("7. create only (DO NOTHING), rival created the name inside the window", "REPEATABLE READ",
                   insert_rival, CREATE_ONLY, uuid4(), PARENT, rival_args=(uuid4(), PARENT))  # fmt: skip
        await case("8. clobber (DO UPDATE), rival created the name inside the window", "REPEATABLE READ",
                   insert_rival, CLOBBER, uuid4(), PARENT, rival_args=(uuid4(), PARENT))  # fmt: skip
        await case("9. create only (DO NOTHING), the name was there before the snapshot", "REPEATABLE READ",
                   insert_rival, CREATE_ONLY, uuid4(), PARENT, rival_first=True, rival_args=(uuid4(), PARENT))  # fmt: skip
        await case("10. create only (DO NOTHING), rival created the name inside the window", "READ COMMITTED",
                   insert_rival, CREATE_ONLY, uuid4(), PARENT, rival_args=(uuid4(), PARENT))  # fmt: skip
    finally:
        if first.is_in_transaction():
            await first.execute("ROLLBACK")
        await first.execute(f"DROP SCHEMA {schema} CASCADE")
        await first.close()
        await rival.close()


def sqlite() -> None:
    print(f"sqlite library {sqlite3.sqlite_version}")
    with tempfile.TemporaryDirectory() as directory:
        path = OsPath(directory) / "raw.sqlite"
        first = sqlite3.connect(path, isolation_level=None, timeout=0)
        rival = sqlite3.connect(path, isolation_level=None, timeout=0)
        first.execute("PRAGMA journal_mode = WAL")
        first.execute(
            "CREATE TABLE e (entry_id BLOB NOT NULL UNIQUE, parent_id BLOB, name TEXT NOT NULL, "
            "path TEXT NOT NULL UNIQUE, version INTEGER, deleted_at TEXT, UNIQUE (parent_id, name))"
        )
        first.execute("INSERT INTO e VALUES (?, ?, 'a', '/a', 1, NULL)", (A.bytes, PARENT.bytes))
        first.execute("BEGIN IMMEDIATE")
        seen = first.execute("SELECT version FROM e").fetchall()
        try:
            rival.execute("BEGIN IMMEDIATE")
            outcome = "the rival began a write transaction"
        except sqlite3.OperationalError as exc:
            outcome = f"ERROR {exc.sqlite_errorname}: {exc}"
        try:
            rival.execute("UPDATE e SET version = version + 1")
            plain = "the rival's bare UPDATE ran"
        except sqlite3.OperationalError as exc:
            plain = f"ERROR {exc.sqlite_errorname}: {exc}"
        matched = first.execute(
            "UPDATE e SET version = 2 WHERE entry_id = ? AND version = ? AND path = ? AND deleted_at IS NULL",
            (A.bytes, 1, "/a"),
        ).rowcount
        first.execute("COMMIT")
        print(f"-- a second writer while one holds BEGIN IMMEDIATE (the snapshot saw version {seen[0][0]})")
        print(f"   the rival's BEGIN IMMEDIATE -> {outcome}")
        print(f"   the rival's bare UPDATE     -> {plain}")
        print(f"   the holder's guarded UPDATE -> {matched} row(s) matched")
        held = first.execute(
            "INSERT INTO e VALUES (?, ?, 'a', '/a2', 1, NULL) ON CONFLICT (parent_id, name) DO NOTHING "
            "RETURNING entry_id, path, version",
            (uuid4().bytes, PARENT.bytes),
        ).fetchall()
        free = first.execute(
            "INSERT INTO e VALUES (?, ?, 'free', '/free', 1, NULL) ON CONFLICT (parent_id, name) DO NOTHING "
            "RETURNING path, version",
            (uuid4().bytes, PARENT.bytes),
        ).fetchall()
        print(f"-- ON CONFLICT (parent_id, name) DO NOTHING RETURNING\n   over a held name -> {len(held)} row(s); over a free name -> {free}")
        first.close()
        rival.close()


async def main() -> None:
    print("== sqlite")
    sqlite()
    if not os.environ.get(POSTGRES_ENV):
        print(f"NOT RUN: the postgres leg, because {POSTGRES_ENV} is unset")
        return
    print("== postgres")
    await postgres()


if __name__ == "__main__":
    run(main, deadline=90.0)
