"""Time the lexical build's chunk scan directly, and measure bounded alternatives to it.

Extends study 02's rebuild harness (``../rebuild.py``): copies the clean
100,000-file store (SQLite) or opens a prepared schema (Postgres),
rewrites one file through ``write()`` so ``build_epoch`` rebuilds whole,
then times ``reindex()`` with ``_chunk_batches`` in ``lexical.py``
replaced, in this process only, by one of the variants below. Every
variant yields the same ``(id, entry_id, content)`` batches in ascending
id order; after the rebuild the four lexical tables are counted and
checksummed row by row so the variants can be compared for identical
epoch contents. Nothing under ``src/`` is edited.

Variants (``--variant``):
  baseline            the shipped keyset pages of 256 rows, every page execute timed
  keyset_N            the same shape with N rows a page (1024, 4096, 16384)
  twophase            all (id, entry_id) pairs drained first through a streaming
                      cursor over the join, then content by chunked ``id IN (...)``
                      under the dialect's membership budget; writes interleave
  twophase_1000       the same with the Oracle floor of 1,000 ids a probe
  stream_buffered     one streaming cursor over the full rows, yield_per 256,
                      ``lex_docs`` writes buffered until the cursor is exhausted
  prefilter_temp      qualifying entry_ids into a temp table once, then keyset
                      pages of 256 over chunks joined to the temp table
  prefilter_set       qualifying entry_ids into a Python set once, then keyset
                      pages of 256 over chunks alone, filtered in Python
  exists_subquery     keyset pages of 256 over chunks alone, the entry filter as
                      ``entry_id IN (SELECT ...)`` instead of a join
  scalar_subquery     keyset pages of 256 over chunks alone, the entry filter as a
                      correlated ``(SELECT 1 ...) = 1`` SQLite does not flatten

Usage:
  uv run python harness.py --engine sqlite --source <base db> --scratch <dir> --variant baseline --out <json>
  uv run python harness.py --engine postgres --url postgresql+asyncpg://... --schema <s> --variant baseline --out <json>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import platform
import resource
import shutil
import sqlite3
import statistics
import sys
import time
from functools import partial, wraps
from pathlib import Path as FsPath

from sqlalchemy import bindparam, event, func, insert, literal, select, text
from sqlalchemy.dialects import postgresql, sqlite

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import indexing as indexing_module
from vfs.storage.backends.database import lexical as lexical_module
from vfs.storage.backends.database.dialects import ByteBatcher, chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.offload import call_offloaded

REPO = FsPath(__file__).resolve().parents[6]
GENERATOR = REPO / "context/research/studies/2026-11-09-the-dirty-row-budgets-of-grep-and-glean/experiments/corpus.py"

TIMERS: dict[str, dict[str, float | int]] = {}
PAGES: list[dict[str, float | int]] = []
SCAN: dict[str, object] = {}
PROFILE = None
MEMBERSHIP_BUDGET = 0
PAGE_ROWS = 256
PROBE_SIZE = 0


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


class TimedBuilder:
    """The native lexical builder with add_docs timed on the offload thread."""

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

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install_timers() -> None:
    for name in ("chunk_dirty", "build_epoch", "publish_epoch", "reclaim_epochs"):
        timed_async(backend_module, name, f"phase.{name}")
    timed_async(indexing_module, "build_lexical_epoch", "build.lexical_total")
    timed_async(lexical_module, "bulk_insert", "lexical.inserts")
    original_builder = lexical_module.lexical_builder
    lexical_module.lexical_builder = lambda: TimedBuilder(original_builder())


def install_statement_counter(storage: DatabaseStorage) -> dict[str, int]:
    counts = {"statements": 0}

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        counts["statements"] += 1

    return counts


# ---------------------------------------------------------------------------
# The scan variants: each replaces lexical._chunk_batches for this process
# ---------------------------------------------------------------------------


def _record_page(wall: float, rows: int, chars: int) -> None:
    PAGES.append({"wall_s": wall, "rows": rows, "chars": chars})


async def _consume(batcher, rows, yield_sink):
    """Feed rows through the batcher, timing add and the consumer separately."""
    for row in rows:
        t0 = time.perf_counter()
        full = batcher.add((row[0], row[1], row[2]))
        bucket("scan.batcher_add")["wall_s"] += time.perf_counter() - t0
        bucket("scan.batcher_add")["rows"] += 1
        if full is not None:
            await yield_sink(full)


def covered_filter(tables):
    entry = tables.entry
    return (entry.c.chunked, entry.c.indexable, entry.c.deleted_at.is_(None))


def joined_page_statement(tables, page_rows: int):
    chunks, entry = tables.chunks, tables.entry
    return (
        select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(*covered_filter(tables))
        .order_by(chunks.c.id)
        .limit(page_rows)
    )


def make_keyset(page_rows: int, statement_of=joined_page_statement, row_filter=None):
    async def _chunk_batches(session, tables):
        scan = statement_of(tables, page_rows)
        batcher = ByteBatcher(lexical_module._doc_size, lexical_module._TOKENIZE_BATCH_BYTES)
        pending: list = []

        async def sink(full):
            pending.append(full)

        last = 0
        while True:
            t0 = time.perf_counter()
            page = (await session.execute(scan.where(tables.chunks.c.id > last))).all()
            wall = time.perf_counter() - t0
            if not page:
                _record_page(wall, 0, 0)
                break
            _record_page(wall, len(page), sum(len(r.content) for r in page))
            rows = page if row_filter is None else [r for r in page if row_filter(r)]
            SCAN["rows_dropped"] = SCAN.get("rows_dropped", 0) + (len(page) - len(rows))
            await _consume(batcher, rows, sink)
            last = page[-1].id
            while pending:
                full = pending.pop(0)
                t0 = time.perf_counter()
                yield full
                bucket("scan.yield")["wall_s"] += time.perf_counter() - t0
                bucket("scan.yield")["calls"] += 1
        final = batcher.flush()
        if final is not None:
            t0 = time.perf_counter()
            yield final
            bucket("scan.yield")["wall_s"] += time.perf_counter() - t0
            bucket("scan.yield")["calls"] += 1

    return _chunk_batches


def make_twophase(probe_size: int):
    async def _chunk_batches(session, tables):
        chunks, entry = tables.chunks, tables.entry
        ids_scan = (
            select(chunks.c.id, chunks.c.entry_id)
            .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
            .where(*covered_filter(tables))
            .order_by(chunks.c.id)
        )
        t0 = time.perf_counter()
        rss0 = rss_bytes()
        pairs: list[tuple[int, str]] = []
        async for row in await session.stream(ids_scan.execution_options(yield_per=256)):
            pairs.append((row.id, row.entry_id))
        SCAN["phase1_wall_s"] = time.perf_counter() - t0
        SCAN["phase1_pairs"] = len(pairs)
        SCAN["phase1_rss_delta_mb"] = round((rss_bytes() - rss0) / 2**20, 1)
        SCAN["phase1_getsizeof_mb"] = round(
            (sys.getsizeof(pairs) + sum(sys.getsizeof(p) + sys.getsizeof(p[0]) + sys.getsizeof(p[1]) for p in pairs)) / 2**20, 1
        )
        batcher = ByteBatcher(lexical_module._doc_size, lexical_module._TOKENIZE_BATCH_BYTES)
        pending: list = []

        async def sink(full):
            pending.append(full)

        fetch = select(chunks.c.id, chunks.c.entry_id, chunks.c.content).order_by(chunks.c.id)
        for probe in chunked(pairs, probe_size):
            ids = [p[0] for p in probe]
            t0 = time.perf_counter()
            page = (await session.execute(fetch.where(membership(chunks.c.id, ids, PROFILE)))).all()
            wall = time.perf_counter() - t0
            assert len(page) == len(ids), (len(page), len(ids))
            _record_page(wall, len(page), sum(len(r.content) for r in page))
            await _consume(batcher, page, sink)
            while pending:
                full = pending.pop(0)
                t0 = time.perf_counter()
                yield full
                bucket("scan.yield")["wall_s"] += time.perf_counter() - t0
                bucket("scan.yield")["calls"] += 1
        final = batcher.flush()
        if final is not None:
            t0 = time.perf_counter()
            yield final
            bucket("scan.yield")["wall_s"] += time.perf_counter() - t0
            bucket("scan.yield")["calls"] += 1

    return _chunk_batches


async def stream_buffered_chunk_batches(session, tables):
    """One streaming cursor over the full rows; the consumer's lex_docs writes are
    deferred (see ``buffered_build_lexical_epoch``) until the cursor is exhausted."""
    chunks, entry = tables.chunks, tables.entry
    scan = (
        select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(*covered_filter(tables))
        .order_by(chunks.c.id)
    )
    batcher = ByteBatcher(lexical_module._doc_size, lexical_module._TOKENIZE_BATCH_BYTES)
    pending: list = []

    async def sink(full):
        pending.append(full)

    t0 = time.perf_counter()
    rows_seen = 0
    chars = 0
    result = await session.stream(scan.execution_options(yield_per=256))
    async for partition in result.partitions(256):
        wall = time.perf_counter() - t0
        rows_seen += len(partition)
        page_chars = sum(len(r.content) for r in partition)
        chars += page_chars
        _record_page(wall, len(partition), page_chars)
        await _consume(batcher, partition, sink)
        while pending:
            full = pending.pop(0)
            t1 = time.perf_counter()
            yield full
            bucket("scan.yield")["wall_s"] += time.perf_counter() - t1
            bucket("scan.yield")["calls"] += 1
        t0 = time.perf_counter()
    final = batcher.flush()
    if final is not None:
        t1 = time.perf_counter()
        yield final
        bucket("scan.yield")["wall_s"] += time.perf_counter() - t1
        bucket("scan.yield")["calls"] += 1


async def buffered_build_lexical_epoch(session, tables, epoch, executor):
    """build_lexical_epoch with the lex_docs rows held until the scan's cursor is closed."""
    builder = lexical_module.lexical_builder()
    buffered: list[dict] = []
    async for batch in lexical_module._chunk_batches(session, tables):
        docs = [(chunk_id, content) for chunk_id, _entry_id, content in batch]
        lengths = await call_offloaded(executor, partial(builder.add_docs, docs))
        buffered.extend(
            {"epoch": epoch, "chunk_id": chunk_id, "entry_id": entry_id, "dl": dl}
            for (chunk_id, entry_id, _content), dl in zip(batch, lengths, strict=True)
        )
    SCAN["buffered_lex_docs_rows"] = len(buffered)
    SCAN["buffered_lex_docs_getsizeof_mb"] = round(
        (sys.getsizeof(buffered) + sum(sys.getsizeof(r) + sys.getsizeof(r["entry_id"]) + 2 * 28 for r in buffered)) / 2**20, 1
    )
    t0 = time.perf_counter()
    for page in chunked(buffered, lexical_module._LEXICAL_INSERT_ROWS):
        await lexical_module.bulk_insert(session, tables.lex_docs, list(page))
    SCAN["buffered_lex_docs_write_s"] = round(time.perf_counter() - t0, 3)
    n_docs, avg_dl = await call_offloaded(executor, builder.finish)
    stats = {"epoch": epoch, "n_docs": n_docs, "avg_dl": avg_dl, "k1": lexical_module.BM25_K1, "b": lexical_module.BM25_B}
    await session.execute(insert(tables.lex_stats), [stats])
    while (summaries := await call_offloaded(executor, partial(lexical_module._df_rows, builder, epoch))) is not None:
        await lexical_module.bulk_insert(session, tables.lex_df, summaries)
    while (blocks := await call_offloaded(executor, partial(lexical_module._block_rows, builder, epoch))) is not None:
        await lexical_module.bulk_insert(session, tables.lex_postings, blocks)


