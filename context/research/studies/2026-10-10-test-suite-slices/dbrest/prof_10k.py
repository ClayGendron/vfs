import asyncio, time, cProfile, pstats, io, tempfile
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
async def main():
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite")
    await s.write(entries=[Entry(path=Path("/warm.txt"), content="x")], parents=True)
    t0=time.perf_counter()
    entries = [Entry(path=Path(f"/lake/d{i // 500:02}/r{i:05}.json"), content=f'{{"row": {i}}}') for i in range(10_000)]
    print(f"build 10k Entry models: {time.perf_counter()-t0:.2f}s")
    pr = cProfile.Profile(); pr.enable(); t0=time.perf_counter()
    w = await s.write(entries=entries, parents=True); assert w.success
    pr.disable(); print(f"write under profile: {time.perf_counter()-t0:.2f}s")
    st = pstats.Stats(pr); st.sort_stats("tottime"); buf=io.StringIO(); st.stream=buf; st.print_stats(30); print(buf.getvalue()[:7000])
    st.sort_stats("cumulative"); buf=io.StringIO(); st.stream=buf; st.print_stats(40); print(buf.getvalue()[:9000])
    await s.close()
asyncio.run(main())
