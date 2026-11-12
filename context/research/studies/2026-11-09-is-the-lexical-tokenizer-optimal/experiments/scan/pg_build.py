"""Build the 100,000-file store on the Postgres test container, the way study 02 did.

Creates the schema, writes study 02's corpus (``generate(100000)``) in
batches of 10,000 through ``storage.write``, then ``reindex()`` until no
live entry awaits the index, and checksums the lexical epoch so the
harness runs on this schema can be compared against it. The data
directory is a tmpfs, so the schema is gone with the container.

Usage: uv run python pg_build.py <url> <schema> <files> <out json>
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path as FsPath

from sqlalchemy import text

from harness import load_generator, lexical_checksum, rss_bytes, table_counts
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends import DatabaseStorage

WRITE_BATCH = 10_000


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


async def main() -> None:
    url, schema, files, out_json = sys.argv[1], sys.argv[2], int(sys.argv[3]), FsPath(sys.argv[4])
    report: dict[str, object] = {"url": url.split("@")[-1], "schema": schema, "files": files}
    short = DatabaseStorage(url=url)
    assert await short._host.ensure_ready() is None
    async with short._host.engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        report["postgres_version"] = (await conn.execute(text("SHOW server_version"))).scalar_one()
    await short.close()
    storage = DatabaseStorage(url=url, schema=schema)
    assert await storage._host.ensure_ready() is None
    corpus = load_generator()
    log(f"writing {files} files")
    t0 = time.perf_counter()
    batch: list[Entry] = []
    written = 0
    for path, content in corpus.generate(files):
        batch.append(Entry(path=Path(path), content=content))
        if len(batch) == WRITE_BATCH:
            r = await storage.write(entries=batch, parents=True)
            assert r.success, r.errors
            written += len(batch)
            log(f"  wrote {written}/{files}")
            batch = []
    if batch:
        r = await storage.write(entries=batch, parents=True)
        assert r.success, r.errors
    report["write_wall_s"] = round(time.perf_counter() - t0, 2)
    runs = []
    for attempt in range(4):
        t0 = time.perf_counter()
        result = await storage.reindex()
        wall = round(time.perf_counter() - t0, 2)
        counts = await table_counts(storage)
        runs.append({"attempt": attempt, "success": result.success, "wall_s": wall, **counts})
        log(f"  reindex #{attempt} wall={wall}s success={result.success} not_encoded={counts['not_encoded']} epoch={counts['epoch']}")
        if result.success and counts["not_encoded"] == 0:
            break
    report["reindex"] = runs
    report["counts"] = await table_counts(storage)
    async with storage._host.engine.connect() as conn:
        report["schema_bytes"] = (
            await conn.execute(
                text(
                    "SELECT sum(pg_total_relation_size(c.oid)) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relkind = 'r'"
                ),
                {"s": schema},
            )
        ).scalar_one()
        await conn.execute(text("ANALYZE"))
        await conn.commit()
    report["checksum_epoch"] = report["counts"]["epoch"]
    report["checksum"] = await lexical_checksum(storage, report["counts"]["epoch"])
    report["rss_peak_mb"] = round(rss_bytes() / 2**20, 1)
    log(f"done: {json.dumps(report['counts'])} schema_bytes={report['schema_bytes']}")
    await storage.close()
    out_json.write_text(json.dumps(report, indent=2, default=str) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
