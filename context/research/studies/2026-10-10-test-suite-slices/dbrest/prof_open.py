import asyncio, time, cProfile, pstats, io, sys
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

async def one():
    s = DatabaseStorage(url="sqlite+aiosqlite:///:memory:")
    r = await s.write(entries=[Entry(path=Path("/a.txt"), content="x")], parents=True); assert r.success
    await s.close()

async def main():
    await one(); await one()
    # timed loop of 10
    t0=time.perf_counter()
    for _ in range(10): await one()
    print(f"mean open+write+close over 10: {(time.perf_counter()-t0)/10*1000:.1f} ms")
    pr = cProfile.Profile(); pr.enable()
    for _ in range(10): await one()
    pr.disable()
    st = pstats.Stats(pr); st.sort_stats("cumulative")
    s = io.StringIO(); st.stream = s; st.print_stats(45); print(s.getvalue()[:9000])
asyncio.run(main())
