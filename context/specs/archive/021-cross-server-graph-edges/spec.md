# 021 — Cross-Server Graph Edges

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · graph traversal · the hard one
- **Depends on:** 015, 016, 017, 020
- **Enables:** higher-quality cross-corpus search; semantic
  knowledge graphs that span SQL backends and vendor backends
  (Slack, Jira, Confluence).

## Intent

Make graph edges work *across mount boundaries* — including
across remote backends — without requiring all participants to
share a database, schema, or even a process. Today the graph
lives inside one `DatabaseFileSystem` and its edges are SQL rows
pointing to other entries in the same backend. Edges that should
span "this auth.py imports that protobuf in another mount" are
inexpressible.

This story introduces:

- A **`(mount, path)` qualified node identity** that the graph
  layer treats as a primitive.
- An **edge store with three placement modes** so edges can live
  on the source side, the target side, or in a third-party edge
  registry.
- **Federated traversal** — traversal queries fan out to whichever
  backend(s) own the relevant edges, results are merged at the
  router, and the agent sees one connected graph.

This is intentionally the most ambitious story in the wave. It
assumes 020 (remote backends) is in place; without that, edges
can only span in-process backends and the design is a subset.

## Why

- **The product point.** The whole pitch of "VFS for enterprise
  knowledge" depends on cross-source connections. A search result
  from Slack cited as "discusses" an entry in the wiki, which is
  cited by a code symbol in a repo, is the agentic super-power.
  Without cross-server edges, each backend is a silo.
- **User asked for it explicitly.** "I think it would be really
  great if we could get cross server edges to work, and do so
  elegantly. This would solve a lot of problems."
- **Plan 9 doesn't directly help here.** Plan 9 doesn't have a
  graph model; the closest analogue is `import` / namespace
  composition. The Plan 9 lesson we *do* keep: identity is
  qid-shaped, not path-shaped. An edge points to a *node
  identity*, which is `(mount-uri, qid_path, qid_version)`, not
  to a string path.

## Scope

### In

1. **Qualified node identity.**
   ```python
   @dataclass(frozen=True)
   class NodeId:
       mount_uri: str       # backend URI, stable across reconnects
       qid_path: str        # backend-internal stable id
       version: int | None  # None = "latest"; specific = pinned
   ```
   The graph layer's primary key. Path strings are display
   conveniences. Mounts can move under a node; the node
   identity does not change.

2. **Edge primitives.**
   ```python
   @dataclass(frozen=True)
   class Edge:
       src: NodeId
       dst: NodeId
       kind: str        # "imports", "cites", "discusses", "owns", ...
       weight: float = 1.0
       attrs: dict[str, Any] = ...

       # Where this edge is materialized:
       # - source-side: stored in the src's mount
       # - target-side: stored in the dst's mount
       # - registry-side: stored in a separate "edge registry" backend
       placement: Literal["source", "target", "registry"]
   ```

3. **Edge placement rules.**
   - **Source-side (default):** an edge lives in the source's
     mount. Cheap to write (one mount), but traversal "incoming
     edges of node X" requires asking every mount.
   - **Target-side:** an edge lives in the target's mount.
     Mirror of the above.
   - **Registry-side:** edges where neither endpoint is a natural
     home (e.g., human-curated cross-references) live in a
     dedicated **edge registry** backend that knows about no
     content but holds many `(NodeId, NodeId, kind, ...)` rows.

   Mixed placement is fine. The edge structure carries
   `placement` so the traversal knows where to look.

4. **`mkedge` becomes mount-aware.**
   `client.mkedge("/a/x", "/b/y", kind="imports")`:
   - Resolve `/a/x` → `(mount_a, "/x")`, `/b/y` → `(mount_b, "/y")`.
   - Look up nodes' qids on each mount (round-trip per mount).
   - Decide placement (default: source-side, i.e., on `mount_a`).
   - Call `mount_a.write_edge(Edge(src, dst, ...))`.
   - If `mount_a` doesn't support `write_edge` (read-only, vendor
     backend without an edge model), fall back to registry-side.

