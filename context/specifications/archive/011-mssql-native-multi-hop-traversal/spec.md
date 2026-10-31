# 011 — MSSQL native multi-hop graph traversal

- **Status:** draft
- **Date:** 2026-04-23
- **Owner:** Clay Gendron
- **Kind:** feature + backend + graph

## Intent

Make `MSSQLFileSystem.ancestors(...)`, `descendants(...)`, and `neighborhood(...)` execute as a **single round trip to SQL Server**, matching the shape already used by `meeting_subgraph` on the same backend.

Covered operations:

- `ancestors`
- `descendants`
- `neighborhood`

Out of scope:

- `predecessors`, `successors` — already a single SQL query on MSSQL (`_one_hop` with `depth=1`); leave unchanged
- `meeting_subgraph` — already a single stored-procedure call; leave unchanged

Today (for the three covered methods):

- [`MSSQLFileSystem._ancestors_impl` / `_descendants_impl` / `_neighborhood_impl`](/Users/claygendron/Git/Repos/grover/src/vfs/backends/mssql.py) all delegate to [`_run_graph_traversal(...)`](/Users/claygendron/Git/Repos/grover/src/vfs/backends/mssql.py) (mssql.py:602-647).
- `_run_graph_traversal` drives a **Python BFS loop** that calls [`_one_hop`](/Users/claygendron/Git/Repos/grover/src/vfs/backends/mssql.py) (mssql.py:546-583) once per layer, plus a separate [`_filter_valid_seeds`](/Users/claygendron/Git/Repos/grover/src/vfs/backends/mssql.py) call for `neighborhood` (mssql.py:585-600).
- For a traversal of depth N this costs N (or N+1) separate `OPENJSON`-bound round trips.
- The choice to loop in Python was documented in commit `98ba8ae` as a deliberate tradeoff to avoid T-SQL recursive-CTE cycle hazards.

After this story:

- Each of the three methods issues **one call** to SQL Server and reads a single result set.
- Traversal, cycle avoidance, and bounded-depth expansion happen inside SQL Server.
- The Python side only marshals seeds / depth / scope into parameters and hydrates `VFSResult` rows back out.
- The existing `_one_hop` / `_run_graph_traversal` helpers may be deleted once all three callers move off them.

## Why

- **Backend coherence.** `meeting_subgraph` already runs as one stored-proc call; `ancestors` / `descendants` / `neighborhood` are the only remaining multi-hop traversals that still round-trip per layer. The Postgres backend (story 004) likewise does all multi-hop traversal in one query. The MSSQL backend is the outlier.
- **Round-trip cost.** Each BFS layer on MSSQL today pays a full network round trip, `OPENJSON` frontier parse, plan lookup, and result marshaling. At typical depth 3–5, that is 3–5 separate client↔server exchanges where one would do.
- **Freshness.** One call means one snapshot. Today's Python-driven BFS can see layer N and layer N+1 at slightly different snapshots if other writers are active mid-traversal.
- **Scope creep containment.** `neighborhood` currently pays an extra `_filter_valid_seeds` round trip before BFS starts. Folding it into the same SQL statement removes a whole separate network hop.
- **Consistency with story 004.** The Postgres backend made the exact same transition; MSSQL has been the lagging backend. This story closes that gap.

## Native Definition

For this story, **native in MSSQL** means:

- frontier expansion and cycle avoidance happen inside SQL Server
- recursive CTEs are allowed
- stored procedures and session-scoped temp tables (`#tmp`) are allowed
- Python may pass parameters and shape returned `Entry` rows, but it must not drive BFS layer-by-layer

This story requires each of the three methods to be **one round trip** from Python to SQL Server. It does not require every method to be a single SQL statement — a stored procedure that internally uses temp tables counts as one round trip.

## Current Contract To Preserve

The reference behavior is the current MSSQL path through [`_run_graph_traversal`](/Users/claygendron/Git/Repos/grover/src/vfs/backends/mssql.py), as exercised by [tests/test_database_graph.py](/Users/claygendron/Git/Repos/grover/tests/test_database_graph.py) and the MSSQL-facing expectations in the backend integration tests.

The native MSSQL implementation must preserve these externally visible semantics:

