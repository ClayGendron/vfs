# R4 — The meeting subgraph and the minimal meeting subgraph

- **Date:** 2026-10-14
- **Researcher:** R4 (vfs graph-traversal study)
- **Scripts:** `scratchpad/experiments/r4_reference.py`, `r4_sql_bfs.py`, `r4_scale.py`, `r4_diag.py`, `r4_diag2.py` (all run with `uv run python` from the vfs repo root; SQLite in memory)

## Summary

The meeting subgraph is a directed-Steiner-tree approximation built from a multi-source BFS. I wrote a pure-Python reference, then moved the BFS into SQL and validated the two against each other on 200 random digraphs. The result is clear. **Ownership (which seed claims a node) is exactly reproducible in SQL**: the rule "nearest seed, ties by seed input order" matched the sequential reference on every node in all 200 trials. **Which bridge edge is chosen when wavefronts meet is a tie-break**, and a set-based Kruskal order differs from the sequential queue order in 71/200 trials; replaying the sequential queue order in Python over the same SQL rows restores parity (200/200 bridge lists). **Directed leaf stripping is a bug in the old semantics**: it deletes the meeting point in the canonical use case (`a -> x <- b`, two files sharing a dependency) and collapsed 73/200 random results to "seeds only" even though a connection was found. Pruning must be undirected, like discovery. At scale (100k nodes, 400k edges, 1,000 seeds), **a single recursive CTE is the wrong shape**: its working table is `nodes × origins` because a recursive CTE has no visited set; it grew to 2.48M rows and 26 s at depth 4. **One statement per hop with a visited table is the right shape**: three statements, 0.77 s, and it stopped at hop 2 because Python's union-find saw all 1,000 seeds joined. No surveyed retrieval system computes a Steiner/meeting subgraph; they all return k-hop unions, one-hop stars, or personalised PageRank. The meeting subgraph is a differentiator, provided its contract is set-based and undirected.

## Findings table

| # | Finding | Evidence | Label |
|---|---|---|---|
| 1 | Ownership by "nearest seed, ties by seed order" is exactly what a sequential FIFO multi-source BFS computes, and SQL reproduces it. | `r4_diag.py`: ownership differs 0/200 | EXECUTED |
| 2 | Bridge choice is a tie-break. Kruskal order over meeting edges differs from queue order in 71/200; queue-order replay in Python over the same rows: 200/200 identical bridge lists, 198/200 identical pre-strip sets (2 parent tie-breaks). | `r4_diag.py`, `r4_diag2.py` | EXECUTED |
| 3 | Directed leaf stripping erases the meeting point of `a -> x <- b` and `a -> x -> y <- b`; it collapsed 73/200 random results to seeds only. | `r4_diag2.py` part B; `r4_diag.py` | EXECUTED |
| 4 | A recursive CTE with `UNION ALL` and a parent column enumerates walks, not nodes; 200 tiny trials did not finish in 120 s. | first `r4_sql_bfs.py` run, killed | EXECUTED |
| 5 | A recursive CTE with `UNION` over `(node, origin, ord, depth)` is bounded but its working table is `nodes × origins`: 8.9k / 67k / 428k / 2.48M rows at depth 1/2/3/4 for 1,000 seeds; 1.9 / 2.6 / 5.8 / 26 s. | `r4_scale.py` A | EXECUTED |
| 6 | One statement per hop with a `visited` table: 7.5k new nodes at hop 1, 38k at hop 2, all 1,000 seeds connected after hop 2, 0.77 s total, 999 bridges. | `r4_scale.py` B | EXECUTED |
| 7 | "Stop when all seeds are connected" cannot be expressed inside one recursive CTE on any of our engines (no cross-iteration aggregate); it needs an app-side loop or a per-dialect procedure. | SQL standard recursion semantics; SQLite/Postgres docs | READ |
| 8 | The old native functions (PL/pgSQL, T-SQL) copied the **entire** edge table into a temp table per call and popped one queue node per loop iteration. | `src2/vfs/backends/postgres.py:209-228,267-284`; `src2/vfs/backends/mssql.py:77-101,167-183` | READ |
| 9 | networkx `steiner_tree` (Kou, Mehlhorn) and rustworkx `steiner_tree` are undirected-only, metric-closure based; Mehlhorn's first step is exactly our ownership partition (nearest terminal per node). | networkx `steinertree.py:9,65-72,105-125,173`; rustworkx `steiner_tree.rs:309-381,527-581` | READ |
| 10 | No surveyed retrieval system computes a Steiner/meeting subgraph. HippoRAG and KAG run PPR; graphrag, LightRAG, youtu-graphrag take one-hop stars; graphiti and cognee take k-hop unions (depth ≤ 3, 1). | Part B citations | READ |
| 11 | The tombstone rule holds in the SQL walk: a hidden intermediary is absent and nothing is reached through it (the walk routed around it). | `r4_sql_bfs.py` tombstone check | EXECUTED |