async def prefilter_temp_chunk_batches(session, tables):
    """Qualifying entry_ids into a temp table once; keyset pages join chunks to it."""
    chunks, entry = tables.chunks, tables.entry
    dialect = session.get_bind().dialect.name
    t0 = time.perf_counter()
    await session.execute(text("DROP TABLE IF EXISTS tmp_covered"))
    if dialect == "sqlite":
        await session.execute(text("CREATE TEMP TABLE tmp_covered (entry_id TEXT PRIMARY KEY)"))
        await session.execute(
            text(
                "INSERT INTO tmp_covered SELECT entry_id FROM vfs_entries "
                "WHERE chunked = 1 AND indexable = 1 AND deleted_at IS NULL"
            )
        )
    else:
        await session.execute(text("CREATE TEMP TABLE tmp_covered (entry_id VARCHAR(26) PRIMARY KEY)"))
        await session.execute(
            text(
                f"INSERT INTO tmp_covered SELECT entry_id FROM {entry.fullname} "
                "WHERE chunked AND indexable AND deleted_at IS NULL"
            )
        )
        await session.execute(text("ANALYZE tmp_covered"))
    SCAN["prefilter_wall_s"] = round(time.perf_counter() - t0, 3)
    SCAN["prefilter_rows"] = (await session.execute(text("SELECT count(*) FROM tmp_covered"))).scalar_one()
    covered = text("SELECT entry_id FROM tmp_covered").columns(entry_id=chunks.c.entry_id.type).subquery("tmp_covered")

    def statement_of(tables, page_rows):
        return (
            select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
            .select_from(chunks.join(covered, covered.c.entry_id == chunks.c.entry_id))
            .order_by(chunks.c.id)
            .limit(page_rows)
        )

    async for batch in make_keyset(PAGE_ROWS, statement_of)(session, tables):
        yield batch
    await session.execute(text("DROP TABLE IF EXISTS tmp_covered"))


