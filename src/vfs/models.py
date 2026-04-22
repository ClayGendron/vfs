"""VFSObject — unified kinded object model for the ``vfs_objects`` table.

All entities in the VFS namespace (files, directories, chunks, versions,
edges, api nodes) live in a single table.  The ``kind`` column determines
which nullable fields are relevant and how operations dispatch.
"""

from __future__ import annotations

import copy as _copy_mod
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import PrivateAttr, model_validator
from sqlalchemy import DateTime, Index, MetaData
from sqlalchemy.orm import InstanceState
from sqlmodel import Field, SQLModel
from sqlmodel._compat import finish_init
from sqlmodel.main import SQLModelMetaclass

from vfs.bm25 import tokenize as lexical_tokenize
from vfs.paths import (
    decompose_edge,
    extract_extension,
    is_meta_root_path,
    normalize_path,
    parse_kind,
    split_path,
    validate_path,
    version_path,
)
from vfs.paths import (
    parent_path as compute_parent_path,
)
from vfs.results import Entry
from vfs.vector import Vector, VectorType
from vfs.versioning import create_version as create_version_record
from vfs.versioning import reconstruct_version

# ---------------------------------------------------------------------------
# Base class — adds Pydantic validation back to SQLModel table models
# ---------------------------------------------------------------------------


class ValidatedSQLModel(SQLModel):
    """SQLModel base that runs Pydantic validation on explicit ``__init__``.

    SQLModel ``table=True`` models normally skip validation.  This override
    restores it while preserving no-validation for ORM loads and
    ``model_validate()`` calls.
    """

    _explicit_fields: frozenset[str] = PrivateAttr(default_factory=frozenset)

    def __init__(self, **data: object) -> None:
        explicit_fields = frozenset(data)
        super().__init__(**data)
        if not self.__class__.model_config.get("table", False):
            self._explicit_fields = explicit_fields
            return
        if not finish_init.get():
            self._explicit_fields = explicit_fields
            return
        sa_state = self.__dict__.get("_sa_instance_state")
        field_values = {}
        for field_name in self.__class__.model_fields:
            if hasattr(self, field_name):
                field_values[field_name] = getattr(self, field_name)
        self.__pydantic_validator__.validate_python(field_values, self_instance=self)
        if sa_state is not None:
            self.__dict__["_sa_instance_state"] = sa_state
        self._explicit_fields = explicit_fields


# ---------------------------------------------------------------------------
# The unified object model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionWritePlan:
    """Decision-complete write plan for a file mutation."""

    version_rows: tuple[VFSObjectBase, ...]
    final_content: str
    final_content_hash: str
    final_size_bytes: int
    final_lines: int
    final_version_number: int
    chain_verified: bool = True


@dataclass(frozen=True)
class PostgresVectorColumnSpec:
    """Schema metadata for a model-declared native Postgres vector column."""

    column_name: str
    dimension: int
    index_method: str
    operator_class: str
    index_name: str


