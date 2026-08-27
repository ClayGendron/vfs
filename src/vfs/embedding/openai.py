"""OpenAI embeddings behind the seam — an ``AsyncOpenAI`` client, one model.

The adapter speaks to whatever ``client.embeddings.create`` it is
handed, so it imports nothing from ``openai`` at runtime and a fake
transport tests it offline. Caps are the documented ones — 2,048 inputs
and 300,000 tokens per request, 8,192 tokens per input — and the
response's ``usage.total_tokens`` is reported exactly. Retries within
one request, with ``Retry-After`` honoured, are the client's own.

    from openai import AsyncOpenAI

    provider = OpenAIEmbeddingProvider(AsyncOpenAI(), "text-embedding-3-small")
    provider = OpenAIEmbeddingProvider(AsyncOpenAI(), "text-embedding-3-large", dimensions=1024)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from vfs.embedding.provider import Embedded, estimate_tokens, qualified_model_id

if TYPE_CHECKING:
    from collections.abc import Sequence

OPENAI_DIMENSIONS: Final[dict[str, int]] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
"""Each model's native width; the ``text-embedding-3`` family also accepts a smaller ``dimensions``."""

MAX_INPUT_TOKENS: Final = 8_192
MAX_BATCH_INPUTS: Final = 2_048
MAX_BATCH_TOKENS: Final = 300_000

_MATRYOSHKA_PREFIX: Final = "text-embedding-3"


class OpenAIEmbeddingProvider:
    """``/v1/embeddings`` through an async client; no query/document asymmetry."""

    max_input_tokens: int | None = MAX_INPUT_TOKENS
    max_batch_inputs: int = MAX_BATCH_INPUTS
    max_batch_tokens: int | None = MAX_BATCH_TOKENS

    def __init__(self, client: Any, model: str = "text-embedding-3-small", dimensions: int | None = None) -> None:
        native = OPENAI_DIMENSIONS.get(model)
        if dimensions is None and native is None:
            msg = f"unknown OpenAI embedding model {model!r}: pass dimensions= explicitly"
            raise ValueError(msg)
        if dimensions is not None and native is not None and not model.startswith(_MATRYOSHKA_PREFIX):
            msg = f"{model!r} has a fixed width; only the {_MATRYOSHKA_PREFIX} family takes dimensions="
            raise ValueError(msg)
        if dimensions is not None and dimensions < 1:
            msg = f"dimensions must be positive, got {dimensions}"
            raise ValueError(msg)
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self.dimension = dimensions if dimensions is not None else native or 0
        self.model_id = qualified_model_id("openai", model, self.dimension)

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text])).vectors[0]

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        request: dict[str, Any] = {"input": list(texts), "model": self._model, "encoding_format": "float"}
        if self._dimensions is not None:
            request["dimensions"] = self._dimensions
        response = await self._client.embeddings.create(**request)
        items = sorted(response.data, key=lambda item: item.index)
        vectors = [[float(value) for value in item.embedding] for item in items]
        if len(vectors) != len(texts) or any(len(vector) != self.dimension for vector in vectors):
            msg = f"{self.model_id} answered {len(vectors)} vectors for {len(texts)} inputs, or a wrong width"
            raise RuntimeError(msg)
        usage = getattr(response, "usage", None)
        tokens = getattr(usage, "total_tokens", None)
        if not isinstance(tokens, int):
            tokens = sum(self.estimate_tokens(text) for text in texts)
        return Embedded(vectors, tokens)