## Part A — algorithms

### networkx (READ; `~/Git/Repos/networkx`, BSD-3)

- `networkx/algorithms/approximation/steinertree.py:9` and `:173` — both `metric_closure` and `steiner_tree` carry `@not_implemented_for("directed")`. Undirected only.
- Kou (`:105-146`): one single-source Dijkstra per terminal, complete graph on terminals weighted by distance, MST, expand each MST edge to its path, MST again, then `_remove_nonterminal_leaves` (`:149-164`). Docstring `:188`: O(|S| |V|²). Requires a connected graph (`:114-116`).
- Mehlhorn (`:65-102`): one `multi_source_dijkstra` from all terminals (`:66`), records for each node its nearest terminal `s[v] = paths[v][0]` (`:71`) — this is the Voronoi/ownership partition. Then for every edge `(u, v)` with different owners it proposes a terminal-to-terminal edge weighted `d(u) + w + d(v)` (`:77-84`), MST on that, expand, MST again, strip non-terminal leaves. Docstring `:193`: O(|E| + |V| log |V|). Supports multiple components if every component holds a terminal (`:243-244`).
- `_remove_nonterminal_leaves` (`:149-164`) is **undirected degree-1 stripping** to a fixed point. Note the contrast with the old vfs rule (directed in-or-out zero).
- `articulation_points` (`components/biconnected.py:264-334`) — iterative Hopcroft–Tarjan, undirected only (`:337` decorator). The DFS keeps `discovery` and `low`; a parent is an articulation point when `low[child] >= discovery[parent]` (`:375`); the root when it has more than one DFS child (`:390-393`).
- `ego_graph` (`generators/ego.py:11-66`): single centre, `radius`, `undirected=True` folds both directions (`:46-56`), returns the induced subgraph. This is `neighborhood`, not a meeting.
- `bfs_layers` (`traversal/breadth_first_search.py:430-479`): multi-source, yields layers, no origin tracking. `multi_source_dijkstra` (`shortest_paths/weighted.py:651`) returns distance and path per node; path[0] is the origin seed — the origin-tracking idea.
- `voronoi_cells` (`algorithms/voronoi.py:10-86`): literally `multi_source_dijkstra_path` then `nearest = {v: p[0]}` (`:76-78`); "unreachable" bucket for the rest (`:83-85`). Our ownership map is a Voronoi partition with a deterministic tie-break.

### rustworkx (READ; `~/Git/Repos/rustworkx`, Apache-2.0)

- `rustworkx-core/src/steiner_tree.rs:527-581` — `steiner_tree`: Mehlhorn. `fast_metric_edges` (`:309-438`) adds a dummy node joined to every terminal (`:350-353`), runs one Dijkstra from it (`:366-372`), and `partition[u]` is the terminal closest to `u` (`:376-381`). Then for each graph edge with different partitions it emits a terminal pair with the concatenated path (`:385-423`). Kruskal with union-find (`:547-560`); returns `None` if the terminals are not all connected (`:562-564`). Undirected only (`GraphProp<EdgeType = Undirected>` on `metric_closure`, `:209`).
- `rustworkx-core/src/connectivity/biconnected.rs:201-215` — `articulation_points`; the same DFS yields `bridges` (`:245-258`). Undirected only (`:206`).
- `rustworkx-core/src/traversal/bfs_visit.rs:169-188` — `breadth_first_search` runs the starts **sequentially**: each start's BFS exhausts before the next begins (the loop at `:179-186` calls `bfs_visitor` per start on a shared `discovered` map). This confirms the 2026-03-03 memo's finding: no interleaved wavefronts, so no origin tracking. `bfs_layers` (`:251-283`) is interleaved but drops origins.
- What a vfs Rust kernel could mirror: Mehlhorn's partition-then-Kruskal shape, union-find, Hopcroft–Tarjan. The data a kernel would receive from SQL is small (the visited rows and the meeting edges: 46k rows and 62k meets at 1,000 seeds in the probe), so Python handles it today; a kernel is an optimisation, not a necessity.

