"""S6: replay a world with the posture rows written before the entries (the write inherits labels; no relabel of existing rows)."""
from __future__ import annotations
import asyncio, random, sys, time
from collections import Counter
from sqlalchemy import event
from sqlalchemy.engine import Engine
sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")
from tests.storage.database.test_rights import SYSTEM, _POSTURE_OF, _assert_labels, _expected, _authority
from tests.support.grant_worlds import LAYOUTS, SUBJECT_SETS, random_world
from vfs.authority import EVERYONE_NAME
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

C = Counter(); PH = ["x"]
@event.listens_for(Engine, "before_cursor_execute")
def _c(conn, cursor, statement, parameters, context, executemany):
    C[PH[0]] += 1

async def replay(world, postures_first):
    storage = InMemoryStorage()
    entries = [Entry(path=Path(p), content=p, owner_id=o) for p, o in sorted(world.owners.items())]
    async def write():
        assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    async def rows():
        for row in world.grants:
            if row.principal_id == EVERYONE_NAME:
                r = await storage.posture(path=Path(row.path_prefix), posture=_POSTURE_OF[row.level], authority=SYSTEM)
            else:
                r = await storage.grant(path=Path(row.path_prefix), principal=row.principal_id, level=row.level, authority=SYSTEM)
            assert r.success is True, r.errors
    if postures_first:
        await rows(); await write()
    else:
        await write(); await rows()
    for member, groups in world.member_of.items():
        for group in sorted(groups):
            assert (await storage.add_member(group=group, member=member, authority=SYSTEM)).success is True
    return storage

async def main():
    for label, first in (("write first (live)", False), ("postures first", True), ("write first (live)", False), ("postures first", True)):
        rng = random.Random(58); PH[0] = label; C[label] = 0
        t0 = time.perf_counter()
        for _ in range(30):
            world = random_world(rng, LAYOUTS[0])
            storage = await replay(world, first)
            try:
                await _assert_labels(storage, world)
                for subjects in SUBJECT_SETS:
                    result = await storage.glob(patterns=("/**",), authority=_authority(subjects))
                    assert {str(o.path) for o in result.observations} - {"/"} == _expected(world, subjects, "read")
            finally:
                await storage.close()
        print(f"{label:20s} {time.perf_counter()-t0:5.2f}s  statements={C[label]}")

asyncio.run(main())
