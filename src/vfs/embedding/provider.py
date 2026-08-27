"""The embedding provider seam — the protocol every adapter satisfies.

A provider names its vector space (``model_id``, ``dimension``), declares
the caps one request must stay inside, and embeds **one batch** within
them. It never batches across requests, never caches, never counts
cost: storage owns budgets, the chunk-row cache and the streaming loop
that feeds a provider during ``reindex``. Vectors cross the seam as
plain ``list[list[float]]``.

    class MyProvider:
        model_id = "acme/embedder-v2@768"
        dimension = 768
        max_input_tokens = 8192
        max_batch_inputs = 256
        max_batch_tokens = None

        def estimate_tokens(self, text: str) -> int: ...
        async def embed_query(self, text: str) -> list[float]: ...
        async def embed_documents(self, texts: Sequence[str]) -> Embedded: ...

The query and document doors are separate on purpose: a whole model
family (E5, BGE, Voyage, Cohere) prefixes queries and passages
differently, and the provider — not the caller — owns that prefix.
``model_id`` is provider- and dimension-qualified
(``openai/text-embedding-3-small@1536``) because Matryoshka truncation
makes one model name several incompatible spaces.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

CHARS_PER_TOKEN: Final = 4
"""The default estimator's divisor — the planning figure every hosted API quotes."""

LOCAL_BATCH_INPUTS: Final = 2_048
"""Inputs per hop for a CPU provider — bounds one worker call's payload, never eligibility."""


class Embedded(NamedTuple):
    """One batch's vectors, input-aligned, and the tokens it cost.

    ``tokens`` is provider-reported where the API says (OpenAI's
    ``usage.total_tokens``) and estimated otherwise.
    """

    vectors: list[list[float]]
    tokens: int


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A vector space and the means to put text into it, one batch at a time."""

    model_id: str
    """Provider- and dimension-qualified identity, e.g. ``openai/text-embedding-3-small@1536``."""

    dimension: int
    """Vector width — required: vfs owns fixed-width columns."""

    max_input_tokens: int | None
    """Per-input cap, or ``None`` when the provider takes any length."""

    max_batch_inputs: int
    """Inputs one ``embed_documents`` call may carry."""

    max_batch_tokens: int | None
    """Tokens summed over one call's inputs, or ``None`` when uncapped."""

    def estimate_tokens(self, text: str) -> int:
        """The provider's own token estimate for *text* — the batcher's meter."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed one query, with the model's query prefix applied."""
        ...

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        """Embed one batch of documents within the caps, with the document prefix applied."""
        ...


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """``ceil(len(text) / 4)``, at least one — the default meter for providers without a tokenizer."""
    return max(1, -(-len(text) // CHARS_PER_TOKEN))


def qualified_model_id(provider: str, model: str, dimension: int) -> str:
    """``provider/model@dimension`` — the one spelling of a vector space's identity."""
    return f"{provider}/{model}@{dimension}"


class LocalEmbeddingProvider:
    """Base for CPU-bound providers: a sync batch kernel hopped off the loop.

    Subclasses set ``model_id`` and ``dimension`` and implement
    :meth:`embed_batch`. ``embed_documents`` runs the kernel on
    *executor* — the loop's default pool when none is given — so a
    10⁵-chunk reindex never holds the event loop; ``embed_query`` runs
    its one short text inline. Caps are unbounded except the per-hop
    input count, which only shapes a worker call's payload.
    """

    model_id: str
    dimension: int
    max_input_tokens: int | None = None
    max_batch_inputs: int = LOCAL_BATCH_INPUTS
    max_batch_tokens: int | None = None

    def __init__(self, *, executor: Executor | None = None) -> None:
        self._executor = executor

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """The synchronous kernel: one vector per text, in order."""
        raise NotImplementedError

    async def embed_query(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    async def embed_documents(self, texts: Sequence[str]) -> Embedded:
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(self._executor, partial(self.embed_batch, list(texts)))
        return Embedded(vectors, sum(self.estimate_tokens(text) for text in texts))
