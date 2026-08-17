"""One cold staged run (or real grep) against a fresh clone. argv:
db_path mode(file|chunk|real) row_key budget(int|none)"""
import asyncio, json, sys, time

import harness
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.indexing import current_epoch

async def main():
    db, mode_name, key, budget_s = sys.argv[1:5]
    budget = None if budget_s == "none" else int(budget_s)
    row = next(r for r in harness.ROWS if r[0] == key)
    _, pattern, kwargs = row
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}")
    assert await storage._host.ensure_ready() is None
    host = storage._host
    if mode_name == "real":
        t0 = time.perf_counter()
        result = await storage.grep(pattern=pattern, **kwargs)
        ms = (time.perf_counter() - t0) * 1000
        n = sum(len(o.matches or ()) for o in result.observations)
        print(json.dumps({"total_ms": ms, "n_pairs": n}))
    else:
        async with host.session_factory() as session:
            epoch = await current_epoch(session, host.tables)
        mode = harness.FileMode(host, epoch) if mode_name == "file" else harness.ChunkMode(host)
        times, m, pairs = await harness.staged_run(host, mode, pattern, kwargs, budget, overlay=False)
        print(json.dumps({"total_ms": sum(times.values()) * 1000,
                          "stages_ms": {k: v * 1000 for k, v in times.items()},
                          "metrics": {k: v for k, v in m.items() if k != "truncations"} | {"truncations": m["truncations"]},
                          "n_pairs": len(pairs)}))
    await storage.close()

asyncio.run(main())
