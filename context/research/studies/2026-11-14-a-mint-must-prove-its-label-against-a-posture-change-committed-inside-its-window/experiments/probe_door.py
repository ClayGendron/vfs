"""Does a posture write on Postgres wait for the holds in flight only, once it takes a table lock first?

Scratch research code. Three sessions on a table shaped like the stamps
table: a mint holding ``FOR SHARE`` on the everyone row, a posture write
that arrives second, and a mint that arrives third. Run once with the
posture write issuing only its ``UPDATE`` and once with ``LOCK TABLE …
IN EXCLUSIVE MODE`` before it.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import asyncpg

DSN = "postgresql://vfs:vfs@localhost:54320/vfs"
SHARE = "SELECT revision FROM {t} WHERE principal_id = '*' FOR SHARE"
PLAIN = "SELECT revision FROM {t} WHERE principal_id = '*'"
UPDATE = "UPDATE {t} SET revision = revision + 1 WHERE principal_id = '*'"
DOOR = "LOCK TABLE {t} IN EXCLUSIVE MODE"


async def waiting(conn: asyncpg.Connection, pid: int) -> bool:
    return bool(await conn.fetchval("SELECT count(*) FROM pg_locks WHERE pid = $1 AND NOT granted", pid))


async def run(door: bool) -> dict[str, object]:
    schema = f"vfs_probe_{uuid.uuid4().hex[:10]}"
    t = f"{schema}.stamps"
    watch, first, posture, late, later = [await asyncpg.connect(DSN) for _ in range(5)]
    found: dict[str, object] = {"door": door}
    try:
        await watch.execute(f"CREATE SCHEMA {schema}")
        await watch.execute(f"CREATE TABLE {t} (principal_id text PRIMARY KEY, revision bigint NOT NULL)")
        await watch.execute(f"INSERT INTO {t} VALUES ('*', 0)")
        # The first mint holds the shared lock.
        await first.execute("BEGIN")
        await first.fetchval(SHARE.format(t=t))

        # The posture write arrives and waits.
        async def write() -> None:
            await posture.execute("BEGIN")
            if door:
                await posture.execute(DOOR.format(t=t))
            await posture.execute(UPDATE.format(t=t))

        task = asyncio.create_task(write())
        pid = posture.get_server_pid()
        for _ in range(100):
            if await waiting(watch, pid):
                break
            await asyncio.sleep(0.02)
        found["posture write waits behind the first mint"] = await waiting(watch, pid)
        # A plain read, the watch's form, while the posture write waits.
        found["plain read while it waits"] = await asyncio.wait_for(late.fetchval(PLAIN.format(t=t)), timeout=2)
        # A second mint arrives while the posture write waits.
        await late.execute("BEGIN")
        await late.execute("SET LOCAL lock_timeout = '400ms'")
        try:
            await late.fetchval(SHARE.format(t=t))
            found["a mint arriving while it waits"] = "granted at once"
        except asyncpg.exceptions.LockNotAvailableError:
            found["a mint arriving while it waits"] = "queues behind the posture write"
            await late.execute("ROLLBACK")
        # The first mint commits.
        await first.execute("COMMIT")
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
            found["after the first mint commits"] = "the posture write proceeds"
        except TimeoutError:
            found["after the first mint commits"] = "the posture write still waits"
            # A third mint arrives: with no queue it too passes the waiting posture write.
            await later.execute("BEGIN")
            await later.execute("SET LOCAL lock_timeout = '400ms'")
            try:
                await later.fetchval(SHARE.format(t=t))
                found["a third mint, arriving now"] = "granted at once"
            except asyncpg.exceptions.LockNotAvailableError:
                found["a third mint, arriving now"] = "queues"
            await later.execute("ROLLBACK")
            await late.execute("ROLLBACK")
            await asyncio.wait_for(task, timeout=5)
            found["after every mint is gone"] = "the posture write proceeds"
        await posture.execute("COMMIT")
        found["stamp after"] = await watch.fetchval(PLAIN.format(t=t))
    finally:
        for conn in (first, posture, late, later):
            await conn.close()
        await watch.execute(f"DROP SCHEMA {schema} CASCADE")
        await watch.close()
    return found


async def main() -> None:
    for door in (False, True):
        print(json.dumps(await run(door)))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