5. **Edge registry backend.**
   A new `EdgeRegistryFS(VirtualFileSystem)` whose only job is
   to store edges. Tiny SQL schema:
   ```
   edges(src_mount, src_qid, src_version,
         dst_mount, dst_qid, dst_version,
         kind, weight, attrs, created_at)
   ```
   Mounted at `/.edges` (or wherever the user prefers) by
   default. Indexed by `src_*`, `dst_*`, and `kind`.

6. **Federated traversal.**
   `client.successors(node, depth=2, kinds=["imports"])`:
   - Translate `node` (a path) to `NodeId` via stat.
   - **Outgoing edges** queried from `node.mount_uri` (source-side
     edges live there) and from `/.edges` (registry edges).
     Both calls are per-frontier-batch.
   - **Incoming edges** queried by fanning out to every mount
     that might host them: today this is `for m in mounts: yield
     from m.incoming_edges(node)`. Cost is "all mounts" for
     incoming traversal; future optimization story can index
     this.
   - Frontier expansion: each new node is a `NodeId`. Resolve to
     paths only at the end (when handing back to the agent).

7. **`VirtualFileSystem` graph public API.**
   ```python
   async def write_edge(self, edge: Edge) -> VFSResult: ...
   async def outgoing(self, node: NodeId, *,
                      kinds: tuple[str, ...] = (),
                      ) -> VFSResult: ...
   async def incoming(self, node: NodeId, *,
                      kinds: tuple[str, ...] = (),
                      ) -> VFSResult: ...
   async def known_nodes(self, *,
                         qid_paths: tuple[str, ...] = (),
                         ) -> VFSResult:
       """Resolve a batch of qid_paths into stat-shaped Candidates;
       used during federated traversal to render NodeId → path."""
   ```
   `successors` / `predecessors` / `neighborhood` /
   `meeting_subgraph` etc. become **router-level** methods that
   compose `outgoing` / `incoming` / `known_nodes` calls across
   mounts.

8. **Capability flags for backends.**
   Backends declare what they support at `initialize`:
   - `graph.outgoing.source` — host source-side edges
   - `graph.incoming.source` — host target-side edges
   - `graph.write` — accept `mkedge`
   - `graph.attrs` — support edge attributes

   Backends that don't declare any graph capability are
   skipped during fanout — the registry handles edges to/from
   their nodes.

9. **Pinning vs. drift.**
   An edge's `version` can be `None` ("latest") or pinned to a
   specific qid version. Pinned edges survive content rewrites;
   latest edges follow the head. Configurable per `mkedge` call.

10. **Cycle and depth limits.**
    Federated traversal has a strict depth limit (default 3,
    configurable) and cycle guard. Without these, a fanout across
    20 mounts at depth 5 is unworkable.

### Out

- A query optimizer that decides which mounts to query first
  based on edge counts. v1 fans out to all relevant mounts
  in parallel; optimization is its own story.
- Path-similarity / fuzzy edges. Edges are exact `(qid, qid)`
  refs.
- Edge inference (auto-detected "discusses" relationships).
  Edges are written explicitly; auto-detection is a separate
  pipeline.
- Distributed transactions across edge writes spanning mounts.
  `mkedge` writes one row in one mount; cross-mount atomicity is
  not promised, mirroring story 014's stance.
- Graph algorithms (pagerank, centrality) at the federated
  level. Story 024 (graph workspace sessions) handles those
  inside a session-bound subgraph.

## Acceptance Criteria

1. **`mkedge` across two `DatabaseFileSystem` mounts works.**
   Test fixture: two SQL backends, write an edge, traverse it.
2. **`mkedge` across a `DatabaseFileSystem` and a `RemoteFS`
   works.** Subprocess server fixture; same test.
3. **Edge registry backend ships.** `EdgeRegistryFS` is a
   first-class subclass; mounted at `/.edges` by default;
   stores edges between any two `NodeId`s.
