# Graph traversal: how the field walks a graph on SQL, and what the vfs schema measured

- **Status:** research memo (commits us to nothing). Feeds ADR 079
  (proposed, same day) and spec 164 (drafted the same day).
- **Date:** 2026-10-14
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-13, starting the graph work: implement
  ancestors, predecessors, neighborhood, the meeting subgraph and the
  minimal meeting subgraph, with four directions — (1) SQL native as
  much as possible; (2) rights enforced through the traversal, not
  after it; (3) collapse the four directional methods into a direction
  plus a `depth` argument with names that make the direction
  unmistakable (his first suggestion: `in_degree` / `out_degree`);
  (4) every supported dialect serves `graph`, revisiting ADR 059 pin 4,
  which withholds it from unknown dialects. Traversal only: centrality
  stays index-time data (spec 136), and is out of scope here.
- **Method:** six parallel studies, each a read-only subagent with the
  same brief (`studies/2026-10-14-graph-traversal/00-brief.md`), each
  told to label every claim EXECUTED, READ or INFERRED and to copy
  nothing. Three studied prior art; three ran experiments. The
  experiments ran on the live vfs schema and backend (`DatabaseStorage`
  over SQLite, built through the public verbs `write` and `mkedge`),
  on plain SQLite tables shaped like `vfs_edges`, and as compile-only
  renders for the other four dialects. Scripts and their outputs are in
  `studies/2026-10-14-graph-traversal/experiments/`. The six reports
  are the numbered files beside them; this memo is the synthesis.
  Every engine fact for Postgres, MariaDB, SQL Server and Oracle that
  was not executed is marked so in the studies; the four real-engine
  legs were not run.
- **Sources (clones refreshed to `origin/HEAD` on 2026-10-13, none
  dirty; licences read from the checkout — `refresh.log` and
  `licenses.log` in the studies folder):** `age` `d7e2e74` (Apache-2.0);
  `gel` `8519106` (Apache-2.0); `cayley` `81dcd7d` (Apache-2.0);
  `duckpgq` `91433a8` (MIT); `sqlalchemy` `cc5822a8e` (MIT);
  `postgres` `b128e75e` (PostgreSQL licence); `sqlite` `3d17c3f9e`
  (public domain); `spicedb` `a1dad93` (Apache-2.0); `openfga`
  `526995e` (Apache-2.0); `jackrabbit-oak` `9c7d6d0` (Apache-2.0);
  `tinkerpop` `ab3ef76c03` (Apache-2.0); `openCypher` `677cbaf`
  (Apache-2.0); `opengql-grammar` `16ea71b` (Apache-2.0); `GraphLite`
  `a370a1c` (Apache-2.0); `ladybug` `0ba61c4` (MIT); `kuzu` `89f0263`
  (MIT, archived upstream); `neo4j` `eccd584a` (GPL-3.0, study only);
  `networkx` `6da4704` (BSD-3); `rustworkx` `25398ab4` (Apache-2.0);
  `graphiti` `9b17e94` (Apache-2.0); `LightRAG` `4d0afc1bc` (MIT);
  `cognee` `f154b32a9` (Apache-2.0); `HippoRAG` `d5c8329` (MIT);
  `graphrag` `5faaaf4` (MIT); `mem0` `d26ba5e` (Apache-2.0); `memori`
  `574b1ea` (Apache-2.0); `terminusdb` `79cbbcff` (Apache-2.0);
  `helix-db` `16b7a837` (AGPL, study only); `mirage` `314f00488`
  (Apache-2.0); `afs` `1e9b731` (BSL 1.1, study only); `letta`
  `5bcdd177d` (Apache-2.0); `oso` `7292df0` (Apache-2.0, upstream
  idle since 2025-02). Engine documentation for MariaDB, SQL Server
  and Oracle by URL, cited in the studies.

## One-paragraph summary

