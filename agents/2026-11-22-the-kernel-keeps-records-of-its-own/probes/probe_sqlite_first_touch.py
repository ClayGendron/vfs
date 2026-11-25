"""A mount's first touch and the store's first touch on one SQLite file, in each order and at once.

The spec's decision 4 puts the kernel's tables in the mount's own file. The mount's first touch is read
to verify its meta row and not its table list, and this had not been run. Each case uses a fresh file,
a real mount (``SQLiteStorage`` under the kernel) and the stand-in store on a second engine.

Cases:

- ``store-then-mount``: the store makes its tables in a file that does not exist yet; the mount is
  opened on that file afterwards.
- ``mount-then-store``: the usual order.
- ``at-once``: both first touches are gathered on a fresh file, eight times over.
- ``foreign-table``: the file already holds a table named with a kernel prefix that the store did not
  make, and a table of an application's own.
- ``read-only``: the file is made read-only after the mount wrote to it; what the store's first touch
  and its flush raise, and how today's classifier reads that failure.
- ``statistics``: after a mount write large enough to make its statistics pass due, which tables
  ``sqlite_stat1`` names.

For each it reports what each first touch returned, the file's page size and journal mode, the tables in
the file, and whether a mount write and read and a store commit then work.

    PROBE_SCRATCH=<a scratch directory outside the repository> \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_sqlite_first_touch.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import stat
import uuid
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import URL
from sqlalchemy.exc import DBAPIError
from standin import StandinStore, StoreUnavailable, open_store

from vfs import AsyncVirtualFileSystem, Entry, SQLiteStorage
from vfs.storage.backends.database.dialects import is_permanent_defect, is_retryable, profile_for


def facts(database: FsPath) -> dict[str, Any]:
    conn = sqlite3.connect(database)
    tables = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'"))
    out = {
        "page_size": conn.execute("PRAGMA page_size").fetchone()[0],
        "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        "mount_tables": sum(1 for t in tables if t.startswith("vfs_")),
        "store_tables": [t for t in tables if t.startswith("standin_")],
        "other_tables": [t for t in tables if not t.startswith(("vfs_", "standin_", "sqlite_"))],
    }
    if "vfs_meta" in tables:
        out["mount_format"] = conn.execute("SELECT schema_format_version FROM vfs_meta").fetchone()[0]
    if "standin_kernel_meta" in tables:
        out["store_meta_rows"] = conn.execute("SELECT count(*) FROM standin_kernel_meta").fetchone()[0]
    conn.close()
    return out


async def use(fs: AsyncVirtualFileSystem, store: StandinStore) -> dict[str, Any]:
    """One mount write and read, and one store commit."""
    wrote = await fs.write(path="/a.md", content="one\n")
    read = await fs.read("/a.md")

    async def record(conn: Any) -> None:
        await conn.execute(store.stamps.insert().values(session="s", path="/a.md", vid="v1", turn=1))

    failure = await store.record_after(record)
    return {"mount_write": wrote.success, "mount_read": read.success, "store_commit_failure": failure}


async def touch_mount(fs: AsyncVirtualFileSystem) -> str:
    result = await fs.stat("/")
    return "ok" if result.success else f"{result.errors[0].kind}: {result.errors[0].message[:160]}"


async def touch_store(store: StandinStore) -> str:
    try:
        await store.first_touch()
    except (StoreUnavailable, DBAPIError) as exc:
        return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    return "ok"


async def case(name: str, root: FsPath, n: int = 0) -> dict[str, Any]:
    directory = root / f"touch-{name}-{uuid.uuid4().hex[:8]}"
    directory.mkdir(parents=True)
    database = directory / "knowledge.db"
    url = URL.create("sqlite+aiosqlite", database=str(database))
    out: dict[str, Any] = {"case": name if not n else f"{name} {n}"}
    if name == "foreign-table":
        conn = sqlite3.connect(database)
        conn.execute("CREATE TABLE vfs_session_notes (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("CREATE TABLE app_orders (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        out["before"] = facts(database)
    fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=database))
    store = open_store("sqlite", url)
    if name == "store-then-mount":
        out["store_first_touch"] = await touch_store(store)
        out["after_store"] = facts(database)
        out["mount_first_touch"] = await touch_mount(fs)
    elif name == "at-once":
        out["mount_first_touch"], out["store_first_touch"] = await asyncio.gather(touch_mount(fs), touch_store(store))
    else:
        out["mount_first_touch"] = await touch_mount(fs)
        out["store_first_touch"] = await touch_store(store)
    if name == "statistics":
        entries = [Entry(path=f"/s/d{i // 100:02d}/f{i:05d}.md", content=f"file {i}\n") for i in range(3000)]
        wrote = await fs.write(entries, parents=True)
        out["batch_ok"] = wrote.success

        async def many(conn: Any) -> None:
            rows = [{"session": "s", "path": f"/s/{i}", "vid": "v", "turn": 1} for i in range(3000)]
            await conn.execute(store.stamps.insert().values(rows))

        await store.record_after(many)
        again = await fs.write(path="/s/after.md", content="x\n")
        out["write_after_ok"] = again.success
        await asyncio.sleep(1.0)
    if name == "read-only":
        out["use_while_writable"] = await use(fs, store)
        await store.close()
        await fs.close()
        database.chmod(stat.S_IRUSR | stat.S_IRGRP)
        fs = AsyncVirtualFileSystem(storage=SQLiteStorage(path=database))
        store = open_store("sqlite", url)
        read = await fs.read("/a.md")
        out["mount_read_on_read_only_file"] = read.success
        profile = profile_for("sqlite")
        try:
            await store.first_touch()
            out["store_first_touch_on_read_only_file"] = "ok"
        except StoreUnavailable as exc:
            cause = exc.__cause__
            out["store_first_touch_on_read_only_file"] = str(exc)
            out["failed_after_tries"] = store.commits[-1].attempts
            out["classifier_says_retryable"] = is_retryable(profile, cause) if cause else None
            out["classifier_says_permanent_defect"] = is_permanent_defect(cause) if cause else None
            out["sqlite_errorcode"] = getattr(getattr(cause, "orig", None), "sqlite_errorcode", None)
        except DBAPIError as exc:
            out["store_first_touch_on_read_only_file"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
            out["classifier_says_retryable"] = is_retryable(profile, exc)
            out["classifier_says_permanent_defect"] = is_permanent_defect(exc)
            out["sqlite_errorcode"] = getattr(exc.orig, "sqlite_errorcode", None)
        database.chmod(stat.S_IRUSR | stat.S_IWUSR)
    else:
        out["use"] = await use(fs, store)
    await store.close()
    await fs.close()
    out["after"] = facts(database)
    if name == "statistics":
        conn = sqlite3.connect(database)
        try:
            names = sorted({r[0] for r in conn.execute("SELECT tbl FROM sqlite_stat1")})
        except sqlite3.OperationalError as exc:
            names = [f"no sqlite_stat1: {exc}"]
        conn.close()
        out["tables_with_statistics"] = names
    out["files_after_close"] = sorted(p.name for p in directory.iterdir())
    shutil.rmtree(directory, ignore_errors=True)
    return out


async def main() -> None:
    root = FsPath(os.environ["PROBE_SCRATCH"])
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for name in ("store-then-mount", "mount-then-store", "foreign-table", "read-only", "statistics"):
        results.append(await asyncio.wait_for(case(name, root), timeout=120))
    at_once = [await asyncio.wait_for(case("at-once", root, n), timeout=120) for n in range(1, 9)]
    summary = {
        "runs": len(at_once),
        "mount_first_touch": sorted({c["mount_first_touch"] for c in at_once}),
        "store_first_touch": sorted({c["store_first_touch"] for c in at_once}),
        "page_sizes": sorted({c["after"]["page_size"] for c in at_once}),
        "journal_modes": sorted({c["after"]["journal_mode"] for c in at_once}),
        "use": [c["use"] for c in at_once if c["use"] != at_once[0]["use"]] or at_once[0]["use"],
    }
    payload = {
        "script": "probe_sqlite_first_touch.py",
        "sqlite": sqlite3.sqlite_version,
        "cases": results,
        "at_once": summary,
    }
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
