# 004 - Implementation Notes

This document maps the current implementation for story 004 to [spec.md](./spec.md).

It also records the implementation decisions that were resolved while landing the change:

- the live repo contract uses `kind == "edge"` and `edge_type`, not the older `connection` / `connection_type` vocabulary that still appears in parts of the draft spec
- native Postgres graph traversal shipped as a mix of inline SQL for the simple traversals and one provisioned PL/pgSQL function for `meeting_subgraph`, not as one SQL function per method
- `predecessors`, `successors`, `ancestors`, `descendants`, and `neighborhood` now return node entries only on the Postgres-native path; `meeting_subgraph` is the only method in scope that emits edge entries
- surviving edge entries for `meeting_subgraph` use the repo's actual canonical metadata-edge namespace via `edge_out_path(...)`: `/.vfs/.../__meta__/edges/out/...`
- while landing the story, the Postgres backend test run also exposed an existing native-pgvector readback issue when asyncpg returned array-like values; that compatibility fix was included in the same change so the Postgres backend file stays green

## High-level result

Story 004 landed in six layers:

1. explicit Postgres-native graph schema install/verify hooks on `PostgresFileSystem`
2. shared Postgres graph helpers for scoping, seed normalization, and native row hydration
3. inline native SQL implementations for `predecessors`, `successors`, `ancestors`, `descendants`, and `neighborhood`
4. a provisioned PL/pgSQL implementation for `meeting_subgraph`
5. Postgres integration fixtures and tests that provision and lock in the native graph path
6. a small pgvector result-decoding compatibility fix plus a README capability update

The shipped implementation matches the story intent: Postgres-backed graph traversal now executes in PostgreSQL without delegating to the in-memory `RustworkxGraph` cache, while preserving the public `VFSResult` contract.

## 1. Explicit native graph schema contract

Spec coverage:

- [spec.md](./spec.md) "In" items 2, 6, and 7
- [spec.md](./spec.md) "Acceptance criteria" items 9, 10, and 11

Key code:

