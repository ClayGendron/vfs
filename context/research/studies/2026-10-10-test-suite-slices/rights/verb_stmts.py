"""Statements and transactions per verb call during a replay, and a cProfile of init + first_touch."""
from __future__ import annotations
import asyncio, cProfile, pstats, random, sys, time
from collections import Counter
from sqlalchemy import event
from sqlalchemy.engine import Engine
sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")
from tests.storage.database.test_rights import SYSTEM, _POSTURE_OF
from tests.support.grant_worlds import LAYOUTS, random_world
from vfs.authority import EVERYONE_NAME
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

PH = ["none"]; C: Counter[str] = Counter(); KINDS: Counter[str] = Counter()
@event.listens_for(Engine, "before_cursor_execute")
def _c(conn, cursor, statement, parameters, context, executemany):
    C[PH[0]] += 1
    KINDS[f"{PH[0]}:{statement.lstrip().split(None, 1)[0].upper()}"] += 1
@event.listens_for(Engine, "begin")
def _b(conn):
    C[PH[0] + ":txn"] += 1

async def ph(key, coro):
    PH[0] = key
    try:
        return await coro
    finally:
        PH[0] = "none"

async def main():
    rng = random.Random(58)
    n = Counter()
    prof = cProfile.Profile()
    for _ in range(30):
        world = random_world(rng, LAYOUTS[0])
        prof.enable(); storage = InMemoryStorage(); prof.disable()
        prof.enable(); r = await ph("first_touch", storage.first_touch()); prof.disable()
        n["first_touch"] += 1
        entries = [Entry(path=Path(p), content=p, owner_id=o) for p, o in sorted(world.owners.items())]
        await ph("write", storage.write(entries=entries, parents=True, authority=SYSTEM)); n["write"] += 1
        for row in world.grants:
            if row.principal_id == EVERYONE_NAME:
                await ph("posture", storage.posture(path=Path(row.path_prefix), posture=_POSTURE_OF[row.level], authority=SYSTEM)); n["posture"] += 1
            else:
                await ph("grant", storage.grant(path=Path(row.path_prefix), principal=row.principal_id, level=row.level, authority=SYSTEM)); n["grant"] += 1
        for member, groups in world.member_of.items():
            for group in sorted(groups):
                await ph("add_member", storage.add_member(group=group, member=member, authority=SYSTEM)); n["add_member"] += 1
        await ph("close", storage.close()); n["close"] += 1
    for k in ("first_touch", "write", "posture", "grant", "add_member", "close"):
        print(f"{k:12s} calls={n[k]:4d} stmts/call={C[k]/n[k]:6.1f} txns/call={C[k+':txn']/n[k]:5.2f}")
    for k in sorted(KINDS):
        print(f"   {k:24s} {KINDS[k]}")
    st = pstats.Stats(prof); st.sort_stats("cumulative"); st.print_stats(30)

asyncio.run(main())