1. `VFSResult.function` continues to match the invoked traversal method (`"ancestors"`, `"descendants"`, `"neighborhood"`).
2. All three methods return node entries only.
3. Zero valid seeds returns an empty successful result.
4. Unknown, non-graph, or soft-deleted seeds are ignored.
5. Multi-seed inputs return the union of nodes reachable from any seed, deduplicated by path.
6. `ancestors` is directed transitive reverse reachability.
7. `descendants` is directed transitive forward reachability.
8. `ancestors` / `descendants` exclude the seeds themselves, unless a seed is independently reachable from another seed (current behavior).
9. `neighborhood(depth=N)` is bounded undirected expansion at most N hops from any seed, and includes the seed when the seed participates in the live graph (same `include_seeds=True` semantics the Python BFS applies today via `_filter_valid_seeds`).
10. Result ordering is stable — entries are sorted by path, matching the current `sorted(collected)` behavior.
11. User scoping continues to behave exactly as it does today through `_live_graph_where` / `_scope_path` / `_unscope_result`.

## Important Semantic Boundaries

This story preserves the **database-backed** graph model already used by the MSSQL backend:

- graph topology comes from live `vfs_objects` rows where `kind = 'edge' AND deleted_at IS NULL AND source_path IS NOT NULL AND target_path IS NOT NULL AND edge_type IS NOT NULL`
- graph nodes are the visible endpoints of those live edge rows
- edge liveness is determined by the edge row itself; endpoint file rows are not separately consulted
- no new persisted node table or broadened graph membership

This story does **not** change:

- the `vfs_objects` schema
- the Postgres, SQLite, or base `DatabaseFileSystem` implementations
- the public `VirtualFileSystem` method signatures
- the `RustworkxGraph` in-memory fallback used by the base `DatabaseFileSystem`

## Expected Touch Points

- `src/vfs/backends/mssql.py`
  - new native routine(s) for directed reachability and bounded undirected expansion
  - `_ancestors_impl`, `_descendants_impl`, `_neighborhood_impl` rewritten to make a single call
  - `install_native_graph_schema()` and `_verify_graph_schema()` extended to cover any new stored objects
  - `_run_graph_traversal`, `_one_hop`, `_filter_valid_seeds` may be removed if no caller remains
- `tests/test_database_graph.py` or an MSSQL-specific test module for integration coverage
- `tests/conftest.py` MSSQL fixture provisioning, if any new artifacts are introduced
- MSSQL backend docs where native capabilities are described
- `context/stories/011-mssql-native-multi-hop-traversal/query.sql` (optional prototype area, mirroring story 004)

## Scope

### In

1. A MSSQL-native implementation that collapses each of `_ancestors_impl`, `_descendants_impl`, `_neighborhood_impl` into **one round trip** to SQL Server.

2. Traversal over the same authoritative live-edge schema already used by `meeting_subgraph` and `_one_hop`:
   - `kind = 'edge'`
   - `deleted_at IS NULL`
   - non-null `source_path`, `target_path`, `edge_type`
   - optional `source_path LIKE @scope_prefix AND target_path LIKE @scope_prefix` when `user_scoped=True`

3. Cycle-safe traversal. The native routine must terminate on graphs with cycles. Acceptable strategies:
   - temp-table `#visited` + BFS loop inside a stored procedure (mirrors the `meeting_subgraph` proc shape)
   - recursive CTE with a breadcrumb trail column (fixed-width `NVARCHAR(4000)`, `CHARINDEX` cycle check) and a `MAXRECURSION` cap matching a policy depth limit

4. Bounded-depth expansion for `neighborhood` handled inside the native routine, using the caller's `depth` parameter.

5. Seed filtering for `neighborhood` done inline with the traversal. The separate `_filter_valid_seeds` round trip is removed; seeds appear in the result only when they touch at least one live edge, and that check runs in the same statement / proc as the BFS.

6. Determinism:
   - seed priority is the caller's input order
   - within equal frontier opportunities, ties are broken by stable path ordering
   - the native implementation may not inherit Python `set` iteration order

7. Integration with the existing native-graph provisioning contract on `MSSQLFileSystem`:
   - any new stored procedures, functions, or types are installed by `install_native_graph_schema()` and checked by `verify_native_graph_schema()` / `_verify_graph_schema()`
   - request-path execution assumes the artifacts already exist; no `CREATE OR ALTER PROCEDURE` is issued during a request
   - `_native_graph_verified` caching is updated accordingly

8. Concurrency safety for normal web/API use:
   - no shared mutable scratch tables across sessions (temp tables are session-local in SQL Server; stored procs on a shared connection must avoid `##global_temp` tables)
   - safe under SQLAlchemy async session pooling and `aioodbc` connection reuse
   - deterministic results under concurrent reads on the same graph

9. Results returned through the existing `VFSResult` / `Entry` contract with no public API change.