class VFSObjectBase(ValidatedSQLModel):
    """Base fields for a VFS namespace entity.

    Every entity — file, directory, chunk, version, edge, api node —
    shares these fields.  The ``kind`` column determines which nullable
    fields are relevant and how operations dispatch.

    Subclass with ``table=True`` and a ``__tablename__`` to create a
    concrete table model.
    """

    # --- Identity -----------------------------------------------------------

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        max_length=36,
        primary_key=True,
    )
    path: str = Field(max_length=4096, unique=True, index=True)
    external_id: str | None = Field(default=None, max_length=4096)
    name: str = Field(default="", max_length=255)
    parent_path: str = Field(default="", max_length=4096, index=True)
    kind: str = Field(default="", max_length=32, index=True)

    # --- Content ------------------------------------------------------------

    content: str | None = Field(default=None)
    version_diff: str | None = Field(default=None)
    content_hash: str | None = Field(default=None, max_length=64)
    mime_type: str | None = Field(default=None, max_length=255)
    ext: str | None = Field(default=None, max_length=32, index=True)

    # --- Metrics ------------------------------------------------------------

    lines: int = Field(default=0)
    size_bytes: int = Field(default=0)
    tokens: int = Field(default=0)
    lexical_tokens: int = Field(default=0)

    # --- Chunk-specific -----------------------------------------------------

    line_start: int | None = Field(default=None)
    line_end: int | None = Field(default=None)

    # --- Version-specific ---------------------------------------------------

    version_number: int | None = Field(default=None)
    is_snapshot: bool | None = Field(default=None)
    created_by: str | None = Field(default=None, max_length=255)

    # --- Edge-specific ------------------------------------------------------

    source_path: str | None = Field(default=None, max_length=4096, index=True)
    target_path: str | None = Field(default=None, max_length=4096, index=True)
    edge_type: str | None = Field(default=None, max_length=255)
    edge_weight: float | None = Field(default=None)
    edge_distance: float | None = Field(default=None)

    # --- Embedding ----------------------------------------------------------

    embedding: Vector | None = Field(default=None, sa_type=VectorType())  # ty: ignore[invalid-argument-type]

    # --- Ownership ----------------------------------------------------------

    owner_id: str | None = Field(default=None, max_length=255, index=True)
    original_path: str | None = Field(default=None, max_length=4096)

    # --- Timestamps ---------------------------------------------------------

    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
    )

    # --- Copy / Path manipulation ---------------------------------------------

    def clone(self) -> VFSObjectBase:
        """Create a detached copy with independent SQLAlchemy state."""
        c = _copy_mod.copy(self)
        c.__dict__["_sa_instance_state"] = InstanceState(
            c,
            type(self)._sa_class_manager,  # ty: ignore[unresolved-attribute]
        )
        return c

    def _rederive_path_fields(self) -> None:
        """Normalize path and re-derive ``name``, ``parent_path``, and ``ext``."""
        self.path = normalize_path(self.path)
        self.name = split_path(self.path)[1]
        self.parent_path = compute_parent_path(self.path)
        self.ext = extract_extension(self.path) if self.kind == "file" else None

    def add_prefix(self, prefix: str) -> VFSObjectBase:
        """Prepend *prefix* to path in place, re-deriving name and parent."""
        if not prefix:
            return self
        prefix = normalize_path(prefix)
        self.path = prefix + self.path if self.path != "/" else prefix
        self._rederive_path_fields()
        return self

    def strip_prefix(self, prefix: str) -> VFSObjectBase:
        """Strip *prefix* from path in place, re-deriving name and parent."""
        if not prefix:
            return self
        prefix = normalize_path(prefix)
        if self.path == prefix:
            self.path = "/"
        elif self.path.startswith(prefix + "/"):
            self.path = self.path[len(prefix) :]
        else:
            msg = f"Path {self.path!r} does not start with prefix {prefix!r}"
            raise ValueError(msg)
        self._rederive_path_fields()
        return self

    def to_entry(
        self,
        *,
        score: float | None = None,
        include_content: bool = False,
    ) -> Entry:
        """Project this object to an immutable ``Entry``.

        Callers pass ``score`` for ranked results (vector/bm25/pagerank). By
        default ``content`` is omitted — set ``include_content=True`` for
        ``read`` / ``grep`` paths that genuinely need the text.
        """
        return Entry(
            path=self.path,
            kind=self.kind,
            content=self.content if include_content else None,
            size_bytes=self.size_bytes,
            score=score,
            updated_at=self.updated_at,
        )

    @staticmethod
    def _content_metadata(content: str) -> tuple[str, int, int]:
        """Return ``(sha256, size_bytes, lines)`` for *content*."""
        encoded = content.encode()
        return (
            hashlib.sha256(encoded).hexdigest(),
            len(encoded),
            content.count("\n") + 1 if content else 0,
        )

    @staticmethod
    def _lexical_token_count(content: str) -> int:
        """Return the lexical BM25 token count for *content*."""
        return len(lexical_tokenize(content))

    def _stored_version_payload(self) -> str:
        """Return the snapshot text or diff payload for a version row."""
        if self.kind != "version":
            msg = f"Stored payload requested for non-version object: {self.path}"
            raise ValueError(msg)
        payload = self.content if self.is_snapshot else self.version_diff
        if payload is None:
            msg = f"Version row missing stored payload: {self.path}"
            raise ValueError(msg)
        return payload

    @classmethod
    def create_version_row(
        cls,
        *,
        file_path: str,
        version_number: int,
        version_content: str,
        prev_content: str | None,
        created_by: str,
        force_snapshot: bool = False,
    ) -> VFSObjectBase:
        """Construct a version row with explicit reconstructed-state metadata."""
        content_hash, size_bytes, lines = cls._content_metadata(version_content)
        record = create_version_record(
            prev_content=prev_content,
            version_content=version_content,
            version_number=version_number,
            force_snapshot=force_snapshot,
        )
        now = datetime.now(UTC)
        return cls(
            path=version_path(file_path, version_number),
            kind="version",
            content=record.content,
            version_diff=record.version_diff,
            version_number=version_number,
            is_snapshot=record.is_snapshot,
            created_by=created_by,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            lexical_tokens=cls._lexical_token_count(version_content),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def _reconstruct_file_version(
        cls,
        version_rows: list[VFSObjectBase],
        target_version: int,
    ) -> str:
        """Reconstruct the content for *target_version* from version rows."""
        by_number = {
            row.version_number: row
            for row in version_rows
            if row.version_number is not None and row.version_number <= target_version
        }
        if target_version not in by_number:
            msg = f"Missing version row for v{target_version}"
            raise ValueError(msg)

        snapshot_version: int | None = None
        for num in range(target_version, 0, -1):
            row = by_number.get(num)
            if row is not None and row.is_snapshot:
                snapshot_version = num
                break
        if snapshot_version is None:
            msg = f"Missing snapshot for v{target_version}"
            raise ValueError(msg)

        chain: list[tuple[bool, str]] = []
        for num in range(snapshot_version, target_version + 1):
            row = by_number.get(num)
            if row is None:
                msg = f"Missing version row for v{num}"
                raise ValueError(msg)
            chain.append((bool(row.is_snapshot), row._stored_version_payload()))

        reconstructed = reconstruct_version(chain)
        expected_hash = by_number[target_version].content_hash
        if expected_hash is not None:
            actual_hash, _, _ = cls._content_metadata(reconstructed)
            if actual_hash != expected_hash:
                msg = f"Hash mismatch for v{target_version}"
                raise ValueError(msg)
        return reconstructed

    def plan_file_write(
        self,
        new_content: str,
        version_rows: list[VFSObjectBase] | None = None,
        *,
        latest_version_hash: str | None = None,
    ) -> VersionWritePlan:
        """Plan all version rows and final file state for a file write.

        Fast path: when *latest_version_hash* is provided and both
        the file hash and version hash agree, reconstruction is skipped
        entirely — the diff is computed directly from current content.

        Slow path: when hashes disagree or *version_rows* are provided
        without a hash, the full reconstruction check runs to detect
        external edits or broken version chains.
        """
        if self.kind != "file":
            msg = f"Version planning only applies to files: {self.path}"
            raise ValueError(msg)
        observed_content = self.content or ""
        observed_hash, observed_size, observed_lines = self._content_metadata(observed_content)
        planned_rows: list[VFSObjectBase] = []
        current_content = observed_content
        current_version = self.version_number or 0

        if current_version == 0:
            planned_rows.append(
                type(self).create_version_row(
                    file_path=self.path,
                    version_number=1,
                    version_content=new_content,
                    prev_content=None,
                    created_by="auto",
                    force_snapshot=True,
                )
            )
            content_hash, size_bytes, lines = self._content_metadata(new_content)
            return VersionWritePlan(
                version_rows=tuple(planned_rows),
                final_content=new_content,
                final_content_hash=content_hash,
                final_size_bytes=size_bytes,
                final_lines=lines,
                final_version_number=1,
            )

        # ── Integrity check ──────────────────────────────────────────
        # Fast path: file hash matches stored hash AND latest version
        # hash agrees → chain is intact, skip reconstruction.
        file_hash_ok = self.content_hash is not None and observed_hash == self.content_hash
        chain_verified = file_hash_ok and latest_version_hash == self.content_hash

        if not chain_verified:
            # Slow path: detect external edits or broken chains.
            external_detected = self.content_hash is not None and observed_hash != self.content_hash
            if external_detected:
                current_version += 1
                planned_rows.append(
                    type(self).create_version_row(
                        file_path=self.path,
                        version_number=current_version,
                        version_content=observed_content,
                        prev_content=None,
                        created_by="external",
                        force_snapshot=True,
                    )
                )
            elif version_rows is None:
                # Hash mismatch on version but no rows to diagnose — signal
                # the caller to fetch the chain and re-plan.
                return VersionWritePlan(
                    version_rows=(),
                    final_content=observed_content,
                    final_content_hash=observed_hash,
                    final_size_bytes=observed_size,
                    final_lines=observed_lines,
                    final_version_number=current_version,
                    chain_verified=False,
                )
            else:
                # Have version rows — check chain integrity.
                try:
                    reconstructed = type(self)._reconstruct_file_version(version_rows, current_version)
                except ValueError:
                    reconstructed = None
                if reconstructed != observed_content:
                    current_version += 1
                    planned_rows.append(
                        type(self).create_version_row(
                            file_path=self.path,
                            version_number=current_version,
                            version_content=observed_content,
                            prev_content=None,
                            created_by="repair",
                            force_snapshot=True,
                        )
                    )

        if new_content == current_content:
            return VersionWritePlan(
                version_rows=tuple(planned_rows),
                final_content=current_content,
                final_content_hash=observed_hash,
                final_size_bytes=observed_size,
                final_lines=observed_lines,
                final_version_number=current_version,
            )

        current_version += 1
        planned_rows.append(
            type(self).create_version_row(
                file_path=self.path,
                version_number=current_version,
                version_content=new_content,
                prev_content=current_content,
                created_by="auto",
            )
        )
        content_hash, size_bytes, lines = self._content_metadata(new_content)
        return VersionWritePlan(
            version_rows=tuple(planned_rows),
            final_content=new_content,
            final_content_hash=content_hash,
            final_size_bytes=size_bytes,
            final_lines=lines,
            final_version_number=current_version,
        )

    def apply_write_plan(self, plan: VersionWritePlan) -> None:
        """Apply a planned file write to this live file row."""
        self.content = plan.final_content
        self.version_diff = None
        self.content_hash = plan.final_content_hash
        self.size_bytes = plan.final_size_bytes
        self.lines = plan.final_lines
        self.lexical_tokens = self._lexical_token_count(plan.final_content)
        self.version_number = plan.final_version_number
        self.updated_at = datetime.now(UTC)

    def update_content(self, content: str) -> None:
        """Update content and recompute derived metrics.

        The model validator only runs on ``__init__``, not attribute mutation,
        so we recompute manually here.
        """
        if self.kind == "directory":
            msg = f"Cannot set content on a directory: {self.path}"
            raise ValueError(msg)
        self.content = content
        self.version_diff = None
        self.content_hash, self.size_bytes, self.lines = self._content_metadata(content)
        self.lexical_tokens = self._lexical_token_count(content)
        self.updated_at = datetime.now(UTC)

    # --- Validator ----------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _normalize_and_derive(cls, data: dict[str, object]) -> dict[str, object]:
        """Normalize path, derive parent_path, infer kind, compute metrics."""
        raw_path = data.get("path")
        if not isinstance(raw_path, str):
            return data

        path = normalize_path(raw_path)
        inferred_kind = data.get("kind") or parse_kind(path)

        # Validate and normalize path
        valid, err = validate_path(raw_path)
        if not valid:
            allows_long_metadata_path = (
                err == "Path too long (max 4096 characters)"
                and (
                    inferred_kind in {"chunk", "version", "edge", "api"}
                    or (inferred_kind == "directory" and is_meta_root_path(path))
                )
                and len(path) <= 8192
            )
            if allows_long_metadata_path:
                valid = True
            else:
                msg = f"Invalid path {raw_path!r}: {err}"
                raise ValueError(msg)
        data["path"] = path

        # Derive name and parent_path from path
        if not data.get("name"):
            data["name"] = split_path(path)[1]
        if not data.get("parent_path"):
            data["parent_path"] = compute_parent_path(path)

        # Infer kind from path markers if not explicitly set
        if not data.get("kind"):
            data["kind"] = inferred_kind
        elif data["kind"] not in {"file", "directory", "chunk", "version", "edge", "api"}:
            msg = f"Unknown kind: {data['kind']!r}"
            raise ValueError(msg)

        # Derive extension from path for fast type-scoped queries (files only).
        # Chunks, versions, edges, apis, and directories leave ext NULL
        # so the (ext, kind) index only covers file rows.  ``ValidatedSQLModel``
        # re-runs the validator with all field defaults populated, so presence
        # of "ext" in *data* is not a reliable signal — check for None instead.
        if data.get("ext") is None and data.get("kind") == "file":
            data["ext"] = extract_extension(path)

        # For edges, extract source/target/type from path.
        if data.get("kind") == "edge":
            parts = decompose_edge(path)
            if parts:
                if not data.get("source_path"):
                    data["source_path"] = parts.source
                if not data.get("edge_type"):
                    data["edge_type"] = parts.edge_type
                if not data.get("target_path"):
                    data["target_path"] = parts.target

        # Reject null bytes in stored text payloads — not valid in SQL text columns
        content = data.get("content")
        if isinstance(content, str) and "\x00" in content:
            msg = f"Content contains null bytes (path={data.get('path')!r})"
            raise ValueError(msg)
        version_diff = data.get("version_diff")
        if isinstance(version_diff, str) and "\x00" in version_diff:
            msg = f"version_diff contains null bytes (path={data.get('path')!r})"
            raise ValueError(msg)

        kind = data.get("kind")

        # Kind-specific content invariants
        if kind == "directory":
            data["content"] = None
            content = None
        elif kind == "file" and content is None:
            data["content"] = ""
            content = ""

        if kind == "version":
            payload_count = int(content is not None) + int(version_diff is not None)
            if payload_count > 1:
                msg = "Version rows must not set both content and version_diff"
                raise ValueError(msg)

        # Compute content metrics (empty string is valid content, distinct from None)
        explicit_version_metadata = kind == "version" and (
            data.get("content_hash") is not None or "size_bytes" in data or "lines" in data
        )
        if not explicit_version_metadata and isinstance(content, str):
            content_hash, size_bytes, lines = cls._content_metadata(content)
            data["content_hash"] = content_hash
            data["size_bytes"] = size_bytes
            data["lines"] = lines

        if isinstance(content, str):
            data["lexical_tokens"] = cls._lexical_token_count(content)

        # Ensure timestamps
        now = datetime.now(UTC)
        if not data.get("created_at"):
            data["created_at"] = now
        if not data.get("updated_at"):
            data["updated_at"] = now

        return data


class VFSObject(VFSObjectBase, table=True):
    """Default concrete table — ``vfs_objects``."""

    __tablename__ = "vfs_objects"
    __table_args__ = (Index("ix_vfs_objects_ext_kind", "ext", "kind"),)


_POSTGRES_NATIVE_MODEL_CACHE: dict[tuple[int, str | None, str, str], type[VFSObjectBase]] = {}


def resolve_embedding_vector_type(model: type[VFSObjectBase]) -> VectorType:
    """Return the model-declared ``VectorType`` for ``embedding``."""
    table = getattr(model, "__table__", None)
    if table is None or "embedding" not in table.c:
        msg = f"Model {model.__name__} does not declare an 'embedding' column"
        raise ValueError(msg)
    vector_type = table.c.embedding.type
    if not isinstance(vector_type, VectorType):
        msg = f"Model {model.__name__}.embedding must use VectorType"
        raise ValueError(msg)
    return vector_type


def postgres_vector_column_spec(model: type[VFSObjectBase]) -> PostgresVectorColumnSpec:
    """Return the native Postgres vector-index contract declared on *model*."""
    vector_type = resolve_embedding_vector_type(model)
    if not vector_type.postgres_native or vector_type.dimension is None:
        msg = (
            f"Model {model.__name__}.embedding must be declared with "
            "VectorType(dimension=<N>, postgres_native=True) for native Postgres vector search"
        )
        raise ValueError(msg)

    table_name = str(model.__tablename__)
    column_name = "embedding"
    metric = vector_type.postgres_operator_class.removesuffix("_ops")
    index_name = f"ix_{table_name}_{column_name}_{metric}_{vector_type.postgres_index_method}"
    return PostgresVectorColumnSpec(
        column_name=column_name,
        dimension=vector_type.dimension,
        index_method=vector_type.postgres_index_method,
        operator_class=vector_type.postgres_operator_class,
        index_name=index_name,
    )


def postgres_native_vfs_object_model(
    *,
    dimension: int,
    model_name: str | None = None,
    index_method: str = "hnsw",
    operator_class: str = "vector_cosine_ops",
) -> type[VFSObjectBase]:
    """Build or reuse a ``VFSObject`` table model with native pgvector embedding."""
    key = (dimension, model_name, index_method, operator_class)
    cached = _POSTGRES_NATIVE_MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    def _class_token(value: str) -> str:
        return "".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)

    class_name = f"PostgresNativeVFSObject{dimension}{_class_token(index_method)}{_class_token(operator_class)}"
    if model_name:
        class_name += _class_token(model_name)
    embedding_sa_type = cast(
        "Any",
        VectorType(
            dimension=dimension,
            model_name=model_name,
            postgres_native=True,
            postgres_index_method=index_method,
            postgres_operator_class=operator_class,
        ),
    )
    attrs: dict[str, object] = {
        "__module__": __name__,
        "__tablename__": "vfs_objects",
        "__table_args__": (Index("ix_vfs_objects_ext_kind", "ext", "kind"),),
        "metadata": MetaData(),
        "__annotations__": {"embedding": Vector | None},
        "embedding": Field(
            default=None,
            sa_type=embedding_sa_type,
        ),
    }
    postgres_native_model = cast(
        "type[VFSObjectBase]",
        SQLModelMetaclass(class_name, (VFSObjectBase,), attrs, table=True),
    )
    _POSTGRES_NATIVE_MODEL_CACHE[key] = postgres_native_model
    return postgres_native_model
