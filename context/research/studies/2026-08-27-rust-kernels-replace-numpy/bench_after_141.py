"""After spec 141: the shipped ``candidate_ids`` kernel on the full linux store.

The three-arm scripts monkeypatched internals spec 141 deleted (the
numpy ladder, ``grep_mod.np``); this one measures the product as it
ships. Site 2 is the live planner's exact blob choice per pattern fed
to ``vfs._native.candidate_ids`` — the ladder alone, then the ladder
meeting a 10 K-id allow-list — and the end-to-end rows are plain
``DatabaseStorage.grep`` calls. Compare against ``results/grep_sites.json``
and ``results/e2e_grep.json`` (the numpy rows) for the before figures.

    VFS_BENCH_DB=/path/to/landing_full.sqlite uv run python bench_after_141.py
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
import statistics
import time

from benchlib import DB, dump, machine, timed_ms

from vfs import _native
from vfs.models.code_grams import build_code_gram_query
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import grep as grep_mod
from vfs.storage.backends.database.indexing import current_epoch

PATTERNS = [
    ("rare_ident", "randomize_kstack_offset"),
    ("medium_ident", "kmalloc"),
    ("word_heavy", "pr_debug"),
    ("punct_neq_null", "!= NULL"),
    ("hot_ident", "return"),
    ("hot_alt", r"(mutex_lock|spin_lock)"),
]
E2E = [
    ("zero_hit", "xyzzy_no_such_symbol_42", {}),
    ("medium_ident", "kmalloc", {}),
    ("hot_ident", "return", {}),
    ("scoped_medium", "kmalloc", {"globs": ("/drivers/net/**",)}),
]
ALLOW = 10_000
E2E_RUNS = 5


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    host = storage._host
    tables, budget = host.tables, host.membership_budget
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    entry_ids = [r[0] for r in con.execute("SELECT id FROM vfs WHERE kind='file' AND encoded=1 ORDER BY id")]
    allow = sorted(random.Random(7).sample(entry_ids, ALLOW))

    sites = []
    async with host.session_factory() as session:
        epoch = await current_epoch(session, tables)
        for label, pattern in PATTERNS:
            plan = build_code_gram_query(pattern)
            groups = grep_mod._plan_groups(plan)
            grams = sorted({g for group in groups for g in group})
            meta = await grep_mod._posting_meta(session, tables, budget, epoch, grams)
            chosen = grep_mod._choose_grams(groups, meta)
            wanted = sorted({g for gc in chosen if gc for g in gc})
            blobs = await grep_mod._posting_blobs(session, tables, budget, epoch, wanted)
            fed = [[blobs[g] for g in gc] for gc in chosen if gc]
            postings = sum(meta[g].doc_count for gc in chosen if gc for g in gc)
            _ids, total = _native.candidate_ids(fed, None, 1 << 31)
            row = {
                "label": label,
                "pattern": pattern,
                "postings_decoded": postings,
                "candidates": total,
                "ladder_ms": timed_ms(lambda: _native.candidate_ids(fed, None, 1 << 31)),
                "ladder_capped_ms": timed_ms(lambda: _native.candidate_ids(fed, None, grep_mod.CANDIDATE_BUDGET)),
                f"allow{ALLOW}_survivors": _native.candidate_ids(fed, allow, 1 << 31)[1],
                f"allow{ALLOW}_ms": timed_ms(lambda: _native.candidate_ids(fed, allow, grep_mod.CANDIDATE_BUDGET)),
            }
            sites.append(row)
            print(
                f"{label:<15} cand={total:>7,} post={postings:>9,}  ladder={row['ladder_ms']:.3f} ms  "
                f"capped={row['ladder_capped_ms']:.3f} ms  allow={row[f'allow{ALLOW}_ms']:.3f} ms"
            )

    e2e = []
    for label, pattern, kwargs in E2E:
        await storage.grep(pattern=pattern, **kwargs)  # warm
        samples = []
        for _ in range(E2E_RUNS):
            t0 = time.perf_counter()
            result = await storage.grep(pattern=pattern, **kwargs)
            samples.append((time.perf_counter() - t0) * 1000.0)
        row = {
            "label": label,
            "pattern": pattern,
            "kwargs": {k: list(v) if isinstance(v, tuple) else v for k, v in kwargs.items()},
            "files": len(result.observations),
            "warnings": [e.message for e in result.errors] if result.errors else [],
            "total_ms": round(statistics.median(samples), 2),
        }
        e2e.append(row)
        print(f"e2e {label:<15} files={row['files']:>6,}  {row['total_ms']:.1f} ms  {row['warnings']}")
    await storage.close()
    dump("after-141.json", {"machine": machine(), "protocol": _native.PROTOCOL_VERSION, "sites": sites, "e2e": e2e})


if __name__ == "__main__":
    asyncio.run(main())
