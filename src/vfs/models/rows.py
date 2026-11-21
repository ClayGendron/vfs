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

import functools
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal, NamedTuple

from sqlalchemy import (
    BINARY,
    DDL,
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
from ulid import ULID

from vfs.models.lexical import MAX_TERM_BYTES
from vfs.models.links import MAX_LINK_CONTEXT_LENGTH
from vfs.models.media import MAX_RENDER_DETAIL_LENGTH, MAX_RENDER_GENERATION_LENGTH
from vfs.models.vector import NativeEmbeddingConfig, VectorType
from vfs.paths import MAX_PATH_LENGTH, MAX_SEGMENT_LENGTH

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect
    from sqlalchemy.sql import FromClause
    from sqlalchemy.types import TypeEngine

# Entries-table columns with no counterpart field on the domain model: the id
# backbone, the tombstone's root (the row a delete named, which restore and
# sweep act on as a set), and the per-entry version — minted and guarded
# storage-side, reported on observations, never authored on an Entry.
ENTRY_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"id", "entry_id", "parent_id", "trash_root_id", "version"}
    | {"chunked", "encoded", "indexable", "indexed_epoch", "chunk_source_hash", "chunk_generation"}
    | {"link_source_hash", "link_generation", "everyone_level"}
    | {"render_source_hash", "render_generation", "render_detail", "render_units", "media_width", "media_height"},
)

# The Entry fields homed in a body table rather than the entries row —
# bodies leave the narrow row so metadata writes never rewrite them. Each
# names the ``VFSTables`` attribute of the table holding it.
ENTRY_BODY_HOMES: Final[dict[str, str]] = {"content": "content", "data": "blobs"}
ENTRY_CONTENT_FIELDS: Final[frozenset[str]] = frozenset(ENTRY_BODY_HOMES)

# Per-model column exemptions for the metadata family: the id backbone plus
# the owner references, which the models carry as Path fields (below) and
# the persistence layer resolves to entry identities.
VERSION_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"entry_id"})
CHUNK_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"id", "entry_id"})
EDGE_ROW_ONLY_COLUMNS: Final[frozenset[str]] = frozenset({"id", "source_id", "target_id", "provenance", "context"})

# Who authored an edge row. Minted by the layer, never the caller: the verb
# gate stamps user/agent/system, the fs mirror stamps system, the rebuild
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
# is a reserved word on some engines); unlisted fields share their column's name.
MODEL_COLUMN_RENAMES: Final[dict[str, dict[str, str]]] = {
    "Version": {"number": "version_number"},
    "Chunk": {},
    "Edge": {},
}

# First-touch writes this into the meta row; every later first touch compares
# and refuses loudly on mismatch — never PRAGMA/catalog sniffing.
SCHEMA_FORMAT_VERSION: Final = 28

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

# Table families cached by shape: hot tenants stay resident, cold ones rebuild.
TABLE_FAMILY_CACHE: Final = 64

# Posting-list encoding tag. v1 writes ``delta+varint`` only; the per-row tag
# lets the format evolve per gram without a migration (``roaring`` is the
# reserved density-tier upgrade; tag 2 — the dropped delta+gamma — is retired,
# never reused).
ENCODING_DELTA_VARINT: Final = 1
ENCODING_ROARING: Final = 3


class BytewiseString(TypeDecorator[str]):
    """A bounded key string, bytewise-ordered and byte-budgeted where pinned.

    *length* denominates UTF-8 bytes — the same unit as the path
    contract and every engine's index-key cap, so a lawful value always
    fits the column and the column's worst-case key never outgrows an
    engine. SQLite's default BINARY collation is already bytewise;
    Postgres pins ``COLLATE "C"`` in DDL, or pagination order and LIKE
    sargability silently diverge between the two.

    Any other engine takes the plain ``String`` fallback with no
    collation pin, so bytewise order and byte budgeting there rest on
    engine defaults — an accepted degradation, not a pinned contract.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int) -> None:
        super().__init__(length)
        self.length = length

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(String(self.length, collation="C"))
        return dialect.type_descriptor(String(self.length))

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).decode()
        return value


def _body_text() -> Text:
    """An unbounded text body: ``Text`` is each engine's unbounded form, where a bare ``String()`` has no length."""
    return Text()


def _body_bytes() -> LargeBinary:
    """An unbounded bytes body: BLOB on SQLite and BYTEA on Postgres."""
    return LargeBinary()


def _timestamp() -> DateTime:
    """A zone-aware instant that keeps sub-second precision on both engines."""
    return DateTime(timezone=True)


