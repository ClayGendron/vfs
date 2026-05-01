"""Benchmark recursive_text_split against the 5 largest text files in the repo.

Run before and after each optimization pass to confirm progress:

    uv run python "grep_glob research/bench_text_splitter.py"

Reports per-file: wall time (best of N), throughput (MB/s), chunks emitted,
peak heap delta (tracemalloc). Aggregate totals at the bottom.
"""

from __future__ import annotations

import gc
import statistics
import time
import tracemalloc
from pathlib import Path

from vfs.chunking import recursive_text_split

REPO_ROOT = Path(__file__).resolve().parent.parent

# Hand-picked from `find . -type f \( -name "*.py" -o -name "*.md" -o -name
# "*.ipynb" -o -name "*.sql" -o -name "*.json" -o -name "*.html" \) -exec wc
# -c {} +` excluding .git/dist/site/__pycache__. Largest non-binary code/doc
# files representative of what the chunker will see in practice.
TARGETS: list[Path] = [
    REPO_ROOT / "examples/postgres_repo_glob_grep.ipynb",
    REPO_ROOT / "docs/plans/everything_is_a_file.md",
    REPO_ROOT / "tests/test_database.py",
    REPO_ROOT / "src/vfs/backends/database.py",
    REPO_ROOT / "tests/test_write_pressure.py",
]

CHUNK_SIZE = 2048
OVERLAP = 256
ITERATIONS = 5  # best-of for wall-time stability


def bench_one(path: Path) -> dict[str, float | int]:
    content = path.read_text(encoding="utf-8")

    # Warm-up + correctness sanity.
    chunks = recursive_text_split(content, chunk_size=CHUNK_SIZE, overlap=OVERLAP)

    # Wall time (best of N).
    timings: list[float] = []
    for _ in range(ITERATIONS):
        gc.collect()
        start = time.perf_counter()
        recursive_text_split(content, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
        timings.append(time.perf_counter() - start)
    best = min(timings)
    median = statistics.median(timings)

    # Heap allocation. tracemalloc tracks Python-level allocations only —
    # close enough to compare two implementations of the same routine.
    gc.collect()
    tracemalloc.start()
    tracemalloc.clear_traces()
    snapshot_before = tracemalloc.take_snapshot()
    recursive_text_split(content, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    snapshot_after = tracemalloc.take_snapshot()
    diffs = snapshot_after.compare_to(snapshot_before, "filename")
    alloc_bytes = sum(stat.size_diff for stat in diffs if stat.size_diff > 0)
    tracemalloc.stop()

    bytes_in = len(content.encode("utf-8"))
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "size_bytes": bytes_in,
        "chunks": len(chunks),
        "best_ms": best * 1000.0,
        "median_ms": median * 1000.0,
        "throughput_mb_s": (bytes_in / 1_048_576) / best if best > 0 else 0.0,
        "alloc_kb": alloc_bytes / 1024.0,
    }


def main() -> None:
    results = [bench_one(path) for path in TARGETS]

    header = (
        f"{'file':55s} {'size':>10s} {'chunks':>7s} "
        f"{'best ms':>10s} {'median ms':>10s} {'MB/s':>8s} {'alloc KB':>10s}"
    )
    print(header)
    print("-" * len(header))
    for row in results:
        print(
            f"{row['path']:55s} "
            f"{row['size_bytes']:>10,d} "
            f"{row['chunks']:>7d} "
            f"{row['best_ms']:>10.2f} "
            f"{row['median_ms']:>10.2f} "
            f"{row['throughput_mb_s']:>8.1f} "
            f"{row['alloc_kb']:>10.1f}"
        )

    total_bytes = sum(int(r["size_bytes"]) for r in results)
    total_best_ms = sum(float(r["best_ms"]) for r in results)
    total_alloc = sum(float(r["alloc_kb"]) for r in results)
    total_chunks = sum(int(r["chunks"]) for r in results)

    print("-" * len(header))
    print(
        f"{'TOTAL':55s} "
        f"{total_bytes:>10,d} "
        f"{total_chunks:>7d} "
        f"{total_best_ms:>10.2f} "
        f"{'':>10s} "
        f"{(total_bytes / 1_048_576) / (total_best_ms / 1000) if total_best_ms > 0 else 0:>8.1f} "
        f"{total_alloc:>10.1f}"
    )
    print(
        f"\nconfig: chunk_size={CHUNK_SIZE} overlap={OVERLAP} "
        f"iterations={ITERATIONS} (best of)"
    )


if __name__ == "__main__":
    main()