async def prefilter_set_chunk_batches(session, tables):
    """Qualifying entry_ids into a Python set once; keyset pages over chunks alone, filtered here."""
    chunks, entry = tables.chunks, tables.entry
    t0 = time.perf_counter()
    rss0 = rss_bytes()
    covered: set[str] = set()
    async for row in await session.stream(
        select(entry.c.entry_id).where(*covered_filter(tables)).execution_options(yield_per=4096)
    ):
        covered.add(row.entry_id)
    SCAN["prefilter_wall_s"] = round(time.perf_counter() - t0, 3)
    SCAN["prefilter_rows"] = len(covered)
    SCAN["prefilter_rss_delta_mb"] = round((rss_bytes() - rss0) / 2**20, 1)
    SCAN["prefilter_getsizeof_mb"] = round((sys.getsizeof(covered) + sum(sys.getsizeof(e) for e in covered)) / 2**20, 1)

    def statement_of(tables, page_rows):
        return select(chunks.c.id, chunks.c.entry_id, chunks.c.content).order_by(chunks.c.id).limit(page_rows)

    async for batch in make_keyset(PAGE_ROWS, statement_of, row_filter=lambda r: r.entry_id in covered)(session, tables):
        yield batch


def exists_subquery_statement(tables, page_rows: int):
    chunks, entry = tables.chunks, tables.entry
    qualifying = select(entry.c.entry_id).where(*covered_filter(tables))
    return (
        select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
        .where(chunks.c.entry_id.in_(qualifying))
        .order_by(chunks.c.id)
        .limit(page_rows)
    )


