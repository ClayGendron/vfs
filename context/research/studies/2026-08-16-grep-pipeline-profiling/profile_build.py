"""Reindex build-side attribution: where the wall time actually goes.

Points at an already-built sqlite store (the linux benchmark's, or any
other), resets its index state (chunked/encoded flags, postings, epochs,
pointer), then times one ``storage.reindex()`` with wall-clock wrappers
around the phase coroutines and the leaf hot spots. cProfile is
deliberately not used for the headline numbers — it inflates tight
Python loops ~2-3x while leaving C calls honest, which mis-ranks
tree-sitter against the interpreted extraction loop.

Landed-run record (2026-08-16, the benchmark's linux.sqlite: 93,760
docs / 1.59 GB corpus, M-series laptop):

- **Pure-Python engine** (the 672 s recorded baseline), attributed on a
  1/31 sample x31: extraction (``unique_code_grams``) ~384 s across its
  two passes (the ``_indexable`` gate re-extracts what ``build_epoch``
  extracts again), ``Chunk.split`` (tree-sitter) ~142 s,
  ``encode_postings`` ~17 s, fetch/SQL/accumulate/glue ~101 s.
- **Rust engine** (slice B, full-corpus run): reindex total 191-208 s.
  ``build_epoch`` 272 s -> 5.6-7.6 s; ``_indexable`` gate ~2.8 s total;
  ``Chunk.split`` 161 s — now 84% of the verb — plus ~19 s of
  chunk-row fetch/insert/flip machinery around it. The grep-index build
  proper (gate + extraction + grouping + encode + posting inserts) is
  ~30 s. Row counts on all 25 benchmark queries are identical to the
  pure-built index (parity also pinned byte-for-byte in
  ``tests/test_native.py``).
- Chunking parallelization is blocked in-process: the tree_sitter pyo3
  binding holds the GIL through ``parse`` and its ``Parser`` is
  ``unsendable`` (thread-pinned) — an 8-thread pool measured 1.0x.

Run:  DB=/path/to/store.sqlite uv run python \
      context/research/studies/2026-08-16-grep-pipeline-profiling/profile_build.py
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path as OsPath

from sqlalchemy import text

import vfs.storage.backends.database.backend as backend_mod
import vfs.storage.backends.database.indexing as indexing
from vfs.native import active_core
from vfs.storage.backends.database import DatabaseStorage

DB = OsPath(os.environ["DB"])

WALLS: dict[str, float] = {}


def timed_async(name, fn):
    async def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = await fn(*args, **kwargs)
        WALLS[name] = WALLS.get(name, 0.0) + (time.perf_counter() - t0)
        return result

    return wrapper


def timed_sync(name, fn):
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        out = fn(*args, **kwargs)
        WALLS[name] = WALLS.get(name, 0.0) + (time.perf_counter() - t0)
        return out

    return wrapper


async def main() -> None:
    print(f"active core: {active_core()}", flush=True)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    result = await storage.stat(path="/")
    assert result.success, result.errors
    async with storage._host.session_factory() as session:
        await session.execute(text("UPDATE vfs SET chunked = 0, encoded = 0"))
        await session.execute(text("DELETE FROM vfs_grams_posting_list"))
        await session.execute(text("DELETE FROM vfs_gram_epochs"))
        await session.execute(text("UPDATE vfs_meta SET current_gram_epoch = NULL"))
        await session.commit()

    for name in ("chunk_dirty", "build_epoch", "publish_epoch", "reclaim_epochs"):
        wrapped = timed_async(name, getattr(indexing, name))
        setattr(indexing, name, wrapped)
        setattr(backend_mod, name, wrapped)
    indexing.Chunk.split = timed_sync("  Chunk.split", indexing.Chunk.split)
    indexing._indexable = timed_sync("  _indexable gate", indexing._indexable)

    t0 = time.perf_counter()
    result = await storage.reindex()
    wall = time.perf_counter() - t0
    assert result.success, result.errors
    print(f"reindex total: {wall:.1f}s")
    for name, seconds in WALLS.items():
        print(f"  {name:20} {seconds:>7.1f}s")
    await storage.close()


asyncio.run(main())
