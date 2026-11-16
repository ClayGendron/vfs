"""Experiment 04-a: run the SQLite conformance contract with the engine wearing the generic floor.

Run: PYTHONPATH=<this folder> uv run pytest -p generic_floor_plugin
"tests/storage/test_conformance.py::TestSqliteConformance" --no-cov -q, with
FLOOR_KEEPS_SQLITE_SETTINGS=1, FLOOR_KEEPS_NAME=1 or FLOOR_ONE_FIELD=<field> for the
variants below. It swaps the
profile resolver the engine host calls, so every SQLite storage the suite builds
resolves to ``GENERIC`` stamped with the name ``exotic``, as an unknown dialect would.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from vfs.storage.backends.database import engine
from vfs.storage.backends.database.dialects import GENERIC

_REAL = engine.profile_for


def _floor(dialect_name: str):
    if dialect_name != "sqlite":
        return _REAL(dialect_name)
    field = os.environ.get("FLOOR_ONE_FIELD")
    if field:
        # Variant c: SQLite's own profile with one field taken from the floor.
        return replace(_REAL("sqlite"), **{field: getattr(GENERIC, field)})
    if os.environ.get("FLOOR_KEEPS_SQLITE_SETTINGS") == "1":
        # Variant b: the floor's policy, with SQLite's own connection facts kept.
        sqlite = _REAL("sqlite")
        # Variant d keeps the name too, so the engine installs pysqlite's transaction fix.
        return replace(
            GENERIC,
            name="sqlite" if os.environ.get("FLOOR_KEEPS_NAME") == "1" else "exotic",
            session_settings=sqlite.session_settings,
            file_settings=sqlite.file_settings,
            retryable_sqlite_codes=sqlite.retryable_sqlite_codes,
        )
    return replace(GENERIC, name="exotic")


@pytest.fixture(autouse=True)
def _generic_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "profile_for", _floor)
