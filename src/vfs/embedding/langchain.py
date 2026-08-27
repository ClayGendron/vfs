"""A LangChain ``Embeddings`` object behind the seam.

LangChain's base class carries neither a model identity nor a
dimension, so the adapter is *told* its identity and probes the width
once by embedding a sentinel when it is not given. It speaks the async
pair (``aembed_documents`` / ``aembed_query``) and imports nothing from
LangChain at runtime — any object with that surface serves.

    provider = LangChainEmbeddingProvider(embeddings, model_id="voyage/voyage-3", dimension=1024)
    provider = LangChainEmbeddingProvider(embeddings, model_id="ollama/nomic-embed-text")  # width probed
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from vfs.embedding.provider import Embedded, estimate_tokens

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_BATCH_INPUTS: Final = 1_000
"""LangChain's own OpenAI chunk size — the widest batch its adapters expect."""

DIMENSION_PROBE: Final = "dimension probe"
"""The sentinel embedded once, at construction, when no width is given."""

_PROVIDER_PREFIX: Final = "langchain"


class LangChainEmbeddingProvider:
    """``Embeddings`` → the seam; identity supplied, width supplied or probed."""

    max_input_tokens: int | None = None
    max_batch_inputs: int = DEFAULT_BATCH_INPUTS
    max_batch_tokens: int | None = None

    def __init__(self, embeddings: Any, *, model_id: str, dimension: int | None = None) -> None:
        if not model_id:
            msg = "model_id must name the LangChain embedder's model"
            raise ValueError(msg)
        self._embeddings = embeddings
        if dimension is None:
            dimension = len(embeddings.embed_query(DIMENSION_PROBE))
        if dimension < 1:
            msg = f"dimension must be positive, got {dimension}"
            raise ValueError(msg)
        self.dimension = dimension
        if "/" not in model_id:
            model_id = f"{_PROVIDER_PREFIX}/{model_id}"
        self.model_id = model_id if "@" in model_id else f"{model_id}@{dimension}"

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    async def embed_query(self, text: str) -> list[float]:
        return self._checked([await self._embeddings.aembed_query(text)])[0]

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        vectors = self._checked(await self._embeddings.aembed_documents(list(texts)))
        if len(vectors) != len(texts):
            msg = f"{self.model_id} answered {len(vectors)} vectors for {len(texts)} inputs"
            raise RuntimeError(msg)
        return Embedded(vectors, sum(self.estimate_tokens(text) for text in texts))

    def _checked(self, rows: Sequence[Sequence[float]]) -> list[list[float]]:
        vectors = [[float(value) for value in row] for row in rows]
        if any(len(vector) != self.dimension for vector in vectors):
            msg = f"{self.model_id} answered a vector of the wrong width (expected {self.dimension})"
            raise RuntimeError(msg)
        return vectors
