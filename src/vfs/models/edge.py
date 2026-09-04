"""The ``Edge`` model — one typed relation between two files.

An edge is entry-scoped metadata, not a namespace entry: its identity is
``(source, target, edge_type)`` — mirroring the ``edges`` table's
``(source_id, target_id, edge_type)`` key. It carries no ``path`` or ``name``
and is never placed in the namespace; traversal is a verb over rows, never a
directory listing.

Construction is the validation door: endpoints must be user-space paths
(never the root or the reserved ``/.vfs`` scope) and ``edge_type`` must be a
lawful single segment. Edges are caller-authored *except* the filesystem
hierarchy family: the reserved ``"fs"`` type is refused here because storage
mints those rows directly at the row layer, mirroring ``parent_id`` — no
caller, and no domain model, ever holds one.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, model_validator

from vfs.paths import Path, is_meta_path, validate_segment

# The storage-minted hierarchy-mirror edge type. Refused at the model and at
# the verb gate; row-layer minting is the only writer.
RESERVED_EDGE_TYPE: Final = "fs"


class Edge(BaseModel):
    """One directed, typed edge between two user-space entries."""

    source: Path
    target: Path
    edge_type: str
    weight: float | None = None
    distance: float | None = None

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
        if self.edge_type == RESERVED_EDGE_TYPE:
            msg = f"edge_type {RESERVED_EDGE_TYPE!r} is reserved for the storage-minted hierarchy mirror"
            raise ValueError(msg)
        return self
