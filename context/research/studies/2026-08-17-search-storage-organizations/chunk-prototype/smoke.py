import asyncio, harness
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.indexing import current_epoch

async def main():
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{harness.STORE}")
    assert await storage._host.ensure_ready() is None
    host = storage._host
    async with host.session_factory() as session:
        epoch = await current_epoch(session, host.tables)
    for key, pattern, kwargs in [harness.ROWS[2], harness.ROWS[15], harness.ROWS[11]]:
        real_ms, real_pairs, _tr = await harness.real_grep(storage, pattern, kwargs)
        ft, fm, fp = await harness.staged_run(host, harness.FileMode(host, epoch), pattern, kwargs, 25000)
        ct, cm, cp = await harness.staged_run(host, harness.ChunkMode(host), pattern, kwargs, None)
        print(key)
        print("  real", len(real_pairs), f"{real_ms:.1f}ms")
        print("  file", len(fp), f"{sum(ft.values())*1000:.1f}ms", {k: f"{v*1000:.1f}" for k,v in ft.items()}, fm)
        print("  chunk", len(cp), f"{sum(ct.values())*1000:.1f}ms", {k: f"{v*1000:.1f}" for k,v in ct.items()}, cm)
        print("  file==real:", fp == real_pairs, " chunk==real:", cp == real_pairs)
        if cp != real_pairs:
            print("   chunk-real:", sorted(cp - real_pairs)[:5], " real-chunk:", sorted(real_pairs - cp)[:5])
    await storage.close()

asyncio.run(main())
