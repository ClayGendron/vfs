"""Insert shapes on the real lex_postings table, sqlite via aiosqlite + SQLAlchemy.

Block-shaped rows (7 columns, ~560 B of blobs); time per row for each shape.
"""

from __future__ import annotations

import asyncio
import os
import random
import sqlite3
import sys
import time

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from vfs.models.rows import build_vfs_tables
from vfs.storage.backends.database.dialects import chunked

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000
DB = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/9aca8a65-866f-4cbb-bc2b-685f1963370c/scratchpad/insert_shapes.sqlite"


def rows(n: int) -> list[dict]:
    rng = random.Random(1)
    out = []
    for i in range(n):
        ids = bytes(rng.getrandbits(8) for _ in range(180))
        out.append(
            {
                "epoch": 1,
                "term": f"t{i:08d}",
                "block_no": 0,
                "doc_count": 128,
                "doc_ids": ids,
                "tfs": ids[:128],
                "dls": ids[:256],
            }
        )
    return out


async def fresh():
    if os.path.exists(DB):
        os.unlink(DB)
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB}")
    tables = build_vfs_tables(table_name="vfs")
    async with engine.begin() as conn:
        await conn.run_sync(tables.metadata.create_all)
    return engine, tables


async def shape_session_executemany(data, page):
    engine, tables = await fresh()
    t0 = time.perf_counter()
    async with AsyncSession(engine) as session, session.begin():
        for chunk in chunked(data, page):
            await session.execute(insert(tables.lex_postings), list(chunk))
    wall = time.perf_counter() - t0
    await engine.dispose()
    return wall


async def shape_session_values(data, page):
    engine, tables = await fresh()
    t0 = time.perf_counter()
    async with AsyncSession(engine) as session, session.begin():
        for chunk in chunked(data, page):
            await session.execute(insert(tables.lex_postings).values(list(chunk)))
    wall = time.perf_counter() - t0
    await engine.dispose()
    return wall


async def shape_conn_executemany(data, page):
    engine, tables = await fresh()
    t0 = time.perf_counter()
    async with engine.begin() as conn:
        for chunk in chunked(data, page):
            await conn.execute(insert(tables.lex_postings), list(chunk))
    wall = time.perf_counter() - t0
    await engine.dispose()
    return wall


async def shape_driver_executemany(data, page):
    engine, tables = await fresh()
    t = tables.lex_postings
    cols = ["epoch", "term", "block_no", "doc_count", "doc_ids", "tfs", "dls"]
    sql = f"INSERT INTO {t.name} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    tuples = [tuple(r[c] for c in cols) for r in data]
    t0 = time.perf_counter()
    async with engine.begin() as conn:
        for chunk in chunked(tuples, page):
            await conn.exec_driver_sql(sql, list(chunk))
    wall = time.perf_counter() - t0
    await engine.dispose()
    return wall


def shape_raw_sqlite3(data, page):
    if os.path.exists(DB):
        os.unlink(DB)
    con = sqlite3.connect(DB)
    con.execute(
        "CREATE TABLE vfs_lex_postings (epoch INTEGER NOT NULL, term VARCHAR(64) NOT NULL, block_no INTEGER NOT NULL,"
        " doc_count INTEGER NOT NULL, doc_ids BLOB NOT NULL, tfs BLOB NOT NULL, dls BLOB NOT NULL,"
        " PRIMARY KEY (epoch, term, block_no)) WITHOUT ROWID"
    )
    cols = ["epoch", "term", "block_no", "doc_count", "doc_ids", "tfs", "dls"]
    tuples = [tuple(r[c] for c in cols) for r in data]
    t0 = time.perf_counter()
    with con:
        for chunk in chunked(tuples, page):
            con.executemany("INSERT INTO vfs_lex_postings VALUES (?,?,?,?,?,?,?)", list(chunk))
    wall = time.perf_counter() - t0
    con.close()
    return wall


async def main():
    data = rows(N)
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB}")
    budget = engine.dialect.insertmanyvalues_max_parameters
    await engine.dispose()
    per_values = budget // 7
    print(f"rows {N}; parameter budget {budget} -> {per_values} rows per multirow VALUES statement", flush=True)
    results = {
        "session.execute(insert, rows) page 20k  [lexical today]": await shape_session_executemany(data, 20_000),
        f"session.execute(insert.values(rows)) page {per_values} [write path]": await shape_session_values(data, per_values),
        "conn.execute(insert, rows) page 20k": await shape_conn_executemany(data, 20_000),
        "conn.exec_driver_sql(sql, tuples) page 20k [driver executemany via SQLAlchemy]": await shape_driver_executemany(data, 20_000),
        "sqlite3.executemany sync page 20k [raw reference]": shape_raw_sqlite3(data, 20_000),
    }
    for name, wall in results.items():
        print(f"{name:85s} {wall:6.2f} s  {wall / N * 1e6:5.2f} us/row")


if __name__ == "__main__":
    asyncio.run(main())
