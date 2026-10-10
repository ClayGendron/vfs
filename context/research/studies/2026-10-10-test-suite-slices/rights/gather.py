"""The glob oracle test: serial replays vs replays gathered concurrently. Same worlds, same checks."""
from __future__ import annotations
import asyncio, random, sys, time
sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")
from tests.storage.database.test_rights import WORLDS, _authority, _expected, _replay
from tests.support.grant_worlds import SUBJECT_SETS, random_world

async def check(world, storage):
    try:
        for subjects in SUBJECT_SETS:
            result = await storage.glob(patterns=("/**",), authority=_authority(subjects))
            assert result.success is True
            named = {str(o.path) for o in result.observations} - {"/"}
            assert named == _expected(world, subjects, "read")
    finally:
        await storage.close()

async def serial():
    rng = random.Random(58)
    for _ in range(WORLDS):
        world = random_world(rng)
        await check(world, await _replay(world))

async def gathered(width):
    rng = random.Random(58)
    worlds = [random_world(rng) for _ in range(WORLDS)]
    sem = asyncio.Semaphore(width)
    async def one(world):
        async with sem:
            await check(world, await _replay(world))
    await asyncio.gather(*(one(w) for w in worlds))

for label, coro in (("serial", serial()), ("gather(4)", gathered(4)), ("gather(30)", gathered(30)), ("serial again", serial())):
    t0 = time.perf_counter(); asyncio.run(coro); print(f"{label:14s} {time.perf_counter()-t0:5.2f}s")
