# 164 — Graph traversal as a frontier walk: `inbound`, `outbound`, `neighborhood`, `meet`

- **Status:** **landed 2026-10-14** (ADR 079 accepted the same day; the four slices built in one landing, see *Landing notes*). Reviewed before the build the same day against the tree spec 165 left (ADR 080 accepted, `VERB_RUNGS`, `Visibility.admits → Rung`, the road as derived `list`); the review scored the draft 48/100 on an eight-dimension readiness rubric and folded nine amendments in (below, *Amendments from the pre-build review*). Draft history: cut 2026-10-14 from ADR 079 (proposed) and the memo it stands on; revised the same day with Clay's decisions (the application controls the recursion; the names; `minimal` as a flag; seeds at depth 0; `depth=None` lawful; the hierarchy mirror off by default; traversal rights on the expanded ladder; `limit` 128; every edge among the returned nodes, rendered hierarchically with edge types). Spec 165 landed first (Clay, 2026-10-14). Four slices (A–D below), built in one landing. No `[NEEDS CLARIFICATION]` remains.
- **Date:** 2026-10-14
- **Owner:** Clay Gendron
- **Kind:** feature (the first backend implementation of the `graph` verb) and vocabulary change (four method names and a flag replace seven; new parameters; a new `Observation` field; a renderer arrangement; two gate rule types; capability pins flip; public docs name the verb)
- **Depends on:** ADR 079 (all ten pins, pin 2 as amended by ADR 080); ADR 080 as built (pins 5, 6, 7, 9, 11 and 12: `VERB_RUNGS["graph"]` is `Needs("read", traverse="list")`; `Visibility.admits` answers a rung, `holds`/`shows`/`reads`; `bare_observation`; the road derived per call by `Visibility.road`; anonymous judged at the addressed path); ADR 018 as built (`vfs_edges` with `ix_vfs_edges_fwd` and `ix_vfs_edges_rev`, `fs` rows minted by the mirror); ADR 065 rule 1 and ADR 067 (the predicate function); spec 162 as built (edges hide with a tombstoned endpoint through the liveness term; `descent.liveness_filters`); the enforcement spine as built (`rights.Visibility`: `prepare`, `narrow`, `holds`, `reads`, `road`, `clauses`; `ranges.visible_entries`; the pinned join construct in `ranges.py`); the membership helpers (`membership.membership`, `dialects.chunked`, `dialects.membership_budget`, `DialectProfile.range_join`); the params gate (`params.PARAMS["graph"]`, `_ONE_TARGET`); the result envelope (`Result.merge`, `with_mount` rebasing `edge_target`); `results/projection._DEFAULT_PROJECTION["graph"]`; `results/render.py`; `ErrorKind.truncated` at warning severity as `glean` emits it.
- **Decisions it implements:** ADR 079, pins 1–10 (pin 2 as amended). Retires the `GRAPH_METHODS` vocabulary spec 067 recorded. Folds in ADR 016 pin 4's deferred `edges(path, direction, type)` verb.
- **Research it stands on:** `../../../research/2026-10-14-graph-traversal-prior-art-and-experiments.md` and the studies under `../../../research/studies/2026-10-14-graph-traversal/` — in particular `06-executed-experiments-on-the-vfs-schema.md` (the statement counts, the cycle bomb, the planner finding) and `04-meeting-subgraph.md` (the 200-trial comparison and the pruning bug). The experiment scripts there are the spikes for this spec and stay there untouched; the backend's tests re-pin their numbers as statement counts, and the test oracles are written fresh to the rules declared here.

## Intent

Today `graph` routes, validates its method against seven names, and comes back `unsupported` from every storage. After this spec the database backend answers it on every engine it runs on, including the generic floor: a caller gives one seed path or ten thousand seed observations, a direction and a depth, and gets back the nodes reached with their distance and the edges among them, seeing only what its rights admit and never passing through what they do not. A fourth method returns the subgraph that joins a set of seeds. The hierarchy mirror is not followed unless the caller names it: a walk is over the relations callers and extractors authored. Centrality is not touched: it stays index-time data under spec 136.

