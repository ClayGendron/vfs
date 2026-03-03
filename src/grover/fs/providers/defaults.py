"""Default provider implementations — renamed services.

``DefaultVersionProvider`` (formerly ``VersioningService``) and
``DefaultChunkProvider`` (formerly ``ChunkService``) are the built-in
implementations backed by SQLModel tables.
"""

from grover.fs.chunks import DefaultChunkProvider
from grover.fs.versioning import DefaultVersionProvider

__all__ = [
    "DefaultChunkProvider",
    "DefaultVersionProvider",
]
