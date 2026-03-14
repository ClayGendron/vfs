"""Internal types — Ref, File, FileChunk, FileVersion, FileConnection.

These are the runtime data types for Grover's internal API. They are
dataclasses and represent files hierarchically: chunks and versions
are attributes of files, not fake files.

DB models live in ``grover.models.database`` and use the ``Model`` suffix.
"""

from dataclasses import dataclass, field
from datetime import datetime

from grover.models.internal.evidence import Evidence


@dataclass(slots=True)
class Ref:
    """Identity for any addressable entity in Grover."""

    path: str


@dataclass(slots=True)
class FileChunk(Ref):
    """A chunk (function, class, section) within a file."""

    name: str = ""
    content: str = ""
    embedding: list[float] | None = None
    tokens: int = 0
    line_start: int = 0
    line_end: int = 0
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class FileVersion(Ref):
    """A historical version of a file."""

    number: int = 0
    embedding: list[float] | None = None
    evidence: list[Evidence] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass(slots=True)
class File(Ref):
    """A file or directory with optional hydrated content, chunks, and versions."""

    is_directory: bool = False
    content: str | None = None
    embedding: list[float] | None = None
    tokens: int = 0
    lines: int = 0
    size_bytes: int = 0
    mime_type: str = ""
    current_version: int = 0
    chunks: list[FileChunk] = field(default_factory=list)
    versions: list[FileVersion] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class FileConnection:
    """A directed edge between two entities."""

    source: Ref
    target: Ref
    type: str
    weight: float = 1.0
    distance: float = 1.0
    evidence: list[Evidence] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
