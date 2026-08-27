"""Tests for ``vfs.models.vector`` — the Vector runtime type and its column type.

``Vector[N]`` subclasses validate dimension at construction and through
pydantic; ``VectorType`` stores packed little-endian float32 portably and
switches to native pgvector only on PostgreSQL — bind and result stay
dimension- and model-guarded on every path.
"""

from __future__ import annotations

import pytest
from pgvector.sqlalchemy import Vector as PGVector
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import LargeBinary
from sqlalchemy.dialects import postgresql, sqlite

from vfs.models.vector import Vector, VectorType, pack_vector, unpack_vector

SQLITE = sqlite.dialect()
POSTGRES = postgresql.dialect()


# ---------------------------------------------------------------------------
# Vector — subscription forms and construction
# ---------------------------------------------------------------------------


class TestVectorSubscription:
    def test_dimension_form(self) -> None:
        v = Vector[3]([1.0, 2.0, 3.0])
        assert (v.dimension, v.model_name) == (3, None)
        assert type(v).__name__ == "Vector[3]"

    def test_model_name_form(self) -> None:
        v = Vector["text-embedding-3-large"]([1.0])
        assert (v.dimension, v.model_name) == (None, "text-embedding-3-large")

    def test_pair_form(self) -> None:
        v = Vector[2, "m"]([1.0, 2.0])
        assert (v.dimension, v.model_name) == (2, "m")
        assert type(v).__name__ == "Vector[2, 'm']"

    def test_wrong_tuple_arity_raises(self) -> None:
        with pytest.raises(TypeError, match="got 3 elements"):
            Vector[1, "m", "extra"]  # ty: ignore[invalid-argument-type]

    def test_wrong_tuple_types_raise(self) -> None:
        with pytest.raises(TypeError, match=r"\(str, int\)"):
            Vector["m", 1]  # ty: ignore[invalid-argument-type]

    def test_unsupported_parameter_raises(self) -> None:
        with pytest.raises(TypeError, match="float"):
            Vector[1.5]  # ty: ignore[invalid-argument-type]

    def test_dimension_is_enforced_at_construction(self) -> None:
        with pytest.raises(ValueError, match="Expected 3 dimensions, got 1"):
            Vector[3]([1.0])

    def test_unsubscripted_accepts_any_length(self) -> None:
        assert Vector() == []
        assert Vector([1.0, 2.0]).dimension is None


# ---------------------------------------------------------------------------
# Vector — pydantic validation and serialization
# ---------------------------------------------------------------------------


class TestVectorPydantic:
    def test_none_passes_through(self) -> None:
        assert TypeAdapter(Vector).validate_python(None) is None

    def test_list_validates_into_the_subclass(self) -> None:
        v2 = Vector[2]
        v = TypeAdapter(v2).validate_python([1.0, 2.0])
        assert type(v) is v2
        assert v == [1.0, 2.0]

    def test_same_class_instance_passes_through_unchanged(self) -> None:
        v2 = Vector[2]
        v = v2([1.0, 2.0])
        assert TypeAdapter(v2).validate_python(v) is v

    def test_foreign_vector_instance_is_reconstructed(self) -> None:
        v2 = Vector[2]
        converted = TypeAdapter(v2).validate_python(Vector([3.0, 4.0]))
        assert type(converted) is v2
        assert converted == [3.0, 4.0]

    def test_non_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Expected list or Vector"):
            TypeAdapter(Vector).validate_python("nope")

    def test_dimension_is_enforced_through_pydantic(self) -> None:
        with pytest.raises(ValidationError, match="Expected 2 dimensions"):
            TypeAdapter(Vector[2]).validate_python([1.0])

    def test_serializes_as_a_plain_list(self) -> None:
        v2 = Vector[2]
        assert TypeAdapter(v2).dump_python(v2([1.0, 2.0])) == [1.0, 2.0]
        assert TypeAdapter(v2).dump_json(v2([1.0, 2.0])) == b"[1.0,2.0]"


# ---------------------------------------------------------------------------
# VectorType — configuration and dialect binding
# ---------------------------------------------------------------------------


class TestVectorTypeConfiguration:
    def test_native_requires_a_fixed_dimension(self) -> None:
        with pytest.raises(ValueError, match="fixed dimension"):
            VectorType(native=True)

    def test_pgvector_type_requires_a_fixed_dimension(self) -> None:
        with pytest.raises(ValueError, match="fixed dimension"):
            VectorType().pgvector_sqlalchemy_type()

    def test_dialect_impl_is_native_only_on_postgres(self) -> None:
        column = VectorType(dimension=3, native=True)
        assert isinstance(column.load_dialect_impl(POSTGRES), PGVector)
        assert isinstance(column.load_dialect_impl(SQLITE), LargeBinary)
        assert column.is_native_on(POSTGRES) and not column.is_native_on(SQLITE)
        assert not VectorType(dimension=3).is_native_on(POSTGRES)

    def test_copy_preserves_configuration(self) -> None:
        column = VectorType(
            dimension=5,
            model_name="m",
            native=True,
            postgres_index_method="ivfflat",
            postgres_operator_class="vector_l2_ops",
        )
        dup = column.copy()
        assert (dup.dimension, dup.model_name, dup.native) == (5, "m", True)
        assert (dup.postgres_index_method, dup.postgres_operator_class) == ("ivfflat", "vector_l2_ops")


# ---------------------------------------------------------------------------
# The packed format
# ---------------------------------------------------------------------------


