"""glean latency for callers with partial access, against the whole-mount fast path.

A caller whose rights cover the whole mount scores with the stored
statistics. Every other caller pays for exact visible-set statistics:
a visible corpus count, every index block of every query term read and
filtered to visible chunks, the visible chunk list, and the vector leg
once per clause. This script measures that price.

The corpus is deterministic: ``TOPS`` top folders, each holding
``FOLDERS`` folders of ``FILES`` files. Bodies draw from a Zipf
vocabulary, so ``w0000`` sits in nearly every file; three planted
words give known document frequencies (``zrare`` in 25 files, ``zmid``
in 2%, ``zhalf`` in 50%). Callers separate the two things that could
cost: how much of the mount they see, and how many grants (filter
arms) their rights compile to.

    uv run --no-sync python bench.py --engine sqlite --tops 10 --folders 100 --files 50
    VFS_TEST_POSTGRES_URL=... uv run --no-sync python bench.py --engine postgres ...

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import tempfile
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.authority import Authority, Principal
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.rights import RightsCache, resolve_authority, visibility_clauses

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = Authority.system()
VOCAB = 5_000
WORDS_PER_FILE = 150
QUERIES = {
    "rare (25 files)": "zrare",
    "mid (2%)": "zmid",
    "half (50%)": "zhalf",
    "common (~all)": "w0000",
    "mixed 4 words": "zrare zmid zhalf w0000",
}


def corpus(tops: int, folders: int, files: int, seed: int = 58) -> list[Entry]:
    rng = random.Random(seed)
    weights = [1 / (rank + 1) for rank in range(VOCAB)]
    vocab = [f"w{rank:04d}" for rank in range(VOCAB)]
    paths = [f"/t{t:02d}/f{f:03d}/doc{n:03d}.md" for t in range(tops) for f in range(folders) for n in range(files)]
    rare = set(rng.sample(range(len(paths)), 25))
    mid = set(rng.sample(range(len(paths)), max(1, len(paths) // 50)))
    half = set(rng.sample(range(len(paths)), len(paths) // 2))
    entries = []
    for i, path in enumerate(paths):
        words = rng.choices(vocab, weights=weights, k=WORDS_PER_FILE)
        words += [w for w, bag in (("zrare", rare), ("zmid", mid), ("zhalf", half)) if i in bag]
        rng.shuffle(words)
        entries.append(Entry(path=Path(path), content=" ".join(words)))
    return entries


def callers(tops: int, folders: int) -> dict[str, list[str]]:
    """Caller label → the prefixes it is granted ``read`` on."""
    every_folder = [f"/t{t:02d}/f{f:03d}" for t in range(tops) for f in range(folders)]
    spread = every_folder[:: max(1, len(every_folder) // max(1, len(every_folder) // 10))]
    half_folders = every_folder[::2]
    return {
        "whole (fast path)": ["/"],
        "50% via 5 grants": [f"/t{t:02d}" for t in range(0, tops, 2)],
        f"50% via {len(half_folders)} grants": half_folders,
        "10% via 1 grant": ["/t00"],
        f"10% via {len(spread)} grants": spread,
        "1 folder (0.1%)": [every_folder[0]],
    }


async def run(engine: str, tops: int, folders: int, files: int, reps: int) -> None:
    table_name = f"vfs_{uuid4().hex[:10]}"
    tmp = tempfile.mkdtemp(prefix="vfs-glean-bench-")
    url = f"sqlite+aiosqlite:///{tmp}/vfs.sqlite" if engine == "sqlite" else os.environ["VFS_TEST_POSTGRES_URL"]
    storage = DatabaseStorage(url=url, table_name=table_name, embedder=HashEmbeddingProvider())
    lines: list[str] = []
    try:
        entries = corpus(tops, folders, files)
        t0 = time.perf_counter()
        for start in range(0, len(entries), 5_000):
            result = await storage.write(entries=entries[start : start + 5_000], parents=True, authority=SYSTEM)
            assert result.success, result.errors[:2]
        t_write = time.perf_counter() - t0
        t0 = time.perf_counter()
        assert (await storage.reindex()).success
        t_index = time.perf_counter() - t0
        assert (await storage.posture(path=Path("/"), posture="private", authority=SYSTEM)).success
        grants = callers(tops, folders)
        for n, (label, prefixes) in enumerate(grants.items()):
            for prefix in prefixes:
                ok = await storage.grant(path=Path(prefix), principal=f"c{n}", level="read", authority=SYSTEM)
                assert ok.success, ok.errors
        header = (f"## {engine} — {len(entries):,} files ({tops} × {folders} × {files}), "
                  f"write {t_write:.0f}s, reindex {t_index:.0f}s, median of {reps} warm runs, limit 10\n")
        print(header, flush=True)
        lines.append(header)

        statements = 0

        def count(*_: Any) -> None:
            nonlocal statements
            statements += 1

        sync_engine = storage._host.engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", count)
        host = storage._host
        table = ["| caller | clauses | " + " | ".join(QUERIES) + " |", "|---|---|" + "---|" * len(QUERIES)]
        for n, label in enumerate(grants):
            who = Authority.of(Principal(f"c{n}"))
            async with host.session_factory() as session:
                resolved = await resolve_authority(
                    session, host.tables, host.profile, host.membership_budget, who, RightsCache()
                )
            assert not isinstance(resolved, Exception)
            clauses = visibility_clauses(host.tables.entry, resolved.read, host.profile, host.parameter_budget)
            cells = []
            for query in QUERIES.values():
                samples = []
                hits = 0
                for r in range(reps + 1):
                    statements = 0
                    t0 = time.perf_counter()
                    result = await storage.glean(query=query, limit=10, authority=who)
                    dt = (time.perf_counter() - t0) * 1000
                    assert result.success, result.errors[:2]
                    if r == 0:
                        hits = len(result.observations)
                        continue
                    samples.append(dt)
                cells.append(f"{statistics.median(samples):.0f} ms · {statements} stmts · {hits} hits")
            n_clauses = "whole" if clauses is None else str(len(clauses))
            row = f"| {label} | {n_clauses} | " + " | ".join(cells) + " |"
            print(row, flush=True)
            table.append(row)
        event.remove(sync_engine, "before_cursor_execute", count)
        lines += table
    finally:
        await storage.close()
        if engine != "sqlite":
            dropper = create_async_engine(url)
            async with dropper.begin() as conn:
                await conn.run_sync(build_vfs_tables(table_name=table_name).metadata.drop_all)
            await dropper.dispose()
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    out = os.path.join(HERE, "runs", f"{engine}-{tops * folders * files}.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {out}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres"])
    ap.add_argument("--tops", type=int, default=10)
    ap.add_argument("--folders", type=int, default=100)
    ap.add_argument("--files", type=int, default=50)
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.tops, a.folders, a.files, a.reps))
