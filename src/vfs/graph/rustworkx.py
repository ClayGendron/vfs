"""RustworkxGraph — rustworkx-backed graph implementing GraphProvider.

Stores topology as ``_nodes`` (set of paths) and adjacency dicts
``_out`` (source → targets) / ``_in`` (target → sources).
No tuple-per-edge allocation — O(degree) lookups for predecessors
and successors instead of O(|E|) scans.

Query/algorithm methods are ``async def``:
- Light reads run inline (no thread overhead).
- Heavy algorithms use ``asyncio.to_thread`` with a snapshot for concurrency.

Mutations stay synchronous (trivial set operations, called from background tasks).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import TYPE_CHECKING, Any

import rustworkx
from sqlmodel import select

from vfs.paths import decompose_edge, edge_out_path
from vfs.results import Entry, VFSResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import VFSEntry


# ---------------------------------------------------------------------------
# Union-Find — used by meeting_subgraph
# ---------------------------------------------------------------------------


class UnionFind:
    """Path-compressed union-find with rank balancing."""

    __slots__ = ("components", "parent", "rank")

    def __init__(self, elements: list[str]) -> None:
        self.parent = {e: e for e in elements}
        self.rank = dict.fromkeys(elements, 0)
        self.components = len(self.parent)

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.components -= 1
        return True


# ---------------------------------------------------------------------------
# RustworkxGraph
# ---------------------------------------------------------------------------


class RustworkxGraph:
    """Directed knowledge graph over file paths.

    Implements the ``GraphProvider`` protocol.
    """

    DEFAULT_TTL: float = 3600  # 1 hour

    def __init__(self, model: type[VFSEntry], *, ttl: float | None = None, user_scoped: bool = False) -> None:
        self._model = model
        self._ttl = ttl if ttl is not None else self.DEFAULT_TTL
        self._user_scoped = user_scoped
        self._nodes: set[str] = set()
        self._out: dict[str, set[str]] = {}  # source → targets
        self._in: dict[str, set[str]] = {}  # target → sources
        self._edge_types: dict[tuple[str, str], str] = {}  # (source, target) → type
        self._loaded_at: float | None = None

    def __repr__(self) -> str:
        edge_count = sum(len(ts) for ts in self._out.values())
        return f"RustworkxGraph(nodes={len(self._nodes)}, edges={edge_count})"

    def invalidate(self) -> None:
        """Force a DB reload on the next ``ensure_fresh`` call."""
        self._loaded_at = None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def add_node(self, path: str, *, session: AsyncSession) -> None:
        """Add a node. Idempotent."""
        await self.ensure_fresh(session)
        self._nodes.add(path)

    async def remove_node(self, path: str, *, session: AsyncSession) -> None:
        """Remove a node and all incident edges. Raises ``KeyError`` if missing."""
        await self.ensure_fresh(session)
        if path not in self._nodes:
            msg = f"Node not found: {path!r}"
            raise KeyError(msg)
        self._nodes.discard(path)
        # Remove outgoing edges
        for t in self._out.pop(path, set()):
            self._edge_types.pop((path, t), None)
            in_set = self._in.get(t)
            if in_set is not None:
                in_set.discard(path)
                if not in_set:
                    del self._in[t]
        # Remove incoming edges
        for s in self._in.pop(path, set()):
            self._edge_types.pop((s, path), None)
            out_set = self._out.get(s)
            if out_set is not None:
                out_set.discard(path)
                if not out_set:
                    del self._out[s]

    async def has_node(self, path: str, *, session: AsyncSession) -> bool:
        await self.ensure_fresh(session)
        return path in self._nodes

    async def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        *,
        weight: float = 1.0,
        session: AsyncSession,
    ) -> None:
        """Add a directed edge. Auto-creates missing endpoint nodes."""
        await self.ensure_fresh(session)
        self._nodes.add(source)
        self._nodes.add(target)
        self._out.setdefault(source, set()).add(target)
        self._in.setdefault(target, set()).add(source)
        self._edge_types[(source, target)] = edge_type

    async def remove_edge(self, source: str, target: str, *, session: AsyncSession) -> None:
        """Remove the edge between *source* and *target*. Raises ``KeyError``."""
        await self.ensure_fresh(session)
        if source not in self._nodes:
            msg = f"Node not found: {source!r}"
            raise KeyError(msg)
        if target not in self._nodes:
            msg = f"Node not found: {target!r}"
            raise KeyError(msg)
        if target not in self._out.get(source, set()):
            msg = f"No edge from {source!r} to {target!r}"
            raise KeyError(msg)
        out_set = self._out.get(source)
        if out_set is not None:
            out_set.discard(target)
            if not out_set:
                del self._out[source]
        in_set = self._in.get(target)
        if in_set is not None:
            in_set.discard(source)
            if not in_set:
                del self._in[target]
        self._edge_types.pop((source, target), None)

    async def has_edge(self, source: str, target: str, *, session: AsyncSession) -> bool:
        await self.ensure_fresh(session)
        return target in self._out.get(source, set())

    @property
    def nodes(self) -> set[str]:
        return self._nodes

    # ------------------------------------------------------------------
    # Snapshot and graph construction helpers
    # ------------------------------------------------------------------

    def _snapshot(self, user_id: str | None = None) -> tuple[frozenset[str], dict[str, frozenset[str]]]:
        """Return immutable copies of nodes and edges for thread-safe reads.

        When *user_id* is provided on a user-scoped graph, only nodes
        and edges belonging to that user (path prefix ``/{user_id}/``)
        are included.
        """
        if self._user_scoped and user_id:
            prefix = f"/{user_id}/"
            user_nodes = frozenset(n for n in self._nodes if n.startswith(prefix))
            user_edges = {
                s: frozenset(t for t in ts if t in user_nodes) for s, ts in self._out.items() if s in user_nodes
            }
            return user_nodes, user_edges
        return (
            frozenset(self._nodes),
            {s: frozenset(ts) for s, ts in self._out.items()},
        )

    @staticmethod
    def _build_graph_from(
        nodes: frozenset[str],
        edges_out: dict[str, frozenset[str]],
    ) -> tuple[rustworkx.PyDiGraph, dict[str, int], dict[int, str]]:
        """Build a PyDiGraph from node set and adjacency dict."""
        graph: rustworkx.PyDiGraph = rustworkx.PyDiGraph()
        path_to_idx: dict[str, int] = {}
        idx_to_path: dict[int, str] = {}
        for path in nodes:
            idx = graph.add_node(path)
            path_to_idx[path] = idx
            idx_to_path[idx] = path
        for source, targets in edges_out.items():
            src_idx = path_to_idx.get(source)
            if src_idx is None:
                continue
            for target in targets:
                tgt_idx = path_to_idx.get(target)
                if tgt_idx is not None:
                    graph.add_edge(src_idx, tgt_idx, None)
        return graph, path_to_idx, idx_to_path

    async def graph(self, *, user_id: str | None = None, session: AsyncSession) -> rustworkx.PyDiGraph:
        """Access the underlying rustworkx directed graph."""
        await self.ensure_fresh(session)
        nodes, edges_out = self._snapshot(user_id)
        g, _, _ = self._build_graph_from(nodes, edges_out)
        return g

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def ensure_fresh(self, session: AsyncSession) -> None:
        """Load from DB if never loaded or TTL has expired."""
        if self._loaded_at is not None and (time.monotonic() - self._loaded_at) < self._ttl:
            return
        await self._load(session)

    async def _load(self, session: AsyncSession) -> None:
        """Load graph state from VFSEntry edge rows.

        Build-then-swap: new state is assembled in local variables and
        assigned atomically so concurrent readers never see an empty graph.
        """
        new_nodes: set[str] = set()
        new_out: dict[str, set[str]] = {}
        new_in: dict[str, set[str]] = {}
        new_edge_types: dict[tuple[str, str], str] = {}

        # Graph load only needs the four edge columns — projecting the
        # full row would pull every file's content + embedding blob just to
        # rebuild the edge list.
        stmt = select(
            self._model.path,
            self._model.source_path,
            self._model.target_path,
            self._model.edge_type,
        ).where(
            self._model.kind == "edge",
            self._model.deleted_at.is_(None),  # ty: ignore[unresolved-attribute]
        )
        result = await session.execute(stmt)
        for row in result.all():
            src = row.source_path
            tgt = row.target_path
            parts = decompose_edge(row.path)
            edge_type = row.edge_type or (parts.edge_type if parts else "")
            if src and tgt:
                new_nodes.add(src)
                new_nodes.add(tgt)
                new_out.setdefault(src, set()).add(tgt)
                new_in.setdefault(tgt, set()).add(src)
                new_edge_types[(src, tgt)] = edge_type

        # Atomic swap
        self._nodes = new_nodes
        self._out = new_out
        self._in = new_in
        self._edge_types = new_edge_types
        self._loaded_at = time.monotonic()

    # ------------------------------------------------------------------
    # Result construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _relationship_entries(
        paths_dict: dict[str, list[str]],
    ) -> list[Entry]:
        """Build entries from {path: [related_paths]} mapping."""
        return [Entry(path=p) for p in sorted(paths_dict)]

    @staticmethod
    def _subgraph_entries(
        node_set: set[str],
        edges_out: dict[str, frozenset[str]],
        edge_types: dict[tuple[str, str], str],
    ) -> list[Entry]:
        """Build node + edge entries from a subgraph."""
        # Nodes
        entries: list[Entry] = [Entry(path=p) for p in sorted(node_set)]

        # Edges as projected edge entries.
        entries.extend(
            Entry(path=edge_out_path(s, t, edge_types[(s, t)]))
            for s in node_set
            for t in edges_out.get(s, frozenset())
            if t in node_set
        )

        return entries

    @staticmethod
    def _score_entries(
        scores: dict[str, float],
        *,
        in_degrees: dict[str, int] | None = None,
        out_degrees: dict[str, int] | None = None,
    ) -> list[Entry]:
        """Build entries from {path: score} mapping, sorted by score descending.

        When *in_degrees* / *out_degrees* are provided (pagerank-run degree
        counts), those values are written into each ``Entry`` directly and
        override any persisted degree columns on the object row.
        """
        sorted_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        in_degrees = in_degrees or {}
        out_degrees = out_degrees or {}
        return [
            Entry(
                path=path,
                score=score,
                in_degree=in_degrees.get(path),
                out_degree=out_degrees.get(path),
            )
            for path, score in sorted_items
        ]

    @staticmethod
    def _extract_paths(result: VFSResult) -> list[str]:
        """Extract path strings from a VFSResult."""
        return [e.path for e in result.entries]

    # ------------------------------------------------------------------
    # Light reads — async inline (no thread overhead)
    # ------------------------------------------------------------------

    def _visible_nodes(self, user_id: str | None = None) -> set[str]:
        """Return the set of nodes visible to *user_id*.

        On a user-scoped graph with a *user_id*, only nodes whose path
        starts with ``/{user_id}/`` are visible.  Otherwise all nodes.
        """
        if self._user_scoped and user_id:
            prefix = f"/{user_id}/"
            return {n for n in self._nodes if n.startswith(prefix)}
        return self._nodes

    async def predecessors(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """One-hop backward: nodes with edges pointing to any candidate."""
        try:
            await self.ensure_fresh(session)
            visible = self._visible_nodes(user_id)
            query_paths = set(self._extract_paths(candidates)) & visible
            predecessor_targets: dict[str, list[str]] = {}

            for t in query_paths:
                for s in self._in.get(t, set()):
                    if s not in query_paths and s in visible:
                        predecessor_targets.setdefault(s, []).append(t)

            return VFSResult(
                function="predecessors",
                entries=self._relationship_entries(predecessor_targets),
            )

        except Exception as e:
            return VFSResult(function="predecessors", success=False, errors=[f"predecessors failed: {e}"])

    async def successors(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """One-hop forward: nodes that any candidate points to."""
        try:
            await self.ensure_fresh(session)
            visible = self._visible_nodes(user_id)
            query_paths = set(self._extract_paths(candidates)) & visible
            successor_sources: dict[str, list[str]] = {}

            for s in query_paths:
                for t in self._out.get(s, set()):
                    if t not in query_paths and t in visible:
                        successor_sources.setdefault(t, []).append(s)

            return VFSResult(
                function="successors",
                entries=self._relationship_entries(successor_sources),
            )

        except Exception as e:
            return VFSResult(function="successors", success=False, errors=[f"successors failed: {e}"])

    # ------------------------------------------------------------------
    # Heavy traversal — async via to_thread
    # ------------------------------------------------------------------

    async def ancestors(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Transitive backward: union of all ancestor sets, excluding candidates."""
        try:
            await self.ensure_fresh(session)
            visible = self._visible_nodes(user_id)
            valid_paths = set(self._extract_paths(candidates)) & visible
            if not valid_paths:
                return VFSResult(function="ancestors")
            nodes, edges_out = self._snapshot(user_id)
            return await asyncio.to_thread(
                self._ancestors_impl,
                nodes,
                edges_out,
                valid_paths,
            )

        except Exception as e:
            return VFSResult(function="ancestors", success=False, errors=[f"ancestors failed: {e}"])

    @staticmethod
    def _ancestors_impl(
        nodes: frozenset[str],
        edges_out: dict[str, frozenset[str]],
        valid_paths: set[str],
    ) -> VFSResult:
        graph, path_to_idx, idx_to_path = RustworkxGraph._build_graph_from(nodes, edges_out)
        result_map: dict[str, list[str]] = {}
        for candidate in valid_paths:
            for i in rustworkx.ancestors(graph, path_to_idx[candidate]):
                p = idx_to_path.get(i)
                if p is not None and p not in valid_paths:
                    result_map.setdefault(p, []).append(candidate)
        return VFSResult(
            function="ancestors",
            entries=RustworkxGraph._relationship_entries(result_map),
        )

    async def descendants(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Transitive forward: union of all descendant sets, excluding candidates."""
        try:
            await self.ensure_fresh(session)
            visible = self._visible_nodes(user_id)
            valid_paths = set(self._extract_paths(candidates)) & visible
            if not valid_paths:
                return VFSResult(function="descendants")
            nodes, edges_out = self._snapshot(user_id)
            return await asyncio.to_thread(
                self._descendants_impl,
                nodes,
                edges_out,
                valid_paths,
            )

        except Exception as e:
            return VFSResult(function="descendants", success=False, errors=[f"descendants failed: {e}"])

    @staticmethod
    def _descendants_impl(
        nodes: frozenset[str],
        edges_out: dict[str, frozenset[str]],
        valid_paths: set[str],
    ) -> VFSResult:
        graph, path_to_idx, idx_to_path = RustworkxGraph._build_graph_from(nodes, edges_out)
        result_map: dict[str, list[str]] = {}
        for candidate in valid_paths:
            for i in rustworkx.descendants(graph, path_to_idx[candidate]):
                p = idx_to_path.get(i)
                if p is not None and p not in valid_paths:
                    result_map.setdefault(p, []).append(candidate)
        return VFSResult(
            function="descendants",
            entries=RustworkxGraph._relationship_entries(result_map),
        )

    async def neighborhood(
        self,
        candidates: VFSResult,
        *,
        depth: int = 2,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Bounded undirected BFS around candidate nodes."""
        try:
            await self.ensure_fresh(session)
            visible = self._visible_nodes(user_id)
            seed_paths = set(self._extract_paths(candidates)) & visible
            if not seed_paths:
                return VFSResult(function="neighborhood")

            _, snap_out = self._snapshot(user_id)
            if self._user_scoped and user_id:
                snap_in = {t: frozenset(s for s in ss if s in visible) for t, ss in self._in.items() if t in visible}
            else:
                snap_in = {t: frozenset(ss) for t, ss in self._in.items()}
            snap_edge_types = self._edge_types.copy()

            visited: set[str] = set(seed_paths)
            frontier: set[str] = set(seed_paths)
            for _ in range(depth):
                next_frontier: set[str] = set()
                for node in frontier:
                    for n in snap_out.get(node, ()):
                        if n not in visited:
                            visited.add(n)
                            next_frontier.add(n)
                    for n in snap_in.get(node, ()):
                        if n not in visited:
                            visited.add(n)
                            next_frontier.add(n)
                frontier = next_frontier
                if not frontier:
                    break

            visited_edges = {s: ts for s, ts in snap_out.items() if s in visited}
            return VFSResult(
                function="neighborhood",
                entries=self._subgraph_entries(
                    visited,
                    visited_edges,
                    snap_edge_types,
                ),
            )

        except Exception as e:
            return VFSResult(function="neighborhood", success=False, errors=[f"neighborhood failed: {e}"])

    # ------------------------------------------------------------------
    # Subgraph algorithms
    # ------------------------------------------------------------------

    async def meeting_subgraph(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Find minimal subgraph connecting all candidate nodes.

        Uses multi-source BFS with union-find to detect when seed
        wavefronts meet, then leaf-strips non-seed nodes. O(V+E).
        """
        try:
            await self.ensure_fresh(session)
            visible = self._visible_nodes(user_id)
            valid_seeds = [p for p in self._extract_paths(candidates) if p in visible]
            if len(valid_seeds) <= 1:
                return VFSResult(
                    function="meeting_subgraph",
                    entries=[Entry(path=p) for p in valid_seeds],
                )
            _, edges_out = self._snapshot(user_id)
            if self._user_scoped and user_id:
                edges_in = {t: frozenset(s for s in ss if s in visible) for t, ss in self._in.items() if t in visible}
            else:
                edges_in = {t: frozenset(ss) for t, ss in self._in.items()}
            return await asyncio.to_thread(
                self._meeting_subgraph_impl,
                edges_out,
                edges_in,
                valid_seeds,
                self._edge_types.copy(),
            )

        except Exception as e:
            return VFSResult(function="meeting_subgraph", success=False, errors=[f"meeting_subgraph failed: {e}"])

    @staticmethod
    def _meeting_subgraph_impl(
        edges_out: dict[str, frozenset[str]],
        edges_in: dict[str, frozenset[str]],
        seeds: list[str],
        edge_types: dict[tuple[str, str], str],
    ) -> VFSResult:
        seed_set = set(seeds)

        # Multi-source BFS with union-find
        origin: dict[str, str] = {}
        pred: dict[str, str] = {}
        uf = UnionFind(seeds)

        queue: deque[str] = deque()
        for s in seeds:
            origin[s] = s
            pred[s] = s
            queue.append(s)

        bridges: list[tuple[str, str]] = []

        while queue and uf.components > 1:
            node = queue.popleft()
            node_origin = origin[node]
            for neighbor in edges_out.get(node, ()):
                if neighbor not in origin:
                    origin[neighbor] = node_origin
                    pred[neighbor] = node
                    queue.append(neighbor)
                elif uf.find(origin[neighbor]) != uf.find(node_origin):
                    bridges.append((node, neighbor))
                    uf.union(origin[neighbor], node_origin)
            for neighbor in edges_in.get(node, ()):
                if neighbor not in origin:
                    origin[neighbor] = node_origin
                    pred[neighbor] = node
                    queue.append(neighbor)
                elif uf.find(origin[neighbor]) != uf.find(node_origin):
                    bridges.append((node, neighbor))
                    uf.union(origin[neighbor], node_origin)

        # Trace predecessor chains from bridge endpoints back to seeds
        kept: set[str] = set(seeds)
        for a, b in bridges:
            for start in (a, b):
                node = start
                while node != pred[node]:
                    kept.add(node)
                    node = pred[node]
                kept.add(node)

        # Leaf stripping — remove non-seed leaves iteratively
        kept = RustworkxGraph._strip_leaves(kept, edges_out, edges_in, seed_set)

        return VFSResult(
            function="meeting_subgraph",
            entries=RustworkxGraph._subgraph_entries(
                kept,
                edges_out,
                edge_types,
            ),
        )

    @staticmethod
    def _strip_leaves(
        kept: set[str],
        edges_out: dict[str, frozenset[str]],
        edges_in: dict[str, frozenset[str]],
        protected: set[str],
    ) -> set[str]:
        """Remove non-protected leaf nodes iteratively. O(n+e)."""
        succs: dict[str, set[str]] = {}
        preds: dict[str, set[str]] = {}
        for s in kept:
            succs[s] = {t for t in edges_out.get(s, ()) if t in kept}
        for t in kept:
            preds[t] = {s for s in edges_in.get(t, ()) if s in kept}

        queue = [n for n in kept if n not in protected and (not succs.get(n) or not preds.get(n))]
        removed: set[str] = set()
        while queue:
            node = queue.pop()
            if node in removed or node in protected:
                continue
            removed.add(node)
            for succ in succs.get(node, ()):
                preds[succ].discard(node)
                if succ not in protected and succ not in removed and (not preds[succ] or not succs[succ]):
                    queue.append(succ)
            for pred_node in preds.get(node, ()):
                succs[pred_node].discard(node)
                if (
                    pred_node not in protected
                    and pred_node not in removed
                    and (not succs[pred_node] or not preds[pred_node])
                ):
                    queue.append(pred_node)
        return kept - removed

    async def min_meeting_subgraph(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Pruned meeting subgraph — drop non-candidate nodes while staying connected.

        Uses ``rustworkx.articulation_points`` to identify nodes whose removal
        would disconnect the graph. Non-seed, non-articulation-point nodes are
        removed one at a time (recomputing articulation points after each
        removal) until only seeds and structurally critical intermediaries
        remain.
        """
        try:
            meeting = await self.meeting_subgraph(candidates, user_id=user_id, session=session)
            if not meeting.success:
                # Re-wrap under this function's name.
                return VFSResult(
                    function="min_meeting_subgraph",
                    success=False,
                    errors=list(meeting.errors),
                )

            candidate_paths = set(self._extract_paths(candidates))
            # Extract node set from meeting result — projected edge paths
            # decompose, node paths do not.
            node_set = {e.path for e in meeting.entries if not decompose_edge(e.path)}

            # If meeting subgraph is already minimal, return it under the
            # current function's name.
            if len(node_set) <= len(candidate_paths):
                return VFSResult(
                    function="min_meeting_subgraph",
                    entries=list(meeting.entries),
                )

            # Build edge topology from stored edge types (authoritative)
            edges_out: dict[str, set[str]] = {}
            for s, t in self._edge_types:
                if s in node_set and t in node_set:
                    edges_out.setdefault(s, set()).add(t)

            return await asyncio.to_thread(
                self._min_meeting_impl,
                node_set,
                edges_out,
                candidate_paths,
                self._edge_types.copy(),
            )

        except Exception as e:
            return VFSResult(
                function="min_meeting_subgraph",
                success=False,
                errors=[f"min_meeting_subgraph failed: {e}"],
            )

    @staticmethod
    def _min_meeting_impl(
        node_set: set[str],
        edges_out: dict[str, set[str]],
        candidate_paths: set[str],
        edge_types: dict[tuple[str, str], str],
    ) -> VFSResult:
        # Build undirected PyGraph for articulation point detection
        graph = rustworkx.PyGraph()
        path_to_idx: dict[str, int] = {}
        idx_to_path: dict[int, str] = {}
        for p in node_set:
            idx = graph.add_node(p)
            path_to_idx[p] = idx
            idx_to_path[idx] = p
        seen: set[tuple[str, str]] = set()
        for s in node_set:
            for t in edges_out.get(s, ()):
                if t in node_set:
                    key = (min(s, t), max(s, t))
                    if key not in seen:
                        seen.add(key)
                        graph.add_edge(path_to_idx[s], path_to_idx[t], None)

        # Iteratively remove non-seed, non-articulation-point nodes
        current_nodes = set(node_set)
        changed = True
        while changed:
            changed = False
            art_paths = {idx_to_path[i] for i in rustworkx.articulation_points(graph) if i in idx_to_path}
            removable = current_nodes - candidate_paths - art_paths
            if removable:
                node = next(iter(removable))
                idx = path_to_idx[node]
                graph.remove_node(idx)
                del path_to_idx[node]
                del idx_to_path[idx]
                current_nodes.discard(node)
                changed = True

        edges_out_frozen = {s: frozenset(ts) for s, ts in edges_out.items()}
        return VFSResult(
            function="min_meeting_subgraph",
            entries=RustworkxGraph._subgraph_entries(
                current_nodes,
                edges_out_frozen,
                edge_types,
            ),
        )

    # ------------------------------------------------------------------
    # Centrality algorithms
    # ------------------------------------------------------------------

    async def _run_centrality(
        self,
        function: str,
        rx_fn: Any,
        candidates: VFSResult,
        session: AsyncSession,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
        """Generic centrality: ensure_fresh -> snapshot -> to_thread."""
        try:
            await self.ensure_fresh(session)
            nodes, edges_out = self._snapshot(user_id)
            return await asyncio.to_thread(
                self._centrality_impl,
                nodes,
                edges_out,
                candidates,
                function,
                rx_fn,
                kwargs,
            )

        except Exception as e:
            return VFSResult(function=function, success=False, errors=[f"{function} failed: {e}"])

    @staticmethod
    def _centrality_impl(
        nodes: frozenset[str],
        edges_out: dict[str, frozenset[str]],
        candidates: VFSResult,
        function: str,
        rx_fn: Any,
        kwargs: dict[str, object],
    ) -> VFSResult:
        graph, _, idx_to_path = RustworkxGraph._build_graph_from(nodes, edges_out)
        if graph.num_nodes() == 0:
            return VFSResult(function=function)
        scores = rx_fn(graph, **kwargs)
        raw = {idx_to_path[idx]: score for idx, score in scores.items() if idx in idx_to_path}
        # Filter to candidate paths if any were provided
        candidate_paths = set(RustworkxGraph._extract_paths(candidates))
        if candidate_paths:
            raw = {p: s for p, s in raw.items() if p in candidate_paths}

        # Compute in/out degrees from the rustworkx graph — these override
        # any persisted degree columns on the underlying object row.
        in_degrees: dict[str, int] = {}
        out_degrees: dict[str, int] = {}
        for idx, path in idx_to_path.items():
            if path in raw:
                in_degrees[path] = graph.in_degree(idx)
                out_degrees[path] = graph.out_degree(idx)

        return VFSResult(
            function=function,
            entries=RustworkxGraph._score_entries(
                raw,
                in_degrees=in_degrees,
                out_degrees=out_degrees,
            ),
        )

    async def pagerank(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """PageRank centrality scores."""
        return await self._run_centrality(
            "pagerank",
            rustworkx.pagerank,
            candidates,
            session,
            user_id=user_id,
        )

    async def betweenness_centrality(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Betweenness centrality scores."""
        return await self._run_centrality(
            "betweenness_centrality",
            rustworkx.digraph_betweenness_centrality,
            candidates,
            session,
            user_id=user_id,
            normalized=True,
        )

    async def closeness_centrality(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Closeness centrality scores."""
        return await self._run_centrality(
            "closeness_centrality",
            rustworkx.closeness_centrality,
            candidates,
            session,
            user_id=user_id,
        )

    async def degree_centrality(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Degree centrality (in + out) scores."""
        return await self._run_centrality(
            "degree_centrality",
            rustworkx.digraph_degree_centrality,
            candidates,
            session,
            user_id=user_id,
        )

    async def in_degree_centrality(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """In-degree centrality scores."""
        return await self._run_centrality(
            "in_degree_centrality",
            rustworkx.in_degree_centrality,
            candidates,
            session,
            user_id=user_id,
        )

    async def out_degree_centrality(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Out-degree centrality scores."""
        return await self._run_centrality(
            "out_degree_centrality",
            rustworkx.out_degree_centrality,
            candidates,
            session,
            user_id=user_id,
        )

    async def hits(
        self,
        candidates: VFSResult,
        *,
        score: str = "authority",
        max_iter: int = 1000,
        tol: float = 1e-8,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """HITS hub and authority scores.

        *score* selects which metric becomes the ``Entry.score`` and controls
        sort order.  ``"authority"`` (default) ranks by how many hubs point
        to a node.  ``"hub"`` ranks by how many authorities a node points
        to.
        """
        if score not in ("authority", "hub"):
            return VFSResult(
                function="hits",
                success=False,
                errors=[f"hits score must be 'authority' or 'hub', got {score!r}"],
            )
        try:
            await self.ensure_fresh(session)
            nodes, edges_out = self._snapshot(user_id)
            return await asyncio.to_thread(
                self._hits_impl,
                nodes,
                edges_out,
                candidates,
                score,
                max_iter,
                tol,
            )

        except Exception as e:
            return VFSResult(function="hits", success=False, errors=[f"hits failed: {e}"])

    @staticmethod
    def _hits_impl(
        nodes: frozenset[str],
        edges_out: dict[str, frozenset[str]],
        candidates: VFSResult,
        score: str,
        max_iter: int,
        tol: float,
    ) -> VFSResult:
        graph, _, idx_to_path = RustworkxGraph._build_graph_from(nodes, edges_out)
        candidate_paths = set(RustworkxGraph._extract_paths(candidates))

        # Precompute per-node in/out degrees so the Entry rows carry the
        # values observed by the rustworkx run, overriding persisted degrees.
        in_degrees_all: dict[str, int] = {idx_to_path[i]: graph.in_degree(i) for i in idx_to_path}
        out_degrees_all: dict[str, int] = {idx_to_path[i]: graph.out_degree(i) for i in idx_to_path}

        if graph.num_nodes() == 0 or graph.num_edges() == 0:
            # Filter to graph-only paths, consistent with the normal path
            # where non-graph candidates are silently dropped via score dicts.
            graph_paths = set(idx_to_path.values())
            all_paths = sorted(candidate_paths & graph_paths) if candidate_paths else sorted(graph_paths)
            return VFSResult(
                function="hits",
                entries=[
                    Entry(
                        path=p,
                        score=0.0,
                        in_degree=in_degrees_all.get(p),
                        out_degree=out_degrees_all.get(p),
                    )
                    for p in all_paths
                ],
            )

        hubs_raw, auths_raw = rustworkx.hits(graph, max_iter=max_iter, tol=tol)
        hubs = {idx_to_path[idx]: s for idx, s in hubs_raw.items() if idx in idx_to_path}
        auths = {idx_to_path[idx]: s for idx, s in auths_raw.items() if idx in idx_to_path}
        if candidate_paths:
            hubs = {p: s for p, s in hubs.items() if p in candidate_paths}
            auths = {p: s for p, s in auths.items() if p in candidate_paths}

        primary = auths if score == "authority" else hubs
        all_paths = sorted(primary, key=primary.__getitem__, reverse=True)
        return VFSResult(
            function="hits",
            entries=[
                Entry(
                    path=p,
                    score=primary[p],
                    in_degree=in_degrees_all.get(p),
                    out_degree=out_degrees_all.get(p),
                )
                for p in all_paths
            ],
        )