The shape is a frontier walk (ADR 079 pin 1): one chunked SQL statement per hop, the visited set and the stop condition in the application, the caller's view narrowing every hop at the rung a walk passes a node on and the Python authority judging every row. The memo measured the alternative — one recursive statement per seed chunk — and found it exponential on SQL Server and Oracle and unable to stop early; it is recorded as a later acceleration (pin 4), not built here.

## Amendments from the pre-build review (2026-10-14)

The review's rubric, question bank, probes and verdict are in the session scratchpad, not the repo; what follows is what they changed. Each amendment is folded into the sections below; this list is the index.

1. **The rung is `list` to pass, `read` to return** (ADR 080 pin 5). The hop statement is narrowed at the verb's *traverse* rung; each row is whole when the caller `reads` it, else bare. `_viewed` reads a verb's `traverse` rung when declared, for the view and for the anonymous check. The draft's "`read` until spec 165 lands" clauses are gone.
2. **Bare node rows and type-only edge rows are defined** (§2.4).
3. **A road directory is passed** (ADR 080 pin 7): under a partial named view, one directories-only probe per frontier chunk feeds `Visibility.road` (§2.2).
4. **Induced edges are the selected types only, fetched over the nodes the walk never expanded, one membership list per statement** (§2.4). The draft's "last level only" fetch missed back-edges (executed probe); its two-list statement exceeded SQL Server's bind cap and its chunk cross product cost 100 statements on Oracle (executed arithmetic).
5. **The walk stops after the hop that reaches `limit`** (§2.3).
6. **Every statement the verb issues is in the count formula** (§2.5, acceptance criterion 4).
7. **The renderer re-derives the hierarchy by the declared rule**; no field is added for it (§1.4).
8. **The gate gains two declared rule types** for the value-conditional and disjointness checks; `base.graph` carries the defaults the gate never substitutes (§1.2).
9. **The meeting oracle is written fresh** to the declared tie-breaks and undirected stripping; the research script stays as it is (§3.4).

## 1. The vocabulary (slice A)

### 1.1 Methods

`GRAPH_METHODS` in `src/vfs/ops.py` becomes exactly:

| Method | Meaning | Replaces |
|---|---|---|
| `outbound` | what this node points to: follow each edge from its `source` to its `target`, the direction `mkedge` was given | `successors` (depth 1), `descendants` (depth `None`) |
| `inbound` | what points at this node: follow each edge from its `target` back to its `source` | `predecessors` (depth 1), `ancestors` (depth `None`) |
| `neighborhood` | follow edges in either direction | `neighborhood` |
| `meet` | the subgraph that joins the seeds; with `minimal=True`, pruned to the nodes needed to keep them connected | `meeting_subgraph`, `min_meeting_subgraph` |

The `ops.py` module docstring's graph paragraph is rewritten to say this. `VERB_RUNGS["graph"]` already reads `Needs("read", traverse="list")`: `list` to pass a node, `read` to return its contents. Decided by Clay 2026-10-14: `forward` / `reverse` rejected (a reference points at an older document, so "forward" reads as going back in time); `in` / `out` rejected (`in` is a Python keyword); `both` / `around` rejected (they do not say what the walk does); `meet` over `connect` (graph terminology); the minimal form is a flag, not a method.

### 1.2 Parameters

`params.PARAMS["graph"]` becomes, in house style:

```
ParamSpec("method", "str", required=True, choices=GRAPH_METHODS,
          doc="inbound, outbound or neighborhood from the seeds; meet joins them")
ParamSpec("path", "path", doc="the seed node")
_OBSERVATIONS                       # many seeds; chain glean → graph
ParamSpec("depth", "int", minimum=1, maximum=INT_CEILING, default=1,
          doc="hops from the nearest seed; None walks until nothing new is reached")
ParamSpec("edge_types", "str_seq", nullable=False, default=(),
          doc="follow only these edge types; empty follows every authored type; name fs to follow the tree")
ParamSpec("edge_types_not", "str_seq", nullable=False, default=(),
          doc="never follow these edge types")
ParamSpec("minimal", "bool", nullable=False, default=False,
          doc="meet only: prune to the nodes needed to keep the seeds connected")
ParamSpec("limit", "int", minimum=1, maximum=INT_CEILING, default=128,
          doc="node rows to return, nearest first; None returns every row")
_COLUMNS
_AUTHORITY
```

