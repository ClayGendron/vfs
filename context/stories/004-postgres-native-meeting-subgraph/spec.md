# 004 — Postgres-native graph traversal

- **Status:** draft
- **Date:** 2026-04-20
- **Updated:** 2026-04-21
- **Owner:** Clay Gendron
- **Kind:** feature + backend + graph

## Intent

Make the Postgres backend execute the full graph traversal surface natively inside PostgreSQL for `PostgresFileSystem`, while preserving the public VFS contract and the current graph semantics that callers rely on today.

Covered operations in this story:

- `predecessors`
- `successors`
- `ancestors`
- `descendants`
- `neighborhood`
- `meeting_subgraph`

Today:

- [DatabaseFileSystem](/Users/claygendron/Git/Repos/grover/src/vfs/backends/database.py) routes graph traversal through the in-memory [RustworkxGraph](/Users/claygendron/Git/Repos/grover/src/vfs/graph/rustworkx.py).
- [PostgresFileSystem](/Users/claygendron/Git/Repos/grover/src/vfs/backends/postgres.py) already overrides text and vector search paths, but graph traversal still leaves Postgres and runs in Python.
- The authoritative graph topology already lives in Postgres as live connection rows on `vfs_objects`, with `source_path`, `target_path`, and `connection_type`.

After this story:

- `PostgresFileSystem.predecessors(...)`, `successors(...)`, `ancestors(...)`, `descendants(...)`, `neighborhood(...)`, and `meeting_subgraph(...)` execute natively in Postgres.
- Python only marshals seed paths, depth, and scope into SQL and hydrates `VFSResult` rows back out.
- The Postgres-native path does not depend on the in-memory Rustworkx cache for those operations.

## Why

- **Backend coherence:** PostgreSQL-backed mounts should execute graph retrieval in the same system that already owns the connection rows.
- **Freshness:** native traversal runs against one MVCC snapshot of the live database instead of a TTL-cached in-memory graph.
- **Scalability:** the backend should not need to hydrate the full graph into Python just to answer one traversal query.
- **Architectural consistency:** `PostgresFileSystem` already exists to push backend-specific search work into Postgres; graph traversal belongs in the same direction.
- **Expansion path:** `meeting_subgraph` should not be the only native graph primitive if the long-term direction is a Postgres-native graph-aware backend.

## Native Definition

For this story, **native in Postgres** means:

- traversal and set expansion happen inside PostgreSQL
- recursive CTEs are allowed
- PL/pgSQL is allowed
- session-local temp tables are allowed
- Python may pass parameters and shape returned `Entry` rows, but it must not reconstruct or traverse the graph in memory

This story does **not** require every method to be expressed as a single SQL statement. Different methods may use different native strategies where appropriate.

## Current Contract To Preserve

The reference behavior is the current database-backed path through [DatabaseFileSystem](/Users/claygendron/Git/Repos/grover/src/vfs/backends/database.py), as exercised by [tests/test_database_graph.py](/Users/claygendron/Git/Repos/grover/tests/test_database_graph.py), [tests/test_graph.py](/Users/claygendron/Git/Repos/grover/tests/test_graph.py), and the Postgres-facing expectations in [tests/test_postgres_backend.py](/Users/claygendron/Git/Repos/grover/tests/test_postgres_backend.py).

The native Postgres implementation must preserve these externally visible semantics:

1. `VFSResult.function` continues to match the invoked traversal method.
2. `predecessors`, `successors`, `ancestors`, `descendants`, and `neighborhood` return node entries only.
3. `meeting_subgraph` returns both:
   - node entries (`/src/a.py`)
   - connection-path entries (`/src/a.py/.connections/imports/src/b.py`) for edges whose endpoints survive in the returned subgraph
4. Zero valid seeds returns an empty successful result.
5. One valid seed preserves current per-method behavior:
   - `predecessors`, `successors`, `ancestors`, `descendants` may return zero or more related nodes
   - `neighborhood(depth >= 1)` includes the seed when the seed participates in the graph
   - `meeting_subgraph` returns that seed only