def scalar_subquery_statement(tables, page_rows: int):
    """The entry filter as a correlated scalar subquery compared to 1: SQLite does not
    flatten this into a join, so no Bloom filter is built per execution."""
    chunks, entry = tables.chunks, tables.entry
    qualifies = (
        select(literal(1))
        .select_from(entry)
        .where(entry.c.entry_id == chunks.c.entry_id, *covered_filter(tables))
        .scalar_subquery()
    )
    return (
        select(chunks.c.id, chunks.c.entry_id, chunks.c.content)
        .where(qualifies == 1)
        .order_by(chunks.c.id)
        .limit(page_rows)
    )


def install_variant(name: str) -> None:
    global PAGE_ROWS, PROBE_SIZE
    if name == "baseline":
        lexical_module._chunk_batches = make_keyset(256)
    elif name.startswith("keyset_"):
        PAGE_ROWS = int(name.split("_", 1)[1])
        lexical_module._chunk_batches = make_keyset(PAGE_ROWS)
    elif name == "twophase":
        PROBE_SIZE = MEMBERSHIP_BUDGET
        lexical_module._chunk_batches = make_twophase(PROBE_SIZE)
    elif name.startswith("twophase_"):
        PROBE_SIZE = int(name.split("_", 1)[1])
        lexical_module._chunk_batches = make_twophase(PROBE_SIZE)
    elif name == "stream_buffered":
        lexical_module._chunk_batches = stream_buffered_chunk_batches
        indexing_module.build_lexical_epoch = buffered_build_lexical_epoch
    elif name == "prefilter_temp":
        lexical_module._chunk_batches = prefilter_temp_chunk_batches
    elif name == "prefilter_set":
        lexical_module._chunk_batches = prefilter_set_chunk_batches
    elif name == "exists_subquery":
        lexical_module._chunk_batches = make_keyset(256, exists_subquery_statement)
    elif name == "scalar_subquery":
        lexical_module._chunk_batches = make_keyset(256, scalar_subquery_statement)
    else:
        raise SystemExit(f"unknown variant {name}")


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------