class TestPackedFormat:
    def test_little_endian_float32_four_bytes_a_component(self) -> None:
        packed = pack_vector([1.0, -2.5])
        assert packed == b"\x00\x00\x80\x3f\x00\x00\x20\xc0"
        assert unpack_vector(packed) == [1.0, -2.5]

    def test_float32_rounds_the_way_the_engines_store_it(self) -> None:
        assert unpack_vector(pack_vector([0.1]))[0] == pytest.approx(0.1, abs=1e-7)

    def test_a_torn_payload_is_refused(self) -> None:
        with pytest.raises(ValueError, match="whole number of float32"):
            unpack_vector(b"\x00\x00\x00")

    def test_the_empty_vector_round_trips(self) -> None:
        assert unpack_vector(pack_vector([])) == []


# ---------------------------------------------------------------------------
# VectorType — bind parameters
# ---------------------------------------------------------------------------


class TestVectorTypeBind:
    def test_none_passes_through(self) -> None:
        assert VectorType().process_bind_param(None, SQLITE) is None

    def test_packs_float32_bytes_by_default(self) -> None:
        assert VectorType().process_bind_param([1.0, 2.5], SQLITE) == pack_vector([1.0, 2.5])

    def test_enforces_dimension(self) -> None:
        with pytest.raises(ValueError, match="expected 3 dims, got 1"):
            VectorType(dimension=3).process_bind_param([1.0], SQLITE)

    def test_refuses_a_model_name_mismatch(self) -> None:
        column = VectorType(dimension=2, model_name="text-embedding-3-large")
        with pytest.raises(ValueError, match="model name mismatch"):
            column.process_bind_param(Vector[2, "other-model"]([1.0, 2.0]), SQLITE)

    def test_accepts_a_matching_or_unset_model_name(self) -> None:
        column = VectorType(dimension=2, model_name="m")
        assert column.process_bind_param(Vector[2, "m"]([1.0, 2.0]), SQLITE) == pack_vector([1.0, 2.0])
        assert column.process_bind_param([1.0, 2.0], SQLITE) == pack_vector([1.0, 2.0])

    def test_native_passes_a_list_on_postgres_only(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_bind_param([1.0, 2.0], POSTGRES) == [1.0, 2.0]
        assert column.process_bind_param([1.0, 2.0], SQLITE) == pack_vector([1.0, 2.0])


# ---------------------------------------------------------------------------
# VectorType — result values
# ---------------------------------------------------------------------------


class TestVectorTypeResult:
    def test_none_passes_through(self) -> None:
        assert VectorType().process_result_value(None, SQLITE) is None

    def test_unpacks_into_the_configured_subclass(self) -> None:
        v = VectorType(dimension=2, model_name="m").process_result_value(pack_vector([1.0, 2.0]), SQLITE)
        assert v is not None
        assert (v.dimension, v.model_name) == (2, "m")
        assert v == [1.0, 2.0]

    def test_coercion_covers_every_configuration(self) -> None:
        one = pack_vector([1.0])
        dimensioned = VectorType(dimension=1).process_result_value(one, SQLITE)
        assert dimensioned is not None and dimensioned.dimension == 1
        named = VectorType(model_name="m").process_result_value(one, SQLITE)
        assert named is not None and named.model_name == "m"
        plain = VectorType().process_result_value(one, SQLITE)
        assert plain is not None and (plain.dimension, plain.model_name) == (None, None)

    def test_accepts_every_buffer_shape(self) -> None:
        one = pack_vector([1.5, 2.0])
        assert VectorType().process_result_value(bytearray(one), SQLITE) == [1.5, 2.0]
        assert VectorType().process_result_value(memoryview(one), SQLITE) == [1.5, 2.0]

    def test_refuses_non_bytes(self) -> None:
        with pytest.raises(ValueError, match="expected packed float32 bytes"):
            VectorType().process_result_value("[1.0, 2.0]", SQLITE)

    def test_refuses_a_torn_payload(self) -> None:
        with pytest.raises(ValueError, match="whole number of float32"):
            VectorType().process_result_value(b"\x00\x00\x00", SQLITE)

    def test_enforces_dimension(self) -> None:
        with pytest.raises(ValueError, match="expected 3 dims, got 1"):
            VectorType(dimension=3).process_result_value(pack_vector([1.0]), SQLITE)

    def test_native_accepts_list_tuple_and_tolist(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_result_value([1.0, 2.0], POSTGRES) == [1.0, 2.0]
        assert column.process_result_value((1.0, 2.0), POSTGRES) == [1.0, 2.0]

        class NumpyLike:
            def tolist(self) -> list[float]:
                return [1.0, 2.0]

        assert column.process_result_value(NumpyLike(), POSTGRES) == [1.0, 2.0]

    def test_native_accepts_any_iterable_and_numeric_strings(self) -> None:
        column = VectorType(dimension=2, native=True)
        assert column.process_result_value(iter([1.0, 2.0]), POSTGRES) == [1.0, 2.0]
        assert column.process_result_value(["1.5", 2], POSTGRES) == [1.5, 2.0]

    def test_native_refuses_text_non_iterables_and_non_numeric_elements(self) -> None:
        column = VectorType(dimension=2, native=True)
        with pytest.raises(ValueError, match="iterable native vector value"):
            column.process_result_value("[1.0, 2.0]", POSTGRES)
        with pytest.raises(ValueError, match="iterable native vector value"):
            column.process_result_value(5, POSTGRES)
        with pytest.raises(ValueError, match="numeric vector element"):
            column.process_result_value([None, 1.0], POSTGRES)
