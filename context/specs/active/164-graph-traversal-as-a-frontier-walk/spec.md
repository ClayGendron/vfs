# 164 — Graph traversal as a frontier walk: `inbound`, `outbound`, `neighborhood`, `meet`

- **Status:** draft, cut 2026-10-14 from ADR 079 (proposed) and the
  memo it stands on; revised the same day with Clay's decisions (the
  application controls the recursion; the names; `minimal` as a flag;
  seeds at depth 0; `depth=None` lawful; the hierarchy mirror off by
  default; traversal rights on the expanded ladder, spec 165; `limit`
  128; every edge among the returned nodes, rendered hierarchically
  with edge types). **Blocked on spec 165** (Clay, 2026-10-14: the
  ladder first, then the walk on its final rungs). Four slices (A–D
  below); A and B land together, C and D follow. No
  `[NEEDS CLARIFICATION]` remains: the rendering (tree glyphs, no
  Mermaid) was decided 2026-10-14.
- **Date:** 2026-10-14
- **Owner:** Clay Gendron
- **Kind:** feature (the first backend implementation of the `graph`
  verb) and vocabulary change (four method names and a flag replace
  seven; new
  parameters; a new `Observation` field; a renderer arrangement;
  capability pins flip; public docs name the verb)
- **Depends on:** ADR 079 (all ten pins); **spec 165 (the expanded
  permission ladder), which lands first** and gives the walk its
  `list` rung for intermediate nodes and the verb-to-rung table in
  `ops.py`; this spec then reads the table and adds nothing to the
  ladder; ADR 018 as built (`vfs_edges`
  with `ix_vfs_edges_fwd` and `ix_vfs_edges_rev`, `fs` rows minted by
  the mirror); ADR 065 rule 1 and ADR 067 (the predicate function);
  ADR 070 (the road); spec 162 as built (edges hide with a tombstoned
  endpoint through the liveness term; `descent.liveness_filters`,
  `tombstone_side`); the enforcement spine as built
  (`rights.Visibility`: `prepare`, `narrow`, `admits`, `entries`,
  `clauses`; `ranges.visible_entries`); the membership helpers
  (`membership.membership`, `dialects.chunked`,
  `dialects.membership_budget`, `DialectProfile.range_join`); the
  params gate (`params.PARAMS["graph"]`, `_ONE_TARGET`); the result
  envelope (`Result.merge`, `with_mount` rebasing `edge_target`);
  `results/projection._DEFAULT_PROJECTION["graph"]`;
  `results/render.py`; `ErrorKind.truncated` at warning severity as
  `glean` emits it.
- **Decisions it implements:** ADR 079, pins 1–10. Retires the
  `GRAPH_METHODS` vocabulary spec 067 recorded. Folds in ADR 016 pin
  4's deferred `edges(path, direction, type)` verb.
- **Research it stands on:**
  `../../../research/2026-10-14-graph-traversal-prior-art-and-experiments.md`
  and the studies under
  `../../../research/studies/2026-10-14-graph-traversal/` — in
  particular `06-executed-experiments-on-the-vfs-schema.md` (the
  statement counts, the cycle bomb, the planner finding) and
  `04-meeting-subgraph.md` (the 200-trial comparison and the pruning
  bug). The experiment scripts there are the spikes for this spec;
  the backend's tests re-pin their numbers as statement counts.

## Intent

Today `graph` routes, validates its method against seven names, and
comes back `unsupported` from every storage. After this spec the
database backend answers it on every engine it runs on, including the
generic floor: a caller gives one seed path or ten thousand seed
observations, a direction and a depth, and gets back the nodes reached
with their distance and the edges that reached them, seeing only what
its rights admit and never passing through what they do not. A fourth
method returns the subgraph that joins a set of seeds. The hierarchy
mirror is not followed unless the caller names it: a walk is over the
relations callers and extractors authored. Centrality is
not touched: it stays index-time data under spec 136.

The shape is a frontier walk (ADR 079 pin 1): one chunked SQL
statement per hop, the visited set and the stop condition in the
application, the caller's view narrowing every hop and the Python
authority judging every row. The memo measured the alternative — one
recursive statement per seed chunk — and found it exponential on SQL
Server and Oracle and unable to stop early; it is recorded as a later
acceleration (pin 4), not built here.

## 1. The vocabulary (slice A)

### 1.1 Methods

`GRAPH_METHODS` in `src/vfs/ops.py` becomes exactly:

