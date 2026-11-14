"""Probe 6: the generic floor's road check while a narrowing posture is in flight over D deeper postures.

usage: probe_generic_hole.py DATA_DIR D [range]
The profile is SQLite's with no range source and Oracle's IN-list cap (the generic floor's spelling, the
suite's idiom), or SQLite's own with "range". A narrowing posture at / is held in flight (marked, no label
rewritten), then ann, who owns nothing beneath and holds one grant, lists /h; /h/u00007/pub is opened to
`list`, so the right answer is the road to /h/u00007. Counts and outcomes only.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime

from world import DATA, SYSTEM, Recorder, who

from sqlalchemy import and_, insert, update
from vfs.authority import EVERYONE_NAME
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import SQLITE
from vfs.storage.backends.database.labels import mark_relabel
from vfs.storage.backends.database.revision import bump_revision

HERE = DATA


async def main() -> None:
    deeper = int(sys.argv[2])
    ranged = len(sys.argv) > 3
    profile = SQLITE if ranged else replace(SQLITE, range_source=None, in_list_budget=1_000)
    engine_module.profile_for = lambda name: profile
    path = os.path.join(HERE, f"generic-{deeper}-{'range' if ranged else 'floor'}.sqlite")
    if os.path.exists(path):
        os.remove(path)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{path}", posture="read")
    try:
        files = [Entry(path=Path(f"/h/u{i:05}/f.md"), content="x") for i in range(deeper)]
        files.append(Entry(path=Path("/g/a.md"), content="x"))
        files.append(Entry(path=Path("/h/u00007/pub/x.md"), content="x"))
        assert (await storage.write(entries=files, parents=True, authority=SYSTEM)).success
        for i in range(deeper):
            assert (await storage.posture(path=Path(f"/h/u{i:05}"), posture="none", authority=SYSTEM)).success
        assert (await storage.posture(path=Path("/h/u00007/pub"), posture="list", authority=SYSTEM)).success
        assert (await storage.grant(path=Path("/g"), principal="ann", level="read", authority=SYSTEM)).success
        steady = await storage.ls(path=Path("/h"), authority=who("ann"))
        host = storage._host
        grants = host.tables.grants
        async with host.session_factory() as session, session.begin():
            revision = await bump_revision(session, host.tables)
            key = and_(grants.c.principal_id == EVERYONE_NAME, grants.c.path_prefix == "/")
            await session.execute(update(grants).where(key).values(level="none", revision=revision))
            await mark_relabel(session, host.tables, "/", revision)
        rec = Recorder(storage)
        held, rows = await rec.run(storage.ls(path=Path("/h"), authority=who("ann")))
        print(
            f"D={deeper} {'range source' if ranged else 'generic floor'}: steady ls ok={steady.success} "
            f"rows={[str(o.path) for o in steady.observations]}; in flight ls ok={held.success} "
            f"rows={[str(o.path) for o in held.observations]} "
            f"errors={[(e.kind, str(e)[:160]) for e in held.errors]} statements={len(rows)} "
            f"max binds={max((b for _, b, _ in rows), default=0)} max bound bytes={max((s for _, _, s in rows), default=0)}"
        )
        _ = insert, datetime, UTC
    finally:
        await storage.close()


asyncio.run(main())