def rss_bytes() -> int:
    # macOS reports ru_maxrss in bytes; Linux in KiB.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if platform.system() == "Darwin" else peak * 1024


def cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


async def table_counts(storage: DatabaseStorage) -> dict[str, int]:
    t = storage._host.tables
    out: dict[str, int] = {}
    async with storage._host.engine.connect() as conn:
        for name in ("chunks", "posting_list", "lex_postings", "lex_df", "lex_docs", "lex_stats"):
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


async def lexical_checksum(storage: DatabaseStorage, epoch: int) -> dict[str, dict[str, object]]:
    """Row counts and a SHA-256 over every row of the epoch's four lexical tables, in key order."""
    t = storage._host.tables
    specs = {
        "lex_docs": (t.lex_docs, [t.lex_docs.c.chunk_id, t.lex_docs.c.entry_id, t.lex_docs.c.dl], [t.lex_docs.c.chunk_id]),
        "lex_df": (
            t.lex_df,
            [t.lex_df.c.term, t.lex_df.c.df, t.lex_df.c.idf, t.lex_df.c.max_weight, t.lex_df.c.blocks],
            [t.lex_df.c.term],
        ),
        "lex_stats": (t.lex_stats, [t.lex_stats.c.n_docs, t.lex_stats.c.avg_dl, t.lex_stats.c.k1, t.lex_stats.c.b], []),
        "lex_postings": (
            t.lex_postings,
            [
                t.lex_postings.c.term,
                t.lex_postings.c.block_no,
                t.lex_postings.c.doc_count,
                t.lex_postings.c.doc_ids,
                t.lex_postings.c.tfs,
                t.lex_postings.c.dls,
            ],
            [t.lex_postings.c.term, t.lex_postings.c.block_no],
        ),
    }
    # Columns that carry chunk ids: left out of the second digest, so a store rebuilt in
    # place (Postgres, where each run's rewrite mints new chunk ids) can still be compared.
    id_bearing = {"chunk_id", "doc_ids", "blocks"}
    out: dict[str, dict[str, object]] = {}
    async with storage._host.engine.connect() as conn:
        for name, (table, columns, order) in specs.items():
            digest = hashlib.sha256()
            digest_no_ids = hashlib.sha256()
            count = 0
            stmt = select(*columns).where(table.c.epoch == epoch).order_by(*order)
            async for row in await conn.stream(stmt.execution_options(yield_per=10_000)):
                count += 1
                for key, value in zip(row._fields, row, strict=True):
                    encoded = bytes(value) if isinstance(value, (bytes, bytearray, memoryview)) else repr(value).encode()
                    digest.update(encoded)
                    digest.update(b"\x1f")
                    if key not in id_bearing:
                        digest_no_ids.update(encoded)
                        digest_no_ids.update(b"\x1f")
                digest.update(b"\x1e")
                digest_no_ids.update(b"\x1e")
            out[name] = {"rows": count, "sha256": digest.hexdigest(), "sha256_without_ids": digest_no_ids.hexdigest()}
    return out


