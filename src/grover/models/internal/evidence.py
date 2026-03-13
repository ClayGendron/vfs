"""Evidence types — why a path appeared in a search result.

All evidence types are frozen Pydantic BaseModels. They attach to
``File``, ``FileChunk``, ``FileVersion``, and ``FileConnection`` objects
to explain how each entity was discovered by an operation.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Evidence(BaseModel):
    """Base evidence — why an entity appeared in a result."""

    model_config = ConfigDict(frozen=True)

    operation: str
    score: float = 0.0
    query_args: dict = {}


# =====================================================================
# Search evidence
# =====================================================================


class LineMatch(BaseModel):
    """A single line match within a file."""

    model_config = ConfigDict(frozen=True)

    line_number: int
    line_content: str
    context_before: tuple[str, ...] = ()
    context_after: tuple[str, ...] = ()


class GlobEvidence(Evidence):
    """Evidence from a glob match."""

    is_directory: bool = False
    size_bytes: int | None = None
    mime_type: str | None = None


class GrepEvidence(Evidence):
    """Evidence from a grep match."""

    line_matches: tuple[LineMatch, ...] = ()


class TreeEvidence(Evidence):
    """Evidence from a tree listing."""

    depth: int = 0
    is_directory: bool = False


class ListDirEvidence(Evidence):
    """Evidence from a directory listing."""

    is_directory: bool = False
    size_bytes: int | None = None


# =====================================================================
# Trash / version / share evidence
# =====================================================================


class TrashEvidence(Evidence):
    """Evidence from a trash listing."""

    deleted_at: datetime | None = None
    original_path: str = ""


class VersionEvidence(Evidence):
    """Evidence from a version listing."""

    version: int = 0
    content_hash: str = ""
    size_bytes: int = 0
    created_at: datetime | None = None
    created_by: str | None = None


class ShareEvidence(Evidence):
    """Evidence from a share listing."""

    grantee_id: str = ""
    permission: str = ""
    granted_by: str = ""
    expires_at: datetime | None = None


# =====================================================================
# Vector / lexical / hybrid evidence
# =====================================================================


class VectorEvidence(Evidence):
    """Evidence from a vector (semantic) search."""

    snippet: str = ""


class LexicalEvidence(Evidence):
    """Evidence from a lexical (BM25/full-text) search."""

    snippet: str = ""


class HybridEvidence(Evidence):
    """Evidence from a hybrid search."""

    snippet: str = ""


# =====================================================================
# Graph evidence
# =====================================================================


class GraphEvidence(Evidence):
    """Evidence from a graph query."""

    algorithm: str = ""
    relationship: str = ""
