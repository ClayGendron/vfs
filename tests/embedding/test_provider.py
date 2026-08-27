"""The provider protocol: every shipped provider satisfies it; the shared helpers and the CPU base."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.support.embedding_doubles import FakeLangChainEmbeddings, FakeOpenAIClient, FakeStaticModel, ScriptedProvider
from vfs.embedding import (
    Embedded,
    EmbeddingProvider,
    HashEmbeddingProvider,
    LangChainEmbeddingProvider,
    LocalEmbeddingProvider,
    Model2VecEmbeddingProvider,
    OpenAIEmbeddingProvider,
    estimate_tokens,
    qualified_model_id,
)
from vfs.embedding.provider import LOCAL_BATCH_INPUTS


class TestProtocol:
    @pytest.mark.parametrize(
        "provider",
        [
            HashEmbeddingProvider(),
            OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-3-small", dimensions=8),
            LangChainEmbeddingProvider(FakeLangChainEmbeddings(), model_id="fake", dimension=6),
            Model2VecEmbeddingProvider(FakeStaticModel(), model_name="fake"),
            ScriptedProvider(),
        ],
        ids=["hash", "openai", "langchain", "model2vec", "scripted"],
    )
    async def test_every_provider_satisfies_the_seam(self, provider: EmbeddingProvider) -> None:
        assert isinstance(provider, EmbeddingProvider)
        assert provider.dimension >= 1 and "@" in provider.model_id and "/" in provider.model_id
        assert provider.model_id.endswith(f"@{provider.dimension}")
        assert provider.max_batch_inputs >= 1
        assert provider.estimate_tokens("four chars here") >= 1
        query = await provider.embed_query("a query")
        assert len(query) == provider.dimension
        answer = await provider.embed_documents(["one document", "and another"])
        assert isinstance(answer, Embedded)
        assert [len(vector) for vector in answer.vectors] == [provider.dimension] * 2
        assert answer.tokens >= 2

    def test_a_partial_object_is_not_a_provider(self) -> None:
        assert not isinstance(object(), EmbeddingProvider)


class TestHelpers:
    def test_the_default_estimate_is_a_ceiling_over_four_chars_at_least_one(self) -> None:
        assert estimate_tokens("") == 1
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcde") == 2
        assert estimate_tokens("x" * 4000) == 1000

    def test_the_qualified_id_spelling(self) -> None:
        assert qualified_model_id("openai", "text-embedding-3-small", 1536) == "openai/text-embedding-3-small@1536"


class _Counting(LocalEmbeddingProvider):
    model_id = "test/counting@2"
    dimension = 2

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # ty: ignore[invalid-argument-type]
        self.threads: list[str] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:  # ty: ignore[invalid-method-override]
        self.threads.append(threading.current_thread().name)
        return [[float(len(text)), 1.0] for text in texts]


class TestLocalBase:
    async def test_documents_hop_to_the_given_executor_and_the_query_runs_inline(self) -> None:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed-test") as pool:
            provider = _Counting(executor=pool)
            answer = await provider.embed_documents(["ab", "cde"])
            assert answer.vectors == [[2.0, 1.0], [3.0, 1.0]] and answer.tokens == 2
            assert provider.threads[-1].startswith("embed-test")
            assert await provider.embed_query("abcd") == [4.0, 1.0]
            assert not provider.threads[-1].startswith("embed-test")

    async def test_the_default_hop_is_the_loops_pool(self) -> None:
        provider = _Counting()
        await provider.embed_documents(["x"])
        assert provider.threads[-1] != threading.main_thread().name  # a worker thread served it

    def test_the_declared_caps(self) -> None:
        provider = _Counting()
        assert (provider.max_input_tokens, provider.max_batch_inputs, provider.max_batch_tokens) == (
            None,
            LOCAL_BATCH_INPUTS,
            None,
        )

    def test_the_base_kernel_is_abstract(self) -> None:
        with pytest.raises(NotImplementedError):
            LocalEmbeddingProvider().embed_batch(["x"])