6. Unknown or non-graph seeds are ignored.
7. Multi-seed one-hop or reachability methods preserve the current union semantics across seeds.
8. `neighborhood` preserves current bounded undirected expansion semantics.
9. `meeting_subgraph` preserves current semantics:
   - traversal is effectively undirected for discovery and bridge detection
   - final pruning is directed leaf stripping against the kept subgraph
10. User scoping continues to behave exactly as it does today through `DatabaseFileSystem` / `PostgresFileSystem` path scoping and result unscoping.

## Important Semantic Boundaries

This story preserves the **database-backed** graph model, not every possible behavior of an isolated in-memory `RustworkxGraph` instance.

Specifically:

- the native implementation derives graph topology from live `connection` rows in `vfs_objects`
- graph nodes are the visible endpoints of those live connections
- this story does not add a separate persisted node table or broaden graph membership to every file row
- edge liveness is determined by the live connection row itself; the native implementation does not revalidate endpoint file rows before treating an edge as part of the graph

That keeps the Postgres-native path aligned with how `RustworkxGraph._load()` currently builds graph state for database-backed use.

## Method-Specific Semantics

### `predecessors`

- Directed one-hop reverse adjacency.
- Result is the union of distinct incoming neighbors for all valid seeds.
- Seed nodes themselves are not included unless they are also predecessors of another supplied seed under current behavior.

### `successors`

- Directed one-hop forward adjacency.
- Result is the union of distinct outgoing neighbors for all valid seeds.
- Seed nodes themselves are not included unless they are also successors of another supplied seed under current behavior.

### `ancestors`

- Directed transitive reverse reachability.
- Result includes all nodes that can reach any valid seed by following connection direction.
- Seed nodes themselves are excluded unless current behavior includes them indirectly through another seed relationship.

### `descendants`

- Directed transitive forward reachability.
- Result includes all nodes reachable from any valid seed by following connection direction.
- Seed nodes themselves are excluded unless current behavior includes them indirectly through another seed relationship.

### `neighborhood`

- Bounded undirected expansion around each valid seed.
- Result preserves current depth semantics from the VFS API.
- The result includes the seed only when the seed exists as a graph node under the database-backed graph model.

### `meeting_subgraph`

- Multi-source undirected discovery with deterministic seed ownership and bridge detection.
- Backtracks along the native predecessor tree used during traversal.
- Emits the surviving node set plus canonical connection-path entries for surviving directed edges.
- Applies iterative directed leaf stripping to non-seed nodes after bridge backtracking.

## Expected Touch Points

- `src/vfs/backends/postgres.py`
- `src/vfs/backends/__init__.py` only if export surface changes
- PostgreSQL migration/provisioning path for installing native graph function(s), view(s), or other artifacts
- `tests/test_postgres_backend.py`
- `tests/test_database_graph.py`
- `tests/conftest.py` Postgres fixtures/provisioning helpers
- Postgres-facing backend docs where native capabilities are described
- [context/stories/004-postgres-native-meeting-subgraph/query.sql](/Users/claygendron/Git/Repos/grover/context/stories/004-postgres-native-meeting-subgraph/query.sql) as the initial prototype area for native graph SQL

## Scope

### In

1. Add Postgres-native implementation paths on `PostgresFileSystem` for:
   - `_predecessors_impl`
   - `_successors_impl`
   - `_ancestors_impl`
   - `_descendants_impl`
   - `_neighborhood_impl`
   - `_meeting_subgraph_impl`

2. Execute graph traversal inside Postgres using SQL and, where useful, PL/pgSQL over the `vfs_objects` table.

3. Make all methods operate from the authoritative connection-row schema:
   - `kind = 'connection'`
   - `deleted_at IS NULL`
   - `source_path`
   - `target_path`
   - `connection_type`

