"""Harness: open a store, count statements per phase, wrap the verbs' scan-tier helpers with timers and counters.

Nothing here edits vfs. The wrappers replace module attributes in the
harness process only (``glean.entries_for_scan`` and friends), so every
statement a verb issues is bucketed by the phase that issued it, and the
rows and bytes each phase moved are counted where the helper's return
value exposes them.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from functools import wraps

from sqlalchemy import event, func, select, text

from vfs.storage.backends import DatabaseStorage
from vfs.storage.backends.database import glean as glean_module
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database import offload as offload_module

# ---------------------------------------------------------------------------
# Phase accounting
# ---------------------------------------------------------------------------

PHASE: list[str] = ["other"]
PHASES: dict[str, dict[str, float | int]] = {}
IN_OVERLAY = [False]


def _bucket(name: str) -> dict[str, float | int]:
    return PHASES.setdefault(name, {"calls": 0, "wall_s": 0.0, "rows": 0, "bytes": 0, "statements": 0})


def reset_phases() -> None:
    PHASES.clear()


@contextmanager
def phase(name: str):
    previous = PHASE[0]
    PHASE[0] = name
    bucket = _bucket(name)
    bucket["calls"] += 1
    t0 = time.perf_counter()
    try:
        yield bucket
    finally:
        bucket["wall_s"] += time.perf_counter() - t0
        PHASE[0] = previous


def _body_len(body) -> int:
    return len(body) if isinstance(body, (bytes, bytearray)) else len(body.encode("utf-8", "surrogatepass"))


def _wrap_async(module, name: str, phase_name: str, *, rows=None, nbytes=None):
    original = getattr(module, name)

    @wraps(original)
    async def wrapper(*args, **kwargs):
        with phase(phase_name) as bucket:
            result = await original(*args, **kwargs)
            if rows is not None:
                bucket["rows"] += rows(result)
            if nbytes is not None:
                bucket["bytes"] += nbytes(result)
            return result

    setattr(module, name, wrapper)


def _wrap_sync(module, name: str, phase_name: str, *, only_in_overlay: bool = False):
    original = getattr(module, name)

    @wraps(original)
    def wrapper(*args, **kwargs):
        if only_in_overlay and not IN_OVERLAY[0]:
            return original(*args, **kwargs)
        # Runs on the offload thread for _overlay_blocks: time only, do not touch PHASE.
        bucket = _bucket(phase_name)
        bucket["calls"] += 1
        t0 = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            bucket["wall_s"] += time.perf_counter() - t0

    setattr(module, name, wrapper)


def install_wrappers() -> None:
    """Wrap the scan-tier helpers of both verbs at module-attribute level."""
    # glean: the overlay and its three phases.
    _wrap_async(glean_module, "entries_for_scan", "glean.nominees", rows=lambda r: len(r.rows))
    _wrap_async(glean_module, "_surrogate_ids", "glean.surrogate_ids", rows=lambda r: len(r))
    _wrap_async(
        glean_module,
        "content_for_entries",
        "glean.bodies",
        rows=lambda r: len(r),
        nbytes=lambda r: sum(_body_len(b) for b in r.values()),
    )
    _wrap_sync(glean_module, "_overlay_blocks", "glean.tokenize")
    _wrap_sync(glean_module, "score_blocks", "glean.score", only_in_overlay=True)
    original_overlay = glean_module._overlay

    @wraps(original_overlay)
    async def overlay(*args, **kwargs):
        IN_OVERLAY[0] = True
        try:
            with phase("glean.overlay") as bucket:
                hits, bodies = await original_overlay(*args, **kwargs)
                bucket["rows"] += len(hits)
                return hits, bodies
        finally:
            IN_OVERLAY[0] = False

    glean_module._overlay = overlay
    # grep: index rows, scan nominees, posting blobs, bodies, the matcher.
    _wrap_async(
        grep_module,
        "entries_for_scan",
        "grep.nominees",
        rows=lambda r: len(r.rows),
        nbytes=lambda r: sum(m["size_bytes"] or 0 for m in r.rows),
    )
    _wrap_async(grep_module, "_entries_for_docs", "grep.index_rows", rows=lambda r: len(r))
    _wrap_async(
        grep_module, "_posting_blobs", "grep.postings", rows=lambda r: len(r), nbytes=lambda r: sum(map(len, r.values()))
    )
    _wrap_async(
        grep_module,
        "content_for_entries",
        "grep.bodies",
        rows=lambda r: len(r),
        nbytes=lambda r: sum(_body_len(b) for b in r.values()),
    )
    for method in ("hit_lines", "count_lines"):
        original = getattr(offload_module.VerifyOffload, method)

        @wraps(original)
        async def verify(self, *args, _original=original, **kwargs):
            with phase("grep.verify"):
                return await _original(self, *args, **kwargs)

        setattr(offload_module.VerifyOffload, method, verify)


# ---------------------------------------------------------------------------
# Statement counting
# ---------------------------------------------------------------------------


class StatementCounter:
    def __init__(self, storage: DatabaseStorage) -> None:
        self.count = 0
        self.kinds: dict[str, int] = {}
        self.enabled = False

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if not self.enabled:
                return
            self.count += 1
            verb = statement.lstrip().split(" ", 1)[0].upper()
            self.kinds[verb] = self.kinds.get(verb, 0) + 1
            _bucket(PHASE[0])["statements"] += 1

    def reset(self) -> None:
        self.count, self.kinds = 0, {}

    @contextmanager
    def capture(self):
        self.reset()
        reset_phases()
        self.enabled = True
        try:
            yield self
        finally:
            self.enabled = False


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


async def open_store(url: str, *, schema: str | None = None, wall: float) -> tuple[DatabaseStorage, StatementCounter]:
    storage = DatabaseStorage(url=url, schema=schema, grep_wall_seconds=wall, glean_wall_seconds=wall)
    refused = await storage._host.ensure_ready()
    assert refused is None, refused
    return storage, StatementCounter(storage)


def sqlite_url(db_path: str) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def checkpoint_and_copy(src: str, dst: str) -> float:
    """Fold the WAL into the main file, then copy it: a clean store per level."""
    conn = sqlite3.connect(src)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(dst + suffix):
            os.remove(dst + suffix)
    t0 = time.perf_counter()
    shutil.copyfile(src, dst)
    return round(time.perf_counter() - t0, 2)


async def clone_schema(url: str, source: str, target: str, wall: float) -> tuple[DatabaseStorage, StatementCounter, float]:
    """Postgres: a fresh schema built by vfs's own DDL, filled by INSERT ... SELECT from *source*."""
    t0 = time.perf_counter()
    short = DatabaseStorage(url=url, schema=source)
    assert await short._host.ensure_ready() is None
    async with short._host.engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {target} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {target}"))
    await short.close()
    storage, counter = await open_store(url, schema=target, wall=wall)
    tables = storage._host.tables.metadata.sorted_tables
    async with storage._host.engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"TRUNCATE TABLE {target}.{table.name}"))
        for table in tables:
            await conn.execute(text(f"INSERT INTO {target}.{table.name} SELECT * FROM {source}.{table.name}"))
        for table in tables:
            for column in table.columns:
                if column.identity is not None or column.autoincrement is True:
                    await conn.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{target}.{table.name}', '{column.name}'), "
                            f"COALESCE((SELECT MAX({column.name}) FROM {target}.{table.name}), 1))"
                        )
                    )
        await conn.execute(text(f"ANALYZE"))
    return storage, counter, round(time.perf_counter() - t0, 2)


