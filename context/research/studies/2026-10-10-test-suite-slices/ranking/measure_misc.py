"""Measured levers: preview stub (upper bound), write batch size, pre-indexed sqlite reopen, smaller corpus."""
from __future__ import annotations
import asyncio, shutil, sys, tempfile, time
from pathlib import Path
from sqlalchemy import select
from tests.ranking.corpora import Corpus, beir, vfs_native
from tests.ranking.driver import Loaded, bm25_run, glean_run, load_corpus
from tests.ranking.metrics import evaluate
from vfs.models import Entry
from vfs.paths import Path as VPath
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import chunked
import vfs.storage.backends.database.glean as glean_mod
from vfs.results.preview import Preview

def clock():
    return time.perf_counter(), time.process_time()
def since(t):
    return round(time.perf_counter()-t[0],2), round(time.process_time()-t[1],2)

async def preview_stub(name):
    corpus = vfs_native() if name == "vfs_native" else beir(name)
    tmp = Path(tempfile.mkdtemp())
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite")
    loaded = await load_corpus(storage, corpus)
    t = clock(); real = await glean_run(loaded); print(f"[{name}] glean_run with preview   wall,cpu {since(t)}")
    orig = glean_mod.select_preview
    glean_mod.select_preview = lambda text, start, terms: Preview(text="", start=start, end=start, matched=False)
    try:
        t = clock(); stubbed = await glean_run(loaded); print(f"[{name}] glean_run preview stubbed wall,cpu {since(t)}")
    finally:
        glean_mod.select_preview = orig
    print(f"[{name}] runs identical with preview stubbed: {real == stubbed}")
    await storage.close()

async def batch_sizes(name):
    corpus = vfs_native() if name == "vfs_native" else beir(name)
    entries = [Entry(path=VPath(corpus.paths[d]), content=t) for d, t in corpus.docs.items()]
    for batch in (250, 1000, 5000, 20000):
        tmp = Path(tempfile.mkdtemp())
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite")
        t = clock(); n = 0
        for b in chunked(entries, batch):
            r = await storage.write(entries=list(b), parents=True); assert r.success, r.errors; n += 1
        w = since(t); t = clock(); r = await storage.reindex(); assert r.success; ri = since(t)
        print(f"[{name}] batch={batch:5d} calls={n:3d} write wall,cpu {w}  reindex wall,cpu {ri}")
        await storage.close()

async def preindexed(name):
    corpus = vfs_native() if name == "vfs_native" else beir(name)
    tmp = Path(tempfile.mkdtemp())
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite")
    t = clock(); loaded = await load_corpus(storage, corpus); print(f"[{name}] fresh load_corpus wall,cpu {since(t)}")
    bm = await bm25_run(loaded)
    await storage.close()
    print(f"[{name}] sqlite file size MB {round((tmp/'vfs.sqlite').stat().st_size/1e6,1)}")
    copy = Path(tempfile.mkdtemp()); shutil.copy(tmp/"vfs.sqlite", copy/"vfs.sqlite")
    t = clock()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{copy}/vfs.sqlite")
    r = await storage.reindex(); assert r.success  # no-op reindex: nothing dirty
    tables = storage._host.tables
    async with storage._host.engine.connect() as conn:
        epoch = (await conn.execute(select(tables.meta.c.current_gram_epoch))).scalar_one()
        located = select(tables.chunks.c.id, tables.entry.c.path).select_from(tables.chunks.join(tables.entry, tables.entry.c.entry_id == tables.chunks.c.entry_id))
        path_of = {row.id: row.path for row in await conn.execute(located)}
    reopened = Loaded(storage, corpus, epoch, path_of)
    print(f"[{name}] reopen pre-indexed (open + no-op reindex + map) wall,cpu {since(t)}")
    bm2 = await bm25_run(reopened)
    print(f"[{name}] bm25 runs identical from pre-indexed file: {bm == bm2}")
    await storage.close()

async def smaller(fraction):
    golden = vfs_native()
    docs = dict(list(golden.docs.items())[: int(len(golden.docs) * fraction)])
    keep = set(docs)
    qrels = {q: {d: g for d, g in graded.items() if d in keep} for q, graded in golden.qrels.items()}
    qrels = {q: g for q, g in qrels.items() if any(v > 0 for v in g.values())}
    queries = {q: t for q, t in golden.queries.items() if q in qrels}
    corpus = Corpus("small", docs, {d: golden.paths[d] for d in docs}, queries, qrels)
    tmp = Path(tempfile.mkdtemp())
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite")
    t = clock(); loaded = await load_corpus(storage, corpus); l = since(t)
    t = clock(); run = await glean_run(loaded); g = since(t)
    positives = sum(1 for q in qrels.values() if any(v > 0 for v in q.values()))
    nums = evaluate(qrels, run) if positives else {}
    print(f"[small {fraction}] docs={len(docs)} chunks={len(loaded.path_of)} load wall,cpu {l} glean_run wall,cpu {g} queries-with-a-positive={positives}/{len(golden.queries)} ndcg@10={nums.get('ndcg@10')}")
    await storage.close()

async def main():
    which = sys.argv[1]
    if which == "preview":
        for n in ("vfs_native", "scifact", "nfcorpus"): await preview_stub(n)
    elif which == "batch":
        for n in ("vfs_native", "scifact"): await batch_sizes(n)
    elif which == "preindexed":
        for n in ("vfs_native", "scifact"): await preindexed(n)
    elif which == "smaller":
        for f in (1.0, 0.5, 0.25): await smaller(f)
asyncio.run(main())
