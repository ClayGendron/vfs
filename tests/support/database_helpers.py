"""Shared helpers for the database-backend test files.

The per-module suites under ``tests/storage/database/`` all build the
same sqlite URL, and several of them need the same doubles: a driver
error the retry classifier recognizes, and a session whose UPDATEs
answer with canned RETURNING rows (the VALUES-join arm sqlite cannot
execute). Helpers used by a single file stay in that file.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from vfs.paths import Path
from vfs.storage.backends.database.staging import StagedEntry

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

    from vfs.storage.backends.database.staging import PersistenceState


# ---------------------------------------------------------------------------
# Mount URLs
# ---------------------------------------------------------------------------


def _url(tmp_path: pathlib.Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite"


# ---------------------------------------------------------------------------
# Driver-error doubles
# ---------------------------------------------------------------------------


class _SqliteError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("locked")
        self.sqlite_errorcode = code


# ---------------------------------------------------------------------------
# Session doubles for the arms sqlite cannot execute
# ---------------------------------------------------------------------------


class _CannedReturning:
    """Result double: canned RETURNING mappings, iterable as row objects."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows

    def all(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(**row) for row in self._rows]

    def __iter__(self) -> Iterator[SimpleNamespace]:
        return iter(SimpleNamespace(**row) for row in self._rows)

    @property
    def rowcount(self) -> int:
        return len(self._rows)


class _ReturningSession:
    """Session double for the VALUES-join arm SQLite cannot execute.

    UPDATE statements answer with the canned RETURNING rows; the guard
    miss re-probe (a SELECT) answers with *probed*.
    """

    def __init__(self, returned: list[dict[str, object]], probed: list[dict[str, object]] | None = None) -> None:
        self.returned = returned
        self.probed = probed if probed is not None else []
        self.statements: list[Any] = []

    def get_bind(self) -> SimpleNamespace:
        # A real dialect so probe statements compile; flags declared as
        # the double intends, independent of the driver's own defaults.
        dialect = postgresql.dialect()
        dialect.update_returning = True
        dialect.update_returning_multifrom = True
        dialect.supports_sane_rowcount = True
        dialect.supports_sane_multi_rowcount = False
        return SimpleNamespace(dialect=dialect)

    async def execute(self, stmt: Any, params: Any = None) -> _CannedReturning:
        self.statements.append(stmt)
        if isinstance(stmt, Select):
            return _CannedReturning(self.probed)
        return _CannedReturning(self.returned)


# ---------------------------------------------------------------------------
# Staged material
# ---------------------------------------------------------------------------


def _staged_material(path: str, entry_id: str, *, persistence: PersistenceState = "update") -> StagedEntry:
    return StagedEntry(
        path=Path(path),
        parent=Path("/"),
        kind="file",
        persistence=persistence,
        entry_id=entry_id,
        content="mine",
        base_version=1,
        version=2,
    )