10. MSSQL-native integration coverage for each of the three operations, including at least:
    - one cyclic-graph case for `ancestors` / `descendants` that would hang a naive recursive CTE without cycle protection
    - one deep-chain case (depth ≥ 5) to confirm the single-round-trip path works past the default CTE `MAXRECURSION` boundary if a CTE is used
    - one seed-not-in-graph case for each method
    - one `neighborhood(depth=0)` case and one `depth=N ≥ 2` case
    - one multi-seed `neighborhood` case confirming union semantics

### Out

1. Changes to `predecessors` / `successors` on MSSQL — they already make one query.
2. Changes to `meeting_subgraph` on MSSQL — already a single proc call.
3. Changes to the Postgres, SQLite, or base `DatabaseFileSystem` graph paths.
4. Any change to the `vfs_objects` schema or the live-edge predicate.
5. Introducing new SQL dialect features beyond what `meeting_subgraph` already requires (no SQL/Graph NODE/EDGE tables, no CLR).
6. A transitive-closure table or any persisted precomputed reachability — that is a separate story.
7. Any change to the public `VirtualFileSystem` method signatures or `VFSResult` shape.

## Design Constraints

1. The three in-scope methods must each issue exactly one database round trip on the native path. Subsidiary work done inside a stored procedure (multiple statements, temp-table BFS loops, recursive CTE iterations, cursor scans) does not count as additional round trips for this constraint.

2. The native implementation must not call the in-memory graph helpers for these methods:
   - `self._graph.ancestors(...)`
   - `self._graph.descendants(...)`
   - `self._graph.neighborhood(...)`

3. The native implementation must continue to use `_live_graph_where(...)` semantics — same live-edge predicate, same optional user-scope prefix clause — or an equivalent predicate inlined into the stored procedure.

4. The native implementation must filter by user scope inside SQL Server when `user_scoped=True`. It must not rely on post-processing in Python to strip out-of-scope paths.

5. The implementation should work from the existing indexes on `source_path` and `target_path`. Profiling-driven index additions (for example a covering `(kind, deleted_at, source_path) INCLUDE (target_path, edge_type)` and the symmetric `target_path` variant) are in scope for this story only if they materially improve the native traversal on representative graphs; otherwise defer to a separate indexing story.

6. Only live edges participate in traversal. Soft-deleted or scope-excluded edges are invisible even if their endpoints are otherwise reachable.

7. `ancestors`, `descendants`, and `neighborhood` must deduplicate nodes by path even if multiple traversal routes discover the same node.

8. Depth handling for `neighborhood` must preserve the VFS API contract exactly, including the current meaning of `depth=0` (seeds only, when they participate in the graph) and bounded higher depths.

9. The native routine must terminate. If a recursive CTE is used, a `MAXRECURSION` cap must be set to a policy-defined limit that is at least as large as the largest `neighborhood` depth the API accepts, and the implementation must document the cap.

10. If a stored procedure is introduced, it must follow the conventions already used by `grover_meeting_subgraph`:
    - `SET NOCOUNT ON`
    - session-scoped `#tmp` tables only
    - `CREATE OR ALTER PROCEDURE` in the installer, not at request time
    - `NVARCHAR(450)` for path columns
    - schema-qualified via `_qualify(...)`

11. If a recursive CTE is used, the implementation must:
    - use fixed-width `NVARCHAR(4000)` for any breadcrumb trail (no `NVARCHAR(MAX)`)
    - use `OPTION (MAXRECURSION <cap>)` explicitly
    - combine with `OPTION (RECOMPILE)` per the "Execution Plan Stability" section — the two hints share a single `OPTION` clause

12. Every statement whose plan choice depends on caller-supplied parameters (seed list, scope prefix, depth, frontier, exclude) must carry `OPTION (RECOMPILE)`. See "Execution Plan Stability" for the full rule and rationale.

## Execution Plan Stability

SQL Server compiles a stored procedure once per parameter shape and caches the plan. The first execution **sniffs** the parameter values and bakes them into the plan; later calls with very different values reuse that plan. For graph traversal the inputs that matter most to plan choice — seed count, scope-prefix selectivity, graph density, depth — are exactly the ones that vary between calls. Without explicit recompile hints, a proc compiled against a 3-seed call from a tenant with a narrow scope can produce a plan that is catastrophically wrong for a 300-seed call from a tenant covering most of the table.

The existing single-hop paths already defend against this: `_one_hop` and `_filter_valid_seeds` both use `OPTION (RECOMPILE)`. The existing `grover_meeting_subgraph` procedure does not, and its initial `INSERT INTO #_gm_edge ... FROM {table} WHERE ... AND source_path LIKE @p_scope_prefix + N'%'` is the canonical parameter-sniffing hazard — scope-prefix selectivity alone can swing plan choice by orders of magnitude across tenants.

### Required for new native artifacts in this story

