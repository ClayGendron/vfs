import asyncio, cProfile, pstats, sys, tempfile, time, io
from vfs.embedding import HashEmbeddingProvider
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
mode = sys.argv[1]
async def main():
    # warm one
    s = InMemoryStorage(); await s._host.ensure_ready(); await s.close()
    tmp = tempfile.mkdtemp()
    pr = cProfile.Profile()
    walls=[]; cpus=[]
    for i in range(10):
        s = InMemoryStorage() if mode=="memory" else DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/v{i}.sqlite", embedder=HashEmbeddingProvider())
        w0=time.perf_counter(); c0=time.process_time()
        pr.enable(); await s._host.ensure_ready(); pr.disable()
        walls.append(time.perf_counter()-w0); cpus.append(time.process_time()-c0)
        await s.close()
    print(mode, "first_touch wall median %.1fms cpu median %.1fms" % (sorted(walls)[5]*1000, sorted(cpus)[5]*1000))
    st = pstats.Stats(pr); st.sort_stats("cumulative"); st.print_stats(28)
asyncio.run(main())
