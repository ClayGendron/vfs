"""The hashing embedder: the harness's pin, determinism, its cosine honesty, the provider face."""

from __future__ import annotations

import math

import pytest

from tests.ranking.embedders import HASH_DIMENSION, PIN_SENTENCE, vector_digest
from tests.ranking.test_embedders import HASH_PIN
from vfs.embedding import HashEmbeddingProvider, hash_embedding
from vfs.embedding.hashing import HASH_DIMENSION as CORE_DIMENSION


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class TestHashEmbedding:
    def test_the_harness_pin_is_cores_function(self) -> None:
        assert vector_digest(hash_embedding(PIN_SENTENCE, HASH_DIMENSION)) == HASH_PIN

    def test_unit_length_and_determinism(self) -> None:
        one = hash_embedding("the cache is a cache", 32)
        assert math.isclose(math.sqrt(sum(v * v for v in one)), 1.0, rel_tol=1e-9)
        assert one == hash_embedding("the cache is a cache", 32)

    def test_shared_vocabulary_scores_positive_and_disjoint_near_zero(self) -> None:
        a = hash_embedding("the scheduler flushes the cache", 256)
        b = hash_embedding("the cache is flushed by the scheduler", 256)
        c = hash_embedding("quantum chromodynamics lattice", 256)
        assert _cosine(a, b) > 0.3
        assert abs(_cosine(a, c)) < 0.3

    def test_empty_text_is_the_zero_vector(self) -> None:
        assert hash_embedding("", 8) == [0.0] * 8

    def test_a_non_positive_dimension_is_refused(self) -> None:
        with pytest.raises(ValueError, match="dimension must be positive"):
            hash_embedding("x", 0)
        with pytest.raises(ValueError, match="dimension must be positive"):
            HashEmbeddingProvider(0)


class TestHashProvider:
    async def test_identity_defaults_and_vectors(self) -> None:
        provider = HashEmbeddingProvider()
        assert provider.dimension == CORE_DIMENSION == 64
        assert provider.model_id == "hash/blake2b-tokens-bigrams@64"
        assert await provider.embed_query("alpha beta") == hash_embedding("alpha beta", 64)
        answer = await provider.embed_documents(["alpha beta", "gamma"])
        assert answer.vectors == [hash_embedding("alpha beta", 64), hash_embedding("gamma", 64)]

    def test_a_wider_space_has_its_own_identity(self) -> None:
        assert HashEmbeddingProvider(256).model_id == "hash/blake2b-tokens-bigrams@256"
