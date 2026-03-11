"""Tests for subgraph extraction, neighborhood, meeting subgraph, and common reachable."""

from __future__ import annotations

import pytest

from grover.providers.graph import RustworkxGraph
from grover.providers.graph.protocol import GraphProvider

# ======================================================================
# Subgraph
# ======================================================================


class TestSubgraph:
    async def test_basic_extraction(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        g.add_edge("/c.py", "/d.py", "imports")
        g.add_edge("/d.py", "/e.py", "imports")
        sub = await g.subgraph(["/a.py", "/b.py", "/c.py"])
        assert set(sub.paths) == {"/a.py", "/b.py", "/c.py"}
        # Only edges with both endpoints in the subgraph
        edge_pairs = {(cc.source_path, cc.target_path) for cc in sub.connection_candidates}
        assert ("/a.py", "/b.py") in edge_pairs
        assert ("/b.py", "/c.py") in edge_pairs
        assert ("/c.py", "/d.py") not in edge_pairs

    async def test_empty_paths(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        sub = await g.subgraph([])
        assert sub.paths == ()
        assert sub.connection_candidates == []

    async def test_missing_paths_skipped(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        sub = await g.subgraph(["/a.py", "/missing.py"])
        assert set(sub.paths) == {"/a.py"}

    async def test_all_nodes(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        sub = await g.subgraph(["/a.py", "/b.py", "/c.py"])
        assert len(sub.connection_candidates) == 2

    async def test_result_is_file_search_result(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        sub = await g.subgraph(["/a.py"])
        assert sub.success is True
        assert len(sub) == 1


# ======================================================================
# Neighborhood
# ======================================================================


class TestNeighborhood:
    async def test_out_depth_1(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        sub = await g.neighborhood("/a.py", max_depth=1, direction="out")
        assert set(sub.paths) == {"/a.py", "/b.py"}

    async def test_out_depth_2(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        sub = await g.neighborhood("/a.py", max_depth=2, direction="out")
        assert set(sub.paths) == {"/a.py", "/b.py", "/c.py"}

    async def test_in_direction(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        sub = await g.neighborhood("/c.py", max_depth=1, direction="in")
        assert set(sub.paths) == {"/b.py", "/c.py"}

    async def test_both_direction(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        sub = await g.neighborhood("/b.py", max_depth=1, direction="both")
        assert set(sub.paths) == {"/a.py", "/b.py", "/c.py"}

    async def test_edge_type_filter_ignored_with_minimal_storage(self) -> None:
        # Minimal storage does not store edge types — filter is a no-op
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/a.py", "/c.py", "contains")
        sub = await g.neighborhood("/a.py", max_depth=1, direction="out", edge_types=["imports"])
        # Both neighbors included since edge types aren't stored
        assert "/b.py" in sub.paths
        assert "/c.py" in sub.paths

    async def test_missing_node(self) -> None:
        g = RustworkxGraph()
        with pytest.raises(KeyError):
            await g.neighborhood("/missing.py")

    async def test_depth_0(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        sub = await g.neighborhood("/a.py", max_depth=0)
        assert set(sub.paths) == {"/a.py"}


# ======================================================================
# Meeting subgraph
# ======================================================================


class TestMeetingSubgraph:
    async def test_linear_chain(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        g.add_edge("/c.py", "/d.py", "imports")
        sub = await g.meeting_subgraph(["/a.py", "/d.py"])
        # Should include intermediate nodes B and C
        assert "/b.py" in sub.paths
        assert "/c.py" in sub.paths

    async def test_diamond(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/a.py", "/c.py", "imports")
        g.add_edge("/b.py", "/d.py", "imports")
        g.add_edge("/c.py", "/d.py", "imports")
        sub = await g.meeting_subgraph(["/a.py", "/d.py"])
        assert "/a.py" in sub.paths
        assert "/d.py" in sub.paths

    async def test_disconnected(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        g.add_node("/b.py")
        sub = await g.meeting_subgraph(["/a.py", "/b.py"])
        # No connection — should at least contain start nodes
        assert "/a.py" in sub.paths
        assert "/b.py" in sub.paths

    async def test_single_start(self) -> None:
        g = RustworkxGraph()
        g.add_node("/a.py")
        sub = await g.meeting_subgraph(["/a.py"])
        assert set(sub.paths) == {"/a.py"}
        assert sub.connection_candidates == []

    async def test_three_starts(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/hub.py", "imports")
        g.add_edge("/b.py", "/hub.py", "imports")
        g.add_edge("/c.py", "/hub.py", "imports")
        sub = await g.meeting_subgraph(["/a.py", "/b.py", "/c.py"])
        # Hub should be found via common descendants
        assert len(sub) >= 3

    async def test_pruning_at_max_size(self) -> None:
        # Build a large graph
        g = RustworkxGraph()
        for i in range(20):
            g.add_edge(f"/node{i}.py", f"/node{i + 1}.py", "imports")
        sub = await g.meeting_subgraph(["/node0.py", "/node20.py"], max_size=5)
        assert len(sub) <= 5

    async def test_start_nodes_never_pruned(self) -> None:
        g = RustworkxGraph()
        for i in range(10):
            g.add_edge(f"/node{i}.py", f"/node{i + 1}.py", "imports")
        sub = await g.meeting_subgraph(["/node0.py", "/node10.py"], max_size=3)
        assert "/node0.py" in sub.paths
        assert "/node10.py" in sub.paths

    async def test_scores_populated(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        sub = await g.meeting_subgraph(["/a.py", "/c.py"])
        # Every file candidate should have a score from the enrichment
        assert len(sub) > 0
        for c in sub.file_candidates:
            assert len(c.evidence) > 0
            assert isinstance(c.evidence[0].score, float)


# ======================================================================
# Common reachable
# ======================================================================


class TestCommonReachable:
    async def test_forward_common_descendants(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/c.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        g.add_edge("/c.py", "/d.py", "imports")
        result = await g.common_reachable(["/a.py", "/b.py"], direction="forward")
        assert "/c.py" in result
        assert "/d.py" in result

    async def test_reverse_common_ancestors(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/a.py", "/c.py", "imports")
        result = await g.common_reachable(["/b.py", "/c.py"], direction="reverse")
        assert "/a.py" in result

    async def test_no_common(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/x.py", "imports")
        g.add_edge("/b.py", "/y.py", "imports")
        result = await g.common_reachable(["/a.py", "/b.py"], direction="forward")
        assert result == set()

    async def test_single_path(self) -> None:
        g = RustworkxGraph()
        g.add_edge("/a.py", "/b.py", "imports")
        g.add_edge("/b.py", "/c.py", "imports")
        result = await g.common_reachable(["/a.py"], direction="forward")
        assert result == {"/b.py", "/c.py"}


# ======================================================================
# Protocol satisfaction
# ======================================================================


class TestProtocolSatisfaction:
    def test_supports_graph_provider(self) -> None:
        g = RustworkxGraph()
        assert isinstance(g, GraphProvider)