4. **Source-side edges resolved during outgoing traversal.**
   Traversal from a node only queries that node's mount and
   the registry — not every mount.
5. **Incoming traversal fans out across mounts.** Tests verify
   that an edge sourced from mount A and pointing to mount B is
   visible via `incoming(B's node)` regardless of placement.
6. **`NodeId` is the primary key.** A node's path can change
   (rebind, reflag) without breaking edges, as long as the
   underlying `qid_path` is stable.
7. **Pinned edges survive rewrites.** A `version`-pinned edge
   continues to point to the historic qid version even after
   the file is overwritten; latest-edges follow the head.
8. **Capability negotiation prunes fanout.** Backends without
   graph capability are not included in incoming-edge fanout.
9. **Cycle guard fires on cross-mount cycles.** A cycle through
   two backends terminates traversal with bookkeeping (which
   nodes were skipped).
10. **`mkedge` to a read-only target works via registry.** When
    the target mount has no `graph.write` capability, the edge
    is stored in the registry without error.
11. **No regression on single-backend graph operations.** All
    existing `predecessors` / `successors` / `neighborhood`
    tests continue to pass; for single-mount setups, edges are
    still source-side in that one mount.
12. **Federated traversal latency.** Benchmark: depth-2
    traversal across 5 mounts under 200ms on a fixture with
    1k edges. (Numbers indicative; tune later.)

## Risks

- **Fanout cost for incoming edges.** O(mounts × frontier).
  Mitigation: parallelize, cap depth, future story can introduce
  a federated edge index.
- **Edge-to-deleted-node staleness.** When a node is deleted,
  its edges become stale across multiple mounts. Mitigation:
  edges carry their target's `qid_version`; reads of stale
  edges return `Detail.stale=True` rather than failing
  outright.
- **Registry growth.** Cross-corpus edges can dominate.
  Mitigation: registry is a `DatabaseFileSystem` like any other,
  partitionable, indexable; future story can shard.
- **NodeId stability across mount-uri changes.** If a backend's
  URL changes (host migration), historical edges go stale.
  Mitigation: ship a `mount_uri` rename utility (`write
  /.edges/ctl "rewrite_mount_uri old=... new=..."`).
- **Privacy / cross-tenant leakage.** An edge from a node in
  tenant A to a node in tenant B is itself sensitive. The
  registry must respect per-session permission overlays
  (story 023).

## Open Questions

1. **Should the registry be a special backend with its own
   methods or a normal mount with edge-shaped `VFSEntry`s?**
   Default: a normal mount whose entries are edge rows
   (`kind="edge"`). Lets the existing read/write/glob machinery
   work on edges.

2. **How are edges discoverable through `/.edges/`?** Default:
   `glob("/.edges/<src-mount>/**")` returns all edges sourced
   from a mount. `glob("/.edges/-/<dst-mount>/**")` returns all
   incoming.

3. **Does `mkedge` accept paths or `NodeId`?** Default: paths
   for ergonomics; the implementation translates internally.

4. **What happens to edges when a mount is `unmount`ed?**
   Default: edges in other mounts pointing into the unmounted
   mount become stale-but-readable; `Detail.stale=True`. Edges
   *inside* the unmounted mount are inaccessible until remount.

5. **Edge subscriptions.** Should an agent be able to
   `subscribe(/.edges/...)` to get notified when new edges land?
   Default: yes, through the same notification mechanism as
   `/.mounts/`.

## References

- `src/vfs/graph/protocol.py`, `src/vfs/graph/rustworkx.py` —
  current single-backend graph
- `src/vfs/models.py` — VFSEntry kinds; `kind="edge"` already exists
- Story 011 — MSSQL native multi-hop traversal (single-backend)
- `feedback_graph_traversal_scope.md` (auto-memory) — graph
  traversal stays database-side; rustworkx is out of scope
- `docs/plan9-mount-namespace-recommendations.html` — no direct
  rec; this is net-new beyond the namespace work
