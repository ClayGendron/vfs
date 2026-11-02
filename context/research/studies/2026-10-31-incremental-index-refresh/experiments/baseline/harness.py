"""Shared helpers: open a store, count SQL statements, count index rows, time a coroutine."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

from sqlalchemy import event, func, select

from vfs.storage.backends import DatabaseStorage


class StatementCounter:
    def __init__(self, storage: DatabaseStorage) -> None:
        self.count = 0
        self.rows_bound = 0
        self.kinds: dict[str, int] = {}
        self.enabled = False

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if not self.enabled:
                return
            self.count += 1
            verb = statement.lstrip().split(" ", 1)[0].upper()
            self.kinds[verb] = self.kinds.get(verb, 0) + 1
            if executemany:
                self.rows_bound += len(parameters)

    def reset(self) -> None:
        self.count, self.rows_bound, self.kinds = 0, 0, {}

    @contextmanager
    def capture(self):
        self.reset()
        self.enabled = True
        try:
            yield self
        finally:
            self.enabled = False


async def open_store(db_path: str, **kw) -> tuple[DatabaseStorage, StatementCounter]:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db_path}", **kw)
    refused = await storage._host.ensure_ready()
    assert refused is None, refused
    return storage, StatementCounter(storage)


async def table_counts(storage: DatabaseStorage) -> dict[str, int]:
    t = storage._host.tables
    out = {}
    async with storage._host.engine.connect() as conn:
        for name in ("posting_list", "lex_postings", "lex_docs", "lex_df", "chunks", "entry"):
            out[name] = (await conn.execute(select(func.count()).select_from(getattr(t, name)))).scalar_one()
        out["not_encoded"] = (
            await conn.execute(
                select(func.count())
                .select_from(t.entry)
                .where(t.entry.c.encoded.is_(False), t.entry.c.deleted_at.is_(None), t.entry.c.kind == "file")
            )
        ).scalar_one()
        out["epoch"] = (await conn.execute(select(t.meta.c.current_gram_epoch))).scalar_one()
        out["posting_mb"] = round(
            ((await conn.execute(select(func.sum(t.posting_list.c.byte_size)))).scalar_one() or 0) / 1_000_000, 2
        )
        lex_cols = [t.lex_postings.c.doc_ids, t.lex_postings.c.tfs, t.lex_postings.c.dls]
        lex_bytes = 0
        for c in lex_cols:
            lex_bytes += (await conn.execute(select(func.sum(func.length(c))))).scalar_one() or 0
        out["lex_posting_mb"] = round(lex_bytes / 1_000_000, 2)
    return out


def db_parts_mb(db_path: str) -> dict[str, float]:
    out = {}
    for suffix, key in (("", "db_main_mb"), ("-wal", "wal_mb")):
        try:
            out[key] = round(os.path.getsize(db_path + suffix) / 1_000_000, 1)
        except FileNotFoundError:
            out[key] = 0.0
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
    return result, round(time.perf_counter() - t0, 3)
