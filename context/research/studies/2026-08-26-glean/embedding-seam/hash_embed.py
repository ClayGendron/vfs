"""Zero-dependency feature-hashing embedder: deterministic, dimension-parameterized."""
from __future__ import annotations

import math
import re
import zlib

_TOKEN = re.compile(r"\w+")


def embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        h = zlib.crc32(tok.encode())  # stable across processes, unlike hash()
        vec[h % dim] += 1.0 if (h >> 31) & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed_batch(texts: list[str], dim: int = 256) -> list[list[float]]:
    return [embed(t, dim) for t in texts]
