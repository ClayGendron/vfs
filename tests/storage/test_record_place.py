"""The place a storage names for the kernel's records: its own database, read with no I/O.

A storage answers one question with one value: where the kernel keeps
its records. A SQLite file names itself, Postgres names its database and
schema, a database in memory names a second one in memory, and a
storage on the generic floor, or on a memory URL SQLAlchemy reads as a
file, names none. A place never shows a password.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import AsyncAdaptedQueuePool, Pool

from tests.support.floor_dialect import FLOOR_URL
from vfs import DatabaseStorage, InMemoryStorage, PostgresStorage, RecordPlace, SQLiteStorage
from vfs.storage import SupportsRecordPlace
from vfs.storage.backends.database.drivers import url_of_place

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

PASSWORD = "hunter2"
"""A password no place may print."""

SERVER = f"postgresql+asyncpg://vfs:{PASSWORD}@localhost:1/vfs"
"""A Postgres URL that nothing listens on: a place is read without a connection."""


def _creator() -> Any:
    """A connection maker the application gives; nothing calls it while a place is read."""
    raise AssertionError("a place is read with no connection")


@pytest.fixture
def connects() -> Iterator[list[object]]:
    """Every connection any pool opens while the test runs."""
    opened: list[object] = []

    def connected(*connection: object) -> None:
        opened.append(connection)

    event.listen(Pool, "connect", connected)
    yield opened
    event.remove(Pool, "connect", connected)


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


class TestSqlite:
    async def test_a_sqlite_storage_names_its_own_file(self, tmp_path: pathlib.Path, connects: list[object]) -> None:
        """Guards a place of another file, a place that drops the application's creator, and one that keeps its pool."""
        path = tmp_path / "knowledge.db"
        pool = AsyncAdaptedQueuePool(_creator)
        arguments = {"creator": _creator, "connect_args": {"timeout": 3}}
        storage = SQLiteStorage(path=path, engine_arguments=arguments)
        pooled = SQLiteStorage(path=path, engine_arguments={"pool": pool})
        place = storage.record_place
        assert place is not None
        assert isinstance(storage, SupportsRecordPlace)
        assert (place.url, place.label, place.schema, place.durable) == (storage.engine.url, str(path), None, True)
        assert isinstance(place.url, URL) and place.url.database == str(path)
        assert place.engine_arguments == {"creator": _creator, "connect_args": {"timeout": 3}}
        assert pooled.record_place is not None
        assert pooled.record_place.engine_arguments == {}
        assert (sorted(tmp_path.iterdir()), connects) == ([], [])
        await storage.close()
        await pooled.close()

    async def test_a_path_with_a_question_mark_keeps_it(self, tmp_path: pathlib.Path) -> None:
        """Guards a place handed as text, where the question mark would start a query."""
        path = tmp_path / "notes?v2.db"
        storage = SQLiteStorage(path=path)
        place = storage.record_place
        assert place is not None
        assert isinstance(place.url, URL)
        assert (place.url.database, place.label) == (str(path), str(path))
        assert place.url.query == storage.engine.url.query
        queried = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/a.db?timeout=7")
        queried_place = queried.record_place
        assert queried_place is not None and isinstance(queried_place.url, URL)
        assert dict(queried_place.url.query) == {"timeout": "7"}
        assert sorted(tmp_path.iterdir()) == []
        await storage.close()
        await queried.close()

    async def test_an_in_memory_storage_names_a_place_in_memory(self, connects: list[object]) -> None:
        storage = InMemoryStorage()
        place = storage.record_place
        assert place == RecordPlace.in_memory()
        assert place is not None
        assert (str(place.url), place.label, place.durable, place.engine_arguments) == (
            "sqlite+aiosqlite://",
            "memory",
            False,
            None,
        )
        assert connects == []
        await storage.close()

    async def test_a_memory_url_read_as_a_file_names_no_place(self) -> None:
        """Guards a place on a URL SQLAlchemy opens as a file, whose database is in memory all the same."""
        storage = DatabaseStorage(url="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")
        assert storage.record_place is None
        await storage.close()

    async def test_a_storage_on_the_generic_floor_names_no_place(self) -> None:
        storage = DatabaseStorage(url=FLOOR_URL)
        assert storage.record_place is None
        await storage.close()


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------


class TestPostgres:
    async def test_a_postgres_storage_names_its_own_database_and_schema(self, connects: list[object]) -> None:
        """Guards a place in another schema, and one that hands the store the mount's own pool."""
        storage = PostgresStorage(url=SERVER, schema="tenant", engine_arguments={"pool_size": 7})
        place = storage.record_place
        assert place is not None
        assert (place.url, place.schema, place.label, place.durable) == (storage.engine.url, "tenant", "tenant", True)
        assert place.engine_arguments == {"pool_size": 7}
        pooled = PostgresStorage(url=SERVER, engine_arguments={"pool": AsyncAdaptedQueuePool(_creator)})
        assert pooled.record_place is not None
        assert pooled.record_place.engine_arguments == {}
        unschemed = PostgresStorage(url=SERVER)
        assert unschemed.record_place is not None
        assert (unschemed.record_place.schema, unschemed.record_place.label) == (None, "the default schema")
        assert unschemed.record_place.engine_arguments is None
        assert connects == []
        for built in (storage, pooled, unschemed):
            await built.close()


# ---------------------------------------------------------------------------
# What a place prints, and which places a store takes
# ---------------------------------------------------------------------------


class TestWhatAPlaceShows:
    async def test_a_label_never_holds_the_password(self) -> None:
        """Guards a place whose label or repr prints its URL, as text or as SQLAlchemy's URL."""
        storages = [PostgresStorage(url=SERVER), PostgresStorage(url=make_url(SERVER))]
        places = [storage.record_place for storage in storages]
        places.append(RecordPlace(url=SERVER, label="the server", engine_arguments={"password": PASSWORD}))
        for place in places:
            assert place is not None
            assert PASSWORD not in place.label
            assert PASSWORD not in repr(place)
        for storage in storages:
            await storage.close()

    def test_a_place_of_another_dialect_is_refused_when_the_store_is_built(self) -> None:
        """Guards a store built on a dialect it keeps no records in, and a refusal that prints the URL."""
        place = RecordPlace(url=f"mysql+aiomysql://vfs:{PASSWORD}@db.example/vfs", label="the server")
        with pytest.raises(ValueError, match="SQLite or Postgres") as refused:
            url_of_place(place)
        message = str(refused.value)
        assert "'mysql'" in message
        assert (PASSWORD in message, "db.example" in message) == (False, False)
        for served in (SERVER, "sqlite+aiosqlite:///records.db", "sqlite+aiosqlite://"):
            assert url_of_place(RecordPlace(url=served, label="served")) == make_url(served)
