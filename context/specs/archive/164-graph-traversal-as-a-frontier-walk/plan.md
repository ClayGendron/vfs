# 164 — plan

Regenerated 2026-10-14 after the pre-build review (the draft's risks "limit awaits Clay" and "165 may land after" are decided; the mechanisms the review found missing are named here).

## Approach

Build bottom-up in the database backend, one new module, then the vocabulary, then the public surface.

1. **`storage/backends/database/graph.py`** (new; the only place the walk lives). Module layout per the house order: docstring (the frontier walk, the rights rule at `list`/`read`, the road probe and its cost, the profile acknowledgement — round trips grow with depth reached, the CTE acceleration named as the future direction), imports, constants, public API grouped as gate → resolve → hop → walk → meet → observe, internal helpers last. The shapes:
   - `GraphRequest` (NamedTuple): method, depth, edge types, minimal, limit, fetched columns — built once by the backend from the call.
   - `hop_statements(tables, profile, request, direction, chunk, view) -> list[Select]`: the narrowed statements for one frontier chunk and one direction (the clause fan expands here), plus the directories-only road probe when the view is partial and named.
   - `walk(session, host facts, request, seeds, view) -> Walk`: the §2.3 loop; `Walk` holds the visited map (`id → Node(depth, path, mapping)`), the expanded set, the hop rows (an edge list keyed by ids), and the stop facts for the warning.
   - `meet(...) -> Meeting`: the multi-source loop with owners, parents, bridges and components; `prune` and `prune_minimal` are session-free over dictionaries.
   - `induced_edges(session, …, unexpanded ids, kept ids) -> rows`: the one-list chunked fetch, the far endpoint judged in Python.
   - `observe(...) -> Result`: node rows (whole or bare), edge rows (type-only on a `list` endpoint), the `limit` cut, the warnings.
2. **`DatabaseStorage.graph`** in `backend.py`: the gate on `depth`, `limit` and the type-list size as `tree` gates `max_depth`, then `_execute("graph", self._viewed("graph", authority, seeds, body))`. `_viewed` builds the view at `needs.traverse` when declared and judges anonymous at that rung.
3. **`ranges.py`**: the pinned join construct becomes public (`pinned_join(left, right, on, profile)`); the hint sites stay where they are (the hop needs none).
4. **Vocabulary and gate**: `ops.GRAPH_METHODS`, `params.PARAMS["graph"]`, the three value-rule types and `VALUE_RULES`, `base.graph`, `session.graph`, `protocol.SupportsGraph`.
5. **Model and render**: `Observation.depth`, `OBSERVATION_QUERY_FIELDS`, `_RIGHT_ALIGN_FIELDS`, `_DEFAULT_PROJECTION["graph"]`, `graph` in the projection-free set, the arrangement in `render.py` (`_render_graph`: nodes, edges, the parent rule, the glyphs, the count line).
6. **Tests**: the conformance family in `tests/support/storage_contract.py` (`@needs("graph", "mkedge")`), the oracles in `tests/support/oracles/` (`graph_walk.py`, `meeting_subgraph.py`), the backend tests in `tests/storage/database/test_graph.py` (statement counts with the listener, the planner pin, the predicate placements under both profiles, the `list` pass, the road probe), the gate and dispatch pins, the render tests in `tests/results/`.
7. **Docs**: README, `docs/reference/api.md`, the how-to.

## Trade-offs taken

- **Loop in the app, hop in SQL.** The memo's measurements: the recursive statement is exponential on SQL Server and Oracle and cannot stop early; the loop is bounded by the nodes reached. The price is one statement per level reached. Acknowledged in the docstring; the CTE arm is the named future direction for the three engines that deduplicate `UNION`.
- **Two statements for `neighborhood`,** one per index, rather than an `OR` join: every profile plans an index seek; the `OR` form was only measured on SQLite.
- **The join pin on the hop statement.** Reusing `range_join` rather than running `ANALYZE` (the backend runs none) or adding a profile field: the planner misread is the same one the ranges join hit. No hint: the entries side is a primary-key probe.
- **Narrow at `list`, probe the road.** Narrowing in SQL keeps the hop bounded by what the caller may name (a caller who sees 1 % of a corpus must not fetch 100 %); the road is a per-call derivation ADR 080 keeps out of the compiled spans, so it costs one directories-only statement per frontier chunk under a partial named view. Documented.
- **One list per statement.** The induced fetch binds the near column only and judges the far endpoint in Python: linear in chunks, never two lists against one bind cap (SQL Server's chunk is 2,000 of 2,099).
- **Early stop at `limit`.** BFS by level makes the `(depth, path)` cut exact after the hop that crosses the limit; memory is bounded by the limit plus one level's fan-out instead of the reach.
- **Python for the post-walk phase of `meet`.** Union-find, backtracking, stripping and articulation points over a kept set of hundreds to low thousands; measured in milliseconds on 62k meeting rows. A Rust kernel is the named direction if a profile disagrees.
- **A declared tie-break** for the discovering edge, the owner, the parent and the bridge order, pinned by tests, rather than parity with the archived Python's queue accidents; the renderer re-derives the hierarchy by the same rule rather than carrying a field for it.

## Risks

- The hop statement's plan on Postgres, MariaDB, SQL Server and Oracle is unmeasured; the `range_join` pin is the mitigation and the engine legs the proof (`db_test` skill before landing).
- The road probe under a partial named view adds a statement per frontier chunk; accepted, documented, pinned in the count formula.
- A caller who names thousands of edge types is refused at `membership_budget // 2`; acceptable, documented.
- `limit` on `meet` can cut a bridge node; the answer is still a consistent subgraph and the components record counted before the cut tells the caller the seeds did connect. Flagged to Clay.
