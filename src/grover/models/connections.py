"""FileConnection model — directed edges in the knowledge graph.

Provides ``FileConnectionBase`` (non-table base) and ``FileConnection``
(concrete table).  Subclass ``FileConnectionBase`` with ``table=True`` and
a custom ``__tablename__`` to use a different table name per backend.

Replaces the previous ``GroverEdge`` model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class FileConnectionBase(SQLModel):
    """Base fields for a graph edge. Subclass with ``table=True`` for a concrete table."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source_path: str = Field(index=True)
    target_path: str = Field(index=True)
    type: str = Field(default="")
    weight: float = Field(default=1.0)
    metadata_json: str = Field(default="{}")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore[invalid-argument-type]
    )


class FileConnection(FileConnectionBase, table=True):
    """Default graph edge table — ``grover_file_connections``."""

    __tablename__ = "grover_file_connections"
