"""Shared harness for the set-based topology-statement studies (specs 080 / 102).

Every run mints its own table namespace on the engine named by an env var,
drops it on exit, and can attach a per-statement profiler to the engine.
Run from the repo root with ``uv run python <script>``.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

ENGINE_ENV = {
    "postgres": "VFS_TEST_POSTGRES_URL",
    "mysql": "VFS_TEST_MYSQL_URL",
    "mariadb": "VFS_TEST_MARIADB_URL",
    "mssql": "VFS_TEST_MSSQL_URL",
    "oracle": "VFS_TEST_ORACLE_URL",
}
RESULTS = FsPath(__file__).parent / "results"


@asynccontextmanager
async def minted(url: str):
    """A fresh backend in its own namespace; the namespace is dropped on exit."""
    table_name = f"vfs_{uuid.uuid4().hex[:10]}"
    storage = DatabaseStorage(url=url, table_name=table_name)
    try:
        yield storage
    finally:
        await storage.close()
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(build_vfs_tables(table_name=table_name).metadata.drop_all)
        finally:
            await engine.dispose()


def sibling(url: str, storage: DatabaseStorage) -> DatabaseStorage:
    """A rival handle on the same namespace."""
    return DatabaseStorage(url=url, table_name=storage._host.tables.entry.name)


def scattered_corpus(size: int, *, dirs_with_children: int = 0) -> tuple[list[Entry], list[Path]]:
    """``size`` files spread ten per directory, plus optional directory targets.

    Returns the entries to write and the scattered target list: every file,
    plus ``dirs_with_children`` extra directories (each holding five files)
    that are targets themselves — the descendant-rewrite arm's exercise.
    """
    entries: list[Entry] = []
    targets: list[Path] = []
    for i in range(size):
        path = Path(f"/d{i // 10:05}/f{i:06}.txt")
        entries.append(Entry(path=path, content=f"body {i}"))
        targets.append(path)
    for j in range(dirs_with_children):
        for k in range(5):
            entries.append(Entry(path=Path(f"/t{j:04}/c{k}.txt"), content=f"child {j} {k}"))
        targets.append(Path(f"/t{j:04}"))
    entries.append(Entry(path=Path("/rival/r.txt"), content="rival"))
    return entries, targets


class StatementProfile:
    """Per-statement-shape timing off the engine's cursor events."""

    def __init__(self, storage: DatabaseStorage) -> None:
        self.table = storage._host.tables.entry.name
        self.shapes: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "seconds": 0.0, "rows": 0})
        self.enabled = False
        sync_engine = storage._host.engine.sync_engine

        @event.listens_for(sync_engine, "before_cursor_execute")
        def before(conn, cursor, statement, parameters, context, executemany) -> None:
            if self.enabled:
                conn.info["_study_t0"] = time.perf_counter()

        @event.listens_for(sync_engine, "after_cursor_execute")
        def after(conn, cursor, statement, parameters, context, executemany) -> None:
            if not self.enabled:
                return
            elapsed = time.perf_counter() - conn.info.pop("_study_t0", time.perf_counter())
            bucket = self.shapes[self.shape(statement, executemany)]
            bucket["count"] += 1
            bucket["seconds"] += elapsed
            bucket["rows"] += len(parameters) if executemany and isinstance(parameters, (list, tuple)) else 1

    def shape(self, statement: str, executemany: bool) -> str:
        text = re.sub(r"\s+", " ", statement).replace(self.table, "entries").strip()
        text = re.sub(r"\((\s*[:?%$@][\w()]*\s*,?\s*)+\)", "(…)", text)
        prefix = "[many] " if executemany else ""
        return prefix + text[:110]

    def report(self, top: int = 12) -> list[dict[str, Any]]:
        rows = [{"shape": k, **v} for k, v in self.shapes.items()]
        rows.sort(key=lambda r: -r["seconds"])
        total = sum(r["seconds"] for r in rows)
        for r in rows:
            r["share"] = round(r["seconds"] / total, 3) if total else 0.0
            r["seconds"] = round(r["seconds"], 4)
        return rows[:top]


def save(name: str, payload: dict[str, Any]) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"saved results/{name}.json")
