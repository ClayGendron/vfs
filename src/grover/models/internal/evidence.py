"""Evidence types — why a path appeared in a search result.

All evidence types are frozen dataclasses. They attach to
``File``, ``FileChunk``, ``FileVersion``, and ``FileConnection`` objects
to explain how each entity was discovered by an operation.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Evidence:
    """Base evidence — why an entity appeared in a result."""

    operation: str
    score: float = 0.0
    query_args: dict = field(default_factory=dict)


# =====================================================================
# Search evidence
# =====================================================================


@dataclass(frozen=True, slots=True)
class LineMatch:
    """A single line match within a file."""

    line_number: int
    line_content: str
    context_before: tuple[str, ...] = ()
    context_after: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GlobEvidence(Evidence):
    """Evidence from a glob match."""

    is_directory: bool = False
    size_bytes: int | None = None
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class GrepEvidence(Evidence):
    """Evidence from a grep match."""

    line_matches: tuple[LineMatch, ...] = ()


@dataclass(frozen=True, slots=True)
class TreeEvidence(Evidence):
    """Evidence from a tree listing."""

    depth: int = 0
    is_directory: bool = False


@dataclass(frozen=True, slots=True)
class ListDirEvidence(Evidence):
    """Evidence from a directory listing."""

    is_directory: bool = False
    size_bytes: int | None = None


# =====================================================================
# Trash / version / share evidence
# =====================================================================


@dataclass(frozen=True, slots=True)
class TrashEvidence(Evidence):
    """Evidence from a trash listing."""

    deleted_at: datetime | None = None
    original_path: str = ""


@dataclass(frozen=True, slots=True)
class VersionEvidence(Evidence):
    """Evidence from a version listing."""

    version: int = 0
    content_hash: str = ""
    size_bytes: int = 0
    created_at: datetime | None = None
    created_by: str | None = None


@dataclass(frozen=True, slots=True)
class ShareEvidence(Evidence):
    """Evidence from a share listing."""

    grantee_id: str = ""
    permission: str = ""
    granted_by: str = ""
    expires_at: datetime | None = None


# =====================================================================
# Vector / lexical / hybrid evidence
# =====================================================================


@dataclass(frozen=True, slots=True)
class VectorEvidence(Evidence):
    """Evidence from a vector (semantic) search."""

    snippet: str = ""


@dataclass(frozen=True, slots=True)
class LexicalEvidence(Evidence):
    """Evidence from a lexical (BM25/full-text) search."""

    snippet: str = ""


@dataclass(frozen=True, slots=True)
class HybridEvidence(Evidence):
    """Evidence from a hybrid search."""

    snippet: str = ""


# =====================================================================
# Graph evidence
# =====================================================================


@dataclass(frozen=True, slots=True)
class GraphRelationshipEvidence(Evidence):
    """Evidence from a graph relationship query (predecessors, successors, ancestors, descendants).

    *paths* lists the candidate nodes this file is related to.
    """

    paths: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GraphCentralityEvidence(Evidence):
    """Evidence from a graph centrality algorithm (pagerank, betweenness, etc.)."""

    scores: dict[str, float] = field(default_factory=dict)