4. Preserve current algorithmic shape closely enough that external behavior remains compatible:
   - direct adjacency lookup for `predecessors` and `successors`
   - recursive reachability for `ancestors` and `descendants`
   - bounded undirected expansion for `neighborhood`
   - multi-source BFS-style expansion, first-claim ownership, bridge detection, predecessor-chain backtracking, and iterative directed leaf stripping for `meeting_subgraph`

5. Make the native implementation deterministic where the current Python implementation is not.

   Acceptable rule:

   - seed priority is the caller's input order
   - within equal frontier opportunities, ties are broken by stable path ordering

   Exact intermediary choice does not need to match Python `set` iteration accidents, but the result must satisfy the same contract and acceptance tests.

6. Add explicit backend setup methods for the native graph artifacts.

   Required shape:

   - `verify_native_graph_schema()` on `PostgresFileSystem`
   - a companion explicit install/provision helper for non-request use, such as `install_native_graph_schema()` or equivalent

   Required behavior:

   - request-path execution must assume the artifacts already exist
   - tests and local/dev setup may provision the artifact(s) through the explicit install helper
   - normal request handling must never issue `CREATE OR REPLACE FUNCTION ...`

7. Make the implementation concurrency-safe for normal web/API use.

   Required properties:

   - no shared mutable scratch tables across sessions
   - no dependence on global request state
   - safe to run many requests concurrently on different DB connections
   - safe under SQLAlchemy async session pooling

8. Return results through the existing `VFSResult` / `Entry` contract with no public API change.

9. Add Postgres-native integration coverage for each operation in this story.

### Out

1. Native `min_meeting_subgraph`.
2. Native `pagerank`, `hits`, or other centrality algorithms.
3. Replacing the shared `DatabaseFileSystem` graph path for SQLite or MSSQL.
4. Changing the public `VirtualFileSystem` method signatures.
5. Adding a new persisted graph topology table.
6. Requiring a single-statement pure-SQL implementation for every method.
7. Reworking the entire graph model to include isolated non-connection file rows as graph nodes.

## Design Constraints

1. The backend must not load the full graph into Python for these operations.

2. The backend must not call the corresponding in-memory graph methods when executing the Postgres-native path:
   - `self._graph.predecessors(...)`
   - `self._graph.successors(...)`
   - `self._graph.ancestors(...)`
   - `self._graph.descendants(...)`
   - `self._graph.neighborhood(...)`
   - `self._graph.meeting_subgraph(...)`

3. The native implementation must filter by user scope in Postgres when `user_scoped=True`.

4. The implementation should work from the existing indexes on `source_path` and `target_path`, but the story may add additional Postgres indexes if profiling shows they materially improve native traversal.

5. The implementation must only consider live edges:
   - soft-deleted connection rows are excluded
   - edges whose endpoints fall outside the requested user scope are excluded
   - endpoint file rows are not separately consulted for edge liveness; a live connection row remains authoritative even if the endpoint file rows are inconsistent or absent

6. The returned connection-path entries for `meeting_subgraph` must continue to use the canonical VFS encoding:

```text
<source>/.connections/<connection_type>/<target-without-leading-slash>
```

7. `meeting_subgraph` predecessor backtracking must follow the first-claim predecessor tree established by the native BFS state, not arbitrary graph edges.

   Required termination behavior:

   - backtracking stops at a seed, or
   - backtracking stops at an already-added ancestor in the predecessor chain

   The implementation must not be able to loop indefinitely on graph cycles during backtracking.

8. `ancestors`, `descendants`, and `neighborhood` must deduplicate nodes by path even if multiple traversal routes discover the same node.

9. Depth handling for `neighborhood` must preserve the VFS API contract exactly, including the current meaning of `depth=0` and higher bounded depths.

## Acceptance Criteria

1. On `PostgresFileSystem`, `predecessors`, `successors`, `ancestors`, `descendants`, `neighborhood`, and `meeting_subgraph` execute natively in Postgres and return normal `VFSResult` objects.