### vfs's own prior work (READ)

- `context/research/2026-03-03-graph-memory-and-meeting-subgraph.md` — in-memory design: multi-source BFS over `neighbors_undirected()`, origin by first claim, bridge on cross-owner touch, union-find until one component, backtrack both bridge ends, **directed** leaf stripping. 130 ms at 1M nodes in-process. Key correct observation there: `steiner_tree` is undirected-only and runs k Dijkstras.
- `context/research/2026-04-22-mssql-native-meeting-subgraph.md` — T-SQL port of the PL/pgSQL. Its one real semantic decision: bridge parity via `ROW_NUMBER() OVER (PARTITION BY component ORDER BY neighbor)` so one bridge per cross-component per frontier step.
- `context/specs/archive/004-postgres-native-meeting-subgraph/spec.md` "Method-Specific Semantics": undirected discovery, deterministic ownership (seed input order, then stable path order), backtrack along the predecessor tree, **directed** leaf stripping; returns nodes plus edge entries for surviving edges; zero seeds → empty; one seed → that seed only; unknown seeds ignored; disconnected seeds both survive.
- `src2/vfs/graph/rustworkx.py:606-668` (`_meeting_subgraph_impl`) — the Python original. `:585-589`: `len(valid_seeds) <= 1` returns the seeds as nodes only, no edges. `:628`: loop while `queue and uf.components > 1`. `:636-638, 644-646`: bridge recorded on a cross-component touch, then union. `:650-656`: backtrack both ends to the seed. `:671-704` `_strip_leaves`: a non-protected node with no kept successor **or** no kept predecessor is removed — directed. `:303-320` `_subgraph_entries`: returns node entries plus one projected edge entry per surviving directed edge.
- `src2/vfs/graph/rustworkx.py:706-813` (`min_meeting_subgraph`) — builds an undirected `PyGraph` over the kept set (`:772-787`), then repeatedly removes one non-seed, non-articulation node and recomputes articulation points (`:790-803`). It does not re-strip leaves afterwards, but a degree-1 node is never an articulation point, so leaves go anyway. It short-circuits when `len(node_set) <= len(candidate_paths)` (`:738`).
- The native functions. `src2/vfs/backends/postgres.py:141-419` and `src2/vfs/backends/mssql.py:62-330`. Both **copy every live edge into a temp table** (`postgres.py:209-223`, `mssql.py:77-91`) and build a full undirected adjacency table (`:225-228`, `:98-101`) on every call, then pop **one queue node per outer iteration** (`postgres.py:275-284`, `mssql.py:174-183`). That is O(E) per request regardless of seed count, plus one round of statements per visited node. The 2026-04-22 memo's "set-based rewrite" made the inner neighbour scan set-based, not the outer loop. Leaf stripping is a set-based `DELETE ... WHERE NOT EXISTS` loop (`postgres.py:370-397`) — that part is the right shape.

## Part B — how retrieval and agent-memory systems connect seeds (READ)