Nobody in the field compiles a multi-hop graph walk into a recursive
SQL statement. The two serious graph-on-SQL systems (Apache AGE,
DuckPGQ) load the whole edge set into the engine process and run a C
kernel; every authorization system (SpiceDB, OpenFGA) and every
agent-memory system walks hop by hop in the application, one flat
query per hop, with a visited set and a depth cap. Our own experiments
explain why. A recursive CTE has no visited set: with a depth column
it enumerates paths, not nodes, and on the two engines that allow only
`UNION ALL` in the recursive member (SQL Server, Oracle) a dense cycle
makes it exponential (7.9 million rows at depth 3 on a 200-node
cluster; 1.58 billion predicted at depth 4). The per-hop loop with an
app-side visited set returned 399 rows in two statements on the same
graph. The per-hop loop also has three properties the CTE lacks: the
caller's rights can be judged by the Python authority on every row
(the law vfs already holds for every read), the meeting subgraph can
stop the moment the seeds are joined, and it needs no engine fact at
all — so every dialect, including the generic floor, serves `graph`.
The naming study found that `in_degree` and `out_degree` are counts in
every library and are already count fields on vfs's own observation
row; the field names direction by the stored arrow or by point of view,
and the arrow-relative pair `forward` / `reverse` is the one an agent
cannot misread, because `mkedge` already defines the arrow. The meeting
subgraph is a differentiator: no retrieval system studied joins seeds,
they all expand around them. Its old directed pruning rule is a bug
(it deletes the shared dependency in `a → x ← b`), and its ownership
rule is exactly reproducible in SQL or in the app.

## 1. The question in plain terms

A graph walk starts at some seed nodes and follows edges. vfs stores
edges in one table, `vfs_edges`, with both directions indexed. A walk
must answer four things on every hop: which edges to follow (the
direction and the edge types), whether the far node is alive (not a
tombstone), whether the caller may see the far node (its rights), and
when to stop (the depth). The design question is where each of those
four runs: inside one SQL statement that recurses, or in a loop where
each hop is one plain statement and the application keeps the state.

Two terms used throughout. A **recursive CTE** is one SQL statement
that repeats a sub-select until it produces no new rows; the engine
keeps a working table between rounds. A **frontier loop** is an
application loop: the set of nodes found in the last hop is the
frontier; one statement fetches the frontier's neighbours; the
application removes the ones already seen and makes the rest the next
frontier.

## 2. What the five engines can and cannot do (study 01)

The facts a portable recursive statement would have to live under,
read from the engine sources and documentation and executed on SQLite:

| Fact | PostgreSQL | SQLite | MariaDB | SQL Server 2025 | Oracle 23ai |
|---|---|---|---|---|---|
| Keyword SQLAlchemy emits (executed) | `WITH RECURSIVE` | `WITH RECURSIVE` | `WITH RECURSIVE` | `WITH` | `WITH` |
| `UNION` (dedup) between anchor and recursive member | yes | yes | yes | **no, `UNION ALL` only** | **no, `UNION ALL` only** |
| Subquery in the recursive member | yes, if it does not name the CTE | yes | yes (inferred) | **no subqueries at all** | yes, if it does not name the CTE |
| Cycle clause | `CYCLE` (14+) | none | `CYCLE … RESTRICT` (10.5.2+) | none | `CYCLE`; without it a cycle is error ORA-32044 |
| Recursion cap | none | none | `max_recursive_iterations` default 1000, **stops silently** | `MAXRECURSION` default 100, **error 530** | none |
| Evaluation | whole working table per round | one row at a time, FIFO | per step | one row at a time, LIFO (depth-first emission) | per step |

Three consequences follow, each executed on SQLite and confirmed by the
documentation of the other four.

- **No engine deduplicates visited nodes inside the recursion when a
  depth column is carried.** `UNION` compares whole rows, so `(node,
  depth 2)` and `(node, depth 3)` are both kept. Postgres's own
  documentation says it: changing `UNION ALL` to `UNION` "would not
  eliminate the looping" once a depth output is required.
- **The depth column is path length, never shortest distance.** A node
  reached by two paths appears once per path. Shortest distance needs
  `GROUP BY node, MIN(depth)` outside the recursion. Executed: 310 of
  1,253 reached nodes carried rows at several depths.
