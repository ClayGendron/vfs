"""Shared fixtures for the live suite.

Engines come from a fixture that disposes them. In-memory SQLite makes an
abandoned connection cheap, but the suite also runs against real servers
(the engine legs selected by ``VFS_TEST_<ENGINE>_URL`` below), where every
undisposed engine holds a socket and a server-side session for the length
of the run.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final

import pytest
from sqlalchemy import Engine, create_engine

from vfs.storage.backends.database import DatabaseStorage

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
async def _dispose_test_local_storages(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Close every ``DatabaseStorage`` a test made, on the test's own loop.

    Each instance owns an async engine whose driver thread reports back to
    the loop it was created on; an instance dropped without ``close()``
    would otherwise finalize at garbage-collection time against a closed
    loop, which under workers surfaces as an unhandled thread exception in
    whatever test runs next. ``close()`` is idempotent, so already-closed
    instances are fine, and a borrowed-engine close never disposes. A
    storage a module-scoped fixture built is constructed before this
    fixture patches, so it is not tracked and must close in its fixture.
    """
    created: list[DatabaseStorage] = []
    original = DatabaseStorage.__init__

    def tracking(self: DatabaseStorage, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(DatabaseStorage, "__init__", tracking)
    yield
    for storage in created:
        await storage.close()


# ---------------------------------------------------------------------------
# Selection: the real-engine legs
# ---------------------------------------------------------------------------

ENGINE_URLS: Final = {
    "postgres": ("VFS_TEST_POSTGRES_URL",),
    "mariadb": ("VFS_TEST_MARIADB_URL", "VFS_TEST_MYSQL_URL"),
    "mssql": ("VFS_TEST_MSSQL_URL",),
    "oracle": ("VFS_TEST_ORACLE_URL",),
}
"""Each engine marker and the URL variables that make its leg runnable."""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect every engine leg whose URL is unset.

    Deselection rather than a skip: a skipped engine item still pays its
    fixtures and lands in the summary line, and a local run has nothing to
    report about servers it was never pointed at. The fixture-time skip in
    ``server_storage`` stays as the backstop for a leg selected by hand.
    The ``slow`` marks stay plain markers: everything runs by default, and
    ``-m "not slow"`` is the opt-out.
    """
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if _engine_leg_without_url(item):
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def _engine_leg_without_url(item: pytest.Item) -> bool:
    legs = [name for name in ENGINE_URLS if item.get_closest_marker(name)]
    return bool(legs) and not any(os.environ.get(var) for name in legs for var in ENGINE_URLS[name])
