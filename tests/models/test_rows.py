"""Tests for the hand-written Core row definitions and their model lockstep."""

from __future__ import annotations

from datetime import UTC, datetime
from types import UnionType
from typing import Union, cast, get_args, get_origin
from uuid import UUID

import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Double,
    Engine,
    LargeBinary,
    MetaData,
    String,
    Table,
    create_engine,
    create_mock_engine,
    insert,
    inspect,
    select,
    type_coerce,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import ColumnDefault, CreateIndex, CreateTable
from ulid import ULID

from vfs.models import Chunk, Edge, Entry, Version
from vfs.models.lexical import MAX_TERM_BYTES
from vfs.models.links import MAX_LINK_CONTEXT_LENGTH
from vfs.models.rows import (
    CHUNK_ROW_ONLY_COLUMNS,
    EDGE_ROW_ONLY_COLUMNS,
    ENCODING_DELTA_VARINT,
    ENTRY_BODY_HOMES,
    ENTRY_CONTENT_FIELDS,
    ENTRY_ROW_ONLY_COLUMNS,
    MAX_PRINCIPAL_ID_LENGTH,
    MODEL_COLUMN_RENAMES,
    MODEL_FIELD_ONLY,
    MODEL_OWNER_FIELDS,
    SCHEMA_FORMAT_VERSION,
    TABLE_FAMILY_CACHE,
    ULID_LENGTH,
    VERSION_ROW_ONLY_COLUMNS,
    BytewiseString,
    ULIDBytes,
    ULIDKey,
    VFSTables,
    build_vfs_tables,
    entry_key_of,
)
from vfs.models.vector import NativeEmbeddingConfig, VectorType
from vfs.paths import MAX_PATH_LENGTH, MAX_SEGMENT_LENGTH, Path

TABLE_ATTRS = (
    "entry",
    "content",
    "versions",
    "version_subjects",
    "chunks",
    "edges",
    "meta",
    "index_state",
    "lock",
    "gram_epochs",
    "posting_list",
    "segments",
    "lex_docs",
    "lex_postings",
    "lex_df",
    "lex_stats",
)

# Postgres truncates identifiers past 63 bytes; the tightest cap among the engines.
POSTGRES_IDENTIFIER_CAP = 63

# The metadata family: each model, its table attribute, and the table's
# columns with no model field (the id backbone and owner references).
METADATA_MODELS = (
    (Version, "versions", VERSION_ROW_ONLY_COLUMNS),
    (Chunk, "chunks", CHUNK_ROW_ONLY_COLUMNS),
    (Edge, "edges", EDGE_ROW_ONLY_COLUMNS),
)


@pytest.fixture
def tables() -> VFSTables:
    return build_vfs_tables()


# ---------------------------------------------------------------------------
# Model ⇄ row drift — each model pinned to its own table
# ---------------------------------------------------------------------------


def _allows_none(annotation: object) -> bool:
    """Whether the annotation admits ``None`` (i.e. is ``X | None``)."""
    if get_origin(annotation) in {Union, UnionType}:
        return type(None) in get_args(annotation)
    return False


class TestEntryRowDrift:
    def test_entries_columns_are_the_resident_fields_plus_row_only(self, tables: VFSTables) -> None:
        resident = set(Entry.model_fields) - ENTRY_CONTENT_FIELDS
        assert set(tables.entry.c.keys()) == resident | ENTRY_ROW_ONLY_COLUMNS

    def test_body_tables_home_the_bodies(self, tables: VFSTables) -> None:
        assert set(ENTRY_BODY_HOMES) == ENTRY_CONTENT_FIELDS
        for field, home in ENTRY_BODY_HOMES.items():
            assert field in Entry.model_fields
            assert field in getattr(tables, home).c
            assert field not in tables.entry.c

    def test_row_only_columns_never_exist_on_entry(self) -> None:
        assert not ENTRY_ROW_ONLY_COLUMNS & set(Entry.model_fields)

    def test_nullability_matches_entry_optionality_for_resident_fields(self, tables: VFSTables) -> None:
        for name, field in Entry.model_fields.items():
            if name in ENTRY_CONTENT_FIELDS:
                continue
            column = tables.entry.c[name]
            assert column.nullable == _allows_none(field.annotation), (
                f"nullability drift on {name!r}: column nullable={column.nullable}, Entry annotation {field.annotation}"
            )


