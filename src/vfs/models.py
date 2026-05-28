"""VFSEntry — unified kinded record for namespace rows.

All entities in the VFS namespace (files, directories, chunks, versions,
edges, api nodes) share a single record shape. The ``kind`` column
determines which nullable fields are relevant and how operations dispatch.

``VFSEntry`` itself is ``table=False``. Each filesystem instance mints its
own ``table=True`` subclass at construction time via
:func:`_build_entry_table_class`, scoped to the mount's ``table_name``,
``schema``, and — on Postgres — ``NativeEmbeddingConfig``.
"""

from __future__ import annotations

import copy as _copy_mod
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, cast

from pydantic import PrivateAttr, model_validator
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
)
from sqlalchemy.orm import InstanceState
from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelMetaclass

from vfs.bm25 import tokenize as lexical_tokenize
from vfs.code_grams import GRAM_SIZE, normalize_content
from vfs.chunking import (
    grammar_for_extension,
    NOTEBOOK_EXTENSION,
    split_code,
    split_notebook,
    split_with_line_ranges,
)
from vfs.paths import (
    base_path,
    chunk_path,
    decompose_edge,
    extract_extension,
    normalize_path,
    parse_kind,
    split_path,
    validate_path,
    version_path,
)
from vfs.paths import (
    parent_path as compute_parent_path,
)
from vfs.results import Candidate
from vfs.vector import NativeEmbeddingConfig, Vector, VectorType
from vfs.versioning import create_version as create_version_record
from vfs.versioning import reconstruct_version

# ---------------------------------------------------------------------------
# The unified object model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionWritePlan:
    """Decision-complete write plan for a file mutation."""

    version_rows: tuple[VFSEntry, ...]
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