- **`UNION ALL` with a depth bound enumerates every path.** On a
  200-node fully connected cluster the row count is `Σ (N−1)^d`: 200,
  39,801, 7,920,400 at depths 1, 2, 3 (executed, 4.8 s at depth 3), and
  1,576,159,601 at depth 4 (predicted from the executed series, not
  run). A hub module that everyone imports and that imports everyone
  is an ordinary shape in a code graph.

SQLAlchemy compiles the recursive shape for all five dialects without
complaint, including `UNION` for SQL Server and Oracle, which those
engines then refuse. SQLAlchemy models none of the recursion facts
(no cap, no cycle clause, no set-operator rule), so any recursive design
would add three `DialectProfile` fields.

## 3. How the field walks a graph on a SQL table (study 02)

| System | Execution shape | Depth bound | Cycle policy | Direction words |
|---|---|---|---|---|
| Apache AGE (Cypher on Postgres) | whole graph cached in the backend process; C depth-first search as a set-returning function in the plan | caller's `[*lo..hi]`, no cap | trail (no repeated edge) for paths; visited set for shortest path | `->`, `<-`, `-` |
| DuckPGQ (SQL/PGQ on DuckDB) | CSR of the whole edge table built per query; 512-lane multi-source BFS as a scalar function | `{lo,hi}`; unbounded walk refused | visited bitset | `->`, `<-`, `-` |
| cayley (graph over SQL) | client-side loop, one morphism per depth, visited map in Go; its SQL optimizer cannot even push a multi-value frontier into `IN` | default 50 | visited set | `Out`, `In`, `Both` |
| gel (EdgeDB on Postgres) | backlinks are joins; no transitive closure in the language | n/a | n/a | `.link`, `.<link` |
| jackrabbit-oak | direct children by key range; descendants by client walk | n/a | tree | child / parent |
| SpiceDB, OpenFGA (authorization) | application loop, one flat fan-out query per hop over a chunk of ids | 50 / 25 | depth (SpiceDB); tuple-keyed visited set (OpenFGA) | relation names |
| terminusdb, GraphLite, helix-db | in-process over their own stores | bounded or capped | trail / all four GQL path modes / visited set | `p`/`n`; GQL arrows; `Out`/`In`/`Both` |

The split is clean. Systems that return **paths** use trail semantics
and pay factorial cost; AGE's source comment calls a vertex-visited set
"incorrect, not merely faster" for path queries. Systems that answer
**reachability** use a visited set and return a node set with a depth.
vfs's verb is reachability. The recursive CTE is something only vfs's
own archived spec 011 reached for; no shipping system uses it.

AGE is the one system with rights inside the walk: it loads vertices
and edges through SPI so Postgres row-level security filters them, and
drops every edge whose endpoint was filtered. Its regression test
`regress/sql/rls_vle.sql` pins exactly vfs's rule: hide the middle node
and nothing beyond it is reached.

## 4. Rights inside the walk (study 03)

vfs already owns the predicate. `Rights.admits` in Python is the law;
the storage half compiles the same rights to one of two SQL pushdowns:
the three-seek `UNION ALL` join on `entry_id` where the dialect
declares a range source, or a literal `OR` of path terms split into
disjunctive clauses on the generic floor, each statement run once per
clause and merged. Every read verb then checks each fetched row with
`admits`; `tree` does exactly this.

Executed on SQLite with a planted chain `x → hidden → y`:

- the predicate on the far node **inside** the walk reaches `{x, z}`;
- the predicate applied **after** the walk reaches `{x, z, y}` — `y`
  leaks, reached through the hidden node.

So a post-walk filter cannot enforce Clay's rule; it can hide a node
but cannot un-walk the hop through it. The predicate must run on every
hop. Two more facts bind the shape:

- **The clause fan cannot ride a recursion.** Clauses are disjunctive
  statements merged afterwards. A path whose middle node is admitted by
  clause 1 and whose next node by clause 2 is found by neither
  statement. Inside a recursion the predicate must be whole in one
  statement. In a frontier loop, merging the clauses **per hop** is
  sound, because the next hop starts from the merged frontier.