| System | Primitive | Parameters | Steiner/meeting? |
|---|---|---|---|
| HippoRAG (`src/hipporag/HippoRAG.py:2177-2218`) | Personalised PageRank with the seed phrases and passages as the reset vector; igraph `prpack`, `directed=False` (`:2208`), `damping=0.5` default (`:2179`). Linking map trimmed to top 30 (`:2104-2105`); `passage_node_weight=0.05` (`:2013`). | `linking_top_k`, `damping`, `passage_node_weight` | No. Returns every passage ranked; no subgraph. |
| graphrag (`packages/graphrag/graphrag/query/input/retrieval/relationships.py:14-54`, `context_builder/local_context.py:232-317`) | "In-network" = edges with both ends in the selected entity set; "out-network" = edges with one end in it, ranked by `rank`/`weight`, budget `top_k_relationships × |entities|` (`:316`). One hop. | `top_k_relationships` (10), `relationship_ranking_attribute` | No. One-hop star union, plus in-network edges — the only "connect the seeds" signal is the in-network filter, zero hops. |
| LightRAG (`lightrag/operate.py:6200-6260`, `:6260-6330`) | Vector top-k entities, then `get_nodes_edges_batch` — all incident edges of each seed, deduped, sorted by `(degree, weight)`. One hop. | `top_k` | No. One-hop union. |
| graphiti (`graphiti_core/search/search_utils.py:67,480-560,805-850,1793-1855`) | Cypher variable-length `*1..{bfs_max_depth}` from `bfs_origin_node_uuids`, `MAX_SEARCH_DEPTH = 3` (`:67`), `LIMIT $limit`; `node_distance_reranker` scores only direct `RELATES_TO` adjacency to one `center_node_uuid` (`:1813-1817`), everything else is `inf` (`:1838-1839`). | `bfs_max_depth`, `limit`, `center_node_uuid` | No. k-hop union with a hard row limit; the "distance" reranker is one hop. |
| cognee (`cognee/infrastructure/databases/graph/graph_db_interface.py:1007-1029`; `modules/retrieval/utils/brute_force_triplet_search.py:61,144-146`) | `get_neighborhood(node_ids, depth=1, edge_types)` — k-hop union around up to `neighborhood_seed_top_k=10` seeds; adapters implement it, default view caps nodes in Python. | `depth`, `max_nodes`, `edge_types` | No. k-hop union. |
| KAG (`kag/common/tools/graph_api/graph_api_abc.py:53,66`; `kag/common/tools/algorithm_tool/chunk_retriever/ppr_chunk_retriever.py:99-103`) | `get_entity_one_hop(entity)` → `OneHopGraphData` with `in_relations`/`out_relations` (`kag/interface/common/model/retriever_data.py:413`); plus `calculate_pagerank_scores(start_nodes, top_k)` in the graph store. | `top_k` | No. One-hop star and PPR. |
| youtu-graphrag (`models/retriever/enhanced_kt_retriever.py:747-759`) | `_get_one_hop_triples_from_nodes` — triples incident to the top nodes, truncated to `top_k`. | `top_k` | No. One hop. |
| mem0 | **Graph memory was removed from OSS** in v3; it is a Platform-only feature (`docs/migration/oss-v2-to-v3.mdx:19,41`). The clone at `d26ba5e` (2026-10-12) has no `graph_memory.py` and no related-node Cypher. Docs claim "multi-hop recall" (`docs/platform/features/graph-memory.mdx:13,41`). | — | [NOT VERIFIED: code not in the OSS clone] |

Conclusion for Part B: every system expands around seeds; **none joins them**. The meeting subgraph is an oddity in the sense that nobody else ships it, and a differentiator in the sense that "show me the structure that connects these k files" is a question none of them can answer. The closest cousins are graphrag's in-network filter (zero hops) and Mehlhorn's partition step (the algorithm, not a product).

## Part C — executed prototype

### C1. Pure-Python reference (`r4_reference.py`)

Design: one FIFO queue seeded in input order; neighbours scanned in sorted id order; a node is owned by the first wavefront to reach it; a cross-owner touch is a bridge and unions the owners; stop when one component or the queue empties; keep = seeds + backtracks; directed leaf strip to a fixed point. `min_` recomputes Hopcroft–Tarjan articulation points on the undirected kept subgraph after each single removal (lowest id first), then re-strips. Hand graph: `1->2->3->4`, `2->5->3` (a cycle), `3->6` and `9->1` (spurs), `7->8` disconnected; seeds `[1, 4, 8]`.

