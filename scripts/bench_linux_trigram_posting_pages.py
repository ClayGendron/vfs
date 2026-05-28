"""Benchmark Postgres posting-page layouts with real Linux source trigrams.

This experiment uses files from a local Linux checkout as source data, extracts
VFS folded byte trigrams per chunk, and materializes compressed posting pages in
a fresh local Postgres database. It is meant to answer concrete storage/read
questions for Story 013's portable trigram index:

* How many posting rows do 1 KB / 2 KB / 4 KB / ... payload targets produce?
* When does Postgres TOAST the ``bytea`` payload table in practice?
* What does rarest-first read cost look like for real code-search literals?
* How expensive is staging append vs. append-only posting-page flush?
* How does Postgres ``bytea`` storage mode affect page-shaped postings?

Run:

    uv run --with asyncpg python scripts/bench_linux_trigram_posting_pages.py

Useful larger run:

    uv run --with asyncpg python scripts/bench_linux_trigram_posting_pages.py \
      --max-chunks 5000 --payload-targets 1024,2048,4096,8192,16384

The script creates and drops ``vfs_linux_trgm_bench`` unless ``--keep-db`` is
passed. Override the admin DSN with ``VFS_BENCH_ADMIN_DSN``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from vfs.code_grams import grams_for_fixed_string, unique_code_grams


ADMIN_DSN = os.environ.get("VFS_BENCH_ADMIN_DSN", "postgresql://localhost/postgres")
DEFAULT_LINUX_ROOT = "/Users/claygendron/Git/Repos/linux"
BENCH_DB = "vfs_linux_trgm_bench"

ACTION_ADD = 1
ENCODING_DELTA_VARINT = 1

CODE_SUFFIXES = {
    ".S",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".inc",
    ".lds",
    ".mk",
    ".pl",
    ".py",
    ".rs",
    ".sh",
    ".txt",
}

QUERY_LITERALS = (
    "static inline",
    "spin_lock",
    "module_init",
    "return -EINVAL",
    "struct file_operations",
    "copy_from_user",
    "EXPORT_SYMBOL",
    "for_each",
)


@dataclass(frozen=True)
class Corpus:
    chunks: int
    files_seen: int
    files_indexed: int
    skipped_binary: int
    skipped_decode: int
    skipped_large: int
    postings: int
    grams: int
    by_gram: dict[int, list[int]]


@dataclass(frozen=True)
class LayoutResult:
    payload_target: int
    block_rows: int
    load_seconds: float
    append_rows: int
    append_postings: int
    append_seconds: float
    read_seconds: float
    read_queries: int
    relation_size: str
    total_size: str
    toast_size: str
    avg_doc_count: float
    p95_doc_count: int
    avg_payload_bytes: float
    p95_payload_bytes: int
    max_payload_bytes: int
    toast_bytes: int


def encode_postings(doc_ids: list[int]) -> bytes:
    """Delta-gap + varint encode a sorted doc_id list, excluding the anchor."""
    out = bytearray()
    prev = doc_ids[0]
    for doc_id in doc_ids[1:]:
        gap = doc_id - prev
        while True:
            byte = gap & 0x7F
            gap >>= 7
            if gap:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
        prev = doc_id
    return bytes(out)


def decode_postings(min_doc_id: int, blob: bytes) -> list[int]:
    doc_ids = [min_doc_id]
    cur = min_doc_id
    gap = 0
    shift = 0
    for byte in blob:
        gap |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            cur += gap
            doc_ids.append(cur)
            gap = 0
            shift = 0
    return doc_ids


def varint_len(value: int) -> int:
    size = 1
    value >>= 7
    while value:
        size += 1
        value >>= 7
    return size


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        if path.suffix and path.suffix not in CODE_SUFFIXES:
            continue
        yield path


def iter_chunks(text: str, chunk_chars: int) -> Iterable[str]:
    if len(text) <= chunk_chars:
        yield text
        return
    for start in range(0, len(text), chunk_chars):
        yield text[start : start + chunk_chars]


def build_corpus(
    *,
    linux_root: Path,
    max_files: int,
    max_chunks: int,
    chunk_chars: int,
    max_file_bytes: int,
) -> Corpus:
    by_gram: dict[int, list[int]] = defaultdict(list)
    files_seen = 0
    files_indexed = 0
    skipped_binary = 0
    skipped_decode = 0
    skipped_large = 0
    doc_id = 1
    postings = 0

    for path in iter_source_files(linux_root):
        if files_seen >= max_files or doc_id > max_chunks:
            break
        files_seen += 1
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > max_file_bytes:
            skipped_large += 1
            continue
        if b"\0" in data:
            skipped_binary += 1
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped_decode += 1
            continue

        indexed_file = False
        for chunk in iter_chunks(text, chunk_chars):
            if doc_id > max_chunks:
                break
            grams = unique_code_grams(chunk, folded=True)
            if not grams:
                continue
            for gram in grams:
                by_gram[gram].append(doc_id)
            postings += len(grams)
            doc_id += 1
            indexed_file = True
        if indexed_file:
            files_indexed += 1

    return Corpus(
        chunks=doc_id - 1,
        files_seen=files_seen,
        files_indexed=files_indexed,
        skipped_binary=skipped_binary,
        skipped_decode=skipped_decode,
        skipped_large=skipped_large,
        postings=postings,
        grams=len(by_gram),
        by_gram=dict(by_gram),
    )


def blocks_for_gram(gram_key: int, doc_ids: list[int], payload_target: int) -> list[tuple]:
    rows = []
    current: list[int] = []
    current_bytes = 0
    for doc_id in doc_ids:
        extra_bytes = 0 if not current else varint_len(doc_id - current[-1])
        if current and current_bytes + extra_bytes > payload_target:
            rows.append(block_row(gram_key, current))
            current = [doc_id]
            current_bytes = 0
        else:
            current.append(doc_id)
            current_bytes += extra_bytes
    if current:
        rows.append(block_row(gram_key, current))
    return rows


def block_row(gram_key: int, doc_ids: list[int]) -> tuple:
    blob = encode_postings(doc_ids)
    return (
        gram_key,
        1,
        len(doc_ids),
        doc_ids[0],
        doc_ids[-1],
        ENCODING_DELTA_VARINT,
        len(blob),
        blob,
        True,
    )


def build_blocks(corpus: Corpus, payload_target: int) -> list[tuple]:
    rows: list[tuple] = []
    for gram_key, doc_ids in corpus.by_gram.items():
        rows.extend(blocks_for_gram(gram_key, doc_ids, payload_target))
    return rows


def split_by_doc_id(corpus: Corpus, cutoff_doc_id: int) -> tuple[Corpus, Corpus]:
    """Split a corpus into ``doc_id <= cutoff`` and ``doc_id > cutoff``."""
    left: dict[int, list[int]] = {}
    right: dict[int, list[int]] = {}
    left_postings = 0
    right_postings = 0
    for gram_key, doc_ids in corpus.by_gram.items():
        left_docs = [doc_id for doc_id in doc_ids if doc_id <= cutoff_doc_id]
        right_docs = [doc_id for doc_id in doc_ids if doc_id > cutoff_doc_id]
        if left_docs:
            left[gram_key] = left_docs
            left_postings += len(left_docs)
        if right_docs:
            right[gram_key] = right_docs
            right_postings += len(right_docs)

    left_chunks = min(corpus.chunks, cutoff_doc_id)
    right_chunks = max(0, corpus.chunks - cutoff_doc_id)
    return (
        Corpus(
            chunks=left_chunks,
            files_seen=corpus.files_seen,
            files_indexed=corpus.files_indexed,
            skipped_binary=corpus.skipped_binary,
            skipped_decode=corpus.skipped_decode,
            skipped_large=corpus.skipped_large,
            postings=left_postings,
            grams=len(left),
            by_gram=left,
        ),
        Corpus(
            chunks=right_chunks,
            files_seen=corpus.files_seen,
            files_indexed=corpus.files_indexed,
            skipped_binary=corpus.skipped_binary,
            skipped_decode=corpus.skipped_decode,
            skipped_large=corpus.skipped_large,
            postings=right_postings,
            grams=len(right),
            by_gram=right,
        ),
    )


DDL = """
CREATE TABLE posting_pages (
    page_id       BIGSERIAL PRIMARY KEY,
    gram_key      INTEGER  NOT NULL,
    batch_id      BIGINT   NOT NULL,
    doc_count     INTEGER  NOT NULL,
    min_doc_id    BIGINT   NOT NULL,
    max_doc_id    BIGINT   NOT NULL,
    encoding      SMALLINT NOT NULL,
    byte_count    INTEGER  NOT NULL,
    postings      BYTEA    NOT NULL,
    is_active     BOOLEAN  NOT NULL
);
CREATE INDEX ix_posting_pages_lookup
    ON posting_pages (gram_key, is_active, min_doc_id);
