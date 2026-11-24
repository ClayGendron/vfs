"""Shared pieces for the probes of this work directory.

Run each probe from the repository root: ``uv run --no-sync python agents/<this directory>/probes/<probe>.py``.
A probe that needs Postgres reads ``VFS_PROBE_POSTGRES_URL`` and skips that leg when the variable is unset.
Nothing here touches ``src/`` or ``tests/``. Costs are counted, never timed.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    event,
    text,
)

from vfs import AsyncVirtualFileSystem, InMemoryStorage
from vfs.authority import Authority, Principal

POSTGRES_URL = os.environ.get("VFS_PROBE_POSTGRES_URL")
SQLITE_URL = "sqlite+aiosqlite:///:memory:"

SYSTEM = Authority.system()
ANON = Authority.anonymous()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))

LIVE = text("deleted_at IS NULL")
TRASHED = text("deleted_at IS NOT NULL")


def entries(meta: MetaData, shape: str, name: str = "probe_entries") -> Table:
    """A table with the key columns of ``vfs_entries`` under one of two key shapes.

    ``live_only`` makes both name keys partial, over the live rows. ``generation`` adds
    ``name_generation``, 0 on a live row and the row's own ``id`` on a deleted one, to both keys.
    """
    columns: list[Any] = [
        Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
        Column("entry_id", String(26), nullable=False, unique=True),
        Column("parent_id", String(26)),
        Column("path", String(1024), nullable=False),
        Column("name", String(255), nullable=False),
        Column("kind", String(32), nullable=False),
        Column("version", BigInteger, nullable=False, default=1),
        Column("deleted_at", DateTime(timezone=True)),
        Column("trash_root_id", String(26)),
    ]
    live_side = {"sqlite_where": LIVE, "postgresql_where": LIVE}
    trashed_side = {"sqlite_where": TRASHED, "postgresql_where": TRASHED}
    if shape == "live_only":
        columns += [
            Index(f"uq_{name}_live_path", "path", unique=True, **live_side),
            Index(f"uq_{name}_live_children", "parent_id", "name", unique=True, **live_side),
            Index(f"ix_{name}_path", "path"),
        ]
    elif shape == "generation":
        columns += [
            Column("name_generation", BigInteger, nullable=False, server_default="0"),
            UniqueConstraint("path", "name_generation", name=f"uq_{name}_path_generation"),
            UniqueConstraint("parent_id", "name_generation", "name", name=f"uq_{name}_parent_generation_name"),
            CheckConstraint(
                "(deleted_at IS NULL AND name_generation = 0) OR (deleted_at IS NOT NULL AND name_generation <> 0)",
                name=f"ck_{name}_generation_agrees",
            ),
        ]
    else:
        raise ValueError(shape)
    columns.append(Index(f"ix_{name}_trashed_path", "path", "deleted_at", **trashed_side))
    return Table(name, meta, *columns)


def make() -> tuple[AsyncVirtualFileSystem, InMemoryStorage]:
    storage = InMemoryStorage()
    return AsyncVirtualFileSystem(storage=storage), storage


def brief(result: Any) -> str:
    """One line for a Result: its errors, or its rows as path, kind, version and status."""
    parts: list[str] = []
    for error in getattr(result, "errors", None) or []:
        parts.append(f"ERROR {getattr(error.kind, 'value', error.kind)} at {error.path} {error.message!r}")
    rows = []
    for row in getattr(result, "observations", None) or []:
        bits = [str(row.path)]
        for field in ("kind", "version", "status"):
            value = getattr(row, field, None)
            if value is not None:
                bits.append(f"{field}={value}")
        rows.append("(" + " ".join(bits) + ")")
    if rows:
        parts.append(f"{len(rows)} row(s): " + " ".join(rows[:6]) + (" ..." if len(rows) > 6 else ""))
    return " | ".join(parts) or "empty result"


def show(label: str, result: Any) -> Any:
    print(f"  {label}: {brief(result)}")
    return result


class Statements:
    """Counts cursor executions on a storage's engine, by leading verb."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._engine = storage._host.engine.sync_engine
        self.count = 0
        self.by_verb: Counter[str] = Counter()

    def _before(self, conn, cursor, statement, parameters, context, executemany) -> None:
        verb = statement.lstrip().split(None, 1)[0].upper()
        if verb in {"BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK", "ANALYZE"}:
            return
        self.count += 1
        self.by_verb[verb] += 1

    def __enter__(self) -> Statements:
        event.listen(self._engine, "before_cursor_execute", self._before)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self._engine, "before_cursor_execute", self._before)

    def report(self, label: str) -> None:
        print(f"  {label}: statements={self.count} {dict(sorted(self.by_verb.items()))}")
