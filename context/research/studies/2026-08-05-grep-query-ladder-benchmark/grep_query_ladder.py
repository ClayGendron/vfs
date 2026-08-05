"""Rerunnable grep query-ladder benchmark through the live pipeline.

The 072 spike's query ladder measured a hand-rolled schema; this
harness re-measures the same pattern classes through the **live**
``DatabaseStorage`` — reindex build, the posting ladder, the refusal
gate, the budget case, and the scan tier for calibration — so the
numbers stay reproducible as the pipeline evolves.

Shape: a deterministic synthetic code corpus (default 10,000 docs,
``DOCS=n`` env to change) seeded into two sqlite stores — one
reindexed (index tier), one left dirty (scan tier). Each ladder
pattern runs on both, median of three, reporting latency, rows, and
whether the budget truncation flag fired. Refused patterns report the
refusal plus their ``allow_scan=True`` timing.

Landed-run record (2026-08-05, 10K docs / ~9 MB, sqlite file store,
M-series laptop): reindex build 4.7 s. Index tier: zero-hit 2.7 ms,
rare 5.3 ms / 10 rows, medium 31 ms / 500 rows, hot phrase
66 ms / 1,250 rows, punct 31 ms / 500 rows, regex 31 ms / 500 rows,
wrapped regex 29 ms / 334 rows, folded 33 ms / 500 rows; ultra-hot
``return`` 236 ms / 5,000 rows with **no** truncation at this scale
(the ~10K-candidate budget case needs the spike's ~1M tier to trip).
Scan tier: 243–442 ms across the same patterns — the index wins
8–90x on selective patterns here, and the gap widens with corpus
size (the spike measured 30–700x at the 990K tier). Refusals: ``ab``
and ``medium_ident_a|ab`` refuse classified in ~0.1 ms; their
``allow_scan`` runs land in scan-tier territory (244 / 308 ms).

Run:  uv run python context/research/studies/2026-08-05-grep-query-ladder-benchmark/grep_query_ladder.py
"""

from __future__ import annotations

import asyncio
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path as OsPath

from vfs.models import Entry
from vfs.paths import Path
from vfs.results import Severity
from vfs.storage.backends.database import DatabaseStorage

DOCS = int(os.environ.get("DOCS", "10000"))
ITERATIONS = 3
BATCH = 1_000

# (label, pattern, kwargs) — the spike's ladder classes on this corpus.
LADDER = (
    ("zero-hit", "xyzzy_unlikely_sentinel_42", {}),
    ("rare", "rare_sentinel_needle", {}),
    ("medium", "medium_ident_alpha", {}),
    ("hot phrase", "def __init__", {}),
    ("punct", "!= NULL", {"fixed_strings": True}),
    ("regex", r"static\s+int\s+\w+_probe", {}),
    ("wrapped regex", ".*alloc_page.*", {}),
    ("folded", "(?i)Mutex_Lock", {}),
    ("ultra-hot (budget)", "return", {}),
)

REFUSED = (
    ("sub-3-byte", "ab"),
    ("short branch", "medium_ident_a|ab"),
)


def corpus() -> list[Entry]:
    rng = random.Random(42)
    entries = []
    for i in range(DOCS):
        lines = [f"# module {i}", "def __init__(self):" if i % 8 == 0 else f"def handler_{i}(self):"]
        for j in range(25):
            lines.append(f"    value_{j} = compute_{rng.randrange(1000)}(input_{j})")
        if i % 2 == 0:
            lines.append("    return value_0")
        if i % 20 == 0:
            lines.append("    medium_ident_alpha = probe(ptr != NULL)")
            lines.append("static int device_probe(void)")
        if i % 30 == 0:
            lines.append("    page = alloc_page(mask)")
        if i % 20 == 5:
            lines.append("    mutex_lock(&lock)" if i % 40 == 5 else "    Mutex_Lock(&lock)")
        if i % 1000 == 7:
            lines.append("    rare_sentinel_needle = True")
        entries.append(Entry(path=Path(f"/src/pkg{i % 100:03}/mod_{i:05}.py"), content="\n".join(lines)))
    return entries


async def seed(url: str, entries: list[Entry]) -> DatabaseStorage:
    storage = DatabaseStorage(url=url)
    for start in range(0, len(entries), BATCH):
        result = await storage.write(entries=entries[start : start + BATCH], parents=True)
        assert result.success is True, result.errors
    return storage


async def measure(storage: DatabaseStorage, pattern: str, kwargs: dict) -> tuple[float, int, bool, bool]:
    times, rows, truncated, refused = [], 0, False, False
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        result = await storage.grep(pattern=pattern, **kwargs)
        times.append(time.perf_counter() - start)
        rows = len(result.observations)
        truncated = any(e.severity is Severity.warning for e in result.errors)
        refused = not result.success
    return statistics.median(times), rows, truncated, refused


async def main() -> int:
    scratch = OsPath(tempfile.mkdtemp(prefix="vfs-grep-ladder-"))
    entries = corpus()
    print(f"corpus: {DOCS} docs, ~{sum(len(e.content or '') for e in entries) >> 20} MB")
    indexed = await seed(f"sqlite+aiosqlite:///{scratch}/indexed.sqlite", entries)
    scan = await seed(f"sqlite+aiosqlite:///{scratch}/scan.sqlite", entries)
    start = time.perf_counter()
    assert (await indexed.reindex()).success is True
    print(f"reindex build: {time.perf_counter() - start:.1f} s\n")

    print(f"{'class':<20} {'pattern':<28} {'index':>10} {'scan':>10}  rows  flags")
    for label, pattern, kwargs in LADDER:
        ims, irows, itrunc, irefused = await measure(indexed, pattern, kwargs)
        sms, _srows, strunc, _srefused = await measure(scan, pattern, kwargs)
        flags = " ".join(f for f, on in (("truncated", itrunc or strunc), ("REFUSED", irefused)) if on)
        print(f"{label:<20} {pattern:<28} {ims * 1000:>8.1f}ms {sms * 1000:>8.1f}ms {irows:>5}  {flags}")

    print()
    for label, pattern in REFUSED:
        rms, _, _, refused = await measure(indexed, pattern, {})
        assert refused, f"{pattern!r} was expected to refuse"
        oms, orows, otrunc, _ = await measure(indexed, pattern, {"allow_scan": True})
        flags = "truncated" if otrunc else ""
        print(
            f"refused: {label:<13} {pattern:<28} refusal {rms * 1000:.1f}ms, "
            f"allow_scan {oms * 1000:.1f}ms / {orows} rows {flags}"
        )
    await indexed.close()
    await scan.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