2. The Postgres-native implementation preserves these cases for one-hop traversal:
   - `predecessors` of a node with incoming edges returns the distinct incoming sources
   - `predecessors` of a root-like or unknown node returns an empty successful result
   - `successors` of a node with outgoing edges returns the distinct outgoing targets
   - `successors` of a leaf-like or unknown node returns an empty successful result
   - multi-seed calls return the union of distinct neighbors across seeds

3. The Postgres-native implementation preserves these cases for reachability:
   - `ancestors` of a leaf-like node returns all transitive upstream nodes
   - `ancestors` of a root-like or unknown node returns an empty successful result
   - `descendants` of a root-like node returns all transitive downstream nodes
   - `descendants` of a leaf-like or unknown node returns an empty successful result
   - cycles do not create duplicate rows or non-terminating traversal

4. The Postgres-native implementation preserves these cases for `neighborhood`:
   - depth-1 returns the seed plus one-hop neighbors when the seed is in the graph
   - higher depth expands undirected reachability only up to the requested bound
   - isolated or unknown nodes produce the same empty behavior as the current database-backed contract
   - multi-seed inputs preserve current union semantics

5. The Postgres-native implementation preserves these cases for `meeting_subgraph`:
   - zero valid seeds -> empty result
   - one valid seed -> that seed only
   - two connected seeds -> both seeds plus required intermediates
   - adjacent seeds -> both seeds plus the connecting edge entry
   - disconnected seeds in separate live graph components -> both seeds survive
   - unknown seed mixed with one valid seed -> only the valid seed survives
   - a non-seed dangling spur that has no kept in-neighbor or no kept out-neighbor after bridge backtracking is stripped from the final result
   - a non-seed intermediary with both a kept predecessor and a kept successor is not stripped solely for being non-seed

6. Returned edge entries for `meeting_subgraph` correspond exactly to the surviving node set and use canonical connection paths.

7. User-scoped mounts do not discover or emit other users' nodes or edges for any method covered by this story.

8. The native implementation is deterministic for the same seed order, depth, and committed database state.

9. Concurrent requests on separate Postgres sessions do not interfere with one another.

10. No request-path DDL is required for normal execution once the backend is provisioned.

11. `PostgresFileSystem` exposes `verify_native_graph_schema()` and an explicit non-request install/provision helper for the native graph artifacts.

12. Postgres-native integration tests cover at least one deterministic tie case for `meeting_subgraph` so the implementation does not silently inherit Python `set` iteration nondeterminism.

## Suggested Implementation Shape

The story does not mandate one implementation form for every method, but this split is the intended direction:

- `predecessors` / `successors`: direct indexed SQL against live connection rows
- `ancestors` / `descendants`: recursive CTEs or equivalent native reachability helpers
- `neighborhood`: recursive CTE with bounded depth over an undirected adjacency projection
- `meeting_subgraph`: PL/pgSQL or equivalent native routine using explicit traversal state

That keeps the cheap methods cheap while leaving room for the more stateful `meeting_subgraph` logic to use temp tables where justified.

## Non-Goals / Follow-On Work

- `min_meeting_subgraph` can become a follow-on story once native `meeting_subgraph` exists as a foundation.
- `pagerank`, `hits`, and other centrality routines can become separate Postgres-native stories later.
- If future profiling shows that temp-table churn is material, a follow-on story may refine the implementation strategy further.
- If the team later wants all graph algorithms native in Postgres, this story should establish the install/provision/test pattern rather than solve every graph primitive at once.

## Open Questions

1. Should the native graph artifacts live in the default schema, a dedicated internal schema, or be schema-qualified alongside the data table?
2. Do we want to add Postgres-specific partial indexes for live connection rows as part of this story, or leave that to profiling after the first native implementation lands?
3. Do we want one install helper that provisions all native graph artifacts together, or a finer-grained internal split with one public provisioning entrypoint?
