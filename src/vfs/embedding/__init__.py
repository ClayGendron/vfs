"""Embedding providers: the seam ``reindex`` fills ``chunks.embedding`` through.

``provider`` holds the protocol and the CPU-provider base; ``hashing``
the deterministic zero-dependency floor; ``model2vec``, ``openai`` and
``langchain`` the adapters, each importing its library lazily or not at
all so the core stays dependency-free.
"""

from vfs.embedding.hashing import HASH_DIMENSION, HashEmbeddingProvider, hash_embedding
from vfs.embedding.langchain import LangChainEmbeddingProvider
from vfs.embedding.model2vec import Model2VecEmbeddingProvider
from vfs.embedding.openai import OpenAIEmbeddingProvider
from vfs.embedding.provider import (
    Embedded,
    EmbeddingProvider,
    LocalEmbeddingProvider,
    estimate_tokens,
    qualified_model_id,
)

__all__ = [
    "HASH_DIMENSION",
    "Embedded",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "LangChainEmbeddingProvider",
    "LocalEmbeddingProvider",
    "Model2VecEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "estimate_tokens",
    "hash_embedding",
    "qualified_model_id",
]
