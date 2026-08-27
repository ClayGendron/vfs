"""The three adapters against their doubles: OpenAI, LangChain, model2vec — and the real potion model when cached."""

from __future__ import annotations

import importlib.util
import os

import pytest

from tests.ranking.embedders import PIN_SENTENCE, POTION_MODEL, vector_digest
from tests.ranking.test_embedders import POTION_PIN
from tests.support.embedding_doubles import FakeLangChainEmbeddings, FakeOpenAIClient, FakeStaticModel
from vfs.embedding import LangChainEmbeddingProvider, Model2VecEmbeddingProvider, OpenAIEmbeddingProvider
from vfs.embedding import model2vec as model2vec_module
from vfs.embedding.langchain import DIMENSION_PROBE
from vfs.embedding.openai import MAX_BATCH_INPUTS, MAX_BATCH_TOKENS, MAX_INPUT_TOKENS


class TestOpenAI:
    def test_identity_from_the_model_table(self) -> None:
        provider = OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-3-large")
        assert (provider.model_id, provider.dimension) == ("openai/text-embedding-3-large@3072", 3072)
        assert (provider.max_input_tokens, provider.max_batch_inputs, provider.max_batch_tokens) == (
            MAX_INPUT_TOKENS,
            MAX_BATCH_INPUTS,
            MAX_BATCH_TOKENS,
        )

    def test_matryoshka_dimensions_qualify_the_identity(self) -> None:
        provider = OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-3-large", dimensions=256)
        assert (provider.model_id, provider.dimension) == ("openai/text-embedding-3-large@256", 256)

    def test_refusals_at_construction(self) -> None:
        with pytest.raises(ValueError, match="unknown OpenAI embedding model"):
            OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-9-future")
        assert OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-9-future", dimensions=64).dimension == 64
        with pytest.raises(ValueError, match="fixed width"):
            OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-ada-002", dimensions=256)
        with pytest.raises(ValueError, match="dimensions must be positive"):
            OpenAIEmbeddingProvider(FakeOpenAIClient(), "text-embedding-3-small", dimensions=0)

    async def test_documents_ride_one_request_sorted_by_index_with_reported_usage(self) -> None:
        client = FakeOpenAIClient(dimension=1536)
        provider = OpenAIEmbeddingProvider(client, "text-embedding-3-small")
        answer = await provider.embed_documents(["first", "second"])
        assert client.requests == [
            {"input": ["first", "second"], "model": "text-embedding-3-small", "encoding_format": "float"}
        ]
        assert [len(v) for v in answer.vectors] == [1536, 1536]
        assert answer.tokens == len("first") + len("second")
        # sorted by index: the first vector is the first input's
        first = await provider.embed_query("first")
        assert answer.vectors[0] == first

    async def test_dimensions_are_sent_only_when_set_and_usage_falls_back_to_the_estimate(self) -> None:
        client = FakeOpenAIClient(usage=False)
        provider = OpenAIEmbeddingProvider(client, "text-embedding-3-small", dimensions=8)
        answer = await provider.embed_documents(["abcdefgh"])
        assert client.requests[0]["dimensions"] == 8
        assert answer.tokens == provider.estimate_tokens("abcdefgh") == 2

    async def test_a_wrong_width_or_count_is_refused(self) -> None:
        provider = OpenAIEmbeddingProvider(FakeOpenAIClient(dimension=4), "text-embedding-3-small")
        with pytest.raises(RuntimeError, match="wrong width"):
            await provider.embed_documents(["x"])


class TestLangChain:
    def test_identity_supplied_and_qualified(self) -> None:
        provider = LangChainEmbeddingProvider(FakeLangChainEmbeddings(), model_id="nomic-embed-text", dimension=6)
        assert provider.model_id == "langchain/nomic-embed-text@6"
        assert (
            LangChainEmbeddingProvider(FakeLangChainEmbeddings(), model_id="voyage/voyage-3@6", dimension=6).model_id
            == "voyage/voyage-3@6"
        )

    def test_the_width_is_probed_once_when_not_given(self) -> None:
        embeddings = FakeLangChainEmbeddings(dimension=12)
        provider = LangChainEmbeddingProvider(embeddings, model_id="probed")
        assert provider.dimension == 12 and embeddings.probes == [DIMENSION_PROBE]

    def test_refusals(self) -> None:
        with pytest.raises(ValueError, match="model_id must name"):
            LangChainEmbeddingProvider(FakeLangChainEmbeddings(), model_id="")
        with pytest.raises(ValueError, match="dimension must be positive"):
            LangChainEmbeddingProvider(FakeLangChainEmbeddings(), model_id="m", dimension=0)

    async def test_the_async_pair_serves_and_widths_are_checked(self) -> None:
        embeddings = FakeLangChainEmbeddings(dimension=6)
        provider = LangChainEmbeddingProvider(embeddings, model_id="m", dimension=6)
        answer = await provider.embed_documents(["a b", "c"])
        assert embeddings.calls == [["a b", "c"]] and len(answer.vectors) == 2 and answer.tokens == 2
        assert len(await provider.embed_query("q")) == 6
        wrong = LangChainEmbeddingProvider(FakeLangChainEmbeddings(dimension=3), model_id="m", dimension=6)
        with pytest.raises(RuntimeError, match="wrong width"):
            await wrong.embed_query("q")

    async def test_a_short_answer_is_refused(self) -> None:
        class Short(FakeLangChainEmbeddings):
            async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
                return [await self.aembed_query(texts[0])]

        provider = LangChainEmbeddingProvider(Short(), model_id="m", dimension=6)
        with pytest.raises(RuntimeError, match="answered 1 vectors for 2 inputs"):
            await provider.embed_documents(["a", "b"])


class TestModel2Vec:
    async def test_a_loaded_model_object_serves_with_its_width(self) -> None:
        model = FakeStaticModel(dim=5)
        provider = Model2VecEmbeddingProvider(model, model_name="fake/model")
        assert (provider.model_id, provider.dimension) == ("model2vec/fake/model@5", 5)
        answer = await provider.embed_documents(["x y"])
        assert model.encoded == [["x y"]] and len(answer.vectors[0]) == 5

    def test_loading_by_name_without_the_extra_is_a_classified_import_error(self, monkeypatch) -> None:
        monkeypatch.setattr(model2vec_module, "_PACKAGE", "model2vec_absent_package")
        with pytest.raises(ImportError, match="embed-local"):
            Model2VecEmbeddingProvider()

    def test_loading_by_name_goes_through_from_pretrained(self, monkeypatch) -> None:
        class Loader:
            @staticmethod
            def from_pretrained(name: str) -> FakeStaticModel:
                assert name == "minishlab/potion-base-8M"
                return FakeStaticModel(dim=256)

        monkeypatch.setattr(model2vec_module, "static_model_loader", lambda: Loader)
        assert Model2VecEmbeddingProvider().model_id == "model2vec/minishlab/potion-base-8M@256"

    async def test_the_real_potion_model_reproduces_the_harness_pin_when_cached(self) -> None:
        if importlib.util.find_spec("model2vec") is None:
            pytest.skip("model2vec is not installed")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            provider = Model2VecEmbeddingProvider(model_name=POTION_MODEL)
        except Exception:
            pytest.skip("potion-base-8M is not in the local Hub cache")
        assert provider.dimension == 256
        assert vector_digest(await provider.embed_query(PIN_SENTENCE)) == POTION_PIN
