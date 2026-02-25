"""Tests for SearchEngine composition and supported_protocols()."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from grover.mount.protocols import (
    SupportsEmbedding,
    SupportsGlob,
    SupportsHybridSearch,
    SupportsLexicalSearch,
    SupportsVectorSearch,
)
from grover.search._engine import SearchEngine

# ------------------------------------------------------------------
# Fake providers and stores
# ------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic embedding provider."""

    @property
    def dimensions(self) -> int:
        return 8

    @property
    def model_name(self) -> str:
        return "fake-model"

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()[:8]
        raw = [float(b) for b in h]
        norm = math.sqrt(sum(x * x for x in raw))
        return [x / norm for x in raw]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FakeVectorStore:
    """Minimal VectorStore implementation."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def upsert(self, entries: list[Any]) -> None:
        for e in entries:
            self._data[e.id] = e

    async def search(self, vector: list[float], k: int = 10) -> list[Any]:
        return []

    async def delete(self, ids: list[str]) -> None:
        for id_ in ids:
            self._data.pop(id_, None)

    async def fetch(self, ids: list[str]) -> list[Any]:
        return []

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    @property
    def index_name(self) -> str:
        return "fake-index"


class FakeLexicalStore:
    """Minimal FullTextStore mock."""

    async def index(self, path: str, content: str, **kw: Any) -> None: ...

    async def remove(self, path: str, **kw: Any) -> None: ...

    async def search(self, query: str, **kw: Any) -> list[Any]:
        return []


class FakeHybridProvider:
    """Component claiming hybrid search capability."""

    async def hybrid_search(self, query: str, **kw: Any) -> list[Any]:
        return []


# ==================================================================
# Constructor
# ==================================================================


class TestConstructor:
    def test_keyword_args(self):
        store = FakeVectorStore()
        provider = FakeEmbeddingProvider()
        se = SearchEngine(vector=store, embedding=provider)
        assert se.vector is store
        assert se.embedding is provider

    def test_no_args(self):
        se = SearchEngine()
        assert se.vector is None
        assert se.embedding is None


# ==================================================================
# supported_protocols()
# ==================================================================


class TestSupportedProtocols:
    def test_empty_engine(self):
        se = SearchEngine()
        assert se.supported_protocols() == set()

    def test_vector_and_embedding(self):
        se = SearchEngine(vector=FakeVectorStore(), embedding=FakeEmbeddingProvider())
        protos = se.supported_protocols()
        assert SupportsVectorSearch in protos
        assert SupportsEmbedding in protos
        assert SupportsLexicalSearch not in protos

    def test_vector_only_no_embedding(self):
        """Vector without embedding should NOT satisfy SupportsVectorSearch."""
        se = SearchEngine(vector=FakeVectorStore())
        protos = se.supported_protocols()
        assert SupportsVectorSearch not in protos

    def test_embedding_only(self):
        se = SearchEngine(embedding=FakeEmbeddingProvider())
        protos = se.supported_protocols()
        assert SupportsEmbedding in protos
        assert SupportsVectorSearch not in protos

    def test_lexical_only(self):
        se = SearchEngine(lexical=FakeLexicalStore())
        protos = se.supported_protocols()
        assert SupportsLexicalSearch in protos
        assert SupportsVectorSearch not in protos

    def test_hybrid(self):
        se = SearchEngine(hybrid=FakeHybridProvider())
        protos = se.supported_protocols()
        assert SupportsHybridSearch in protos

    def test_all_components(self):
        se = SearchEngine(
            vector=FakeVectorStore(),
            embedding=FakeEmbeddingProvider(),
            lexical=FakeLexicalStore(),
            hybrid=FakeHybridProvider(),
        )
        protos = se.supported_protocols()
        assert SupportsVectorSearch in protos
        assert SupportsEmbedding in protos
        assert SupportsLexicalSearch in protos
        assert SupportsHybridSearch in protos

    def test_no_filesystem_protocols(self):
        """SearchEngine should never return SupportsGlob etc."""
        se = SearchEngine(
            vector=FakeVectorStore(),
            embedding=FakeEmbeddingProvider(),
            lexical=FakeLexicalStore(),
            hybrid=FakeHybridProvider(),
        )
        protos = se.supported_protocols()
        assert SupportsGlob not in protos


# ==================================================================
# Property accessors
# ==================================================================


class TestPropertyAccessors:
    def test_vector_property(self):
        store = FakeVectorStore()
        se = SearchEngine(vector=store)
        assert se.vector is store

    def test_embedding_property(self):
        provider = FakeEmbeddingProvider()
        se = SearchEngine(embedding=provider)
        assert se.embedding is provider

    def test_lexical_property(self):
        lex = FakeLexicalStore()
        se = SearchEngine(lexical=lex)
        assert se.lexical is lex
