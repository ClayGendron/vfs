"""Decision 6's price and decision 3's covering claim, by counts.

a) Directories of at most 200 entries whose bytes are mostly the unencoded tail: in hand's B against the bytes
   the ladder's scan side fetches for the same scope (vfs grep with content fetches counted).
b) The DDL of ix_vfs_entries_path on Postgres, compiled from vfs's own metadata: whether `SELECT id, path` is covered.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, DatabaseStorage

DB = sys.argv[1]
fetched = [0]
real_content = g.content_for_entries


async def content(session, tables, profile, mb, ids):
    out = await real_content(session, tables, profile, mb, ids)
    fetched[0] += sum(len(v) for v in out.values())
    return out


g.content_for_entries = content


async def main() -> None:
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = raw.execute(
        "SELECT substr(path, 1, length(path) - length(name) - 1) AS dir, count(*), sum(size_bytes), "
        "sum(CASE WHEN encoded THEN 0 ELSE size_bytes END) FROM vfs_entries WHERE kind='file' GROUP BY dir "
        "HAVING sum(CASE WHEN encoded THEN 0 ELSE size_bytes END) > 0 ORDER BY 4 DESC LIMIT 3").fetchall()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    try:
        for directory, files, total, tail in rows:
            fetched[0] = 0
            r = await fs.grep("dentry_lru_isolate", paths=(directory,), output_mode="files")
            print(f"a) {directory}: {files} files, in hand B = {total / 1e6:.1f} MB, of it unencoded {tail / 1e6:.1f} MB; "
                  f"the ladder fetched {fetched[0] / 1e6:.1f} MB for a pattern with 1 match corpus-wide ({len(r.observations)} rows)")
        entry = storage.tables.entry if hasattr(storage, "tables") else None
        if entry is None:
            from vfs.models.rows import build_vfs_tables  # noqa: PLC0415
            entry = build_vfs_tables().entry
        for index in entry.indexes:
            if index.name == "ix_vfs_entries_path":
                print("b)", str(CreateIndex(index).compile(dialect=postgresql.dialect())).strip())
    finally:
        raw.close()
        await fs.close()


asyncio.run(main())