1. Every statement in a new stored procedure whose plan choice depends on caller-supplied parameters — seed list, scope prefix, depth, frontier, exclude — must carry `OPTION (RECOMPILE)`. In particular:
   - any `SELECT` / `INSERT ... SELECT` that reads `{table}` under the live-edge predicate and user-scope prefix
   - any BFS expansion statement whose frontier is a temp table whose row count can cross recompile thresholds
   - any recursive CTE used for `ancestors` / `descendants`

2. Recursive CTEs must set `OPTION (MAXRECURSION <cap>)` explicitly in addition to `OPTION (RECOMPILE)`. When combining hints, use a single `OPTION` clause: `OPTION (RECOMPILE, MAXRECURSION 0)`.

3. Do **not** use `WITH RECOMPILE` at the procedure level. Statement-level `OPTION (RECOMPILE)` is more surgical — it leaves the cheap temp-table-only statements alone and only recompiles the selectivity-sensitive ones.

4. Do **not** rely on `OPTIMIZE FOR UNKNOWN` or local-variable parameter-masking tricks. They paper over sniffing by making every call equally mediocre; for this workload the parameter values genuinely inform the plan, and per-call recompile is the right tool.

### Follow-on cleanup for existing native artifacts

These are out of scope for the *code* of story 011 but the spec records the gap so it is not forgotten:

- **MSSQL `grover_meeting_subgraph`**: add `OPTION (RECOMPILE)` to the `INSERT INTO #_gm_edge ... FROM {table}` statement and to any later statement that reads `{table}` or joins against the temp tables under caller-driven selectivity. Temp-table rowcount-triggered recompiles catch some of the later BFS statements already; the base-table read is the one that genuinely needs the hint.
- **Postgres `grover_meeting_subgraph`**: set `plan_cache_mode = 'force_custom_plan'` on the function (either via `ALTER FUNCTION grover_meeting_subgraph(...) SET plan_cache_mode = 'force_custom_plan'` at install time, or via `SET LOCAL plan_cache_mode = 'force_custom_plan'` at the top of the function body). PL/pgSQL caches a generic plan after roughly five executions; forcing custom plans per call avoids the equivalent sniffing hazard on the Postgres side.

These should land as a small companion change — ideally in the same PR or the immediate follow-up — so the plan-stability contract is consistent across every native graph artifact, not just the new ones.

### Statistics maintenance

Plan choice also depends on statistics freshness. `vfs_objects` can grow faster than SQL Server's auto-stats sampling threshold updates, especially on edge-heavy mounts. Periodic `UPDATE STATISTICS {table} WITH FULLSCAN` belongs in deploy/runbook documentation rather than in request-path code; this spec does not require implementing it, but the testing and documentation produced by the story should call it out as operational context.

## Acceptance Criteria

1. On `MSSQLFileSystem`, each of `ancestors`, `descendants`, `neighborhood` executes via a single round trip to SQL Server. Verified by counting SQL statements issued on the connection for representative graphs at depth 1, 3, and 5.

2. For `ancestors`:
   - a leaf-like node returns all transitive upstream nodes across the live graph
   - a root-like or unknown node returns an empty successful result
   - seeds are excluded unless reached indirectly via another seed
   - cycles do not cause duplicate rows or non-termination

3. For `descendants`:
   - a root-like node returns all transitive downstream nodes across the live graph
   - a leaf-like or unknown node returns an empty successful result
   - seeds are excluded unless reached indirectly via another seed
   - cycles do not cause duplicate rows or non-termination

4. For `neighborhood`:
   - `depth=0` with a seed in the graph returns only that seed
   - `depth=0` with a seed not in the graph returns an empty successful result
   - `depth=1` returns the seed plus one-hop neighbors (undirected) when the seed is in the graph
   - `depth=N` for `N ≥ 2` expands undirected reachability up to bound `N`
   - isolated or unknown seeds produce the same empty behavior as the current Python path
   - multi-seed inputs preserve union semantics and deduplicate by path

5. User-scoped mounts do not discover or emit other users' nodes for any of the three methods.

6. The native implementation is deterministic for the same seed order, depth, and committed database state.

7. Concurrent requests on separate SQL Server sessions do not interfere with one another. The test suite covers at least one concurrent invocation case against the same mount.

8. No request-path DDL is required for normal execution once the backend is provisioned. Any new native artifacts are installed by `install_native_graph_schema()` and checked by `verify_native_graph_schema()`.

9. All existing MSSQL graph traversal tests continue to pass without modification to their assertions.

10. `_run_graph_traversal`, `_one_hop`, and `_filter_valid_seeds` are either removed or are no longer called by any in-scope method. Any remaining call sites are documented.

