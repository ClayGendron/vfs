"""Hand-written SQLAlchemy Core row definitions for a mount's storage.

This module is the persistence half of the domain/persistence split: the
columns, lengths, indexes, and id backbone of what a mount actually stores.
The tables are written by hand and never derived from :class:`vfs.models.Entry`
— this module does not import it. The two artifacts are held in lockstep by a
drift test instead, so a schema change is always a deliberate edit here, never
a side effect of touching the domain model.

Identity is stable, never location-derived (decision record 004): ``node_id``
(ULID) is the permanent logical identity; every table keeps an integer
surrogate key for compact row references, and every dependent table — content,
versions, chunks, edges, postings — keys on the integer, never the ULID and
never the path. ``parent_id`` is the one structural pointer; ``path`` survives
as a regenerable cache (unique, binary-collated) that nothing references.

:func:`build_vfs_tables` mints one mount's tables on a fresh
:class:`MetaData`, so a single ``create_all`` provisions them all and two
mounts never share schema objects. Only the storage backend should ever touch
these tables; rows never escape it.

Entry fields live across the family: the narrow ``entries`` row carries
identity and metadata (never bodies), and :data:`ENTRY_FIELD_HOMES` maps each
remaining domain field to its home table. Binary collation is pinned in DDL on
path/name key columns — a pagination-correctness and LIKE-sargability
prerequisite, not an ordering nicety.
"""

from __future__ import annotations

from typing import Final, NamedTuple

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
    UniqueConstraint,
)

from vfs.models.vector import NativeEmbeddingConfig, VectorType
from vfs.paths import MAX_PATH_LENGTH, MAX_SEGMENT_LENGTH

# Entries-table columns with no counterpart field on the domain model: the id
# backbone plus the identity-based restore metadata (never paths — a trashed
# entry restores by parent identity, immune to ancestor renames).
ENTRY_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"id", "node_id", "parent_id", "original_parent_id", "original_name"},
)

# Where each Entry field that is NOT an entries-table column lives:
# field name -> (VFSTables attribute, column name). Bodies and per-kind
# payloads leave the narrow entries row so metadata writes never rewrite
# content. The drift test walks this mapping.
ENTRY_FIELD_HOMES: Final[dict[str, tuple[str, str]]] = {
    "content": ("content", "content"),
    "version_diff": ("versions", "version_diff"),
    "is_snapshot": ("versions", "is_snapshot"),
    "created_by": ("versions", "created_by"),
    "line_start": ("chunks", "line_start"),
    "line_end": ("chunks", "line_end"),
    "embedding": ("chunks", "embedding"),
    "edge_type": ("edges", "edge_type"),
    "edge_weight": ("edges", "weight"),
    "edge_distance": ("edges", "distance"),
}

# First-touch writes this into the meta row; every later first touch compares
# and refuses loudly on mismatch — never PRAGMA/catalog sniffing.
SCHEMA_FORMAT_VERSION: Final = 1

# ULIDs render as 26 Crockford-base32 characters.
ULID_LENGTH: Final = 26

# Postgres caps identifiers at 63 chars; the longest derived name adds 22
# ("uq_" + "_chunks_entry_index"), so 63 - 22. A tightness test pins the math.
MAX_TABLE_NAME_LENGTH: Final = 41

# Posting-list encoding tag. v1 writes ``delta+varint`` only; the per-row tag
# lets the format evolve per gram without a migration (``roaring`` is the
# reserved density-tier upgrade; tag 2 — the dropped delta+gamma — is retired,
# never reused).
ENCODING_DELTA_VARINT: Final = 1
ENCODING_ROARING: Final = 3


