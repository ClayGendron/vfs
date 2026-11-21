"""The two engines by name, and the warning a storage on any other dialect logs.

vfs supports SQLite and Postgres. ``SQLiteStorage`` and ``PostgresStorage``
name them: each is a ``DatabaseStorage`` that only constructs, and each
refuses a URL of another engine before it builds one. A storage on any
other dialect is served the generic floor and logs one ``WARNING`` on the
engine module's logger, once, when it is built.
"""

from __future__ import annotations

import inspect
import logging
import os
import pathlib
from typing import TYPE_CHECKING, Any

import pytest

from tests.support.floor_dialect import FLOOR_NAME, FLOOR_URL
from vfs import DatabaseStorage, InMemoryStorage, PostgresStorage, SQLiteStorage
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage import backends
from vfs.storage.backends.database import engine as engine_module

if TYPE_CHECKING:
    from collections.abc import Callable

ENGINE_LOGGER = "vfs.storage.backends.database.engine"
POSTGRES_URL = "postgresql+asyncpg://vfs:vfs@localhost:54320/vfs"
SECRET = "s3cret-pw"


def _floor_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == ENGINE_LOGGER]


async def _round_trip(storage: DatabaseStorage) -> str | None:
    """Write one file and read it back, then close the storage."""
    try:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])).success is True
        return (await storage.read(path=Path("/a.txt"))).one().content
    finally:
        await storage.close()


@pytest.fixture
def engines_built(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every URL an engine is built from in the test, so a refusal can show it built none."""
    built: list[object] = []
    real = engine_module.create_async_engine

    def recording(url: Any, **arguments: Any) -> Any:
        built.append(url)
        return real(url, **arguments)

    monkeypatch.setattr(engine_module, "create_async_engine", recording)
    return built


# ---------------------------------------------------------------------------
# The floor warns
# ---------------------------------------------------------------------------


class TestTheFloorWarns:
    async def test_a_storage_on_an_unknown_dialect_logs_one_warning_when_it_is_built(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Guards: a floor storage that says nothing, or says it again at every capabilities read."""
        with caplog.at_level(logging.WARNING, logger=ENGINE_LOGGER):
            storage = DatabaseStorage(url=FLOOR_URL)
            built = len(_floor_records(caplog))
            for _ in range(10):
                assert "search" not in storage.capabilities()
        assert (built, len(_floor_records(caplog))) == (1, 1)
        assert _floor_records(caplog)[0].levelno == logging.WARNING
        await storage.close()

    def test_a_construction_refused_for_its_arguments_logs_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        """Guards: a warning about a storage that was never built, because an argument check ran after the host."""
        with caplog.at_level(logging.WARNING, logger=ENGINE_LOGGER), pytest.raises(ValueError, match="search_wall"):
            DatabaseStorage(url=FLOOR_URL, search_wall_seconds=0)
        assert _floor_records(caplog) == []

    async def test_two_storages_on_the_floor_log_two_records(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger=ENGINE_LOGGER):
            storages = [DatabaseStorage(url=FLOOR_URL), DatabaseStorage(url=FLOOR_URL)]
        assert len(_floor_records(caplog)) == 2
        for storage in storages:
            await storage.close()

    async def test_the_record_names_the_dialect_and_the_two_engines_vfs_supports(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=ENGINE_LOGGER):
            storage = DatabaseStorage(url=FLOOR_URL)
        [record] = _floor_records(caplog)
        message = record.getMessage()
        for phrase in (repr(FLOOR_NAME), "generic floor", "testing only", "SQLite and Postgres"):
            assert phrase in message
        await storage.close()

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(lambda tmp: DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/a.db"), id="sqlite-url"),
            pytest.param(lambda tmp: SQLiteStorage(path=tmp / "a.db"), id="sqlite-path"),
            pytest.param(lambda _tmp: InMemoryStorage(), id="memory"),
            pytest.param(
                lambda _tmp: DatabaseStorage(url=os.environ["VFS_TEST_POSTGRES_URL"]),
                id="postgres-url",
                marks=pytest.mark.postgres,
            ),
            pytest.param(
                lambda _tmp: PostgresStorage(url=os.environ["VFS_TEST_POSTGRES_URL"]),
                id="postgres-named",
                marks=pytest.mark.postgres,
            ),
        ],
    )
    async def test_a_storage_on_a_supported_engine_logs_nothing(
        self,
        build: Callable[[pathlib.Path], DatabaseStorage],
        tmp_path: pathlib.Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger=ENGINE_LOGGER):
            storage = build(tmp_path)
            storage.capabilities()
        assert _floor_records(caplog) == []
        await storage.close()


# ---------------------------------------------------------------------------
# SQLiteStorage
# ---------------------------------------------------------------------------


