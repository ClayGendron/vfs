"""Term-shape economics over a built linux-tree store.

Companion to ``2026-08-17-path-indexing-prior-art.md`` §8. For each
candidate path-term shape (directory segments, ancestor prefixes,
basename terms, path trigrams) this measures posting volume and
vocabulary, the posting rows a subtree rename must touch, the cost of
intersecting a segment posting with a content-candidate id set, and
the cost of maintaining segment postings synchronously (bulk-batch
insert, single-file write, hot-segment rename UPDATE) in a scratch
SQLite database.

    uv run python measure_shapes.py /path/to/linux.sqlite
"""

from __future__ import annotations

import random
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

RENAME_TARGETS: tuple[str, ...] = ("/drivers", "/drivers/net", "/fs/ext4", "/kernel/sched")
INTERSECT_PROBES: tuple[str, ...] = ("ext4", "sched", "net", "drivers")
CONTENT_CANDIDATES = 25_000
ETL_BATCH_FILES = 10_000
SEGMENTS_PER_FILE = 4


def path_trigrams(path: str) -> set[bytes]:
    folded = path.lower().encode()
    return {folded[i : i + 3] for i in range(len(folded) - 2)}


def measure_volumes(files: list[tuple[int, str]]) -> dict[str, list[int]]:
    """Posting volume and vocabulary per shape; returns segment postings."""
    seg_rows = pref_rows = tri_rows = 0
    seg_vocab: set[str] = set()
    pref_vocab: set[str] = set()
    tri_vocab: set[bytes] = set()
    base_vocab: set[str] = set()
    seg_postings: dict[str, list[int]] = {}
    for entry_id, path in files:
        parts = path.strip("/").split("/")
        dirs = parts[:-1]
        segments = set(dirs)
        seg_rows += len(segments)
        seg_vocab |= segments
        for segment in segments:
            seg_postings.setdefault(segment, []).append(entry_id)
        for depth in range(1, len(dirs) + 1):
            pref_vocab.add("/" + "/".join(dirs[:depth]))
        pref_rows += len(dirs)
        base_vocab.add(parts[-1])
        grams = path_trigrams(path)
        tri_rows += len(grams)
        tri_vocab |= grams
    n = len(files)
    print(f"{'shape':20s} {'rows':>12s} {'rows/file':>10s} {'vocab':>9s}")
    print(f"{'dir segments':20s} {seg_rows:>12,} {seg_rows / n:>10.1f} {len(seg_vocab):>9,}")
    print(f"{'ancestor prefixes':20s} {pref_rows:>12,} {pref_rows / n:>10.1f} {len(pref_vocab):>9,}")
    print(f"{'basename terms':20s} {n:>12,} {1.0:>10.1f} {len(base_vocab):>9,}")
    print(f"{'path trigrams':20s} {tri_rows:>12,} {tri_rows / n:>10.1f} {len(tri_vocab):>9,}")
    return seg_postings


def measure_cascades(files: list[tuple[int, str]]) -> None:
    """Posting rows a subtree rename must delete+insert (or UPDATE), per shape."""
    print(f"\n{'renamed dir':22s} {'descendants':>11s} {'segments':>9s} {'prefixes':>9s} {'trigrams':>10s}")
    for target in RENAME_TARGETS:
        prefix = target + "/"
        segment = target.rsplit("/", 1)[-1]
        depth = len(target.strip("/").split("/"))
        descendants = [(fid, p) for fid, p in files if p.startswith(prefix)]
        seg = sum(1 for _f, p in descendants if p.strip("/").split("/")[:-1].count(segment) == 1)
        pref = sum(max(0, len(p.strip("/").split("/")) - depth) for _f, p in descendants)
        tri = sum(len(path_trigrams(p)) for _f, p in descendants)
        print(f"{target:22s} {len(descendants):>11,} {seg:>9,} {pref:>9,} {tri:>10,}")


def measure_intersection(files: list[tuple[int, str]], seg_postings: dict[str, list[int]]) -> None:
    """Sorted-array intersection: content candidates x one segment posting."""
    rng = np.random.default_rng(7)
    all_ids = np.array(sorted(fid for fid, _p in files), dtype=np.int64)
    content = np.sort(rng.choice(all_ids, size=CONTENT_CANDIDATES, replace=False))
    print(f"\nintersection ({CONTENT_CANDIDATES:,} content candidates x segment posting):")
    for probe in INTERSECT_PROBES:
        posting = np.array(sorted(seg_postings[probe]), dtype=np.int64)
        start = time.perf_counter()
        for _ in range(100):
            survivors = content[np.isin(content, posting, assume_unique=True)]
        per_call_ms = (time.perf_counter() - start) / 100 * 1000
        print(f"  {probe:10s} |posting|={len(posting):>6,} -> {per_call_ms:6.3f} ms, {len(survivors)} survivors")


def measure_maintenance(hot_segment_rows: int) -> None:
    """Synchronous segment-posting maintenance costs in a scratch SQLite db."""
    random.seed(7)
    segments = [f"seg{i}" for i in range(3000)]
    with tempfile.TemporaryDirectory() as tmp:
        con = sqlite3.connect(str(Path(tmp) / "postings.sqlite"))
        con.execute(
            "create table seg_postings (segment text not null, entry_id integer not null,"
            " primary key (segment, entry_id)) without rowid"
        )
        preload = list({(random.choice(segments), i) for i in range(1, 93_761) for _ in range(SEGMENTS_PER_FILE)})
        con.executemany("insert or ignore into seg_postings values (?, ?)", preload)
        con.executemany(
            "insert or ignore into seg_postings values ('hot', ?)", [(i,) for i in range(1, hot_segment_rows + 1)]
        )
        con.commit()

        batch = list({(random.choice(segments), 200_000 + i) for i in range(ETL_BATCH_FILES) for _ in range(SEGMENTS_PER_FILE)})
        start = time.perf_counter()
        con.executemany("insert into seg_postings values (?, ?)", batch)
        con.commit()
        print(f"\n{ETL_BATCH_FILES:,}-file batch ({len(batch):,} posting rows): {(time.perf_counter() - start) * 1000:.1f} ms")

        start = time.perf_counter()
        for i in range(100):
            con.execute("begin")
            rows = [(random.choice(segments), 500_000 + i) for _ in range(SEGMENTS_PER_FILE)]
            con.executemany("insert or ignore into seg_postings values (?, ?)", rows)
            con.commit()
        print(f"single-file write ({SEGMENTS_PER_FILE} rows, own tx): {(time.perf_counter() - start) / 100 * 1000:.2f} ms")

        start = time.perf_counter()
        moved = con.execute("update seg_postings set segment = 'hot2' where segment = 'hot'").rowcount
        con.commit()
        print(f"hot-segment rename via UPDATE ({moved:,} rows): {(time.perf_counter() - start) * 1000:.1f} ms")
        con.close()


def main(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    files = con.execute("select id, path from vfs where kind = 'file'").fetchall()
    con.close()
    print(f"files: {len(files)}")
    seg_postings = measure_volumes(files)
    measure_cascades(files)
    measure_intersection(files, seg_postings)
    widest = max((len(ids) for ids in seg_postings.values()), default=0)
    measure_maintenance(widest)


if __name__ == "__main__":
    main(sys.argv[1])
