"""Tests for the hand-written Core row definitions and their model lockstep."""

from __future__ import annotations

from types import UnionType
from typing import Union, get_args, get_origin
from uuid import UUID

import pytest
from sqlalchemy import Engine, String, insert, inspect, select
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mssql import pymssql
from sqlalchemy.dialects.mysql import mariadb
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import ColumnDefault, CreateIndex, CreateTable
from ulid import ULID

from vfs.models import Chunk, Edge, Entry, Version
from vfs.models.rows import (
    CHUNK_ROW_ONLY_COLUMNS,
    EDGE_ROW_ONLY_COLUMNS,
    ENCODING_DELTA_VARINT,
    ENTRY_CONTENT_FIELDS,
    ENTRY_ROW_ONLY_COLUMNS,
    MAX_TABLE_NAME_LENGTH,
    MODEL_COLUMN_RENAMES,
    MODEL_FIELD_ONLY,
    MODEL_OWNER_FIELDS,
    SCHEMA_FORMAT_VERSION,
    ULID_LENGTH,
    VERSION_ROW_ONLY_COLUMNS,
    BytewiseString,
    ULIDKey,
    VFSTables,
    build_vfs_tables,
)
from vfs.models.vector import NativeEmbeddingConfig, VectorType
from vfs.paths import MAX_PATH_LENGTH, MAX_SEGMENT_LENGTH, Path

TABLE_ATTRS = ("entry", "content", "versions", "chunks", "edges", "meta", "gram_epochs", "posting_list")

# The metadata family: each model, its table attribute, and the table's
# columns with no model field (the id backbone and owner references).
METADATA_MODELS = (
    (Version, "versions", VERSION_ROW_ONLY_COLUMNS),
    (Chunk, "chunks", CHUNK_ROW_ONLY_COLUMNS),
    (Edge, "edges", EDGE_ROW_ONLY_COLUMNS),
)


