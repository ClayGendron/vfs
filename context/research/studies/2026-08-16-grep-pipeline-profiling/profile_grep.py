"""Stage attribution for the grep read path on the linux-scale index.

Companion to the 2026-08-16 linux benchmark: reuses its built sqlite
store (``WORKDIR`` env must point at the benchmark scratch holding
``linux.sqlite``) and profiles four query shapes through the public
``DatabaseStorage.grep``:

- the zero-hit row (attributes the fixed per-call floor),
- a selective literal (the healthy baseline),
- a verify-heavy word row (the verify-stage cost split),
- the wrapped-wildcard pathology (why it overruns the wall budget).

Two instruments per query: cProfile cumulative times bucketed into
pipeline stages (index candidate fetch / overlay scan / content fetch /
verify / result assembly), and counters recorded by wrapping the module
functions (candidate doc ids, entry rows from each tier, entries
verified). Wrapping is read-only observation — the wrapped functions
are restored before the process exits.

Run:  WORKDIR=/path/to/linux-bench uv run python \
      context/research/studies/2026-08-16-grep-pipeline-profiling/profile_grep.py
"""

from __future__ import annotations

import asyncio
import cProfile
import os
import pstats
import sys
import time
from pathlib import Path as OsPath

import vfs.storage.backends.database.grep as grep_mod
from vfs.storage.backends.database import DatabaseStorage

WORKDIR = OsPath(os.environ["WORKDIR"])

QUERIES = (
    ("zero-hit", "xyzzy_no_such_symbol_42", {}),
    ("selective", "randomize_kstack_offset", {}),
    ("word-heavy", "pr_debug", {"word_regexp": True}),
    ("wrapped wildcard", ".*alloc_page.*", {}),
)

# cumtime buckets: stage label -> function names inside grep's modules.
STAGES = {
    "index: posting meta+blobs": {"_posting_meta", "_posting_blobs", "_doc_ids_for_plan", "_index_doc_ids"},
    "index: decode+intersect": {"decode_postings"},
    "index: doc->entry rows": {"_entries_for_docs"},
    "overlay: scan nomination": {"_entries_for_scan"},
    "content fetch": {"_content_for_entries"},
    "verify (regex over lines)": {"verify"},
    "result assembly": {"_observe_hit"},
}

counters: dict[str, int] = {}


def wrap_counters() -> None:
    original_docs = grep_mod._index_doc_ids
    original_entries = grep_mod._entries_for_docs
    original_scan = grep_mod._entries_for_scan

    async def counting_docs(*args: object, **kwargs: object):
        ids = await original_docs(*args, **kwargs)
        counters["candidate doc ids"] = int(ids.size)
        return ids

    async def counting_entries(*args: object, **kwargs: object):
        rows = await original_entries(*args, **kwargs)
        counters["index-tier entry rows"] = len(rows)
        return rows

    async def counting_scan(*args: object, **kwargs: object):
        nominated = await original_scan(*args, **kwargs)
        counters["overlay-tier entry rows"] = len(nominated.rows)
        return nominated

    grep_mod._index_doc_ids = counting_docs
    grep_mod._entries_for_docs = counting_entries
    grep_mod._entries_for_scan = counting_scan


def stage_table(stats: pstats.Stats, total: float) -> None:
    rows = []
    for label, names in STAGES.items():
        cum = sum(v[3] for k, v in stats.stats.items() if k[2] in names)  # ty: ignore[unresolved-attribute]
        if cum:
            rows.append((cum, label))
    for cum, label in sorted(rows, reverse=True):
        print(f"    {label:<28} {cum:>8.2f}s  ({100 * cum / total:>4.1f}%)")


async def main() -> int:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{WORKDIR}/linux.sqlite")
    wrap_counters()
    await storage.grep(pattern="warmup_query_zzz")  # connection + pool warmup

    for label, pattern, kwargs in QUERIES:
        counters.clear()
        profiler = cProfile.Profile()
        start = time.perf_counter()
        profiler.enable()
        result = await storage.grep(pattern=pattern, **kwargs)
        profiler.disable()
        total = time.perf_counter() - start
        hits = sum(len(o.matches or ()) for o in result.observations)
        warnings = [e.message.split(";")[0] for e in result.errors]
        print(f"\n== {label}: {pattern!r}  {total * 1000:.0f}ms, {len(result.observations)} files / {hits} lines")
        for key, value in counters.items():
            print(f"    {key:<28} {value:>8}")
        for message in warnings:
            print(f"    warning: {message}")
        stats = pstats.Stats(profiler)
        stage_table(stats, total)
        print("    top raw cumtime:")
        stats.sort_stats("cumulative")
        for key, value in list(stats.stats.items())[:60]:  # ty: ignore[unresolved-attribute]
            file, line, name = key
            if "vfs" in file and value[3] > 0.05:
                print(f"      {value[3]:>7.2f}s  {name}  ({OsPath(file).name}:{line})")
    await storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
