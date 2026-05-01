"""Benchmark vfs.chunking.recursive_text_split vs LangChain's
``RecursiveCharacterTextSplitter`` on every markdown file in the repo.

Run:
    uv run --with langchain-text-splitters python "grep_glob research/bench_vs_langchain.py"

Reports per-file: ours best-of-N, LangChain best-of-N, ratio (LC/ours), chunk
count parity. Aggregate totals at the bottom.
"""

from __future__ import annotations

import gc
import statistics
import time
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from vfs.chunking import DEFAULT_SEPARATORS, recursive_text_split

REPO_ROOT = Path(__file__).resolve().parent.parent
CHUNK_SIZE = 2048
OVERLAP = 256
ITERATIONS = 5

EXCLUDE_PARTS = {".venv", "node_modules", ".git", "site", "dist", "__pycache__"}


def find_markdown_files() -> list[Path]:
    """Every committed-source markdown file under the repo, sorted by size desc."""
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*.md"):
        if any(part in EXCLUDE_PARTS for part in path.parts):
            continue
        if not path.is_file():
            continue
        files.append(path)
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    return files


def best_of(fn, content: str) -> tuple[float, float]:
    """Return ``(best_ms, median_ms)`` over ``ITERATIONS`` calls of ``fn(content)``."""
    timings: list[float] = []
    for _ in range(ITERATIONS):
        gc.collect()
        start = time.perf_counter()
        fn(content)
        timings.append(time.perf_counter() - start)
    return min(timings) * 1000.0, statistics.median(timings) * 1000.0


def make_lc_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=OVERLAP,
        separators=list(DEFAULT_SEPARATORS),
        keep_separator="start",  # match our left-edge separator semantics
        length_function=len,
        is_separator_regex=False,
    )


def main() -> None:
    files = find_markdown_files()
    if not files:
        print("no markdown files found")
        return

    print(f"corpus: {len(files)} markdown files, {sum(p.stat().st_size for p in files):,} bytes")
    print(f"config: chunk_size={CHUNK_SIZE} overlap={OVERLAP} iterations={ITERATIONS} (best of)\n")

    lc_splitter = make_lc_splitter()

    header = (
        f"{'file':60s} {'size':>9s} "
        f"{'ours':>10s} {'langchain':>10s} {'ratio':>7s} "
        f"{'ours #':>7s} {'lc #':>5s}"
    )
    print(header)
    print("-" * len(header))

    total_size = 0
    total_ours = 0.0
    total_lc = 0.0
    total_ours_chunks = 0
    total_lc_chunks = 0

    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        size = len(content.encode("utf-8"))
        if size == 0:
            continue

        ours_best, _ = best_of(
            lambda c: recursive_text_split(c, chunk_size=CHUNK_SIZE, overlap=OVERLAP),
            content,
        )
        lc_best, _ = best_of(lc_splitter.split_text, content)

        ours_chunks = recursive_text_split(content, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
        lc_chunks = lc_splitter.split_text(content)

        ratio = (lc_best / ours_best) if ours_best > 0 else float("inf")
        rel = path.relative_to(REPO_ROOT)
        rel_str = str(rel)
        if len(rel_str) > 60:
            rel_str = "..." + rel_str[-57:]
        print(
            f"{rel_str:60s} {size:>9,d} "
            f"{ours_best:>9.2f}ms {lc_best:>9.2f}ms {ratio:>6.1f}x "
            f"{len(ours_chunks):>7d} {len(lc_chunks):>5d}"
        )

        total_size += size
        total_ours += ours_best
        total_lc += lc_best
        total_ours_chunks += len(ours_chunks)
        total_lc_chunks += len(lc_chunks)

    print("-" * len(header))
    ratio_total = (total_lc / total_ours) if total_ours > 0 else float("inf")
    print(
        f"{'TOTAL':60s} {total_size:>9,d} "
        f"{total_ours:>9.2f}ms {total_lc:>9.2f}ms {ratio_total:>6.1f}x "
        f"{total_ours_chunks:>7d} {total_lc_chunks:>5d}"
    )

    ours_throughput = (total_size / 1_048_576) / (total_ours / 1000) if total_ours > 0 else 0
    lc_throughput = (total_size / 1_048_576) / (total_lc / 1000) if total_lc > 0 else 0
    print(f"\nours throughput     : {ours_throughput:>8.1f} MB/s")
    print(f"langchain throughput: {lc_throughput:>8.1f} MB/s")
    print(f"speedup             : {ratio_total:>8.1f}x")


if __name__ == "__main__":
    main()
