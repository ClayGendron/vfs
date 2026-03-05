"""Tests for graph filtering and node similarity."""

from __future__ import annotations

import pytest

from grover.providers.graph import RustworkxGraph
from grover.providers.graph.protocol import SupportsFiltering, SupportsNodeSimilarity

# ======================================================================
# find_nodes
# ======================================================================


class TestFindNodes:
    def test_path_predicate(self) -> None:
        # Minimal storage only supports path-based queries
        g = RustworkxGraph()
        g.add_node("/a.py")
        g.add_node("/b.ts")
        g.add_node("/c.py")
        result = g.find_nodes(path=lambda p: p.endswith(".py"))
        assert set(result) == {"/a.py", "/c.py"}

    def test_path_exact_match(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        g.add_node("/b.py")
        result = g.find_nodes(path="/a.py")
        assert result == ["/a.py"]

    def test_no_attrs_returns_all(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        g.add_node("/b.py")
        result = g.find_nodes()
        assert set(result) == {"/a.py", "/b.py"}

    def test_non_path_attr_returns_empty(self) -> None:
        # Minimal storage — non-path attrs not stored
        g = RustworkxGraph()
        g.add_node("/a.py", lang="python")
        result = g.find_nodes(lang="python")
        assert result == []


# ======================================================================
# find_edges
# ======================================================================


class TestFindEdges:
    def test_by_source(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/c.py", "/b.py", "imports")
        result = g.find_edges(source="/a.py")
        assert len(result) == 1
        assert result[0][0] == "/a.py"

    def test_edge_type_ignored_with_minimal_storage(self) -> None:
        # Minimal storage — edge_type filter is a no-op
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/a.py", "/c.py", "contains")
        result = g.find_edges(edge_type="imports", source="/a.py")
        # Both edges match since type is not stored
        assert len(result) == 2

    def test_no_filter(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/c.py", "/d.py", "calls")
        result = g.find_edges()
        assert len(result) == 2

    def test_by_target(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/c.py", "/b.py", "imports")
        g.add_edge("/a.py", "/d.py", "imports")
        result = g.find_edges(target="/b.py")
        assert len(result) == 2
        assert all(tgt == "/b.py" for _, tgt, _ in result)


# ======================================================================
# edges_of
# ======================================================================


class TestEdgesOf:
    def test_out_edges(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/c.py", "/a.py", "imports")
        result = g.edges_of("/a.py", direction="out")
        assert len(result) == 1
        assert result[0][0] == "/a.py"
        assert result[0][1] == "/b.py"

    def test_in_edges(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/c.py", "/a.py", "imports")
        result = g.edges_of("/a.py", direction="in")
        assert len(result) == 1
        assert result[0][0] == "/c.py"
        assert result[0][1] == "/a.py"

    def test_both_edges(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/c.py", "/a.py", "imports")
        result = g.edges_of("/a.py", direction="both")
        assert len(result) == 2

    def test_edge_type_filter_ignored(self) -> None:
        # Minimal storage — edge_types filter is a no-op
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/a.py", "/c.py", "contains")
        result = g.edges_of("/a.py", direction="out", edge_types=["imports"])
        assert len(result) == 2

    def test_missing_node(self) -> None:
        g = RustworkxGraph()
        with pytest.raises(KeyError):
            g.edges_of("/missing.py")

    def test_self_loop_not_duplicated(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/a.py", "self_ref")
        result = g.edges_of("/a.py", direction="both")
        assert len(result) == 1


# ======================================================================
# node_similarity
# ======================================================================


class TestNodeSimilarity:
    def test_identical_neighbors(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/c.py", "imports")
        g.add_edge("/a.py", "/d.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        g.add_edge("/b.py", "/d.py", "imports")
        assert g.node_similarity("/a.py", "/b.py") == 1.0

    def test_disjoint_neighbors(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/x.py", "imports")
        g.add_edge("/b.py", "/y.py", "imports")
        assert g.node_similarity("/a.py", "/b.py") == 0.0

    def test_partial_overlap(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/c.py", "imports")
        g.add_edge("/a.py", "/d.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        g.add_edge("/b.py", "/e.py", "imports")
        sim = g.node_similarity("/a.py", "/b.py")
        assert abs(sim - 1 / 3) < 0.001

    def test_no_neighbors(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        g.add_node("/b.py")
        assert g.node_similarity("/a.py", "/b.py") == 0.0


# ======================================================================
# similar_nodes
# ======================================================================


class TestSimilarNodes:
    def test_returns_top_k(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/c.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        g.add_node("/d.py")
        result = g.similar_nodes("/a.py", k=2)
        assert len(result) <= 2
        assert result[0][0] == "/b.py"
        assert result[0][1] > 0

    def test_self_excluded(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        result = g.similar_nodes("/a.py")
        paths = [r[0] for r in result]
        assert "/a.py" not in paths

    def test_empty_graph(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        result = g.similar_nodes("/a.py")
        assert result == []


# ======================================================================
# Protocol satisfaction
# ======================================================================


class TestProtocolSatisfaction:
    def test_supports_filtering(self) -> None:
        g = RustworkxGraph()
        assert isinstance(g, SupportsFiltering)

    def test_supports_node_similarity(self) -> None:
        g = RustworkxGraph()
        assert isinstance(g, SupportsNodeSimilarity)