| Method | Meaning | Replaces |
|---|---|---|
| `outbound` | what this node points to: follow each edge from its `source` to its `target`, the direction `mkedge` was given | `successors` (depth 1), `descendants` (depth `None`) |
| `inbound` | what points at this node: follow each edge from its `target` back to its `source` | `predecessors` (depth 1), `ancestors` (depth `None`) |
| `neighborhood` | follow edges in either direction | `neighborhood` |
| `meet` | the subgraph that joins the seeds; with `minimal=True`, pruned to the nodes needed to keep them connected | `meeting_subgraph`, `min_meeting_subgraph` |

The `ops.py` module docstring's graph paragraph is rewritten to say
this, and the verb-to-rung table spec 165 creates gains its `graph`
entries (the rung an intermediate node needs, `list`; the rung a
returned row's contents need, `read`). Decided
by Clay 2026-10-14: `forward` / `reverse` rejected (a reference points
at an older document, so "forward" reads as going back in time);
`in` / `out` rejected (`in` is a Python keyword); `both` / `around`
rejected (they do not say what the walk does); `meet` over `connect`
(graph terminology); the minimal form is a flag, not a method.

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

Shape rule `_ONE_TARGET` stays; a new rule refuses `minimal=True`
with any method but `meet` as `invalid`. A type named in both
`edge_types` and `edge_types_not` is `invalid`. Each type name passes
`validate_segment`, as `Edge.edge_type` does. **`fs` is followed only
when `edge_types` names it**: the empty default means every authored
type, and `edge_types_not=("fs",)` is redundant but lawful.
`base.VirtualFileSystem.graph` gains the keyword parameters with the
same defaults and routes them through `_route_single` unchanged. The
`SupportsGraph` protocol gains them.

### 1.3 The `depth` field

`Observation` gains one query-relative field, `depth: int | None`,
added to `OBSERVATION_QUERY_FIELDS` and to the renderer's
right-aligned set. It is never persisted. The drift test that holds
mirrors in lockstep is unaffected because `depth` is a query field.

### 1.4 Rendering

`_DEFAULT_PROJECTION["graph"]` becomes `("path", "kind", "depth")`.
`results/render.py` gains a `graph` arrangement that is hierarchical,
as `tree`'s is, so an agent and a human read the same picture (Clay,
2026-10-14: show the connections with their edge types in a form that
conveys complicated graphs). Each seed is a root line; each reached
node is indented under the node that discovered it, with the edge
type on the line and the depth; every further edge among the returned
nodes (a cross-link or a cycle) is printed where its source sits, as
a line that names the type and the target and marks it as already
shown. Weight and distance are appended only when populated.

```
/src/app.py  (seed)
├── imports → /src/db.py  [1]
│   ├── imports → /src/config.py  [2]
│   └── references → /src/app.py  ↑ (cycle)
└── imports → /src/config.py  ↑ (already shown)
edges: 4 among 3 nodes
```

An edge row never appears in the node table (an edge row is any
observation whose `edge_target` is populated). Decided by Clay on
2026-10-14 from the rendering options page: the tree glyphs above
(`├──`, `│`, `└──`, the type then `→` then the target, the depth in
brackets, `↑ shown` for a cross-link and `↑ cycle` for a cycle, a
closing count line), the same family `tree` already prints; **no
Mermaid arrangement is planned** — the rows carry every edge and
type, so a caller who wants a diagram draws its own. For `meet`, each
seed is a root, the node where two wavefronts met carries
`← meeting point`, the other seed's path is drawn upward into it, and
the closing line names the components; a `limit` cut ends the block
with the existing truncated warning line.

### 1.5 Pins that flip

- `tests/test_ops.py`'s dispatch sample for `graph` uses `outbound`.
- `tests/test_params.py` gains the three new parameters and the
  conflicting-type refusal.
- `tests/base/test_dispatch.py` and `tests/base/test_authority.py`
  samples use the new names; the kwargs pin becomes
  `{"path", "method", "depth", "edge_types", "edge_types_not", "minimal", "limit", "columns"}`.
- The README's verb line and `docs/reference/api.md` name the four
  methods (slice D).

## 2. The walks: `inbound`, `outbound`, `neighborhood` (slice B)

### 2.1 Resolution

`DatabaseStorage.graph` runs under `_execute` and `_viewed`, as `tree`
does. Seeds arrive as one path or as observations already grouped to
this mount by the router. Step one resolves seed paths to rows: one
chunked `path IN` fetch (`descent.rows_by_path` or its equivalent,
`membership_budget` chunks, sorted and deduplicated) carrying the
liveness term and the view's narrowing, every row passing `admits`.
A seed that does not resolve — unknown, tombstoned, hidden, or under
`/.vfs` — yields no row and starts no hop. Hidden and unknown are
indistinguishable in the answer (ADR 065 rule 2). A seed that resolves
is a node row at depth 0.