- **`admits` cannot judge rows inside a recursion.** The pushdown is
  exact today (executed: the three-seek join admitted 504 rows and
  `admits` admitted the same 504), and the parity tests pin that. But
  the architecture's rule is that SQL narrows toward the Python
  authority, which judges every row. A recursion would make the SQL
  pushdown the sole referee of which hops happen. A frontier loop keeps
  the law: SQL narrows each hop, `admits` judges every row before it
  becomes a frontier node.

Per engine, a recursive design would also have to spell the visible
set so it is computed once: a `MATERIALIZED` CTE on SQLite and
Postgres, a materialize hint on Oracle, a prior CTE on MariaDB, and on
SQL Server a `#temp` table, because its recursive member admits no
subquery and its CTEs are not materialized. The frontier loop uses
`Visibility.narrow` as every other read does.

The road case (ADR 070): a directory hidden to the caller but with a
visible row beneath it shows as a bare name in `ls`, `glob` and
`tree`. `admits` is false for it, and vfs already decided that edges
on a road directory answer not-found (memo 2026-09-28 §5.2). So in a
walk a road-only directory is absent, and a walk over `fs` edges
differs from `tree` exactly there. The honest options are to document
the difference or to route `fs`-only walks to the subtree scan; this
memo recommends documenting it (§8, open question 1).

## 5. The meeting subgraph (study 04)

The meeting subgraph joins k seeds: a multi-source breadth-first
search where each node is owned by the seed that reaches it first,
edges between differently owned nodes are bridges, union-find merges
components as bridges appear, the walk stops when every seed is in one
component or the frontier empties, and the kept set is the bridge paths
traced back to the seeds, then pruned. It is a directed Steiner-tree
approximation; Mehlhorn's algorithm in networkx and rustworkx starts
with the same ownership partition.

Executed on 200 random cyclic digraphs against a pure-Python reference:

- **Ownership is exact.** "Nearest seed, ties by seed input order" is
  what the sequential first-claim search computes; a SQL window
  function or the app loop reproduces it on every node in all 200
  trials.
- **Bridge choice is a tie-break.** A set-based order differed from the
  sequential queue order in 71 of 200 trials; both are valid spanning
  forests over the same meeting edges, and seed connectivity never
  differs. The contract should declare the rule; the old Python order
  was never a contract.
- **Directed leaf stripping is a bug.** The archived rule removed any
  non-seed node with no kept in-neighbour **or** no kept out-neighbour.
  On `a → x ← b` (two files importing one module) it deletes `x` and
  returns the two seeds with no edges, as if unrelated. It collapsed 73
  of 200 random results to seeds only. Discovery is undirected, so
  pruning must be undirected degree-one stripping, which is what
  networkx does.
- **One recursive statement is the wrong shape at scale.** On 100k
  nodes, 400k edges and 1,000 seeds, a recursive CTE carrying the owner
  grew to 2.48 million working rows at depth 4 (26 s) because the
  working table is nodes × origins. One statement per hop with a
  visited set did it in three statements (0.77 s) and stopped at hop 2,
  when union-find saw all 1,000 seeds joined. "Stop when connected"
  cannot be expressed inside one recursive CTE on any supported engine.
- **The old native functions were O(E) per call.** The archived
  PL/pgSQL and T-SQL procedures copied the whole live edge table into a
  temp table on every request and popped one queue node per loop
  iteration.

No retrieval or agent-memory system studied computes a meeting
subgraph. HippoRAG and KAG run personalised PageRank; graphrag,
LightRAG and youtu-graphrag take one-hop stars; graphiti and cognee
take k-hop unions (depth at most 3). "Show me the structure that
connects these k files" is a question none of them answers.

The minimal form removes non-seed nodes that are not articulation
points of the undirected kept subgraph (a node whose removal would
disconnect it), re-stripping leaves after each removal. It is the same
traversal with one more pruning pass on a small set.

## 6. Names, parameters and rows (study 05)

- **`in_degree` / `out_degree` are counts** in networkx, rustworkx and
  every graph library, and vfs's own `Observation` already carries
  `in_degree` and `out_degree` as ranking-count fields
  (`models/entry.py`). Using them as walk names would collide inside
  the very rows the verb returns.
