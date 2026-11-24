"""The fixtures every test of the kernel's store shares: the place a test names, and a maker of stores on it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.support.server_schemas import server_storage
from vfs import RecordPlace, SQLiteStorage
from vfs.kernel_store import KernelStore

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Callable


@pytest.fixture
async def place(request: pytest.FixtureRequest, tmp_path: pathlib.Path) -> AsyncIterator[RecordPlace]:
    """The place the test names: a SQLite file a storage names, a database in memory, or a Postgres schema."""
    kind = request.param
    if kind == "file":
        place = SQLiteStorage(path=str(tmp_path / "knowledge.db")).record_place
        assert place is not None
        yield place
    elif kind == "memory":
        yield RecordPlace.in_memory()
    else:
        async with server_storage("VFS_TEST_POSTGRES_URL") as storage:
            place = storage.record_place
            assert place is not None
            yield place


@pytest.fixture
async def stores(place: RecordPlace) -> AsyncIterator[Callable[..., KernelStore]]:
    """A maker of stores on the test's place, each closed at teardown."""
    made: list[KernelStore] = []

    def make(**options: Any) -> KernelStore:
        made.append(store := KernelStore(place, **options))
        return store

    yield make
    for store in made:
        await store.close()