### 2.2 The hop statement

For a frontier F (a list of `entry_id` values first seen at the
previous depth), one statement per chunk of `membership_budget`:

- `outbound`: `SELECT e.source_id, e.target_id, e.edge_type, e.weight,
  e.distance, far.<columns> FROM vfs_edges e <range_join> vfs_entries
  far ON far.entry_id = e.target_id WHERE membership(e.source_id,
  chunk) AND <liveness(far)> AND <type filter>`, where the type
  filter is `e.edge_type IN (edge_types)` when given, else
  `e.edge_type <> 'fs'`, and `NOT IN (edge_types_not)` when given.
- `inbound`: the same with `e.target_id` in the membership and
  `far.entry_id = e.source_id`.
- `neighborhood`: both statements per chunk, merged. (Two statements over
  the two indexes, not one `OR` join; the memo's §7 found the `OR`
  form adequate on SQLite but the two-index form is what every
  profile can plan.)

The `<range_join>` keyword is the profile's `range_join`
(`CROSS JOIN` on SQLite, `INNER LOOP JOIN` on SQL Server, the
`STRAIGHT_JOIN … FORCE INDEX` pair on MariaDB), because a plain `JOIN`
let SQLite's planner drive from the tombstone index and probe the
edge index once per entry × seed (measured: 8.2 s for 1,000 seeds,
0.013 s with the pin). The liveness term is `liveness_filters(far,
profile, include_meta=False)`. The `<columns>` are `path`, `kind`,
the view's `RIGHTS_FIELDS`, and whatever `columns` asks for.

