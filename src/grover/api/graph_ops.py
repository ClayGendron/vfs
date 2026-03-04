"""GraphOpsMixin — graph query operations for GroverAsync."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grover.exceptions import CapabilityNotSupportedError
from grover.results import (
    FileCandidate,
    GraphEvidence,
    GraphResult,
)

if TYPE_CHECKING:
    from grover.api.context import GroverContext
    from grover.providers.graph.protocol import GraphStore


class GraphOpsMixin:
    """Graph query operations extracted from GroverAsync."""

    _ctx: GroverContext

    def get_graph(self, path: str | None = None) -> GraphStore:
        """Return the graph for the mount owning *path*, or the first available.

        This replaces the old ``self.graph`` attribute which was removed
        in favor of per-mount graphs.
        """
        return self._ctx.resolve_graph_any(path)

    # ------------------------------------------------------------------
    # Graph query wrappers (resolve mount → delegate to backend's graph)
    # ------------------------------------------------------------------

    def predecessors(self, path: str) -> GraphResult:
        """Return graph predecessors of *path* (nodes with edges pointing to it)."""
        refs = self._ctx.resolve_graph(path).predecessors(path)
        return GraphResult.from_refs(refs, operation="predecessors")

    def successors(self, path: str) -> GraphResult:
        """Return graph successors of *path* (nodes it points to)."""
        refs = self._ctx.resolve_graph(path).successors(path)
        return GraphResult.from_refs(refs, operation="successors")

    def path_between(self, source: str, target: str) -> GraphResult:
        """Return the shortest path from *source* to *target*."""
        refs = self._ctx.resolve_graph(source).path_between(source, target)
        if refs is None:
            return GraphResult(
                success=True,
                message="No path found",
            )
        return GraphResult.from_refs(refs, operation="path_between")

    def contains(self, path: str) -> GraphResult:
        """Return files contained by *path*."""
        refs = self._ctx.resolve_graph(path).contains(path)
        return GraphResult.from_refs(refs, operation="contains")

    # ------------------------------------------------------------------
    # Graph algorithm wrappers (capability-checked)
    # ------------------------------------------------------------------

    def pagerank(
        self,
        *,
        personalization: dict[str, float] | None = None,
        path: str | None = None,
    ) -> GraphResult:
        """Run PageRank on the knowledge graph.

        *path* selects which mount's graph to use (defaults to first visible).
        Raises :class:`~grover.exceptions.CapabilityNotSupportedError` if
        the graph backend does not support centrality algorithms.
        """
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.pagerank(personalization=personalization)
        except (AttributeError, NotImplementedError):
            msg = "Graph backend does not support centrality algorithms"
            raise CapabilityNotSupportedError(msg) from None
        candidates = [
            FileCandidate(
                path=node_path,
                evidence=[
                    GraphEvidence(
                        operation="pagerank",
                        algorithm="pagerank",
                    )
                ],
            )
            for node_path in scores
        ]
        return GraphResult(
            success=True,
            message=f"PageRank computed for {len(candidates)} node(s)",
            file_candidates=candidates,
        )

    def meeting_subgraph(
        self,
        paths: list[str],
        *,
        max_size: int = 50,
    ) -> GraphResult:
        """Extract the subgraph connecting *paths* via shortest paths."""
        graph = self._ctx.resolve_graph_any(paths[0] if paths else None)
        try:
            sub = graph.meeting_subgraph(paths, max_size=max_size)
        except (AttributeError, NotImplementedError):
            msg = "Graph backend does not support subgraph extraction"
            raise CapabilityNotSupportedError(msg) from None
        return GraphResult.from_paths(sorted(sub.nodes), operation="meeting_subgraph")

    def neighborhood(
        self,
        path: str,
        *,
        max_depth: int = 2,
        direction: str = "both",
        edge_types: list[str] | None = None,
    ) -> GraphResult:
        """Extract the neighborhood subgraph around *path*."""
        graph = self._ctx.resolve_graph(path)
        try:
            sub = graph.neighborhood(
                path,
                max_depth=max_depth,
                direction=direction,
                edge_types=edge_types,
            )
        except (AttributeError, NotImplementedError):
            msg = "Graph backend does not support subgraph extraction"
            raise CapabilityNotSupportedError(msg) from None
        return GraphResult.from_paths(sorted(sub.nodes), operation="neighborhood")

    def find_nodes(self, *, path: str | None = None, **attrs: object) -> GraphResult:
        """Find graph nodes matching all attribute predicates."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            node_list = graph.find_nodes(**attrs)
        except (AttributeError, NotImplementedError):
            msg = "Graph backend does not support filtering"
            raise CapabilityNotSupportedError(msg) from None
        return GraphResult.from_paths(node_list, operation="find_nodes")
