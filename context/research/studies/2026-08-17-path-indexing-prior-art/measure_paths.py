"""Path-structure measurements over a built linux-tree store.

Companion to ``2026-08-17-path-indexing-prior-art.md`` §5. Points at
the SQLite store produced by the 2026-08-16 linux-grep-benchmark
harness (``studies/2026-08-16-linux-grep-benchmark/benchmark.py``
builds it) and reports the facts the memo cites: unique directory
segments and their doc frequencies, total segment-posting volume,
path-corpus size, full-corpus regex sweep timings, and the stored
extension distribution.

    uv run python measure_paths.py /path/to/linux.sqlite
"""

from __future__ import annotations

import re
import sqlite3
import statistics
import sys
import time
from collections import Counter

SWEEPS: tuple[tuple[str, str], ...] = (
    ("path-anchored glob (/drivers/net/**/*.c)", r"^/drivers/net/.*\.c$"),
    ("name-arm wildcard (*_test.c)", r"[^/\n]*_test\.c$"),
    ("name-arm glob (*.h)", r"[^/\n]*\.h$"),
)

SEGMENT_PROBES: tuple[str, ...] = ("drivers", "net", "ext4", "sched", "include", "Documentation")


def main(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    files = con.execute("select id, path from vfs where kind = 'file'").fetchall()
    con.close()
    print(f"files: {len(files)}")

    start = time.perf_counter()
    segment_docs: Counter[str] = Counter()
    for _entry_id, path in files:
        components = path.strip("/").split("/")
        for segment in set(components[:-1]):
            segment_docs[segment] += 1
    built_ms = (time.perf_counter() - start) * 1000
    frequencies = sorted(segment_docs.values(), reverse=True)
    postings = sum(frequencies)
    print(f"unique dir segments: {len(segment_docs)} (built in {built_ms:.0f} ms)")
    print(f"total segment postings: {postings} ({postings / len(files):.1f} per file)")
    print(f"top segments: {segment_docs.most_common(8)}")
    print(f"median doc-freq: {statistics.median(frequencies)}, p90: {frequencies[len(frequencies) // 10]}")
    for probe in SEGMENT_PROBES:
        print(f"  files under {probe!r}: {segment_docs.get(probe, 0)}")

    corpus = "\n".join(path for _entry_id, path in files)
    print(f"path corpus: {len(corpus) / 1e6:.1f} MB as one newline-joined blob")
    for label, pattern in SWEEPS:
        rx = re.compile(pattern, re.M)
        start = time.perf_counter()
        hits = sum(1 for _match in rx.finditer(corpus))
        print(f"  {label}: {(time.perf_counter() - start) * 1000:.1f} ms, {hits} hits")

    names = (path.rsplit("/", 1)[-1] for _entry_id, path in files)
    extensions = Counter(name.rsplit(".", 1)[-1] if "." in name else "" for name in names)
    print(f"top extensions: {extensions.most_common(6)}")


if __name__ == "__main__":
    main(sys.argv[1])
