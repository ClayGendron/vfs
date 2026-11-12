"""Time a full rebuild of the 100,000-file SQLite store and split it into phases.

Copies study 02's clean base store, rewrites one file through ``write()``
so one live entry is not encoded (the condition ``build_epoch`` rebuilds
the whole gram and lexical index on), then times ``reindex()`` with
timers patched over the phase functions in the namespaces that call
them: the gram phases in ``backend.py``, the gram feed, gram inserts and
``build_lexical_epoch`` in ``indexing.py``, the lexical inserts and the
builder in ``lexical.py``. The builder is wrapped in a proxy that times
``add_docs``, ``finish`` and the two drains on the offload thread, and
counts the documents and characters fed. Nothing under ``src/`` is
edited; the patches live in this process only.

Optionally dumps a uniform sample of chunk rows as a bodies directory
for the Rust bench (corpus C: the documents the builder actually sees).

Usage: uv run python rebuild.py <source db> <scratch dir> <out json> [--dump-chunks N]
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import resource
import shutil
import sqlite3
import sys
import time
from functools import partial, wraps
from pathlib import Path as FsPath

from sqlalchemy import event, func, select

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import indexing as indexing_module
from vfs.storage.backends.database import lexical as lexical_module

REPO = FsPath(__file__).resolve().parents[5]
GENERATOR = REPO / "context/research/studies/2026-11-09-the-dirty-row-budgets-of-grep-and-glean/experiments/corpus.py"

TIMERS: dict[str, dict[str, float | int]] = {}


def bucket(name: str) -> dict[str, float | int]:
    return TIMERS.setdefault(name, {"calls": 0, "wall_s": 0.0, "rows": 0, "chars": 0})


def timed_async(module, name: str, label: str) -> None:
    original = getattr(module, name)

    @wraps(original)
    async def wrapper(*args, **kwargs):
        b = bucket(label)
        b["calls"] += 1
        t0 = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            b["wall_s"] += time.perf_counter() - t0

    setattr(module, name, wrapper)


def timed_sync(module, name: str, label: str, *, rows=None, chars=None) -> None:
    original = getattr(module, name)

    @wraps(original)
    def wrapper(*args, **kwargs):
        b = bucket(label)
        b["calls"] += 1
        if rows is not None:
            b["rows"] += rows(*args, **kwargs)
        if chars is not None:
            b["chars"] += chars(*args, **kwargs)
        t0 = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            b["wall_s"] += time.perf_counter() - t0

    setattr(module, name, wrapper)


class TimedBuilder:
    """The native lexical builder with every method timed on the offload thread."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def add_docs(self, docs):
        b = bucket("lexical.builder.add_docs")
        b["calls"] += 1
        b["rows"] += len(docs)
        b["chars"] += sum(len(content) for _id, content in docs)
        t0 = time.perf_counter()
        try:
            return self._inner.add_docs(docs)
        finally:
            b["wall_s"] += time.perf_counter() - t0

    def finish(self):
        b = bucket("lexical.builder.finish")
        b["calls"] += 1
        t0 = time.perf_counter()
        try:
            return self._inner.finish()
        finally:
            b["wall_s"] += time.perf_counter() - t0

    def next_df_batch(self, row_cap):
        b = bucket("lexical.builder.next_df_batch")
        b["calls"] += 1
        t0 = time.perf_counter()
        try:
            out = self._inner.next_df_batch(row_cap)
            b["rows"] += 0 if out is None else len(out)
            return out
        finally:
            b["wall_s"] += time.perf_counter() - t0

    def next_batch(self, row_cap):
        b = bucket("lexical.builder.next_batch")
        b["calls"] += 1
        t0 = time.perf_counter()
        try:
            out = self._inner.next_batch(row_cap)
            b["rows"] += 0 if out is None else len(out)
            return out
        finally:
            b["wall_s"] += time.perf_counter() - t0


def install_timers() -> None:
    for name in ("chunk_dirty", "build_epoch", "publish_epoch", "reclaim_epochs"):
        timed_async(backend_module, name, f"phase.{name}")
    timed_async(indexing_module, "build_lexical_epoch", "build.lexical_total")
    timed_async(indexing_module, "bulk_insert", "build.gram_inserts")
    timed_sync(
        indexing_module,
        "_feed_docs",
        "build.gram_feed",
        rows=lambda builder, batch: len(batch),
        chars=lambda builder, batch: sum(len(c) for _id, c in batch),
    )
    timed_async(lexical_module, "bulk_insert", "lexical.inserts")
    original_builder = lexical_module.lexical_builder
    lexical_module.lexical_builder = lambda: TimedBuilder(original_builder())