@pytest.fixture
def tables() -> VFSTables:
    return build_vfs_tables(table_name="vfs_entries")


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

    def test_content_table_homes_the_body(self, tables: VFSTables) -> None:
        for field in ENTRY_CONTENT_FIELDS:
            assert field in Entry.model_fields
            assert field in tables.content.c

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
            "vfs_entries_content",
            "vfs_entries_versions",
            "vfs_entries_chunks",
            "vfs_entries_edges",
            "vfs_entries_meta",
            "vfs_entries_gram_epochs",
            "vfs_entries_grams_posting_list",
        }
        for attr in TABLE_ATTRS:
            assert getattr(tables, attr).metadata is tables.metadata

    def test_mounts_never_share_schema_objects(self, tables: VFSTables) -> None:
        other = build_vfs_tables(table_name="vfs_entries")
        assert other.metadata is not tables.metadata
        assert other.entry is not tables.entry

    def test_schema_applies_to_every_table(self) -> None:
        scoped = build_vfs_tables(table_name="t", schema="tenant")
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
        for column in (tables.entry.c.path, tables.entry.c.name, tables.entry.c.original_name):
            kind = column.type
            assert isinstance(kind, BytewiseString)
            postgres = kind.load_dialect_impl(postgresql.dialect())
            assert isinstance(postgres, String) and postgres.collation == "C"
            # UTF-8 binary collation: Unicode-safe VARCHAR whose byte order
            # matches SQLite/Postgres-C; plain _BIN2 was a code-page VARCHAR.
            ms = kind.load_dialect_impl(mssql.dialect())
            assert isinstance(ms, String) and ms.collation == "Latin1_General_100_BIN2_UTF8"

    def test_mysql_family_key_columns_are_byte_typed(self, tables: VFSTables) -> None:
        # utf8mb4 VARCHAR keys cost 4 bytes/char against InnoDB's 3,072-byte
        # cap; VARBINARY keys cost their own bytes, so the DDL provisions.
        for dialect in (mysql.dialect(), mariadb.MariaDBDialect()):
            ddl = str(CreateTable(tables.entry).compile(dialect=dialect))
            assert f"VARBINARY({MAX_PATH_LENGTH})" in ddl
            assert f"VARBINARY({MAX_SEGMENT_LENGTH})" in ddl

    def test_bytewise_string_round_trips_utf8_on_the_mysql_family(self) -> None:
        kind = BytewiseString(MAX_PATH_LENGTH)
        for dialect in (mysql.dialect(), mariadb.MariaDBDialect()):
            assert kind.process_bind_param("/é.txt", dialect) == "/é.txt".encode()
            assert kind.process_result_value("/é.txt".encode(), dialect) == "/é.txt"
        assert kind.process_bind_param("/é.txt", sqlite.dialect()) == "/é.txt"
        assert kind.process_result_value("/é.txt", sqlite.dialect()) == "/é.txt"

    def test_bodies_live_outside_entries_and_sit_last(self, tables: VFSTables) -> None:
        assert "content" not in tables.entry.c
        assert "version_diff" not in tables.entry.c
        assert list(tables.content.c.keys())[-1] == "content"
        assert list(tables.versions.c.keys())[-2:] == ["content", "version_diff"]
        assert list(tables.chunks.c.keys())[-1] == "content"

    def test_dependent_tables_key_on_entry_identity_never_path(self, tables: VFSTables) -> None:
        for table in (tables.content, tables.versions, tables.chunks):
            assert isinstance(table.c.entry_id.type, ULIDKey)
            assert not any("path" in column.name for column in table.c)
        for name in ("source_id", "target_id"):
            assert isinstance(tables.edges.c[name].type, ULIDKey)
        assert not any("path" in column.name for column in tables.edges.c)

    def test_edges_are_narrow_id_triples_indexed_both_directions(self, tables: VFSTables) -> None:
        assert {"id", "source_id", "target_id", "edge_type", "weight", "distance"} == set(tables.edges.c.keys())
        by_name = {str(index.name): index for index in tables.edges.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_edges_fwd"].columns] == ["source_id", "edge_type"]
        assert [c.name for c in by_name["ix_vfs_entries_edges_rev"].columns] == ["target_id", "edge_type"]

    def test_posting_rows_are_epoch_scoped_with_varint_default(self, tables: VFSTables) -> None:
        assert [c.name for c in tables.posting_list.primary_key.columns] == ["epoch", "gram_key"]
        default = tables.posting_list.c.encoding.default
        assert isinstance(default, ColumnDefault)
        assert default.arg == ENCODING_DELTA_VARINT
        assert {"epoch", "format_version", "options_hash", "created_at"} == set(tables.gram_epochs.c.keys())

    def test_ext_kind_composite_index(self, tables: VFSTables) -> None:
        by_name = {str(index.name): index for index in tables.entry.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_ext_kind"].columns] == ["ext", "kind"]

    def test_default_embedding_is_portable(self, tables: VFSTables) -> None:
        vector_type = tables.chunks.c.embedding.type
        assert isinstance(vector_type, VectorType)
        assert vector_type.postgres_native is False
        assert vector_type.dimension is None

    def test_native_embedding_shapes_the_chunk_column(self) -> None:
        native = build_vfs_tables(
            table_name="t",
            native_embedding=NativeEmbeddingConfig(dimension=8, model_name="m"),
        )
        vector_type = native.chunks.c.embedding.type
        assert isinstance(vector_type, VectorType)
        assert vector_type.postgres_native is True
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
    stamped = {"entry_id": entry_id, "parent_id": parent_id, "version": 1}
    return {**resident, **stamped, "original_parent_id": None, "original_name": None}


class TestULIDKey:
    """The one identity-conversion home: storage form and round-trip per arm."""

    def test_storage_form_is_binary_16_per_dialect_never_text(self) -> None:
        key = ULIDKey()
        forms = {
            name: key.compile(dialect=dialect)
            for name, dialect in (
                ("postgresql", postgresql.dialect()),
                ("mssql", mssql.dialect()),
                ("oracle", oracle.dialect()),
                ("mysql", mysql.dialect()),
                ("sqlite", sqlite.dialect()),
                # Non-default dialects whose supports_native_uuid flag lies
                # about sort order: the allow-list must hold them to bytes.
                ("mariadb", mariadb.MariaDBDialect()),
                ("mssql+pymssql", pymssql.MSDialect_pymssql()),
            )
        }
        # mssql is deliberately not UNIQUEIDENTIFIER: its sort order would
        # forfeit the ULID's time-ordered index locality.
        assert forms == {
            "postgresql": "UUID",
            "mssql": "BINARY(16)",
            "oracle": "RAW(16)",
            "mysql": "BINARY(16)",
            "sqlite": "BINARY(16)",
            "mariadb": "BINARY(16)",
            "mssql+pymssql": "BINARY(16)",
        }

    def test_bytes_arm_round_trips_and_sorts_like_the_string(self) -> None:
        key = ULIDKey()
        dialect = mssql.dialect()
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


class TestTableNameBudget:
    def test_at_limit_name_keeps_every_identifier_within_postgres_cap(self) -> None:
        tables = build_vfs_tables(table_name="x" * MAX_TABLE_NAME_LENGTH)
        names = [table.name for table in tables.metadata.tables.values()]
        for table in tables.metadata.tables.values():
            names += [c.name for c in table.constraints if isinstance(c.name, str)]
            names += [i.name for i in table.indexes if isinstance(i.name, str)]
        # Tight bound: the longest derived name lands exactly on 63, so a
        # future longer suffix must lower MAX_TABLE_NAME_LENGTH to pass.
        assert max(len(name) for name in names) == 63

    def test_at_limit_ddl_compiles_on_postgres(self) -> None:
        tables = build_vfs_tables(table_name="x" * MAX_TABLE_NAME_LENGTH)
        dialect = postgresql.dialect()
        for table in tables.metadata.tables.values():
            CreateTable(table).compile(dialect=dialect)
            for index in table.indexes:
                CreateIndex(index).compile(dialect=dialect)

    def test_over_limit_name_is_refused_loudly(self) -> None:
        with pytest.raises(ValueError, match="63-char"):
            build_vfs_tables(table_name="x" * (MAX_TABLE_NAME_LENGTH + 1))


class TestDDL:
    def test_one_create_all_provisions_the_whole_family(self, tables: VFSTables, engine: Engine) -> None:
        tables.metadata.create_all(engine)
        assert set(inspect(engine).get_table_names()) == set(tables.metadata.tables)

    def test_body_columns_compile_to_longtext_on_mysql(self, tables: VFSTables) -> None:
        # MySQL's plain TEXT caps bodies at 64KB; the pin is LONGTEXT.
        dialect = mysql.dialect()
        bodies = (
            tables.content.c.content,
            tables.versions.c.content,
            tables.versions.c.version_diff,
            tables.chunks.c.content,
        )
        assert [column.type.compile(dialect=dialect) for column in bodies] == ["LONGTEXT"] * 4

    def test_whole_family_ddl_compiles_on_every_dialect(self, tables: VFSTables) -> None:
        # Served, not refused: no column type may fail DDL compile on any
        # engine class — MySQL once refused the unbounded String() bodies.
        for module in (postgresql, mssql, oracle, mysql, sqlite):
            dialect = module.dialect()
            for table in tables.metadata.tables.values():
                CreateTable(table).compile(dialect=dialect)
                for index in table.indexes:
                    CreateIndex(index).compile(dialect=dialect)

    def test_native_embedding_ddl_compiles_off_postgres(self, engine: Engine) -> None:
        native = build_vfs_tables(table_name="t", native_embedding=NativeEmbeddingConfig(dimension=8))
        native.metadata.create_all(engine)  # VectorType falls back to TEXT

    def test_entry_splits_into_entries_plus_content_and_reads_back(self, tables: VFSTables, engine: Engine) -> None:
        tables.metadata.create_all(engine)
        entry = Entry(path=Path("/docs/a.md"), content="hello")
        ulid = "0" * ULID_LENGTH
        with engine.begin() as conn:
            pk = conn.execute(
                insert(tables.entry), [_entries_row(entry, entry_id=ulid, parent_id=None)]
            ).inserted_primary_key
            conn.execute(insert(tables.content), [{"entry_id": ulid, "content": entry.content}])
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
