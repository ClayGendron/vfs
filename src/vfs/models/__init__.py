"""Domain models: what the VFS stores and observes.

``entry`` holds the core ``Entry``/``Observation``/``Match`` models;
``rows``, ``vector``, ``versioning``, ``chunking``, and ``code_grams``
carry the supporting column, embedding, and content machinery.
"""

from vfs.models.entry import (
    OBSERVATION_MIRROR_FIELDS,
    OBSERVATION_QUERY_FIELDS,
    Entry,
    Match,
    Observation,
)

__all__ = [
    "OBSERVATION_MIRROR_FIELDS",
    "OBSERVATION_QUERY_FIELDS",
    "Entry",
    "Match",
    "Observation",
]
