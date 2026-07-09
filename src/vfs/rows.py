"""Hand-written SQLAlchemy Core row definitions for a mount's storage.

This module is the persistence half of the domain/persistence split: the
columns, lengths, indexes, and id backbone of what a mount actually stores.
The tables are written by hand and never derived from :class:`vfs.models.Entry`
— this module does not import it. The two artifacts are held in lockstep by a
drift test instead, so a schema change is always a deliberate edit here, never
a side effect of touching the domain model.

:func:`build_vfs_tables` mints one mount's tables — the entry table plus the
two gram-index tables — on a fresh :class:`MetaData`, so a single
``create_all`` provisions all three and two mounts never share schema objects.
Only the repository layer should ever touch these tables; rows never escape it.

The entry table carries columns the domain model does not
(:data:`ENTRY_ROW_ONLY_COLUMNS`): the ``id`` backbone and the relationship
columns (``parent_dir``, ``parent_file``, ``source_path``, ``target_path``),
which the repository populates from the entry's path projections.
"""

from __future__ import annotations

from typing import Final, NamedTuple, TypedDict

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Table,
)

from vfs.paths import MAX_PATH_LENGTH, MAX_SEGMENT_LENGTH
from vfs.vector import NativeEmbeddingConfig, VectorType

# Entry-table columns with no counterpart field on the domain model: the id
# backbone plus the relationship columns the repository derives from ``path``.
ENTRY_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"id", "parent_dir", "parent_file", "source_path", "target_path"},
)

# --- Code-gram index codes --------------------------------------------------

# Staging delta-log action.
GRAM_ACTION_DELETE: Final = 0
GRAM_ACTION_ADD: Final = 1

# Posting-list encoding tag. v1 writes only ``delta+gamma``; the per-row tag
# lets the format evolve per gram without a migration (``delta+varint`` is a
# reserved debug fallback, ``roaring`` the reserved query-path encoding).
ENCODING_DELTA_VARINT: Final = 1
ENCODING_DELTA_GAMMA: Final = 2
ENCODING_ROARING: Final = 3


class GramStagingRow(TypedDict):
    """One insertable row of the ``*_grams_staging`` delta-log.

    Mirrors the staging table built in :func:`build_vfs_tables`, minus its
    server-assigned ``seq`` primary key. ``doc_id`` is null on adds (resolved
    by the ``entry_id``→``id`` join at flush) and carries the captured id on
    deletes.
    """

    gram_key: int
    entry_id: str
    doc_id: int | None
    action: int


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------


class VFSTables(NamedTuple):
    """One mount's schema objects, all bound to the same ``metadata``."""

    metadata: MetaData
    entry: Table
    gram_staging: Table
    posting_list: Table


def build_vfs_tables(
    *,
    table_name: str,
    schema: str | None = None,
    native_embedding: NativeEmbeddingConfig | None = None,
) -> VFSTables:
    """Build one mount's entry table and its two gram-index tables in memory.

    Constructs the schema objects only; issues no DDL. All three tables bind
    to one fresh :class:`MetaData` so a single ``create_all`` provisions them.
    The SQLite entry PK is ``AUTOINCREMENT`` so a deleted top rowid is never
    reused — the posting-list ``doc_id`` must stay stable.
    """
    metadata = MetaData()

    embedding_type = (
        VectorType(
            dimension=native_embedding.dimension,
            model_name=native_embedding.model_name,
            postgres_native=True,
            postgres_index_method=native_embedding.index_method,
            postgres_operator_class=native_embedding.operator_class,
        )
        if native_embedding is not None
        else VectorType()
    )

    entry = Table(
        table_name,
        metadata,
        # Identity. ``parent_dir``/``parent_file`` are the repository-derived
        # relationship columns (id references arrive in a later phase).
        Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
        Column("external_id", String(1024)),
        Column("path", String(MAX_PATH_LENGTH), nullable=False, unique=True, index=True),
        Column("name", String(MAX_SEGMENT_LENGTH), nullable=False),
        Column("kind", String(32), nullable=False, index=True),
        Column("parent_dir", String(MAX_PATH_LENGTH), nullable=False, index=True),
        Column("parent_file", String(MAX_PATH_LENGTH), index=True),
        # Content. Unbounded text columns take no length: VARCHAR on
        # SQLite/Postgres, VARCHAR(max) on MSSQL.
        Column("content", String()),
        Column("description", String()),
        Column("version_diff", String()),
        Column("content_hash", String(64)),
        Column("mime_type", String(MAX_SEGMENT_LENGTH)),
        Column("ext", String(32), index=True),
        # Metrics.
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        # Chunk-specific.
        Column("line_start", Integer),
        Column("line_end", Integer),
        # Search indexing.
        Column("chunked", Boolean, nullable=False, default=False, index=True),
        Column("encoded", Boolean, nullable=False, default=False, index=True),
        # Version-specific.
        Column("version_number", Integer),
        Column("is_snapshot", Boolean),
        Column("created_by", String(255)),
        # Edge-specific. ``source_path``/``target_path`` are repository-derived
        # like the parent columns above.
        Column("source_path", String(MAX_PATH_LENGTH), index=True),
        Column("target_path", String(MAX_PATH_LENGTH), index=True),
        Column("edge_type", String(MAX_SEGMENT_LENGTH)),
        Column("edge_weight", Float),
        Column("edge_distance", Float),
        # Embedding.
        Column("embedding", embedding_type),
        # Ownership.
        Column("owner_id", String(255), index=True),
        Column("original_path", String(MAX_PATH_LENGTH)),
        # Timestamps.
        Column("created_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        Column("deleted_at", DateTime(timezone=True)),
        Index(f"ix_{table_name}_ext_kind", "ext", "kind"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Staging delta-log: one append-only row per ``(gram_key, entry_id,
    # action)`` change to an indexed chunk; the fold keys on ``(gram_key,
    # entry_id)`` by latest action using the monotonic ``seq``. Indexes mirror
    # the read fold and the cascade delete.
    grams_name = f"{table_name}_grams_staging"
    gram_staging = Table(
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

    # Durable posting list: one row per gram. ``postings`` holds the gram's
    # full sorted ``doc_id`` set (``encoding`` names the packing; v1 writes
    # ``delta+gamma`` only), ``doc_count == len(decode(postings))``, and
    # ``byte_size == len(postings)`` (storage view + hot-gram trigger). A gram
    # with zero docs has no row.
    postings_name = f"{table_name}_grams_posting_list"
    posting_list = Table(
        postings_name,
        metadata,
        Column("gram_key", Integer, primary_key=True, autoincrement=False),
        Column("postings", LargeBinary, nullable=False),
        Column("encoding", SmallInteger, nullable=False, default=ENCODING_DELTA_GAMMA),
        Column("doc_count", Integer, nullable=False),
        Column("byte_size", Integer, nullable=False),
        schema=schema,
    )

    return VFSTables(metadata=metadata, entry=entry, gram_staging=gram_staging, posting_list=posting_list)
