"""Tests for the centrality prior kernel behind ``vfs.models.signals.centrality_prior``.

The owner packs the graph and the tree and dispatches to the engine; the
engine measures, transforms, smooths and scales. The oracle in
``tests/support/oracles/signals.py`` referees every value.
"""

from __future__ import annotations

import random

import pytest

from tests.support.oracles.signals import centrality_prior as oracle_prior
from vfs.models.signals import NO_PARENT, centrality_prior
from vfs.storage.ranking import InDegree, Katz, PageRank

# Nodes: 0 = root, 1 = dir a, 2 = a/x, 3 = a/y, 4 = z.
PARENTS = [NO_PARENT, 0, 1, 1, 0]
FILES = [False, False, True, True, True]


def random_forest(rng: random.Random, node_count: int) -> tuple[list[int], list[bool]]:
    """A tree of directories with files hung on them; roots at the front."""
    parents = [NO_PARENT]
    files = [False]
    for node in range(1, node_count):
        parents.append(rng.randrange(node))
        files.append(rng.random() < 0.7)
    return parents, files


# ---------------------------------------------------------------------------
# Hand cases through the owner
# ---------------------------------------------------------------------------


class TestCentralityPrior:
    def test_in_degree_without_smoothing_scales_the_log_count(self) -> None:
        prior = centrality_prior(5, [3, 4, 4], [2, 2, 3], PARENTS, FILES, InDegree(), 0.0)
        assert prior[:2] == [0.0, 0.0] and prior[2] == 1.0 and prior[4] == 0.0
        assert prior[3] == pytest.approx(0.6309297535714574)

    def test_smoothing_lifts_a_sibling_of_a_referenced_file(self) -> None:
        prior = centrality_prior(5, [4], [2], PARENTS, FILES, InDegree(), 0.2)
        assert prior[2] == 1.0 and 0.0 < prior[3] < 1.0 and prior[4] == 0.0

    def test_a_uniform_measure_is_zero_everywhere(self) -> None:
        assert centrality_prior(5, [], [], PARENTS, FILES, InDegree(), 0.2) == [0.0] * 5
        assert centrality_prior(0, [], [], [], [], InDegree(), 0.2) == []

    def test_pagerank_and_katz_rank_the_referenced_file_first(self) -> None:
        for measure in (PageRank(), Katz(alpha=0.5, iterations=10)):
            prior = centrality_prior(5, [4, 3], [3, 2], PARENTS, FILES, measure, 0.0)
            assert prior[2] == 1.0 and prior[3] < 1.0

    def test_malformed_inputs_are_refused(self) -> None:
        with pytest.raises(ValueError, match="disagree"):
            centrality_prior(5, [1], [], PARENTS, FILES, InDegree(), 0.0)
        with pytest.raises(ValueError, match="outside"):
            centrality_prior(5, [9], [2], PARENTS, FILES, InDegree(), 0.0)
        with pytest.raises(ValueError, match="cycle"):
            centrality_prior(2, [], [], [1, 0], [True, True], InDegree(), 0.0)
        with pytest.raises(ValueError, match="gamma"):
            centrality_prior(5, [], [], PARENTS, FILES, InDegree(), 2.0)


# ---------------------------------------------------------------------------
# Parity with the oracle
# ---------------------------------------------------------------------------


class TestParity:
    @pytest.mark.parametrize("seed", range(6))
    @pytest.mark.parametrize("gamma", [0.0, 0.2, 0.3])
    def test_every_measure_matches_the_oracle_on_random_graphs(self, seed: int, gamma: float) -> None:
        rng = random.Random(seed)
        node_count = rng.randrange(1, 60)
        parents, files = random_forest(rng, node_count)
        edge_count = rng.randrange(0, 4 * node_count)
        sources = [rng.randrange(node_count) for _ in range(edge_count)]
        targets = [rng.randrange(node_count) for _ in range(edge_count)]
        for measure in (InDegree(), PageRank(damping=0.85, iterations=10), Katz(alpha=0.05, iterations=8)):
            engine = centrality_prior(node_count, sources, targets, parents, files, measure, gamma)
            name, damping, alpha, iterations = measure.kernel_args()
            params = {"damping": damping, "alpha": alpha, "iterations": iterations}
            expected = oracle_prior(node_count, sources, targets, parents, files, name, gamma, **params)
            assert engine == pytest.approx(expected, rel=1e-12, abs=1e-12), (name, seed, gamma)
            assert all(value == 0.0 for value, file in zip(engine, files, strict=True) if not file)
            assert all(0.0 <= value <= 1.0 for value in engine)

    def test_the_oracle_refuses_what_the_engine_refuses(self) -> None:
        with pytest.raises(ValueError, match="cycle"):
            oracle_prior(2, [], [], [1, 0], [True, True], "in_degree", 0.0)
        with pytest.raises(ValueError, match="unknown measure"):
            oracle_prior(1, [], [], [NO_PARENT], [True], "hits", 0.0)