async def drop_schema(url: str, schema: str) -> None:
    short = DatabaseStorage(url=url)
    assert await short._host.ensure_ready() is None
    async with short._host.engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    await short.close()


async def dirty_paths(storage: DatabaseStorage) -> set[str]:
    """The paths of the live file rows awaiting the index."""
    t = storage._host.tables
    async with storage._host.engine.connect() as conn:
        rows = await conn.execute(
            select(t.entry.c.path).where(
                t.entry.c.encoded.is_(False), t.entry.c.deleted_at.is_(None), t.entry.c.kind == "file"
            )
        )
        return {row.path for row in rows}


async def table_counts(storage: DatabaseStorage) -> dict[str, int]:
    t = storage._host.tables
    out: dict[str, int] = {}
    async with storage._host.engine.connect() as conn:
        for name in ("entry", "chunks", "posting_list", "lex_postings"):
            out[name] = (await conn.execute(select(func.count()).select_from(getattr(t, name)))).scalar_one()
        out["files"] = (
            await conn.execute(
                select(func.count()).select_from(t.entry).where(t.entry.c.kind == "file", t.entry.c.deleted_at.is_(None))
            )
        ).scalar_one()
        out["not_encoded"] = (
            await conn.execute(
                select(func.count())
                .select_from(t.entry)
                .where(t.entry.c.encoded.is_(False), t.entry.c.deleted_at.is_(None), t.entry.c.kind == "file")
            )
        ).scalar_one()
        out["epoch"] = (await conn.execute(select(t.meta.c.current_gram_epoch))).scalar_one()
    return out


def db_size_mb(db_path: str) -> float:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(db_path + suffix)
        except FileNotFoundError:
            pass
    return round(total / 1_000_000, 1)


async def timed(coro):
    t0 = time.perf_counter()
    result = await coro
    return result, round(time.perf_counter() - t0, 4)
