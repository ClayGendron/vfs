"""Probe 9: an ordinary caller's compile and reads while a posture change above every home is in flight.

usage: probe_window.py DATA_DIR N [N ...]   (builds world-N.sqlite in DATA_DIR when it is absent)
On a copy of world-N, posture /home is narrowed from `read` to `list` and held in flight (the posture row
written and marked, no label rewritten: the suite's _hold_posture shape). Counts what ann's compile
carries and what her reads issue, then lets the relabel finish and counts the verb's own work.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys

from world import DATA, SYSTEM, Recorder, build, who

from sqlalchemy import and_, update
from vfs.authority import EVERYONE_NAME
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.labels import mark_relabel
from vfs.storage.backends.database.revision import bump_revision
from vfs.storage.backends.database.rights import resolve_authority

HERE = DATA


async def main() -> None:
    for n in map(int, sys.argv[2:]):
        source = os.path.join(HERE, f"world-{n}.sqlite")
        if not os.path.exists(source):
            await (await build(f"sqlite+aiosqlite:///{source}", n)).close()
        copy = os.path.join(HERE, f"window-{n}.sqlite")
        shutil.copyfile(source, copy)
        for side in ("-wal", "-shm"):
            if os.path.exists(source + side):
                shutil.copyfile(source + side, copy + side)
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{copy}")
        await storage.first_touch()
        host = storage._host
        grants = host.tables.grants
        try:
            async with host.session_factory() as session, session.begin():
                revision = await bump_revision(session, host.tables)
                key = and_(grants.c.principal_id == EVERYONE_NAME, grants.c.path_prefix == "/home")
                hit = await session.execute(update(grants).where(key).values(level="list", revision=revision))
                if hit.rowcount == 0:
                    from sqlalchemy import insert  # noqa: PLC0415  (scratch probe)
                    from datetime import UTC, datetime  # noqa: PLC0415

                    await session.execute(
                        insert(grants).values(
                            principal_id=EVERYONE_NAME, path_prefix="/home", level="list",
                            granted_by="system", granted_at=datetime.now(UTC), revision=revision,
                        )
                    )
                await mark_relabel(session, host.tables, "/home", revision)
            rec = Recorder(storage)
            async with host.session_factory() as session:

                async def cold(session=session):
                    return await resolve_authority(
                        session, host.tables, host.profile, host.membership_budget, who("ann"), None
                    )

                res, rows = await rec.run(cold())
            rights = res.at("read")
            ranges = rights.ranges()
            print(
                f"N={n} window: ann cold compile statements={len(rows)} posture rows read="
                f"{sum(1 for t, _, _ in rows if 'vfs_grants' in t)} read-rung hole pieces="
                f"{len(ranges.holes.points) + len(ranges.holes.opens)} spans={len(rights.spans)}"
            )
            for key, call in (
                ("grep needle", lambda: storage.grep(pattern="needle", authority=who("ann"))),
                ("glob /shared/**", lambda: storage.glob(patterns=("/shared/**",), authority=who("ann"))),
                ("read own", lambda: storage.read(path=Path("/home/ann/f0.md"), authority=who("ann"))),
            ):
                await call()
                result, rows = await rec.run(call())
                print(
                    f"   {key:16} ok={result.success} rows={len(result.observations)} statements={len(rows)} "
                    f"max binds={max(b for _, b, _ in rows)} max bound bytes={max(s for _, _, s in rows)}"
                )
            result, rows = await rec.run(storage.posture(path=Path("/home"), posture="list", authority=SYSTEM))
            print(f"   the posture verb finishing it: {(result.model_extra or {}).get('relabel')} statements={len(rows)}")
        finally:
            await storage.close()


asyncio.run(main())
