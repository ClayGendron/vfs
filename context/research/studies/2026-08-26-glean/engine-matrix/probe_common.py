"""Shared plumbing for the engine-matrix probes (throwaway research code).

Every engine is reached through a SQLAlchemy async engine; each probe is a
list of (label, sql, params) executed in order, with errors captured and
printed rather than raised so one refused statement never hides the rest.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from sqlalchemy import bindparam, event, text
from sqlalchemy.ext.asyncio import create_async_engine

URLS = {
    "postgres_compose": "postgresql+asyncpg://vfs:vfs@localhost:54320/vfs",
    "pgvector": "postgresql+asyncpg://vfs:vfs@localhost:54321/vfs",
    "mysql9": "mysql+aiomysql://vfs:vfs@localhost:33064/vfs?charset=utf8mb4",
    "mariadb118": "mariadb+aiomysql://vfs:vfs@localhost:33063/vfs?charset=utf8mb4",
    "mssql2025": (
        "mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14331/master"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    ),
    "mssql2025_glean": (
        "mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14331/glean"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    ),
    "oracle23": "oracle+oracledb_async://vfs:vfs@localhost:15210/?service_name=FREEPDB1",
    "oracle_regular": "oracle+oracledb_async://vfs:vfs@localhost:15211/?service_name=FREEPDB1",
    "oracle_regular_system": "oracle+oracledb_async://system:vfs-sys@localhost:15211/?service_name=FREEPDB1",
    "oracle_regular_cdb": "oracle+oracledb_async://system:vfs-sys@localhost:15211/?service_name=FREE",
    "sqlite": "sqlite+aiosqlite:///{path}",
}


def make_engine(name: str, sqlite_path: str = "/tmp/glean_probe.sqlite", load_vec: bool = True):
    url = URLS[name]
    if name == "sqlite":
        url = url.format(path=sqlite_path)
    eng = create_async_engine(url, echo=False)
    if name == "sqlite" and load_vec:
        import sqlite_vec  # uv run --with sqlite-vec

        @event.listens_for(eng.sync_engine, "connect")
        def _load(dbapi_conn, _rec):
            raw = dbapi_conn._connection._conn  # aiosqlite -> sqlite3
            raw.enable_load_extension(True)
            sqlite_vec.load(raw)
            raw.enable_load_extension(False)

    return eng


async def run(name: str, steps, *, autocommit: bool = True, quiet: bool = False, **kw):
    """Run steps against one engine; return {label: rows|error}."""
    eng = make_engine(name, **kw)
    out: dict[str, object] = {}
    try:
        async with eng.connect() as conn:
            if autocommit:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            for step in steps:
                label, sql, *rest = step
                params = rest[0] if rest else {}
                expanding = rest[1] if len(rest) > 1 else ()
                stmt = text(sql).bindparams(*[bindparam(n, expanding=True) for n in expanding])
                t0 = time.perf_counter()
                try:
                    res = await conn.execute(stmt, params)
                    rows = [tuple(r) for r in res.fetchall()] if res.returns_rows else res.rowcount
                    if not autocommit:
                        await conn.commit()
                    dt = time.perf_counter() - t0
                    out[label] = {"ok": True, "rows": rows, "ms": round(dt * 1000, 1)}
                    if not quiet:
                        shown = rows if not isinstance(rows, list) or len(rows) <= 12 else rows[:12] + ["..."]
                        print(f"[{name}] {label}: OK {dt*1000:.1f}ms -> {shown}")
                except Exception as exc:  # noqa: BLE001
                    if not autocommit:
                        await conn.rollback()
                    msg = " | ".join(line.strip() for line in str(exc).splitlines() if line.strip())[:600]
                    out[label] = {"ok": False, "error": f"{type(exc).__name__}: {msg}"}
                    if not quiet:
                        print(f"[{name}] {label}: ERROR {type(exc).__name__}: {msg}")
    finally:
        await eng.dispose()
    return out


def dump(path: str, data) -> None:
    with open(path, "w") as fh:
        json.dump(data, fh, indent=1, default=str)


def main(coro):
    asyncio.run(coro)
