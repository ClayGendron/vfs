"""Benchmark: update the posting list directly vs. append to a staging table.

Question this answers: *do we even need the staging (delta-log) table?* Story 013
ships `staging → flush → posting blocks`: the write path appends cheap deltas, and
a background flush folds them into immutable, delta+varint-encoded posting blocks.
The alternative is to skip staging and fold new grams into the durable posting list
inline on every write. This script measures the per-write cost of each, against a
real durable store.

Workload (faithful to story 013 §5):
  * 1,000,000 existing (gram_key, doc_id) postings, encoded into immutable blocks
    (min_doc_id raw anchor + delta-gap varint, bounded by BLOCK_CAP doc_ids).
  * 50,000 new postings from freshly-chunked docs. Per §5.3 doc_ids are a stable,
    monotonic auto-increment — every new doc_id is GREATER than all existing ones.

Three measurements, each from the identical starting state (Postgres):
  A  — staging append: bulk INSERT 50k delta rows. No read of the posting list.
       This is what the MVP write path does today.
  B1 — inline full CoW merge: read the affected grams' active blocks, decode, union
       the new doc_ids, re-split + re-encode, retire old blocks, insert new. The
       general "maintain the posting list now" path.
  B2 — inline append-only fast path: exploit monotonic doc_ids — new ids exceed
       every existing one, so just encode one fresh block per affected gram and
       insert it; never decode or rewrite existing blocks.

Run (asyncpg is in the `postgres` extra):
    uv run --with asyncpg python scripts/bench_posting_update_vs_staging.py

Override the admin connection with VFS_BENCH_ADMIN_DSN
(default: postgresql://localhost/postgres). A throwaway database
`vfs_posting_bench` is created and dropped each run.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid

import asyncpg

# ---------------------------------------------------------------------------
# Workload parameters
# ---------------------------------------------------------------------------

NUM_GRAMS = 16_384          # distinct gram_keys (skewed; common trigrams recur)
GRAMS_PER_DOC = 150         # distinct grams per chunk/doc
TARGET_EXISTING = 1_000_000  # existing (gram, doc) postings in the durable store
TARGET_NEW = 50_000          # new postings to integrate (one write batch)
BLOCK_CAP = 128             # max doc_ids per posting block (story 013 §5.1)
BATCH_ID = 1

ADMIN_DSN = os.environ.get("VFS_BENCH_ADMIN_DSN", "postgresql://localhost/postgres")
BENCH_DB = "vfs_posting_bench"

ACTION_ADD = 1
ENCODING_DELTA_VARINT = 1

random.seed(1337)


# ---------------------------------------------------------------------------
# delta+varint posting-block codec (story 013 §5.4)
# ---------------------------------------------------------------------------


def _skewed_gram() -> int:
    """Sample a gram_key skewed toward low keys, so block sizes vary realistically."""
    return int(NUM_GRAMS * (random.random() ** 1.5)) % NUM_GRAMS


def encode_postings(doc_ids: list[int]) -> bytes:
    """Delta-gap + varint encode a sorted doc_id list (excludes the min anchor)."""
    out = bytearray()
    prev = doc_ids[0]
    for d in doc_ids[1:]:
        gap = d - prev
        while True:
            byte = gap & 0x7F
            gap >>= 7
            if gap:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
        prev = d
    return bytes(out)


def decode_postings(min_doc_id: int, blob: bytes) -> list[int]:
    """Inverse of :func:`encode_postings`."""
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


def blocks_for_gram(gram_key: int, doc_ids: list[int]) -> list[tuple]:
    """Split a gram's sorted doc_ids into encoded block rows (BLOCK_CAP each)."""
    rows = []
    for start in range(0, len(doc_ids), BLOCK_CAP):
        chunk = doc_ids[start : start + BLOCK_CAP]
        rows.append(
            (
                gram_key,
                BATCH_ID,
                len(chunk),
                chunk[0],
                chunk[-1],
                ENCODING_DELTA_VARINT,
                encode_postings(chunk),
                True,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------


def generate_postings(start_doc: int, target: int) -> tuple[dict[int, list[int]], int]:
    """Assign monotonically increasing doc_ids to skewed grams.

    Returns ``({gram_key: [sorted doc_ids]}, next_doc_id)``. doc_ids ascend with
    the doc loop, so each gram's list is naturally sorted.
    """
    by_gram: dict[int, list[int]] = {}
    doc_id = start_doc
    count = 0
    while count < target:
        grams = set()
        while len(grams) < GRAMS_PER_DOC:
            grams.add(_skewed_gram())
        for g in grams:
            by_gram.setdefault(g, []).append(doc_id)
            count += 1
            if count >= target:
                break
        doc_id += 1
    return by_gram, doc_id


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE posting_blocks (
    block_id    BIGSERIAL PRIMARY KEY,
    gram_key    INTEGER  NOT NULL,
    batch_id    BIGINT   NOT NULL,
    doc_count   INTEGER  NOT NULL,
    min_doc_id  BIGINT   NOT NULL,
    max_doc_id  BIGINT   NOT NULL,
    encoding    SMALLINT NOT NULL,
    postings    BYTEA    NOT NULL,
    is_active   BOOLEAN  NOT NULL
);
CREATE INDEX ix_pb_gram_active ON posting_blocks (gram_key, is_active, min_doc_id);
CREATE INDEX ix_pb_batch ON posting_blocks (batch_id);

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


async def insert_blocks(conn: asyncpg.Connection, block_rows: list[tuple]) -> None:
    await conn.executemany(
        """INSERT INTO posting_blocks
           (gram_key, batch_id, doc_count, min_doc_id, max_doc_id, encoding, postings, is_active)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
        block_rows,
    )


async def reset_posting_blocks(conn: asyncpg.Connection, original_blocks: list[tuple]) -> None:
    """Restore the posting table to its pristine 1M-posting state."""
    await conn.execute("TRUNCATE posting_blocks RESTART IDENTITY")
    await insert_blocks(conn, original_blocks)


# ---------------------------------------------------------------------------
# The three measured approaches
# ---------------------------------------------------------------------------


async def measure_staging_append(
    conn: asyncpg.Connection,
    new_postings: list[tuple[int, int]],
) -> float:
    """A — append 50k deltas to staging. doc_id NULL for adds (resolved at flush)."""
    rows = [(BATCH_ID, gram, str(uuid.uuid4()), None, ACTION_ADD) for gram, _doc in new_postings]
    await conn.execute("TRUNCATE staging RESTART IDENTITY")
    t = time.perf_counter()
    async with conn.transaction():
        await conn.executemany(
            "INSERT INTO staging (batch_id, gram_key, entry_id, doc_id, action) VALUES ($1,$2,$3,$4,$5)",
            rows,
        )
    return time.perf_counter() - t


async def measure_inline_merge(
    conn: asyncpg.Connection,
    new_by_gram: dict[int, list[int]],
) -> tuple[float, int, int]:
    """B1 — full copy-on-write merge of new doc_ids into the durable posting list."""
    affected = sorted(new_by_gram)
    t = time.perf_counter()
    async with conn.transaction():
        existing_rows = await conn.fetch(
            "SELECT block_id, gram_key, min_doc_id, postings FROM posting_blocks "
            "WHERE gram_key = ANY($1::int[]) AND is_active",
            affected,
        )
        existing_by_gram: dict[int, list[int]] = {}
        retire_ids: list[int] = []
        for r in existing_rows:
            retire_ids.append(r["block_id"])
            existing_by_gram.setdefault(r["gram_key"], []).extend(
                decode_postings(r["min_doc_id"], r["postings"])
            )

        new_blocks: list[tuple] = []
        for gram, new_docs in new_by_gram.items():
            merged = sorted(set(existing_by_gram.get(gram, [])) | set(new_docs))
            new_blocks.extend(blocks_for_gram(gram, merged))

        if retire_ids:
            await conn.execute(
                "UPDATE posting_blocks SET is_active = false WHERE block_id = ANY($1::bigint[])",
                retire_ids,
            )
        await insert_blocks(conn, new_blocks)
    return time.perf_counter() - t, len(affected), len(new_blocks)


async def measure_inline_append(
    conn: asyncpg.Connection,
    new_by_gram: dict[int, list[int]],
) -> tuple[float, int]:
    """B2 — append-only fast path: new doc_ids > all existing, so just add new blocks."""
    t = time.perf_counter()
    async with conn.transaction():
        new_blocks: list[tuple] = []
        for gram, new_docs in new_by_gram.items():
            new_blocks.extend(blocks_for_gram(gram, sorted(new_docs)))
        await insert_blocks(conn, new_blocks)
    return time.perf_counter() - t, len(new_blocks)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run() -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f"DROP DATABASE IF EXISTS {BENCH_DB} WITH (FORCE)")
    await admin.execute(f"CREATE DATABASE {BENCH_DB}")
    await admin.close()

    target = ADMIN_DSN.rsplit("/", 1)[0] + "/" + BENCH_DB
    conn = await asyncpg.connect(target)
    try:
        await conn.execute(DDL)

        print("Generating workload ...")
        existing_by_gram, next_doc = generate_postings(start_doc=1, target=TARGET_EXISTING)
        total_existing = sum(len(v) for v in existing_by_gram.values())

        original_blocks: list[tuple] = []
        for gram, docs in existing_by_gram.items():
            original_blocks.extend(blocks_for_gram(gram, docs))

        new_by_gram, _ = generate_postings(start_doc=next_doc, target=TARGET_NEW)
        new_postings = [(g, d) for g, docs in new_by_gram.items() for d in docs]
        total_new = len(new_postings)

        print("Loading durable posting store ...")
        await insert_blocks(conn, original_blocks)

        size = await conn.fetchval("SELECT pg_size_pretty(pg_total_relation_size('posting_blocks'))")
        print(
            f"\nDurable store: {total_existing:,} postings across "
            f"{len(existing_by_gram):,} grams in {len(original_blocks):,} blocks ({size})"
        )
        print(
            f"New batch:     {total_new:,} postings touching "
            f"{len(new_by_gram):,} distinct grams "
            f"(doc_ids {next_doc:,}+ — all > existing max)\n"
        )

        # A — staging append
        a = await measure_staging_append(conn, new_postings)

        # B1 — inline full CoW merge (reset first)
        await reset_posting_blocks(conn, original_blocks)
        b1, affected, b1_blocks = await measure_inline_merge(conn, new_by_gram)

        # B2 — inline append-only (reset first)
        await reset_posting_blocks(conn, original_blocks)
        b2, b2_blocks = await measure_inline_append(conn, new_by_gram)

        print(f"{'Approach':<46}{'Time':>10}   Notes")
        print("-" * 80)
        print(f"{'A  staging append (insert 50k deltas)':<46}{a:>9.3f}s   no posting-list read")
        print(
            f"{'B1 inline merge (read+decode+re-encode+CoW)':<46}{b1:>9.3f}s   "
            f"{affected:,} grams, {b1_blocks:,} blocks rewritten"
        )
        print(
            f"{'B2 inline append (monotonic doc_id fast path)':<46}{b2:>9.3f}s   "
            f"{b2_blocks:,} new blocks, 0 rewritten"
        )
        print("-" * 80)
        print(f"B1 / A = {b1 / a:6.1f}x      B2 / A = {b2 / a:6.1f}x")
    finally:
        await conn.close()
        admin = await asyncpg.connect(ADMIN_DSN)
        await admin.execute(f"DROP DATABASE IF EXISTS {BENCH_DB} WITH (FORCE)")
        await admin.close()


if __name__ == "__main__":
    asyncio.run(run())
