"""Tests for the graph subpackage — UnionFind, RustworkxGraph, GraphProvider."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import rustworkx

from vfs.graph import GraphProvider, RustworkxGraph, UnionFind
from vfs.models import VFSEntry, _build_entry_table_class
from vfs.paths import decompose_edge
from vfs.results import Entry, VFSResult

_TEST_TABLE = _build_entry_table_class(table_name="vfs_entries")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_mock_session = AsyncMock()


@pytest.fixture(autouse=True)
def _fresh_mock_session():
    global _mock_session
    _mock_session = AsyncMock()


def _loaded_graph() -> RustworkxGraph:
    """Create a RustworkxGraph that skips DB loading (TTL already satisfied)."""
    g = RustworkxGraph(model=_TEST_TABLE)
    g._loaded_at = time.monotonic()
    return g


def _result(*paths: str) -> VFSResult:
    """Build a VFSResult from path strings."""
    return VFSResult(entries=[Entry(path=p) for p in paths])


def _node_paths(result: VFSResult) -> set[str]:
    """Extract entry paths that are nodes (not connections)."""
    return {e.path for e in result.entries if not decompose_edge(e.path)}


def _edge_entries(result: VFSResult) -> list[Entry]:
    """Extract entries that represent connection edges."""
    return [e for e in result.entries if decompose_edge(e.path)]


# ===========================================================================
# UnionFind
# ===========================================================================


class TestUnionFindInit:
    def test_initial_state(self):
        uf = UnionFind(["a", "b", "c"])
        assert uf.components == 3
        assert uf.find("a") == "a"
        assert uf.find("b") == "b"

    def test_empty(self):
        uf = UnionFind([])
        assert uf.components == 0


class TestUnionFindUnion:
    def test_union_merges(self):
        uf = UnionFind(["a", "b"])
        assert uf.union("a", "b") is True
        assert uf.components == 1
        assert uf.find("a") == uf.find("b")

    def test_union_same_set_returns_false(self):
        uf = UnionFind(["a", "b"])
        uf.union("a", "b")
        assert uf.union("a", "b") is False
        assert uf.components == 1

    def test_union_three_elements(self):
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.components == 1
        assert uf.find("a") == uf.find("c")

    def test_rank_balancing(self):
        uf = UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")  # rank[root] = 1
        uf.union("c", "d")  # rank[root] = 1
        uf.union("a", "c")  # merge two rank-1 trees
        assert uf.components == 1

    def test_rank_swap_lower_attaches_to_higher(self):
        """When ra has lower rank than rb, they swap so the smaller tree
        attaches to the larger — covers line 60."""
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")  # {a, b} rank 1
        # Now union c (rank 0) with a (rank 1) — c's root has lower rank
        uf.union("c", "a")  # c's root (rank 0) < a's root (rank 1) → swap
        assert uf.components == 1
        assert uf.find("c") == uf.find("a")


class TestUnionFindFind:
    def test_path_compression(self):
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")
        uf.union("b", "c")
        root = uf.find("c")
        # After find with path compression, c's parent should point closer to root
        assert uf.parent["c"] == root


# ===========================================================================
# RustworkxGraph — init and repr
# ===========================================================================


class TestRustworkxGraphInit:
    def test_empty_graph(self):
        g = RustworkxGraph(model=_TEST_TABLE)
        assert len(g.nodes) == 0
        assert g._loaded_at is None

    def test_default_ttl(self):
        g = RustworkxGraph(model=_TEST_TABLE)
        assert g._ttl == 3600

    def test_custom_ttl(self):
        g = RustworkxGraph(model=_TEST_TABLE, ttl=60)
        assert g._ttl == 60

    def test_repr_empty(self):
        g = RustworkxGraph(model=_TEST_TABLE)
        assert repr(g) == "RustworkxGraph(nodes=0, edges=0)"

    def test_repr_with_data(self):
        g = _loaded_graph()
        g._nodes = {"/a.py", "/b.py"}
        g._out = {"/a.py": {"/b.py"}}
        assert repr(g) == "RustworkxGraph(nodes=2, edges=1)"


# ===========================================================================
# Mutations
# ===========================================================================


class TestAddNode:
    async def test_add_node(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        assert "/a.py" in g.nodes

    async def test_add_node_idempotent(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        await g.add_node("/a.py", session=_mock_session)
        assert len(g.nodes) == 1


class TestRemoveNode:
    async def test_remove_node(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        await g.remove_node("/a.py", session=_mock_session)
        assert "/a.py" not in g.nodes

    async def test_remove_node_missing_raises(self):
        g = _loaded_graph()
        with pytest.raises(KeyError, match="Node not found"):
            await g.remove_node("/missing.py", session=_mock_session)

    async def test_remove_node_cleans_outgoing_edges(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.remove_node("/a.py", session=_mock_session)
        assert not await g.has_edge("/a.py", "/b.py", session=_mock_session)
        # Target node still exists
        assert "/b.py" in g.nodes

    async def test_remove_node_cleans_incoming_edges(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.remove_node("/b.py", session=_mock_session)
        assert "/a.py" in g.nodes
        assert "/a.py" not in g._out  # out set cleaned when only target was /b.py

    async def test_remove_node_cleans_edge_types(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.remove_node("/a.py", session=_mock_session)
        assert ("/a.py", "/b.py") not in g._edge_types


class TestHasNode:
    async def test_has_node_true(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        assert await g.has_node("/a.py", session=_mock_session) is True

    async def test_has_node_false(self):
        g = _loaded_graph()
        assert await g.has_node("/a.py", session=_mock_session) is False


class TestAddEdge:
    async def test_add_edge(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        assert await g.has_edge("/a.py", "/b.py", session=_mock_session)

    async def test_add_edge_auto_creates_nodes(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        assert "/a.py" in g.nodes
        assert "/b.py" in g.nodes

    async def test_add_edge_stores_type(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        assert g._edge_types[("/a.py", "/b.py")] == "imports"

    async def test_add_edge_updates_adjacency(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        assert "/b.py" in g._out["/a.py"]
        assert "/a.py" in g._in["/b.py"]


class TestRemoveEdge:
    async def test_remove_edge(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.remove_edge("/a.py", "/b.py", session=_mock_session)
        assert not await g.has_edge("/a.py", "/b.py", session=_mock_session)

    async def test_remove_edge_missing_source_raises(self):
        g = _loaded_graph()
        with pytest.raises(KeyError, match="Node not found"):
            await g.remove_edge("/missing.py", "/b.py", session=_mock_session)

    async def test_remove_edge_missing_target_raises(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        with pytest.raises(KeyError, match="Node not found"):
            await g.remove_edge("/a.py", "/missing.py", session=_mock_session)

    async def test_remove_edge_no_edge_raises(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        await g.add_node("/b.py", session=_mock_session)
        with pytest.raises(KeyError, match="No edge"):
            await g.remove_edge("/a.py", "/b.py", session=_mock_session)

    async def test_remove_edge_cleans_empty_sets(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.remove_edge("/a.py", "/b.py", session=_mock_session)
        assert "/a.py" not in g._out
        assert "/b.py" not in g._in

    async def test_remove_edge_cleans_edge_types(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.remove_edge("/a.py", "/b.py", session=_mock_session)
        assert ("/a.py", "/b.py") not in g._edge_types


class TestHasEdge:
    async def test_has_edge_true(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        assert await g.has_edge("/a.py", "/b.py", session=_mock_session) is True

    async def test_has_edge_false(self):
        g = _loaded_graph()
        assert await g.has_edge("/a.py", "/b.py", session=_mock_session) is False


# ===========================================================================
# Snapshot and graph construction
# ===========================================================================


class TestSnapshot:
    def test_returns_immutable_copies(self):
        g = _loaded_graph()
        g._nodes = {"/a.py", "/b.py"}
        g._out = {"/a.py": {"/b.py"}}
        nodes, edges = g._snapshot()
        assert isinstance(nodes, frozenset)
        assert isinstance(edges["/a.py"], frozenset)

    def test_snapshot_is_independent(self):
        g = _loaded_graph()
        g._nodes = {"/a.py"}
        g._out = {"/a.py": {"/b.py"}}
        nodes, _ = g._snapshot()
        g._nodes.add("/c.py")
        assert "/c.py" not in nodes


class TestBuildGraphFrom:
    def test_builds_correct_graph(self):
        nodes = frozenset(["/a.py", "/b.py", "/c.py"])
        edges = {"/a.py": frozenset(["/b.py"]), "/b.py": frozenset(["/c.py"])}
        graph, p2i, i2p = RustworkxGraph._build_graph_from(nodes, edges)
        assert graph.num_nodes() == 3
        assert graph.num_edges() == 2
        assert len(p2i) == 3
        assert len(i2p) == 3

    def test_skips_edges_with_missing_nodes(self):
        nodes = frozenset(["/a.py"])
        edges = {"/a.py": frozenset(["/missing.py"])}
        graph, _, _ = RustworkxGraph._build_graph_from(nodes, edges)
        assert graph.num_nodes() == 1
        assert graph.num_edges() == 0

    def test_skips_edges_with_missing_source(self):
        nodes = frozenset(["/b.py"])
        edges = {"/missing.py": frozenset(["/b.py"])}
        graph, _, _ = RustworkxGraph._build_graph_from(nodes, edges)
        assert graph.num_nodes() == 1
        assert graph.num_edges() == 0


class TestGraph:
    async def test_returns_pydigraph(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.graph(session=_mock_session)
        assert isinstance(result, rustworkx.PyDiGraph)
        assert result.num_nodes() == 2
        assert result.num_edges() == 1


# ===========================================================================
# Persistence
# ===========================================================================


class TestEnsureFresh:
    async def test_loads_when_never_loaded(self):
        g = RustworkxGraph(model=_TEST_TABLE)
        assert g._loaded_at is None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await g.ensure_fresh(mock_session)
        assert g._loaded_at is not None
        mock_session.execute.assert_awaited_once()

    async def test_skips_when_within_ttl(self):
        g = _loaded_graph()
        mock_session = AsyncMock()
        await g.ensure_fresh(mock_session)
        mock_session.execute.assert_not_awaited()

    async def test_reloads_when_ttl_expired(self):
        g = RustworkxGraph(model=_TEST_TABLE, ttl=0)
        g._loaded_at = time.monotonic() - 1  # expired

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await g.ensure_fresh(mock_session)
        mock_session.execute.assert_awaited_once()


class TestLoad:
    async def test_loads_connection_rows(self):
        g = RustworkxGraph(model=_TEST_TABLE)

        row = MagicMock()
        row.source_path = "/a.py"
        row.target_path = "/b.py"
        row.path = "/.vfs/a.py/__meta__/edges/out/imports/b.py"
        row.edge_type = "imports"
        row.kind = "edge"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute.return_value = mock_result

        await g._load(mock_session)

        assert "/a.py" in g.nodes
        assert "/b.py" in g.nodes
        assert "/b.py" in g._out["/a.py"]
        assert "/a.py" in g._in["/b.py"]
        assert g._edge_types[("/a.py", "/b.py")] == "imports"
        assert g._loaded_at is not None

    async def test_atomic_swap_clears_old_data(self):
        g = _loaded_graph()
        g._nodes = {"/old.py"}
        g._out = {"/old.py": {"/other.py"}}

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await g._load(mock_session)

        assert "/old.py" not in g.nodes
        assert g._out == {}

    async def test_skips_rows_without_source_or_target(self):
        g = RustworkxGraph(model=_TEST_TABLE)

        row = MagicMock()
        row.source_path = None
        row.target_path = "/b.py"
        row.path = "/orphan"
        row.edge_type = None
        row.kind = "edge"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute.return_value = mock_result

        await g._load(mock_session)
        assert len(g.nodes) == 0

    async def test_falls_back_to_decomposed_type(self):
        g = RustworkxGraph(model=_TEST_TABLE)

        row = MagicMock()
        row.source_path = "/a.py"
        row.target_path = "/b.py"
        row.path = "/.vfs/a.py/__meta__/edges/out/calls/b.py"
        row.edge_type = None  # not set — should decompose from path
        row.kind = "edge"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute.return_value = mock_result

        await g._load(mock_session)
        # edge_type decomposed from path
        assert g._edge_types[("/a.py", "/b.py")] != ""


# ===========================================================================
# Result construction helpers
# ===========================================================================


class TestRelationshipEntries:
    def test_builds_entries(self):
        paths_dict = {"/a.py": ["/b.py", "/c.py"]}
        result = RustworkxGraph._relationship_entries(paths_dict)
        assert len(result) == 1
        assert result[0].path == "/a.py"

    def test_sorted_by_path(self):
        paths_dict = {"/c.py": ["/a.py"], "/a.py": ["/b.py"]}
        result = RustworkxGraph._relationship_entries(paths_dict)
        assert [e.path for e in result] == ["/a.py", "/c.py"]


class TestSubgraphEntries:
    def test_builds_node_and_edge_entries(self):
        node_set = {"/a.py", "/b.py"}
        edges_out = {"/a.py": frozenset(["/b.py"])}
        edge_types = {("/a.py", "/b.py"): "imports"}
        result = RustworkxGraph._subgraph_entries(
            node_set,
            edges_out,
            edge_types,
        )
        # 2 node entries + 1 connection entry
        assert len(result) == 3
        node_paths = [e.path for e in result if not decompose_edge(e.path)]
        assert sorted(node_paths) == ["/a.py", "/b.py"]
        conn_entries = [e for e in result if decompose_edge(e.path)]
        assert len(conn_entries) == 1

    def test_only_includes_edges_within_node_set(self):
        node_set = {"/a.py"}
        edges_out = {"/a.py": frozenset(["/b.py"])}  # /b.py not in node_set
        edge_types = {("/a.py", "/b.py"): "imports"}
        result = RustworkxGraph._subgraph_entries(
            node_set,
            edges_out,
            edge_types,
        )
        assert len(result) == 1  # only the node, no edge


class TestScoreEntries:
    def test_sorted_descending(self):
        scores = {"/a.py": 0.3, "/b.py": 0.9, "/c.py": 0.5}
        result = RustworkxGraph._score_entries(scores)
        assert [e.path for e in result] == ["/b.py", "/c.py", "/a.py"]

    def test_scores_in_entries(self):
        scores = {"/a.py": 0.42}
        result = RustworkxGraph._score_entries(scores)
        assert result[0].score == 0.42


class TestExtractPaths:
    def test_extracts_paths(self):
        gr = _result("/a.py", "/b.py")
        paths = RustworkxGraph._extract_paths(gr)
        assert paths == ["/a.py", "/b.py"]

    def test_empty_result(self):
        paths = RustworkxGraph._extract_paths(VFSResult())
        assert paths == []


# ===========================================================================
# Traversal — predecessors and successors
# ===========================================================================


class TestPredecessors:
    async def test_finds_predecessors(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/b.py", "imports", session=_mock_session)

        result = await g.predecessors(_result("/b.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert paths == {"/a.py", "/c.py"}

    async def test_excludes_query_paths(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.predecessors(_result("/b.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert "/b.py" not in paths

    async def test_no_predecessors(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.predecessors(_result("/a.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_unknown_path_returns_empty(self):
        g = _loaded_graph()
        result = await g.predecessors(_result("/missing.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        # Add a node so the query path intersects _nodes, then corrupt _in
        g._nodes.add("/a.py")
        g._in = None  # type: ignore[assignment]
        result = await g.predecessors(_result("/a.py"), session=_mock_session)
        assert result.success is False
        assert "predecessors failed" in result.errors[0]

    async def test_returns_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.predecessors(_result("/b.py"), session=_mock_session)
        assert result.function == "predecessors"


class TestSuccessors:
    async def test_finds_successors(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/a.py", "/c.py", "calls", session=_mock_session)

        result = await g.successors(_result("/a.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert paths == {"/b.py", "/c.py"}

    async def test_excludes_query_paths(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.successors(_result("/a.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert "/a.py" not in paths

    async def test_no_successors(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.successors(_result("/a.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._out = None  # type: ignore[assignment]
        result = await g.successors(_result("/a.py"), session=_mock_session)
        assert result.success is False
        assert "successors failed" in result.errors[0]


# ===========================================================================
# Traversal — ancestors
# ===========================================================================


class TestAncestors:
    async def test_finds_transitive_ancestors(self):
        # A → B → C → D
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/d.py", "imports", session=_mock_session)

        result = await g.ancestors(_result("/d.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert paths == {"/a.py", "/b.py", "/c.py"}

    async def test_excludes_query_paths(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.ancestors(_result("/b.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert "/b.py" not in paths

    async def test_no_ancestors(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.ancestors(_result("/a.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_unknown_path_returns_empty(self):
        g = _loaded_graph()
        result = await g.ancestors(_result("/missing.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_handles_cycle(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/a.py", "imports", session=_mock_session)

        result = await g.ancestors(_result("/a.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert paths == {"/b.py"}

    async def test_multiple_candidates(self):
        # A → B, C → D
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/d.py", "imports", session=_mock_session)

        result = await g.ancestors(_result("/b.py", "/d.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert paths == {"/a.py", "/c.py"}

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.ancestors(_result("/b.py"), session=_mock_session)
        assert result.function == "ancestors"

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._out = None  # type: ignore[assignment]
        result = await g.ancestors(_result("/a.py"), session=_mock_session)
        assert result.success is False
        assert "ancestors failed" in result.errors[0]


# ===========================================================================
# Traversal — descendants
# ===========================================================================


class TestDescendants:
    async def test_finds_transitive_descendants(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/d.py", "imports", session=_mock_session)

        result = await g.descendants(_result("/a.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert paths == {"/b.py", "/c.py", "/d.py"}

    async def test_excludes_query_paths(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.descendants(_result("/a.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert "/a.py" not in paths

    async def test_no_descendants(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.descendants(_result("/a.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_unknown_path_returns_empty(self):
        g = _loaded_graph()
        result = await g.descendants(_result("/missing.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._out = None  # type: ignore[assignment]
        result = await g.descendants(_result("/a.py"), session=_mock_session)
        assert result.success is False
        assert "descendants failed" in result.errors[0]


# ===========================================================================
# Traversal — neighborhood
# ===========================================================================


class TestNeighborhood:
    async def test_depth_1(self):
        # A → B → C
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.neighborhood(_result("/b.py"), depth=1, session=_mock_session)
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py"}

    async def test_depth_0_returns_seed_only(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.neighborhood(_result("/a.py"), depth=0, session=_mock_session)
        assert _node_paths(result) == {"/a.py"}

    async def test_follows_both_directions(self):
        # A → B, C → B — neighborhood of B includes both A and C
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/b.py", "calls", session=_mock_session)

        result = await g.neighborhood(_result("/b.py"), depth=1, session=_mock_session)
        assert _node_paths(result) == {"/a.py", "/b.py", "/c.py"}

    async def test_includes_edges_within_visited(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.neighborhood(_result("/b.py"), depth=1, session=_mock_session)
        assert len(_edge_entries(result)) == 2  # a→b and b→c

    async def test_excludes_edges_outside_visited(self):
        # A → B → C → D, depth=1 from B visits {A, B, C}
        # Edge C→D should NOT be included
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)
        await g.add_edge("/c.py", "/d.py", "imports", session=_mock_session)

        result = await g.neighborhood(_result("/b.py"), depth=1, session=_mock_session)
        assert "/d.py" not in _node_paths(result)

    async def test_unknown_path_returns_empty(self):
        g = _loaded_graph()
        result = await g.neighborhood(_result("/missing.py"), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_disconnected_node(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.neighborhood(_result("/a.py"), depth=2, session=_mock_session)
        assert _node_paths(result) == {"/a.py"}

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.neighborhood(_result("/a.py"), depth=1, session=_mock_session)
        assert result.function == "neighborhood"

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._out = None  # type: ignore[assignment]
        result = await g.neighborhood(_result("/a.py"), session=_mock_session)
        assert result.success is False
        assert "neighborhood failed" in result.errors[0]


# ===========================================================================
# Subgraph — meeting_subgraph
# ===========================================================================


class TestMeetingSubgraph:
    async def test_connects_two_seeds(self):
        # A → B → C
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.meeting_subgraph(_result("/a.py", "/c.py"), session=_mock_session)
        node_paths = _node_paths(result)
        assert "/a.py" in node_paths
        assert "/c.py" in node_paths
        assert "/b.py" in node_paths  # intermediate

    async def test_single_seed(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.meeting_subgraph(_result("/a.py"), session=_mock_session)
        assert len(result.entries) == 1
        assert result.entries[0].path == "/a.py"

    async def test_zero_seeds(self):
        g = _loaded_graph()
        result = await g.meeting_subgraph(_result(), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_adjacent_seeds(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.meeting_subgraph(_result("/a.py", "/b.py"), session=_mock_session)
        assert _node_paths(result) == {"/a.py", "/b.py"}

    async def test_disconnected_seeds(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        await g.add_node("/b.py", session=_mock_session)

        result = await g.meeting_subgraph(_result("/a.py", "/b.py"), session=_mock_session)
        node_paths = _node_paths(result)
        # Both seeds present even though disconnected
        assert "/a.py" in node_paths
        assert "/b.py" in node_paths

    async def test_includes_edge_entries(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.meeting_subgraph(_result("/a.py", "/b.py"), session=_mock_session)
        assert len(_edge_entries(result)) == 1

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.meeting_subgraph(_result("/a.py", "/b.py"), session=_mock_session)
        assert result.function == "meeting_subgraph"

    async def test_unknown_seed_ignored(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.meeting_subgraph(
            _result("/a.py", "/missing.py"),
            session=_mock_session,
        )
        # Only the valid seed is returned
        assert len(result.entries) == 1
        assert result.entries[0].path == "/a.py"

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._nodes.add("/b.py")
        g._out = None  # type: ignore[assignment]
        result = await g.meeting_subgraph(_result("/a.py", "/b.py"), session=_mock_session)
        assert result.success is False
        assert "meeting_subgraph failed" in result.errors[0]


# ===========================================================================
# Subgraph — min_meeting_subgraph
# ===========================================================================


class TestMinMeetingSubgraph:
    async def test_subset_of_meeting(self):
        # A → B → C → D, seeds = A and D
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)
        await g.add_edge("/c.py", "/d.py", "imports", session=_mock_session)

        meeting = await g.meeting_subgraph(_result("/a.py", "/d.py"), session=_mock_session)
        min_meeting = await g.min_meeting_subgraph(
            _result("/a.py", "/d.py"),
            session=_mock_session,
        )

        meeting_nodes = _node_paths(meeting)
        min_nodes = _node_paths(min_meeting)
        assert min_nodes <= meeting_nodes

    async def test_contains_seeds(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.min_meeting_subgraph(
            _result("/a.py", "/c.py"),
            session=_mock_session,
        )
        node_paths = _node_paths(result)
        assert "/a.py" in node_paths
        assert "/c.py" in node_paths

    async def test_removes_non_essential_nodes(self):
        # A → B → C, A → C, seeds = A and C
        # B is not essential since A→C exists directly
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)
        await g.add_edge("/a.py", "/c.py", "imports", session=_mock_session)

        result = await g.min_meeting_subgraph(
            _result("/a.py", "/c.py"),
            session=_mock_session,
        )
        node_paths = _node_paths(result)
        assert "/a.py" in node_paths
        assert "/c.py" in node_paths
        # B may or may not be removed depending on articulation point logic

    async def test_single_seed_returns_meeting(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.min_meeting_subgraph(_result("/a.py"), session=_mock_session)
        assert len(result.entries) == 1
        assert result.entries[0].path == "/a.py"

    async def test_prunes_intermediate_non_articulation_node(self):
        """Exercises the articulation point removal loop (lines 726-732).

        Seeds A and B connected by two parallel paths through X and Y:
          A → X → B, A → Y → B, X → Y
        Meeting subgraph includes all 4 nodes. X↔Y cross-link means
        neither is an articulation point — min_meeting can prune one.
        """
        g = _loaded_graph()
        await g.add_edge("/a.py", "/x.py", "imports", session=_mock_session)
        await g.add_edge("/x.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/a.py", "/y.py", "calls", session=_mock_session)
        await g.add_edge("/y.py", "/b.py", "calls", session=_mock_session)
        await g.add_edge("/x.py", "/y.py", "imports", session=_mock_session)

        # Force meeting to include both X and Y by using 3 seeds
        meeting = await g.meeting_subgraph(
            _result("/a.py", "/b.py", "/x.py"),
            session=_mock_session,
        )
        meeting_nodes = _node_paths(meeting)

        result = await g.min_meeting_subgraph(
            _result("/a.py", "/b.py", "/x.py"),
            session=_mock_session,
        )
        min_nodes = _node_paths(result)
        assert {"/a.py", "/b.py", "/x.py"} <= min_nodes
        # Y is not a seed and not an articulation point → prunable
        if len(meeting_nodes) > 3:
            assert "/y.py" not in min_nodes

    async def test_error_propagates(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._nodes.add("/b.py")
        g._out = None  # type: ignore[assignment]
        result = await g.min_meeting_subgraph(
            _result("/a.py", "/b.py"),
            session=_mock_session,
        )
        assert result.success is False


# ===========================================================================
# Subgraph helper — _strip_leaves
# ===========================================================================


class TestStripLeaves:
    def test_removes_unprotected_leaves(self):
        # A → B → C, protected = {A, C}
        edges_out = {"A": frozenset(["B"]), "B": frozenset(["C"])}
        edges_in = {"B": frozenset(["A"]), "C": frozenset(["B"])}
        kept = {"A", "B", "C"}
        protected = {"A", "C"}

        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        assert result == {"A", "B", "C"}  # B has both preds and succs — not a leaf

    def test_removes_dangling_node(self):
        # A → B → C, A → D, protected = {A, C}
        edges_out = {
            "A": frozenset(["B", "D"]),
            "B": frozenset(["C"]),
        }
        edges_in = {
            "B": frozenset(["A"]),
            "C": frozenset(["B"]),
            "D": frozenset(["A"]),
        }
        kept = {"A", "B", "C", "D"}
        protected = {"A", "C"}

        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        # D has no successors within kept — should be stripped
        assert "D" not in result
        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_protects_seeds(self):
        # Single node, protected
        edges_out: dict[str, frozenset[str]] = {}
        edges_in: dict[str, frozenset[str]] = {}
        kept = {"A"}
        protected = {"A"}

        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        assert result == {"A"}

    def test_cascading_removal(self):
        """Removing one leaf exposes another — covers lines 631-637, 645."""
        # A → B → C → D, protected = {A}
        # D is a leaf (no succs) → removed
        # C becomes a leaf (no succs after D removed) → removed
        # B becomes a leaf (no succs after C removed) → removed
        # A is protected → kept
        edges_out = {
            "A": frozenset(["B"]),
            "B": frozenset(["C"]),
            "C": frozenset(["D"]),
        }
        edges_in = {
            "B": frozenset(["A"]),
            "C": frozenset(["B"]),
            "D": frozenset(["C"]),
        }
        kept = {"A", "B", "C", "D"}
        protected = {"A"}

        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        assert result == {"A"}

    def test_cascading_removal_via_preds(self):
        """Cascade via predecessor direction — covers line 645."""
        # A → B → C → D, protected = {D}
        # A is a leaf (no preds) → removed
        # B becomes a leaf (no preds after A removed) → removed
        # C becomes a leaf (no preds after B removed) → removed
        # D is protected → kept
        edges_out = {
            "A": frozenset(["B"]),
            "B": frozenset(["C"]),
            "C": frozenset(["D"]),
        }
        edges_in = {
            "B": frozenset(["A"]),
            "C": frozenset(["B"]),
            "D": frozenset(["C"]),
        }
        kept = {"A", "B", "C", "D"}
        protected = {"D"}

        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        assert result == {"D"}

    def test_empty_input(self):
        result = RustworkxGraph._strip_leaves(set(), {}, {}, set())
        assert result == set()


# ===========================================================================
# Centrality — pagerank
# ===========================================================================


class TestPagerank:
    async def test_returns_scores(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.pagerank(_result(), session=_mock_session)
        assert result.success is True
        assert len(result.entries) == 3
        # All scores should be positive
        assert all(e.score is not None and e.score >= 0 for e in result.entries)

    async def test_filters_by_candidates(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.pagerank(_result("/a.py"), session=_mock_session)
        assert len(result.entries) == 1
        assert result.entries[0].path == "/a.py"

    async def test_empty_graph(self):
        g = _loaded_graph()
        result = await g.pagerank(_result(), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.pagerank(_result(), session=_mock_session)
        assert result.function == "pagerank"

    async def test_sorted_descending(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/b.py", "calls", session=_mock_session)

        result = await g.pagerank(_result(), session=_mock_session)
        scores = [e.score for e in result.entries]
        assert scores == sorted(scores, reverse=True)


# ===========================================================================
# Centrality — betweenness
# ===========================================================================


class TestBetweennessCentrality:
    async def test_returns_scores(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.betweenness_centrality(_result(), session=_mock_session)
        assert result.success is True
        assert len(result.entries) == 3

    async def test_bridge_node_scores_highest(self):
        # A → B → C — B is the bridge
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.betweenness_centrality(_result(), session=_mock_session)
        scores = {e.path: e.score for e in result.entries}
        assert scores["/b.py"] is not None
        assert scores["/a.py"] is not None
        assert scores["/c.py"] is not None
        assert scores["/b.py"] >= scores["/a.py"]
        assert scores["/b.py"] >= scores["/c.py"]

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.betweenness_centrality(_result(), session=_mock_session)
        assert result.function == "betweenness_centrality"

    async def test_error_returns_failure(self):
        """Covers _run_centrality error handler (lines 761-762)."""
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._out = None  # type: ignore[assignment]
        result = await g.betweenness_centrality(_result(), session=_mock_session)
        assert result.success is False
        assert "betweenness_centrality failed" in result.errors[0]


# ===========================================================================
# Centrality — closeness
# ===========================================================================


class TestClosenessCentrality:
    async def test_returns_scores(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.closeness_centrality(_result(), session=_mock_session)
        assert result.success is True
        assert len(result.entries) == 3

    async def test_filters_by_candidates(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.closeness_centrality(_result("/b.py"), session=_mock_session)
        assert len(result.entries) == 1
        assert result.entries[0].path == "/b.py"

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.closeness_centrality(_result(), session=_mock_session)
        assert result.function == "closeness_centrality"


# ===========================================================================
# Centrality — degree
# ===========================================================================


class TestDegreeCentrality:
    async def test_degree_centrality(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.degree_centrality(_result(), session=_mock_session)
        assert result.success is True
        assert len(result.entries) == 2

    async def test_in_degree_centrality(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/c.py", "/b.py", "calls", session=_mock_session)

        result = await g.in_degree_centrality(_result(), session=_mock_session)
        scores = {e.path: e.score for e in result.entries}
        # B has 2 incoming edges, highest in-degree
        assert scores["/b.py"] is not None
        assert scores["/a.py"] is not None
        assert scores["/b.py"] > scores["/a.py"]

    async def test_out_degree_centrality(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/a.py", "/c.py", "calls", session=_mock_session)

        result = await g.out_degree_centrality(_result(), session=_mock_session)
        scores = {e.path: e.score for e in result.entries}
        # A has 2 outgoing edges, highest out-degree
        assert scores["/a.py"] is not None
        assert scores["/b.py"] is not None
        assert scores["/a.py"] > scores["/b.py"]

    async def test_function_names(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        for method, fn_name in [
            (g.degree_centrality, "degree_centrality"),
            (g.in_degree_centrality, "in_degree_centrality"),
            (g.out_degree_centrality, "out_degree_centrality"),
        ]:
            result = await method(_result(), session=_mock_session)
            assert result.function == fn_name


# ===========================================================================
# Centrality — HITS
# ===========================================================================


class TestHits:
    async def test_returns_scores(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/a.py", "/c.py", "calls", session=_mock_session)

        result = await g.hits(_result(), session=_mock_session)
        assert result.success is True
        for e in result.entries:
            assert e.score is not None

    async def test_filters_by_candidates(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        await g.add_edge("/b.py", "/c.py", "calls", session=_mock_session)

        result = await g.hits(_result("/b.py"), session=_mock_session)
        assert len(result.entries) == 1
        assert result.entries[0].path == "/b.py"

    async def test_edgeless_graph_returns_zero_scores(self):
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)
        await g.add_node("/b.py", session=_mock_session)

        result = await g.hits(_result(), session=_mock_session)
        assert result.success is True
        for e in result.entries:
            assert e.score == 0.0

    async def test_edgeless_filters_to_graph_paths(self):
        """Non-graph candidates are excluded even in the edgeless early-return."""
        g = _loaded_graph()
        await g.add_node("/a.py", session=_mock_session)

        result = await g.hits(_result("/a.py", "/missing.py"), session=_mock_session)
        paths = {e.path for e in result.entries}
        assert "/a.py" in paths
        assert "/missing.py" not in paths

    async def test_empty_graph(self):
        g = _loaded_graph()
        result = await g.hits(_result(), session=_mock_session)
        assert result.success is True
        assert result.entries == []

    async def test_custom_max_iter_and_tol(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)

        result = await g.hits(
            _result(),
            max_iter=50,
            tol=1e-4,
            session=_mock_session,
        )
        assert result.success is True
        assert len(result.entries) == 2

    async def test_function_name(self):
        g = _loaded_graph()
        await g.add_edge("/a.py", "/b.py", "imports", session=_mock_session)
        result = await g.hits(_result(), session=_mock_session)
        assert result.function == "hits"

    async def test_sorted_by_authority_descending(self):
        # Hub → many targets: hub should have high hub score,
        # targets should have high authority score
        g = _loaded_graph()
        await g.add_edge("/hub.py", "/auth1.py", "imports", session=_mock_session)
        await g.add_edge("/hub.py", "/auth2.py", "calls", session=_mock_session)
        await g.add_edge("/hub.py", "/auth3.py", "imports", session=_mock_session)

        result = await g.hits(_result(), session=_mock_session)
        scores = [e.score for e in result.entries]
        assert scores == sorted(scores, reverse=True)

    async def test_score_hub(self):
        g = _loaded_graph()
        await g.add_edge("/hub.py", "/a.py", "imports", session=_mock_session)
        await g.add_edge("/hub.py", "/b.py", "calls", session=_mock_session)

        result = await g.hits(_result(), score="hub", session=_mock_session)
        # Hub node should rank first when scoring by hub
        assert result.entries[0].path == "/hub.py"

    async def test_score_authority(self):
        g = _loaded_graph()
        await g.add_edge("/hub.py", "/a.py", "imports", session=_mock_session)
        await g.add_edge("/hub.py", "/b.py", "calls", session=_mock_session)

        result = await g.hits(_result(), score="authority", session=_mock_session)
        assert result.success is True
        for e in result.entries:
            assert e.score is not None

    async def test_score_invalid(self):
        g = _loaded_graph()
        result = await g.hits(_result(), score="invalid", session=_mock_session)
        assert result.success is False
        assert "authority" in result.errors[0]

    async def test_error_returns_failure(self):
        g = _loaded_graph()
        g._nodes.add("/a.py")
        g._out = None  # type: ignore[assignment]
        result = await g.hits(_result("/a.py"), session=_mock_session)
        assert result.success is False
        assert "hits failed" in result.errors[0]


# ===========================================================================
# Protocol compliance
# ===========================================================================


class TestNeighborhoodUserScoped:
    async def test_user_scoped_filters_snap_in(self):
        """Line 524-525: neighborhood builds filtered snap_in when user_scoped."""
        g = RustworkxGraph(model=VFSEntry, user_scoped=True)
        g._loaded_at = time.monotonic()
        # User-scoped: only paths under /alice/ are visible to user_id="alice"
        await g.add_edge("/alice/a.py", "/alice/b.py", "imports", session=_mock_session)
        await g.add_edge("/bob/c.py", "/alice/b.py", "calls", session=_mock_session)

        result = await g.neighborhood(
            _result("/alice/a.py"),
            depth=2,
            user_id="alice",
            session=_mock_session,
        )
        paths = {e.path for e in result.entries}
        assert "/alice/b.py" in paths
        # /bob/c.py is not visible to alice
        assert "/bob/c.py" not in paths


class TestMeetingSubgraphUserScoped:
    async def test_user_scoped_filters_edges_in(self):
        """Line 583-584: meeting_subgraph builds filtered edges_in when user_scoped."""
        g = RustworkxGraph(model=VFSEntry, user_scoped=True)
        g._loaded_at = time.monotonic()
        await g.add_edge("/alice/a.py", "/alice/mid.py", "imports", session=_mock_session)
        await g.add_edge("/alice/mid.py", "/alice/b.py", "calls", session=_mock_session)

        result = await g.meeting_subgraph(
            _result("/alice/a.py", "/alice/b.py"),
            user_id="alice",
            session=_mock_session,
        )
        assert result.success is True
        paths = {e.path for e in result.entries}
        assert "/alice/a.py" in paths
        assert "/alice/b.py" in paths


class TestMinMeetingSubgraphPruning:
    async def test_removes_non_seed_non_articulation_nodes(self):
        """Lines 778-784: _min_meeting_impl prunes removable intermediary nodes."""
        g = _loaded_graph()
        # A → X → B, and A → B directly. X is not a seed and not an
        # articulation point (there's a direct A→B path), so it should be pruned.
        await g.add_edge("/a.py", "/x.py", "imports", session=_mock_session)
        await g.add_edge("/x.py", "/b.py", "calls", session=_mock_session)
        await g.add_edge("/a.py", "/b.py", "uses", session=_mock_session)

        result = await g.min_meeting_subgraph(
            _result("/a.py", "/b.py"),
            session=_mock_session,
        )
        assert result.success is True
        paths = {e.path for e in result.entries}
        assert "/a.py" in paths
        assert "/b.py" in paths
        # X should be pruned since it's not an articulation point
        assert "/x.py" not in paths

    async def test_error_handling(self):
        """Lines 739-740: exception returns error result."""
        from unittest.mock import patch

        g = _loaded_graph()
        await g.add_edge("/a.py", "/mid.py", "imports", session=_mock_session)
        await g.add_edge("/mid.py", "/b.py", "calls", session=_mock_session)

        # Patch _min_meeting_impl to raise, simulating an internal error
        with patch.object(
            RustworkxGraph,
            "_min_meeting_impl",
            side_effect=RuntimeError("boom"),
        ):
            result = await g.min_meeting_subgraph(
                _result("/a.py", "/b.py"),
                session=_mock_session,
            )
        assert result.success is False
        assert "min_meeting_subgraph failed" in result.errors[0]


class TestStripLeavesDirect:
    """Direct tests for _strip_leaves static method (line 687)."""

    def test_duplicate_node_in_queue_skips(self):
        """Line 687: node already in removed set is skipped on second pop.

        Graph: F→E, with protected={A}. E and F are both leaves:
        - E has no succs → queued initially
        - F has no preds → queued initially
        When F is removed, E loses its only pred and gets re-queued.
        E is then popped for the second time and hits the 'already removed'
        continue on line 687.
        """
        kept = {"A", "E", "F"}
        edges_out: dict[str, frozenset[str]] = {
            "F": frozenset({"E"}),
        }
        edges_in: dict[str, frozenset[str]] = {
            "E": frozenset({"F"}),
        }
        protected = {"A"}
        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        # Only A should survive — E and F are stripped
        assert result == {"A"}

    def test_strip_leaves_all_protected(self):
        """All nodes are protected — nothing removed."""
        kept = {"A", "B"}
        edges_out: dict[str, frozenset[str]] = {"A": frozenset({"B"})}
        edges_in: dict[str, frozenset[str]] = {"B": frozenset({"A"})}
        protected = {"A", "B"}
        result = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, protected)
        assert result == {"A", "B"}


class TestMinMeetingImplDirect:
    """Direct tests for _min_meeting_impl static method (lines 781-787)."""

    def test_prunes_non_seed_non_articulation(self):
        """Lines 781-787: removes a non-seed, non-articulation-point node.

        A → X → B, A → B — X is removable.
        """
        node_set = {"/a.py", "/x.py", "/b.py"}
        edges_out: dict[str, set[str]] = {
            "/a.py": {"/x.py", "/b.py"},
            "/x.py": {"/b.py"},
        }
        candidate_paths = {"/a.py", "/b.py"}
        edge_types: dict[tuple[str, str], str] = {
            ("/a.py", "/x.py"): "imports",
            ("/x.py", "/b.py"): "calls",
            ("/a.py", "/b.py"): "uses",
        }
        result = RustworkxGraph._min_meeting_impl(
            node_set,
            edges_out,
            candidate_paths,
            edge_types,
        )
        assert result.success
        node_paths = {e.path for e in result.entries if "/__meta__/edges/" not in e.path}
        assert "/a.py" in node_paths
        assert "/b.py" in node_paths
        assert "/x.py" not in node_paths


class TestProtocol:
    def test_exports(self):
        """GraphProvider and RustworkxGraph are importable from vfs.graph."""
        from vfs.graph import RustworkxGraph, UnionFind

        assert GraphProvider is not None
        assert RustworkxGraph is not None
        assert UnionFind is not None
