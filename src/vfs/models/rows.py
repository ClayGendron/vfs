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

from typing import TYPE_CHECKING, Annotated, Any, Final, Literal, NamedTuple

from sqlalchemy import (
    BINARY,
    DDL,
    VARBINARY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Double,
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
    event,
    text,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.dialects.oracle import RAW
from ulid import ULID

from vfs.models.lexical import MAX_TERM_BYTES
from vfs.models.links import MAX_LINK_CONTEXT_LENGTH
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
    {"id", "entry_id", "parent_id", "original_parent_id", "original_name", "origin_path", "version"}
    | {"chunked", "encoded", "indexable", "chunk_source_hash", "chunk_generation"}
    | {"link_source_hash", "link_generation", "everyone_level"},
)

# The Entry field homed in the content table rather than the entries row —
# bodies leave the narrow row so metadata writes never rewrite content.
ENTRY_CONTENT_FIELDS: Final[frozenset[str]] = frozenset({"content"})

# Per-model column exemptions for the metadata family: the id backbone plus
# the owner references, which the models carry as Path fields (below) and
# the persistence layer resolves to entry identities.
VERSION_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"entry_id"})
CHUNK_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"id", "entry_id"})
EDGE_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"id", "source_id", "target_id", "provenance", "context"})

# Who authored an edge row. Minted by the layer, never the caller: the verb
# gate stamps user/agent/system, the fs mirror stamps system, the reindex
# extractor stamps extracted — and each deleter touches only its own kind.
EdgeProvenance = Literal["user", "agent", "system", "extracted"]
EDGE_PROVENANCE_VALUES: Final[frozenset[str]] = frozenset({"user", "agent", "system", "extracted"})

# Owner-reference fields per model: the Path field standing in for the row's
# id reference. The drift test excuses these from column matching.
MODEL_OWNER_FIELDS: Final[dict[str, frozenset[str]]] = {
    "Version": frozenset({"file"}),
    "Chunk": frozenset({"file"}),
    "Edge": frozenset({"source", "target"}),
}

