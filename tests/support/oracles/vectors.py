"""The cosine top-k kernel's oracle.

``struct`` decode, one Python loop a row, ``sorted``: slow and obviously
right. The engine multiplies and adds in float32 from the first component
to the last, so the oracle rounds to float32 after every operation — a
float64 product or sum of two float32 values rounds to the same float32
the engine produced — and its scores are bit-comparable with the engine's.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def as_float32(value: float) -> float:
    """*value* rounded to the nearest float32."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def cosine_topk(query: Sequence[float], ids: Sequence[int], vectors: bytes, k: int) -> list[tuple[int, float]]:
    """The top ``k`` of ``ids`` by dot product with ``query``, ``score DESC, id ASC``."""
    if not query:
        msg = "the query vector is empty"
        raise ValueError(msg)
    dimension = len(query)
    expected = len(ids) * dimension * 4
    if len(vectors) != expected:
        msg = f"expected {expected} bytes for {len(ids)} vectors of {dimension} components, got {len(vectors)}"
        raise ValueError(msg)
    query32 = [as_float32(component) for component in query]
    stride = dimension * 4
    scored: list[tuple[int, float]] = []
    for position, chunk_id in enumerate(ids):
        row = struct.unpack(f"<{dimension}f", vectors[position * stride : (position + 1) * stride])
        score = 0.0
        for q, v in zip(query32, row, strict=True):
            score = as_float32(score + as_float32(q * v))
        scored.append((chunk_id, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:k]