CREATE INDEX ix_posting_pages_range
    ON posting_pages (gram_key, is_active, max_doc_id);

CREATE TABLE staging (
    seq       BIGSERIAL PRIMARY KEY,
    batch_id  BIGINT       NOT NULL,
    gram_key  INTEGER      NOT NULL,
    entry_id  VARCHAR(36)  NOT NULL,
    doc_id    BIGINT,
    action    SMALLINT     NOT NULL
);
CREATE INDEX ix_staging_gram_entry ON staging (gram_key, entry_id, seq);
"""


async def create_database() -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {BENCH_DB} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {BENCH_DB}")
    finally:
        await admin.close()


async def drop_database() -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {BENCH_DB} WITH (FORCE)")
    finally:
        await admin.close()


def bench_dsn() -> str:
    return ADMIN_DSN.rsplit("/", 1)[0] + "/" + BENCH_DB


async def insert_blocks(conn: asyncpg.Connection, rows: list[tuple]) -> None:
    await conn.executemany(
        """INSERT INTO posting_pages
           (gram_key, batch_id, doc_count, min_doc_id, max_doc_id,
            encoding, byte_count, postings, is_active)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        rows,
    )


async def apply_storage_mode(conn: asyncpg.Connection, storage: str) -> None:
    if storage == "default":
        return
    storage_sql = {
        "plain": "PLAIN",
        "main": "MAIN",
        "external": "EXTERNAL",
        "extended": "EXTENDED",
    }[storage]
    await conn.execute(f"ALTER TABLE posting_pages ALTER COLUMN postings SET STORAGE {storage_sql}")


