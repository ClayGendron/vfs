"""Load a source tree into a SQLite DatabaseStorage and build its index.

Walks the files ``rg --files`` lists under ``--root`` (the tree ripgrep would search), writes each UTF-8 file as
a text entry in batches of ``BATCH`` through ``DatabaseStorage.write``, then runs ``rebuild``. Files that are not
UTF-8 are skipped and counted. Phase timings and counts are written as JSON beside the database.

    uv run python agents/2026-11-21-linux-grep-benchmark/ingest.py --root ~/Git/Repos/linux --db linux.db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path as FsPath

from vfs import DatabaseStorage
from vfs.models import Entry
from vfs.paths import Path

BATCH = 10_000


async def ingest(root: FsPath, db: FsPath, prefix: str) -> dict[str, object]:
    listed = subprocess.run(["rg", "--files", "-0", prefix or "."], cwd=root, capture_output=True, check=True)
    names = sorted({name.removeprefix("./") for name in listed.stdout.decode().split("\0") if name})
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}")
    stats: dict[str, object] = {"files_listed": len(names)}
    skipped: list[str] = []
    written_files = 0
    written_bytes = 0
    started = time.perf_counter()
    try:
        batch: list[Entry] = []
        for name in names:
            raw = (root / name).read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped.append(name)
                continue
            if "\0" in text:
                skipped.append(name)
                continue
            batch.append(Entry(path=Path("/" + name), content=text))
            written_bytes += len(raw)
            if len(batch) == BATCH:
                written_files += await write(storage, batch)
                batch = []
                print(f"written {written_files} files, {time.perf_counter() - started:.1f}s", flush=True)
        if batch:
            written_files += await write(storage, batch)
        stats["write_seconds"] = time.perf_counter() - started
        print(f"write done: {written_files} files in {stats['write_seconds']:.1f}s", flush=True)
        rebuild_started = time.perf_counter()
        rebuilt = await storage.rebuild()
        stats["rebuild_seconds"] = time.perf_counter() - rebuild_started
        stats["rebuild_success"] = rebuilt.success
        stats["rebuild_errors"] = [str(error) for error in rebuilt.errors][:20]
        stats["rebuild_warnings"] = [str(warning) for warning in getattr(rebuilt, "warnings", [])][:20]
        print(f"rebuild done in {stats['rebuild_seconds']:.1f}s success={rebuilt.success}", flush=True)
    finally:
        await storage.close()
    stats.update(
        files_written=written_files,
        bytes_written=written_bytes,
        files_skipped=len(skipped),
        skipped_sample=skipped[:50],
        db_bytes=db.stat().st_size,
    )
    return stats


async def write(storage: DatabaseStorage, batch: list[Entry]) -> int:
    result = await storage.write(entries=batch, parents=True)
    if not result.success:
        raise RuntimeError(f"write failed: {result.errors[:5]}")
    return len(batch)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=FsPath, required=True)
    parser.add_argument("--db", type=FsPath, required=True)
    parser.add_argument("--prefix", default="", help="ingest only this subdirectory of the root")
    args = parser.parse_args()
    if args.db.exists():
        raise SystemExit(f"{args.db} exists; remove it first")
    stats = asyncio.run(ingest(args.root.expanduser(), args.db, args.prefix))
    args.db.with_suffix(".ingest.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps({k: v for k, v in stats.items() if k != "skipped_sample"}, indent=2))


if __name__ == "__main__":
    main()
