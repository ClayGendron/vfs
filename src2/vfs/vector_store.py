"""VectorStore protocol — async interface for vector similarity search.

``VectorStore`` abstracts the storage and retrieval of embedding vectors.
Implementations may use in-memory indexes (usearch), cloud services
(Databricks, Pinecone), or database extensions (pgvector).

The filesystem layer calls ``query()`` during ``vector_search`` and
``semantic_search``.  ``upsert()`` and ``delete()`` maintain the index
as files are written or removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class VectorItem:
    """A path + vector pair for upsert into the store."""

    path: str
    vector: list[float]
    owner_id: str | None = None


@dataclass(frozen=True)
class VectorHit:
    """A single similarity search result from the store."""

    path: str
    score: float


@runtime_checkable
class VectorStore(Protocol):
    """Async protocol for vector similarity search backends."""

    async def query(
        self,
        vector: list[float],
        *,
        k: int = 10,
        paths: list[str] | None = None,
        user_id: str | None = None,
    ) -> list[VectorHit]:
        """Find the *k* nearest vectors.

        If *paths* is provided, results are constrained to those paths.
        If *user_id* is provided, results are constrained to that user.
        Returns hits sorted by descending score.
        """
        ...

    async def upsert(self, items: list[VectorItem]) -> None:
        """Insert or update vectors in the store."""
        ...

    async def delete(self, paths: list[str]) -> None:
        """Remove vectors by path."""
        ...
