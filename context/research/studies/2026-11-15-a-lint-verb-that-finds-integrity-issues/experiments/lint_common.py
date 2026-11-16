"""Shared helpers for study 02's probes: a fresh in-memory vfs, direct SQL, compact result lines, statement counts.

Run a probe from the repository root as ``uv run --no-sync python <script>``.
Every probe owns private in-process SQLite databases that vanish with the process;
nothing here writes a file.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import event, func, select, text

from vfs import AsyncVirtualFileSystem, InMemoryStorage
from vfs.authority import Authority, Principal

sys.path.insert(0, str(FsPath(__file__).parent))

SYSTEM = Authority.system()
ANON = Authority.anonymous()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))


def make() -> tuple[AsyncVirtualFileSystem, InMemoryStorage]:
    storage = InMemoryStorage()
    return AsyncVirtualFileSystem(storage=storage), storage


def brief(result: Any) -> str:
    """One line for a Result: success, its errors, and its observations."""
    parts: list[str] = [f"success={getattr(result, 'success', None)}"]
    for error in getattr(result, "errors", None) or []:
        severity = getattr(error, "severity", None)
        parts.append(
            f"ERR kind={getattr(error.kind, 'value', error.kind)} sev={getattr(severity, 'value', severity)} "
            f"path={error.path} msg={str(error.message)[:170]!r}"
        )
    rows = []
    for row in getattr(result, "observations", None) or []:
        bits = [str(row.path)]
        for name in ("kind", "version", "status", "size_bytes", "lines"):
            value = getattr(row, name, None)
            if value is not None:
                bits.append(f"{name}={value}")
        for name in ("content", "data"):
            value = getattr(row, name, None)
            if value is not None:
                bits.append(f"{name}={value[:36]!r}")
        rows.append("(" + " ".join(bits) + ")")
    if rows:
        parts.append(f"{len(rows)} row(s): " + " ".join(rows[:8]) + (" ..." if len(rows) > 8 else ""))
    return " | ".join(parts)


def show(label: str, result: Any) -> Any:
    print(f"    {label}: {brief(result)}")
    return result


async def attempt(label: str, call: Any) -> Any:
    """Await *call* and print its Result, or the exception it raised."""
    try:
        return show(label, await call)
    except Exception as error:  # noqa: BLE001 - a probe reports whatever happens
        print(f"    {label}: RAISED {type(error).__name__}: {str(error)[:200]}")
        return None


async def run_sql(storage: InMemoryStorage, *statements: Any) -> list[int]:
    """Execute and commit statements on the store's own engine, as an out-of-band writer would."""
    counts: list[int] = []
    async with storage._host.session_factory() as session:
        for statement in statements:
            found = await session.execute(statement)
            counts.append(found.rowcount)
        await session.commit()
    return counts


async def fetch(storage: InMemoryStorage, statement: Any) -> list[Any]:
    async with storage._host.session_factory() as session:
        return list((await session.execute(statement)).all())


async def counts(storage: InMemoryStorage, *names: str) -> dict[str, int]:
    tables = storage._host.tables
    wanted = names or (
        "entry", "content", "blobs", "versions", "version_subjects", "chunks", "segments", "edges",
        "lex_docs", "grants", "relabels", "signals",
    )  # fmt: skip
    out: dict[str, int] = {}
    async with storage._host.session_factory() as session:
        for name in wanted:
            out[name] = (await session.execute(select(func.count()).select_from(getattr(tables, name)))).scalar_one()
    return out


async def plan(storage: InMemoryStorage, sql: str, params: dict[str, Any] | None = None) -> list[str]:
    """SQLite's EXPLAIN QUERY PLAN lines for *sql*."""
    async with storage._host.session_factory() as session:
        found = await session.execute(text("EXPLAIN QUERY PLAN " + sql), params or {})
        return [row[-1] for row in found.all()]


class StatementCounter:
    """Counts cursor executions on the storage's engine."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._engine = storage._host.engine.sync_engine
        self.statements = 0
        self.by_verb: Counter[str] = Counter()
        self.samples: list[str] = []

    def _on(self, conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        self.statements += 1
        self.by_verb[statement.lstrip().split(None, 1)[0].upper()] += 1
        self.samples.append(" ".join(statement.split())[:160])

    def __enter__(self) -> StatementCounter:
        event.listen(self._engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self._engine, "before_cursor_execute", self._on)