`depth` and `limit` are nullable with a non-`None` default — the first such integers in the table. **The gate never substitutes a `ParamSpec.default`** (it is a schema fact): `base.VirtualFileSystem.graph` and `SupportsGraph` carry `depth: int | None = 1` and `limit: int | None = 128` in their own signatures, and a test pins each signature default equal to its ParamSpec default.

Shape rule `_ONE_TARGET` stays. Two rule types join `params.py` beside `ShapeRule`, declared per op in a `VALUE_RULES` table and checked by `param_violation` after the shape rules: `OnlyWith(param, value, other, allowed, msg)` — `minimal=True` is lawful only when `method == "meet"`, else `invalid`; `Disjoint(left, right, msg)` — a type named in both `edge_types` and `edge_types_not` is `invalid`. Each type name passes `validate_segment`, as `Edge.edge_type` does (`Segments(param)`, the third rule type). **`fs` is followed only when `edge_types` names it**: the empty default means every authored type, and `edge_types_not=("fs",)` is redundant but lawful. `base.VirtualFileSystem.graph` gains the keyword parameters with the same defaults and routes them through `_route_single` unchanged; the `Session` wrapper and the `SupportsGraph` protocol gain them.

### 1.3 The `depth` field

`Observation` gains one query-relative field, `depth: int | None`, added to `OBSERVATION_QUERY_FIELDS` and to the renderer's right-aligned set. It is never persisted. The drift test that holds mirrors in lockstep is unaffected because `depth` is a query field.

### 1.4 Rendering

`_DEFAULT_PROJECTION["graph"]` becomes `("path", "kind", "depth")` and `graph` joins the projection-free functions: its arrangement is hierarchical, as `tree`'s is, so an agent and a human read the same picture (Clay, 2026-10-14: show the connections with their edge types in a form that conveys complicated graphs). The renderer rebuilds the hierarchy from the rows alone, by one declared rule: a node row's parent is the returned node one level shallower that an edge row joins it to, the least by `(edge_type, path)` when several qualify; a seed, and any node with no such neighbour, is a root line. Under its parent a node prints with the edge type and the arrow's direction — `imports → /src/db.py` when the parent is the source, `imports ← /src/db.py` when the child points at the parent — and its depth in brackets. Every further edge row prints where its source sits, as a line that names the type and the target and marks it `↑ cycle` when the target is an ancestor in the rendered tree and `↑ shown` otherwise. Weight and distance are appended only when populated. A closing line counts the edges and nodes.

```
/src/app.py  (seed)
├── imports → /src/db.py  [1]
│   ├── imports → /src/config.py  [2]
│   └── references → /src/app.py  ↑ cycle
└── imports → /src/config.py  ↑ shown
edges: 4 among 3 nodes
```