# Model fields with no column on the model's own table: a version's
# subjects live one row each in the ``version_subjects`` side table.
MODEL_FIELD_ONLY: Final[dict[str, frozenset[str]]] = {
    "Version": frozenset({"subjects"}),
    "Chunk": frozenset(),
    "Edge": frozenset(),
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
SCHEMA_FORMAT_VERSION: Final = 18

# The widest principal id a grant, membership, or owner column stores.
MAX_PRINCIPAL_ID_LENGTH: Final = 255

# ULIDs render as 26 Crockford-base32 characters.
ULID_LENGTH: Final = 26

# A ranking signal's name — one short lowercase token, the ``Ranker`` gate.
MAX_SIGNAL_NAME_LENGTH: Final = 32

# The widest ``embedding_model`` the meta row stores (``provider/model@dim``).
MAX_MODEL_ID_LENGTH: Final = 255

# pgvector's HNSW and IVFFlat indexes accept at most this many components.
PGVECTOR_INDEX_MAX_DIMENSION: Final = 2_000

# Auto-named indexes take the bare table name: SQLAlchemy's default folds
# the schema in, so a long schema would push them past identifier caps.
_NAMING_CONVENTION: Final = {"ix": "ix_%(table_name)s_%(column_0_name)s"}

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
MSSQL_UTF8_COLLATION: Final = "Latin1_General_100_BIN2_UTF8"


def _string(length: int) -> String:
    """A general string column that stores non-Latin1 losslessly everywhere.

    A plain ``String`` on MSSQL compiles with the *database's* default
    collation — commonly CP-1252 — which squeezes any non-Latin1 value
    to ``?`` at conversion time; the UTF-8 collation variant closes that
    on the column side (the bind side is the engine's
    ``use_setinputsizes=False``).
    """
    return String(length).with_variant(String(length, collation=MSSQL_UTF8_COLLATION), "mssql")


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
            return dialect.type_descriptor(String(self.length, collation=MSSQL_UTF8_COLLATION))
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
    return Text().with_variant(LONGTEXT(), *_MYSQL_FAMILY).with_variant(Text(collation=MSSQL_UTF8_COLLATION), "mssql")


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
    version_subjects: Table
    chunks: Table
    edges: Table
    meta: Table
    gram_epochs: Table
    posting_list: Table
    segments: Table
    lex_docs: Table
    lex_postings: Table
    lex_df: Table
    lex_stats: Table
    signals: Table
    signal_epochs: Table
    grants: Table
    memberships: Table
    relabels: Table
    principal_revisions: Table

    def content_joined(self) -> FromClause:
        """Entries LEFT-joined to content on ``entry_id`` — the one canonical join."""
        return self.entry.outerjoin(self.content, self.content.c.entry_id == self.entry.c.entry_id)

    def epoch_scoped(self) -> tuple[Table, ...]:
        """Every table keyed by gram epoch — what a build fills and a reclaim sweeps."""
        return (self.posting_list, self.lex_docs, self.lex_postings, self.lex_df, self.lex_stats, self.gram_epochs)


def build_vfs_tables(
    *,
    schema: str | None = None,
    native_embedding: NativeEmbeddingConfig | None = None,
) -> VFSTables:
    """Build one mount's table family in memory.

    Constructs the schema objects only; issues no DDL. Every table binds to
    one fresh :class:`MetaData` so a single ``create_all`` provisions them.
    Integer PKs that feed posting-list ``doc_id`` values are SQLite
    ``AUTOINCREMENT`` so a deleted top rowid is never reused.

    The names are fixed — every table is ``vfs_*`` — so one schema holds one
    mount; *schema* is what places a mount, on engines that have schemas.
    """
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)

    embedding_type = (
        VectorType(
            dimension=native_embedding.dimension,
            model_name=native_embedding.model_name,
            native=True,
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
        "vfs_entries",
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
        # Link provenance: the body hash and extractor generation the stored
        # extracted out-edges derive from — the same skip law, its own stamp.
        Column("link_source_hash", String(64)),
        Column("link_generation", _string(32)),
        Column("owner_id", _string(255), index=True),
        # The everyone level at this path (0 none, 1 read, 2 read_write):
        # the deepest covering posture row's level, stamped with the row.
        # No default on purpose — a mint site that forgets it fails loudly.
        Column("everyone_level", SmallInteger, nullable=False),
        Column("original_parent_id", ULIDKey()),
        Column("original_name", BytewiseString(MAX_SEGMENT_LENGTH)),
        # A trashed row's path at the moment it was deleted: what its
        # rights are judged by. NULL on every live row; cleared by restore.
        Column("origin_path", BytewiseString(MAX_PATH_LENGTH)),
        Column("created_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        Column("deleted_at", DateTime(timezone=True)),
        UniqueConstraint("parent_id", "name", name="uq_vfs_entries_parent_name"),
        Index("ix_vfs_entries_ext_kind", "ext", "kind"),
        # Serves grep's overlay probe: the encoded=0 seek set is mostly
        # directories, so kind in the key rejects them without row lookups.
        Index("ix_vfs_entries_encoded_kind", "encoded", "kind"),
        # Restore lookup by original site. Plain composite: a filtered
        # index over the mostly-NULL restore columns is not portable.
        Index("ix_vfs_entries_restore", "original_parent_id", "original_name"),
        # The everyone leg of a partial read: "rows under /p everyone may
        # see" is one seek here; the leading column alone serves the rest.
        Index("ix_vfs_entries_everyone_path", "everyone_level", "path"),
        # The range join for trashed rows seeks their origin as it seeks
        # ``path`` for live ones; the index holds only the trashed rows.
        Index("ix_vfs_entries_origin_path", "origin_path"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Current content, one body per row, keyed by entry identity. The body
    # column is physically last: width changes to earlier columns never
    # rewrite the blob's pages.
    content = Table(
        "vfs_content",
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
    # (``version_diff``). Every row names who acted (``actor``), how the
    # authority was proven (``provenance``), and the edge identity it came
    # in under; the subjects it acted for sit one per row in the side
    # table below. Bodies last, metadata first.
    versions = Table(
        "vfs_versions",
        metadata,
        Column("entry_id", ULIDKey(), primary_key=True),
        Column("version_number", Integer, primary_key=True, autoincrement=False),
        Column("is_snapshot", Boolean, nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        Column("actor", _string(255)),
        Column("provenance", String(16)),
        Column("source_identity", _string(255)),
        # The grant revision in force when the version was written: which
        # grants allowed it, answerable without replaying history.
        Column("grant_revision", BigInteger),
        Column("created_at", DateTime(timezone=True)),
        Column("content", _body_text()),
        Column("version_diff", _body_text()),
        schema=schema,
    )

    # The subjects a version was written for: one row per member of the
    # authority's set, keyed by the version it attributes. A system-actor
    # version has no rows here.
    version_subjects = Table(
        "vfs_version_subjects",
        metadata,
        Column("entry_id", ULIDKey(), primary_key=True),
        Column("version_number", Integer, primary_key=True, autoincrement=False),
        Column("principal_id", _string(255), primary_key=True),
        schema=schema,
    )

    # Chunks: the indexed/embedded unit, keyed by entry identity — never by
    # path (a rename rewrites zero chunk rows). The integer PK feeds posting
    # doc_ids, hence AUTOINCREMENT. ``encoded`` is the per-chunk gram-index
    # dirty flag; embedding staleness needs none (``embedding IS NULL``).
    chunks = Table(
        "vfs_chunks",
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
        UniqueConstraint("entry_id", "chunk_index", name="uq_vfs_chunks_entry_index"),
        schema=schema,
        sqlite_autoincrement=True,
    )
    if native_embedding is not None:
        _attach_pgvector_ddl(metadata, chunks, native_embedding)

    # Edges: narrow ID triples with both traversal directions indexed. No
    # path columns — liveness and addressing come from joining entries.
    # ``provenance`` has no default on purpose: a mint site that forgets to
    # stamp the author class must fail loudly, never mislabel a row.
    fs_where = text("edge_type = 'fs'")
    edges = Table(
        "vfs_edges",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("source_id", ULIDKey(), nullable=False),
        Column("target_id", ULIDKey(), nullable=False),
        Column("edge_type", _string(MAX_SEGMENT_LENGTH), nullable=False),
        Column("weight", Float),
        Column("distance", Float),
        Column("provenance", _string(16), nullable=False),
        # The referring line an extracted edge was read from, folded; NULL
        # on every authored row.
        Column("context", _string(MAX_LINK_CONTEXT_LENGTH)),
        UniqueConstraint("source_id", "target_id", "edge_type", name="uq_vfs_edges_src_tgt_type"),
        Index("ix_vfs_edges_fwd", "source_id", "edge_type"),
        Index("ix_vfs_edges_rev", "target_id", "edge_type"),
        # Single-parent hardening: at most one fs in-edge per entry, emitted
        # only where the engine has partial/filtered indexes; elsewhere the
        # conformance invariant is the declared floor.
        Index(
            "uq_vfs_edges_fs_parent",
            "target_id",
            unique=True,
            sqlite_where=fs_where,
            postgresql_where=fs_where,
            mssql_where=fs_where,
            # The stub narrows ``dialect`` to str; the runtime accepts a tuple.
        ).ddl_if(dialect=("sqlite", "postgresql", "mssql")),  # ty: ignore[invalid-argument-type]
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Single-row mount metadata: the schema-format version first touch
    # verifies, the durable mount identity that keys the per-mount advisory
    # lock, and the current-epoch pointer whose one-row flip publishes a
    # rebuilt gram index atomically. Versions are per-entry monotone
    # values on their own rows — the mount keeps no version sequence.
    meta = Table(
        "vfs_meta",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("schema_format_version", Integer, nullable=False),
        Column("mount_identity", String(ULID_LENGTH), nullable=False),
        Column("current_gram_epoch", Integer),
        # Reindex single-runner lease: holder token + last-heartbeat epoch
        # millis. NULL holder or a stale heartbeat means the lease is free.
        Column("reindex_holder", String(ULID_LENGTH)),
        Column("reindex_heartbeat", BigInteger),
        # The mount's one embedding space — the provider- and dimension-
        # qualified model id and its width, stamped by the first embed.
        Column("embedding_model", _string(MAX_MODEL_ID_LENGTH)),
        Column("embedding_dimension", Integer),
        # The grant spine's revision: every grant, posture, or membership
        # write bumps it first, so the bump is also the admin writes' lock.
        Column("grant_revision", BigInteger, nullable=False, default=0),
        Column("created_at", DateTime(timezone=True)),
        CheckConstraint("id = 1", name="ck_vfs_meta_single_row"),
        schema=schema,
    )

    # One row per gram-index build: the two-part fingerprint (format
    # version, options hash) — coverage is per-row flag state, not a
    # version threshold. Rows outside the current epoch are reclaimable
    # garbage, swept by the reindex verb.
    gram_epochs = Table(
        "vfs_gram_epochs",
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
        "vfs_grams_posting_list",
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
        "vfs_segments",
        metadata,
        Column("segment", BytewiseString(MAX_SEGMENT_LENGTH), primary_key=True),
        Column("entry_id", ULIDKey(), primary_key=True),
        Index("ix_vfs_segments_entry", "entry_id"),
        schema=schema,
    )

    # The lexical (BM25) index, epoch-scoped beside the gram postings and
    # rebuilt whole per reindex: one doc row per chunk with its exact
    # token count; one row per (term, block) holding up to a block's
    # postings as three delta+varint blobs, keyed so a term's blocks are
    # contiguous; one summary row per term with its document frequency,
    # idf, maximum weight and per-block summary blob; one row per epoch
    # with the corpus statistics and the constants they were weighted
    # under. ``term`` is folded text, bytewise — a collation that unified
    # accents would collide the key. Every row is its primary key: SQLite
    # stores them WITHOUT ROWID, in the key B-tree itself, as the
    # clustered engines do — no second copy per row.
    lex_docs = Table(
        "vfs_lex_docs",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("chunk_id", BigInteger, primary_key=True, autoincrement=False),
        Column("entry_id", ULIDKey(), nullable=False),
        Column("dl", Integer, nullable=False),
        Index("ix_vfs_lex_docs_entry", "epoch", "entry_id"),
        schema=schema,
        sqlite_with_rowid=False,
    )
    lex_postings = Table(
        "vfs_lex_postings",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("term", BytewiseString(MAX_TERM_BYTES), primary_key=True),
        Column("block_no", Integer, primary_key=True, autoincrement=False),
        Column("doc_count", Integer, nullable=False),
        Column("doc_ids", LargeBinary().with_variant(LONGBLOB(), *_MYSQL_FAMILY), nullable=False),
        Column("tfs", LargeBinary().with_variant(LONGBLOB(), *_MYSQL_FAMILY), nullable=False),
        Column("dls", LargeBinary().with_variant(LONGBLOB(), *_MYSQL_FAMILY), nullable=False),
        schema=schema,
        sqlite_with_rowid=False,
    )
    lex_df = Table(
        "vfs_lex_df",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("term", BytewiseString(MAX_TERM_BYTES), primary_key=True),
        Column("df", Integer, nullable=False),
        Column("idf", Double, nullable=False),
        Column("max_weight", Double, nullable=False),
        Column("blocks", LargeBinary().with_variant(LONGBLOB(), *_MYSQL_FAMILY), nullable=False),
        schema=schema,
        sqlite_with_rowid=False,
    )
    lex_stats = Table(
        "vfs_lex_stats",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("n_docs", Integer, nullable=False),
        Column("avg_dl", Double, nullable=False),
        Column("k1", Double, nullable=False),
        Column("b", Double, nullable=False),
        schema=schema,
        sqlite_with_rowid=False,
    )

    # Ranking signals: one stored prior per (entry, signal), sparse — no
    # row is factor one. Rows carry the generation they were computed
    # under; ``signal_epochs`` names each signal's live generation and the
    # options it was computed with, so a refresh writes the new
    # generation beside the old, flips the pointer, then sweeps.
    signals = Table(
        "vfs_signals",
        metadata,
        Column("entry_id", ULIDKey(), primary_key=True),
        Column("signal", _string(MAX_SIGNAL_NAME_LENGTH), primary_key=True),
        Column("generation", String(ULID_LENGTH), primary_key=True),
        Column("value", Float, nullable=False),
        schema=schema,
    )
    signal_epochs = Table(
        "vfs_signal_epochs",
        metadata,
        Column("signal", _string(MAX_SIGNAL_NAME_LENGTH), primary_key=True),
        Column("generation", String(ULID_LENGTH), nullable=False),
        Column("options_hash", String(64), nullable=False),
        Column("row_count", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True)),
        schema=schema,
    )

    # Row grants: one row per (principal, prefix), additive-only — a row
    # widens, nothing narrows except the everyone rows (principal ``*``)
    # that carry a mount's posture. Prefixes are mount-relative canonical
    # paths in the entries table's collation. A surrogate key keeps the
    # wide pair in a secondary index, inside SQL Server's clustered cap.
    grants = Table(
        "vfs_grants",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("principal_id", _string(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
        Column("path_prefix", BytewiseString(MAX_PATH_LENGTH), nullable=False),
        Column("level", String(16), nullable=False),
        Column("granted_by", _string(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
        Column("granted_at", DateTime(timezone=True), nullable=False),
        Column("revision", BigInteger, nullable=False),
        UniqueConstraint("principal_id", "path_prefix", name="uq_vfs_grants_key"),
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Group memberships: *principal_id* is a direct member of *group_id*,
    # itself possibly a member of another group. The reverse index serves
    # the write-time depth and cycle checks, which walk downward.
    memberships = Table(
        "vfs_memberships",
        metadata,
        Column("principal_id", _string(MAX_PRINCIPAL_ID_LENGTH), primary_key=True),
        Column("group_id", _string(MAX_PRINCIPAL_ID_LENGTH), primary_key=True),
        Column("granted_by", _string(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
        Column("granted_at", DateTime(timezone=True), nullable=False),
        Index("ix_vfs_memberships_group", "group_id"),
        schema=schema,
    )

    # Posture rows whose relabel has not settled: the path, the revision the mark was
    # planted under (it keys every compile made meanwhile), and the last path rewritten.
    relabels = Table(
        "vfs_relabels",
        metadata,
        Column("path_prefix", BytewiseString(MAX_PATH_LENGTH), primary_key=True),
        Column("revision", BigInteger, nullable=False),
        Column("cursor", BytewiseString(MAX_PATH_LENGTH), nullable=True),
        schema=schema,
    )

    # One row per principal or group ever named by a grants or memberships write, stamped
    # with that write's grant revision; a caller's compile is keyed on its subjects' and groups' stamps.
    principal_revisions = Table(
        "vfs_principal_revisions",
        metadata,
        Column("principal_id", _string(MAX_PRINCIPAL_ID_LENGTH), primary_key=True),
        Column("revision", BigInteger, nullable=False),
        schema=schema,
    )

    return VFSTables(
        metadata=metadata,
        entry=entry,
        content=content,
        versions=versions,
        version_subjects=version_subjects,
        chunks=chunks,
        edges=edges,
        meta=meta,
        gram_epochs=gram_epochs,
        posting_list=posting_list,
        segments=segments,
        lex_docs=lex_docs,
        lex_postings=lex_postings,
        lex_df=lex_df,
        lex_stats=lex_stats,
        signals=signals,
        signal_epochs=signal_epochs,
        grants=grants,
        memberships=memberships,
        relabels=relabels,
        principal_revisions=principal_revisions,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _attach_pgvector_ddl(metadata: MetaData, chunks: Table, config: NativeEmbeddingConfig) -> None:
    """The extension and the ANN index behind a native pgvector column — PostgreSQL only.

    Both statements are dialect-conditional DDL events: every other
    engine provisions its own column with no index, so one table
    definition serves the whole matrix. A space wider than pgvector's
    index cap gets the column and an exact scan, never a failing DDL.
    """
    extension = DDL("CREATE EXTENSION IF NOT EXISTS vector").execute_if(dialect="postgresql")
    event.listen(metadata, "before_create", extension)
    if config.dimension > PGVECTOR_INDEX_MAX_DIMENSION:
        return
    index = DDL(
        f"CREATE INDEX IF NOT EXISTS ix_vfs_chunks_embedding ON {chunks.fullname} "
        f"USING {config.index_method} (embedding {config.operator_class})"
    ).execute_if(dialect="postgresql")
    event.listen(chunks, "after_create", index)