- The field names direction either **by point of view** (Gremlin
  `in()` / `out()` / `both()`, neo4j `INCOMING` / `OUTGOING`; Gremlin's
  javadoc needs a worked example and later added `from` / `to`
  aliases) or **by the stored arrow** (networkx `reverse=`, cognee
  `forward` / `reverse` / `both`, AGE's internal `RIGHT` / `LEFT` /
  `NONE`). vfs already names the arrow: `mkedge(source, target)`. So
  `forward` follows each edge from its source to its target, `reverse`
  follows it back, `both` ignores the arrow. One sentence defines them
  and nothing collides. `in` is a Python keyword and reads as "inside";
  `upstream` / `downstream` flip meaning between dependency graphs and
  data-flow graphs.
- Every reachability API collapses one-hop and k-hop into **direction
  plus depth** (helix-db `max_depth`, cayley `FollowRecursive`,
  GraphLite `max_hops`, apoc `maxLevel`). Default depth 1 is the common
  agent question ("what points at this?"). Unbounded depth is allowed by
  Gremlin, Cypher, apoc and AGE and refused by Kuzu; it is safe only
  under node-global uniqueness, which a visited-set walk gives.
- **Seeds at depth 0** in every method: networkx `ego_graph`, apoc
  (`minLevel` 0), cognee and LightRAG include the centre; the archived
  "excluded unless reached via another seed" rule is unstable under a
  multi-seed union; and the meeting subgraph must return the seeds
  anyway, so one law serves every method.
- **Rows.** Mature "subgraph" answers return nodes and edges (cognee,
  LightRAG, apoc `subgraphAll`). vfs's `Observation` already has the
  edge fields (`edge_target`, `edge_type`, `edge_weight`,
  `edge_distance`) and `mkedge` already returns edge rows in that
  shape. It has no `depth` field; one is needed. Executed: under
  `graph`'s current default projection an edge row renders as a blank
  duplicate of its source path, so the verb needs its own arrangement.
- ADR 016 pin 4 promised a read verb `edges(path, direction, type)`.
  A depth-1 `forward` or `reverse` walk whose edge rows carry the type
  and weight is that verb; no separate name is needed.
- **Consumers** bound answers with a count and a truncation flag
  (cognee, LightRAG); graphiti's silent `max_nodes` cap is the
  counterexample. vfs already has `ErrorKind.truncated` at warning
  severity, which `glean` emits. One `graph` tool with a `method` enum
  is the common MCP shape; graphiti's thirteen tools show the cost of
  the alternative.

## 7. What the vfs schema measured (study 06)

Built through the public verbs on `DatabaseStorage` over SQLite: 2,000
files in one `write`, 8,000 authored edges of three types in one
`mkedge`, plus the 2,005 `fs` rows the backend minted; one strongly
connected component of 1,914 nodes, so the graph is cyclic. Then a
second file with 10,000 more files and 20,000 more edges for the
batch contract, and a third with a 200-node and a 50-node fully
connected cluster for the cycle bomb.

- **Correctness.** A recursive CTE per seed chunk (with `UNION`,
  `GROUP BY node, MIN(depth)`, the liveness term and the rights
  predicate on the far node) agreed with a pure-Python BFS in 480 of
  480 trials (three directions × depths 1–4 × 20 seed sets × two type
  filters). The frontier loop agreed with it on every comparison.
- **Seed chunking.** `membership_budget` chunks 10,000 seeds into 1
  statement-chunk on SQLite, Postgres and MariaDB, 5 on SQL Server and
  10 on Oracle. Union of per-chunk walks equals the joint walk, with
  the same minimum depths (executed), so chunking is sound.
- **Statement counts at 10,000 seeds, depth 2 → 4:**

  | form | SQLite / Postgres / MariaDB | SQL Server | Oracle |
  |---|---|---|---|
  | recursive CTE per seed chunk | 1 | 5 | 10 |
  | frontier loop (per hop, per frontier chunk) | 2 → 3 | 6 → 7 | 12 → 13 |

  The CTE's count is independent of depth; the loop's is the sum over
  hops of the frontier's chunks, and hop 1 is the seed chunks. Rows
  returned by the CTE **grow with the chunk count** (12,003 → 31,535 →
  43,557 rows for the same 12,003-node answer) because each chunk
  re-walks neighbourhoods other chunks also reach; the loop's rows stay
  near the answer size (10,316 → 20,830).
