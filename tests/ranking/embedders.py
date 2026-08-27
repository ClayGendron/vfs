"""The harness's embedders, pinned by the digest of one sentence's vector.

The hashing embedder is core's ``hash_embedding`` — the zero-dependency
floor the conformance suite and the in-memory backend run on — at the
harness's wider dimension. The model2vec loader answers ``None`` when
the package or the cached model is absent, and the tests skip.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import struct
from typing import Any, Final

from vfs.embedding import hash_embedding

StaticModel: Any = None
if importlib.util.find_spec("model2vec") is not None:
    StaticModel = importlib.import_module("model2vec").StaticModel

PIN_SENTENCE: Final = "The scheduler publishes and the allocator flushes; the cache is a cache."
POTION_MODEL: Final = "minishlab/potion-base-8M"
HASH_DIMENSION: Final = 256


def hash_embed(text: str, dimension: int = HASH_DIMENSION) -> list[float]:
    """Core's signed feature hashing of the index's tokens and their bigrams, at the harness width."""
    return hash_embedding(text, dimension)


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
