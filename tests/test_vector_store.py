"""Tests for VectorStore protocol, vector_search, semantic_search, and DatabricksVectorStore."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vfs.backends.database import DatabaseFileSystem
from vfs.vector import Vector
from vfs.vector_store import VectorHit, VectorItem, VectorStore

# ---------------------------------------------------------------------------
# Mock VectorStore
# ---------------------------------------------------------------------------

MOCK_DIM = 4


class MockVectorStore:
    """In-memory VectorStore for testing."""

    def __init__(self, hits: list[VectorHit] | None = None) -> None:
        self._hits = hits or []
        self.last_query_vector: list[float] | None = None
        self.last_query_k: int | None = None
        self.last_query_paths: list[str] | None = None
        self.upserted: list[VectorItem] = []
        self.deleted: list[str] = []

    async def query(
        self,
        vector: list[float],
        *,
        k: int = 10,
        paths: list[str] | None = None,
        user_id: str | None = None,
    ) -> list[VectorHit]:
        self.last_query_vector = vector
        self.last_query_k = k
        self.last_query_paths = paths
        hits = self._hits
        if paths is not None:
            allowed = set(paths)
            hits = [h for h in hits if h.path in allowed]
        return hits[:k]

    async def upsert(self, items: list[VectorItem]) -> None:
        self.upserted.extend(items)

    async def delete(self, paths: list[str]) -> None:
        self.deleted.extend(paths)


# ---------------------------------------------------------------------------
# Mock EmbeddingProvider
# ---------------------------------------------------------------------------


class MockEmbeddingProvider:
    """Fake embedding provider that returns a fixed vector."""

    def __init__(self, dim: int = MOCK_DIM) -> None:
        self._dim = dim

    async def embed(self, text: str) -> Vector:
        cls = Vector[self._dim, "mock-model"]
        return cls([0.1 * (i + 1) for i in range(self._dim)])

    async def embed_batch(self, texts: list[str]) -> list[Vector]:
        cls = Vector[self._dim, "mock-model"]
        return [cls([0.1 * (i + 1) for i in range(self._dim)]) for _ in texts]

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return "mock-model"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_mock_store_satisfies_protocol():
    store = MockVectorStore()
    assert isinstance(store, VectorStore)


# ---------------------------------------------------------------------------
# vector_search via DatabaseFileSystem
# ---------------------------------------------------------------------------


async def test_vector_search_returns_scored_candidates(db: DatabaseFileSystem):
    hits = [
        VectorHit(path="/a.py", score=0.95),
        VectorHit(path="/b.py", score=0.80),
    ]
    db._vector_store = MockVectorStore(hits)

    result = await db.vector_search([0.1, 0.2, 0.3, 0.4], k=5)

    assert result.success
    assert len(result.entries) == 2
    assert result.entries[0].path == "/a.py"
    assert result.entries[0].score == pytest.approx(0.95)
    assert result.entries[1].path == "/b.py"
    assert result.entries[1].score == pytest.approx(0.80)
    assert result.function == "vector_search"


async def test_vector_search_with_candidates(db: DatabaseFileSystem):
    hits = [
        VectorHit(path="/a.py", score=0.95),
        VectorHit(path="/b.py", score=0.80),
        VectorHit(path="/c.py", score=0.70),
    ]
    store = MockVectorStore(hits)
    db._vector_store = store

    # Write files so we have candidates to filter with
    await db.write("/a.py", "aaa")
    await db.write("/b.py", "bbb")
    pre = await db.glob("/*.py")

    result = await db.vector_search([0.1, 0.2, 0.3, 0.4], k=5, candidates=pre)

    assert result.success
    # Store should have received the candidate paths
    assert store.last_query_paths is not None
    assert set(store.last_query_paths) == {"/a.py", "/b.py"}


async def test_vector_search_without_store(db: DatabaseFileSystem):
    result = await db.vector_search([0.1, 0.2], k=5)

    assert not result.success
    assert "requires a vector store" in result.errors[0]


async def test_vector_search_empty_results(db: DatabaseFileSystem):
    db._vector_store = MockVectorStore(hits=[])

    result = await db.vector_search([0.1, 0.2], k=5)

    assert result.success
    assert len(result.entries) == 0


# ---------------------------------------------------------------------------
# semantic_search via DatabaseFileSystem
# ---------------------------------------------------------------------------


async def test_semantic_search_end_to_end(db: DatabaseFileSystem):
    hits = [VectorHit(path="/a.py", score=0.9)]
    store = MockVectorStore(hits)
    db._vector_store = store
    db._embedding_provider = MockEmbeddingProvider()

    result = await db.semantic_search("find auth code", k=5)

    assert result.success
    assert len(result.entries) == 1
    assert result.entries[0].path == "/a.py"
    # Verify the embedding was passed to the store
    assert store.last_query_vector is not None
    assert len(store.last_query_vector) == MOCK_DIM


async def test_semantic_search_without_embedding_provider(db: DatabaseFileSystem):
    db._vector_store = MockVectorStore()

    result = await db.semantic_search("test query", k=5)

    assert not result.success
    assert "requires an embedding provider" in result.errors[0]


async def test_semantic_search_without_vector_store(db: DatabaseFileSystem):
    db._embedding_provider = MockEmbeddingProvider()

    result = await db.semantic_search("test query", k=5)

    assert not result.success
    assert "requires a vector store" in result.errors[0]


async def test_semantic_search_empty_query(db: DatabaseFileSystem):
    db._vector_store = MockVectorStore()
    db._embedding_provider = MockEmbeddingProvider()

    result = await db.semantic_search("", k=5)

    assert not result.success
    assert "requires a query" in result.errors[0]


async def test_semantic_search_whitespace_query(db: DatabaseFileSystem):
    db._vector_store = MockVectorStore()
    db._embedding_provider = MockEmbeddingProvider()

    result = await db.semantic_search("   ", k=5)

    assert not result.success
    assert "requires a query" in result.errors[0]


# ---------------------------------------------------------------------------
# DatabricksVectorStore
# ---------------------------------------------------------------------------


class TestDatabricksVectorStore:
    """Unit tests with mocked Databricks SDK."""

    def _make_store(self):
        """Create a DatabricksVectorStore with mocked SDK."""
        with patch("vfs.databricks_store._HAS_DATABRICKS", True):
            from vfs.databricks_store import DatabricksVectorStore

            store = DatabricksVectorStore(
                index_name="catalog.schema.idx",
                endpoint_name="ep",
            )
        return store

    def _connect_store(self, store):
        """Attach a mock index to the store."""
        store._index = MagicMock()
        store._client = MagicMock()
        return store._index

    async def test_query_parses_response(self):
        store = self._make_store()
        mock_idx = self._connect_store(store)

        mock_idx.similarity_search.return_value = {
            "manifest": {
                "columns": [
                    {"name": "id"},
                    {"name": "score"},
                ],
            },
            "result": {
                "data_array": [
                    ["/a.py", 0.95],
                    ["/b.py", 0.80],
                ],
            },
        }

        hits = await store.query([0.1, 0.2], k=5)

        assert len(hits) == 2
        assert hits[0].path == "/a.py"
        assert hits[0].score == pytest.approx(0.95)
        assert hits[1].path == "/b.py"
        assert hits[1].score == pytest.approx(0.80)

    async def test_query_with_paths_filter(self):
        store = self._make_store()
        mock_idx = self._connect_store(store)

        mock_idx.similarity_search.return_value = {
            "manifest": {"columns": [{"name": "id"}, {"name": "score"}]},
            "result": {"data_array": [["/a.py", 0.9], ["/b.py", 0.8], ["/c.py", 0.7]]},
        }

        hits = await store.query([0.1], k=10, paths=["/a.py", "/c.py"])

        assert len(hits) == 2
        assert {h.path for h in hits} == {"/a.py", "/c.py"}

    async def test_upsert_batches(self):
        store = self._make_store()
        mock_idx = self._connect_store(store)

        items = [VectorItem(path=f"/f{i}.txt", vector=[0.1]) for i in range(2500)]
        await store.upsert(items)

        assert mock_idx.upsert.call_count == 3  # 1000 + 1000 + 500

    async def test_delete(self):
        store = self._make_store()
        mock_idx = self._connect_store(store)

        await store.delete(["/a.py", "/b.py"])

        mock_idx.delete.assert_called_once_with(primary_keys=["/a.py", "/b.py"])

    async def test_not_connected_raises(self):
        store = self._make_store()

        with pytest.raises(RuntimeError, match="Not connected"):
            await store.query([0.1], k=5)

    async def test_connect(self):
        store = self._make_store()

        mock_client_cls = MagicMock()
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_index.return_value = MagicMock()

        with patch("vfs.databricks_store.VectorSearchClient", mock_client_cls):
            await store.connect()

        assert store._client is mock_client
        assert store._index is not None

    async def test_close(self):
        store = self._make_store()
        store._client = MagicMock()
        store._index = MagicMock()

        await store.close()

        assert store._client is None
        assert store._index is None
