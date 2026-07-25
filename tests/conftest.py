"""Shared fixtures for the live suite.

Engines come from a fixture that disposes them. In-memory SQLite makes an
abandoned connection cheap, but the suite also runs against real servers
(see ``--mssql``), where every undisposed engine holds a socket and a
server-side session for the length of the run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, create_engine

from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A disposable in-memory SQLite engine for DDL and Core round-trips."""
    engine = create_engine("sqlite://")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
async def _dispose_test_local_memory_storages(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Dispose every ``InMemoryStorage`` a test made, on the test's own loop.

    Each instance owns an async engine whose driver thread reports back to
    the loop it was created on; an instance dropped without ``close()``
    would otherwise finalize at garbage-collection time against a closed
    loop. ``close()`` is idempotent, so already-closed instances are fine.
    """
    created: list[InMemoryStorage] = []
    original = InMemoryStorage.__init__

    def tracking(self: InMemoryStorage, **kwargs: Any) -> None:
        original(self, **kwargs)
        created.append(self)

    monkeypatch.setattr(InMemoryStorage, "__init__", tracking)
    yield
    for storage in created:
        await storage.close()