class TestMetadataModelRowDrift:
    @pytest.mark.parametrize(("model", "table_attr", "row_only"), METADATA_MODELS)
    def test_model_fields_are_the_table_columns(self, tables: VFSTables, model, table_attr, row_only) -> None:
        owner = MODEL_OWNER_FIELDS[model.__name__]
        field_only = MODEL_FIELD_ONLY[model.__name__]
        renames = MODEL_COLUMN_RENAMES[model.__name__]
        mirrored = {renames.get(field, field) for field in set(model.model_fields) - owner - field_only}
        assert set(getattr(tables, table_attr).c.keys()) == mirrored | row_only

    @pytest.mark.parametrize(("model", "table_attr", "row_only"), METADATA_MODELS)
    def test_owner_references_are_path_fields(self, tables: VFSTables, model, table_attr, row_only) -> None:
        # The models reference their owner by Path; persistence resolves the
        # Path to the entry identity the row-only columns carry.
        for name in MODEL_OWNER_FIELDS[model.__name__]:
            assert model.model_fields[name].annotation is Path
        assert not MODEL_OWNER_FIELDS[model.__name__] & set(getattr(tables, table_attr).c.keys())

    @pytest.mark.parametrize(("model", "table_attr", "row_only"), METADATA_MODELS)
    def test_row_only_columns_never_exist_on_the_model(self, tables: VFSTables, model, table_attr, row_only) -> None:
        assert not row_only & set(model.model_fields)

    @pytest.mark.parametrize(("model", "table_attr", "row_only"), METADATA_MODELS)
    def test_nullability_matches_model_optionality(self, tables: VFSTables, model, table_attr, row_only) -> None:
        table = getattr(tables, table_attr)
        renames = MODEL_COLUMN_RENAMES[model.__name__]
        for name, field in model.model_fields.items():
            if name in MODEL_OWNER_FIELDS[model.__name__] | MODEL_FIELD_ONLY[model.__name__]:
                continue
            column = table.c[renames.get(name, name)]
            assert column.nullable == _allows_none(field.annotation), (
                f"nullability drift on {model.__name__}.{name!r}: column nullable={column.nullable}"
            )


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------


