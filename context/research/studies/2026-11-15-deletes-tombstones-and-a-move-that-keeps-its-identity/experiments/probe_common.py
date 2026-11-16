"""Shared helpers for study 01's probes: a fresh in-memory vfs, compact result printing, raw row dumps.

Run a probe from the repository root as ``uv run --no-sync python <script>``.
Nothing here touches ``src/`` or ``tests/``; every probe owns a private
in-process SQLite database that vanishes when the process ends.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path as FsPath
from typing import Any

from sqlalchemy import event, select

from vfs import AsyncVirtualFileSystem, InMemoryStorage
from vfs.authority import Authority, Principal

sys.path.insert(0, str(FsPath(__file__).parent))

SYSTEM = Authority.system()
ANON = Authority.anonymous()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))
CAROL = Authority.of(Principal("carol"))

CALLERS = {"system": SYSTEM, "alice": ALICE, "bob": BOB, "anonymous": ANON}


def make() -> tuple[AsyncVirtualFileSystem, InMemoryStorage]:
    storage = InMemoryStorage()
    return AsyncVirtualFileSystem(storage=storage), storage


class Aliases:
    """Stable short names for ULIDs, in order of first sight, so output diffs cleanly across runs."""

    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def of(self, entry_id: str | None) -> str | None:
        if entry_id is None:
            return None
        if entry_id not in self._names:
            self._names[entry_id] = f"E{len(self._names) + 1}"
        return self._names[entry_id]


ALIAS = Aliases()


def brief(result: Any) -> str:
    """One line for a Result: its errors, or its observations as path/kind/version/status."""
    errors = getattr(result, "errors", None) or []
    parts: list[str] = []
    for error in errors:
        data = getattr(error, "data", None)
        severity = getattr(error, "severity", None)
        parts.append(
            f"ERROR kind={getattr(error.kind, 'value', error.kind)} path={error.path} "
            f"sev={getattr(severity, 'value', severity)} msg={error.message!r} data={data}"
        )
    rows = []
    for row in getattr(result, "observations", None) or []:
        bits = [str(row.path)]
        for name in ("kind", "version", "status", "size_bytes", "deleted_at"):
            value = getattr(row, name, None)
            if value is not None:
                bits.append(f"{name}={'set' if name == 'deleted_at' else value}")
        content = getattr(row, "content", None)
        if content is not None:
            bits.append(f"content={content[:40]!r}")
        rows.append("(" + " ".join(bits) + ")")
    if rows:
        parts.append(f"{len(rows)} row(s): " + " ".join(rows[:12]) + (" ..." if len(rows) > 12 else ""))
    if not parts:
        parts.append("empty result (no rows, no errors)")
    return " | ".join(parts)


def show(label: str, result: Any) -> Any:
    print(f"  {label}: {brief(result)}")
    return result


async def entries(storage: InMemoryStorage, prefix: str = "/", *, limit: int = 40) -> None:
    """Print the raw vfs_entries rows at and under *prefix*, tombstones included."""
    entry = storage._host.tables.entry
    stmt = (
        select(
            entry.c.id,
            entry.c.entry_id,
            entry.c.parent_id,
            entry.c.path,
            entry.c.name,
            entry.c.kind,
            entry.c.owner_id,
            entry.c.version,
            entry.c.everyone_level,
            entry.c.deleted_at,
            entry.c.trash_root_id,
            entry.c.content_hash,
        )
        .where((entry.c.path == prefix) | entry.c.path.like(prefix.rstrip("/") + "/%"))
        .order_by(entry.c.path)
    )
    async with storage._host.session_factory() as conn:
        found = (await conn.execute(stmt)).mappings().all()
    print(f"  rows under {prefix}: {len(found)}")
    for row in found[:limit]:
        print(
            f"    id={ALIAS.of(row['entry_id'])} path={row['path']} parent={ALIAS.of(row['parent_id'])} "
            f"name={row['name']!r} kind={row['kind']} owner={row['owner_id']} v={row['version']} "
            f"label={row['everyone_level']} deleted={'yes' if row['deleted_at'] is not None else 'no'} "
            f"trash_root={ALIAS.of(row['trash_root_id'])} hash={(row['content_hash'] or '')[:8]}"
        )


async def versions(storage: InMemoryStorage) -> None:
    """Print every version row with its subjects, by entry alias."""
    tables = storage._host.tables
    v, s = tables.versions, tables.version_subjects
    async with storage._host.session_factory() as conn:
        found = (await conn.execute(select(v).order_by(v.c.entry_id, v.c.version_number))).mappings().all()
        subjects = (await conn.execute(select(s))).mappings().all()
    by_key: dict[tuple[str, int], list[str]] = {}
    for row in subjects:
        by_key.setdefault((row["entry_id"], row["version_number"]), []).append(row["principal_id"])
    print(f"  version rows: {len(found)}")
    for row in found:
        body = row["content"]
        print(
            f"    id={ALIAS.of(row['entry_id'])} n={row['version_number']} snapshot={row['is_snapshot']} "
            f"actor={row['actor']} subjects={sorted(by_key.get((row['entry_id'], row['version_number']), []))} "
            f"hash={row['content_hash'][:8]} content={body[:30]!r}"
            if body is not None
            else f"    id={ALIAS.of(row['entry_id'])} n={row['version_number']} snapshot={row['is_snapshot']} "
            f"actor={row['actor']} subjects={sorted(by_key.get((row['entry_id'], row['version_number']), []))} "
            f"hash={row['content_hash'][:8]} content=None diff={'yes' if row['version_diff'] else 'no'}"
        )


async def edges(storage: InMemoryStorage, *, include_fs: bool = False) -> None:
    e = storage._host.tables.edges
    async with storage._host.session_factory() as conn:
        found = (await conn.execute(select(e).order_by(e.c.id))).mappings().all()
    kept = [row for row in found if include_fs or row["edge_type"] != "fs"]
    print(f"  edge rows: {len(kept)} (fs mirror rows {'shown' if include_fs else 'hidden'}; total {len(found)})")
    for row in kept:
        print(
            f"    {ALIAS.of(row['source_id'])} -[{row['edge_type']}]-> {ALIAS.of(row['target_id'])} "
            f"provenance={row['provenance']}"
        )


async def grants(storage: InMemoryStorage) -> None:
    g = storage._host.tables.grants
    async with storage._host.session_factory() as conn:
        found = (await conn.execute(select(g).order_by(g.c.id))).mappings().all()
    print(f"  grant rows: {len(found)}")
    for row in found:
        print(f"    principal={row['principal_id']} prefix={row['path_prefix']} level={row['level']}")


async def table_counts(storage: InMemoryStorage) -> dict[str, int]:
    tables = storage._host.tables
    counts: dict[str, int] = {}
    async with storage._host.session_factory() as conn:
        for name in ("entry", "content", "blobs", "versions", "version_subjects", "chunks", "segments", "edges"):
            table = getattr(tables, name)
            counts[name] = len((await conn.execute(select(table.c[next(iter(table.c.keys()))]))).all())
    return counts


class StatementCounter:
    """Counts cursor executions on the storage's engine: statements, executemany parameter sets, by leading verb."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._engine = storage._host.engine.sync_engine
        self.statements = 0
        self.parameter_sets = 0
        self.by_verb: Counter[str] = Counter()
        self.samples: list[str] = []

    def _on(self, conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        self.statements += 1
        self.parameter_sets += len(parameters) if executemany else 1
        verb = statement.lstrip().split(None, 1)[0].upper()
        self.by_verb[verb + ("(many)" if executemany else "")] += 1
        self.samples.append(" ".join(statement.split())[:150] + (f"  [x{len(parameters)}]" if executemany else ""))

    def __enter__(self) -> StatementCounter:
        event.listen(self._engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self._engine, "before_cursor_execute", self._on)

    def report(self, label: str, *, samples: bool = False) -> None:
        print(f"  {label}: statements={self.statements} parameter_sets={self.parameter_sets} by_verb={dict(self.by_verb)}")
        if samples:
            for sample in self.samples:
                print(f"      {sample}")