def _on_side(*, trashed: bool) -> dict[str, Any]:
    """The predicate of an index that holds one side of the tombstone, on each engine that takes a partial index.

    An engine outside the two builds the index whole, which serves the same reads with the other side in it.
    """
    predicate = text("deleted_at IS NOT NULL" if trashed else "deleted_at IS NULL")
    return {"sqlite_where": predicate, "postgresql_where": predicate}


def _uuid_native(dialect: Dialect) -> bool:
    """True where the engine's own uuid type keeps ULID time-order.

    An allow-list, not ``dialect.supports_native_uuid``: that flag means
    the driver binds uuid objects and says nothing about sort order, and
    an engine can report support while forfeiting time-ordered index
    locality.
    """
    return dialect.name == "postgresql"


EntryId = Annotated[str, "26-char ULID naming one entry row; minted at write, joined on everywhere"]


class ULIDKey(TypeDecorator[str]):
    """A 128-bit identity column speaking 26-char ULID strings in Python.

    The one conversion home: every bound value and every fetched value
    crosses here, so no other module translates identity. Storage is
    binary-16 on every engine, never text: the native ``uuid`` type where
    the dialect binds one and its sort preserves time-order (Postgres),
    and fixed-width ``BINARY(16)`` everywhere else — including engines
    whose only uuid-shaped alternative would be the CHAR(32) hex fallback.
    """

    impl = Uuid
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if _uuid_native(dialect):
            return dialect.type_descriptor(Uuid())
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
    blobs: Table
    versions: Table
    version_subjects: Table
    chunks: Table
    edges: Table
    meta: Table
    index_state: Table
    lock: Table
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
    embed_refusals: Table
    relabels: Table
    principal_revisions: Table

    def content_joined(self) -> FromClause:
        """Entries LEFT-joined to content on ``entry_id`` — the one canonical join."""
        return self.entry.outerjoin(self.content, self.content.c.entry_id == self.entry.c.entry_id)

    def bodies_joined(self, *, content: bool, data: bool) -> FromClause:
        """Entries LEFT-joined to whichever body tables a read projects."""
        source: FromClause = self.entry
        if content:
            source = source.outerjoin(self.content, self.content.c.entry_id == self.entry.c.entry_id)
        if data:
            source = source.outerjoin(self.blobs, self.blobs.c.entry_id == self.entry.c.entry_id)
        return source

    def epoch_scoped(self) -> tuple[Table, ...]:
        """Every table keyed by gram epoch — what a build fills and a reclaim sweeps."""
        return (self.posting_list, self.lex_docs, self.lex_postings, self.lex_df, self.lex_stats, self.gram_epochs)