The statement is narrowed by the view exactly as `tree_rows` narrows
its subtree read: `view.narrow(stmt)` yields one statement (the
three-seek join on `far.entry_id`) or one per clause (the generic
floor's fan), and each returned row must pass `view.admits`. Merging
per hop across clauses is sound: the next hop starts from the merged
frontier. The rule this enforces: **to traverse an edge the caller
must hold the walk's rung on both endpoints**; the near endpoint is
already in the frontier (it passed), the far endpoint passes here. The
rung is the verb-to-rung table's `graph` entry — `read` until spec
165 lands the `list` rung and flips it. The edge-type filters are plain
membership terms; a type
list longer than the budget chunks like any other list (a caller who
names 2,000 types gets several statements per frontier chunk).

### 2.3 The loop

```
visited = {seed_id: (0, None)}           # id → (depth, discovering edge)
frontier = [seed ids in path order]
d = 0
while frontier and (depth is None or d < depth):
    rows = hop(frontier)                  # §2.2, chunked, narrowed, admitted
    new = []
    for row in rows sorted by (far.path, edge_type, near.path):
        if far_id not in visited:
            visited[far_id] = (d + 1, row.edge)
            new.append(far_id)
    frontier = new
    d += 1
```

The visited set is bounded by the nodes reached, so `depth=None`
terminates on any graph: a walk issues at most one hop per level of
its reach, and a hop that finds nothing new ends it. The discovering
edge of a node is the first edge, in the sort order above, that reached
it at its depth — a declared tie-break, pinned by a test. Memory is the
answer's size, the same profile as `tree`.

### 2.4 The answer

Node rows in `(depth, path)` order, the seeds first; each carries
`path`, `kind`, `depth` and the requested `columns`. Then edge rows:
**every edge among the returned nodes**, in `(source path, edge_type,
target path)` order, in the `mkedge` observation shape (`path` =
source, `edge_target`, `edge_type`, `edge_weight`, `edge_distance`;
`populated` stamped accordingly; no `status`). The hop rows already
carry every edge from a frontier node to a reached node; the edges
among the last level's nodes, whose own hop never ran, come from the
same chunked induced-edge fetch `meet` uses (§3.3), restricted to the
last level's ids. The discovering edge of each node (§2.3) is what the
hierarchical renderer indents under; it is one of these rows, not a
separate kind. `limit` (default 128) cuts node rows in that order and
drops every edge row touching a cut node, so the answer is always a
consistent subgraph; a cut appends one `ErrorKind.truncated` warning
with `data={"limit": n, "nodes_found": m, "depth_reached": d}`. `ops`
is `("graph",)`. The router's `with_mount` rebases `path` and
`edge_target` as it does for `mkedge`.

A seed that is a directory walks like any node. With `edge_types`
naming `fs`, its `outbound` walk is its subtree and its `inbound`
walk its ancestor chain. A road-only directory (visible only as a
bare name because a visible row lies beneath it, ADR 070) is below
the `read` rung, so it is absent in a walk and `graph("outbound",
"/", edge_types=("fs",))` differs from `tree("/")` for a partial
caller exactly there. This is the same answer every edge-shaped verb
already gives on a road directory (memo 2026-09-28 §5.2), it only
arises when a caller names `fs`, and it is what spec 165's `list` rung
is for: once "may pass but not read" is a rung, the walk traverses
intermediate nodes at `list` and the two verbs agree. The docstring
says so and points at `tree` and at the rung table.

Decided by Clay on 2026-10-14: `limit` defaults to 128 and the edge
rows follow the nodes; a walk returns every edge among its returned
nodes, presented with their types.

### 2.5 What is pinned (both backends through the conformance contract)

- Directions: on a hand graph with a cycle, `outbound`, `inbound`
  and `neighborhood` at depths 1, 2, 3 and `None` equal a readable
  pure-Python BFS over the same edges (an oracle in `tests/support/`).
- Multi-seed: the union of per-seed walks equals the joint walk with
  the same minimum depths.
- Seeds at depth 0; a tombstoned seed and a hidden seed yield no row;
  a seed under `/.vfs` is `invalid` at the gate as today.
- Tombstone cut: an edge into a tombstoned node is not followed and
  nothing beyond it is reached; `restore` brings the path back.
- Rights cut (the leak test): for a caller who may not see `b` in
  `a → b → c`, `outbound` from `a` returns `a` alone; the same walk as
  the system actor returns all three. Pinned under the three-seek
  profile and under the generic floor's clause fan (two clauses), so
  the per-hop merge is proven.
- Road: a partial caller's `outbound` over `fs` from the root does
  not reach a visible file beneath a road-only directory; `tree` does.
  Pinned as the documented difference until spec 165 flips the rung.
- Type filters: the default follows every authored type and never
  `fs`; `edge_types=("fs",)` walks the tree; `edge_types=("imports",)`
  follows nothing else; a type in both lists is `invalid`;
  `minimal=True` on a walk is `invalid`.
- Statement counts (the scale pin, `slow`): 10,000 seeds at depth 2
  issue exactly `Σ_h ceil(|F_h| / membership_budget)` statements,
  counted with the `before_cursor_execute` listener, under the SQLite
  profile and under a profile constructed with `in_list_budget=1000`;
  no statement carries more binds than the budget.
- The cycle bomb: a 200-node fully connected cluster walked
  `outbound` to depth 4 issues 2 hop statements and returns 200 node rows.
- `limit`: 128 by default; the nearest nodes survive, the truncated
  warning carries the counts, no edge row touches a cut node.
- Induced edges: a cross-link between two reached nodes and an edge
  among the last level's nodes both appear as edge rows.
- Rendering: the tree-glyph arrangement with the edge type on every
  line, cross-links and cycles marked, the meeting point marked for
  `meet`, the count line, the truncated line; an edge row never
  appears in the node table.
- Capabilities: `DatabaseStorage.capabilities()` includes `graph` on
  every profile including `GENERIC`; the pins in
  `tests/storage/database/test_reads.py` and `tests/storage/test_memory.py`
  flip; `storage_ops` derives it from `SupportsGraph`.

## 3. The meeting subgraph: `meet`, and `minimal=True` (slice C)

### 3.1 Discovery

A multi-source walk, undirected (both hop statements per chunk,
merged), over the selected edge types, with ownership. The loop of
§2.3 changes in three places: every visited node records its owner
(the seed that reached it) and its parent; the frontier is processed
in `(owner's seed order, path)` order so that a node reached at the
same depth by two owners goes to the earlier seed — the declared rule
"nearest seed, ties by seed input order", which the memo found exact
against the sequential reference in 200 of 200 trials; and after each
hop the rows whose two endpoints have different owners are the
meetings of that hop.

Meetings are accepted in the order `(meeting depth, the two owners'
seed order, source path, target path)` by union-find over the seeds;
an accepted meeting is a bridge. The walk stops when every resolved
seed is in one component, when the frontier empties, or when `depth`
hops have run (the radius per seed; two seeds `2·depth + 1` edges
apart can still meet at the boundary).

### 3.2 Pruning

The kept set is every seed plus every node on a bridge path: for each
bridge, both endpoints traced back to their seeds through the parent
map. Then undirected degree-one stripping: repeatedly remove any
non-seed node with at most one neighbour inside the kept set. The
archived directed rule is not used; it deleted the shared dependency
in `a → x ← b`. `minimal=True` continues: repeatedly remove the
lowest-path non-seed node that is not an articulation point of the
undirected kept subgraph (Hopcroft–Tarjan over the kept set, hundreds
to low thousands of nodes), re-strip, until none remains. All of this
runs in Python on the kept set; a Rust kernel is a later option if a
profile shows it dominating.

### 3.3 The answer

One final chunked statement fetches the induced edges of the kept set
(`source_id IN kept AND target_id IN kept`, both lists chunked, the
cross product of chunks when the kept set exceeds one chunk). Node
rows carry `depth` = distance from the owning seed; edge rows are the
surviving edges in the `mkedge` shape. `limit` (128) cuts node rows
nearest first and drops the edge rows touching cut nodes, as on every
method. An `info`-severity record
reports `data={"seeds": k, "components": c}` so a caller can read "not
all seeds connected" when `c > 1`. No resolved seed → empty success.
One resolved seed → that node at depth 0, no edges. Seeds in different
components each survive with no edges between them.

### 3.4 What is pinned

- `a → x ← b` with seeds `{a, b}` returns `{a, b, x}` and both edges;
  `a → x → y ← b` returns all four and three edges.
- A cycle offering two equally short routes: `meet` keeps both
  routes' nodes only if both were bridged; `minimal=True` keeps one.
- The oracle: the readable reference of
  `../../../research/studies/2026-10-14-graph-traversal/experiments/r4_reference.py`,
  moved into `tests/support/oracles/`, with the declared tie-breaks;
  200 seeded random digraphs agree on the kept set.
- Hidden and tombstoned intermediaries route the meeting around them
  or leave the seeds unjoined; a hidden seed is absent.
- Early stop: 1,000 seeds that meet within two hops issue hop
  statements for two hops only (statement count pinned, `slow`).
- `components` is reported; a disconnected seed survives alone.

## 4. Docs, pins and the public claim (slice D)

- `README.md`: the alpha banner's "no shipped storage answers it"
  sentence for `graph` goes; the verb table and the search section
  show `inbound`, `outbound`, `neighborhood`, `meet`; the example line
  becomes `await root.graph("inbound", "/enterprise/policies/mfa.md")`
  — what points at this policy.
  The README example runs under Sybil, so it must be true.
- `docs/reference/api.md` gains the `graph` section: methods,
  parameters, the row shapes, the rights rule, the road difference, the
  `limit` warning; `docs/how-to/` gains "walk the edges around a
  file" (depth-1 `inbound` as the "what points here" recipe,
  `edge_types=("fs",)` to walk the tree instead).
