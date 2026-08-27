"""The harness's embedders, pinned by the digest of one sentence's vector.

The hashing embedder is the zero-dependency floor — a local copy of the
function ``HashEmbeddingProvider`` ships in core once the embedding
provider lands, after which this module imports it instead. The
model2vec loader answers ``None`` when the package or the cached model
is absent, and the tests skip.
"""

from __future__ import annotations

import hashlib
import math
import os
import struct
from itertools import pairwise
from typing import Final

from vfs.models.lexical import tokenize

try:
    from model2vec import StaticModel  # ty: ignore[unresolved-import]
except ImportError:  # pragma: no cover - the optional semantic embedder
    StaticModel = None

PIN_SENTENCE: Final = "The scheduler publishes and the allocator flushes; the cache is a cache."
POTION_MODEL: Final = "minishlab/potion-base-8M"
HASH_DIMENSION: Final = 256


def hash_embed(text: str, dimension: int = HASH_DIMENSION) -> list[float]:
    """Signed feature hashing of the index's tokens and their bigrams, L2-normalised."""
    buckets = [0.0] * dimension
    tokens = tokenize(text)
    for feature in tokens + [f"{left} {right}" for left, right in pairwise(tokens)]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        buckets[value % dimension] += 1.0 if value >> 63 else -1.0
    norm = math.sqrt(sum(weight * weight for weight in buckets)) or 1.0
    return [weight / norm for weight in buckets]


def potion_embed(text: str) -> list[float] | None:
    """potion-base-8M's vector for *text* from the local HF cache, or ``None``."""
    if StaticModel is None:
        return None
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    try:
        model = StaticModel.from_pretrained(POTION_MODEL)
    except Exception:  # not cached, or the hub refused offline
        return None
    return [float(value) for value in model.encode([text])[0]]


def vector_digest(vector: list[float]) -> str:
    """sha256 of the vector packed as little-endian float32 — the pin."""
    return hashlib.sha256(struct.pack(f"<{len(vector)}f", *vector)).hexdigest()
