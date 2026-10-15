# 164 — plan

## Approach

Build bottom-up in the database backend, one new module, then the
vocabulary, then the public surface.

1. **`storage/backends/database/graph.py`** (new; the only place the
   walk lives). Module layout per the house order: docstring (the
   frontier walk, the rights rule, the road difference, the profile
   acknowledgement — round trips grow with depth reached, the CTE
   acceleration named as the future direction), imports, constants
   (the discovering-edge sort key, the meeting sort key), public API
   grouped as resolve → hop → walk → meet → observe, internal
   helpers last. Pure functions where possible: `hop_statements(...)`
   returns the statements for one frontier chunk and direction;
   `walk(...)` drives the loop over a session and a `Visibility | None`;
   `meet(...)` drives the multi-source loop and returns the kept
   nodes, bridges and components; `prune(...)` and `prune_minimal(...)`
   are session-free over dictionaries; `induced_edges(...)` is the
   final chunked fetch; `observe_nodes(...)` / `observe_edges(...)`
   build the rows.
2. **`DatabaseStorage.graph`** in `backend.py`: `ensure_ready`, the
   gate on `depth`/`limit` shapes as `tree` gates `max_depth`, then
   `_execute("graph", self._viewed("graph", authority, body))`.
3. **Vocabulary and gate**: `ops.GRAPH_METHODS`, `params.PARAMS["graph"]`,
   `base.graph`, `protocol.SupportsGraph`.
4. **Model and render**: `Observation.depth`, `OBSERVATION_QUERY_FIELDS`,
   `_RIGHT_ALIGN_FIELDS`, `_DEFAULT_PROJECTION["graph"]`, the graph
   arrangement in `render.py`.
5. **Tests**: the conformance family in `tests/support/storage_contract.py`
   (`@needs("graph", "mkedge")`), the oracles in `tests/support/oracles/`
   (BFS; the meeting reference), the backend tests in
   `tests/storage/database/test_graph.py` (statement counts with the
   listener, the planner pin, the predicate placements under both
   profiles), the gate and dispatch pins, the render tests.
6. **Docs**: README, `docs/reference/api.md`, the how-to.

## Trade-offs taken

- **Loop in the app, hop in SQL.** The memo's measurements: the
  recursive statement is exponential on SQL Server and Oracle and
  cannot stop early; the loop is bounded by the nodes reached. The
  price is one statement per level reached. Acknowledged in the
  docstring; the CTE arm is the named future direction for the three
  engines that deduplicate `UNION`.
- **Two statements for `neighborhood`,** one per index, rather than an `OR`
  join: every profile plans an index seek; the `OR` form was only
  measured on SQLite.
- **The join pin on the hop statement.** Reusing `range_join` rather
  than running `ANALYZE` (the backend runs none) or adding a profile
  field: the planner misread is the same one the ranges join hit.
- **Python for the post-walk phase of `meet`.** Union-find,
  backtracking, stripping and articulation points over a kept set of
  hundreds to low thousands; measured in milliseconds on 62k meeting
  rows. A Rust kernel is the named direction if a profile disagrees.
- **A declared tie-break** for the discovering edge and the bridge
  order, pinned by tests, rather than parity with the archived
  Python's queue accidents.

## Risks

- The hop statement's plan on Postgres, MariaDB, SQL Server and
  Oracle is unmeasured; the `range_join` pin is the mitigation and the
  engine legs the proof (`db_test` skill before landing).
- A frontier chunk × type-list chunk cross product on a caller who
  passes thousands of type names; acceptable, documented.
- `limit`'s default and its effect on `meet`'s edge rows, and the walk's edge-row shape, await Clay.
- Spec 165 (the ladder) may land before or after; the rung table keeps the flip to one entry.
- The naming pick may change; it is a rename.