```
meeting_subgraph
  bridges     : [(2, 3)]
  kept nodes  : [1, 2, 3, 4, 8]
  kept edges  : [(1, 2), (2, 3), (3, 4)]
min_meeting_subgraph
  kept nodes  : [1, 2, 3, 4, 8]
  kept edges  : [(1, 2), (2, 3), (3, 4)]
single seed  : ({1}, set(), [])
no seed      : (set(), set(), [])
depth=1      : [1, 2, 3, 4]
depth=2      : [1, 2, 3, 4]
```

The cycle's second route (5) and both spurs (6, 9) are stripped. The disconnected seed 8 survives alone. With `depth=1` the seeds `[1, 4]` still meet because 2 (owned by 1) and 3 (owned by 4) touch at the boundary — meetings at the frontier edge count; expansion past it does not.

### C2. SQL walk + Python finish (`r4_sql_bfs.py`)

Tables shaped like vfs: `vfs_entries(id, path, deleted_at)`, `vfs_edges(id, source_id, target_id, edge_type)` with the `fwd`/`rev` indexes. The one statement:

```sql
WITH RECURSIVE
seeds(node, ord) AS (VALUES ...),
und(a, b) AS ( live edges both ways, both endpoints deleted_at IS NULL ),
walk(node, origin, ord, depth) AS (
    SELECT node, node, ord, 0 FROM seeds
    UNION
    SELECT u.b, w.origin, w.ord, w.depth + 1 FROM walk w JOIN und u ON u.a = w.node
    WHERE w.depth < :depth
),
claim AS ( one row per node: ROW_NUMBER() OVER (PARTITION BY node ORDER BY depth, ord) = 1 ),
parent AS ( MIN(neighbour id) among same-origin claims at depth - 1 )
SELECT 'claim', node, origin, depth, parent FROM claim ...
UNION ALL
SELECT 'meet', source_id, target_id, depth_s, depth_t FROM vfs_edges JOIN claim cs JOIN claim ct WHERE cs.origin <> ct.origin
```

Python then sorts the meets by `(min depth, max depth, owner ords, ids)`, accepts them with union-find (Kruskal), backtracks along `parent`, and strips leaves.

**First attempt, a lesson.** The first version carried `parent` in the recursion under `UNION ALL`. On 20–60-node graphs with cycles it did not finish 200 trials in 120 s and was killed. A recursive CTE has no visited set, so `UNION ALL` enumerates every walk; `UNION` dedupes only identical rows, and a changing `depth` column makes every lap of a cycle a new row. The recursion must carry as few columns as possible and must be depth-bounded. Even then it is `nodes × origins` (see C3).

Output:

```
hand graph         -> ['1', '2', '3', '4', '8'] [('1', '2'), ('2', '3'), ('3', '4')]
tombstone 2 hidden -> ['1', '3', '4', '5'] [('1', '4'), ('4', '5'), ('5', '3')]
nothing hidden     -> ['1', '2', '3'] [('1', '2'), ('2', '3')]
trials=200 depth_bound=12 elapsed=1.8s
identical kept-set: 155 (77.5%)
disagreements: 45; same seed-connectivity: 8; same size: 3
  trial 1: n=55 m=123 seeds=[36, 15] |ref|=2 |sql|=4 same_groups=False only_ref=[] only_sql=[30, 32]
  trial 2: n=57 m=133 seeds=[53, 0, 19, 18, 13, 27] |ref|=7 |sql|=8 same_groups=True only_ref=[] only_sql=[38]
  trial 6: n=27 m=56 seeds=[16, 22, 8, 13] |ref|=6 |sql|=5 same_groups=False only_ref=[10] only_sql=[]
  ...
```

The tombstone row: with node 2 hidden the walk routes `1 -> 4 -> 5 -> 3`; with nothing hidden it takes `1 -> 2 -> 3`. Hidden rows are absent and nothing is reached through them, with no special code — the liveness join on both endpoints does it.

**Why 45 disagree** (`r4_diag.py`):

```
trials: 200
ownership differs (over nodes the reference claimed): 0
bridge edge set differs: 71
pre-strip kept set differs: 71
post-strip (directed) kept set differs: 45
post-strip (undirected) kept set differs: 71
reference: directed strip collapsed a found path to seeds only: 73
sql:       directed strip collapsed a found path to seeds only: 71
first cause of each post-strip disagreement: {'bridge choice': 44, 'parent choice': 1}
```