- ADR 069's "no public claim until a backend serves it" is satisfied
  by this slice; ADR 059's status line records the pin-4 amendment;
  ADR 016's status line records the fold of pin 4.
- `context/specs/STATUS.md` and this spec's status line.

## Scope

In: everything above. Out: centrality or any analytic (spec 136 owns
the signals); the recursive-CTE acceleration (ADR 079 pin 4, its own
spec); cross-mount edges (spec 021, archived); a `paths` verb (trail
semantics, a different algorithm); filter-based bulk `rmedge`; a Rust
kernel for the post-walk phase; the MCP tool schema beyond what the
params gate already generates.

## Acceptance criteria

1. `GRAPH_METHODS == {"inbound", "outbound", "neighborhood", "meet"}`;
   the old names are refused at the gate as `invalid`; `minimal=True`
   is lawful only with `meet`; `fs` is followed only when named.
2. Spec 165 has landed and the walk reads its rungs from the
   verb-to-rung table; `DatabaseStorage.graph` answers every method on SQLite,
   in-memory, and (when the legs run) Postgres, MariaDB, SQL Server
   and Oracle, with identical conformance results; `GENERIC` serves it.
3. The leak test passes under both predicate forms: a node the caller
   cannot see is never in the answer and nothing is reached through it.
4. 10,000 seeds in one call issue `Σ_h ceil(|F_h| / budget)`
   statements and no statement exceeds the bind or `IN`-list budget;
   the cycle bomb issues 2 hop statements at any depth.
5. `meet` on `a → x ← b` keeps `x`; the 200-graph oracle agrees.
6. Node rows carry `depth`; edge rows are every edge among the
   returned nodes in the `mkedge` shape; the renderer prints the
   tree-glyph hierarchy with edge types; `limit` (128) truncation is a warning
   with counts and leaves no dangling edge row.
7. `scripts/ci.sh` green at 100 % coverage; the README example runs.

## Landing notes

(To be written at landing: deviations, the engine legs' outcome, the
measured statement counts.)
