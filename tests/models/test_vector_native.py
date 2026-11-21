"""The native vector column on Postgres, the packed column on SQLite: the column types, the wire
forms each dialect binds and reads, and the distance expression the vector leg orders by."""

from __future__ import annotations

import pytest
from pgvector.sqlalchemy import Vector as PGVector
from sqlalchemy import Column, LargeBinary, MetaData, Table, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from vfs.models.vector import NATIVE_VECTOR_DIALECTS, VectorType, pack_vector
from vfs.storage.backends.database.distance import cosine_distance, has_cosine_distance

DIALECTS = {"postgresql": postgresql.dialect(), "sqlite": sqlite.dialect()}


def _table(native: bool) -> Table:
    return Table("t", MetaData(), Column("embedding", VectorType(dimension=3, native=native)))


class TestColumnTypes:
    def test_the_native_dialects_and_their_types(self) -> None:
        column = VectorType(dimension=3, native=True)
        assert {"postgresql"} == NATIVE_VECTOR_DIALECTS
        assert isinstance(column.load_dialect_impl(DIALECTS["postgresql"]), PGVector)
        assert isinstance(column.load_dialect_impl(DIALECTS["sqlite"]), LargeBinary)
        assert not VectorType(dimension=3).is_native_on(DIALECTS["postgresql"])

    def test_the_ddl_names_each_engines_vector_type(self) -> None:
        table = _table(native=True)
        assert "vector(3)" in str(CreateTable(table).compile(dialect=DIALECTS["postgresql"])).lower()
        assert "BLOB" in str(CreateTable(table).compile(dialect=DIALECTS["sqlite"]))
        assert "BYTEA" in str(CreateTable(_table(native=False)).compile(dialect=DIALECTS["postgresql"]))

    def test_native_type_refusals(self) -> None:
        with pytest.raises(ValueError, match="fixed dimension"):
            VectorType().native_type_for("postgresql")
        with pytest.raises(ValueError, match="no native vector column type"):
            VectorType(dimension=3).native_type_for("sqlite")


class TestWireForms:
    def test_each_dialect_binds_its_own_form(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_bind_param([1.0, 2.0], DIALECTS["postgresql"]) == [1.0, 2.0]
        assert column.process_bind_param([1.0, 2.0], DIALECTS["sqlite"]) == pack_vector([1.0, 2.0])

    def test_each_dialect_reads_its_own_form(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_result_value([1.0, 2.0], DIALECTS["postgresql"]) == [1.0, 2.0]
        assert column.process_result_value(pack_vector([1.0, 2.0]), DIALECTS["sqlite"]) == [1.0, 2.0]


class TestDistance:
    def test_every_supported_dialect_spells_cosine_and_the_floor_does_not(self) -> None:
        table = _table(native=True)
        spellings = {}
        for name, dialect in DIALECTS.items():
            assert has_cosine_distance(name)
            stmt = select(table.c.embedding).order_by(cosine_distance(name, table.c.embedding, [1.0, 0.0, 0.0]))
            spellings[name] = str(stmt.compile(dialect=dialect))
        assert "<=>" in spellings["postgresql"]
        assert "vec_distance_cosine(t.embedding" in spellings["sqlite"]
        for unsupported in ("mysql", "mariadb", "mssql", "oracle", "exotic"):
            assert not has_cosine_distance(unsupported)
        with pytest.raises(ValueError, match="no cosine distance function"):
            cosine_distance("mariadb", table.c.embedding, [1.0, 0.0, 0.0])
