"""The portable vector bytes: packed little-endian float32, four bytes a component.

The one codec every column type and kernel shares — ``vector.py`` binds
it on the portable path, the MariaDB native type reuses it, and the
engine's cosine kernel reads the same bytes straight off a fetched page.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

FLOAT32_BYTES: Final = 4
"""Bytes per packed component."""


def pack_vector(values: Sequence[float]) -> bytes:
    """*values* as little-endian float32 bytes."""
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(raw: bytes) -> list[float]:
    """The floats of a packed vector; refuses a byte length that is not a whole number of components."""
    if len(raw) % FLOAT32_BYTES:
        msg = f"Vector read: {len(raw)} bytes is not a whole number of float32 components"
        raise ValueError(msg)
    return list(struct.unpack(f"<{len(raw) // FLOAT32_BYTES}f", raw))
