"""The embedder pins: one sentence's vector digest for each embedder."""

from __future__ import annotations

import math

import pytest

from tests.ranking.embedders import HASH_DIMENSION, PIN_SENTENCE, hash_embed, potion_embed, vector_digest

HASH_PIN = "c985e95f3c484cf1753fe1321988c241b4a78bec2f4565eae04ae73397819bf4"
POTION_PIN = "8d2c32da1baf10cbd4b8b49e0b0d93b170fa3c9524b10b2b31563251c4f90ee2"


def test_the_hashing_embedder_is_pinned() -> None:
    vector = hash_embed(PIN_SENTENCE)
    assert len(vector) == HASH_DIMENSION
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-6)
    assert vector_digest(vector) == HASH_PIN


def test_the_hashing_embedder_tokenizes_like_the_index() -> None:
    assert hash_embed("Flush The Cache") == hash_embed("flush the cache")  # the fold
    assert hash_embed("PostingsBuilder") != hash_embed("postingsbuilder")  # the case split adds parts


def test_potion_base_8m_is_pinned_when_cached() -> None:
    vector = potion_embed(PIN_SENTENCE)
    if vector is None:
        pytest.skip("model2vec or the cached potion-base-8M model is absent")
    assert len(vector) == 256
    assert vector_digest(vector) == POTION_PIN
