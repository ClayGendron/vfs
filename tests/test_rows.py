"""Tests for the hand-written Core row definitions and their Entry lockstep."""

from __future__ import annotations

from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from sqlalchemy import create_engine, insert, inspect, select

from vfs.models2 import Entry
from vfs.rows import (
    ENTRY_ROW_ONLY_COLUMNS,
    GRAM_ACTION_ADD,
    GramStagingRow,
    VFSTables,
    build_vfs_tables,
)
from vfs.vector import NativeEmbeddingConfig, VectorType


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
    def test_columns_are_entry_fields_plus_row_only(self, tables: VFSTables) -> None:
        columns = set(tables.entry.c.keys())
        assert columns == set(Entry.model_fields) | ENTRY_ROW_ONLY_COLUMNS

    def test_row_only_columns_never_exist_on_entry(self) -> None:
        assert not ENTRY_ROW_ONLY_COLUMNS & set(Entry.model_fields)

    def test_nullability_matches_entry_optionality(self, tables: VFSTables) -> None:
        for name, field in Entry.model_fields.items():
            column = tables.entry.c[name]
            assert column.nullable == _allows_none(field.annotation), (
                f"nullability drift on {name!r}: column nullable={column.nullable}, "
                f"Entry annotation {field.annotation}"
            )

    def test_gram_staging_row_matches_staging_columns(self, tables: VFSTables) -> None:
        insertable = set(tables.gram_staging.c.keys()) - {"seq"}  # seq is server-assigned
        assert set(GramStagingRow.__annotations__) == insertable


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------


class TestBuildVFSTables:
    def test_one_metadata_owns_all_three_tables(self, tables: VFSTables) -> None:
        assert set(tables.metadata.tables) == {
            "vfs_entries",
            "vfs_entries_grams_staging",
            "vfs_entries_grams_posting_list",
        }
        for table in (tables.entry, tables.gram_staging, tables.posting_list):
            assert table.metadata is tables.metadata

    def test_mounts_never_share_schema_objects(self, tables: VFSTables) -> None:
        other = build_vfs_tables(table_name="vfs_entries")
        assert other.metadata is not tables.metadata
        assert other.entry is not tables.entry

    def test_schema_applies_to_all_three_tables(self) -> None:
        scoped = build_vfs_tables(table_name="t", schema="tenant")
        assert {scoped.entry.schema, scoped.gram_staging.schema, scoped.posting_list.schema} == {"tenant"}

    def test_path_is_unique_and_pk_is_sqlite_autoincrement(self, tables: VFSTables) -> None:
        assert tables.entry.c.path.unique
        assert tables.entry.c.id.primary_key
        assert tables.entry.kwargs["sqlite_autoincrement"] is True

    def test_ext_kind_composite_index(self, tables: VFSTables) -> None:
        by_name = {index.name: index for index in tables.entry.indexes}
        assert [c.name for c in by_name["ix_vfs_entries_ext_kind"].columns] == ["ext", "kind"]

    def test_default_embedding_is_portable(self, tables: VFSTables) -> None:
        vector_type = tables.entry.c.embedding.type
        assert isinstance(vector_type, VectorType)
        assert vector_type.postgres_native is False
        assert vector_type.dimension is None

    def test_native_embedding_shapes_the_column(self) -> None:
        native = build_vfs_tables(
            table_name="t",
            native_embedding=NativeEmbeddingConfig(dimension=8, model_name="m"),
        )
        vector_type = native.entry.c.embedding.type
        assert isinstance(vector_type, VectorType)
        assert vector_type.postgres_native is True
        assert vector_type.dimension == 8
        assert vector_type.model_name == "m"
        assert vector_type.postgres_index_method == "hnsw"
        assert vector_type.postgres_operator_class == "vector_cosine_ops"


# ---------------------------------------------------------------------------
# DDL and round-trip — the schema must accept real domain data
# ---------------------------------------------------------------------------


class TestDDL:
    def test_one_create_all_provisions_all_three(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        assert set(inspect(engine).get_table_names()) == set(tables.metadata.tables)

    def test_native_embedding_ddl_compiles_off_postgres(self) -> None:
        native = build_vfs_tables(table_name="t", native_embedding=NativeEmbeddingConfig(dimension=8))
        native.metadata.create_all(create_engine("sqlite://"))  # VectorType falls back to TEXT

    def test_entry_dump_inserts_and_reads_back(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        entry = Entry(path="/docs/a.md", content="hello", description="greeting")
        row = {
            **entry.model_dump(exclude=set(Entry.model_computed_fields)),
            # Repository-derived relationship columns (id refs in a later phase).
            "parent_dir": str(entry.parent_dir),
            "parent_file": entry.parent_file,
            "source_path": entry.source_file,
            "target_path": entry.target_file,
        }
        with engine.begin() as conn:
            conn.execute(insert(tables.entry), [row])
            stored = conn.execute(select(tables.entry)).mappings().one()
        assert stored["path"] == "/docs/a.md"
        assert stored["content"] == "hello"
        assert stored["parent_dir"] == "/docs"
        assert stored["id"] is not None

    def test_gram_staging_accepts_typed_rows(self, tables: VFSTables) -> None:
        engine = create_engine("sqlite://")
        tables.metadata.create_all(engine)
        staged = GramStagingRow(gram_key=7, entry_id="chunk-1", doc_id=None, action=GRAM_ACTION_ADD)
        with engine.begin() as conn:
            conn.execute(insert(tables.gram_staging), [dict(staged)])
            stored = conn.execute(select(tables.gram_staging)).mappings().one()
        assert stored["gram_key"] == 7
        assert stored["seq"] is not None  # server-assigned, monotonic