async def relation_sizes(conn: asyncpg.Connection) -> tuple[str, str, str, int]:
    row = await conn.fetchrow(
        """
        SELECT
          pg_size_pretty(pg_relation_size('posting_pages')) AS relation_size,
          pg_size_pretty(pg_total_relation_size('posting_pages')) AS total_size,
          pg_size_pretty(COALESCE(pg_total_relation_size(c.reltoastrelid), 0)) AS toast_size,
          COALESCE(pg_total_relation_size(c.reltoastrelid), 0) AS toast_bytes
        FROM pg_class c
        WHERE c.oid = 'posting_pages'::regclass
        """
    )
    return row["relation_size"], row["total_size"], row["toast_size"], row["toast_bytes"]


async def page_stats(conn: asyncpg.Connection) -> tuple[float, int, float, int, int]:
    row = await conn.fetchrow(
        """
        SELECT
          avg(doc_count)::float8 AS avg_doc_count,
          percentile_disc(0.95) WITHIN GROUP (ORDER BY doc_count) AS p95_doc_count,
          avg(byte_count)::float8 AS avg_payload_bytes,
          percentile_disc(0.95) WITHIN GROUP (ORDER BY byte_count) AS p95_payload_bytes,
          max(byte_count) AS max_payload_bytes
        FROM posting_pages
        """
    )
    return (
        float(row["avg_doc_count"] or 0),
        int(row["p95_doc_count"] or 0),
        float(row["avg_payload_bytes"] or 0),
        int(row["p95_payload_bytes"] or 0),
        int(row["max_payload_bytes"] or 0),
    )


