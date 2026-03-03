"""Vector search layer — stores, text extraction, embedding providers."""

from grover.fs.providers.protocols import EmbeddingProvider
from grover.search.extractors import (
    EmbeddableChunk,
    extract_from_chunks,
    extract_from_file,
)
from grover.search.protocols import VectorStore
from grover.search.stores.local import LocalVectorStore
from grover.search.types import SearchResult

__all__ = [
    "EmbeddableChunk",
    "EmbeddingProvider",
    "LocalVectorStore",
    "SearchResult",
    "VectorStore",
    "extract_from_chunks",
    "extract_from_file",
]
