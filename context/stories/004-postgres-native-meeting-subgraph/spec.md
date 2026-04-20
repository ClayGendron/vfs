# 004 — Postgres-native meeting_subgraph

- **Status:** draft
- **Date:** 2026-04-20
- **Owner:** Clay Gendron
- **Kind:** feature + backend + graph

## Intent

Make `meeting_subgraph` execute natively inside PostgreSQL for `PostgresFileSystem`, while preserving the public VFS contract and the current graph semantics that callers rely on today.

Today:

- [DatabaseFileSystem](/Users/claygendron/Git/Repos/grover/src/vfs/backends/database.py) routes `meeting_subgraph` through the in-memory [RustworkxGraph](/Users/claygendron/Git/Repos/grover/src/vfs/graph/rustworkx.py).
- [PostgresFileSystem](/Users/claygendron/Git/Repos/grover/src/vfs/backends/postgres.py) overrides text/vector search paths, but graph work still leaves Postgres and runs in Python.
- The authoritative graph topology already lives in Postgres as `connection` rows on `vfs_objects`, with `source_path`, `target_path`, and `connection_type` columns.

After this story:

- `PostgresFileSystem.meeting_subgraph(...)` executes the graph algorithm inside Postgres.
- Python only marshals seed paths into SQL and hydrates `VFSResult` rows back out.
- The native implementation is safe under concurrent requests and does not depend on the in-memory Rustworkx cache for this operation.

## Why

- **Backend coherence:** PostgreSQL-backed mounts should be able to execute graph retrieval in the same system that already owns the connection rows.
- **Freshness:** a native query runs against one MVCC snapshot of the live database instead of a TTL-cached in-memory graph.
- **Scalability:** the backend should not need to hydrate the full graph into Python just to answer one subgraph query.
- **Architectural consistency:** `PostgresFileSystem` already exists to push backend-specific search work into Postgres; graph retrieval belongs in the same direction.

## Native Definition

For this story, **native in Postgres** means:

- the traversal, frontier claiming, bridge detection, predecessor backtracking, and leaf stripping all happen inside PostgreSQL
- PL/pgSQL is allowed
- session-local temp tables are allowed
- Python may pass parameters and shape the returned `Entry` rows, but it must not reconstruct or traverse the graph in memory

This story does **not** require `meeting_subgraph` to be expressible as a single recursive CTE or a single SQL statement.

## Current Contract To Preserve

The reference behavior is the current [RustworkxGraph.meeting_subgraph](/Users/claygendron/Git/Repos/grover/src/vfs/graph/rustworkx.py:569) path as exercised through the database-backed filesystem tests in [tests/test_database_graph.py](/Users/claygendron/Git/Repos/grover/tests/test_database_graph.py) and the lower-level graph tests in [tests/test_graph.py](/Users/claygendron/Git/Repos/grover/tests/test_graph.py).

The native Postgres implementation must preserve these externally visible semantics:

1. `VFSResult.function == "meeting_subgraph"`.
2. Results contain both:
   - node entries (`/src/a.py`)
   - connection-path entries (`/src/a.py/.connections/imports/src/b.py`) for edges whose endpoints survive in the returned subgraph
3. Zero valid seeds returns an empty successful result.
4. One valid seed returns that seed only.
5. Unknown or non-graph seeds are ignored.
6. Disconnected valid seeds still survive in the result even when no bridges are found.
7. Traversal is effectively **undirected** for discovery and bridge detection.
8. Final pruning is **directed** leaf stripping against the kept subgraph.
9. User scoping continues to behave exactly as it does today through `DatabaseFileSystem` / `PostgresFileSystem` path scoping and result unscoping.

## Important Semantic Boundaries

This story preserves the **database-backed** graph model, not every possible behavior of an isolated in-memory `RustworkxGraph` instance.

Specifically:

- the native implementation derives graph topology from live `connection` rows in `vfs_objects`
- graph nodes are the visible endpoints of those live connections
- this story does not add a separate persisted node table or broaden graph membership to every file row
- edge liveness is determined by the live `connection` row itself; the native implementation does not revalidate endpoint file rows before treating an edge as part of the graph

That keeps the Postgres-native path aligned with how `RustworkxGraph._load()` currently builds graph state for database-backed use.

## Expected Touch Points

- `src/vfs/backends/postgres.py`
- `src/vfs/backends/__init__.py` only if export surface changes
- PostgreSQL migration/provisioning path for installing the native function(s)
- `tests/test_postgres_backend.py`
- `tests/test_database_graph.py`
- `tests/conftest.py` Postgres fixtures/provisioning helpers
- Postgres-facing backend docs where native capabilities are described

## Scope

### In

1. Add a Postgres-native implementation path for `_meeting_subgraph_impl` on `PostgresFileSystem`.