async def fetch_docset(conn: asyncpg.Connection, gram_key: int) -> set[int]:
    rows = await conn.fetch(
        "SELECT min_doc_id, postings FROM posting_pages "
        "WHERE gram_key=$1 AND is_active ORDER BY min_doc_id",
        gram_key,
    )
    docs: set[int] = set()
    for row in rows:
        docs.update(decode_postings(row["min_doc_id"], row["postings"]))
    return docs


async def measure_reads(conn: asyncpg.Connection) -> tuple[float, int]:
    queries = 0
    t = time.perf_counter()
    for literal in QUERY_LITERALS:
        grams = grams_for_fixed_string(literal, folded=True)
        if not grams:
            continue
        stats = await conn.fetch(
            """
            SELECT gram_key, sum(doc_count)::bigint AS df
            FROM posting_pages
            WHERE gram_key = ANY($1::int[]) AND is_active
            GROUP BY gram_key
            ORDER BY df, gram_key
            """,
            sorted(grams),
        )
        if not stats:
            continue
        docset: set[int] | None = None
        for stat in stats[: min(4, len(stats))]:
            docs = await fetch_docset(conn, stat["gram_key"])
            docset = docs if docset is None else docset & docs
            if not docset:
                break
        queries += 1
    return time.perf_counter() - t, queries


async def measure_staging_append(
    conn: asyncpg.Connection,
    corpus: Corpus,
    limit: int,
) -> tuple[float, int]:
    rows = []
    for gram_key, doc_ids in corpus.by_gram.items():
        for _doc_id in doc_ids:
            rows.append((1, gram_key, str(uuid.uuid4()), None, ACTION_ADD))
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    await conn.execute("TRUNCATE staging RESTART IDENTITY")
    t = time.perf_counter()
    async with conn.transaction():
        await conn.executemany(
            "INSERT INTO staging (batch_id, gram_key, entry_id, doc_id, action) "
            "VALUES ($1,$2,$3,$4,$5)",
            rows,
        )
    return time.perf_counter() - t, len(rows)


async def run_layout(
    conn: asyncpg.Connection,
    *,
    corpus: Corpus,
    base_corpus: Corpus,
    append_corpus: Corpus,
    payload_target: int,
) -> LayoutResult:
    await conn.execute("TRUNCATE posting_pages RESTART IDENTITY")
    blocks = build_blocks(corpus, payload_target)

    t = time.perf_counter()
    async with conn.transaction():
        await insert_blocks(conn, blocks)
    load_seconds = time.perf_counter() - t

    await conn.execute("TRUNCATE posting_pages RESTART IDENTITY")
    base_blocks = build_blocks(base_corpus, payload_target)
    append_blocks = build_blocks(append_corpus, payload_target)
    async with conn.transaction():
        await insert_blocks(conn, base_blocks)
    t = time.perf_counter()
    async with conn.transaction():
        await insert_blocks(conn, append_blocks)
    append_seconds = time.perf_counter() - t

    read_seconds, read_queries = await measure_reads(conn)
    relation_size, total_size, toast_size, toast_bytes = await relation_sizes(conn)
    avg_doc_count, p95_doc_count, avg_payload, p95_payload, max_payload = await page_stats(conn)

    return LayoutResult(
        payload_target=payload_target,
        block_rows=len(blocks),
        load_seconds=load_seconds,
        append_rows=len(append_blocks),
        append_postings=append_corpus.postings,
        append_seconds=append_seconds,
        read_seconds=read_seconds,
        read_queries=read_queries,
        relation_size=relation_size,
        total_size=total_size,
        toast_size=toast_size,
        avg_doc_count=avg_doc_count,
        p95_doc_count=p95_doc_count,
        avg_payload_bytes=avg_payload,
        p95_payload_bytes=p95_payload,
        max_payload_bytes=max_payload,
        toast_bytes=toast_bytes,
    )


