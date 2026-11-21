"""``SQLiteStorage`` — the database backend on SQLite, by name.

SQLite is the engine for a demo or a local application. A storage keeps
its data in one database, named by a path on disk or by a URL. A URL
carries what a path cannot: the options in its query.

    SQLiteStorage(path="knowledge.db")
    SQLiteStorage(url="sqlite+aiosqlite:///knowledge.db")

The class only constructs. Every verb and every difference between the
engines comes from ``DatabaseStorage`` and the SQLite profile it reads.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy.engine import URL

from vfs.deadline import WALL_TIME_BUDGET
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.drivers import url_of_engine
from vfs.storage.backends.database.embed import EMBED_CONCURRENCY, EMBED_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from vfs.embedding import EmbeddingProvider
    from vfs.models.vector import NativeEmbeddingConfig
    from vfs.rendering.registry import RendererRegistry
    from vfs.rendering.seam import RenderLimits
    from vfs.storage.grants import Posture
    from vfs.storage.ranking import Ranker

SQLITE_DRIVER = "sqlite+aiosqlite"
"""The dialect and driver a path is opened with."""

# An empty path, as text or as ``pathlib.Path("")``, which SQLite would serve as a database in memory.
_NO_FILE = frozenset({"", "."})


class SQLiteStorage(DatabaseStorage):
    """A ``DatabaseStorage`` on SQLite, the engine for a demo or a local application.

    Pass ``path`` or ``url``, exactly one, to say where the data lives.
    ``path`` is a file on disk, and is read as a file name whatever it
    holds, so ``notes?v2.db`` is that file. The one exception is
    ``:memory:``, a private database in memory, which ``InMemoryStorage``
    names. ``url`` reaches a SQLite database through the aiosqlite
    driver, with the options its query carries. Every other argument is
    the one ``DatabaseStorage`` takes.

    Neither ``path`` nor ``url``, or both, raises a ``ValueError``. So
    does an empty ``path``, which SQLite would serve as a database in
    memory that keeps nothing. So does a ``url`` of another dialect,
    before any engine is built, and the error names both dialects.
    """

    def __init__(
        self,
        *,
        path: str | os.PathLike[str] | None = None,
        url: str | URL | None = None,
        engine_arguments: Mapping[str, Any] | None = None,
        schema: str | None = None,
        name: str = "database",
        description: str | None = None,
        trash_days: int = 90,
        grep_wall_seconds: float = WALL_TIME_BUDGET,
        search_wall_seconds: float = WALL_TIME_BUDGET,
        glob_wall_seconds: float = WALL_TIME_BUDGET,
        embedder: EmbeddingProvider | None = None,
        native_embedding: NativeEmbeddingConfig | None = None,
        embed_concurrency: int = EMBED_CONCURRENCY,
        embed_timeout_seconds: float = EMBED_TIMEOUT_SECONDS,
        ranker: Ranker | None = None,
        renderers: RendererRegistry | None = None,
        render_limits: RenderLimits | None = None,
        posture: Posture = "read_write",
    ) -> None:
        if (path is None) == (url is None):
            raise ValueError(f"{type(self).__name__} takes exactly one of path= or url=, to say where its data lives")
        if path is not None:
            database = os.fspath(path)
            if database in _NO_FILE:
                raise ValueError(
                    f"{type(self).__name__} path= must name a file, and {database!r} names none; "
                    "InMemoryStorage keeps a database in memory"
                )
            # Never formatted into a URL string, which would read a '?' in the path as the start of a query.
            address = URL.create(SQLITE_DRIVER, database=database)
        else:
            assert url is not None
            address = url_of_engine(url, engine="sqlite", storage=type(self).__name__)
        super().__init__(
            url=address,
            engine_arguments=engine_arguments,
            schema=schema,
            name=name,
            description=description,
            trash_days=trash_days,
            grep_wall_seconds=grep_wall_seconds,
            search_wall_seconds=search_wall_seconds,
            glob_wall_seconds=glob_wall_seconds,
            embedder=embedder,
            native_embedding=native_embedding,
            embed_concurrency=embed_concurrency,
            embed_timeout_seconds=embed_timeout_seconds,
            ranker=ranker,
            renderers=renderers,
            render_limits=render_limits,
            posture=posture,
        )
