"""The native vector column on the four dialects that have one: the column types, the wire
forms each dialect binds and reads, and the distance expression the vector leg orders by."""

from __future__ import annotations

import json
from array import array

import pytest
from pgvector.sqlalchemy import Vector as PGVector
from sqlalchemy import Column, LargeBinary, MetaData, Table, select
from sqlalchemy.dialects import mssql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import mariadb
from sqlalchemy.dialects.oracle import VECTOR
from sqlalchemy.schema import CreateTable

from vfs.models.vector import NATIVE_VECTOR_DIALECTS, VectorType, pack_vector
from vfs.models.vector_native import MariaDBVector, MSSQLVector
from vfs.storage.backends.database.distance import cosine_distance, has_cosine_distance

DIALECTS = {
    "postgresql": postgresql.dialect(),
    "oracle": oracle.dialect(),
    "mssql": mssql.dialect(),
    "mariadb": mariadb.MariaDBDialect(),
    "sqlite": sqlite.dialect(),
}


def _table(native: bool) -> Table:
    return Table("t", MetaData(), Column("embedding", VectorType(dimension=3, native=native)))


class TestColumnTypes:
    def test_the_native_dialects_and_their_types(self) -> None:
        column = VectorType(dimension=3, native=True)
        assert {"postgresql", "oracle", "mssql", "mariadb"} == NATIVE_VECTOR_DIALECTS
        assert isinstance(column.load_dialect_impl(DIALECTS["postgresql"]), PGVector)
        assert isinstance(column.load_dialect_impl(DIALECTS["oracle"]), VECTOR)
        assert isinstance(column.load_dialect_impl(DIALECTS["mssql"]), MSSQLVector)
        assert isinstance(column.load_dialect_impl(DIALECTS["mariadb"]), MariaDBVector)
        assert isinstance(column.load_dialect_impl(DIALECTS["sqlite"]), LargeBinary)
        assert not VectorType(dimension=3).is_native_on(DIALECTS["oracle"])

    def test_the_ddl_names_each_engines_vector_type(self) -> None:
        table = _table(native=True)
        assert "VECTOR(3)" in str(CreateTable(table).compile(dialect=DIALECTS["mssql"]))
        assert "VECTOR(3)" in str(CreateTable(table).compile(dialect=DIALECTS["mariadb"]))
        assert "VECTOR(3,FLOAT32" in str(CreateTable(table).compile(dialect=DIALECTS["oracle"]))
        assert "vector(3)" in str(CreateTable(table).compile(dialect=DIALECTS["postgresql"])).lower()
        assert "BLOB" in str(CreateTable(table).compile(dialect=DIALECTS["sqlite"]))
        assert "BLOB" in str(CreateTable(_table(native=False)).compile(dialect=DIALECTS["mariadb"]))

    def test_native_type_refusals(self) -> None:
        with pytest.raises(ValueError, match="fixed dimension"):
            VectorType().native_type_for("mssql")
        with pytest.raises(ValueError, match="no native vector column type"):
            VectorType(dimension=3).native_type_for("sqlite")


class TestWireForms:
    def test_each_dialect_binds_its_own_form(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_bind_param([1.0, 2.0], DIALECTS["postgresql"]) == [1.0, 2.0]
        assert column.process_bind_param([1.0, 2.0], DIALECTS["oracle"]) == array("f", [1.0, 2.0])
        assert column.process_bind_param([1.0, 2.0], DIALECTS["mssql"]) == json.dumps([1.0, 2.0])
        assert column.process_bind_param([1.0, 2.0], DIALECTS["mariadb"]) == pack_vector([1.0, 2.0])
        assert column.process_bind_param([1.0, 2.0], DIALECTS["sqlite"]) == pack_vector([1.0, 2.0])

    def test_each_dialect_reads_its_own_form(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_result_value([1.0, 2.0], DIALECTS["postgresql"]) == [1.0, 2.0]
        assert column.process_result_value(array("f", [1.0, 2.0]), DIALECTS["oracle"]) == [1.0, 2.0]
        assert column.process_result_value("[1.0, 2.0]", DIALECTS["mssql"]) == [1.0, 2.0]
        assert column.process_result_value([1.0, 2.0], DIALECTS["mssql"]) == [1.0, 2.0]
        assert column.process_result_value(pack_vector([1.0, 2.0]), DIALECTS["mariadb"]) == [1.0, 2.0]
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
        assert "vector_distance(t.embedding, :query_vector_1, COSINE)" in spellings["oracle"]
        assert (
            "vector_distance(" in spellings["mssql"]
            and "CAST(" in spellings["mssql"]
            and "VECTOR(3)" in spellings["mssql"]
        )
        assert "vec_distance_cosine(t.embedding" in spellings["mariadb"]
        assert "vec_distance_cosine(t.embedding" in spellings["sqlite"]
        assert not has_cosine_distance("mysql") and not has_cosine_distance("exotic")
        with pytest.raises(ValueError, match="no cosine distance function"):
            cosine_distance("mysql", table.c.embedding, [1.0, 0.0, 0.0])
