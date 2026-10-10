"""Where a replayed world's milliseconds go: init, first touch, write, postures, grants, memberships."""

from __future__ import annotations

import asyncio
import random
import sys
import time
from collections import Counter

sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")

from tests.storage.database.test_rights import SYSTEM, _POSTURE_OF  # noqa: E402
from tests.support.grant_worlds import LAYOUTS, random_world  # noqa: E402
from vfs.authority import EVERYONE_NAME  # noqa: E402
from vfs.models import Entry  # noqa: E402
from vfs.paths import Path  # noqa: E402
from vfs.storage.backends.memory import InMemoryStorage  # noqa: E402

T: Counter[str] = Counter()
N: Counter[str] = Counter()


async def timed(key: str, coro):  # noqa: ANN001
    t0 = time.perf_counter()
    try:
        return await coro
    finally:
        T[key] += time.perf_counter() - t0
        N[key] += 1


async def main() -> None:
    rng = random.Random(58)
    layout = LAYOUTS[0] if "siblings" not in sys.argv else LAYOUTS[1]
    for _ in range(30):
        world = random_world(rng, layout)
        t0 = time.perf_counter()
        storage = InMemoryStorage()
        T["init"] += time.perf_counter() - t0
        N["init"] += 1
        assert (await timed("first_touch", storage.first_touch())).success is True
        entries = [Entry(path=Path(p), content=p, owner_id=o) for p, o in sorted(world.owners.items())]
        assert (await timed("write", storage.write(entries=entries, parents=True, authority=SYSTEM))).success is True
        for row in world.grants:
            if row.principal_id == EVERYONE_NAME:
                r = await timed(
                    "posture", storage.posture(path=Path(row.path_prefix), posture=_POSTURE_OF[row.level], authority=SYSTEM)
                )
            else:
                r = await timed(
                    "grant",
                    storage.grant(path=Path(row.path_prefix), principal=row.principal_id, level=row.level, authority=SYSTEM),
                )
            assert r.success is True
        for member, groups in world.member_of.items():
            for group in sorted(groups):
                assert (await timed("add_member", storage.add_member(group=group, member=member, authority=SYSTEM))).success
        await timed("close", storage.close())
    total = sum(T.values())
    print(f"30 worlds ({'siblings' if 'siblings' in sys.argv else 'base'}): total {total:.3f}s")
    for k in sorted(T, key=lambda k: -T[k]):
        print(f"  {k:12s} {T[k]:.3f}s  n={N[k]:4d}  {1000 * T[k] / N[k]:.1f} ms/call")


asyncio.run(main())