class VFSEntry(SQLModel):
    """The full record of one object in the VFS namespace (Constitution §1.2).

    Every entity — file, directory, chunk, version, edge, api node —
    shares this record shape. The ``kind`` column determines which
    nullable fields are relevant and how operations dispatch.

    ``VFSEntry`` is ``table=False``: it carries fields, validators, and
    pure-data methods but is not itself directly writeable. Each
    filesystem mount mints a private ``table=True`` subclass via
    :func:`_build_entry_table_class` at construction time. Developers
    never subclass ``VFSEntry`` by hand.
    """

    _explicit_fields: frozenset[str] = PrivateAttr(default_factory=frozenset)

    def __init__(self, **data: object) -> None:
        explicit = frozenset(data)
        super().__init__(**data)
        self._explicit_fields = explicit

    # --- Identity -----------------------------------------------------------

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_type=BigInteger().with_variant(Integer, "sqlite"),  # ty: ignore[invalid-argument-type]
    )
    # Client-side ``uuid4`` entity identity.
    entry_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        max_length=36,
        unique=True,
        index=True,
    )
    path: str = Field(max_length=1024, unique=True, index=True)
    external_id: str | None = Field(default=None, max_length=1024)
    name: str = Field(default="", max_length=255)
    parent_path: str = Field(default="", max_length=1024, index=True)
    kind: str = Field(default="", max_length=32, index=True)

    # --- Content ------------------------------------------------------------

    content: str | None = Field(default=None)
    description: str | None = Field(default=None)
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

    # --- Search indexing ---------------------------------------------------

    index_content: bool = Field(default=False, index=True)
    indexed_content_hash: str | None = Field(default=None, max_length=64)

    # --- Version-specific ---------------------------------------------------

    version_number: int | None = Field(default=None)
    is_snapshot: bool | None = Field(default=None)
    created_by: str | None = Field(default=None, max_length=255)

    # --- Edge-specific ------------------------------------------------------

    source_path: str | None = Field(default=None, max_length=1024, index=True)
    target_path: str | None = Field(default=None, max_length=1024, index=True)
    edge_type: str | None = Field(default=None, max_length=255)
    edge_weight: float | None = Field(default=None)
    edge_distance: float | None = Field(default=None)

    # --- Embedding ----------------------------------------------------------

    embedding: Vector | None = Field(default=None, sa_type=VectorType())  # ty: ignore[invalid-argument-type]

    # --- Ownership ----------------------------------------------------------

    owner_id: str | None = Field(default=None, max_length=255, index=True)
    original_path: str | None = Field(default=None, max_length=1024)

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

    def clone(self) -> VFSEntry:
        """Create a detached copy with independent SQLAlchemy state.

        ``VFSEntry`` itself is ``table=False`` and has no SQLAlchemy
        instance manager — cloning a base entry skips the InstanceState
        wiring. Minted ``table=True`` subclasses get the full SA state.
        """
        c = _copy_mod.copy(self)
        class_manager = getattr(type(self), "_sa_class_manager", None)
        if class_manager is not None:
            c.__dict__["_sa_instance_state"] = InstanceState(c, class_manager)
        return c

    def _rederive_path_fields(self) -> None:
        """Normalize path and re-derive ``name``, ``parent_path``, and ``ext``."""
        self.path = normalize_path(self.path)
        self.name = split_path(self.path)[1]
        self.parent_path = compute_parent_path(self.path)
        self.ext = extract_extension(self.path) if self.kind == "file" else None

    def add_prefix(self, prefix: str) -> VFSEntry:
        """Prepend *prefix* to path in place, re-deriving name and parent."""
        if not prefix:
            return self
        prefix = normalize_path(prefix)
        self.path = prefix + self.path if self.path != "/" else prefix
        self._rederive_path_fields()
        return self

    def strip_prefix(self, prefix: str) -> VFSEntry:
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

    def to_candidate(
        self,
        *,
        score: float | None = None,
        include_content: bool = False,
    ) -> Candidate:
        """Project this object to an immutable ``Candidate``.

        Callers pass ``score`` for ranked results (vector/bm25/pagerank). By
        default ``content`` is omitted — set ``include_content=True`` for
        ``read`` / ``grep`` paths that genuinely need the text.
        """
        return Candidate(
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
    ) -> VFSEntry:
        """Construct a version row with explicit reconstructed-state metadata.

        Data is normalized by constructing a throwaway :class:`VFSEntry`
        (which runs the field validator), then re-materialized via
        ``cls`` so callers on a minted ``table=True`` subclass get a
        SQLAlchemy-mappable instance while still benefitting from
        ``VFSEntry`` validation.
        """
        content_hash, size_bytes, lines = cls._content_metadata(version_content)
        record = create_version_record(
            prev_content=prev_content,
            version_content=version_content,
            version_number=version_number,
            force_snapshot=force_snapshot,
        )
        now = datetime.now(UTC)
        entry = VFSEntry(
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
        if cls is VFSEntry:
            return entry
        return cls(**entry.model_dump())

    @classmethod
    def _reconstruct_file_version(
        cls,
        version_rows: list[VFSEntry],
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

    def set_version(self, version_number: int) -> None:
        """Set this entry's version, rebuilding its path when the path embeds it.

        ``file`` tracks its current version in ``version_number`` only — its
        path has no version segment. ``version`` (``.../versions/<N>``) and
        ``chunk`` (``.../chunks/<N>/<name>``) carry the version in the path, so
        it is rebuilt.
        """
        if self.kind not in {"file", "version", "chunk"}:
            msg = f"set_version applies only to files, versions, and chunks: kind={self.kind!r}"
            raise ValueError(msg)
        self.version_number = version_number
        if self.kind == "version":
            self.path = version_path(base_path(self.path), version_number)
            self._rederive_path_fields()
        elif self.kind == "chunk":
            name = split_path(self.path)[1]
            self.path = chunk_path(base_path(self.path), name, version_number)
            self._rederive_path_fields()

    def plan_file_write(
        self,
        new_content: str,
        version_rows: list[VFSEntry] | None = None,
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
        planned_rows: list[VFSEntry] = []
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

    # --- Chunking -----------------------------------------------------------

    @staticmethod
    def split_content(content: str, ext: str | None) -> list[tuple[str, int, int]]:
        """Return ``(chunk_text, line_start, line_end)`` tuples for *content*.

        Dispatches on the file extension *ext* (no leading dot): notebooks use
        ``split_notebook``, extensions with a tree-sitter grammar use
        structure-aware ``split_code``, and everything else falls back to the
        recursive separator splitter. Override on a subclass to plug in custom
        chunking. Empty list signals "no split required."
        """
        if ext == NOTEBOOK_EXTENSION:
            return split_notebook(content)
        if grammar := grammar_for_extension(ext):
            return split_code(content, language=grammar)
        return split_with_line_ranges(content)

    def chunk(self) -> list[VFSEntry]:
        """Split this file's content into chunk entries.

        Every indexable document is chunked: content of at least ``GRAM_SIZE``
        bytes always yields at least one ``kind="chunk"`` row (a whole-file
        chunk when it fits in one), and ``self.index_content`` flips to
        ``False`` so only the chunk rows feed content-side indexes. Content
        under ``GRAM_SIZE`` bytes can form no trigram, so it produces no chunk
        and is left unindexed (``index_content=False``). Path naming is
        ``<line_start>_<line_end>`` with an ``@<char_offset>`` suffix only when
        chunks would otherwise collide on identical line ranges (e.g. a single
        oversized line producing multiple chunks).
        """
        if self.kind != "file":
            msg = f"chunk() applies only to files: kind={self.kind!r}"
            raise ValueError(msg)
        content = self.content or ""
        pieces = self.split_content(content, self.ext)
        if not pieces:
            return []

        # Detect duplicate (line_start, line_end) ranges; only those need an
        # @<offset> disambiguator. The content.find walk is skipped for
        # uniquely-keyed pieces (the common case).
        range_counts: dict[tuple[int, int], int] = {}
        for _text, ls, le in pieces:
            key = (ls, le)
            range_counts[key] = range_counts.get(key, 0) + 1

        version = self.version_number or 1
        new_chunks: list[VFSEntry] = []
        cursor = 0
        cls = type(self)
        for text, line_start, line_end in pieces:
            name = f"{line_start}_{line_end}"
            if range_counts[(line_start, line_end)] > 1:
                offset = content.find(text, cursor)
                if offset == -1:
                    offset = cursor
                cursor = offset + 1
                name = f"{name}@{offset}"
            # Run the Pydantic validator via base ``VFSEntry`` first so the
            # chunk row gets ``content_hash``, ``size_bytes``, ``lines``,
            # ``lexical_tokens``, and the chunk-default ``index_content=True``.
            # SQLModel ``table=True`` constructors bypass validators, so
            # going straight through ``cls(...)`` would leave those fields at
            # their zero defaults.
            validated = VFSEntry(
                path=chunk_path(self.path, name, version),
                kind="chunk",
                content=text,
                line_start=line_start,
                line_end=line_end,
                version_number=version,
                owner_id=self.owner_id,
            )

            if cls is VFSEntry:
                new_chunks.append(validated)

            else:
                row = cls(**validated.model_dump())
                row._explicit_fields = validated._explicit_fields
                new_chunks.append(row)

        self.index_content = False
        return new_chunks

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

        if "index_content" not in data:
            data["index_content"] = kind in {"file", "chunk"}

        # Ensure timestamps
        now = datetime.now(UTC)
        if not data.get("created_at"):
            data["created_at"] = now
        if not data.get("updated_at"):
            data["updated_at"] = now

        return data


def resolve_embedding_vector_type(model: type[VFSEntry]) -> VectorType:
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


def postgres_vector_column_spec(model: type[VFSEntry]) -> PostgresVectorColumnSpec:
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


# --- Code-gram index codes ------------------------------------------------
#
# The gram tables are plain Core tables — internal index machinery, never
# constructed through Pydantic — so their enumerated codes live as
# module-level constants rather than class attributes.

# Staging delta-log action.
GRAM_ACTION_DELETE: Final = 0
GRAM_ACTION_ADD: Final = 1

# Posting-list encoding tag. v1 writes only ``delta+gamma``; the per-row tag
# lets the format evolve per gram without a migration (``delta+varint`` is a
# reserved debug fallback, ``roaring`` the reserved query-path encoding).
ENCODING_DELTA_VARINT: Final = 1
ENCODING_DELTA_GAMMA: Final = 2
ENCODING_ROARING: Final = 3


def _build_vfs_tables(
    *,
    table_name: str,
    schema: str | None = None,
    native_embedding: NativeEmbeddingConfig | None = None,
    name: str | None = None,
) -> tuple[type[VFSEntry], Table, Table]:
    """Build a mount's entry model and its two gram-index tables in memory.

    Constructs the schema objects only; issues no DDL. Returns
    ``(entry_model, gram_staging_table, posting_list_table)``. The entry model
    is a private ``table=True`` subclass of :class:`VFSEntry` with its own
    :class:`MetaData`; the two gram tables bind to that same ``MetaData`` so a
    single ``create_all`` provisions all three. The minted class is given a
    unique name (``name`` when supplied, plus a random token) so two mounts
    never collide in SQLAlchemy's declarative registry. The SQLite entry PK is
    ``AUTOINCREMENT`` so a deleted top rowid is never reused — the posting-list
    ``doc_id`` must stay stable. All three are implementation details of the
    calling filesystem and MUST NOT leak onto the public surface.
    """
    # --- entry table -------------------------------------------------------
    table_kwargs: dict[str, object] = {"sqlite_autoincrement": True}
    if schema is not None:
        table_kwargs["schema"] = schema
    attrs: dict[str, object] = {
        "__module__": __name__,
        "__tablename__": table_name,
        "__table_args__": (
            Index(f"ix_{table_name}_ext_kind", "ext", "kind"),
            table_kwargs,
        ),
        "metadata": MetaData(),
    }
    if native_embedding is not None:
        embedding_sa_type = cast(
            "Any",
            VectorType(
                dimension=native_embedding.dimension,
                model_name=native_embedding.model_name,
                postgres_native=True,
                postgres_index_method=native_embedding.index_method,
                postgres_operator_class=native_embedding.operator_class,
            ),
        )
        attrs["__annotations__"] = {"embedding": Vector | None}
        attrs["embedding"] = Field(default=None, sa_type=embedding_sa_type)
    label = "".join(c if c.isalnum() else "_" for c in name) if name else "VFSEntryTable"
    class_name = f"{label}_{uuid.uuid4().hex[:5]}"
    entry_model = cast(
        "type[VFSEntry]",
        SQLModelMetaclass(class_name, (VFSEntry,), attrs, table=True),
    )
    metadata = entry_model.metadata

    # --- staging delta-log -------------------------------------------------
    # One append-only row per ``(gram_key, entry_id, action)`` change to an
    # indexed chunk; the fold keys on ``(gram_key, entry_id)`` by latest action
    # using the monotonic ``seq``. ``doc_id`` is null on adds (resolved by the
    # ``entry_id``→``id`` join at flush) and carries the captured id on deletes.
    # Indexes mirror the read fold and the cascade delete.
    grams_name = f"{table_name}_grams_staging"
    gram_staging_table = Table(
        grams_name,
        metadata,
        Column("seq", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
        Column("gram_key", Integer, nullable=False),
        Column("entry_id", String(36), nullable=False),
        Column("doc_id", BigInteger().with_variant(Integer, "sqlite")),
        Column("action", SmallInteger, nullable=False),
        Index(f"ix_{grams_name}_gram_entry_seq", "gram_key", "entry_id", "seq"),
        Index(f"ix_{grams_name}_entry_id", "entry_id"),
        schema=schema,
    )

    # --- durable posting list ----------------------------------------------
    # One row per gram: ``postings`` holds the gram's full sorted ``doc_id`` set
    # (``encoding`` names the packing; v1 writes ``delta+gamma`` only),
    # ``doc_count == len(decode(postings))``, and ``byte_size == len(postings)``
    # (storage view + hot-gram trigger). A gram with zero docs has no row.
    postings_name = f"{table_name}_grams_posting_list"
    posting_list_table = Table(
        postings_name,
        metadata,
        Column("gram_key", Integer, primary_key=True, autoincrement=False),
        Column("postings", LargeBinary, nullable=False),
        Column("encoding", SmallInteger, nullable=False, default=ENCODING_DELTA_GAMMA),
        Column("doc_count", Integer, nullable=False),
        Column("byte_size", Integer, nullable=False),
        schema=schema,
    )

    return entry_model, gram_staging_table, posting_list_table
