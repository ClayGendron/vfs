"""``SQLiteStorage`` — the database backend on SQLite, by name.

SQLite is the engine for a demo or a local application. A storage keeps
its data in one database file, named by its path.

    SQLiteStorage(path="knowledge.db")

A SQLite URL that carries options in its query is served on the same
tuned profile by ``DatabaseStorage(url=...)``. The class only
constructs. Every verb and every difference between the engines comes
from ``DatabaseStorage`` and the SQLite profile it reads.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy.engine import URL

from vfs.deadline import WALL_TIME_BUDGET
from vfs.storage.backends.database import DatabaseStorage
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

    ``path`` is the file the database lives in. It is read as a file
    name whatever it holds, so ``notes?v2.db`` is that file. The one
    exception is ``:memory:``, a private database in memory, which
    ``InMemoryStorage`` names. Every other argument is the one
    ``DatabaseStorage`` takes.

    An empty ``path`` raises a ``ValueError``, because SQLite would serve
    it as a database in memory that keeps nothing.

    A file system whose root is this storage keeps its own records, the
    rows the kernel keeps about calls, in the same file, in tables of
    their own whose names begin ``vfs_kernel_``, ``vfs_session`` or
    ``vfs_job``. No other file is made, and a copy of the file carries
    them. SQLite has one writer for a file, and the kernel's records share
    it with this storage's writes: while a large batch is being written,
    a record waits for the batch to end. A record written after a change
    that waits longer than its four tries, about 20 seconds, is not
    written; the change stands, and the kernel is handed a warning that
    says so. Postgres has no such wait.
    """

    def __init__(
        self,
        *,
        path: str | os.PathLike[str],
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
        database = os.fspath(path)
        if database in _NO_FILE:
            raise ValueError(
                f"{type(self).__name__} path= must name a file, and {database!r} names none; "
                "InMemoryStorage keeps a database in memory"
            )
        super().__init__(
            # Never formatted into a URL string, which would read a '?' in the path as the start of a query.
            url=URL.create(SQLITE_DRIVER, database=database),
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
