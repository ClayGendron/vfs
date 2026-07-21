"""Shared fixtures for the live suite.

Engines come from a fixture that disposes them. In-memory SQLite makes an
abandoned connection cheap, but the suite also runs against real servers
(see ``--mssql``), where every undisposed engine holds a socket and a
server-side session for the length of the run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, create_engine

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A disposable in-memory SQLite engine for DDL and Core round-trips."""
    engine = create_engine("sqlite://")
    try:
        yield engine
    finally:
        engine.dispose()
