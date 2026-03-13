"""Internal types — Ref, File, FileChunk, FileVersion, FileConnection.

These are the runtime data types for Grover's internal API. They are
Pydantic BaseModels (not SQLModel) and represent files hierarchically:
chunks and versions are attributes of files, not fake files.

DB models live in ``grover.models.database`` and use the ``Model`` suffix.
"""

from datetime import datetime

from pydantic import BaseModel

from grover.models.internal.evidence import Evidence


class Ref(BaseModel):
    """Identity for any addressable entity in Grover."""

    path: str


class FileChunk(Ref):
    """A chunk (function, class, section) within a file."""

    name: str = ""
    content: str = ""
    embedding: list[float] | None = None
    tokens: int = 0
    line_start: int = 0
    line_end: int = 0
    evidence: list[Evidence] = []


class FileVersion(Ref):
    """A historical version of a file."""

    number: int = 0
    embedding: list[float] | None = None
    evidence: list[Evidence] = []
    created_at: datetime | None = None


class File(Ref):
    """A file or directory with optional hydrated content, chunks, and versions."""

    is_directory: bool = False
    content: str | None = None
    embedding: list[float] | None = None
    tokens: int = 0
    lines: int = 0
    current_version: int = 0
    chunks: list[FileChunk] = []
    versions: list[FileVersion] = []
    evidence: list[Evidence] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FileConnection(BaseModel):
    """A directed edge between two entities."""

    source: Ref
    target: Ref
    type: str
    weight: float = 1.0
    distance: float = 1.0
    evidence: list[Evidence] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
