"""GraphOpsMixin — graph query and connection operations for GroverAsync."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grover.exceptions import CapabilityNotSupportedError, MountNotFoundError
from grover.results import (
    AncestorsResult,
    BetweennessResult,
    ClosenessResult,
    CommonNeighborsResult,
    ConnectionResult,
    DegreeResult,
    DescendantsResult,
    EgoGraphResult,
    FileCandidate,
    GraphEvidence,
    HarmonicResult,
    HasPathResult,
    HitsResult,
    KatzResult,
    MeetingSubgraphResult,
    PageRankResult,
    PredecessorsResult,
    ShortestPathResult,
    SubgraphSearchResult,
    SuccessorsResult,
)
from grover.util.paths import normalize_path

if TYPE_CHECKING:
    from grover.api.context import GroverContext
    from grover.providers.graph.protocol import GraphStore
    from grover.results import FileSearchResult


class GraphOpsMixin:
    """Graph query, algorithm, and connection operations extracted from GroverAsync."""

    _ctx: GroverContext

    def get_graph(self, path: str | None = None) -> GraphStore:
        """Return the graph for the mount owning *path*, or the first available."""
        return self._ctx.resolve_graph_any(path)

    # ------------------------------------------------------------------
    # Connection operations (persist through FS, graph updated via worker)
    # ------------------------------------------------------------------

    async def add_connection(
        self,
        source_path: str,
        target_path: str,
        connection_type: str,
        *,
        weight: float = 1.0,
    ) -> ConnectionResult:
        """Add a connection between two files, persisted through the filesystem."""
        source_path = normalize_path(source_path)
        target_path = normalize_path(target_path)

        if err := self._ctx.check_writable(source_path):
            return ConnectionResult(
                success=False,
                message=err,
                source_path=source_path,
                target_path=target_path,
                connection_type=connection_type,
            )

        try:
            mount, _rel = self._ctx.registry.resolve(source_path)
        except MountNotFoundError:
            return ConnectionResult(
                success=False,
                message=f"No mount found for path: {source_path}",
                source_path=source_path,
                target_path=target_path,
                connection_type=connection_type,
            )

        assert mount.filesystem is not None
        async with self._ctx.session_for(mount) as sess:
            result = await mount.filesystem.add_connection(
                source_path,
                target_path,
                connection_type,
                weight=weight,
                session=sess,
            )

        if result.success:
            self._ctx.worker.schedule_immediate(
                self._process_connection_added(source_path, target_path, connection_type, weight)  # type: ignore[attr-defined]
            )

        return result

    async def delete_connection(
        self,
        source_path: str,
        target_path: str,
        *,
        connection_type: str | None = None,
    ) -> ConnectionResult:
        """Delete a connection between two files."""
        source_path = normalize_path(source_path)
        target_path = normalize_path(target_path)

        if err := self._ctx.check_writable(source_path):
            return ConnectionResult(
                success=False,
                message=err,
                source_path=source_path,
                target_path=target_path,
                connection_type=connection_type or "",
            )

        try:
            mount, _rel = self._ctx.registry.resolve(source_path)
        except MountNotFoundError:
            return ConnectionResult(
                success=False,
                message=f"No mount found for path: {source_path}",
                source_path=source_path,
                target_path=target_path,
                connection_type=connection_type or "",
            )

        assert mount.filesystem is not None
        async with self._ctx.session_for(mount) as sess:
            result = await mount.filesystem.delete_connection(
                source_path,
                target_path,
                connection_type=connection_type,
                session=sess,
            )

        if result.success:
            self._ctx.worker.schedule_immediate(
                self._process_connection_deleted(source_path, target_path)  # type: ignore[attr-defined]
            )

        return result

    # ------------------------------------------------------------------
    # Traversal queries
    # ------------------------------------------------------------------

    def predecessors(self, path: str) -> PredecessorsResult:
        """Return graph predecessors of *path* (nodes with edges pointing to it)."""
        refs = self._ctx.resolve_graph(path).predecessors(path)
        return PredecessorsResult.from_refs(refs, operation="predecessors")

    def successors(self, path: str) -> SuccessorsResult:
        """Return graph successors of *path* (nodes it points to)."""
        refs = self._ctx.resolve_graph(path).successors(path)
        return SuccessorsResult.from_refs(refs, operation="successors")

    def ancestors(self, path: str) -> AncestorsResult:
        """Return all nodes reachable by following edges backward from *path*."""
        graph = self._ctx.resolve_graph(path)
        result = graph.ancestors(path)
        return AncestorsResult.from_paths(sorted(result), operation="ancestors")

    def descendants(self, path: str) -> DescendantsResult:
        """Return all nodes reachable by following edges forward from *path*."""
        graph = self._ctx.resolve_graph(path)
        result = graph.descendants(path)
        return DescendantsResult.from_paths(sorted(result), operation="descendants")

    def shortest_path(self, source: str, target: str) -> ShortestPathResult:
        """Return the shortest path from *source* to *target*."""
        refs = self._ctx.resolve_graph(source).path_between(source, target)
        if refs is None:
            return ShortestPathResult(
                success=True,
                message="No path found",
            )
        return ShortestPathResult.from_refs(refs, operation="shortest_path")

    def has_path(self, source: str, target: str) -> HasPathResult:
        """Check if a directed path exists from *source* to *target*.

        ``bool(result)`` is ``True`` if a path exists, ``False`` otherwise.
        When a path exists, the result contains the path nodes.
        """
        graph = self._ctx.resolve_graph(source)
        refs = graph.path_between(source, target)
        if refs is None:
            return HasPathResult(
                success=True,
                message="No path exists",
            )
        return HasPathResult.from_refs(refs, operation="has_path")

    # ------------------------------------------------------------------
    # Subgraph extraction
    # ------------------------------------------------------------------

    def subgraph(
        self,
        candidates: FileSearchResult,
        *,
        path: str | None = None,
    ) -> SubgraphSearchResult:
        """Extract the induced subgraph for nodes in *candidates*."""
        graph = self._ctx.resolve_graph_any(path)
        paths = list(candidates.paths)
        sub = graph.subgraph(paths)
        return SubgraphSearchResult.from_subgraph(sub, operation="subgraph")

    def min_meeting_subgraph(
        self,
        candidates: FileSearchResult,
        *,
        max_size: int = 50,
    ) -> MeetingSubgraphResult:
        """Extract the subgraph connecting candidate nodes via shortest paths."""
        paths = list(candidates.paths)
        graph = self._ctx.resolve_graph_any(paths[0] if paths else None)
        sub = graph.meeting_subgraph(paths, max_size=max_size)
        return MeetingSubgraphResult.from_subgraph(sub, operation="min_meeting_subgraph")

    def ego_graph(
        self,
        path: str,
        *,
        max_depth: int = 2,
        direction: str = "both",
        edge_types: list[str] | None = None,
    ) -> EgoGraphResult:
        """Extract the neighborhood subgraph around *path*."""
        graph = self._ctx.resolve_graph(path)
        sub = graph.neighborhood(
            path,
            max_depth=max_depth,
            direction=direction,
            edge_types=edge_types,
        )
        return EgoGraphResult.from_subgraph(sub, operation="ego_graph")

    # ------------------------------------------------------------------
    # Centrality algorithms
    # ------------------------------------------------------------------

    def _filter_scores(
        self,
        scores: dict[str, float],
        candidates: FileSearchResult | None,
    ) -> dict[str, float]:
        """Filter scores dict to only candidate paths if provided."""
        if candidates is not None:
            candidate_paths = set(candidates.paths)
            return {p: s for p, s in scores.items() if p in candidate_paths}
        return scores

    def pagerank(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
        personalization: dict[str, float] | None = None,
    ) -> PageRankResult:
        """Run PageRank on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.pagerank(personalization=personalization)
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return PageRankResult.from_scored(scores, operation="pagerank", algorithm="pagerank")

    def betweenness_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> BetweennessResult:
        """Betweenness centrality on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.betweenness_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return BetweennessResult.from_scored(
            scores, operation="betweenness_centrality", algorithm="betweenness_centrality"
        )

    def closeness_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> ClosenessResult:
        """Closeness centrality on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.closeness_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return ClosenessResult.from_scored(
            scores, operation="closeness_centrality", algorithm="closeness_centrality"
        )

    def harmonic_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> HarmonicResult:
        """Harmonic centrality on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.harmonic_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return HarmonicResult.from_scored(
            scores, operation="harmonic_centrality", algorithm="harmonic_centrality"
        )

    def katz_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> KatzResult:
        """Katz centrality on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.katz_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return KatzResult.from_scored(
            scores, operation="katz_centrality", algorithm="katz_centrality"
        )

    def degree_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> DegreeResult:
        """Degree centrality (in + out) on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.degree_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return DegreeResult.from_scored(
            scores, operation="degree_centrality", algorithm="degree_centrality"
        )

    def in_degree_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> DegreeResult:
        """In-degree centrality on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.in_degree_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return DegreeResult.from_scored(
            scores, operation="in_degree_centrality", algorithm="in_degree_centrality"
        )

    def out_degree_centrality(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> DegreeResult:
        """Out-degree centrality on the knowledge graph."""
        graph = self._ctx.resolve_graph_any(path)
        try:
            scores = graph.out_degree_centrality()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError(
                "Graph backend does not support centrality algorithms"
            ) from None
        scores = self._filter_scores(scores, candidates)
        return DegreeResult.from_scored(
            scores, operation="out_degree_centrality", algorithm="out_degree_centrality"
        )

    def hits(
        self,
        *,
        path: str | None = None,
        candidates: FileSearchResult | None = None,
    ) -> HitsResult:
        """HITS hub and authority scores.

        Each candidate gets two evidence records: ``hits_authority`` and ``hits_hub``.
        """
        graph = self._ctx.resolve_graph_any(path)
        try:
            hubs, auths = graph.hits()
        except (AttributeError, NotImplementedError):
            raise CapabilityNotSupportedError("Graph backend does not support HITS") from None
        if candidates is not None:
            candidate_paths = set(candidates.paths)
            hubs = {p: s for p, s in hubs.items() if p in candidate_paths}
            auths = {p: s for p, s in auths.items() if p in candidate_paths}
        all_paths = set(hubs) | set(auths)
        file_candidates = [
            FileCandidate(
                path=p,
                evidence=[
                    GraphEvidence(
                        operation="hits_authority", algorithm="hits", score=auths.get(p, 0.0)
                    ),
                    GraphEvidence(operation="hits_hub", algorithm="hits", score=hubs.get(p, 0.0)),
                ],
            )
            for p in sorted(all_paths, key=lambda p: auths.get(p, 0.0), reverse=True)
        ]
        return HitsResult(
            success=True,
            message=f"HITS computed for {len(file_candidates)} node(s)",
            file_candidates=file_candidates,
        )

    # ------------------------------------------------------------------
    # Other graph operations
    # ------------------------------------------------------------------

    def common_neighbors(
        self,
        path1: str,
        path2: str,
        *,
        path: str | None = None,
    ) -> CommonNeighborsResult:
        """Find common neighbors of two nodes."""
        graph = self._ctx.resolve_graph_any(path)
        neighbors = graph.common_neighbors(path1, path2)
        return CommonNeighborsResult.from_paths(sorted(neighbors), operation="common_neighbors")
