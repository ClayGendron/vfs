"""Build the gram posting index for a corpus tier into SQLite.

Two-phase, bounded-memory (codesearch's external-sort discipline):

Phase 1 — stream docs in id order; per doc, numpy-extract the distinct
folded byte trigrams; append (gram_low16, doc_id) records to one of 256
bucket files keyed by the gram's top byte.

Phase 2 — per bucket: load, sort by (gram, doc), group into segments,
bulk-encode delta+varint blobs, compute exact delta+gamma sizes, insert
posting rows. The posting store is epoch-immutable: built once, read-only.

Run: uv run python .../build_index_sqlite.py <N>
"""

from __future__ import annotations

import resource
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from spikelib import (  # noqa: E402
    DATA_DIR,
    MAX_DOC_GRAMS,
    fold_norm_bytes,
    gamma_bytes_per_segment,
    gaps_from_segmented_docs,
    unique_grams_np,
    varint_encode_segments,
)

N_BUCKETS = 256
DOC_BATCH = 5_000


def phase1(n_docs: int, bucket_dir: Path, doubled: bool = False) -> dict[str, float | int]:
    """doubled=True indexes the corpus twice (ids offset by n_docs) to reach
    ~1M rows: posting volumes stay honest, gram diversity stays flat."""
    corpus = sqlite3.connect(DATA_DIR / "corpus.db")
    handles = [(bucket_dir / f"b{b:03d}.bin").open("wb") for b in range(N_BUCKETS)]
    buffers: list[list[np.ndarray]] = [[] for _ in range(N_BUCKETS)]
    buffered = 0
    t0 = time.monotonic()
    stats = {"docs": 0, "skipped_grams": 0, "pairs": 0, "content_bytes": 0}

    def flush() -> None:
        nonlocal buffered
        for b in range(N_BUCKETS):
            if buffers[b]:
                arr = np.concatenate(buffers[b])
                handles[b].write(arr.tobytes())
                buffers[b].clear()
        buffered = 0

    passes = 2 if doubled else 1
    for pass_i in range(passes):
      for start in range(0, n_docs, DOC_BATCH):
        rows = corpus.execute(
            "SELECT id, content FROM docs WHERE id >= ? AND id < ? ORDER BY id",
            (start, min(start + DOC_BATCH, n_docs)),
        ).fetchall()
        if not rows:
            break
        for raw_id, content in rows:
            doc_id = raw_id + pass_i * n_docs
            data = fold_norm_bytes(content)
            grams = unique_grams_np(data)
            if len(grams) == 0:
                continue
            if len(grams) > MAX_DOC_GRAMS:
                stats["skipped_grams"] += 1
                continue
            stats["docs"] += 1
            stats["pairs"] += len(grams)
            stats["content_bytes"] += len(data)
            # Record: (gram & 0xFFFF) << 32 | doc_id, bucketed by gram >> 16.
            rec = ((grams.astype(np.uint64) & np.uint64(0xFFFF)) << np.uint64(32)) | np.uint64(doc_id)
            tops = (grams >> np.uint16(16)).astype(np.uint16)
            order = np.argsort(tops, kind="stable")
            rec = rec[order]
            tops_sorted = tops[order]
            bounds = np.searchsorted(tops_sorted, np.arange(N_BUCKETS + 1), side="left")
            for b in range(N_BUCKETS):
                lo, hi = bounds[b], bounds[b + 1]
                if hi > lo:
                    buffers[b].append(rec[lo:hi])
            buffered += len(grams)
        if buffered >= 30_000_000:
            flush()
        if start % 100_000 == 0 and start:
            print(f"  phase1 {start}/{n_docs} docs, {time.monotonic() - t0:.0f}s", flush=True)
    flush()
    for h in handles:
        h.close()
    corpus.close()
    stats["phase1_s"] = round(time.monotonic() - t0, 1)
    return stats


def phase2(bucket_dir: Path, index_path: Path) -> dict[str, float | int]:
    index_path.unlink(missing_ok=True)
    conn = sqlite3.connect(index_path)
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA page_size = 8192;
        CREATE TABLE posting_list (
            gram INTEGER PRIMARY KEY,
            doc_count INTEGER NOT NULL,
            byte_size INTEGER NOT NULL,
            gamma_size INTEGER NOT NULL,
            postings BLOB NOT NULL
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    t0 = time.monotonic()
    stats = {"grams": 0, "posting_bytes": 0, "gamma_bytes": 0, "max_doc_count": 0}
    for b in range(N_BUCKETS):
        f = bucket_dir / f"b{b:03d}.bin"
        raw = np.fromfile(f, dtype=np.uint64)
        if len(raw) == 0:
            continue
        raw.sort()  # key = gram_low << 32 | doc_id: sorts by (gram, doc)
        gram_low = (raw >> np.uint64(32)).astype(np.uint32)
        docs = (raw & np.uint64(0xFFFFFFFF)).astype(np.uint32)
        uniq, seg_starts = np.unique(gram_low, return_index=True)
        gaps = gaps_from_segmented_docs(docs.astype(np.int64), seg_starts)
        blob, offsets = varint_encode_segments(gaps, seg_starts)
        counts = np.empty(len(uniq), dtype=np.int64)
        counts[:-1] = seg_starts[1:] - seg_starts[:-1]
        counts[-1] = len(docs) - seg_starts[-1]
        rows = []
        for i, g_low in enumerate(uniq):
            gram = (b << 16) | int(g_low)
            lo, hi = int(offsets[i]), int(offsets[i + 1])
            seg_lo = int(seg_starts[i])
            seg_hi = seg_lo + int(counts[i])
            gsize = gamma_bytes_per_segment(gaps[seg_lo:seg_hi])
            rows.append((gram, int(counts[i]), hi - lo, gsize, blob[lo:hi]))
        conn.executemany("INSERT INTO posting_list VALUES (?,?,?,?,?)", rows)
        conn.commit()
        stats["grams"] += len(uniq)
        stats["posting_bytes"] += len(blob)
        stats["gamma_bytes"] += sum(r[3] for r in rows)
        stats["max_doc_count"] = max(stats["max_doc_count"], int(counts.max()))
        if b % 64 == 0:
            print(f"  phase2 bucket {b}/256, {time.monotonic() - t0:.0f}s", flush=True)
    stats["phase2_s"] = round(time.monotonic() - t0, 1)
    return stats, conn


def main() -> None:
    n_docs = int(sys.argv[1])
    doubled = "--double" in sys.argv
    tier = n_docs * 2 if doubled else n_docs
    bucket_dir = DATA_DIR / f"buckets_{tier}"
    bucket_dir.mkdir(parents=True, exist_ok=True)
    index_path = DATA_DIR / f"gram_index_{tier}.db"

    print(f"building gram index for tier N={tier} (doubled={doubled})", flush=True)
    s1 = phase1(n_docs, bucket_dir, doubled=doubled)
    print(f"phase1 done: {s1}", flush=True)
    s2, conn = phase2(bucket_dir, index_path)
    print(f"phase2 done: {s2}", flush=True)

    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20)
    meta = {**s1, **s2, "peak_rss_mb": round(peak_mb)}
    conn.executemany(
        "INSERT OR REPLACE INTO meta VALUES (?,?)",
        [(k, str(v)) for k, v in meta.items()],
    )
    conn.commit()
    conn.close()
    for f in bucket_dir.iterdir():
        f.unlink()
    bucket_dir.rmdir()
    size_mb = index_path.stat().st_size / (1 << 20)
    print(f"DONE tier {tier}: index {size_mb:.0f} MB, meta {meta}", flush=True)


if __name__ == "__main__":
    main()
