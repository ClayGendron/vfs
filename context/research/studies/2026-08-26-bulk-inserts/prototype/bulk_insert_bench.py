"""Before/after benchmark for the bulk-insert path, on any engine.

Two sections, one JSON:

- **micro** — 100 k block-shaped rows into a fresh ``lex_postings`` table,
  three statement shapes: SQLAlchemy's executemany (what the index builds
  and content inserts do today), the driver's own executemany through
  ``exec_driver_sql`` (the proposed path, rendered per dialect), and one
  multirow ``VALUES`` statement per parameter budget (the write path's
  entry insert today; skipped where the dialect has no multirow insert).
- **verbs** — the live tree: ``write`` of a seeded linux sample in batches
  of 1,000 entries, ``reindex`` with the lexical build no-op'd (gram epoch
  + chunks), then ``reindex`` with it (the lexical delta). The sample is
  4,000 files on sqlite and 1,000 on a server engine by default — the
  ratios are what the benchmark is for, and SQL Server under Rosetta
  takes six minutes at 4,000; pass ``--files`` to compare like with like.

    uv run --no-sync python bulk_insert_bench.py --label before
    uv run --no-sync python bulk_insert_bench.py --label before --url postgresql+asyncpg://vfs:vfs@localhost:54320/vfs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path as FsPath

from sqlalchemy import bindparam, insert
from sqlalchemy.ext.asyncio import create_async_engine

import vfs.native as native
from vfs.models import Entry
from vfs.models import lexical as lexical_model
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage, indexing
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.engine import _engine_kwargs

LINUX = FsPath.home() / "Git/Repos/linux"
EXTS = {".c", ".h", ".py", ".rst", ".txt", ".md", ".S", ".sh", ".yaml", ".json"}
RESULTS = FsPath(__file__).resolve().parent / "results"
SCRATCH = FsPath("/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/9aca8a65-866f-4cbb-bc2b-685f1963370c/scratchpad")
COLS = ["epoch", "term", "block_no", "doc_count", "doc_ids", "tfs", "dls"]
PAGE = 20_000


def sample_files(n: int, seed: int) -> list[FsPath]:
    files = sorted(p for p in LINUX.rglob("*") if p.is_file() and p.suffix in EXTS and ".git" not in p.parts)
    return random.Random(seed).sample(files, min(n, len(files)))


def block_rows(n: int) -> list[dict]:
    rng = random.Random(1)
    out = []
    for i in range(n):
        ids = bytes(rng.getrandbits(8) for _ in range(180))
        out.append(
            {"epoch": 1, "term": f"t{i:08d}", "block_no": 0, "doc_count": 128, "doc_ids": ids, "tfs": ids[:128], "dls": ids[:256]}
        )
    return out


# ---------------------------------------------------------------------------
# micro: statement shapes on one table
# ---------------------------------------------------------------------------


async def micro(url: str, n: int, table_name: str, fast_executemany: bool) -> dict:
    kwargs = {**_engine_kwargs(url), **({"fast_executemany": True} if fast_executemany else {})}
    engine = create_async_engine(url, **kwargs)
    tables = build_vfs_tables(table_name=table_name)
    t = tables.lex_postings
    dialect = engine.dialect
    data = block_rows(n)

    async def fresh() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(tables.metadata.drop_all)
            await conn.run_sync(tables.metadata.create_all)

    async def timed(shape, reps: int = 3) -> float:
        walls = []
        for _ in range(reps):
            await fresh()
            t0 = time.perf_counter()
            async with engine.begin() as conn:
                await shape(conn)
            walls.append((time.perf_counter() - t0) / n * 1e6)
        return statistics.median(walls)

    async def sqlalchemy_executemany(conn) -> None:
        for chunk in chunked(data, PAGE):
            await conn.execute(insert(t), list(chunk))

    compiled = insert(t).values({c: bindparam(c) for c in COLS}).compile(dialect=dialect)
    processors = {c: t.c[c].type.dialect_impl(dialect).bind_processor(dialect) for c in COLS}

    def processed(row: dict) -> dict:
        return {c: (processors[c](row[c]) if processors[c] is not None else row[c]) for c in COLS}

    if dialect.positional:
        order = list(compiled.positiontup)
        params = [tuple(p[name] for name in order) for p in map(processed, data)]
    else:
        params = [processed(row) for row in data]
    sql = str(compiled)

    async def driver_executemany(conn) -> None:
        for chunk in chunked(params, PAGE):
            await conn.exec_driver_sql(sql, list(chunk))

    per_values = max(1, dialect.insertmanyvalues_max_parameters // len(COLS))

    async def multirow_values(conn) -> None:
        for chunk in chunked(data, per_values):
            await conn.execute(insert(t).values(list(chunk)))

    async def copy_records(conn) -> None:
        raw = await conn.get_raw_connection()
        for chunk in chunked(params, PAGE):
            await raw.driver_connection.copy_records_to_table(t.name, records=list(chunk), columns=order)

    out = {
        "rows": n,
        "dialect": dialect.name,
        "driver": dialect.driver,
        "paramstyle": dialect.paramstyle,
        "use_insertmanyvalues": dialect.use_insertmanyvalues,
        "fast_executemany": fast_executemany,
        "rendered": sql,
        "us_per_row": {
            "sqlalchemy_executemany": round(await timed(sqlalchemy_executemany), 2),
            "driver_executemany": round(await timed(driver_executemany), 2),
        },
    }
    if dialect.driver == "asyncpg":
        out["us_per_row"]["copy_records"] = round(await timed(copy_records), 2)
    if dialect.supports_multivalues_insert:
        out["us_per_row"]["multirow_values"] = round(await timed(multirow_values), 2)
        out["multirow_rows_per_statement"] = per_values
    async with engine.begin() as conn:
        await conn.run_sync(tables.metadata.drop_all)
    await engine.dispose()
    return out


# ---------------------------------------------------------------------------
# verbs: write and reindex through the live tree
# ---------------------------------------------------------------------------


async def load(storage: DatabaseStorage, files: list[FsPath]) -> tuple[int, int, float]:
    total = 0
    written = 0
    wall = 0.0
    batch: list[Entry] = []

    async def flush() -> None:
        nonlocal wall, written
        t0 = time.perf_counter()
        result = await storage.write(entries=batch, parents=True)
        wall += time.perf_counter() - t0
        assert result.success, result.errors
        written += len(batch)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text or not text:
            continue
        total += len(text.encode())
        batch.append(Entry(path=Path("/" + path.relative_to(LINUX).as_posix()), content=text))
        if len(batch) == 1000:
            await flush()
            batch = []
    if batch:
        await flush()
    return written, total, wall


async def verbs(url: str, files: list[FsPath], table_name: str) -> dict:
    storage = DatabaseStorage(url=url, table_name=table_name)
    written, content_bytes, write_s = await load(storage, files)

    real_build = indexing.build_lexical_epoch

    async def no_lexical(session, tables, epoch, executor) -> None:
        return None

    indexing.build_lexical_epoch = no_lexical  # type: ignore[assignment]
    t0 = time.perf_counter()
    result = await storage.reindex()
    assert result.success, result.errors
    gram_s = time.perf_counter() - t0
    lexical_model.TOKENIZER_VERSION = 99  # type: ignore[misc]
    indexing.build_lexical_epoch = real_build  # type: ignore[assignment]
    t0 = time.perf_counter()
    result = await storage.reindex()
    assert result.success, result.errors
    full_s = time.perf_counter() - t0
    out = {
        "files": written,
        "content_mb": round(content_bytes / 2**20, 1),
        "write_s": round(write_s, 2),
        "write_files_per_s": round(written / write_s),
        "reindex_no_lexical_s": round(gram_s, 2),
        "reindex_with_lexical_s": round(full_s, 2),
        "lexical_delta_s": round(full_s - gram_s, 2),
    }
    if not url.startswith("sqlite"):
        async with storage._host.engine.begin() as conn:
            await conn.run_sync(storage._host.tables.metadata.drop_all)
    await storage.close()
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--label", required=True)
    ap.add_argument("--files", type=int, default=None, help="linux files to write; default 4,000 on sqlite, 1,000 on a server")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--micro-rows", type=int, default=100_000)
    ap.add_argument("--skip-verbs", action="store_true")
    ap.add_argument("--fast-executemany", action="store_true", help="mssql: pyodbc fast_executemany on the micro engine")
    args = ap.parse_args()
    url = args.url
    if url is None:
        db = SCRATCH / f"bulk_{args.label}.sqlite"
        if db.exists():
            db.unlink()
        url = f"sqlite+aiosqlite:///{db}"
    stamp = f"bench_{args.label}"
    print(f"engine {native.active_core()}; {url.split('://')[0]}", flush=True)
    payload = {
        "label": args.label,
        "url_scheme": url.split("://")[0],
        "micro": await micro(url, args.micro_rows, stamp, args.fast_executemany),
    }
    print(json.dumps(payload["micro"]["us_per_row"]), flush=True)
    files = args.files if args.files is not None else (4000 if url.startswith("sqlite") else 1000)
    if not args.skip_verbs:
        payload["verbs"] = await verbs(url, sample_files(files, args.seed), stamp)
        print(json.dumps(payload["verbs"]), flush=True)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{args.label}_{payload['micro']['dialect']}.json"
    out.write_text(json.dumps(payload, indent=1))
    print(f"-> {out}")


asyncio.run(main())
