"""Tests for Vector type and VectorType SQLAlchemy decorator."""

from __future__ import annotations

import json

import pytest

from grover.models.vector import Vector, VectorType


class TestVectorClassGetitem:
    def test_creates_subclass(self):
        vec3 = Vector[3]
        assert vec3._dimension == 3
        assert vec3.__name__ == "Vector[3]"

    def test_different_dimensions(self):
        vec3 = Vector[3]
        vec1024 = Vector[1024]
        assert vec3._dimension == 3
        assert vec1024._dimension == 1024
        assert vec3 is not vec1024

    def test_base_has_no_dimension(self):
        assert Vector._dimension is None


class TestVectorRuntimeValidation:
    def test_correct_dimension_accepted(self):
        v = Vector[3]([1.0, 2.0, 3.0])
        assert len(v) == 3

    def test_wrong_dimension_rejected(self):
        with pytest.raises(ValueError, match="Expected 3 dimensions, got 2"):
            Vector[3]([1.0, 2.0])

    def test_empty_vector_wrong_dimension(self):
        with pytest.raises(ValueError, match="Expected 3 dimensions, got 0"):
            Vector[3]([])


class TestVectorNoDimension:
    def test_any_length_accepted(self):
        v = Vector([1.0, 2.0])
        assert len(v) == 2

    def test_empty_accepted(self):
        v = Vector([])
        assert len(v) == 0

    def test_none_becomes_empty(self):
        v = Vector()
        assert len(v) == 0


class TestVectorIsList:
    def test_isinstance(self):
        assert isinstance(Vector([1, 2, 3]), list)

    def test_subscripted_isinstance(self):
        assert isinstance(Vector[3]([1, 2, 3]), list)

    def test_indexing(self):
        v = Vector([1.0, 2.0, 3.0])
        assert v[0] == 1.0
        assert v[2] == 3.0

    def test_iteration(self):
        v = Vector([1.0, 2.0, 3.0])
        assert list(v) == [1.0, 2.0, 3.0]


class TestVectorTypeJsonRoundtrip:
    def test_bind_and_result(self):
        vt = VectorType()
        data = [1.0, 2.0, 3.0]
        bound = vt.process_bind_param(data, None)
        assert bound is not None
        assert json.loads(bound) == data

        result = vt.process_result_value(bound, None)
        assert isinstance(result, Vector)
        assert list(result) == data

    def test_vector_instance_roundtrip(self):
        vt = VectorType()
        v = Vector([1.0, 2.0, 3.0])
        bound = vt.process_bind_param(v, None)
        result = vt.process_result_value(bound, None)
        assert list(result) == [1.0, 2.0, 3.0]


class TestVectorTypeNoneHandling:
    def test_bind_none(self):
        vt = VectorType()
        assert vt.process_bind_param(None, None) is None

    def test_result_none(self):
        vt = VectorType()
        assert vt.process_result_value(None, None) is None

    def test_dimensioned_bind_none(self):
        vt = VectorType(dimension=3)
        assert vt.process_bind_param(None, None) is None

    def test_dimensioned_result_none(self):
        vt = VectorType(dimension=3)
        assert vt.process_result_value(None, None) is None


class TestVectorTypeEnforcesOnBind:
    def test_wrong_dimension_rejected(self):
        vt = VectorType(dimension=3)
        with pytest.raises(ValueError, match="Vector bind: expected 3 dims, got 2"):
            vt.process_bind_param([1.0, 2.0], None)

    def test_correct_dimension_accepted(self):
        vt = VectorType(dimension=3)
        result = vt.process_bind_param([1.0, 2.0, 3.0], None)
        assert result is not None

    def test_no_dimension_accepts_any(self):
        vt = VectorType()
        result = vt.process_bind_param([1.0, 2.0], None)
        assert result is not None


class TestVectorTypeEnforcesOnRead:
    def test_wrong_dimension_rejected(self):
        vt = VectorType(dimension=3)
        bad_json = json.dumps([1.0, 2.0])
        with pytest.raises(ValueError, match="Vector read: expected 3 dims, got 2"):
            vt.process_result_value(bad_json, None)

    def test_correct_dimension_accepted(self):
        vt = VectorType(dimension=3)
        good_json = json.dumps([1.0, 2.0, 3.0])
        result = vt.process_result_value(good_json, None)
        assert list(result) == [1.0, 2.0, 3.0]


class TestVectorTypePreservesDimensionOnRead:
    def test_returns_dimensioned_subclass(self):
        vt = VectorType(dimension=3)
        good_json = json.dumps([1.0, 2.0, 3.0])
        result = vt.process_result_value(good_json, None)
        assert isinstance(result, Vector)
        assert result._dimension == 3

    def test_no_dimension_returns_base(self):
        vt = VectorType()
        good_json = json.dumps([1.0, 2.0, 3.0])
        result = vt.process_result_value(good_json, None)
        assert isinstance(result, Vector)
        assert result._dimension is None

    def test_cache_ok(self):
        vt = VectorType(dimension=3)
        assert vt.cache_ok is True
