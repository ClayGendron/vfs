"""Provider doubles for the embedding seam and the reindex embed step.

``ScriptedProvider`` is a protocol-complete fake whose behaviour a test
dials: caps, a per-request delay, a failure after N requests, an
exception shaped like an HTTP refusal. The OpenAI, LangChain and
model2vec doubles mimic exactly the surface each adapter calls.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from vfs.embedding import Embedded, estimate_tokens, hash_embedding

if TYPE_CHECKING:
    from collections.abc import Sequence


class ScriptedProvider:
    """A deterministic provider (the hash vectors) with dials on every failure mode."""

    def __init__(
        self,
        dimension: int = 4,
        *,
        model: str = "fake",
        max_batch_inputs: int = 8,
        max_batch_tokens: int | None = None,
        max_input_tokens: int | None = None,
        fail_after: int | None = None,
        error: Exception | None = None,
        failures: list[Exception] | None = None,
        delay: float = 0.0,
    ) -> None:
        self.dimension = dimension
        self.model_id = f"scripted/{model}@{dimension}"
        self.max_batch_inputs = max_batch_inputs
        self.max_batch_tokens = max_batch_tokens
        self.max_input_tokens = max_input_tokens
        self.fail_after = fail_after
        self.error = error
        self.failures = list(failures or [])
        self.delay = delay
        self.batches: list[list[str]] = []

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def vector(self, text: str) -> list[float]:
        return hash_embedding(text, self.dimension)

    async def embed_query(self, text: str) -> list[float]:
        return self.vector(text)

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failures:
            raise self.failures.pop(0)
        if self.fail_after is not None and len(self.batches) >= self.fail_after:
            raise self.error or RuntimeError("provider down")
        self.batches.append(list(texts))
        return Embedded([self.vector(text) for text in texts], sum(self.estimate_tokens(text) for text in texts))


class RateLimitedError(Exception):
    """An HTTP-shaped refusal carrying ``Retry-After`` headers, as the OpenAI client raises."""

    def __init__(self, headers: dict[str, str]) -> None:
        super().__init__("rate limited")
        self.response = SimpleNamespace(headers=headers)


class FakeOpenAIClient:
    """``client.embeddings.create(**request)`` answering hash vectors in shuffled index order."""

    def __init__(self, dimension: int = 8, *, usage: bool = True) -> None:
        self.dimension = dimension
        self.usage = usage
        self.requests: list[dict[str, Any]] = []
        self.embeddings = SimpleNamespace(create=self._create)

    async def _create(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        width = request.get("dimensions", self.dimension)
        data = [
            SimpleNamespace(index=index, embedding=hash_embedding(text, width))
            for index, text in enumerate(request["input"])
        ]
        data.reverse()  # the API may answer out of order; the adapter must sort by index
        usage = SimpleNamespace(total_tokens=sum(len(text) for text in request["input"])) if self.usage else None
        return SimpleNamespace(data=data, usage=usage)


class FakeLangChainEmbeddings:
    """The LangChain ``Embeddings`` surface the adapter calls, sync and async."""

    def __init__(self, dimension: int = 6) -> None:
        self.dimension = dimension
        self.probes: list[str] = []
        self.calls: list[list[str]] = []

    def embed_query(self, text: str) -> list[float]:
        self.probes.append(text)
        return hash_embedding(text, self.dimension)

    async def aembed_query(self, text: str) -> list[float]:
        return hash_embedding(text, self.dimension)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [hash_embedding(text, self.dimension) for text in texts]


class FakeStaticModel:
    """model2vec's ``StaticModel`` surface: ``dim`` and ``encode``."""

    def __init__(self, dim: int = 5) -> None:
        self.dim = dim
        self.encoded: list[list[str]] = []

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.encoded.append(list(texts))
        return [hash_embedding(text, self.dim) for text in texts]
