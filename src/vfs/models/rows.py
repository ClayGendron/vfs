"""Hand-written SQLAlchemy Core row definitions for a mount's storage.

This module is the persistence half of the domain/persistence split: the
columns, lengths, indexes, and id backbone of what a mount actually stores.
The tables are written by hand and never derived from :class:`vfs.models.Entry`
— this module does not import it. The two artifacts are held in lockstep by a
drift test instead, so a schema change is always a deliberate edit here, never
a side effect of touching the domain model.

Identity is stable, never location-derived: ``entry_id`` (ULID, stored
binary-16 via :class:`ULIDKey`) is the permanent
logical identity **and** the referential identity — every durable dependent
table (content, versions, chunks, edges) keys on it, and ``parent_id`` is the
one structural pointer, also an ``entry_id`` value. Each table keeps an
integer surrogate primary key as a local row locator that nothing durable
references; only regenerable stores (posting-list doc ids) may key on it —
the same doctrine that keeps ``path`` honest as a regenerable cache (unique,
binary-collated) that nothing references.

:func:`build_vfs_tables` mints one mount's tables on a fresh
:class:`MetaData`, so a single ``create_all`` provisions them all and two
mounts never share schema objects. Only the storage backend should ever touch
these tables; rows never escape it.

The domain models mirror the family one-to-one — ``Entry`` ↔ ``entries`` (+
``content`` for the body), ``Version`` ↔ ``versions``, ``Chunk`` ↔ ``chunks``,
``Edge`` ↔ ``edges`` — and the per-table constants below declare the columns
with no model field (the id backbone, restore metadata) and the model fields
with no column yet, so the drift test can pin each model to its own table.
Binary collation is pinned in DDL on path/name key columns — a
pagination-correctness and LIKE-sargability prerequisite, not an ordering
nicety.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Final, NamedTuple

from sqlalchemy import (
    BINARY,
    VARBINARY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.dialects.oracle import RAW
from ulid import ULID

from vfs.models.vector import NativeEmbeddingConfig, VectorType
from vfs.paths import MAX_PATH_LENGTH, MAX_SEGMENT_LENGTH

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect
    from sqlalchemy.sql import FromClause
    from sqlalchemy.types import TypeEngine

# Entries-table columns with no counterpart field on the domain model: the id
# backbone, the identity-based restore metadata (never paths — a trashed
# entry restores by parent identity, immune to ancestor renames), and the
# per-entry version — minted and guarded storage-side, reported on
# observations, never authored on an Entry.
ENTRY_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"id", "entry_id", "parent_id", "original_parent_id", "original_name", "version"}
    | {"chunked", "encoded", "indexable", "chunk_source_hash", "chunk_generation"},
)

# The Entry field homed in the content table rather than the entries row —
# bodies leave the narrow row so metadata writes never rewrite content.
ENTRY_CONTENT_FIELDS: Final[frozenset[str]] = frozenset({"content"})

# Per-model column exemptions for the metadata family: the id backbone plus
# the owner references, which the models carry as Path fields (below) and
# the persistence layer resolves to entry identities.
VERSION_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"entry_id"})
CHUNK_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"id", "entry_id"})
EDGE_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"id", "source_id", "target_id"})

# Owner-reference fields per model: the Path field standing in for the row's
# id reference. The drift test excuses these from column matching.
MODEL_OWNER_FIELDS: Final[dict[str, frozenset[str]]] = {
    "Version": frozenset({"file"}),
    "Chunk": frozenset({"file"}),
    "Edge": frozenset({"source", "target"}),
}

# Model fields with no backing column yet, and the spec that resolves each:
# Edge.version is the per-edge monotone value (ADR 013) awaiting the
# edge-wiring spec's column.
MODEL_FIELD_ONLY: Final[dict[str, frozenset[str]]] = {
    "Version": frozenset(),
    "Chunk": frozenset(),
    "Edge": frozenset({"version"}),
}

# Field-name → column-name divergences per model. ``Version.number`` keeps
# the self-describing ``version_number`` column (bare-SQL clarity, and NUMBER
# is an Oracle reserved word); unlisted fields share their column's name.
MODEL_COLUMN_RENAMES: Final[dict[str, dict[str, str]]] = {
    "Version": {"number": "version_number"},
    "Chunk": {},
    "Edge": {},
}

# First-touch writes this into the meta row; every later first touch compares
# and refuses loudly on mismatch — never PRAGMA/catalog sniffing.
SCHEMA_FORMAT_VERSION: Final = 6

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


# SQLAlchemy resolves type variants strictly by dialect name, and
# MariaDB's is "mariadb" — every mysql-family branch must name both.
_MYSQL_FAMILY: Final = ("mysql", "mariadb")

# MSSQL's byte-wise UTF-8 collation (SQL Server 2019+ floor): VARCHAR n
# counts bytes, and non-Latin1 survives the database codepage.
_MSSQL_UTF8_BIN2: Final = "Latin1_General_100_BIN2_UTF8"


def _string(length: int) -> String:
    """A general string column that stores non-Latin1 losslessly everywhere.

    A plain ``String`` on MSSQL compiles with the *database's* default
    collation — commonly CP-1252 — which squeezes any non-Latin1 value
    to ``?`` at conversion time; the UTF-8 collation variant closes that
    on the column side (the bind side is the engine's
    ``use_setinputsizes=False``).
    """
    return String(length).with_variant(String(length, collation=_MSSQL_UTF8_BIN2), "mssql")


class BytewiseString(TypeDecorator[str]):
    """A bounded key string, bytewise-ordered and byte-budgeted where pinned.

    *length* denominates UTF-8 bytes — the same unit as the path
    contract and every engine's index-key cap, so a lawful value always
    fits the column and the column's worst-case key never outgrows an
    engine. SQLite's default BINARY collation is already bytewise;
    Postgres and MSSQL pin it in DDL, or pagination order and LIKE
    sargability silently diverge per engine. MSSQL uses the UTF-8 binary
    collation (SQL Server 2019+ floor), whose VARCHAR ``n`` counts bytes
    — NVARCHAR ``_BIN2`` would sort by UTF-16 code unit and double the
    byte budget past its 1,700-byte index-key cap. The mysql family gets
    ``VARBINARY(n)`` outright: utf8mb4 VARCHAR keys cost 4 bytes per
    declared char against InnoDB's 3,072-byte cap, while binary keys
    cost their own bytes and compare bytewise natively — Python still
    speaks ``str``; the conversion lives here alone.

    Oracle and unmeasured engines take the plain ``String`` fallback:
    character-denominated (``VARCHAR2(n CHAR)`` on Oracle) with no
    collation pin, so bytewise order and byte budgeting there rest on
    engine defaults (Oracle's ``NLS_SORT=BINARY``) — an accepted
    degradation, not a pinned contract.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int) -> None:
        super().__init__(length)
        self.length = length

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name in _MYSQL_FAMILY:
            return dialect.type_descriptor(VARBINARY(self.length))
        if dialect.name == "postgresql":
            return dialect.type_descriptor(String(self.length, collation="C"))
        if dialect.name == "mssql":
            return dialect.type_descriptor(String(self.length, collation=_MSSQL_UTF8_BIN2))
        return dialect.type_descriptor(String(self.length))

    def process_bind_param(self, value: str | None, dialect: Dialect) -> Any:
        if value is not None and dialect.name in _MYSQL_FAMILY:
            return value.encode()
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).decode()
        return value