So:

- **Ownership is exact.** "Nearest seed, ties by seed input order" is the sequential first-claim rule. Proof sketch: level 0 of the queue is in seed order; each level is emitted by scanning the previous level in order and a child inherits its parent's owner, so every level stays grouped by owner ord. A node at distance d is therefore claimed by the lowest-ord seed at distance d. SQL can compute this with a window function. This is the part that is *not* "a CTE's nondeterministic first claim" — it is fully determined.
- **Bridge choice is a tie-break.** The sequential code records the first cross-owner touch in dequeue order. Kruskal by `(min depth, max depth, ords, ids)` picks an equally-short but sometimes different edge in 71/200. Both are valid spanning forests over the same meeting edges; the seeds' connectivity is the same (bridge choice never changes *which* seeds join). The post-strip differences (45) are fewer than the pre-strip ones (71) only because directed stripping wiped 73 reference results down to the seeds, hiding the difference.
- **Exact parity is reachable if wanted** (`r4_diag2.py` part A): assigning queue positions in Python (`depth`, then parent position, then id) and replaying bridge detection in that order over the same SQL rows gives `bridge lists identical 200/200`, `pre-strip kept identical 198/200`; the last 2 are the parent rule (min id vs. first-dequeued). So the SQL rows carry enough to reproduce the sequential algorithm bit-for-bit; the question is only which rule we *declare*.

**Directed stripping is wrong** (`r4_diag2.py` part B):

```
B. a->x<-b, seeds [a,b]
   directed strip  : ['a', 'b'] [] bridges [('b', 'x')]
   undirected strip: ['a', 'b', 'x'] [('a', 'x'), ('b', 'x')]
   a->x->y<-b directed strip: ['a', 'b'] []
```

