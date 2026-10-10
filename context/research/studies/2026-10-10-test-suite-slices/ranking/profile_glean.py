import asyncio, cProfile, pstats, tempfile, time
from pathlib import Path
from tests.ranking.corpora import vfs_native, beir
from tests.ranking.driver import load_corpus, glean_run, bm25_run
from vfs.storage.backends.database import DatabaseStorage
import sys

async def main(name):
    corpus = vfs_native() if name == "vfs_native" else beir(name)
    tmp = Path(tempfile.mkdtemp())
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite")
    loaded = await load_corpus(storage, corpus)
    await glean_run(loaded)  # warm
    pr = cProfile.Profile(); pr.enable()
    t=time.perf_counter()
    await glean_run(loaded)
    pr.disable()
    print("glean_run wall", round(time.perf_counter()-t,2), "queries", len(corpus.queries))
    st = pstats.Stats(pr); st.sort_stats("cumulative"); st.print_stats(40)
    st.sort_stats("tottime"); st.print_stats(25)
    await storage.close()

asyncio.run(main(sys.argv[1]))
