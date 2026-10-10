"""Phase timer for one harness test shape: parse, write, reindex, map, bm25, glean, evaluate."""
from __future__ import annotations

import asyncio
import cProfile
import pstats
import sys
import tempfile
import time
from pathlib import Path

from tests.ranking.corpora import beir, vfs_native
from tests.ranking.driver import WRITE_BATCH, Loaded, bm25_run, glean_run
from tests.ranking.metrics import evaluate
from tests.ranking.embedders import HASH_DIMENSION, POTION_MODEL
from sqlalchemy import select
from vfs.models import Entry
from vfs.paths import Path as VPath
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import chunked
from vfs.embedding import HashEmbeddingProvider, Model2VecEmbeddingProvider
from vfs.storage.ranking import Convex, Ranker


class T:
    def __init__(self):
        self.rows = []
    def __call__(self, name):
        t = self
        class _C:
            def __enter__(s):
                s.t0 = time.perf_counter(); s.c0 = time.process_time()
            def __exit__(s, *a):
                t.rows.append((name, time.perf_counter() - s.t0, time.process_time() - s.c0))
        return _C()


async def run(corpus_name: str, embedder_name: str | None, batch: int, profile_reindex: bool):
    timer = T()
    with timer("parse"):
        corpus = vfs_native() if corpus_name == "vfs_native" else beir(corpus_name)
    tmp = Path(tempfile.mkdtemp())
    embedder = None
    ranker = None
    if embedder_name == "hash":
        embedder = HashEmbeddingProvider(HASH_DIMENSION)
        ranker = Ranker(fusion=Convex({"vector": 0.5, "lexical": 0.5}))
    elif embedder_name == "potion":
        embedder = Model2VecEmbeddingProvider(model_name=POTION_MODEL)
        ranker = Ranker(fusion=Convex({"vector": 0.5, "lexical": 0.5}))
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite", embedder=embedder, ranker=ranker)
    try:
        with timer("entries"):
            entries = [Entry(path=VPath(corpus.paths[d]), content=t) for d, t in corpus.docs.items()]
        with timer(f"write(batch={batch})"):
            for b in chunked(entries, batch):
                r = await storage.write(entries=list(b), parents=True)
                assert r.success, r.errors
        pr = cProfile.Profile() if profile_reindex else None
        with timer("reindex"):
            if pr: pr.enable()
            r = await storage.reindex()
            if pr: pr.disable()
            assert r.success, r.errors
        if pr:
            st = pstats.Stats(pr)
            st.sort_stats("cumulative")
            print("---- reindex cumulative (top 45) ----")
            st.print_stats(45)
        tables = storage._host.tables
        with timer("path_of map"):
            entry, chunks, meta = tables.entry, tables.chunks, tables.meta
            async with storage._host.engine.connect() as conn:
                epoch = (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()
                located = select(chunks.c.id, entry.c.path).select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
                path_of = {row.id: row.path for row in await conn.execute(located)}
        loaded = Loaded(storage, corpus, epoch, path_of)
        print(f"docs={len(corpus.docs)} queries={len(corpus.queries)} chunks={len(path_of)}")
        with timer("bm25_run (driver)"):
            bm = await bm25_run(loaded)
        with timer("glean_run (verb)"):
            gl = await glean_run(loaded)
        with timer("evaluate #1 (ranx, incl JIT)"):
            evaluate(corpus.qrels, bm)
        with timer("evaluate #2 (ranx warm)"):
            evaluate(corpus.qrels, gl)
    finally:
        with timer("close"):
            await storage.close()
    total = sum(s for _, s, _ in timer.rows); ctotal = sum(c for _, _, c in timer.rows)
    print(f"\n== {corpus_name} embedder={embedder_name} ==  (wall, cpu)")
    for name, s, c in timer.rows:
        print(f"  {name:32s} wall {s:7.2f}s {100*s/total:5.1f}%   cpu {c:7.2f}s {100*c/ctotal:5.1f}%")
    print(f"  {'TOTAL':32s} wall {total:7.2f}s          cpu {ctotal:7.2f}s")


if __name__ == "__main__":
    corpus = sys.argv[1]
    emb = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "none" else None
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else WRITE_BATCH
    prof = len(sys.argv) > 4 and sys.argv[4] == "prof"
    asyncio.run(run(corpus, emb, batch, prof))