An edge row never appears as a node (an edge row is any observation whose `edge_target` is populated). Decided by Clay on 2026-10-14 from the rendering options page: the tree glyphs above, the same family `tree` already prints; **no Mermaid arrangement is planned** — the rows carry every edge and type, so a caller who wants a diagram draws its own. For `meet`, each seed is a root; the bridges show as the cross-links they are, and when the seeds do not all connect the components record (§3.3) prints as an info line. (The draft's `← meeting point` glyph needed an owner on the row; the review dropped it rather than add a field for a glyph.) A `limit` cut ends the block with the existing truncated warning line.

### 1.5 Pins that flip

- `tests/test_ops.py`'s dispatch sample for `graph` uses `outbound`.
- `tests/test_params.py` gains the three new parameters, the conflicting-type refusal, the `minimal`-off-`meet` refusal, the bad segment refusal, and the signature-default pin.
- `tests/base/test_dispatch.py` and `tests/base/test_authority.py` samples use the new names; the kwargs pin becomes `{"path", "method", "depth", "edge_types", "edge_types_not", "minimal", "limit", "columns"}`.
- The README's verb line and `docs/reference/api.md` name the four methods (slice D).

## 2. The walks: `inbound`, `outbound`, `neighborhood` (slice B)

### 2.1 Resolution

`DatabaseStorage.graph` runs under `_execute` and `_viewed`, as `tree` does — with one difference `_viewed` now carries for any verb whose rung entry declares `traverse`: the view is built at the traverse rung (`list` for `graph`), and an anonymous caller is judged at the addressed seeds at that same rung, because a seed may lawfully be returned bare. Seeds arrive as one path or as observations already grouped to this mount by the router; an observation contributes its `path` and nothing else (an edge row seeds from its source). A seed under `/.vfs` is `invalid`. Step one resolves seed paths to rows: one chunked `path IN` fetch (`descent.rows_by_path`, `membership_budget` chunks, sorted and deduplicated) of the judged columns and the requested columns, live rows only. Under a view each row must pass `holds(row, "list")`; a hidden directory is probed through `Visibility.road` and, when on the road, is a bare node — the same screen `read` and `tree` apply. A seed that does not resolve — unknown, tombstoned, hidden off the road — yields no row and starts no hop. Hidden and unknown are indistinguishable in the answer (ADR 065 rule 2). A seed that resolves is a node row at depth 0.

### 2.2 The hop statement

For a frontier F (a list of `entry_id` values first seen at the previous depth), one statement per chunk of the frontier budget:

- `outbound`: `SELECT e.source_id, e.target_id, e.edge_type, e.weight, e.distance, far.<columns> FROM vfs_edges e <pinned join> vfs_entries far ON far.entry_id = e.target_id WHERE membership(e.source_id, chunk) AND <liveness(far)> AND <type filter>`, where the type filter is `e.edge_type IN (edge_types)` when given, else `e.edge_type <> 'fs'`, and `e.edge_type NOT IN (edge_types_not)` when given.
- `inbound`: the same with `e.target_id` in the membership and `far.entry_id = e.source_id`.
- `neighborhood`: both statements per chunk, merged. (Two statements over the two indexes, not one `OR` join; the memo's §7 found the `OR` form adequate on SQLite but the two-index form is what every profile can plan.)

The pinned join is the profile's `range_join` keyword through the construct `ranges.py` already compiles (`CROSS JOIN` on SQLite, `INNER LOOP JOIN` on SQL Server, `STRAIGHT_JOIN` on MariaDB, a plain `JOIN` on Postgres and Oracle, which plan it from statistics), because a plain `JOIN` let SQLite's planner drive from the tombstone index and probe the edge index once per entry × seed (measured: 8.2 s for 1,000 seeds, 0.013 s with the pin). No index hint rides the hop: the entries side is a primary-key probe. The liveness term is `liveness_filters(far, profile, include_meta=False)`. The `<columns>` are `path`, `kind`, the view's `RIGHTS_FIELDS`, and `effective_columns(columns, content=False)` — bodies never ride a walk, as they never ride `tree`.

**The bind ledger.** The type lists are bound once per statement and are small by contract (a type name is one path segment; a caller names a handful); their binds are subtracted from the frontier chunk: `frontier_budget = membership_budget − len(edge_types) − len(edge_types_not)`, floored at one. A type list longer than `membership_budget // 2` is refused `invalid` at the backend (the caller can fix it), so no hop statement ever carries two lists that together exceed the cap. The view's clause binds ride on the floor's per-clause statements exactly as they ride `tree`'s.

The statement is narrowed by the view exactly as `tree_rows` narrows its subtree read: `view.narrow(stmt)` yields one statement (the three-seek join on `far.entry_id`) or one per clause (the generic floor's fan), and each returned row must pass `view.holds(row, "list")`. Merging per hop across clauses is sound: the next hop starts from the merged frontier. The rule this enforces: **to traverse an edge the caller must hold `list` on both endpoints** (ADR 080 pin 5); the near endpoint is already in the frontier (it passed), the far endpoint passes here. A far node the caller holds `read` on is returned whole; one it holds only `list` on is returned bare and still enters the frontier.

**The road probe.** The narrowing never returns a directory the caller holds nothing on, yet ADR 080 pin 7 says a walk passes a road directory — one with a nameable row beneath it. So under a partial *named* view (never anonymous, who derives no road) each frontier chunk also issues one un-narrowed statement restricted to `far.kind = 'directory'`, selecting only `judged_columns`; the directories it returns that fail `holds(row, "list")` are offered to `Visibility.road`, and those on the road join the hop's rows as bare directory nodes whose edge rows carry the type alone. Directories are few beside files, and the probe runs only under a partial named view; the docstring says so and names the cost: one statement per frontier chunk.

### 2.3 The loop

```
visited = {seed_id: (0, None)}           # id → (depth, discovering edge)
expanded = set()                          # ids whose hop has run
frontier = [seed ids in path order]
d = 0
while frontier and (depth is None or d < depth):
    rows = hop(frontier)                  # §2.2, chunked, narrowed, judged, road-probed
    expanded |= set(frontier)
    new = []
    for row in rows sorted by (far.path, edge_type, near.path):
        if far_id not in visited:
            visited[far_id] = (d + 1, row.edge)
            new.append(far_id)
    frontier = new
    d += 1
    if limit is not None and len(visited) >= limit:
        break                             # BFS by level: the (depth, path) cut is already exact
```

The visited set is bounded by the nodes reached, so `depth=None` terminates on any graph: a walk issues at most one hop per level of its reach, and a hop that finds nothing new ends it. The discovering edge of a node is the first edge, in the sort order above, that reached it at its depth — a declared tie-break, pinned by a test. The early stop at `limit` is exact because a hop only adds nodes one level deeper than every node already found, and the cut order is `(depth, path)`; it bounds the application's memory by `limit` plus one level's fan-out rather than by the reach. Every hop row is kept (the edge list the answer and `meet`'s pruning read), so memory is the edges touching the returned nodes — the same profile as `tree`.

### 2.4 The answer

Node rows in `(depth, path)` order, the seeds first. A node the caller `reads` carries `path`, `kind`, `depth` and the requested `columns`, `populated` stamped from the fetched set plus `depth`; a node the caller holds only `list` on (a granted `list` row or a road directory) is bare: `path`, `kind`, `depth`, and `populated` exactly those three. Then edge rows: **every edge of the selected types among the returned nodes**, in `(source path, edge_type, target path)` order, in the `mkedge` observation shape (`path` = source, `edge_target`, `edge_type`, `edge_weight`, `edge_distance`; `populated` stamped accordingly; no `status`). An edge touching a node the caller holds only `list` on carries its type and neither measure (ADR 080 pin 6): `edge_weight` and `edge_distance` are `None` and absent from `populated`. Edges of a type the walk did not select — `fs` unless named, and every `edge_types_not` type — are not rows: the answer is the subgraph the walk was asked about.

The hop rows already carry every selected edge *from* each expanded node (its out-edges for `outbound`, in-edges for `inbound`, both for `neighborhood`). The edges of the returned nodes the walk never expanded — the last level, or the level the `limit` stop left — come from **one chunked induced-edge fetch**: `membership(e.<near column>, chunk of unexpanded kept ids)` with the same type filter, liveness term and narrowing as a hop, one statement per chunk (two for `neighborhood`), the far endpoint judged against the kept set in the application. One membership list per statement, so the fetch is linear in the kept set's chunks and never binds two lists at once. Together the two sources are the induced subgraph in the walk's direction(s); for `neighborhood` that is every selected edge among the returned nodes. The discovering edge of each node (§2.3) is one of these rows, not a separate kind. `limit` (default 128) cuts node rows in `(depth, path)` order before the induced fetch runs and drops every edge row touching a cut node, so the answer is always a consistent subgraph; a cut appends one `ErrorKind.truncated` warning with `data={"limit": n, "nodes_found": m, "depth_reached": d}` where `nodes_found` counts the nodes found before the stop (a lower bound on the reach, §2.3) and `depth_reached` the deepest level found. `ops` is `("graph",)`. The router's `with_mount` rebases `path` and `edge_target` as it does for `mkedge`. `limit` bounds node rows **per storage**: a seed set spanning two mounts answers up to `limit` rows from each, merged in mount order — the bound `glean` already documents per entry.

A seed that is a directory walks like any node. With `edge_types` naming `fs`, its `outbound` walk is its subtree and its `inbound` walk its ancestor chain, and for a partial caller it agrees with `tree`: a granted `list` directory is a bare node, a road directory is passed through the probe (§2.2) as a bare node, and a directory the caller holds nothing on and that leads nowhere nameable is absent.

Decided by Clay on 2026-10-14: `limit` defaults to 128 and the edge rows follow the nodes; a walk returns every edge among its returned nodes, presented with their types.

### 2.5 What is pinned (both backends through the conformance contract)

Every pin names the one-line mutation that kills it, in its docstring.

- Directions: on a hand graph with a cycle, `outbound`, `inbound` and `neighborhood` at depths 1, 2, 3 and `None` equal a readable pure-Python BFS over the same edges (`tests/support/oracles/graph_walk.py`). Mutant: swap the membership column.
- Multi-seed: the union of per-seed walks equals the joint walk with the minimum depths; a seed reached from another seed stays at 0. Mutant: let a later hop overwrite a visited depth.
- Seeds at depth 0; a tombstoned seed and a hidden seed yield no row; a seed under `/.vfs` is `invalid`; an observation seed contributes its path.
- Tombstone cut: an edge into a tombstoned node is not followed and nothing beyond it is reached; `restore` brings the path back. Mutant: drop the liveness term.
- Rights cut (the leak test): for a caller who holds nothing on `b` in `a → b → c`, `outbound` from `a` returns `a` alone; the same walk as the system actor returns all three. Pinned under the three-seek profile and under the generic floor's clause fan (two clauses), so the per-hop merge is proven. Mutant: judge rows after the loop.
- The `list` pass: for a caller who holds `list` on `b` and `read` on `a` and `c`, `outbound` from `a` returns all three, `b` bare (`populated == {"path", "kind", "depth"}`), and the two edge rows touching `b` carry their type and no measure. Mutant: build the view at `read`.
- Road: a partial caller's `outbound` over `fs` from the root reaches the visible file beneath a road-only directory, the directory a bare node; the same walk agrees with `tree`. Mutant: skip the probe.
- Type filters: the default follows every authored type and never `fs`; `edge_types=("fs",)` walks the tree; `edge_types=("imports",)` follows nothing else and returns no edge row of another type; a type in both lists is `invalid`; `minimal=True` on a walk is `invalid`; a bad segment is `invalid`.
- Statement counts (the scale pin, `slow`): 10,000 seeds at depth 2, `outbound`, `limit=None`, counted with the `before_cursor_execute` listener, equal exactly `ceil(S / B) + Σ_h ceil(|F_h| / B) + ceil(|U| / B)` — the seed fetch, the hops, the induced fetch over the unexpanded kept set — under the SQLite profile and under a profile with `in_list_budget=1000`; no statement carries more binds than the budget. Mutant: fetch the induced edges unchunked.
- The cycle bomb: a 200-node fully connected cluster walked `outbound` to depth 4 with `limit=None` issues one seed statement, two hop statements and no induced statement (every node was expanded), and returns 200 node rows and 39,800 edge rows.
- `limit`: 128 by default; the nearest nodes survive, the truncated warning carries the counts, no edge row touches a cut node; a walk whose first hop crosses `limit` issues no second hop. Mutant: drop the early stop.
- Induced edges: a cross-link between two reached nodes, an edge among the last level's nodes, and a back-edge from the last level to the seed all appear as edge rows. Mutant: restrict the induced fetch's far endpoint to the last level.
- Rendering: the tree-glyph arrangement with the edge type and arrow on every line, cross-links and cycles marked, the count line, the truncated line; an edge row never appears as a node; an orphan is a root.
- Capabilities: `DatabaseStorage.capabilities()` includes `graph` on every profile including `GENERIC`; the pins in `tests/storage/database/test_reads.py` and `tests/storage/test_memory.py` flip; `storage_ops` derives it from `SupportsGraph`.

## 3. The meeting subgraph: `meet`, and `minimal=True` (slice C)

### 3.1 Discovery

A multi-source walk, undirected (both hop statements per chunk, merged), over the selected edge types, with ownership. The loop of §2.3 changes in three places: every visited node records its owner (the seed that reached it) and its parent; the rows of a hop are claimed in `(owner's seed index, edge_type, near path, far path)` order so that a node reached at the same depth by two owners goes to the earlier seed and a node reached by two routes from one owner takes the parent `(edge_type, near path)` names first — the declared rule "nearest seed, ties by seed input order", which the memo found exact against the sequential reference in 200 of 200 trials; and after each hop the rows whose two endpoints have different owners are the meetings of that hop.

Meetings are accepted in the order `(hop, the two owners' seed indexes ascending, stored source path, stored target path)` by union-find over the seeds; an accepted meeting is a bridge. The walk stops when every resolved seed is in one component, when the frontier empties, or when `depth` hops have run (the radius per seed). When the radius is spent and the seeds are not yet joined, one boundary hop runs from the last frontier that claims nothing new and only detects meetings, so two seeds `2·depth + 1` edges apart still meet at the boundary.

### 3.2 Pruning

The kept set is every seed plus every node on a bridge path: for each bridge, both endpoints traced back to their seeds through the parent map. The induced edges of the kept set come from the hop rows and the induced fetch of §2.4 over the kept nodes the walk never expanded. Then undirected degree-one stripping: repeatedly remove any non-seed node with at most one neighbour inside the kept set. The archived directed rule is not used; it deleted the shared dependency in `a → x ← b`. `minimal=True` continues: repeatedly remove the lowest-path non-seed node that is not an articulation point of the undirected kept subgraph (Hopcroft–Tarjan over the kept set, hundreds to low thousands of nodes), re-strip, until none remains. `list`-only nodes are kept and stripped like any other (ADR 080 pin 5). All of this runs in Python on the kept set; a Rust kernel is a later option if a profile shows it dominating.

### 3.3 The answer

Node rows carry `depth` = distance from the owning seed; edge rows are the surviving edges in the `mkedge` shape, the type-only rule of §2.4 applying. `limit` (128) cuts node rows nearest first and drops the edge rows touching cut nodes, as on every method; the components are counted before the cut. When the resolved seeds end in more than one component an `info`-severity `ErrorKind.not_found` record reports `data={"seeds": k, "components": c}` with the detail "no path joins every seed" (plus `"depth": d` when the radius stopped the walk), so a caller can read "not all seeds connected"; when they all connect, no record. No resolved seed → empty success. One resolved seed → that node at depth 0, no edges. Seeds in different components each survive with no edges between them.

### 3.4 What is pinned

- `a → x ← b` with seeds `{a, b}` returns `{a, b, x}` and both edges; `a → x → y ← b` returns all four and three edges. Mutant: directed stripping.
- A cycle offering two equally short routes: `meet` keeps both routes' nodes only if both were bridged; `minimal=True` keeps one, the lowest-path route. Mutant: skip the articulation check.
- The oracle: `tests/support/oracles/meeting_subgraph.py`, a readable level-synchronous reference written to §3.1–3.2's declared rules (not a copy of the research script, whose sequential queue order and directed stripping the memo found to differ); 200 seeded random digraphs agree on the kept set and the bridges.
- Hidden and tombstoned intermediaries route the meeting around them or leave the seeds unjoined; a hidden seed is absent; a `list`-only intermediary is passed and returned bare.
- Early stop: 1,000 seeds that meet within two hops issue hop statements for two hops only (statement count pinned, `slow`). Mutant: drop the connected check.
- The boundary meeting: two seeds three edges apart meet at `depth=1`. Mutant: skip the boundary hop.
- `components` is reported only when more than one remains; a disconnected seed survives alone.

## 4. Docs, pins and the public claim (slice D)

- `README.md`: the alpha banner's "no shipped storage answers it" sentence for `graph` goes; the verb table and the search section show `inbound`, `outbound`, `neighborhood`, `meet`; the example line becomes `await root.graph("inbound", "/enterprise/policies/mfa.md")` — what points at this policy. The README runs under Sybil (the root `conftest.py`), so it must be true.
- `docs/reference/api.md` gains the `graph` section: methods, parameters, the row shapes, the rights rule, the `limit` warning; `docs/how-to/` gains "walk the edges around a file" (depth-1 `inbound` as the "what points here" recipe, `edge_types=("fs",)` to walk the tree instead).
- ADR 069's "no public claim until a backend serves it" is satisfied by this slice; ADR 059's status line records the pin-4 amendment; ADR 016's status line records the fold of pin 4; ADR 079 moves to accepted.
- `context/specs/STATUS.md` and this spec's status line.

## Scope

In: everything above. Out: centrality or any analytic (spec 136 owns the signals); the recursive-CTE acceleration (ADR 079 pin 4, its own spec); cross-mount edges (spec 021, archived); a `paths` verb (trail semantics, a different algorithm); filter-based bulk `rmedge`; a Rust kernel for the post-walk phase; the MCP tool schema beyond what the params gate already generates.

## Acceptance criteria

1. `GRAPH_METHODS == {"inbound", "outbound", "neighborhood", "meet"}`; the old names are refused at the gate as `invalid`; `minimal=True` is lawful only with `meet`; `fs` is followed only when named; the signature defaults equal the ParamSpec defaults.
2. The walk reads its rungs from `VERB_RUNGS["graph"]`: `list` to pass, `read` to return whole; `DatabaseStorage.graph` answers every method on SQLite, in-memory, and (when the legs run) Postgres, MariaDB, SQL Server and Oracle, with identical conformance results; `GENERIC` serves it.
3. The leak test passes under both predicate forms: a node the caller cannot name is never in the answer and nothing is reached through it; a node the caller may only name is passed and returned bare.
4. 10,000 seeds in one call issue exactly `ceil(S / B) + Σ_h ceil(|F_h| / B) + ceil(|U| / B)` statements and no statement exceeds the bind or `IN`-list budget; the cycle bomb issues two hop statements at any depth and no induced statement.
5. `meet` on `a → x ← b` keeps `x`; the 200-graph oracle agrees.
6. Node rows carry `depth`; edge rows are every selected edge among the returned nodes in the `mkedge` shape; the renderer prints the tree-glyph hierarchy with edge types; `limit` (128) truncation is a warning with counts and leaves no dangling edge row.
7. `scripts/ci.sh` green at 100 % coverage; the README example runs.

## Landing notes

Landed 2026-10-14, all four slices in one tree-green landing (`uv run pytest`, `ruff check`, `ruff format --check`, `ty`, 100 % coverage through `scripts/ci.sh`; the README and docs fences run).

- **Slice A as specified**: `GRAPH_METHODS` is the four names and the defaults live beside it in `ops.py` (`GRAPH_DEPTH_DEFAULT`, `GRAPH_LIMIT_DEFAULT`), imported by the params table, `base.graph`, the `Session` wrapper and `SupportsGraph` alike, with the pin that the signature defaults equal the table's; `OnlyWith`, `Disjoint` and `Segments` are the three value-rule types `VALUE_RULES` declares and `param_violation` checks after the shape rules; `Observation.depth` is a query field; `graph` is projection-free and `_render_graph` rebuilds the hierarchy by the declared parent rule.
- **Slices B and C in one module** (`storage/backends/database/graph.py`, the house order: gate → seeds → hop → walks → answer → helpers). `_viewed` reads a verb's `traverse` rung when declared — the view and the anonymous check for `graph` are at `list`, the row projection at `read` through `Visibility.reads`. `ranges.pinned_join` is the join construct made public; `Visibility.derives_road` exposes the road flag so the probe skips anonymous callers. The induced fetch needs no join and no narrowing: both endpoints are kept nodes, already live and admitted, so it binds the near column alone.
- **Measured statement counts** (SQLite, `before_cursor_execute`): 10,000 seeds over 10,000 targets at depth 1 — 1 seed statement, 1 hop, 1 induced; at depth 2 — 1, 2, 0; under `in_list_budget=1000` — 10, 10, 10 and 10, 20, 0; no statement over the bind cap. The 200-clique at depth 4: 1 seed statement, 2 hops, 0 induced, 200 node rows and 39,800 edge rows. `meet` over 1,000 seeds two hops from one hub: 4 hop statements (two hops, two directions) and 2 induced (the hub, both directions). The walk and `meet` agree with the fresh oracles on 200 seeded random digraphs.
- **Two decisions taken at the build, flagged to Clay**: `limit` on `meet` cuts nearest first like every method and can drop a bridge node (the components count is taken before the cut; pointer in `open-questions.md`); the `← meeting point` glyph was dropped rather than add a row field for it — bridges show as the cross-links they are and the components record prints as the info line.
- **Engine legs**: not run in this landing (no Docker here); the join pin is compile-checked for SQLite, SQL Server and MariaDB and the conformance family runs on every leg the `db_test` skill brings up.
