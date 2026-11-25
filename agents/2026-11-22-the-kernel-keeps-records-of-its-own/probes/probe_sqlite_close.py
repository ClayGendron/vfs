"""Which files are left beside a SQLite database after two engines on it are closed, in each order.

The spec's decision 19 says the directory holds the mount's file and no side file once both the mount's
engine and the store's are closed, whichever ends second. The landed close work was written for one
engine. Each case here opens a fresh file with a real mount (``SQLiteStorage`` under the kernel) and the
stand-in store on a second engine, writes through both, and lists the directory after each step.

Cases:

- ``store-first``: the store is closed, then the kernel.
- ``mount-first``: the kernel is closed, then the store.
- ``together``: both closes are gathered, as decision 19 places the store beside the storages.
- ``store-never``: the kernel is closed and the store is not, which is what a store close that is cut
  short and never finished leaves.
- ``store-connection-out``: the store's engine is disposed while one of its connections is checked out,
  which is what a dispose under a flush in flight meets.
- ``other-process``: a second process holds a connection on the file while both engines close.

    PROBE_SCRATCH=<a scratch directory outside the repository> \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_sqlite_close.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import URL
from standin import open_store

from vfs import AsyncVirtualFileSystem, SQLiteStorage

HOLDER = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1])
conn.execute("SELECT count(*) FROM sqlite_schema").fetchall()
print("open", flush=True)
sys.stdin.readline()
conn.close()
"""


def listing(directory: FsPath) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


async def case(name: str, root: FsPath) -> dict[str, Any]:
    directory = root / f"close-{name}-{uuid.uuid4().hex[:8]}"
    directory.mkdir(parents=True)
    database = directory / "knowledge.db"
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=database))
    store = open_store("sqlite", URL.create("sqlite+aiosqlite", database=str(database)))
    steps: list[tuple[str, list[str]]] = []
    wrote = await fs.write(path="/a.md", content="one\n")
    assert wrote.success, wrote.errors
    await store.first_touch()
    store.put_behind("stamp", {"session": "s", "path": "/a.md", "vid": "v1", "turn": 1}, key=("s", "/a.md"))
    for _ in range(200):
        if not store.buffer:
            break
        await asyncio.sleep(0.01)
    steps.append(("both open, both written", listing(directory)))
    holder: subprocess.Popen[str] | None = None
    if name == "store-first":
        await store.close()
        steps.append(("store closed", listing(directory)))
        await fs.close()
        steps.append(("kernel closed", listing(directory)))
    elif name == "mount-first":
        await fs.close()
        steps.append(("kernel closed", listing(directory)))
        await store.close()
        steps.append(("store closed", listing(directory)))
    elif name == "together":
        await asyncio.gather(fs.close(), store.close())
        steps.append(("both closed in one gather", listing(directory)))
    elif name == "store-never":
        await fs.close()
        steps.append(("kernel closed, store left open", listing(directory)))
        await store.close()
        steps.append(("store closed afterwards", listing(directory)))
    elif name == "store-connection-out":
        out = await store.engine.connect()
        await out.exec_driver_sql("SELECT 1")
        await fs.close()
        await store.close()
        steps.append(("both disposed, one store connection still out", listing(directory)))
        await out.close()
        steps.append(("that connection returned", listing(directory)))
    else:
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER, str(database)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        assert holder.stdout is not None
        holder.stdout.readline()
        await store.close()
        await fs.close()
        steps.append(("both closed, another process still open", listing(directory)))
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=10)
        steps.append(("the other process closed", listing(directory)))
    # What the file holds once everything is closed: both sets of rows, read by a plain connection.
    conn = sqlite3.connect(database)
    stamps = conn.execute("SELECT count(*) FROM standin_stamps").fetchone()[0]
    entries = conn.execute("SELECT count(*) FROM vfs_entries WHERE path = '/a.md'").fetchone()[0]
    conn.close()
    final = listing(directory)
    shutil.rmtree(directory, ignore_errors=True)
    return {
        "case": name,
        "steps": [{"after": label, "files": files} for label, files in steps],
        "stamp_rows_kept": stamps,
        "file_rows_kept": entries,
        "files_after_a_plain_reader_opened_and_closed": final,
    }


async def main() -> None:
    root = FsPath(os.environ["PROBE_SCRATCH"])
    root.mkdir(parents=True, exist_ok=True)
    names = ("store-first", "mount-first", "together", "store-never", "store-connection-out", "other-process")
    results = [await asyncio.wait_for(case(name, root), timeout=60) for name in names]
    print(json.dumps({"script": "probe_sqlite_close.py", "sqlite": sqlite3.sqlite_version, "cases": results}, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
