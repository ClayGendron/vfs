"""Decision 5 reads U first: what does that read cost, and what does it grow with?

The read-only sandbox; vfs's grep runs corpus-wide (allow=None, the U-first step), with the candidate entry fetch and the
scan side stubbed to return nothing, so only the index side runs. Counted: posting bytes fetched, the chosen grams'
summed doc_count, U. Timed: the kernel call. Then today's defer rule is asked whether, for a scope of n files that the
range now states exactly, it would have skipped the blob fetch altogether.

    PYTHONPATH=<pinned src> uv run python r3_03_u_first_cost.py linux.db
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.storage.backends.database.scope import ScanNominees

DB = sys.argv[1]
C: dict = {}
real_blobs, real_meta, real_ext, real_choose = g._posting_blobs, g._posting_meta, g.extension, g._choose_grams


async def blobs(*a, **k):
    out = await real_blobs(*a, **k)
    C["bytes"] = sum(len(b) for b in out.values())
    C["blobs"] = len(out)
    return out


async def meta(*a, **k):
    out = await real_meta(*a, **k)
    C["meta"] = out
    return out


def choose(groups, m):
    chosen = real_choose(groups, m)
    C["chosen"] = chosen
    return chosen


class Rec:
    def __init__(self, r):
        self._r = r

    def __getattr__(self, n):
        return getattr(self._r, n)

    def candidate_ids(self, fed, allow, cap):
        t = time.perf_counter()
        ids, count = self._r.candidate_ids(fed, allow, cap)
        C.setdefault("kernel_ms", []).append((time.perf_counter() - t) * 1e3)
        C["U"] = count
        return ids, count


async def no_entries(*a, **k):
    return []


async def no_scan(*a, **k):
    return ScanNominees([], False)


g._posting_blobs, g._posting_meta, g._choose_grams = blobs, meta, choose
g.extension = lambda: Rec(real_ext())
g._entries_for_docs, g.entries_for_scan = no_entries, no_scan

PATTERNS = ["dentry_lru_isolate", "i_count", "kmalloc", "-EINVAL", "MODULE_LICENSE", "return 0;", "static int", "struct"]


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    try:
        print(f"{'pattern':20} {'U':>7} {'max df':>7} {'blob bytes':>11} {'kernel ms':>9}  defers at n=296 / 1,033 / 3,023")
        for pattern in PATTERNS:
            times = []
            for _ in range(6):
                C.clear()
                r = await fs.grep(pattern, case_mode="sensitive", output_mode="files")
                times.append(statistics.median(C["kernel_ms"]))
            chosen = [grp for grp in C["chosen"] if grp]
            maxdf = max(C["meta"][gram].doc_count for grp in chosen for gram in grp)
            defers = [g._ladder_defers(C["chosen"], C["meta"], n) for n in (296, 1033, 3023)]
            print(
                f"{pattern:20} {C['U']:>7} {maxdf:>7} {C['bytes']:>11,} {statistics.median(times[1:]):>9.2f}  {defers}"
                f"  errors={[e.message[:30] for e in r.errors]}"
            )
    finally:
        await fs.close()


asyncio.run(main())