def _binary_string(length: int) -> String:
    """A VARCHAR whose comparison/order is bytewise on every engine.

    SQLite's default BINARY collation already is; Postgres and MSSQL need
    the collation pinned in DDL or pagination order and LIKE sargability
    silently diverge per engine. MSSQL uses the UTF-8 binary collation
    (SQL Server 2019+ floor): its byte order equals UTF-8/code-point order
    on every engine, where NVARCHAR ``_BIN2`` would sort by UTF-16 code
    unit (diverging on supplementary-plane characters) and would double
    the byte budget past the 1,700-byte index-key cap even for ASCII
    paths at full length.
    """
    return (
        String(length)
        .with_variant(String(length, collation="C"), "postgresql")
        .with_variant(String(length, collation="Latin1_General_100_BIN2_UTF8"), "mssql")
    )


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------


class VFSTables(NamedTuple):
    """One mount's schema objects, all bound to the same ``metadata``."""

    metadata: MetaData
    entry: Table
    content: Table
    versions: Table
    chunks: Table
    edges: Table
    meta: Table
    gram_epochs: Table
    posting_list: Table


def build_vfs_tables(
    *,
    table_name: str,
    schema: str | None = None,
    native_embedding: NativeEmbeddingConfig | None = None,
) -> VFSTables:
    """Build one mount's table family in memory.

    Constructs the schema objects only; issues no DDL. Every table binds to
    one fresh :class:`MetaData` so a single ``create_all`` provisions them.
    Integer PKs that feed posting-list ``doc_id`` values are SQLite
    ``AUTOINCREMENT`` so a deleted top rowid is never reused.

    Refuses a ``table_name`` over :data:`MAX_TABLE_NAME_LENGTH`: derived
    constraint names must fit Postgres's 63-char identifier cap on every
    engine, not fail on the first engine that enforces it.
    """
    if len(table_name) > MAX_TABLE_NAME_LENGTH:
        raise ValueError(
            f"table_name exceeds {MAX_TABLE_NAME_LENGTH} characters "
            f"({len(table_name)}): derived identifiers would overflow "
            f"Postgres's 63-char cap: {table_name!r}"
        )
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

    # The narrow entries row: identity, kind, metadata, restore metadata —
    # never bodies, so a metadata write never rewrites content. The
    # UNIQUE(parent_id, name) index arbitrates concurrent creates and serves
    # keyset pagination; ``path`` is the regenerable cache nothing references.
    entry = Table(
        table_name,
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
        Column("node_id", String(ULID_LENGTH), nullable=False, unique=True, index=True),
        Column("parent_id", BigInteger, index=True),
        Column("external_id", String(1024)),
        Column("path", _binary_string(MAX_PATH_LENGTH), nullable=False, unique=True, index=True),
        Column("name", _binary_string(MAX_SEGMENT_LENGTH), nullable=False),
        Column("kind", String(32), nullable=False, index=True),
        Column("revision", BigInteger),
        Column("content_hash", String(64)),
        Column("mime_type", String(MAX_SEGMENT_LENGTH)),
        Column("ext", String(32), index=True),
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        Column("chunked", Boolean, nullable=False, default=False, index=True),
        Column("encoded", Boolean, nullable=False, default=False, index=True),
        Column("version_number", Integer),
        Column("owner_id", String(255), index=True),
        Column("original_parent_id", BigInteger),
        Column("original_name", _binary_string(MAX_SEGMENT_LENGTH)),
        Column("created_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        Column("deleted_at", DateTime(timezone=True)),
        UniqueConstraint("parent_id", "name", name=f"uq_{table_name}_parent_name"),
        Index(f"ix_{table_name}_ext_kind", "ext", "kind"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Current content, one body per row, keyed by the entries integer id.
    # The body column is physically last: width changes to earlier columns
    # never rewrite the blob's pages.
    content = Table(
        f"{table_name}_content",
        metadata,
        Column("entry_id", BigInteger, primary_key=True, autoincrement=False),
        Column("content", String(), nullable=False),
        schema=schema,
    )

    # Version history. The write path stores full snapshots
    # (``is_snapshot=True``, body in ``content``); the batch pack verb
    # rewrites cold ranges into snapshot-every-N + forward diffs
    # (``version_diff``). Bodies last, metadata first.
    versions = Table(
        f"{table_name}_versions",
        metadata,
        Column("entry_id", BigInteger, primary_key=True, autoincrement=False),
        Column("version_number", Integer, primary_key=True, autoincrement=False),
        Column("is_snapshot", Boolean, nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        Column("created_by", String(255)),
        Column("created_at", DateTime(timezone=True)),
        Column("content", String()),
        Column("version_diff", String()),
        schema=schema,
    )

    # Chunks: the indexed/embedded unit, keyed by entry identity — never by
    # path (a rename rewrites zero chunk rows). The integer PK feeds posting
    # doc_ids, hence AUTOINCREMENT.
    chunks = Table(
        f"{table_name}_chunks",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
        Column("entry_id", BigInteger, nullable=False, index=True),
        Column("chunk_index", Integer, nullable=False),
        Column("line_start", Integer, nullable=False),
        Column("line_end", Integer, nullable=False),
        Column("content_hash", String(64)),
        Column("embedding", embedding_type),
        Column("content", String(), nullable=False),
        UniqueConstraint("entry_id", "chunk_index", name=f"uq_{table_name}_chunks_entry_index"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Edges: narrow ID triples with both traversal directions indexed. No
    # path columns — liveness and addressing come from joining entries.
    edges = Table(
        f"{table_name}_edges",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
        Column("source_id", BigInteger, nullable=False),
        Column("target_id", BigInteger, nullable=False),
        Column("edge_type", String(MAX_SEGMENT_LENGTH), nullable=False),
        Column("weight", Float),
        Column("distance", Float),
        UniqueConstraint("source_id", "target_id", "edge_type", name=f"uq_{table_name}_edges_src_tgt_type"),
        Index(f"ix_{table_name}_edges_fwd", "source_id", "edge_type"),
        Index(f"ix_{table_name}_edges_rev", "target_id", "edge_type"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Single-row mount metadata: the schema-format version first touch
    # verifies, the durable mount identity that keys the per-mount advisory
    # lock, and the current-epoch pointer whose one-row flip publishes a
    # rebuilt gram index atomically.
    meta = Table(
        f"{table_name}_meta",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("schema_format_version", Integer, nullable=False),
        Column("mount_identity", String(ULID_LENGTH), nullable=False),
        Column("current_gram_epoch", Integer),
        Column("created_at", DateTime(timezone=True)),
        CheckConstraint("id = 1", name=f"ck_{table_name}_meta_single_row"),
        schema=schema,
    )

    # One row per gram-index build: the three-part fingerprint (format
    # version, options hash, max-revision watermark). Rows outside the
    # current epoch are reclaimable garbage, swept by the reindex verb.
    gram_epochs = Table(
        f"{table_name}_gram_epochs",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("format_version", Integer, nullable=False),
        Column("options_hash", String(64), nullable=False),
        Column("watermark", BigInteger, nullable=False),
        Column("created_at", DateTime(timezone=True)),
        schema=schema,
    )

    # Durable posting list, epoch-scoped: one row per (epoch, gram).
    # ``postings`` holds the gram's full sorted ``doc_id`` set (``encoding``
    # names the packing; v1 writes ``delta+varint``),
    # ``doc_count == len(decode(postings))``, and ``byte_size ==
    # len(postings)``. A gram with zero docs has no row.
    posting_list = Table(
        f"{table_name}_grams_posting_list",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("gram_key", Integer, primary_key=True, autoincrement=False),
        Column("postings", LargeBinary, nullable=False),
        Column("encoding", SmallInteger, nullable=False, default=ENCODING_DELTA_VARINT),
        Column("doc_count", Integer, nullable=False),
        Column("byte_size", Integer, nullable=False),
        schema=schema,
    )

    return VFSTables(
        metadata=metadata,
        entry=entry,
        content=content,
        versions=versions,
        chunks=chunks,
        edges=edges,
        meta=meta,
        gram_epochs=gram_epochs,
        posting_list=posting_list,
    )