def parse_payload_targets(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linux-root", default=DEFAULT_LINUX_ROOT)
    parser.add_argument("--max-files", type=int, default=3000)
    parser.add_argument("--max-chunks", type=int, default=1500)
    parser.add_argument("--chunk-chars", type=int, default=8192)
    parser.add_argument("--max-file-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--payload-targets", default="1024,2048,4096,8192,16384,65536")
    parser.add_argument("--staging-rows", type=int, default=50_000)
    parser.add_argument("--append-docs", type=int, default=1000)
    parser.add_argument(
        "--storage",
        choices=("default", "plain", "main", "external", "extended"),
        default="default",
        help="Postgres storage mode for posting_pages.postings.",
    )
    parser.add_argument("--keep-db", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    linux_root = Path(args.linux_root)
    payload_targets = parse_payload_targets(args.payload_targets)

    print(f"Building corpus from {linux_root} ...")
    corpus = build_corpus(
        linux_root=linux_root,
        max_files=args.max_files,
        max_chunks=args.max_chunks,
        chunk_chars=args.chunk_chars,
        max_file_bytes=args.max_file_bytes,
    )
    doc_counts = [len(v) for v in corpus.by_gram.values()]
    print(
        f"Corpus: {corpus.chunks:,} chunks from {corpus.files_indexed:,}/{corpus.files_seen:,} files; "
        f"{corpus.postings:,} postings across {corpus.grams:,} grams"
    )
    print(
        f"Skips: binary={corpus.skipped_binary:,}, decode={corpus.skipped_decode:,}, "
        f"large={corpus.skipped_large:,}; gram df p50={int(statistics.median(doc_counts)):,}, "
        f"max={max(doc_counts):,}"
    )

    append_docs = min(args.append_docs, max(0, corpus.chunks - 1))
    base_corpus, append_corpus = split_by_doc_id(corpus, corpus.chunks - append_docs)
    print(
        f"Append batch: {append_corpus.chunks:,} chunks, {append_corpus.postings:,} postings, "
        f"{append_corpus.grams:,} grams"
    )

    await create_database()
    conn = await asyncpg.connect(bench_dsn())
    try:
        await conn.execute(DDL)
        await apply_storage_mode(conn, args.storage)
        staging_seconds, staging_rows = await measure_staging_append(
            conn,
            append_corpus,
            args.staging_rows,
        )
        print(
            f"Staging append: {staging_rows:,} rows in {staging_seconds:.3f}s "
            f"(storage={args.storage})"
        )

        results: list[LayoutResult] = []
        for target in payload_targets:
            print(f"Testing payload target {target:,} bytes ...")
            results.append(
                await run_layout(
                    conn,
                    corpus=corpus,
                    base_corpus=base_corpus,
                    append_corpus=append_corpus,
                    payload_target=target,
                )
            )

        print()
        print(
            "payload  blocks     load_s  append_s  append_rows  read_s  table     total     toast     "
            "avg_docs  p95_docs  avg_B  p95_B  max_B"
        )
        print("-" * 136)
        for r in results:
            print(
                f"{r.payload_target:>7,}  {r.block_rows:>7,}  {r.load_seconds:>7.3f}  "
                f"{r.append_seconds:>8.3f}  {r.append_rows:>11,}  "
                f"{r.read_seconds:>6.3f}  {r.relation_size:>8}  {r.total_size:>8}  "
                f"{r.toast_size:>8}  {r.avg_doc_count:>8.1f}  {r.p95_doc_count:>8,}  "
                f"{r.avg_payload_bytes:>5.0f}  {r.p95_payload_bytes:>5,}  {r.max_payload_bytes:>5,}"
            )

        print()
        print("Interpretation hints:")
        print("- If toast stays near 8192 bytes, payloads are effectively inline for this corpus.")
        print("- If toast jumps, that payload target is crossing Postgres's practical inline boundary.")
        print("- Read timings fetch/decode up to four rare grams per literal, rarest-first.")
        print("- Append flush writes only the final append-docs chunk batch as new immutable pages.")
    finally:
        await conn.close()
        if args.keep_db:
            print(f"Kept database {BENCH_DB}")
        else:
            await drop_database()


if __name__ == "__main__":
    asyncio.run(main())