Two files importing the same module is the canonical meeting. Directed stripping removes the module (out-degree 0 in the kept set) and returns the two seeds with no edges, as if they were unrelated. Discovery is undirected; pruning must be too (networkx's `_remove_nonterminal_leaves` is undirected degree-1 stripping for the same reason). This was latent in the archived spec: its acceptance test "a non-seed dangling spur that has no kept in-neighbor **or** no kept out-neighbor ... is stripped" encodes the bug.

### C3. Scale probe (`r4_scale.py`): 100k nodes, 400k edges (80% local within ±50 ids), 1,000 seeds

```
built N=100000 M=400000 in 1.6s
A. single recursive CTE (UNION over (node, origin, ord, depth)), 1,000 seeds
   depth | walk rows | distinct nodes | claim+meet rows | meets | seconds
       1 |      8912 |           8513 |           11031 |  2518 | count=1.09 full=1.85
       2 |     67465 |          46649 |          111168 | 64519 | count=1.18 full=2.64
       3 |    427843 |          95980 |          343595 | 247615 | count=2.17 full=5.78
       4 |   2482199 |          99944 |          362545 | 262601 | count=9.55 full=25.98
B. one statement per hop, app-side union-find between hops
   hop | new nodes | visited | meets this hop | seed components | seconds
     0 |      7513 |    8513 |             38 |             962 | 0.09
     1 |     38136 |   46649 |           2480 |              39 | 0.25
     2 |         - |   46649 |          62001 |               1 | 0.42  <- all seeds connected, stop
   bridges=999 total=0.77s
```

Reading it:

- **The working table is the cost driver, and it is `nodes × origins`, not nodes.** By depth 3 the walk has touched 96% of the graph (95,980 distinct nodes) but holds 428k rows; by depth 4 it holds 2.48M rows for 99,944 nodes — 25 rows per node, one per seed wavefront that reaches it within the bound. A recursive CTE cannot say "this node is already claimed" because it cannot read its own earlier iterations except through the recursive member's one row. Also, the `claim`/`meet` output stops growing (343k → 362k) while the walk grows 6× — all that work is discarded.
- **The per-hop loop is bounded by what matters.** Its `visited` table holds one row per node (46,649 after hop 2) because `NOT EXISTS (SELECT 1 FROM visited ...)` is a real visited set. The meets at hop 2 (62,001 rows) are the only large output and they are exactly the Mehlhorn candidate edges; union-find over them in Python took well under the 0.42 s shown.
- **Early stop.** The loop stopped after hop 2 because the 1,000 seeds collapsed to one component. The single CTE has no such exit; it must run to its bound. With locality, 1,000 seeds in 100k nodes meet within two hops — a depth bound of 4 does 30× the useful work.
- **Can "stop when all seeds are connected" live in SQL?** Not inside one recursive CTE on any of our engines: the recursive member sees only the previous iteration's rows, never an aggregate over the whole working table, and the standard forbids aggregates and window functions in the recursive term (SQLite, Postgres, MariaDB, SQL Server and Oracle all enforce this). The alternatives are (i) a fixed radius (what the CTE gives: cheap to write, wrong cost profile), (ii) an app-side loop of one statement per hop with the union-find check between hops (what B does; three to five round trips in practice), or (iii) a stored procedure per dialect (what `src2` did; five bodies to maintain and the old ones were O(E) per call anyway). [NOT VERIFIED on Postgres/MariaDB/SQL Server/Oracle: the row counts were measured on SQLite only; the `nodes × origins` growth is a property of the recursion, not the engine.]

## Part D — recommendation

### (a) The SQL/engine split

Three phases, three shapes:

| Phase | Shape | Why |
|---|---|---|
| Seed resolution: paths → ids, visibility, liveness | one statement (chunked by `membership_budget`) | existing `visible_entries` machinery; 10k seeds is 10 chunks on Oracle |
| Multi-source BFS: claim one hop | **one statement per hop**: `INSERT INTO <visited> SELECT ... ROW_NUMBER() OVER (PARTITION BY neighbour ORDER BY ord, parent) ... WHERE NOT EXISTS (visited)`, then `SELECT meets touching this hop` | the visited table is the only thing that keeps the working set at `nodes`, not `nodes × origins`; the rights and liveness predicates are plain joins in the hop statement; the frontier is the previous hop's rows so no `IN` list grows with the batch |
| Union-find across hops, early stop | Python between hops | O(meets α) on a few thousand to tens of thousands of rows; decides whether to issue the next hop |
| Backtrack, leaf strip, articulation pruning | Python (or later a Rust kernel) on the kept rows | the kept set is small (hundreds to low thousands); leaf stripping and Hopcroft–Tarjan are linear; the old PL/pgSQL `DELETE ... WHERE NOT EXISTS` loop would also work but gains nothing |
| Edge observations for the kept set | one statement: `SELECT ... FROM vfs_edges WHERE source_id IN (kept) AND target_id IN (kept)`, chunked | returns `edge_type`, `weight`, `distance` for the surviving edges |

The visited table is per-call scratch. On engines with session temp tables (all five) it is a temp table; on SQLite in tests it is a `TEMP TABLE` in the connection. If the backend prefers no DDL on the request path, the hop statement can instead carry the visited set as a bound `VALUES`/array list — but that reintroduces a statement that grows with the visited count, which breaks the boundedness rule once visited exceeds the `IN` budget. A temp table is the honest choice. Each hop statement is a fixed size.

The recursive CTE still has a place: for a **fixed-radius** `neighborhood` around a few seeds it is one round trip and the `nodes × origins` blow-up is harmless when origins are few. It is the wrong tool for the meeting subgraph at 1,000+ seeds.

A Rust kernel for the post-SQL phase is allowed but not needed yet: the Python finish (union-find, backtrack, strip, articulation points) ran in milliseconds on 62k meets. Reserve the kernel for when a profile shows the Python finish dominating.

### (b) `min_meeting_subgraph`: a parameter, not a method

Make it `minimal: bool = False` on `meeting_subgraph` (or a `prune` enum if a third level ever appears). Reasons: it is the same traversal with one extra pruning pass on the same small kept set; it shares every parameter and every return shape; as a separate method it doubled the vocabulary, the dispatch and the tests in `src2` and still needed `meeting_subgraph` underneath (`rustworkx.py:722`). Do not drop it: on the hand graph it changes nothing, but on a kept set that contains a cycle (two equally short routes both backtracked from different bridges) the articulation pass removes the redundant route, and that is the "minimal" a caller asks for. Define it precisely: after undirected leaf stripping, repeatedly remove the lowest-id non-seed node that is not an articulation point of the undirected kept subgraph, re-strip, until none remains. Deterministic and cheap (the kept set is small; recomputing Hopcroft–Tarjan per removal is O(k·(n+e)) on n in the hundreds).

### (c) What the verb returns

Nodes **and** the surviving edges, as `Observation`s: one per kept node (`path`, kind, the usual columns), and one per surviving edge with `path` = source, `edge_target`, `edge_type`, `edge_weight`, `edge_distance` populated (`src/vfs/models/entry.py:434-437`). The archived contract already returned edges (as projected edge paths); the new model has first-class fields for them, so no synthetic path is needed. Without edges the caller cannot tell `a -> x <- b` from `a -> x -> b`, which is the whole point of the verb. Order: nodes first by path, then edges by (source path, edge_type, target path), so the result is stable for tests.

Two switches the contract must fix now: discovery is undirected over **all** edge types including `fs` (a shared parent directory is a legitimate meeting point; the caller can exclude types if an `edge_types` filter lands), and pruning is **undirected** degree-1 stripping, never the directed rule.

### (d) Single-seed and no-seed cases

- No seed resolved (empty input, or every seed hidden/tombstoned/unknown): empty successful result. Hidden and unknown are indistinguishable by design (hidden rows are absent).
- One seed resolved: that seed as a single node observation, no edges. Matches `src2` (`rustworkx.py:585-589`) and the archived spec. Do not silently turn it into a `neighborhood`; the caller asked to connect seeds and there is nothing to connect.
- Seeds in different components: each survives as a node; no edges between them; no error. The caller can read "k seeds, fewer than k-1 bridges" as "not all connected" if the result carries a count, which is worth exposing (a `components` number in the result's summary, not on observations).
- `depth`: the expansion radius per seed, so two seeds `2·depth + 1` apart can still meet at the boundary (C1 output: `depth=1` connects seeds three edges apart). With no depth the loop runs until the frontier empties or all seeds join. Because the per-hop loop stops early anyway, a default depth is a safety bound (the entries table's own height is a natural one for `fs`-only graphs), not a tuning knob.

### (e) Where the rights predicate rides

In the hop statement, on the **neighbour** endpoint: the join from frontier `f` to the live undirected edge view yields candidate `u.b`; the visibility predicate (R3's form: the `visible_entries` join or the literal OR of path terms) filters `u.b` before the `ROW_NUMBER` claim. A node the caller may not see is therefore never claimed, never enters `visited`, and never becomes a frontier row, so nothing is reached through it — the same mechanism that routed the tombstone check around node 2. The seed-resolution statement applies the predicate to the seeds themselves, so a hidden seed is simply "not resolved" and falls into (d). The meets statement needs no predicate: both endpoints are already in `visited`. The final edge-observation statement needs none either, for the same reason. One predicate, one place per hop, and the liveness term (`deleted_at IS NULL` on the neighbour row) sits beside it.

## Open questions

1. Which bridge tie-break to declare: set-based `(meeting depth, seed order, ids)` (natural in SQL, differs from the old sequential accident in a third of random cases) or queue-order replay (exact parity, needs the position assignment in Python). I recommend the set-based rule and a test pinned to it; the old Python order was never a contract.
2. Whether to expose `edge_types` on `graph` so a caller can exclude `fs` from the meeting (a shared root directory meets everything). R1/R2 own the vocabulary; this memo only notes that `fs` edges will dominate meetings unless filtered.
3. The temp-table choice on the request path versus a per-call `VALUES` list for the visited set. The former is bounded; the latter is not once `visited` passes the `IN` budget. A dialect note on temp-table DDL permissions (Oracle global temporary tables are created once; SQL Server `#t` is per session) belongs to whoever lands the backend.
4. Postgres/MariaDB/SQL Server/Oracle row counts for the per-hop shape were not measured; only SQLite was. The shape's cost model (one row per visited node, one meet row per cross-owner edge) is engine-independent, but the window-function claim step should be run once on each engine's leg.
