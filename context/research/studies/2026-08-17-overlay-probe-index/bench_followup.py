"""Follow-up: winners end-to-end (dirs-encoded, composite index), hop floor,
piggy-backed epoch read with the semantically-correct EXISTS.

Run: uv run python bench_followup.py  → followup_results.json
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path as FsPath

from sqlalchemy import exists, select, text

from bench_probe import CLONES, RUNS_MS, RUNS_US, atime, bench_db, stime
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.storage.backends.database.dialects import op_execution_options
from vfs.storage.backends.database.indexing import current_epoch


async def hop_and_piggyback(db_path: FsPath) -> dict:
    out: dict = {"db": db_path.name, "kind": "hop_and_piggyback"}
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db_path}")
    host = storage._host
    assert await host.ensure_ready() is None
    tables, profile = host.tables, host.profile
    entry, meta = tables.entry, tables.meta
    async with host.session_factory() as session:
        if options := op_execution_options(profile, writer=False):
            await session.connection(execution_options=options)
        conn = await session.connection()
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection

        async def raw_select1():
            cur = await driver.execute("SELECT 1")
            await cur.fetchall()
            await cur.close()

        out["raw_aiosqlite_select1"] = await atime(raw_select1, RUNS_US)
        out["session_text_select1"] = await atime(
            lambda: session.execute(text("SELECT 1")), RUNS_US
        )
        # semantically-correct emptiness once directories are encoded:
        e1 = "SELECT EXISTS(SELECT 1 FROM vfs WHERE NOT encoded)"
        out["exists_text_nokind"] = await atime(lambda: session.execute(text(e1)), RUNS_US)
        out["epoch_read"] = await atime(lambda: current_epoch(session, tables), RUNS_US)
        sub = select(exists(select(entry.c.id).where(~entry.c.encoded))).scalar_subquery()
        combined = select(meta.c.current_gram_epoch, sub.label("overlay")).where(meta.c.id == 1)
        out["epoch_read_plus_exists_nokind"] = await atime(
            lambda: session.execute(combined), RUNS_US
        )
    con = sqlite3.connect(db_path)
    out["sync_select1"] = stime(lambda: con.execute("SELECT 1").fetchall(), RUNS_US)
    out["sync_exists_nokind"] = stime(lambda: con.execute(e1).fetchall(), RUNS_US)
    combined_sql = (
        "SELECT current_gram_epoch, "
        "(SELECT EXISTS(SELECT 1 FROM vfs WHERE NOT encoded)) FROM vfs_meta WHERE id = 1"
    )
    out["sync_epoch_plus_exists"] = stime(lambda: con.execute(combined_sql).fetchall(), RUNS_US)
    con.close()
    return out


async def main() -> None:
    results = []
    for name in ("empty_dirs.sqlite", "empty_p4.sqlite", "base_p4.sqlite"):
        print(f"== {name}", file=sys.stderr)
        results.append(await bench_db(CLONES / name, decompose=False))
    results.append(await hop_and_piggyback(CLONES / "empty_dirs.sqlite"))
    out_path = FsPath(__file__).parent / "followup_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
