"""Domain models: what the VFS stores and observes.

``entry`` holds the namespace ``Entry`` plus ``Observation``/``Match``;
``chunk``, ``version``, and ``edge`` are the entry-scoped metadata models,
one per table; ``rows``, ``vector``, ``versioning``, ``chunking``, and
``code_grams`` carry the supporting column, embedding, and content machinery.
"""

from vfs.models.chunk import Chunk
from vfs.models.edge import Edge
from vfs.models.entry import (
    CONTENT_KINDS,
    ENTRY_OWNED_MIRRORS,
    MEASURED_BODY,
    OBSERVATION_MIRROR_FIELDS,
    OBSERVATION_MIRROR_OWNERS,
    OBSERVATION_QUERY_FIELDS,
    ContentHash,
    Entry,
    Match,
    Observation,
)
from vfs.models.media import RENDER_STATUSES, RENDERED_STATUSES, SOURCES, RenderStatus, Source, sniff_mime
from vfs.models.version import BodyMetrics, Version, line_count, measure_bytes, measure_text

__all__ = [
    "CONTENT_KINDS",
    "ENTRY_OWNED_MIRRORS",
    "MEASURED_BODY",
    "OBSERVATION_MIRROR_FIELDS",
    "OBSERVATION_MIRROR_OWNERS",
    "OBSERVATION_QUERY_FIELDS",
    "RENDERED_STATUSES",
    "RENDER_STATUSES",
    "SOURCES",
    "BodyMetrics",
    "Chunk",
    "ContentHash",
    "Edge",
    "Entry",
    "Match",
    "Observation",
    "RenderStatus",
    "Source",
    "Version",
    "line_count",
    "measure_bytes",
    "measure_text",
    "sniff_mime",
]