def load_generator():
    spec = importlib.util.spec_from_file_location("corpus02", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[k]


def page_summary() -> dict[str, object]:
    walls = [p["wall_s"] for p in PAGES]
    rows = [p["rows"] for p in PAGES]
    chars = [p["chars"] for p in PAGES]
    nonempty = [p for p in PAGES if p["rows"]]
    return {
        "pages": len(PAGES),
        "nonempty_pages": len(nonempty),
        "rows": sum(rows),
        "chars": sum(chars),
        "scan_wall_s": round(sum(walls), 3),
        "page_wall_median_ms": round(1000 * statistics.median(walls), 3) if walls else 0,
        "page_wall_mean_ms": round(1000 * statistics.fmean(walls), 3) if walls else 0,
        "page_wall_p99_ms": round(1000 * percentile(walls, 0.99), 3),
        "page_wall_max_ms": round(1000 * max(walls), 3) if walls else 0,
        "page_rows_median": statistics.median(rows) if rows else 0,
        "page_chars_median": statistics.median(chars) if chars else 0,
        "page_chars_mean": round(statistics.fmean(chars), 0) if chars else 0,
        "first_10_pages_ms": [round(1000 * w, 2) for w in walls[:10]],
        "last_10_pages_ms": [round(1000 * w, 2) for w in walls[-10:]],
    }


def compiled_page_statement(tables, dialect_name: str) -> str:
    dialect = sqlite.dialect() if dialect_name == "sqlite" else postgresql.dialect()
    stmt = joined_page_statement(tables, 256).where(tables.chunks.c.id > bindparam("last", 0))
    return str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def prepare_sqlite(source: str, scratch: FsPath, report: dict) -> DatabaseStorage:
    store_dir = scratch / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(store_dir / "scan_100000.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)
    t0 = time.perf_counter()
    shutil.copyfile(source, db_path)
    report["copy_s"] = round(time.perf_counter() - t0, 2)
    report["db_bytes"] = os.path.getsize(db_path)
    report["sqlite_version"] = sqlite3.sqlite_version
    print(f"copied {source} -> {db_path} in {report['copy_s']}s", flush=True)
    return DatabaseStorage(url=f"sqlite+aiosqlite:///{db_path}")


async def prepare_postgres(url: str, schema: str, report: dict) -> DatabaseStorage:
    storage = DatabaseStorage(url=url, schema=schema)
    async with storage._host.engine.connect() as conn:
        report["postgres_version"] = (await conn.execute(text("SHOW server_version"))).scalar_one()
    return storage


async def main() -> None:
    global PROFILE, MEMBERSHIP_BUDGET
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("sqlite", "postgres"), required=True)
    parser.add_argument("--source")
    parser.add_argument("--scratch")
    parser.add_argument("--url", default="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs")
    parser.add_argument("--schema")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--salt", type=int, default=1, help="revision of document 0 written to dirty the store")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report: dict[str, object] = {
        "engine": args.engine,
        "variant": args.variant,
        "python": sys.version.split()[0],
        "machine": platform.machine(),
    }
    if args.engine == "sqlite":
        storage = await prepare_sqlite(args.source, FsPath(args.scratch), report)
    else:
        storage = await prepare_postgres(args.url, args.schema, report)
    refused = await storage._host.ensure_ready()
    assert refused is None, refused
    PROFILE = storage._host.profile
    MEMBERSHIP_BUDGET = storage._host.membership_budget
    report["membership_budget"] = MEMBERSHIP_BUDGET
    report["parameter_budget"] = storage._host.parameter_budget
    report["page_statement"] = compiled_page_statement(storage._host.tables, args.engine if args.engine == "sqlite" else "postgresql")

    install_variant(args.variant)
    install_timers()
    report["page_rows"] = PAGE_ROWS
    report["probe_size"] = PROBE_SIZE
    statements = install_statement_counter(storage)
    report["before"] = await table_counts(storage)
    print(f"before: {report['before']}", flush=True)

    corpus = load_generator()
    path, content = corpus.document(0, salt=args.salt)
    result = await storage.write(entries=[Entry(path=Path(path), content=content)], parents=True)
    assert result.success, result.errors
    report["salt"] = args.salt
    report["dirtied"] = await table_counts(storage)
    print(f"after one write: not_encoded={report['dirtied']['not_encoded']}", flush=True)

    TIMERS.clear()
    PAGES.clear()
    statements["statements"] = 0
    rss_before = rss_bytes()
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
    report["rss_peak_mb"] = round(rss_bytes() / 2**20, 1)
    report["rss_before_reindex_mb"] = round(rss_before / 2**20, 1)
    report["after"] = await table_counts(storage)
    report["timers"] = {
        k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in TIMERS.items()
    }
    report["scan"] = {**page_summary(), **SCAN}
    print(f"reindex: wall={wall:.2f}s cpu={cpu:.2f}s statements={statements['statements']} success={result.success}", flush=True)
    for name, b in sorted(TIMERS.items()):
        print(f"  {name:36s} calls={b['calls']:6d} wall={b['wall_s']:9.3f}s rows={b['rows']:9d} chars={b['chars']}", flush=True)
    print(f"scan: {json.dumps(report['scan'], default=str)}", flush=True)
    print(f"after: {report['after']}", flush=True)
    t0 = time.perf_counter()
    report["checksum"] = await lexical_checksum(storage, report["after"]["epoch"])
    report["checksum_wall_s"] = round(time.perf_counter() - t0, 2)
    print(f"checksum: {report['checksum']}", flush=True)
    await storage.close()
    FsPath(args.out).write_text(json.dumps(report, indent=2, default=str) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
