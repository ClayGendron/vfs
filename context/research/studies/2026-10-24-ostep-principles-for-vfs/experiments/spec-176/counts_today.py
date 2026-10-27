"""Spec 176 baseline: statements per ls, tree and glob call today (no cursor). Counts only."""

from __future__ import annotations

import asyncio
from collections import Counter

from sqlalchemy import event

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.storage.backends.memory import InMemoryStorage


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    sysa = Authority.system()
    await storage.first_touch()
    stmts: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stmts.append(statement)

    await fs.write([Entry(path=f"/big/f{i:05}.txt", content="x") for i in range(10_000)], parents=True, authority=sysa)
    alice = Authority.of(Principal("alice"))
    await fs.grant("/big", "alice", "read", authority=sysa)
    await fs.posture("/", "none", authority=sysa)
    for who, auth in (("system", sysa), ("alice", alice)):
        for label, call in (
            ("ls /big", lambda a: fs.ls("/big", authority=a)),
            ("tree /big", lambda a: fs.tree("/big", authority=a)),
            ("glob /big/*.txt", lambda a: fs.glob("/big/*.txt", authority=a)),
        ):
            await call(auth)  # warm
            stmts.clear()
            r = await call(auth)
            heads = Counter(s.split(None, 1)[0] for s in stmts)
            print(f"{who:6} {label:16} rows={len(r.observations):5} statements={len(stmts)} {dict(sorted(heads.items()))}")
    await fs.close()


asyncio.run(main())
