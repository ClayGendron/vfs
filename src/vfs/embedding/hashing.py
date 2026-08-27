"""The hashing embedder — the zero-dependency, deterministic floor.

Signed feature hashing of the lexical index's own tokens and their
bigrams, L2-normalised: identical text gives identical vectors, shared
vocabulary gives positive cosine, disjoint vocabulary gives about zero.
It cannot rank by meaning and never pretends to — it exists so the
conformance suite and the in-memory backend can exercise batching,
budgets, the cache, identity refusal, the lease and tier honesty on
every engine leg with no key, no download and no model file.

    provider = HashEmbeddingProvider(dimension=64)
    vector = hash_embedding("flush the cache", 64)

The digest is BLAKE2b, so a vector is the same in every process and on
every platform (``hash()`` is salted per process; this is not).
"""

from __future__ import annotations

import hashlib
import math
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from vfs.embedding.provider import LocalEmbeddingProvider, qualified_model_id
from vfs.models.lexical import tokenize

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

HASH_DIMENSION: Final = 64
"""The default width — small enough that a conformance leg's vectors cost nothing."""

_DIGEST_BYTES: Final = 8
_SIGN_BIT: Final = 63


def hash_embedding(text: str, dimension: int) -> list[float]:
    """The unit vector of *text*'s hashed tokens and bigrams in *dimension* buckets."""
    if dimension < 1:
        msg = f"dimension must be positive, got {dimension}"
        raise ValueError(msg)
    buckets = [0.0] * dimension
    tokens = tokenize(text)
    for feature in tokens + [f"{left} {right}" for left, right in pairwise(tokens)]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=_DIGEST_BYTES).digest()
        value = int.from_bytes(digest, "little")
        buckets[value % dimension] += 1.0 if value >> _SIGN_BIT else -1.0
    norm = math.sqrt(sum(weight * weight for weight in buckets)) or 1.0
    return [weight / norm for weight in buckets]


class HashEmbeddingProvider(LocalEmbeddingProvider):
    """:func:`hash_embedding` behind the provider seam; the same prefix-free vector for queries and documents."""

    def __init__(self, dimension: int = HASH_DIMENSION, *, executor: Executor | None = None) -> None:
        super().__init__(executor=executor)
        if dimension < 1:
            msg = f"dimension must be positive, got {dimension}"
            raise ValueError(msg)
        self.dimension = dimension
        self.model_id = qualified_model_id("hash", "blake2b-tokens-bigrams", dimension)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [hash_embedding(text, self.dimension) for text in texts]
