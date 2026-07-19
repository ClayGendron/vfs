"""The ``Edge`` model — one typed relation between two files.

An edge is entry-scoped metadata, not a namespace entry: its identity is
``(source, target, edge_type)`` — mirroring the ``edges`` table's
``(source_id, target_id, edge_type)`` key. It carries no ``path`` or ``name``
and is never placed in the namespace; traversal is a verb over rows, never a
directory listing.

Construction is the validation door: endpoints must be user-space paths
(never the root or the reserved ``/.vfs`` scope) and ``edge_type`` must be a
lawful single segment, so a malformed edge fails here rather than downstream.
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from vfs.paths import Path, is_meta_path, validate_segment


class Edge(BaseModel):
    """One directed, typed edge between two user-space entries.

    ``version`` is the per-edge monotone value (ADR 013); it is not yet a
    column on the ``edges`` table — the write-path wiring spec adds it.
    """

    source: Path
    target: Path
    edge_type: str
    weight: float | None = None
    distance: float | None = None
    version: int = 1

    @model_validator(mode="after")
    def _validate_shape(self) -> Edge:
        for label, endpoint in (("source", self.source), ("target", self.target)):
            if endpoint == "/":
                msg = f"{label} must not be the root"
                raise ValueError(msg)
            if is_meta_path(endpoint):
                msg = f"{label} must not be a reserved metadata path: {endpoint}"
                raise ValueError(msg)
        validate_segment(self.edge_type, "edge_type")
        if self.version < 1:
            msg = f"version must be >= 1, got {self.version}"
            raise ValueError(msg)
        return self
