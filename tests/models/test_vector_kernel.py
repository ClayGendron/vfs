"""Tests for the cosine top-k kernel behind ``vfs.models.vector.cosine_topk``.

The owner packs the query and ids and dispatches to the engine; the
engine ranks a page of packed unit vectors by dot product, ``score
DESC, id ASC``, refusing an empty query and a torn page. The oracle in
``tests/support/oracles/vectors.py`` referees ids, order and scores.
"""

from __future__ import annotations

import math
import random
from array import array

import pytest

from tests.support.oracles.vectors import cosine_topk as oracle_topk
from vfs import _native
from vfs.models.vector import cosine_topk, pack_vector, unpack_vector


def page(rows: list[list[float]]) -> bytes:
    """*rows* packed one after another, the way a fetched page arrives."""
    return b"".join(pack_vector(row) for row in rows)


def unit_vectors(rng: random.Random, count: int, dimension: int) -> list[list[float]]:
    """*count* random unit vectors of *dimension* components."""
    rows = []
    for _ in range(count):
        raw = [rng.gauss(0.0, 1.0) for _ in range(dimension)]
        norm = math.sqrt(sum(v * v for v in raw))
        rows.append([v / norm for v in raw])
    return rows


# ---------------------------------------------------------------------------
# Hand cases through the owner
# ---------------------------------------------------------------------------


class TestCosineTopK:
    def test_exact_top_k_by_dot_product(self) -> None:
        top = cosine_topk([1.0, 0.0], [1, 2, 3], page([[0.0, 1.0], [1.0, 0.0], [0.6, 0.8]]), 2)
        assert [chunk_id for chunk_id, _ in top] == [2, 3]
        assert top[0][1] == 1.0
        assert top[1][1] == unpack_vector(pack_vector([0.6]))[0]

    def test_ties_break_on_ascending_id(self) -> None:
        top = cosine_topk([1.0, 0.0], [9, 4, 1], page([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]), 3)
        assert top == [(4, 1.0), (9, 1.0), (1, 0.0)]

    def test_k_past_the_page_returns_every_row(self) -> None:
        assert cosine_topk([1.0], [1, 2], page([[1.0], [-1.0]]), 10) == [(1, 1.0), (2, -1.0)]

    def test_k_zero_is_empty(self) -> None:
        assert cosine_topk([1.0], [1], page([[1.0]]), 0) == []

    def test_the_empty_page_is_empty(self) -> None:
        assert cosine_topk([1.0, 0.0], [], b"", 5) == []

    def test_a_torn_page_is_refused(self) -> None:
        with pytest.raises(ValueError, match="expected 16 bytes for 2 vectors of 2 components, got 8"):
            cosine_topk([1.0, 0.0], [1, 2], page([[1.0, 0.0]]), 1)

    def test_an_empty_query_is_refused(self) -> None:
        with pytest.raises(ValueError, match="query vector is empty"):
            cosine_topk([], [1], b"", 1)

    def test_scores_are_float32_products(self) -> None:
        query = [0.1, 0.2, 0.3]
        (row,) = cosine_topk(query, [7], pack_vector(query), 1)
        assert row == (7, oracle_topk(query, [7], pack_vector(query), 1)[0][1])


class TestBindingRefusals:
    def test_torn_query_bytes_are_refused(self) -> None:
        with pytest.raises(ValueError, match="whole float32"):
            _native.vector_topk(b"\x00\x00\x00", array("q", [1]).tobytes(), b"", 1)

    def test_torn_id_bytes_are_refused(self) -> None:
        with pytest.raises(ValueError, match="whole int64"):
            _native.vector_topk(pack_vector([1.0]), b"\x01\x02\x03", b"", 1)


# ---------------------------------------------------------------------------
# Parity with the oracle, and determinism
# ---------------------------------------------------------------------------


class TestParity:
    @pytest.mark.parametrize(("count", "dimension", "k"), [(300, 16, 25), (5000, 8, 40)])
    def test_engine_matches_the_oracle(self, count: int, dimension: int, k: int) -> None:
        rng = random.Random(count * 31 + dimension)
        rows = unit_vectors(rng, count, dimension)
        ids = rng.sample(range(1, count * 10), count)
        query = unit_vectors(rng, 1, dimension)[0]
        engine = cosine_topk(query, ids, page(rows), k)
        oracle = oracle_topk(query, ids, page(rows), k)
        assert len(engine) == len(oracle) == k
        assert [chunk_id for chunk_id, _ in engine] == [chunk_id for chunk_id, _ in oracle]
        for (_, ours), (_, theirs) in zip(engine, oracle, strict=True):
            assert math.isclose(ours, theirs, rel_tol=1e-6)

    def test_the_same_page_ranks_identically_twice(self) -> None:
        rng = random.Random(7)
        rows = unit_vectors(rng, 400, 12)
        ids = list(range(1, 401))
        query = unit_vectors(rng, 1, 12)[0]
        assert cosine_topk(query, ids, page(rows), 50) == cosine_topk(query, ids, page(rows), 50)
