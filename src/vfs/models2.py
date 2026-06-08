"""Domain models and table definitions for the VFS.

This module holds the project's persisted shapes. The central one is
:class:`VFSEntry` — the unified kinded record every namespace entity (file,
directory, chunk, version, edge, api node) shares, where the ``kind`` field
determines which nullable fields are relevant and how operations dispatch.
Alongside it live the supporting structures: the code-gram index tables
(staging delta-log and packed posting list) and the small value types and
write-plan records the entry model produces.

``VFSEntry`` is a pure :class:`pydantic.BaseModel` — a detached domain value,
never bound to a database session. It carries fields, the construction-time
validator, and pure-data methods (``chunk``, ``plan_file_write``,
``set_version``, ``to_candidate``, version reconstruction). Persistence is a
separate concern: :func:`build_entry_table` mints SQLAlchemy 2.0 Core
``Table`` objects per mount from the model's column-annotated fields, and the
repository (elsewhere) is the only code that ever holds a ``Session``.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Final, TypedDict, cast

from pydantic import BaseModel, Field, PrivateAttr, computed_field, model_validator
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Table,
    TypeEngine,
)

from vfs.bm25 import tokenize as lexical_tokenize
from vfs.chunking import (
    NOTEBOOK_EXTENSION,
    grammar_for_extension,
    split_code,
    split_notebook,
    split_with_line_ranges,
)
from vfs.paths import (
    ObjectKind,
    VFSPath,
    chunk_path,
    decompose_edge,
    extract_extension,
    normalize_path,
    resolve_path,
    version_path,
)
from vfs.results import Candidate
from vfs.vector import NativeEmbeddingConfig, Vector, VectorType
from vfs.versioning import create_version as create_version_record
from vfs.versioning import reconstruct_version


@dataclass(frozen=True)
class Col:
    """Column metadata for a persisted model field.

    A field becomes a database column *only* when its type is annotated with a
    ``Col`` — ``Annotated[str, Col(unique=True, index=True)]``. Persistence is
    opt-in: a bare field or a ``@computed_field`` carries no ``Col`` and is not
    stored. :func:`build_entry_table` reads these to emit each ``Column``;
    Pydantic ignores them. ``sa_type`` overrides the type inferred from the
    annotation (e.g. ``DateTime(timezone=True)``, ``VectorType()``); ``length``
    sets ``String`` width; ``persist=False`` is the escape hatch for a field
    that needs a ``Col`` for documentation but must stay out of the table.
    """

    index: bool = False
    unique: bool = False
    primary_key: bool = False
    length: int | None = None
    nullable: bool | None = None
    sa_type: TypeEngine[Any] | None = None
    persist: bool = True


# Gram staging delta-log action codes.
GRAM_ACTION_DELETE: Final = 0
GRAM_ACTION_ADD: Final = 1

# Posting-list encoding tags. v1 writes delta+gamma; the per-row tag lets the
# format evolve per gram without a migration.
ENCODING_DELTA_VARINT: Final = 1
ENCODING_DELTA_GAMMA: Final = 2
ENCODING_ROARING: Final = 3

# Column type for the entry primary key and its self-referential id
# relationships: 64-bit, narrowing to sqlite INTEGER so AUTOINCREMENT applies.
ENTRY_ID_TYPE: Final = BigInteger().with_variant(Integer, "sqlite")


# ---------------------------------------------------------------------------
# The unified object model
# ---------------------------------------------------------------------------


class VFSEntry(BaseModel):
    """The full record of one object in the VFS namespace.

    Every entity — file, directory, chunk, version, edge, api node — shares
    this record shape; ``kind`` determines which nullable fields are relevant
    and how operations dispatch. A pure detached value: constructing one runs
    the validator but never touches a database. :func:`build_entry_table` mints
    the persisted table from the fields annotated with :class:`Col`.
    """

    # Which fields the caller passed explicitly. Transient process-only state:
    # a private attr, so it stays out of model_fields, columns, and model_dump.
    _explicit_fields: frozenset[str] = PrivateAttr(default_factory=frozenset)

    def __init__(self, **data: object) -> None:
        explicit = frozenset(data)
        super().__init__(**data)
        self._explicit_fields = explicit

    # --- Identity -----------------------------------------------------------

    id: Annotated[int | None, Col(primary_key=True, sa_type=ENTRY_ID_TYPE)] = None
    external_id: Annotated[str | None, Col(length=1024)] = None
    path: Annotated[VFSPath, Col(unique=True, index=True, length=1024)]
    name: Annotated[str, Col(length=255)] = ""
    kind: Annotated[ObjectKind, Col(index=True, length=32)]
    parent_dir_id: Annotated[int | None, Col(index=True, sa_type=ENTRY_ID_TYPE)] = None
    parent_file_id: Annotated[int | None, Col(index=True, sa_type=ENTRY_ID_TYPE)] = None

    # --- Content ------------------------------------------------------------

    content: Annotated[str | None, Col()] = None
    description: Annotated[str | None, Col()] = None
    version_diff: Annotated[str | None, Col()] = None
    content_hash: Annotated[str | None, Col(length=64)] = None
    mime_type: Annotated[str | None, Col(length=255)] = None
    ext: Annotated[str | None, Col(index=True, length=32)] = None

    # --- Metrics ------------------------------------------------------------

    lines: Annotated[int, Col()] = 0
    size_bytes: Annotated[int, Col()] = 0
    tokens: Annotated[int, Col()] = 0
    lexical_tokens: Annotated[int, Col()] = 0

    # --- Chunk-specific -----------------------------------------------------

    line_start: Annotated[int | None, Col()] = None
    line_end: Annotated[int | None, Col()] = None

    # --- Search indexing ----------------------------------------------------

    chunked: Annotated[bool, Col(index=True)] = False
    encoded: Annotated[bool, Col(index=True)] = False

    # --- Version-specific ---------------------------------------------------

    version_number: Annotated[int | None, Col()] = None
    is_snapshot: Annotated[bool | None, Col()] = None
    created_by: Annotated[str | None, Col(length=255)] = None

    # --- Edge-specific ------------------------------------------------------
    # source_path / target_path are derived from path below, not stored; the
    # endpoint ids are the stable backbone for those derived paths.

    edge_type: Annotated[str | None, Col(length=255)] = None
    edge_weight: Annotated[float | None, Col()] = None
    edge_distance: Annotated[float | None, Col()] = None
    source_file_id: Annotated[int | None, Col(index=True, sa_type=ENTRY_ID_TYPE)] = None
    target_file_id: Annotated[int | None, Col(index=True, sa_type=ENTRY_ID_TYPE)] = None

    # --- Embedding ----------------------------------------------------------

    embedding: Annotated[Vector | None, Col(sa_type=VectorType())] = None

    # --- Ownership ----------------------------------------------------------

    owner_id: Annotated[str | None, Col(index=True, length=255)] = None
    original_path: Annotated[str | None, Col(length=1024)] = None

    # --- Timestamps ---------------------------------------------------------

    created_at: Annotated[datetime | None, Col(sa_type=DateTime(timezone=True))] = None
    updated_at: Annotated[datetime | None, Col(sa_type=DateTime(timezone=True))] = None
    deleted_at: Annotated[datetime | None, Col(sa_type=DateTime(timezone=True))] = None

    # --- Derived relationship paths -----------------------------------------
    # Projected from path, never stored; the *_id columns above are the stored
    # backbone. These mirror the VFSPath properties of the same name.

    @computed_field
    @property
    def parent_dir(self) -> VFSPath:
        """Directory containing this node."""
        return self.path.parent_dir

    @computed_field
    @property
    def parent_file(self) -> VFSPath | None:
        """Owning file for a chunk/version/edge meta path, else None."""
        return self.path.parent_file

    @computed_field
    @property
    def source_file(self) -> VFSPath | None:
        """Edge tail endpoint for an edge path, else None."""
        return self.path.source_file

    @computed_field
    @property
    def target_file(self) -> VFSPath | None:
        """Edge head endpoint for an edge path, else None."""
        return self.path.target_file