def _body_text() -> Text:
    """An unbounded text body that provisions on every engine.

    Bare ``String()`` carries no length and MySQL's DDL compiler refuses
    it outright; ``Text`` maps to each engine's unbounded form (CLOB on
    Oracle, VARCHAR(max) on MSSQL), with the mysql family pinned to
    LONGTEXT — its bare TEXT caps bodies at 64KB. MSSQL pins the UTF-8
    collation: VARCHAR(max) under the database codepage mangles
    non-Latin1 bodies to ``?`` server-side.
    """
    return Text().with_variant(LONGTEXT(), *_MYSQL_FAMILY).with_variant(Text(collation=_MSSQL_UTF8_BIN2), "mssql")


def _uuid_native(dialect: Dialect) -> bool:
    """True where the engine's own uuid type keeps ULID time-order.

    An allow-list, not ``dialect.supports_native_uuid``: that flag means
    the driver binds uuid objects and says nothing about sort order —
    MSSQL's ``UNIQUEIDENTIFIER`` and MariaDB's byte-swapped native uuid
    both report support while forfeiting time-ordered index locality.
    """
    return dialect.name == "postgresql"


EntryId = Annotated[str, "26-char ULID naming one entry row; minted at write, joined on everywhere"]


class ULIDKey(TypeDecorator[str]):
    """A 128-bit identity column speaking 26-char ULID strings in Python.

    The one conversion home: every bound value and every fetched value
    crosses here, so no other module translates identity. Storage is
    binary-16 on every engine, never text: the native ``uuid`` type where
    the dialect binds one and its sort preserves time-order (Postgres),
    ``RAW(16)`` on Oracle, and fixed-width ``BINARY(16)`` everywhere
    else — including engines whose only uuid-shaped alternative would be
    the CHAR(32) hex fallback or a wrongly-sorted ``UNIQUEIDENTIFIER``.
    """

    impl = Uuid
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if _uuid_native(dialect):
            return dialect.type_descriptor(Uuid())
        if dialect.name == "oracle":
            return dialect.type_descriptor(RAW(16))
        return dialect.type_descriptor(BINARY(16))

    def process_bind_param(self, value: str | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        ulid = ULID.from_str(value)
        return ulid.to_uuid() if _uuid_native(dialect) else ulid.bytes

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if _uuid_native(dialect):
            return str(ULID.from_uuid(value))
        return str(ULID.from_bytes(value))


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
    segments: Table

    def content_joined(self) -> FromClause:
        """Entries LEFT-joined to content on ``entry_id`` — the one canonical join."""
        return self.entry.outerjoin(self.content, self.content.c.entry_id == self.entry.c.entry_id)


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
        # Identity() is explicit for Oracle, whose dialect generates
        # nothing for a bare autoincrement primary key.
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("entry_id", ULIDKey(), nullable=False, unique=True, index=True),
        Column("parent_id", ULIDKey()),
        Column("external_id", _string(1024)),
        Column("path", BytewiseString(MAX_PATH_LENGTH), nullable=False, unique=True, index=True),
        Column("name", BytewiseString(MAX_SEGMENT_LENGTH), nullable=False),
        Column("kind", String(32), nullable=False, index=True),
        Column("version", BigInteger),
        Column("content_hash", String(64)),
        Column("mime_type", _string(MAX_SEGMENT_LENGTH)),
        Column("ext", _string(32), index=True),
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        # Grep-overlay dirty flags: derived state reflects this content /
        # the current gram epoch covers it. Content writes reset both.
        Column("chunked", Boolean, nullable=False, default=False),
        Column("encoded", Boolean, nullable=False, default=False),
        # Gram eligibility: reset by content writes like its siblings,
        # re-stamped with `chunked`; only read behind a true `chunked`.
        Column("indexable", Boolean, nullable=False, default=False),
        # Chunk provenance: the body hash and engine/grammar generation the
        # stored chunk rows derive from — the fingerprint-skip law reads both.
        Column("chunk_source_hash", String(64)),
        Column("chunk_generation", _string(32)),
        Column("owner_id", _string(255), index=True),
        Column("original_parent_id", ULIDKey()),
        Column("original_name", BytewiseString(MAX_SEGMENT_LENGTH)),
        Column("created_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        Column("deleted_at", DateTime(timezone=True)),
        UniqueConstraint("parent_id", "name", name=f"uq_{table_name}_parent_name"),
        Index(f"ix_{table_name}_ext_kind", "ext", "kind"),
        # Serves grep's overlay probe: the encoded=0 seek set is mostly
        # directories, so kind in the key rejects them without row lookups.
        Index(f"ix_{table_name}_encoded_kind", "encoded", "kind"),
        # Restore lookup by original site. Plain composite: a filtered
        # index over the mostly-NULL restore columns is not portable.
        Index(f"ix_{table_name}_restore", "original_parent_id", "original_name"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Current content, one body per row, keyed by entry identity. The body
    # column is physically last: width changes to earlier columns never
    # rewrite the blob's pages.
    content = Table(
        f"{table_name}_content",
        metadata,
        Column("entry_id", ULIDKey(), primary_key=True),
        # Write time of this body row (every overwrite re-mints it) — the
        # age sweep's orphan-reclaim fence is measured against.
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("content", _body_text(), nullable=False),
        schema=schema,
    )

    # Version history. The write path stores full snapshots
    # (``is_snapshot=True``, body in ``content``); the batch pack verb
    # rewrites cold ranges into snapshot-every-N + forward diffs
    # (``version_diff``). Bodies last, metadata first.
    versions = Table(
        f"{table_name}_versions",
        metadata,
        Column("entry_id", ULIDKey(), primary_key=True),
        Column("version_number", Integer, primary_key=True, autoincrement=False),
        Column("is_snapshot", Boolean, nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        Column("created_by", _string(255)),
        Column("created_at", DateTime(timezone=True)),
        Column("content", _body_text()),
        Column("version_diff", _body_text()),
        schema=schema,
    )

    # Chunks: the indexed/embedded unit, keyed by entry identity — never by
    # path (a rename rewrites zero chunk rows). The integer PK feeds posting
    # doc_ids, hence AUTOINCREMENT. ``encoded`` is the per-chunk gram-index
    # dirty flag; embedding staleness needs none (``embedding IS NULL``).
    chunks = Table(
        f"{table_name}_chunks",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("entry_id", ULIDKey(), nullable=False, index=True),
        Column("chunk_index", Integer, nullable=False),
        Column("line_start", Integer, nullable=False),
        Column("line_end", Integer, nullable=False),
        Column("content_hash", String(64)),
        Column("encoded", Boolean, nullable=False, default=False),
        Column("embedding", embedding_type),
        Column("content", _body_text(), nullable=False),
        UniqueConstraint("entry_id", "chunk_index", name=f"uq_{table_name}_chunks_entry_index"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Edges: narrow ID triples with both traversal directions indexed. No
    # path columns — liveness and addressing come from joining entries.
    edges = Table(
        f"{table_name}_edges",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("source_id", ULIDKey(), nullable=False),
        Column("target_id", ULIDKey(), nullable=False),
        Column("edge_type", _string(MAX_SEGMENT_LENGTH), nullable=False),
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
    # rebuilt gram index atomically. Versions are per-entry monotone
    # values on their own rows — the mount keeps no version sequence.
    meta = Table(
        f"{table_name}_meta",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("schema_format_version", Integer, nullable=False),
        Column("mount_identity", String(ULID_LENGTH), nullable=False),
        Column("current_gram_epoch", Integer),
        # Reindex single-runner lease: holder token + last-heartbeat epoch
        # millis. NULL holder or a stale heartbeat means the lease is free.
        Column("reindex_holder", String(ULID_LENGTH)),
        Column("reindex_heartbeat", BigInteger),
        Column("created_at", DateTime(timezone=True)),
        CheckConstraint("id = 1", name=f"ck_{table_name}_meta_single_row"),
        schema=schema,
    )

    # One row per gram-index build: the two-part fingerprint (format
    # version, options hash) — coverage is per-row flag state, not a
    # version threshold. Rows outside the current epoch are reclaimable
    # garbage, swept by the reindex verb.
    gram_epochs = Table(
        f"{table_name}_gram_epochs",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("format_version", Integer, nullable=False),
        Column("options_hash", String(64), nullable=False),
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
        # Mysql's bare BLOB silently truncates at 64KB; a hot gram's
        # doclist blob routinely exceeds it.
        Column("postings", LargeBinary().with_variant(LONGBLOB(), *_MYSQL_FAMILY), nullable=False),
        Column("encoding", SmallInteger, nullable=False, default=ENCODING_DELTA_VARINT),
        Column("doc_count", Integer, nullable=False),
        Column("byte_size", Integer, nullable=False),
        schema=schema,
    )

    # Path-segment postings: one row per (segment, entry_id) — the entry's
    # ancestor directory names, verbatim, leaf excluded (``name`` serves it).
    # Maintained inside the same transactions that write ``path``, never
    # epoch-cycled; the entry_id index serves delete-by-entry and cascades.
    segments = Table(
        f"{table_name}_segments",
        metadata,
        Column("segment", BytewiseString(MAX_SEGMENT_LENGTH), primary_key=True),
        Column("entry_id", ULIDKey(), primary_key=True),
        Index(f"ix_{table_name}_segments_entry", "entry_id"),
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
        segments=segments,
    )
