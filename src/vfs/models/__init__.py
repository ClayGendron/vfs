"""Domain models: what the VFS stores and observes.

``entry`` holds the namespace ``Entry`` plus ``Observation``/``Match``;
``chunk``, ``version``, and ``edge`` are the entry-scoped metadata models,
one per table; ``rows``, ``vector``, ``versioning``, ``chunking``, and
``code_grams`` carry the supporting column, embedding, and content machinery.
"""

from vfs.models.chunk import Chunk
from vfs.models.edge import Edge
from vfs.models.entry import (
    ENTRY_OWNED_MIRRORS,
    OBSERVATION_MIRROR_FIELDS,
    OBSERVATION_MIRROR_OWNERS,
    OBSERVATION_QUERY_FIELDS,
    Entry,
    Match,
    Observation,
)
from vfs.models.version import Version

__all__ = [
    "ENTRY_OWNED_MIRRORS",
    "OBSERVATION_MIRROR_FIELDS",
    "OBSERVATION_MIRROR_OWNERS",
    "OBSERVATION_QUERY_FIELDS",
    "Chunk",
    "Edge",
    "Entry",
    "Match",
    "Observation",
    "Version",
]
