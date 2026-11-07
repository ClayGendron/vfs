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
    from collections.abc import Callable, Sequence


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
        token_of: Callable[[str], int] | None = None,
        real_batch_tokens: int | None = None,
        real_input_tokens: int | None = None,
        refuse_all: bool = False,
        refuse_all_after: int | None = None,
        status_error: Exception | None = None,
        refusal_error: Callable[[], Exception] | None = None,
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
        self.token_of = token_of
        self.real_batch_tokens = real_batch_tokens
        self.real_input_tokens = real_input_tokens
        self.refuse_all = refuse_all
        self.refuse_all_after = refuse_all_after
        self.status_error = status_error
        self.refusal_error = refusal_error
        self.batches: list[list[str]] = []
        self.calls: list[list[str]] = []
        """Every request, answered or refused, the canary included."""

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def vector(self, text: str) -> list[float]:
        return hash_embedding(text, self.dimension)

    async def embed_query(self, text: str) -> list[float]:
        return self.vector(text)

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls.append(list(texts))
        if self.status_error is not None:
            raise self.status_error
        if self.refuse_all or (self.refuse_all_after is not None and len(self.calls) > self.refuse_all_after):
            raise InputRefusedError(400)
        real = self.token_of or self.estimate_tokens
        refusal = self.refusal_error or (lambda: InputRefusedError(400))
        if self.real_input_tokens is not None and any(real(text) > self.real_input_tokens for text in texts):
            raise refusal()
        if self.real_batch_tokens is not None and sum(real(text) for text in texts) > self.real_batch_tokens:
            raise refusal()
        if self.failures:
            raise self.failures.pop(0)
        if self.fail_after is not None and len(self.batches) >= self.fail_after:
            raise self.error or RuntimeError("provider down")
        self.batches.append(list(texts))
        return Embedded([self.vector(text) for text in texts], sum(self.estimate_tokens(text) for text in texts))


class InputRefusedError(Exception):
    """An HTTP-shaped refusal with a status and no ``Retry-After``, as the OpenAI client's ``BadRequestError``."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"Error code: {status_code}")
        self.status_code = status_code
        self.response = SimpleNamespace(status_code=status_code, headers={})


class ResponseStatusError(Exception):
    """An HTTP refusal whose status rides only on its response, as ``httpx.HTTPStatusError`` carries it."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.response = SimpleNamespace(status_code=status_code, headers=headers or {})


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
