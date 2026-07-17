"""Tests for the hand-written Core row definitions and their Entry lockstep."""

from __future__ import annotations

from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from sqlalchemy import String, create_engine, insert, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import ColumnDefault, CreateIndex, CreateTable

from vfs.models import Entry
from vfs.models.rows import (
    ENCODING_DELTA_VARINT,
    ENTRY_FIELD_HOMES,
    ENTRY_ROW_ONLY_COLUMNS,
    MAX_TABLE_NAME_LENGTH,
    SCHEMA_FORMAT_VERSION,
    ULID_LENGTH,
    VFSTables,
    build_vfs_tables,
)
from vfs.models.vector import NativeEmbeddingConfig, VectorType
from vfs.paths import Path

TABLE_ATTRS = ("entry", "content", "versions", "chunks", "edges", "meta", "gram_epochs", "posting_list")


@pytest.fixture
def tables() -> VFSTables:
    return build_vfs_tables(table_name="vfs_entries")


# ---------------------------------------------------------------------------
# Entry ⇄ row drift — the lockstep the hand-written schema must hold
# ---------------------------------------------------------------------------


def _allows_none(annotation: object) -> bool:
    """Whether the annotation admits ``None`` (i.e. is ``X | None``)."""
    if get_origin(annotation) in {Union, UnionType}:
        return type(None) in get_args(annotation)
    return False


class TestEntryRowDrift:
    def test_entries_columns_are_the_resident_fields_plus_row_only(self, tables: VFSTables) -> None:
        resident = set(Entry.model_fields) - set(ENTRY_FIELD_HOMES)
        assert set(tables.entry.c.keys()) == resident | ENTRY_ROW_ONLY_COLUMNS

    def test_every_homed_field_has_its_column(self, tables: VFSTables) -> None:
        for field, (table_attr, column) in ENTRY_FIELD_HOMES.items():
            assert field in Entry.model_fields, f"homed field {field!r} left Entry without a mapping update"
            table = getattr(tables, table_attr)
            assert column in table.c, f"{field!r} maps to missing column {table_attr}.{column}"

    def test_row_only_columns_never_exist_on_entry(self) -> None:
        assert not ENTRY_ROW_ONLY_COLUMNS & set(Entry.model_fields)

    def test_homes_never_claim_entries_resident_fields(self) -> None:
        assert not set(ENTRY_FIELD_HOMES) & ENTRY_ROW_ONLY_COLUMNS

    def test_nullability_matches_entry_optionality_for_resident_fields(self, tables: VFSTables) -> None:
        for name, field in Entry.model_fields.items():
            if name in ENTRY_FIELD_HOMES:
                continue
            column = tables.entry.c[name]
            assert column.nullable == _allows_none(field.annotation), (
                f"nullability drift on {name!r}: column nullable={column.nullable}, Entry annotation {field.annotation}"
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
        assert tables.entry.c.node_id.unique
        node_type = tables.entry.c.node_id.type
        assert isinstance(node_type, String)
        assert node_type.length == ULID_LENGTH
        assert tables.entry.c.parent_id.nullable  # null for the root row
        assert tables.entry.c.path.unique

    def test_create_arbitration_index_is_parent_id_name(self, tables: VFSTables) -> None:
        unique = {c.name for c in tables.entry.constraints if c.name == "uq_vfs_entries_parent_name"}
        assert unique == {"uq_vfs_entries_parent_name"}

    def test_path_and_name_pin_binary_collation_per_dialect(self, tables: VFSTables) -> None:
        for column in (tables.entry.c.path, tables.entry.c.name, tables.entry.c.original_name):
            variants = column.type._variant_mapping
            postgres, mssql = variants["postgresql"], variants["mssql"]
            assert isinstance(postgres, String) and isinstance(mssql, String)
            assert postgres.collation == "C"
            # UTF-8 binary collation: Unicode-safe VARCHAR whose byte order
            # matches SQLite/Postgres-C; plain _BIN2 was a code-page VARCHAR.
            assert mssql.collation == "Latin1_General_100_BIN2_UTF8"

    def test_bodies_live_outside_entries_and_sit_last(self, tables: VFSTables) -> None:
        assert "content" not in tables.entry.c
        assert "version_diff" not in tables.entry.c
        assert list(tables.content.c.keys())[-1] == "content"
        assert list(tables.versions.c.keys())[-2:] == ["content", "version_diff"]
        assert list(tables.chunks.c.keys())[-1] == "content"

    def test_dependent_tables_key_on_the_integer_never_path(self, tables: VFSTables) -> None:
        for table in (tables.content, tables.versions, tables.chunks):
            assert "entry_id" in table.c
            assert not any("path" in column.name for column in table.c)
        for column in tables.edges.c:
            assert "path" not in column.name

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
        assert {"epoch", "format_version", "options_hash", "watermark", "created_at"} == set(
            tables.gram_epochs.c.keys()
        )

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


def _entries_row(entry: Entry, *, node_id: str, parent_id: int | None) -> dict[str, object]:
    """The entries-table row for *entry*: resident fields plus the id backbone."""
    resident = entry.model_dump(exclude=set(ENTRY_FIELD_HOMES) | set(Entry.model_computed_fields))
    return {**resident, "node_id": node_id, "parent_id": parent_id, "original_parent_id": None, "original_name": None}


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
    def test_one_create_all_provisions_the_whole_family(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        assert set(inspect(engine).get_table_names()) == set(tables.metadata.tables)

    def test_native_embedding_ddl_compiles_off_postgres(self) -> None:
        native = build_vfs_tables(table_name="t", native_embedding=NativeEmbeddingConfig(dimension=8))
        native.metadata.create_all(create_engine("sqlite://"))  # VectorType falls back to TEXT

    def test_entry_splits_into_entries_plus_content_and_reads_back(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        entry = Entry(path=Path("/docs/a.md"), content="hello", revision=1)
        ulid = "0" * ULID_LENGTH
        with engine.begin() as conn:
            entry_id = conn.execute(
                insert(tables.entry), [_entries_row(entry, node_id=ulid, parent_id=None)]
            ).inserted_primary_key
            stored_id = conn.execute(select(tables.entry.c.id)).scalar_one()
            conn.execute(insert(tables.content), [{"entry_id": stored_id, "content": entry.content}])
            row = conn.execute(select(tables.entry)).mappings().one()
            body = conn.execute(select(tables.content.c.content)).scalar_one()
        assert entry_id is not None
        assert row["path"] == "/docs/a.md"
        assert row["node_id"] == ulid
        assert row["revision"] == 1
        assert "content" not in row
        assert body == "hello"

    def test_meta_table_enforces_the_single_row(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        row = {
            "id": 1,
            "schema_format_version": SCHEMA_FORMAT_VERSION,
            "mount_identity": "0" * ULID_LENGTH,
            "revision_counter": 0,
        }
        with engine.begin() as conn:
            conn.execute(insert(tables.meta), [row])
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert(tables.meta), [{**row, "id": 2}])

    def test_duplicate_names_under_one_parent_are_refused(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        first = Entry(path=Path("/docs/a.md"), content="x")
        with engine.begin() as conn:
            conn.execute(insert(tables.entry), [_entries_row(first, node_id="0" * ULID_LENGTH, parent_id=7)])
        clone = Entry(path=Path("/docs2/a.md"), content="y")  # distinct path, same (parent_id, name)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert(tables.entry), [_entries_row(clone, node_id="1" * ULID_LENGTH, parent_id=7)])