def install_statement_counter(storage: DatabaseStorage) -> dict[str, int]:
    counts = {"statements": 0}

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        counts["statements"] += 1

    return counts


async def table_counts(storage: DatabaseStorage) -> dict[str, int]:
    t = storage._host.tables
    out: dict[str, int] = {}
    async with storage._host.engine.connect() as conn:
        for name in ("chunks", "posting_list", "lex_postings", "lex_df", "lex_docs"):
            out[name] = (await conn.execute(select(func.count()).select_from(getattr(t, name)))).scalar_one()
        out["files"] = (
            await conn.execute(
                select(func.count()).select_from(t.entry).where(t.entry.c.kind == "file", t.entry.c.deleted_at.is_(None))
            )
        ).scalar_one()
        out["not_encoded"] = (
            await conn.execute(
                select(func.count())
                .select_from(t.entry)
                .where(t.entry.c.encoded.is_(False), t.entry.c.deleted_at.is_(None), t.entry.c.kind == "file")
            )
        ).scalar_one()
        out["epoch"] = (await conn.execute(select(t.meta.c.current_gram_epoch))).scalar_one()
    return out


def load_generator():
    spec = importlib.util.spec_from_file_location("corpus02", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def dump_chunks(db_path: str, out_dir: FsPath, n: int) -> dict[str, int]:
    """A uniform sample of *n* chunk rows as one .txt body each, from a read-only connection."""
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    total = conn.execute("SELECT count(*) FROM vfs_chunks").fetchone()[0]
    # A multiplicative hash of the row id picks about n rows spread over the table.
    rows = conn.execute("SELECT content FROM vfs_chunks WHERE (id * 2654435761) % ? < ? ORDER BY id", (total, n)).fetchall()
    conn.close()
    nbytes = 0
    for i, (content,) in enumerate(rows):
        data = content.encode("utf-8")
        nbytes += len(data)
        (out_dir / f"{i:06d}.txt").write_bytes(data)
    return {"chunk_rows_in_store": total, "sampled": len(rows), "bytes": nbytes}


def cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


async def main() -> None:
    source, scratch, out_json = sys.argv[1], FsPath(sys.argv[2]), sys.argv[3]
    dump_n = int(sys.argv[sys.argv.index("--dump-chunks") + 1]) if "--dump-chunks" in sys.argv else 0
    report: dict[str, object] = {"source": source}
    store_dir = scratch / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(store_dir / "rebuild_100000.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)
    t0 = time.perf_counter()
    shutil.copyfile(source, db_path)
    report["copy_s"] = round(time.perf_counter() - t0, 2)
    report["db_bytes"] = os.path.getsize(db_path)
    print(f"copied {source} -> {db_path} in {report['copy_s']}s", flush=True)

    if dump_n:
        report["chunk_sample"] = dump_chunks(db_path, scratch / "bodies_c", dump_n)
        print(f"chunk sample: {report['chunk_sample']}", flush=True)

    install_timers()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db_path}")
    refused = await storage._host.ensure_ready()
    assert refused is None, refused
    statements = install_statement_counter(storage)
    report["before"] = await table_counts(storage)
    print(f"before: {report['before']}", flush=True)

    corpus = load_generator()
    path, content = corpus.document(0, salt=1)
    result = await storage.write(entries=[Entry(path=Path(path), content=content)], parents=True)
    assert result.success, result.errors
    report["dirtied"] = await table_counts(storage)
    print(f"after one write: not_encoded={report['dirtied']['not_encoded']}", flush=True)

    TIMERS.clear()
    statements["statements"] = 0
    cpu0 = cpu_seconds()
    t0 = time.perf_counter()
    result = await storage.reindex()
    wall = time.perf_counter() - t0
    cpu = cpu_seconds() - cpu0
    report["reindex"] = {
        "success": result.success,
        "wall_s": round(wall, 2),
        "process_cpu_s": round(cpu, 2),
        "statements": statements["statements"],
        "errors": [e.model_dump() if hasattr(e, "model_dump") else str(e) for e in result.errors],
    }
    report["after"] = await table_counts(storage)
    report["timers"] = {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in TIMERS.items()}
    print(f"reindex: wall={wall:.2f}s cpu={cpu:.2f}s statements={statements['statements']} success={result.success}", flush=True)
    for name, b in sorted(TIMERS.items()):
        print(f"  {name:36s} calls={b['calls']:6d} wall={b['wall_s']:9.3f}s rows={b['rows']:9d} chars={b['chars']}", flush=True)
    print(f"after: {report['after']}", flush=True)
    await storage.close()
    FsPath(out_json).write_text(json.dumps(report, indent=2, default=str) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
