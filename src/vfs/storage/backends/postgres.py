"""``PostgresStorage`` — the database backend on Postgres, by name.

Postgres is the engine for a shared deployment. vfs is tested on every
major version the PostgreSQL project supports, with pgvector 0.8
installed by a role that may create extensions. vfs proves the
extension at first touch and never creates it.

    PostgresStorage(url="postgresql+asyncpg://app@db/vfs", schema="vfs")

The class only constructs. Every verb and every difference between the
engines comes from ``DatabaseStorage`` and the Postgres profile it reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vfs.deadline import WALL_TIME_BUDGET
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.drivers import url_of_engine
from vfs.storage.backends.database.embed import EMBED_CONCURRENCY, EMBED_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from sqlalchemy.engine import URL

    from vfs.embedding import EmbeddingProvider
    from vfs.models.vector import NativeEmbeddingConfig
    from vfs.rendering.registry import RendererRegistry
    from vfs.rendering.seam import RenderLimits
    from vfs.storage.grants import Posture
    from vfs.storage.ranking import Ranker


class PostgresStorage(DatabaseStorage):
    """A ``DatabaseStorage`` on Postgres, the engine for a shared deployment.

    ``url`` names the server and the driver, as in
    ``postgresql+asyncpg://app@db/vfs``. ``schema`` is the Postgres
    schema the storage's tables live in, so several storages can share
    one database. Every other argument is the one ``DatabaseStorage``
    takes.

    A ``url`` of another dialect raises a ``ValueError`` before any
    engine is built, and the error names both dialects.
    """

    def __init__(
        self,
        *,
        url: str | URL,
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
        super().__init__(
            url=url_of_engine(url, engine="postgresql", storage=type(self).__name__),
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