- [`src/vfs/backends/postgres.py#L186-L471`](../../../src/vfs/backends/postgres.py#L186-L471) defines the provisioned native `grover_meeting_subgraph(...)` function body
- [`src/vfs/backends/postgres.py#L553-L615`](../../../src/vfs/backends/postgres.py#L553-L615) adds `_native_graph_function_name()`, `_graph_schema_hint()`, `_graph_scope_prefix()`, and `install_native_graph_schema()`
- [`src/vfs/backends/postgres.py#L617-L643`](../../../src/vfs/backends/postgres.py#L617-L643) implements `verify_native_graph_schema()` and `_verify_graph_schema(...)`

The runtime contract now matches the native-search pattern already established by `PostgresFileSystem`:

- request handling does not issue DDL
- tests and setup code provision the graph artifact explicitly through `install_native_graph_schema()`
- runtime code can call `verify_native_graph_schema()` to fail fast when the function is missing

The shipped verification contract is intentionally narrow. Story 004 does not attempt to auto-manage indexes or a separate graph schema object set; it verifies the required function exists against the current table and leaves provisioning to deploy/test setup.

## 2. Shared Postgres graph helpers

Spec coverage:

- [spec.md](./spec.md) "In" items 3, 7, and 8
- [spec.md](./spec.md) "Design constraints" items 1, 3, 5, and 8

Key code:

- [`src/vfs/backends/postgres.py#L569-L600`](../../../src/vfs/backends/postgres.py#L569-L600) scopes native graph SQL to a user prefix when `user_scoped=True`
- [`src/vfs/backends/postgres.py#L592-L600`](../../../src/vfs/backends/postgres.py#L592-L600) normalizes seed paths in stable caller order via `_candidate_paths(...)`
- [`src/vfs/backends/postgres.py#L644-L659`](../../../src/vfs/backends/postgres.py#L644-L659) hydrates SQL rows back into `VFSResult(function=..., entries=[Entry(path=...)])`

These helpers are the main reason the native implementations stay small and consistent:

- every method scopes `path` / `candidates` through the existing `DatabaseFileSystem` helpers first
- every method filters on the same "live edge row" predicate:
  - `kind = 'edge'`
  - `deleted_at IS NULL`
  - non-null `source_path`, `target_path`, and `edge_type`
- every method uses the same stable seed ordering and the same unscoping path on the way out

That keeps user scoping and result shaping aligned with the shared backend contract instead of re-implementing them ad hoc in each native method.

## 3. Inline native SQL for one-hop and reachability traversal

Spec coverage:

- [spec.md](./spec.md) "In" items 1, 2, 3, and 4
- [spec.md](./spec.md) "Acceptance criteria" items 1 through 4

Key code:

- [`src/vfs/backends/postgres.py#L957-L988`](../../../src/vfs/backends/postgres.py#L957-L988) implements `_predecessors_impl(...)`
- [`src/vfs/backends/postgres.py#L990-L1021`](../../../src/vfs/backends/postgres.py#L990-L1021) implements `_successors_impl(...)`
- [`src/vfs/backends/postgres.py#L1023-L1063`](../../../src/vfs/backends/postgres.py#L1023-L1063) implements `_ancestors_impl(...)`
- [`src/vfs/backends/postgres.py#L1065-L1105`](../../../src/vfs/backends/postgres.py#L1065-L1105) implements `_descendants_impl(...)`

The shipped split is simple and deliberate:

- `predecessors` and `successors` are one indexed `SELECT DISTINCT ... ORDER BY ...` each
- `ancestors` and `descendants` use recursive CTEs rooted from the supplied seed set
- all four methods exclude the seed paths themselves from the final row set
- all four methods return empty successful results for zero valid seeds

This matches the story direction to keep the cheap traversals cheap. No Python graph reconstruction is involved, and no call is made into `self._graph.predecessors(...)`, `successors(...)`, `ancestors(...)`, or `descendants(...)`.

## 4. Native bounded undirected neighborhood

Spec coverage:

- [spec.md](./spec.md) "In" items 1, 2, 3, and 4
- [spec.md](./spec.md) "Acceptance criteria" item 4

Key code:

- [`src/vfs/backends/postgres.py#L1107-L1163`](../../../src/vfs/backends/postgres.py#L1107-L1163) implements `_neighborhood_impl(...)`

The native `neighborhood` path shipped with two important clarifications:

- it is implemented as a recursive CTE over the directed edge table, but the expansion step treats each live edge as undirected by choosing "the other endpoint" when either side matches the current frontier node
- the Postgres-native path now returns node entries only

That second point matters because the low-level `RustworkxGraph.neighborhood(...)` helper historically emitted subgraph edge rows as well. Story 004 intentionally narrows the Postgres-native contract to node-only traversal output and leaves edge emission to `meeting_subgraph`.

The implementation also filters the seed set up front to graph-participating nodes only, so isolated or unknown paths return the same empty behavior the database-backed graph contract already relied on.

## 5. Native `meeting_subgraph` via provisioned PL/pgSQL

Spec coverage:

- [spec.md](./spec.md) "In" items 1, 2, 3, 4, and 5
- [spec.md](./spec.md) "Acceptance criteria" items 5, 6, 8, and 12

Key code:

- [`src/vfs/backends/postgres.py#L186-L471`](../../../src/vfs/backends/postgres.py#L186-L471) contains the full provisioned PL/pgSQL implementation
- [`src/vfs/backends/postgres.py#L1165-L1192`](../../../src/vfs/backends/postgres.py#L1165-L1192) implements `_meeting_subgraph_impl(...)` as a thin call into that provisioned function
- [query.sql](./query.sql) preserves the corresponding prototype SQL in story space

The shipped algorithm keeps the shape from the Python `RustworkxGraph.meeting_subgraph(...)` implementation, but runs it in PostgreSQL:

- temp tables hold seeds, live edges, undirected adjacency, visited state, queue state, bridge endpoints, and kept nodes
- multi-source BFS claims nodes by seed origin in caller order
- frontier ties are broken by queue order and sorted neighbor traversal
- when two seed components meet, the function records a bridge and unions the components
- after discovery, it backtracks predecessor chains from bridge endpoints to seeds
- it then iteratively strips non-seed directed leaves from the kept subgraph
- finally, it emits both:
  - surviving node paths
  - surviving canonical edge projection paths under `/.vfs/.../__meta__/edges/out/...`

Two differences from the older draft wording are intentional and match the live repo instead of the stale prose:

- the authoritative row vocabulary is `edge` / `edge_type`
- emitted edge paths use `edge_out_path(...)`, not `/.connections/...`

## 6. Test fixtures, integration coverage, and adjacent compatibility fix

Spec coverage:

- [spec.md](./spec.md) "Expected touch points"
- [spec.md](./spec.md) "Acceptance criteria"

Key code:

- [`tests/conftest.py#L266-L283`](../../../tests/conftest.py#L266-L283) provisions native graph schema in the Postgres backend fixtures
- [`tests/test_postgres_backend.py#L945-L954`](../../../tests/test_postgres_backend.py#L945-L954) verifies the graph function is present and fails clearly when missing
- [`tests/test_postgres_backend.py#L956-L1090`](../../../tests/test_postgres_backend.py#L956-L1090) covers the shipped native traversal behavior end-to-end
- [`src/vfs/vector.py#L211-L233`](../../../src/vfs/vector.py#L211-L233) broadens native pgvector result decoding to accept array-like values from the Postgres driver
- [`README.md#L43-L43`](../../../README.md#L43-L43) updates the backend description to include native graph traversal

The new Postgres-native graph tests lock in the story contract directly:

- one-hop and reachability traversal methods return the expected node sets
- `neighborhood` performs bounded undirected expansion and returns node rows only
- `meeting_subgraph` returns both nodes and canonical `edge_out_path(...)` edge rows
- a deterministic tie case prefers the stable path-order branch
- user-scoped graph queries do not cross user boundaries
- the Postgres-native path does not delegate to the cached `RustworkxGraph`

During the full Postgres backend test run, story 004 also surfaced a pre-existing native pgvector readback issue: asyncpg/pgvector could return array-like values that were not plain `list` / `tuple`. The small `VectorType.process_result_value(...)` fix was included so the full `tests/test_postgres_backend.py --postgres` run remains green.

## 7. Verification that was run

The story was verified with:

- `uvx ruff check src/vfs/backends/postgres.py src/vfs/vector.py tests/conftest.py tests/test_postgres_backend.py README.md`
- `uv run pytest tests/test_postgres_backend.py --postgres -q`

Final focused Postgres backend result:

- `73 passed in 12.54s`

## Summary

Story 004 established a real native graph contract for `PostgresFileSystem`:

- explicit install/verify hooks for the required graph artifact
- inline SQL for cheap traversal methods
- one provisioned PL/pgSQL routine for `meeting_subgraph`
- stable user scoping and `VFSResult` shaping at the boundary
- no dependency on the in-memory Rustworkx cache for the covered traversal methods

The most important implementation takeaway is that this story did not create a second graph model. It moved execution of the existing database-backed graph contract into PostgreSQL, using the repo's live `edge` row vocabulary and canonical metadata-edge namespace.