2. Execute the graph algorithm inside Postgres using PL/pgSQL and SQL over the `vfs_objects` table.

3. Make the algorithm operate from the authoritative connection-row schema:
   - `kind = 'connection'`
   - `deleted_at IS NULL`
   - `source_path`
   - `target_path`
   - `connection_type`

4. Preserve the current algorithmic shape closely enough that external behavior remains compatible:
   - multi-source BFS-style expansion from all seeds
   - first-claim ownership of discovered nodes
   - seed-component merge when distinct wavefronts meet
   - predecessor-chain backtracking from bridge endpoints
   - iterative leaf stripping of non-seed nodes with missing in- or out-neighbors inside the kept subgraph

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
   - tests and local/dev setup may provision the function(s) through the explicit install helper
   - normal request handling must never issue `CREATE OR REPLACE FUNCTION ...`

7. Make the implementation concurrency-safe for normal web/API use.

   Required properties:

   - no shared mutable scratch tables across sessions
   - no dependence on global request state
   - safe to run many requests concurrently on different DB connections
   - safe under SQLAlchemy async session pooling

8. Return results through the existing `VFSResult` / `Entry` contract with no public API change.

9. Add Postgres-native integration coverage for the relevant cases.

### Out

1. Native `min_meeting_subgraph`.
2. Native `pagerank`, `hits`, or other centrality algorithms.
3. Replacing the shared `DatabaseFileSystem` graph path for SQLite or MSSQL.
4. Changing the public `VirtualFileSystem` method signatures.
5. Adding a new persisted graph topology table.
6. Requiring a single-statement pure-SQL implementation.
7. Reworking the entire graph model to include isolated non-connection file rows as graph nodes.

## Design Constraints

1. The backend must not load the full graph into Python for this operation.

2. The backend must not call `self._graph.meeting_subgraph(...)` when executing the Postgres-native path.

3. The native implementation must filter by user scope in Postgres when `user_scoped=True`.

4. The implementation should work from the existing indexes on `source_path` and `target_path`, but the story may add additional Postgres indexes if profiling shows they materially improve native graph traversal.

5. The implementation must only consider live edges:
   - soft-deleted connection rows are excluded
   - edges whose endpoints fall outside the requested user scope are excluded
   - endpoint file rows are not separately consulted for edge liveness; a live connection row remains authoritative even if the endpoint file rows are inconsistent or absent

6. The returned connection-path entries must continue to use the canonical VFS encoding:

```text
<source>/.connections/<connection_type>/<target-without-leading-slash>
```

7. Predecessor backtracking must follow the first-claim predecessor tree established by the native BFS state, not arbitrary graph edges.

   Required termination behavior:

   - backtracking stops at a seed, or
   - backtracking stops at an already-added ancestor in the predecessor chain

   The implementation must not be able to loop indefinitely on graph cycles during backtracking.

## Acceptance Criteria

1. On `PostgresFileSystem`, `meeting_subgraph` executes natively in Postgres and returns a normal `VFSResult(function="meeting_subgraph", ...)`.

2. The Postgres-native implementation preserves these cases:
   - zero valid seeds -> empty result
   - one valid seed -> that seed only
   - two connected seeds -> both seeds plus required intermediates
   - adjacent seeds -> both seeds plus the connecting edge entry
   - disconnected seeds in separate live graph components -> both seeds survive
   - unknown seed mixed with one valid seed -> only the valid seed survives
   - a non-seed dangling spur that has no kept in-neighbor or no kept out-neighbor after bridge backtracking is stripped from the final result
   - a non-seed intermediary with both a kept predecessor and a kept successor is not stripped solely for being non-seed

3. Returned edge entries correspond exactly to the surviving node set and use canonical connection paths.

4. User-scoped mounts do not discover or emit other users' nodes or edges.

5. The native implementation is deterministic for the same seed order and same committed database state.

6. Concurrent requests on separate Postgres sessions do not interfere with one another.

7. No request-path DDL is required for normal execution once the backend is provisioned.

8. `PostgresFileSystem` exposes `verify_native_graph_schema()` and an explicit non-request install/provision helper for the native graph artifacts.

9. Postgres-native integration tests cover at least one deterministic tie case so the implementation does not silently inherit Python `set` iteration nondeterminism.

## Non-Goals / Follow-On Work

- `min_meeting_subgraph` can become a follow-on story once native `meeting_subgraph` exists as a foundation.
- If future profiling shows that temp-table churn is material, a follow-on story may refine the implementation strategy further.
- If the team later wants all graph algorithms native in Postgres, this story should establish the install/provision/test pattern rather than solve all of them at once.

## Open Questions

1. Should the native function live in the default schema, a dedicated internal schema, or be schema-qualified alongside the data table?
2. Do we want to add Postgres-specific partial indexes for live connection rows as part of this story, or leave that to profiling after the first native implementation lands?