@functools.lru_cache(maxsize=TABLE_FAMILY_CACHE)
def build_vfs_tables(
    *,
    schema: str | None = None,
    native_embedding: NativeEmbeddingConfig | None = None,
) -> VFSTables:
    """Build one mount's table family in memory, once per shape.

    Constructs the schema objects only; issues no DDL. Every table binds to
    one :class:`MetaData` so a single ``create_all`` provisions them.
    Integer PKs that feed posting-list ``doc_id`` values are SQLite
    ``AUTOINCREMENT`` so a deleted top rowid is never reused.

    The names are fixed — every table is ``vfs_*`` — so one schema holds one
    mount; *schema* is what places a mount, on engines that have schemas.
    The family is immutable after construction and carries no engine
    binding, so mounts of one shape share it: the cache is keyed by
    *schema* and *native_embedding*, and bounded so a host that places
    thousands of tenants in their own schemas rebuilds cold ones (a few
    milliseconds) rather than holding every family forever.
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
        # Identity() is explicit: some dialects generate nothing for a bare
        # autoincrement primary key, and it is part of the Postgres DDL.
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("entry_id", ULIDKey(), nullable=False, unique=True, index=True),
        Column("parent_id", ULIDKey()),
        Column("external_id", String(1024)),
        Column("path", BytewiseString(MAX_PATH_LENGTH), nullable=False, unique=True, index=True),
        Column("name", BytewiseString(MAX_SEGMENT_LENGTH), nullable=False),
        Column("kind", String(32), nullable=False, index=True),
        Column("version", BigInteger),
        Column("content_hash", String(64)),
        Column("mime_type", String(MAX_SEGMENT_LENGTH)),
        Column("ext", String(32), index=True),
        # Lines of the text the verbs see — the rendering's for a bytes
        # row, zero until rendered — under the one law in ``line_count``.
        Column("lines", Integer, nullable=False, default=0),
        Column("size_bytes", Integer, nullable=False, default=0),
        # Overlay flags: `chunked`, derived state reflects this content; `encoded`,
        # nothing of the row awaits the gram index, so a directory is always true.
        Column("chunked", Boolean, nullable=False, default=False),
        Column("encoded", Boolean, nullable=False, default=False),
        # Gram eligibility: reset by content writes like its siblings,
        # re-stamped with `chunked`; only read behind a true `chunked`.
        Column("indexable", Boolean, nullable=False, default=False),
        # The last published segment that posted the current chunk rows; a re-split clears it.
        Column("indexed_epoch", Integer),
        # Chunk provenance: the body hash and engine/grammar generation the
        # stored chunk rows derive from — the fingerprint-skip law reads both.
        Column("chunk_source_hash", String(64)),
        Column("chunk_generation", String(32)),
        # Link provenance: the body hash and extractor generation the stored
        # extracted out-edges derive from — the same skip law, its own stamp.
        Column("link_source_hash", String(64)),
        Column("link_generation", String(32)),
        # Which body table holds this row's body: text in ``vfs_content``,
        # bytes in ``vfs_blobs``. A bytes row's text is its rendering.
        Column("source", String(8), nullable=False, default="text"),
        # Render provenance: the bytes hash and renderer generation the
        # stored rendering derives from — the same skip law, its own stamp.
        Column("render_source_hash", String(64)),
        Column("render_generation", String(MAX_RENDER_GENERATION_LENGTH)),
        # Where the rendering stands; NULL on text rows. A failure is a
        # status with its reason in ``render_detail``, never a body.
        Column("render_status", String(16)),
        Column("render_detail", String(MAX_RENDER_DETAIL_LENGTH)),
        # The rendering's unit table (pages, slides, sheets) as JSON text.
        Column("render_units", _body_text()),
        Column("media_width", Integer),
        Column("media_height", Integer),
        Column("owner_id", String(255), index=True),
        # The everyone level at this path, the rank of the deepest covering
        # posture row's rung (0 none … 5 read_write), stamped with the row.
        # No default on purpose — a mint site that forgets it fails loudly.
        Column("everyone_level", SmallInteger, nullable=False),
        Column("created_at", _timestamp()),
        Column("updated_at", _timestamp()),
        # The tombstone: a deleted row stays at its path with the time it
        # was deleted and the root the delete named (its own id for a root).
        Column("deleted_at", _timestamp()),
        Column("trash_root_id", ULIDKey()),
        UniqueConstraint("parent_id", "name", name="uq_vfs_entries_parent_name"),
        Index("ix_vfs_entries_ext_kind", "ext", "kind"),
        # Serves grep's overlay probe: the encoded=0 seek set is the pending
        # content rows, and kind in the key answers the kind term beside it.
        Index("ix_vfs_entries_encoded_kind", "encoded", "kind"),
        # The incremental pass's seeks: the rows not yet chunked and the rows awaiting the
        # gram index, live, in id order, apart from the ineligible and the trashed rows.
        Index("ix_vfs_entries_index_pending", "encoded", "chunked", "indexable", "deleted_at", "id"),
        # The everyone leg of a partial read: "rows under /p everyone may
        # see" is one seek here; the leading column alone serves the rest.
        Index("ix_vfs_entries_everyone_path", "everyone_level", "path"),
        # The trash view and the retention sweep seek the tombstoned rows here, and it holds them alone,
        # so no live listing is planned onto its seek of the live rows on a table that is mostly tombstones.
        Index("ix_vfs_entries_deleted_at", "deleted_at", **_on_side(trashed=True)),
        # A listing page seeks the live rows alone, so a tombstone in its range costs no read.
        Index("ix_vfs_entries_live_children", "parent_id", "name", **_on_side(trashed=False)),
        Index("ix_vfs_entries_live_path", "path", **_on_side(trashed=False)),
        Index("ix_vfs_entries_trash_root", "trash_root_id"),
        # The twin lookups: a body hash shared by many rows is found by index, never a scan.
        Index("ix_vfs_entries_content_hash", "content_hash"),
        # The unrendered count, the pending probe and the pending page's keyset seek over live rows.
        Index("ix_vfs_entries_render_status", "render_status", "deleted_at", "id"),
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
        Column("created_at", _timestamp(), nullable=False),
        Column("content", _body_text(), nullable=False),
        schema=schema,
    )

    # Current bytes, one body per bytes-sourced row, keyed by entry identity.
    # The body column is physically last for the same reason as above.
    blobs = Table(
        "vfs_blobs",
        metadata,
        Column("entry_id", ULIDKey(), primary_key=True),
        Column("created_at", _timestamp(), nullable=False),
        Column("data", _body_bytes(), nullable=False),
        schema=schema,
    )
    _attach_blob_storage_ddl(blobs)

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
        Column("actor", String(255)),
        Column("provenance", String(16)),
        Column("source_identity", String(255)),
        # The grant revision in force when the version was written: which
        # grants allowed it, answerable without replaying history.
        Column("grant_revision", BigInteger),
        Column("created_at", _timestamp()),
        Column("content", _body_text()),
        Column("version_diff", _body_text()),
        # A bytes-sourced entry's version is a full bytes snapshot; no diff form.
        Column("data", _body_bytes()),
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
        Column("principal_id", String(255), primary_key=True),
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
        # The embed step's twin lookup: a chunk hash shared by many rows is found by index.
        Index("ix_vfs_chunks_content_hash", "content_hash"),
        schema=schema,
        sqlite_autoincrement=True,
    )
    if native_embedding is not None:
        _attach_pgvector_ddl(metadata, chunks, native_embedding)

    # Embed refusals: a text the provider refused alone, keyed by its hash and
    # the provider facts the refusal depends on; -1 stands for an undeclared cap.
    embed_refusals = Table(
        "vfs_embed_refusals",
        metadata,
        Column("content_hash", String(64), primary_key=True),
        Column("model_id", String(MAX_MODEL_ID_LENGTH), nullable=False),
        Column("max_input_tokens", Integer, nullable=False),
        Column("max_batch_tokens", Integer, nullable=False),
        schema=schema,
    )

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
        Column("edge_type", String(MAX_SEGMENT_LENGTH), nullable=False),
        Column("weight", Float),
        Column("distance", Float),
        Column("provenance", String(16), nullable=False),
        # The referring line an extracted edge was read from, folded; NULL
        # on every authored row.
        Column("context", String(MAX_LINK_CONTEXT_LENGTH)),
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
            # The stub narrows ``dialect`` to str; the runtime accepts a tuple.
        ).ddl_if(dialect=("sqlite", "postgresql")),  # ty: ignore[invalid-argument-type]
        schema=schema,
        sqlite_autoincrement=True,
    )

    # Single-row mount metadata: the schema-format version first touch
    # verifies and the durable mount identity that keys the per-mount
    # advisory lock. Versions are per-entry monotone values on their own
    # rows — the mount keeps no version sequence.
    meta = Table(
        "vfs_meta",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("schema_format_version", Integer, nullable=False),
        Column("mount_identity", String(ULID_LENGTH), nullable=False),
        # The mount's one embedding space — the provider- and dimension-
        # qualified model id and its width, stamped by the first embed.
        Column("embedding_model", String(MAX_MODEL_ID_LENGTH)),
        Column("embedding_dimension", Integer),
        # The grant spine's revision: every grant, posture, or membership
        # write bumps it first, so the bump is also the admin writes' lock.
        Column("grant_revision", BigInteger, nullable=False, default=0),
        Column("created_at", _timestamp()),
        CheckConstraint("id = 1", name="ck_vfs_meta_single_row"),
        schema=schema,
    )

    # The published epoch, whose one-row flip publishes a rebuilt index, and the single-runner lease: on a
    # row of their own, so the admin lock's row is never one a lease-held commit takes.
    index_state = Table(
        "vfs_index_state",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("current_gram_epoch", Integer),
        # Bumped by every publish, full or delta: the readers' coherence token beside the pointer.
        Column("index_generation", Integer, nullable=False, default=0, server_default="0"),
        Column("lease_holder", String(ULID_LENGTH)),
        Column("lease_heartbeat", BigInteger),
        CheckConstraint("id = 1", name="ck_vfs_index_state_single_row"),
        schema=schema,
    )

    # The serialized verbs' lock row: locked for the transaction, read by
    # nothing else, so no other path ever waits behind a verb.
    lock = Table(
        "vfs_lock",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        CheckConstraint("id = 1", name="ck_vfs_lock_single_row"),
        schema=schema,
    )

    # One row per gram-index build: the two-part fingerprint (format
    # version, options hash) — coverage is per-row flag state, not a
    # version threshold. Rows outside the current epoch are reclaimable
    # garbage, swept by the rebuild verb.
    gram_epochs = Table(
        "vfs_gram_epochs",
        metadata,
        Column("epoch", Integer, primary_key=True, autoincrement=False),
        Column("format_version", Integer, nullable=False),
        Column("options_hash", String(64), nullable=False),
        Column("created_at", _timestamp()),
        # A delta: the base it was built on, and when its publish made it live; both null for a full epoch.
        Column("base_epoch", Integer),
        Column("published_at", _timestamp()),
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
        Column("postings", LargeBinary(), nullable=False),
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
    # rebuilt whole per rebuild: one doc row per chunk with its exact
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
        Column("doc_ids", LargeBinary(), nullable=False),
        Column("tfs", LargeBinary(), nullable=False),
        Column("dls", LargeBinary(), nullable=False),
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
        Column("blocks", LargeBinary(), nullable=False),
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
        Column("signal", String(MAX_SIGNAL_NAME_LENGTH), primary_key=True),
        Column("generation", String(ULID_LENGTH), primary_key=True),
        Column("value", Float, nullable=False),
        schema=schema,
    )
    signal_epochs = Table(
        "vfs_signal_epochs",
        metadata,
        Column("signal", String(MAX_SIGNAL_NAME_LENGTH), primary_key=True),
        Column("generation", String(ULID_LENGTH), nullable=False),
        Column("options_hash", String(64), nullable=False),
        Column("row_count", Integer, nullable=False),
        Column("created_at", _timestamp()),
        schema=schema,
    )

    # Row grants: one row per (principal, prefix), additive-only — a row
    # widens, nothing narrows except the everyone rows (principal ``*``)
    # that carry a mount's posture. Prefixes are mount-relative canonical
    # paths in the entries table's collation. A surrogate key keeps the
    # wide pair in a secondary index, inside the tightest clustered-key cap vfs has met.
    grants = Table(
        "vfs_grants",
        metadata,
        Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
        Column("principal_id", String(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
        Column("path_prefix", BytewiseString(MAX_PATH_LENGTH), nullable=False),
        Column("level", String(16), nullable=False),
        Column("granted_by", String(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
        Column("granted_at", _timestamp(), nullable=False),
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
        Column("principal_id", String(MAX_PRINCIPAL_ID_LENGTH), primary_key=True),
        Column("group_id", String(MAX_PRINCIPAL_ID_LENGTH), primary_key=True),
        Column("granted_by", String(MAX_PRINCIPAL_ID_LENGTH), nullable=False),
        Column("granted_at", _timestamp(), nullable=False),
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
        Column("principal_id", String(MAX_PRINCIPAL_ID_LENGTH), primary_key=True),
        Column("revision", BigInteger, nullable=False),
        schema=schema,
    )

    return VFSTables(
        metadata=metadata,
        entry=entry,
        content=content,
        blobs=blobs,
        versions=versions,
        version_subjects=version_subjects,
        chunks=chunks,
        edges=edges,
        meta=meta,
        index_state=index_state,
        lock=lock,
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
        embed_refusals=embed_refusals,
        relabels=relabels,
        principal_revisions=principal_revisions,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _attach_blob_storage_ddl(blobs: Table) -> None:
    """Skip TOAST compression on the bytes body — PostgreSQL only.

    File bytes are mostly pre-compressed, so compressing them again buys
    nothing, and EXTERNAL storage makes a ``substring`` a ranged fetch.
    """
    external = DDL(f"ALTER TABLE {blobs.fullname} ALTER COLUMN data SET STORAGE EXTERNAL").execute_if(
        dialect="postgresql"
    )
    event.listen(blobs, "after_create", external)


def _attach_pgvector_ddl(metadata: MetaData, chunks: Table, config: NativeEmbeddingConfig) -> None:
    """The ANN index behind a native pgvector column — PostgreSQL only.

    A dialect-conditional DDL event: every other engine provisions its
    own column with no index, so one table definition serves the whole
    matrix. A space wider than pgvector's index cap gets the column and
    an exact scan, never a failing DDL. The extension itself is a
    precondition first touch proves, never DDL vfs runs: creating it
    needs rights an application role does not have on a managed server.
    """
    if config.dimension > PGVECTOR_INDEX_MAX_DIMENSION:
        return
    index = DDL(
        f"CREATE INDEX IF NOT EXISTS ix_vfs_chunks_embedding ON {chunks.fullname} "
        f"USING {config.index_method} (embedding {config.operator_class})"
    ).execute_if(dialect="postgresql")
    event.listen(chunks, "after_create", index)