- **The cycle bomb** (200-node cluster, one seed, direction forward):

  | depth | `UNION ALL` rows | `UNION` rows (join work) | frontier rows (statements) |
  |---|---|---|---|
  | 2 | 39,801 | 400 (39,800) | 399 (2) |
  | 3 | 7,920,400 | 600 (79,600) | 399 (2) |
  | 4 | 1,576,159,601 predicted, not run | 800 (119,400) | 399 (2) |

  `UNION` is polynomial but re-expands every node at every level;
  `UNION ALL` is exponential; the loop finds nothing new at hop 2 and
  stops. SQL Server and Oracle only allow `UNION ALL`.
- **A planner finding that binds the loop.** A non-recursive hop
  statement with an `IN` list over the seeds, on a SQLite file with no
  statistics, planned as a scan of every live entry through the
  tombstone index with an edge-index probe per entry × seed: 8.2 s for
  1,000 seeds, ten CPU-minutes for 10,000 before it was killed. The
  profile's own `range_join` pin (`CROSS JOIN` on SQLite) fixed it:
  0.088 s for 10,000 seeds. The recursive member never hit this because
  its working table must drive the join. **Every per-hop statement must
  use the dialect's join pin**, which vfs already models.
- **A temp-table anchor** (one `CREATE`, one bulk `INSERT`, the walk,
  one `DROP`) costs four statements and puts DDL on a read verb; it
  never beats the chunked form on round trips.

## 8. What the evidence says, and where it leaves judgment calls

The frontier loop is the one shape that is bounded on the least
generous engine, keeps `admits` as the referee on every row, lets the
meeting subgraph stop when the seeds join, and needs no engine fact. The
recursive CTE per chunk is correct and cheaper in round trips on the
three engines that deduplicate `UNION`, and is exponential on the two
that do not. "SQL native as much as possible" is honoured by the loop
in the sense that matters: every hop's expansion, type filter, liveness
term and rights predicate is one SQL statement, chunked by the house
budget, over the indexes the schema already has; only the loop control,
the visited set and the stop condition live in the application, which
is where SpiceDB, OpenFGA, cayley and the old vfs backend keep them.

The cost the loop carries is round trips proportional to the depth
reached: a walk of depth d issues at least d statements, and an
unbounded walk issues one per level of the graph's reach from the
seeds. For the hierarchy that is the tree's height; for import graphs
it is their small diameter. The CTE per chunk is the measured
acceleration for engines that deduplicate `UNION`, and belongs in a
later spec if a profile ever shows round trips dominating.

Open questions this memo leaves for the ADR and the spec (pointers in
`../open-questions.md`):

1. Whether a walk over `fs` edges should equal `tree` at a road
   directory (route `fs`-only walks to the subtree scan) or document the
   difference. Recommended: document it; one law for the walk.
2. The method names: `forward` / `reverse` / `both` is the
   recommendation; `outbound` / `inbound` / `around` is the acceptable
   second; `connect` / `connect_min` versus `meet` / `meet_min` for the
   meeting subgraph.
3. Whether the minimal meeting subgraph is a method or a flag. The
   naming study prefers a method (a flag is meaningless on walks and
   needs a cross-parameter gate rule); the algorithm study prefers a
   flag (same traversal, one more pass). Recommended: a method, for the
   closed enum and uniform parameters.
4. Whether `limit` cuts edge rows as well as node rows on the meeting
   subgraph.
5. Real-engine verification of the per-hop statement's plan on
   Postgres, MariaDB, SQL Server and Oracle, and of the two documented
   refusals (`UNION` in a recursive member) if the CTE acceleration is
   ever picked up.

## One-line version

Walk hop by hop with one chunked SQL statement per hop, judge the
rights on every row, keep the visited set and the stop in the app, and
every engine serves `graph`; a single recursive statement is correct on
three engines, exponential on two, and never bounded by the nodes it
reaches.
