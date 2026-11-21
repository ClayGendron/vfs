"""Where reading a scope's files and grepping them in hand stops beating the posting-list grep.

For each scope (a directory, searched recursively) and each pattern, three timings on one warm kernel:

- ``index``: ``grep(pattern, paths=(scope,))``, which plans on the gram posting lists.
- ``list``: ``glob("**", paths=(scope,), kind="file")``, the listing the in-hand path needs first.
- ``in_hand``: ``grep(pattern, observations=listed_rows)``, which fetches every listed file and matches it.

Each timing also records the SQL statements issued (a ``before_cursor_execute`` listener on the storage's engine),
so a remote database's cost can be projected as ``local_ms + statements * rtt_ms + bytes / bandwidth``. The bytes the
in-hand path pulls are the scope's file bytes; the index path's are its posting lists plus its candidates and are not
measured here. Hits of the two strategies are checked equal, and every warning either strategy returns is kept.

    uv run python agents/2026-11-21-linux-grep-benchmark/crossover.py --root ~/Git/Repos/linux --db linux.db --out x.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import event

from vfs import AsyncVirtualFileSystem, DatabaseStorage

SCOPES = (
    "mm/tests",
    "kernel/unwind",
    "kernel/kcsan",
    "drivers/atm",
    "drivers/clocksource",
    "drivers/md",
    "drivers/gpu/drm/amd/display/dc",
    "drivers/media",
    "drivers/gpu",
    "drivers",
    "",
)
PATTERNS = {
    "rare": "^struct dentry \\{",
    "medium": "i_count",
    "common": "EXPORT_SYMBOL_GPL",
    "very common": "return 0;",
}


class StatementCounter:
    def __init__(self, storage: DatabaseStorage) -> None:
        self.count = 0
        event.listen(storage.engine.sync_engine, "before_cursor_execute", self._seen)

    def _seen(self, *_: object) -> None:
        self.count += 1


async def timed(call: Any, counter: StatementCounter, reps: int) -> tuple[dict[str, float], Any]:
    times: list[float] = []
    statements = 0
    result = None
    for repetition in range(reps + 1):
        before = counter.count
        started = time.perf_counter()
        result = await call()
        elapsed = time.perf_counter() - started
        if repetition:
            times.append(elapsed)
            statements = counter.count - before
    return {"median_ms": statistics.median(times) * 1000, "min_ms": min(times) * 1000, "statements": statements}, result


def hits(result: Any) -> set[tuple[str, int]]:
    return {(str(row.path), match.match) for row in result.observations for match in row.matches or []}


def notes(result: Any) -> list[str]:
    return [f"{error.severity}:{error.kind}:{error.message}"[:240] for error in result.errors]


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    root: FsPath = args.root.expanduser()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{args.db}")
    kernel = AsyncVirtualFileSystem(storage=storage)
    counter = StatementCounter(storage)
    rows: list[dict[str, Any]] = []
    try:
        await kernel.stat("/fs")
        for scope in SCOPES:
            paths = (f"/{scope}",) if scope else ()
            listing, listed = await timed(lambda p=paths: kernel.glob("**", paths=p, kind="file"), counter, 1)
            files = listed.observations
            size = sum(os.stat(root / str(row.path).lstrip("/")).st_size for row in files)
            reps = args.reps if len(files) <= 1000 else args.reps_large
            listing, listed = await timed(lambda p=paths: kernel.glob("**", paths=p, kind="file"), counter, reps)
            for label, pattern in PATTERNS.items():
                index, indexed = await timed(lambda p=paths, q=pattern: kernel.grep(q, paths=p), counter, reps)
                in_hand, held = await timed(lambda q=pattern: kernel.grep(q, observations=files), counter, reps)
                row = {
                    "scope": scope or "(whole tree)",
                    "files": len(files),
                    "bytes": size,
                    "pattern": label,
                    "regex": pattern,
                    "hits": len(hits(indexed)),
                    "agree": hits(indexed) == hits(held),
                    "index": index | {"notes": notes(indexed)},
                    "list": listing | {"notes": notes(listed)},
                    "in_hand": in_hand | {"notes": notes(held)},
                }
                rows.append(row)
                print(
                    f"{row['scope']:32} files={len(files):6} {label:12} hits={row['hits']:6} agree={row['agree']} "
                    f"index={index['median_ms']:8.1f}ms/{index['statements']}st "
                    f"list={listing['median_ms']:8.1f}ms/{listing['statements']}st "
                    f"in_hand={in_hand['median_ms']:8.1f}ms/{in_hand['statements']}st "
                    f"notes={len(row['index']['notes'])}/{len(row['in_hand']['notes'])}",
                    flush=True,
                )
    finally:
        await kernel.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=FsPath, required=True)
    parser.add_argument("--db", type=FsPath, required=True)
    parser.add_argument("--out", type=FsPath, required=True)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--reps-large", type=int, default=2)
    args = parser.parse_args()
    args.out.write_text(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