class TestSQLiteStorage:
    async def test_a_storage_at_a_path_keeps_its_files_in_that_file(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "knowledge.db"
        assert await _round_trip(SQLiteStorage(path=path)) == "a"
        assert path.is_file()

    async def test_a_path_given_as_text_is_the_same_file(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "knowledge.db"
        assert await _round_trip(SQLiteStorage(path=str(path))) == "a"
        assert path.is_file()

    async def test_a_path_that_holds_a_question_mark_names_that_file_and_no_other(self, tmp_path: pathlib.Path) -> None:
        """Guards: a path formatted into a URL string, which reads ``notes?v2.db`` as ``notes`` and a query."""
        path = tmp_path / "notes?v2.db"
        assert await _round_trip(SQLiteStorage(path=path)) == "a"
        assert sorted(child.name for child in tmp_path.iterdir()) == ["notes?v2.db"]

    async def test_a_storage_at_a_url_keeps_its_files_where_the_url_says(self, tmp_path: pathlib.Path) -> None:
        """A SQLite URL names the database as a path does, with the options its query carries."""
        path = tmp_path / "knowledge.db"
        assert await _round_trip(SQLiteStorage(url=f"sqlite+aiosqlite:///{path}")) == "a"
        assert path.is_file()

    @pytest.mark.parametrize(
        "where",
        [pytest.param({}, id="neither"), pytest.param({"path": "a.db", "url": "sqlite+aiosqlite:///a.db"}, id="both")],
    )
    def test_a_storage_names_where_its_data_lives_once(
        self, where: dict[str, Any], engines_built: list[object]
    ) -> None:
        with pytest.raises(ValueError, match=r"exactly one of path= or url="):
            SQLiteStorage(**where)
        assert engines_built == []

    @pytest.mark.parametrize(
        "where",
        [pytest.param("", id="empty"), pytest.param(pathlib.Path(), id="empty-path-object")],
    )
    def test_an_empty_path_is_refused_and_builds_no_engine(
        self, where: str | pathlib.Path, engines_built: list[object]
    ) -> None:
        """Guards: an unset setting read as ``""``, which SQLite serves as a database in memory that keeps nothing."""
        with pytest.raises(ValueError, match=r"path= must name a file.*InMemoryStorage"):
            SQLiteStorage(path=where)
        assert engines_built == []

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param(POSTGRES_URL, id="postgres"),
            pytest.param(f"postgresql+asyncpg://app:{SECRET}@db/vfs", id="postgres-with-a-password"),
            pytest.param(FLOOR_URL, id="floor"),
        ],
    )
    def test_a_url_of_another_engine_is_refused_naming_both_and_builds_no_engine(
        self, url: str, engines_built: list[object]
    ) -> None:
        with pytest.raises(ValueError, match=r"SQLiteStorage") as refused:
            SQLiteStorage(url=url)
        message = str(refused.value)
        assert ("'sqlite'" in message, repr(url.partition("+")[0]) in message) == (True, True)
        assert (SECRET in message, url in message) == (False, False)
        assert engines_built == []

    async def test_an_in_memory_storage_is_a_sqlite_storage_over_memory(self) -> None:
        storage = InMemoryStorage()
        assert isinstance(storage, SQLiteStorage)
        assert storage.engine.url.database == ":memory:"
        assert await _round_trip(storage) == "a"


# ---------------------------------------------------------------------------
# PostgresStorage
# ---------------------------------------------------------------------------


class TestPostgresStorage:
    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("sqlite+aiosqlite:///a.db", id="sqlite"),
            pytest.param(f"mysql+aiomysql://app:{SECRET}@db/vfs", id="mysql-with-a-password"),
            pytest.param(FLOOR_URL, id="floor"),
        ],
    )
    def test_a_url_of_another_engine_is_refused_naming_both_and_builds_no_engine(
        self, url: str, engines_built: list[object]
    ) -> None:
        with pytest.raises(ValueError, match=r"PostgresStorage") as refused:
            PostgresStorage(url=url)
        message = str(refused.value)
        assert ("'postgresql'" in message, repr(url.partition("+")[0]) in message) == (True, True)
        assert (SECRET in message, url in message) == (False, False)
        assert engines_built == []

    async def test_a_postgres_url_builds_a_storage_on_the_postgres_profile(self) -> None:
        """Construction connects to nothing, so the profile is read here with no server."""
        storage = PostgresStorage(url=POSTGRES_URL, schema="vfs")
        assert (storage._host.profile.name, storage._host.tables.entry.schema) == ("postgresql", "vfs")
        await storage.close()


@pytest.mark.parametrize(
    ("named", "dropped", "added"),
    [
        pytest.param(SQLiteStorage, {"url"}, {"path", "url"}, id="sqlite"),
        pytest.param(PostgresStorage, set(), set(), id="postgres"),
    ],
)
def test_a_named_storage_takes_every_argument_of_database_storage_with_its_default(
    named: type[DatabaseStorage], dropped: set[str], added: set[str]
) -> None:
    """Guards: an argument added to ``DatabaseStorage``, or a default changed there, that a named class misses."""
    shared = {
        name: (parameter.kind, parameter.default, parameter.annotation)
        for name, parameter in inspect.signature(DatabaseStorage.__init__).parameters.items()
        if name not in dropped
    }
    own = inspect.signature(named.__init__).parameters
    assert {name: (p.kind, p.default, p.annotation) for name, p in own.items() if name not in added} == {
        name: value for name, value in shared.items() if name not in added
    }


def test_both_names_are_exported_where_the_storages_are() -> None:
    assert {"SQLiteStorage", "PostgresStorage"} <= set(backends.__all__)
    assert (backends.SQLiteStorage, backends.PostgresStorage) == (SQLiteStorage, PostgresStorage)
