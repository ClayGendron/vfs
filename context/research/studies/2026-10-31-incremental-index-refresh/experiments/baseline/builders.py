"""Measurement F: CPU cost of building postings and a lexical index over just a dirty set, no database.

Feeds 100 / 500 / 2,000 / 6,000 synthetic docs into the real Rust builders and drains them; records wall
seconds, rows and blob bytes. These sizes approximate 5-, 15-, 30- and 60-minute deltas at the brief's
edit rate (20-100 edits/minute).
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from corpus import generate  # noqa: E402
from vfs.models.chunk import Chunk  # noqa: E402
from vfs.models.code_grams import folded_bytes  # noqa: E402
from vfs.models.lexical import lexical_builder  # noqa: E402
from vfs.models.postings import postings_builder  # noqa: E402
from vfs.paths import Path  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
POSTING_BATCH_BYTES = 1 << 20  # indexing._POSTING_BATCH_BYTES
LEX_ROW_CAP = 2000  # a row cap in the same spirit as the backend's lexical drain
SIZES = (100, 500, 2000, 6000)


def measure(n: int) -> dict:
    docs = [(i + 1, c) for i, (_, c) in enumerate(generate(n, salt=5))]
    content_bytes = sum(len(c.encode()) for _, c in docs)

    # Chunking (the split the reindex does before building), to show its share.
    t0 = time.perf_counter()
    pieces = Chunk.split_batch([(Path(f"/f{i}.md"), c, "md") for i, c in docs])
    chunk_s = time.perf_counter() - t0
    n_chunks = sum(len(p) for p in pieces)

    # Gram postings: fold + feed, then drain in 1 MB batches.
    t0 = time.perf_counter()
    pb = postings_builder()
    folded = [(i, folded_bytes(c)) for i, c in docs]
    fold_s = time.perf_counter() - t0
    for k in range(0, len(folded), 2000):
        pb.add_docs(folded[k : k + 2000])
    feed_s = time.perf_counter() - t0 - fold_s
    t1 = time.perf_counter()
    rows = blob_bytes = 0
    while (batch := pb.next_batch(POSTING_BATCH_BYTES)) is not None:
        rows += len(batch)
        blob_bytes += sum(len(b) for _, b, _ in batch)
    drain_s = time.perf_counter() - t1
    gram_total = time.perf_counter() - t0

    # Lexical: feed chunk texts (as the backend does: one doc per chunk row), finish, drain both tables.
    t0 = time.perf_counter()
    lb = lexical_builder()
    chunk_docs = []
    cid = 0
    for per_doc in pieces:
        for piece in per_doc:
            cid += 1
            chunk_docs.append((cid, piece.content))
    for k in range(0, len(chunk_docs), 2000):
        lb.add_docs(chunk_docs[k : k + 2000])
    n_docs, avg_dl = lb.finish()
    lex_feed_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    df_rows = df_bytes = 0
    while (batch := lb.next_df_batch(LEX_ROW_CAP)) is not None:
        df_rows += len(batch)
        df_bytes += sum(len(r[4]) for r in batch)
    block_rows = block_bytes = 0
    while (batch := lb.next_batch(LEX_ROW_CAP)) is not None:
        block_rows += len(batch)
        block_bytes += sum(len(r[3]) + len(r[4]) + len(r[5]) for r in batch)
    lex_drain_s = time.perf_counter() - t1
    lex_total = time.perf_counter() - t0

    return {
        "docs": n,
        "content_mb": round(content_bytes / 1e6, 2),
        "chunks": n_chunks,
        "chunk_split_s": round(chunk_s, 3),
        "gram_fold_s": round(fold_s, 3),
        "gram_feed_s": round(feed_s, 3),
        "gram_drain_s": round(drain_s, 3),
        "gram_total_s": round(gram_total, 3),
        "gram_rows": rows,
        "gram_blob_mb": round(blob_bytes / 1e6, 2),
        "lex_feed_finish_s": round(lex_feed_s, 3),
        "lex_drain_s": round(lex_drain_s, 3),
        "lex_total_s": round(lex_total, 3),
        "lex_n_docs": n_docs,
        "lex_avg_dl": round(avg_dl, 1),
        "lex_df_rows": df_rows,
        "lex_block_rows": block_rows,
        "lex_blob_mb": round((df_bytes + block_bytes) / 1e6, 2),
    }


if __name__ == "__main__":
    out = [measure(n) for n in SIZES]
    for r in out:
        print(json.dumps(r))
    with open(os.path.join(HERE, "results_builders.json"), "w") as f:
        json.dump(out, f, indent=1)