## Suggested Implementation Shape

This spec does not mandate one form per method, but this split is the intended direction:

- **`ancestors` / `descendants`** — single recursive CTE with cycle detection, or one stored proc each. Recursive CTE is likely the simpler fit because direction is fixed and seed filtering is a straightforward `WHERE target_path IN @seeds` (for ancestors) or `WHERE source_path IN @seeds` (for descendants) on the anchor.

  Sketch (ancestors):

  ```sql
  ;WITH seeds AS (
      SELECT value AS path FROM OPENJSON(@seeds) WITH (value NVARCHAR(450) '$')
  ),
  walk AS (
      SELECT DISTINCT o.source_path AS node,
             CAST(N'|' + o.target_path + N'|' + o.source_path + N'|' AS NVARCHAR(4000)) AS trail
      FROM {table} AS o
      JOIN seeds s ON s.path = o.target_path
      WHERE {live_edge_predicate}
      UNION ALL
      SELECT o.source_path,
             CAST(w.trail + o.source_path + N'|' AS NVARCHAR(4000))
      FROM {table} AS o
      JOIN walk AS w ON o.target_path = w.node
      WHERE {live_edge_predicate}
        AND CHARINDEX(N'|' + o.source_path + N'|', w.trail) = 0
  )
  SELECT DISTINCT node FROM walk
  WHERE node NOT IN (SELECT path FROM seeds)
  ORDER BY node
  OPTION (MAXRECURSION 0);
  ```

  `descendants` is the mirror image swapping `source_path` and `target_path`.

- **`neighborhood`** — one stored procedure that mirrors the `meeting_subgraph` shape at a smaller scale:
  - materialize an undirected adjacency from the live-edge predicate and optional scope prefix
  - seed a `#visited(node, depth)` with the supplied seeds at depth 0 (pre-filtered to those that touch any live edge)
  - BFS loop until no new nodes are added or `depth` is reached
  - select `node` from `#visited` ordered by `node`

  Rationale: an undirected recursive CTE in T-SQL requires duplicating the recursive member for both directions and fighting trail bookkeeping across the merge. A stored proc using temp tables is the same pattern already used and tested by `meeting_subgraph`, and keeps all three methods consistent in provisioning style.

If profiling shows that all three methods are happier as stored procedures (or all three as CTEs), unify on one form. Do not split forms per-method on aesthetic grounds.

## Non-Goals / Follow-On Work

- Retrofitting `OPTION (RECOMPILE)` into the existing MSSQL `grover_meeting_subgraph` proc and setting `plan_cache_mode = 'force_custom_plan'` on the existing Postgres `grover_meeting_subgraph` function — identified in "Execution Plan Stability" as a required companion change; if not folded into this story's PR, the immediate follow-up.
- A `vfs_closure` transitive-closure table for O(1) ancestor/descendant lookup — separate story, higher write-path cost, worth exploring only after this story ships and if profiling shows native multi-hop traversal is still the bottleneck.
- Covering / partial indexes on the edge table — a separate indexing story, benefits all backends and all traversals, should not be coupled to this refactor.
- Native `min_meeting_subgraph`, PageRank, or other centrality algorithms on MSSQL — out of scope.
- Unifying the MSSQL and Postgres native graph interfaces behind a shared abstraction — out of scope; both backends already expose the same Python surface, the divergence is implementation-internal.

## Open Questions

1. Single stored procedure that dispatches on a `mode` parameter (`'ancestors' | 'descendants' | 'neighborhood'`) vs. three separate procedures (or a mix of CTE and proc)? Single proc keeps provisioning simple; separate procs keep plan caching cleaner and let `ancestors` / `descendants` be plain recursive CTEs.
2. Should `neighborhood` preserve its `include_seeds=True` behavior by folding the `_filter_valid_seeds` EXISTS check into the anchor of the CTE / the seed hydration step, or by emitting seeds unconditionally and letting the BFS add edges only when the seed participates? Current Python behavior filters seeds first; the native path should match.
3. What `MAXRECURSION` cap is appropriate? Policy-defined, or a hard `32767` (the T-SQL maximum)? Larger caps are only needed for `ancestors` / `descendants` since `neighborhood` is already bounded by the caller.
4. Should this story also add the covering edge indexes recommended in the broader graph-traversal research, or strictly defer them? Deferring keeps scope tight but may understate the single-round-trip win.
5. Should the new native artifacts live in the same provisioning routine as `grover_meeting_subgraph` (one install call provisions everything) or in a separate install helper so callers can opt in per capability? The existing pattern leans toward one install call; staying consistent is probably right.
