"""The engine core: what any database needs, built with no connection, and the host built on it.

The core is the part of the engine host that knows nothing of a mount:
the engine, the dialect profile, the sessions and the attempts they run
in, the retry, the classifier, the file settings and the dispose. The
host's own lifecycle is pinned in ``test_engine.py``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import Pool

from vfs.storage.backends.database import core as core_module
from vfs.storage.backends.database.core import BUSY_TIMEOUT_CAP, EngineCore
from vfs.storage.backends.database.dialects import SQLITE, SQLITE_VEC_PROBE
from vfs.storage.backends.database.engine import EngineHost

if TYPE_CHECKING:
    import pathlib

# The members any database needs, as the core declares them.
CORE_MEMBERS = (
    "engine",
    "session_factory",
    "profile",
    "parameter_budget",
    "membership_budget",
    "with_retry",
    "classify_failure",
    "apply_file_settings",
    "close",
)


def _file_url(tmp_path: pathlib.Path) -> str:
    """A SQLite URL for a file under *tmp_path* that does not exist yet."""
    return f"sqlite+aiosqlite:///{tmp_path}/core.db"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    async def test_a_core_opens_no_connection_when_it_is_built(self, tmp_path: pathlib.Path) -> None:
        """Guards a core that connects while it is built: SQLite would make the file then."""
        opened: list[object] = []

        def connected(*connection: object) -> None:
            opened.append(connection)

        event.listen(Pool, "connect", connected)
        try:
            core = EngineCore(url=_file_url(tmp_path))
        finally:
            event.remove(Pool, "connect", connected)
        assert (len(opened), sorted(tmp_path.iterdir())) == (0, [])
        await core.close()
        assert sorted(tmp_path.iterdir()) == []

    async def test_a_core_without_the_vector_function_loads_no_extension(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards a checkout that probes for, or loads, the vector extension on a core built without it."""
        probes: list[object] = []
        real = core_module.has_sqlite_vec

        def probed(cursor: Any) -> bool:
            probes.append(cursor)
            return real(cursor)

        monkeypatch.setattr(core_module, "has_sqlite_vec", probed)
        plain = EngineCore(url=_file_url(tmp_path), vector=False)
        async with plain.engine.connect() as conn:
            with pytest.raises(OperationalError, match="vec_version"):
                await conn.execute(text(SQLITE_VEC_PROBE))
        await plain.close()
        assert len(probes) == 0
        vector = EngineCore(url=_file_url(tmp_path))
        async with vector.engine.connect() as conn:
            assert str((await conn.execute(text(SQLITE_VEC_PROBE))).scalar_one()).startswith("v")
        await vector.close()
        assert len(probes) == 1


# ---------------------------------------------------------------------------
# File settings
# ---------------------------------------------------------------------------


class TestFileSettings:
    async def test_the_file_settings_are_the_profiles_and_none_when_it_declares_none(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards a core that sends settings its profile does not declare, or opens a connection to send none."""
        sent: list[str] = []

        def recorded(_conn: object, _cursor: object, statement: str, *_rest: object) -> None:
            sent.append(statement)

        settled = EngineCore(url=_file_url(tmp_path))
        event.listen(settled.engine.sync_engine, "before_cursor_execute", recorded)
        await settled.apply_file_settings()
        await settled.close()
        assert sent == list(SQLITE.file_settings)
        sent.clear()
        monkeypatch.setattr(core_module, "profile_for", lambda _name: replace(SQLITE, file_settings=()))
        bare = EngineCore(url=f"sqlite+aiosqlite:///{tmp_path}/bare.db")
        event.listen(bare.engine.sync_engine, "before_cursor_execute", recorded)
        await bare.apply_file_settings()
        await bare.close()
        assert (sent, (tmp_path / "bare.db").exists()) == ([], False)


# ---------------------------------------------------------------------------
# Transaction control
# ---------------------------------------------------------------------------


class TestTransactionControl:
    @pytest.mark.parametrize(("own", "lowest", "carried"), [(5_000, 1_500, 1_500), (0, 1_500, 0)])
    async def test_a_begin_lowers_the_busy_timeout_to_its_option_and_never_raises_it(
        self, tmp_path: pathlib.Path, own: int, lowest: int, carried: int
    ) -> None:
        """Guards a SQLite ``BEGIN`` sent before the wait its option bounds is set, or one that raises the wait."""
        core = EngineCore(url=_file_url(tmp_path), vector=False)
        bind = core.engine.sync_engine
        waits: list[tuple[str, int]] = []

        @event.listens_for(bind, "checkout")
        def own_wait(dbapi_connection: Any, *_rest: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute(f"PRAGMA busy_timeout = {own}")
            cursor.close()

        @event.listens_for(bind, "before_cursor_execute")
        def read_the_wait(conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
            cursor = conn.connection.dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout")
            waits.append((statement, cursor.fetchone()[0]))
            cursor.close()

        async with core.session_factory() as session:
            await session.connection(execution_options={"vfs_writer": True, BUSY_TIMEOUT_CAP: lowest})
            await session.commit()
        await core.close()
        assert waits == [("BEGIN IMMEDIATE", carried)]


# ---------------------------------------------------------------------------
# The host is a core
# ---------------------------------------------------------------------------


class TestTheHost:
    async def test_the_engine_host_is_an_engine_core(self, tmp_path: pathlib.Path) -> None:
        """Guards a second copy of the engine set-up in the host: each member the host does not extend is the core's."""
        host = EngineHost(url=_file_url(tmp_path))
        assert isinstance(host, EngineCore)
        assert [name for name in CORE_MEMBERS if not hasattr(host, name)] == []
        shared = [name for name in CORE_MEMBERS if name not in {"engine", "session_factory", "close"}]
        assert [name for name in shared if getattr(EngineHost, name) is not getattr(EngineCore, name)] == []
        await host.close()