class TestBuildVFSTables:
    def test_one_metadata_owns_the_whole_family(self, tables: VFSTables) -> None:
        assert set(tables.metadata.tables) == {
            "vfs_entries",
            "vfs_content",
            "vfs_blobs",
            "vfs_versions",
            "vfs_version_subjects",
            "vfs_chunks",
            "vfs_edges",
            "vfs_meta",
            "vfs_index_state",
            "vfs_lock",
            "vfs_gram_epochs",
            "vfs_grams_posting_list",
            "vfs_segments",
            "vfs_lex_docs",
            "vfs_lex_postings",
            "vfs_lex_df",
            "vfs_lex_stats",
            "vfs_signals",
            "vfs_signal_epochs",
            "vfs_grants",
            "vfs_memberships",
            "vfs_relabels",
            "vfs_principal_revisions",
            "vfs_embed_refusals",
        }
        for attr in TABLE_ATTRS:
            assert getattr(tables, attr).metadata is tables.metadata
        # The pointer and the lease live on a row of their own, apart from the admin lock's.
        assert not {"current_gram_epoch", "re" + "index_holder", "re" + "index_heartbeat"} & set(tables.meta.c.keys())
        assert set(tables.index_state.c.keys()) == {
            "id",
            "current_gram_epoch",
            "index_generation",
            "lease_holder",
            "lease_heartbeat",
        }
        assert tables.index_state.c.index_generation.nullable is False
        assert {"base_epoch", "published_at"} <= set(tables.gram_epochs.c.keys())
        assert tables.entry.c.indexed_epoch.nullable is True
        keys = {str(index.name): [column.name for column in index.columns] for index in tables.entry.indexes}
        assert keys["ix_vfs_entries_index_pending"] == ["encoded", "chunked", "indexable", "deleted_at", "id"]
        assert keys["ix_vfs_entries_render_status"] == ["render_status", "deleted_at", "id"]
        assert SCHEMA_FORMAT_VERSION == 28

    def test_mounts_in_different_schemas_never_share_schema_objects(self, tables: VFSTables) -> None:
        other = build_vfs_tables(schema="tenant")
        assert other.metadata is not tables.metadata
        assert other.entry is not tables.entry

    def test_schema_applies_to_every_table(self) -> None:
        scoped = build_vfs_tables(schema="tenant")
        assert {getattr(scoped, attr).schema for attr in TABLE_ATTRS} == {"tenant"}

    def test_identity_backbone(self, tables: VFSTables) -> None:
        assert tables.entry.c.id.primary_key
        assert tables.entry.kwargs["sqlite_autoincrement"] is True
        assert tables.entry.c.entry_id.unique
        assert isinstance(tables.entry.c.entry_id.type, ULIDKey)
        assert isinstance(tables.entry.c.parent_id.type, ULIDKey)
        assert tables.entry.c.parent_id.nullable  # null for the root row
        assert tables.entry.c.path.unique

    def test_create_arbitration_index_is_parent_id_name(self, tables: VFSTables) -> None:
        unique = {c.name for c in tables.entry.constraints if c.name == "uq_vfs_entries_parent_name"}
        assert unique == {"uq_vfs_entries_parent_name"}

    def test_path_and_name_pin_bytewise_order_per_dialect(self, tables: VFSTables) -> None:
        for column in (tables.entry.c.path, tables.entry.c.name):
            kind = column.type
            assert isinstance(kind, BytewiseString)
            postgres = kind.load_dialect_impl(postgresql.dialect())
            assert isinstance(postgres, String) and postgres.collation == "C"

    def test_sqlite_and_any_other_engine_take_the_unpinned_string(self, tables: VFSTables) -> None:
        # SQLite's BINARY collation is bytewise already; any other engine gets plain String,
        # an accepted degradation pinned so it stays deliberate.
        kind = tables.entry.c.path.type
        assert isinstance(kind, BytewiseString)
        fallback = kind.load_dialect_impl(sqlite.dialect())
        assert isinstance(fallback, String) and fallback.collation is None
        assert kind.compile(dialect=sqlite.dialect()) == f"VARCHAR({MAX_PATH_LENGTH})"

    def test_a_bytewise_string_reads_text_and_bytes_as_text(self) -> None:
        kind = BytewiseString(MAX_PATH_LENGTH)
        assert kind.process_result_value("/é.txt", sqlite.dialect()) == "/é.txt"
        assert kind.process_result_value("/é.txt".encode(), sqlite.dialect()) == "/é.txt"

    def test_bodies_live_outside_entries_and_sit_last(self, tables: VFSTables) -> None:
        assert "content" not in tables.entry.c
        assert "version_diff" not in tables.entry.c
        assert list(tables.content.c.keys())[-1] == "content"
        assert list(tables.blobs.c.keys())[-1] == "data"
        assert list(tables.versions.c.keys())[-3:] == ["content", "version_diff", "data"]
        assert list(tables.chunks.c.keys())[-1] == "content"

    def test_dependent_tables_key_on_entry_identity_never_path(self, tables: VFSTables) -> None:
        for table in (tables.content, tables.versions, tables.chunks):
            assert isinstance(table.c.entry_id.type, ULIDKey)
            assert not any("path" in column.name for column in table.c)
        for name in ("source_id", "target_id"):
            assert isinstance(tables.edges.c[name].type, ULIDKey)
        assert not any("path" in column.name for column in tables.edges.c)

    def test_edges_are_narrow_id_triples_indexed_both_directions(self, tables: VFSTables) -> None:
        expected = {"id", "source_id", "target_id", "edge_type", "weight", "distance", "provenance", "context"}
        assert expected == set(tables.edges.c.keys())
        assert tables.edges.c.provenance.nullable is False
        assert tables.edges.c.context.nullable is True
        assert cast("String", tables.edges.c.context.type).length == MAX_LINK_CONTEXT_LENGTH
        assert tables.edges.c.provenance.default is None
        by_name = {str(index.name): index for index in tables.edges.indexes}
        assert [c.name for c in by_name["ix_vfs_edges_fwd"].columns] == ["source_id", "edge_type"]
        assert [c.name for c in by_name["ix_vfs_edges_rev"].columns] == ["target_id", "edge_type"]

    def test_single_parent_index_is_filtered_and_gated_by_dialect(self, tables: VFSTables) -> None:
        # Emitted only where the engine has partial/filtered indexes; a plain
        # unique index on target_id alone would be wrong everywhere else.
        by_name = {str(index.name): index for index in tables.edges.indexes}
        fs_parent = by_name["uq_vfs_edges_fs_parent"]
        assert fs_parent.unique
        assert [c.name for c in fs_parent.columns] == ["target_id"]
        for dialect_name in ("sqlite", "postgresql"):
            assert str(fs_parent.dialect_options[dialect_name]["where"]) == "edge_type = 'fs'"

    @pytest.mark.parametrize(
        ("url", "emitted"),
        [("sqlite://", True), ("postgresql://", True), ("mssql://", False), ("mariadb://", False)],
    )
    def test_single_parent_index_emission_per_dialect(self, url: str, emitted: bool) -> None:
        tables = build_vfs_tables()
        statements: list[str] = []

        def record(sql: object, *args: object, **kwargs: object) -> None:
            statements.append(str(sql.compile(dialect=engine.dialect)))  # ty: ignore[unresolved-attribute]

        engine = create_mock_engine(url, record)
        tables.metadata.create_all(engine, checkfirst=False)
        index_ddl = [s for s in statements if "CREATE UNIQUE INDEX uq_vfs_edges_fs_parent" in s]
        assert bool(index_ddl) is emitted

    def test_posting_rows_are_epoch_scoped_with_varint_default(self, tables: VFSTables) -> None:
        assert [c.name for c in tables.posting_list.primary_key.columns] == ["epoch", "gram_key"]
        default = tables.posting_list.c.encoding.default
        assert isinstance(default, ColumnDefault)
        assert default.arg == ENCODING_DELTA_VARINT
        expected = {"epoch", "format_version", "options_hash", "created_at", "base_epoch", "published_at"}
        assert expected == set(tables.gram_epochs.c.keys())

    def test_lexical_tables_are_epoch_scoped_and_keyed_for_term_runs(self, tables: VFSTables) -> None:
        # One term's blocks are a contiguous run under (epoch, term, block_no);
        # terms are folded text, bytewise — an accent-unifying collation
        # would collide the key — and capped at the tokenizer's byte ceiling.
        assert [c.name for c in tables.lex_docs.primary_key.columns] == ["epoch", "chunk_id"]
        assert [c.name for c in tables.lex_postings.primary_key.columns] == ["epoch", "term", "block_no"]
        assert [c.name for c in tables.lex_df.primary_key.columns] == ["epoch", "term"]
        assert [c.name for c in tables.lex_stats.primary_key.columns] == ["epoch"]
        for table in (tables.lex_postings, tables.lex_df):
            assert isinstance(table.c.term.type, BytewiseString)
            assert table.c.term.type.length == MAX_TERM_BYTES
        assert isinstance(tables.lex_docs.c.entry_id.type, ULIDKey)
        by_name = {str(index.name): index for index in tables.lex_docs.indexes}
        assert [c.name for c in by_name["ix_vfs_lex_docs_entry"].columns] == ["epoch", "entry_id"]
        for column in (
            tables.lex_df.c.idf,
            tables.lex_df.c.max_weight,
            tables.lex_stats.c.avg_dl,
            tables.lex_stats.c.k1,
            tables.lex_stats.c.b,
        ):
            assert isinstance(column.type, Double)
        blobs = (
            tables.lex_postings.c.doc_ids,
            tables.lex_postings.c.tfs,
            tables.lex_postings.c.dls,
            tables.lex_df.c.blocks,
        )
        for column in blobs:
            assert isinstance(column.type, LargeBinary)
        for table in (tables.lex_docs, tables.lex_postings, tables.lex_df, tables.lex_stats):
            assert table.kwargs["sqlite_with_rowid"] is False
        assert "WITHOUT ROWID" in str(CreateTable(tables.lex_postings).compile(dialect=sqlite.dialect()))
        assert tables.epoch_scoped() == (
            tables.posting_list,
            tables.lex_docs,
            tables.lex_postings,
            tables.lex_df,
            tables.lex_stats,
            tables.gram_epochs,
        )

    def test_segment_postings_key_on_segment_then_entry(self, tables: VFSTables) -> None:
        # Verbatim bytewise segment text first (the term lookup), entry
        # identity second; the secondary index serves delete-by-entry.
        assert [c.name for c in tables.segments.primary_key.columns] == ["segment", "entry_id"]
        assert isinstance(tables.segments.c.segment.type, BytewiseString)
        assert tables.segments.c.segment.type.length == MAX_SEGMENT_LENGTH
        assert isinstance(tables.segments.c.entry_id.type, ULIDKey)
        by_name = {str(index.name): index for index in tables.segments.indexes}
        assert [c.name for c in by_name["ix_vfs_segments_entry"].columns] == ["entry_id"]

    def test_ext_kind_composite_index(self, tables: VFSTables) -> None:
        by_name = {str(index.name): index for index in tables.entry.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_ext_kind"].columns] == ["ext", "kind"]

    def test_everyone_level_is_indexed_with_path_only(self, tables: VFSTables) -> None:
        # The everyone leg seeks (everyone_level, path); its leading column
        # serves the unscoped read, so no single-column index is built.
        by_name = {str(index.name): index for index in tables.entry.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_everyone_path"].columns] == ["everyone_level", "path"]
        assert not any([c.name for c in index.columns] == ["everyone_level"] for index in tables.entry.indexes)
        assert tables.entry.c.everyone_level.nullable is False and tables.entry.c.everyone_level.default is None

    def test_the_tombstone_is_two_nullable_columns_each_indexed_alone(self, tables: VFSTables) -> None:
        # NULL on every live row, so each index holds the deleted rows alone, the first by its
        # predicate: the view and the sweep seek deleted_at, restore and the purge a root's set.
        deleted_at, root = tables.entry.c.deleted_at, tables.entry.c.trash_root_id
        assert deleted_at.nullable is True and root.nullable is True and isinstance(root.type, ULIDKey)
        by_name = {str(index.name): index for index in tables.entry.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_deleted_at"].columns] == ["deleted_at"]
        assert [c.name for c in by_name["ix_vfs_entries_trash_root"].columns] == ["trash_root_id"]
        assert not any("origin" in name or "restore" in name for name in by_name)

    def test_the_listing_indexes_hold_one_side_of_the_tombstone_each(self, tables: VFSTables) -> None:
        # A live listing page seeks the live rows alone; the tombstone index never offers it a seek.
        by_name = {str(index.name): index for index in tables.entry.indexes}
        sides = {
            "ix_vfs_entries_live_children": (["parent_id", "name"], "deleted_at IS NULL"),
            "ix_vfs_entries_live_path": (["path"], "deleted_at IS NULL"),
            "ix_vfs_entries_deleted_at": (["deleted_at"], "deleted_at IS NOT NULL"),
        }
        for name, (columns, predicate) in sides.items():
            index = by_name[name]
            assert [c.name for c in index.columns] == columns
            for dialect in ("sqlite", "postgresql"):
                assert str(index.dialect_options[dialect]["where"]) == predicate, (name, dialect)

    def test_the_stamps_and_the_marks_carry_a_revision(self, tables: VFSTables) -> None:
        # One stamp per principal ever named by an admin write, keyed by
        # the id alone; a relabel mark carries the revision it was planted under.
        stamps = tables.principal_revisions
        assert [c.name for c in stamps.primary_key.columns] == ["principal_id"]
        assert (
            isinstance(stamps.c.principal_id.type, String)
            and stamps.c.principal_id.type.length == MAX_PRINCIPAL_ID_LENGTH
        )
        assert stamps.c.revision.nullable is False and isinstance(stamps.c.revision.type, BigInteger)
        marks = tables.relabels
        assert marks.c.revision.nullable is False and isinstance(marks.c.revision.type, BigInteger)
        assert marks.c.cursor.nullable is True

    def test_encoded_kind_composite_index(self, tables: VFSTables) -> None:
        by_name = {str(index.name): index for index in tables.entry.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_encoded_kind"].columns] == ["encoded", "kind"]
        assert "ix_vfs_entries_encoded" not in by_name

    def test_default_embedding_is_portable(self, tables: VFSTables) -> None:
        vector_type = tables.chunks.c.embedding.type
        assert isinstance(vector_type, VectorType)
        assert vector_type.native is False
        assert vector_type.dimension is None

    def test_native_embedding_shapes_the_chunk_column(self) -> None:
        native = build_vfs_tables(
            native_embedding=NativeEmbeddingConfig(dimension=8, model_name="m"),
        )
        vector_type = native.chunks.c.embedding.type
        assert isinstance(vector_type, VectorType)
        assert vector_type.native is True
        assert vector_type.dimension == 8
        assert vector_type.model_name == "m"
        assert vector_type.postgres_index_method == "hnsw"
        assert vector_type.postgres_operator_class == "vector_cosine_ops"


# ---------------------------------------------------------------------------
# DDL and round-trip — the schema must accept real domain data
# ---------------------------------------------------------------------------


def _entries_row(entry: Entry, *, entry_id: str, parent_id: str | None) -> dict[str, object]:
    """The entries-table row for *entry*: resident fields plus the storage-stamped columns.

    ``version`` is minted storage-side (never authored on an Entry), so the
    helper stamps a fresh row's 1 the way the write path would.
    """
    resident = entry.model_dump(exclude=set(ENTRY_CONTENT_FIELDS) | set(Entry.model_computed_fields))
    stamped = {"entry_id": entry_id, "parent_id": parent_id, "version": 1, "everyone_level": 2}
    return {**resident, **stamped}


class TestULIDKey:
    """The one identity-conversion home: storage form and round-trip per arm."""

    def test_storage_form_is_binary_16_per_dialect_never_text(self) -> None:
        key = ULIDKey()
        forms = {
            name: key.compile(dialect=dialect)
            for name, dialect in (
                ("postgresql", postgresql.dialect()),
                ("sqlite", sqlite.dialect()),
                # A dialect served by the floor whose supports_native_uuid flag
                # lies about sort order: the allow-list must hold it to bytes.
                ("mariadb", mariadb.MariaDBDialect()),
            )
        }
        assert forms == {"postgresql": "UUID", "sqlite": "BINARY(16)", "mariadb": "BINARY(16)"}

    def test_bytes_arm_round_trips_and_sorts_like_the_string(self) -> None:
        key = ULIDKey()
        dialect = sqlite.dialect()
        ulids = sorted(str(ULID()) for _ in range(64))
        bound = [key.process_bind_param(u, dialect) for u in ulids]
        assert all(isinstance(b, bytes) and len(b) == 16 for b in bound)
        # Stored byte order equals 26-char string order — the property
        # that keeps binary identity indexes time-local.
        assert sorted(bound) == bound
        assert [key.process_result_value(b, dialect) for b in bound] == ulids
        assert key.process_bind_param(None, dialect) is None
        assert key.process_result_value(None, dialect) is None

    def test_uuid_arm_round_trips_and_sorts_like_the_string(self) -> None:
        key = ULIDKey()
        dialect = postgresql.dialect()
        ulids = sorted(str(ULID()) for _ in range(64))
        bound = [key.process_bind_param(u, dialect) for u in ulids]
        assert all(isinstance(b, UUID) for b in bound)
        assert sorted(bound) == bound
        assert [key.process_result_value(b, dialect) for b in bound] == ulids
        assert key.process_bind_param(None, dialect) is None
        assert key.process_result_value(None, dialect) is None


class TestULIDBytes:
    """The identity column read as its 16 stored bytes, and text turned into those bytes."""

    def test_the_id_reads_as_bytes_and_as_text_alike(self) -> None:
        """Mutation guarded: a bytes arm or an ``entry_key_of`` that reorders or drops a byte."""
        metadata = MetaData()
        ids = Table("ids", metadata, Column("entry_id", ULIDKey(), nullable=False))
        engine = create_engine("sqlite://")
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(insert(ids), [{"entry_id": str(ULID())} for _ in range(1_000)])
            stmt = select(ids.c.entry_id, type_coerce(ids.c.entry_id, ULIDBytes()).label("entry_key"))
            rows = conn.execute(stmt).all()
        engine.dispose()
        assert len(rows) == 1_000
        assert sum(entry_key_of(row.entry_id) != row.entry_key for row in rows) == 0
        assert all(isinstance(row.entry_key, bytes) and len(row.entry_key) == 16 for row in rows)

    def test_the_uuid_arm_hands_on_its_bytes(self) -> None:
        key = ULIDBytes()
        ulid = ULID()
        assert key.process_result_value(ulid.to_uuid(), postgresql.dialect()) == ulid.bytes
        assert key.process_result_value(ulid.bytes, sqlite.dialect()) == ulid.bytes
        assert key.process_result_value(None, sqlite.dialect()) is None
        assert key.compile(dialect=postgresql.dialect()) == "UUID"
        assert key.compile(dialect=sqlite.dialect()) == "BINARY(16)"


class TestFixedNames:
    @staticmethod
    def _identifiers(tables: VFSTables) -> list[str]:
        names = [table.name for table in tables.metadata.tables.values()]
        for table in tables.metadata.tables.values():
            names += [c.name for c in table.constraints if isinstance(c.name, str)]
            names += [i.name for i in table.indexes if isinstance(i.name, str)]
        return names

    def test_every_identifier_carries_the_fixed_prefix(self, tables: VFSTables) -> None:
        names = self._identifiers(tables)
        assert tables.entry.name == "vfs_entries"
        assert all(name.startswith(("vfs_", "ix_vfs_", "uq_vfs_", "ck_vfs_")) for name in names)

    def test_every_identifier_fits_the_postgres_cap(self, tables: VFSTables) -> None:
        assert max(len(name) for name in self._identifiers(tables)) <= POSTGRES_IDENTIFIER_CAP

    def test_a_schema_moves_the_family_and_keeps_its_names(self, tables: VFSTables) -> None:
        scoped = build_vfs_tables(schema="tenant")
        assert sorted(self._identifiers(scoped)) == sorted(self._identifiers(tables))
        assert scoped.entry.fullname == "tenant.vfs_entries"

    def test_the_family_ddl_compiles_on_postgres(self, tables: VFSTables) -> None:
        dialect = postgresql.dialect()
        for table in tables.metadata.tables.values():
            CreateTable(table).compile(dialect=dialect)
            for index in table.indexes:
                CreateIndex(index).compile(dialect=dialect)


class TestDDL:
    def test_one_create_all_provisions_the_whole_family(self, tables: VFSTables, engine: Engine) -> None:
        tables.metadata.create_all(engine)
        assert set(inspect(engine).get_table_names()) == set(tables.metadata.tables)

    def test_every_instant_keeps_sub_second_precision_and_its_zone_on_every_engine(self, tables: VFSTables) -> None:
        columns = [column for table in tables.metadata.tables.values() for column in table.columns]
        instants = [column for column in columns if isinstance(column.type, DateTime)]
        assert {column.name for column in instants} >= {"created_at", "updated_at", "deleted_at", "granted_at"}
        compiled = {
            (dialect.name, column.type.compile(dialect=dialect))
            for column in instants
            for dialect in (postgresql.dialect(), sqlite.dialect())
        }
        assert compiled == {("postgresql", "TIMESTAMP WITH TIME ZONE"), ("sqlite", "DATETIME")}

    def test_id_keys_declare_identity_in_ddl(self, tables: VFSTables) -> None:
        # Postgres moved off BIGSERIAL: the id keys render IDENTITY.
        for table in (tables.entry, tables.chunks, tables.edges):
            ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
            assert "GENERATED BY DEFAULT AS IDENTITY" in ddl
        assert "BIGSERIAL" not in str(CreateTable(tables.entry).compile(dialect=postgresql.dialect()))

    def test_whole_family_ddl_compiles_on_every_dialect(self, tables: VFSTables) -> None:
        # No column type may fail DDL compile on either engine.
        for module in (postgresql, sqlite):
            dialect = module.dialect()
            for table in tables.metadata.tables.values():
                CreateTable(table).compile(dialect=dialect)
                for index in table.indexes:
                    CreateIndex(index).compile(dialect=dialect)

    def test_native_embedding_ddl_compiles_off_postgres(self, engine: Engine) -> None:
        native = build_vfs_tables(native_embedding=NativeEmbeddingConfig(dimension=8))
        native.metadata.create_all(engine)  # VectorType falls back to the packed binary column

    def test_entry_splits_into_entries_plus_content_and_reads_back(self, tables: VFSTables, engine: Engine) -> None:
        tables.metadata.create_all(engine)
        entry = Entry(path=Path("/docs/a.md"), content="hello")
        ulid = "0" * ULID_LENGTH
        with engine.begin() as conn:
            pk = conn.execute(
                insert(tables.entry), [_entries_row(entry, entry_id=ulid, parent_id=None)]
            ).inserted_primary_key
            conn.execute(
                insert(tables.content),
                [{"entry_id": ulid, "created_at": datetime.now(UTC), "content": entry.content}],
            )
            row = conn.execute(select(tables.entry)).mappings().one()
            body = conn.execute(select(tables.content.c.content).where(tables.content.c.entry_id == ulid)).scalar_one()
        assert pk is not None
        assert row["path"] == "/docs/a.md"
        assert row["entry_id"] == ulid
        assert row["version"] == 1
        assert "content" not in row
        assert body == "hello"

    def test_meta_table_enforces_the_single_row(self, tables: VFSTables, engine: Engine) -> None:
        tables.metadata.create_all(engine)
        row = {
            "id": 1,
            "schema_format_version": SCHEMA_FORMAT_VERSION,
            "mount_identity": "0" * ULID_LENGTH,
        }
        with engine.begin() as conn:
            conn.execute(insert(tables.meta), [row])
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert(tables.meta), [{**row, "id": 2}])

    def test_duplicate_names_under_one_parent_are_refused(self, tables: VFSTables, engine: Engine) -> None:
        tables.metadata.create_all(engine)
        first = Entry(path=Path("/docs/a.md"), content="x")
        shared_parent = "2" * ULID_LENGTH
        with engine.begin() as conn:
            conn.execute(
                insert(tables.entry), [_entries_row(first, entry_id="0" * ULID_LENGTH, parent_id=shared_parent)]
            )
        clone = Entry(path=Path("/docs2/a.md"), content="y")  # distinct path, same (parent_id, name)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                insert(tables.entry), [_entries_row(clone, entry_id="1" * ULID_LENGTH, parent_id=shared_parent)]
            )


class TestFamilySharing:
    def test_mounts_of_one_shape_share_one_family(self) -> None:
        # The family is immutable after construction and carries no engine
        # binding, so a second mount of the same shape gets the same objects.
        assert build_vfs_tables() is build_vfs_tables()
        assert build_vfs_tables(schema="tenant") is build_vfs_tables(schema="tenant")
        assert build_vfs_tables(schema="tenant") is not build_vfs_tables()
        native = NativeEmbeddingConfig(dimension=8)
        assert build_vfs_tables(native_embedding=native) is build_vfs_tables(native_embedding=native)
        assert build_vfs_tables(native_embedding=native) is not build_vfs_tables()

    def test_the_family_cache_is_bounded(self) -> None:
        # A host placing thousands of tenants in their own schemas must not
        # hold every family forever; cold shapes rebuild.
        assert build_vfs_tables.cache_info().maxsize == TABLE_FAMILY_CACHE
