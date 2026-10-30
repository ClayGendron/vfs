# R5 — The `graph` verb's vocabulary, parameters and row shape

Researcher R5, 2026-10-14. Reference clones under `~/Git/Repos` (refreshed 2026-10-13), read-only. Evidence labels: **[EXECUTED]** I ran it; **[READ]** I read it at the cited line; **[SURVEY]** a delegated read-only survey of the agent-consumer repos, of which I spot-checked three citations **[EXECUTED]**; **[WEB]** an engine doc fetched by URL; **[INFERRED]** my reasoning.

## Summary

The field does not name walks by degree. `in_degree` / `out_degree` are *counts* everywhere (networkx, rustworkx, Gremlin's `Direction` enum never uses them), and vfs's own `Observation` already carries `in_degree: int | None` and `out_degree: int | None` as ranking **counts** (entry.py:446-447), so that pair would collide inside the very rows the verb returns. The field's direction words are relative to a *point of view* (Gremlin `in()/out()/both()`, neo4j `INCOMING/OUTGOING/BOTH`, AGE's function API `"in"/"out"/"any"`) or relative to the *stored arrow* (networkx `bfs_edges(reverse=)`, cognee `forward/reverse/both`, AGE's internal `DIR_RIGHT/LEFT/NONE`). The arrow-relative pair is the one an LLM cannot misread, because vfs already names the arrow: `mkedge source → target`. I recommend a closed `GRAPH_METHODS = {"forward", "reverse", "both", "connect", "connect_min"}` with `depth` (default 1, `None` = reachability), `edge_types` / `edge_types_not`, and `limit` (default 100, `None` = all). Every answer is node rows (with a new `depth` query field, seeds at depth 0) plus edge rows in the exact shape `mkedge` already returns (`path`=source, `edge_target`, `edge_type`, `edge_weight`, `edge_distance`); a depth-1 `forward`/`reverse` walk's edge rows *are* ADR 016's deferred `edges(path, direction, type)` verb, so that verb needs no separate name. Truncation rides the existing `ErrorKind.truncated` warning that glean already emits. One `graph` tool, one `method` enum, as today.

## Findings table

| # | Finding | Evidence |
|---|---|---|
| 1 | No surveyed system names a neighbour set `in_degree`/`out_degree`; those are counts. vfs's `Observation` already has both as count fields. | networkx `DiGraph.in_degree` is a view of counts; vfs entry.py:446-447, ranking.py:225 [READ] |
| 2 | Point-of-view vocabularies need a sentence of explanation in their own docs. | Gremlin Direction.java:22-30, neo4j Direction.java:27-35 [READ] |
| 3 | Arrow-relative vocabularies exist and are used by an agent-facing system today. | cognee code_retriever.py:241-245 `forward/reverse/both` [EXECUTED spot-check]; networkx `bfs_edges(reverse=)` :109 [READ]; AGE cypher_nodes.h:159-161 [READ] |
| 4 | Unbounded depth is allowed by Gremlin, Cypher, apoc (-1), AGE (-1), DuckPGQ (int64 max); **refused** by Kuzu/Ladybug (omitted upper bound = config default 30, exceeding it is a bind error); clamped by cognee (20). | tinkerpop docs 3135-3137; apoc [WEB]; age_vle.c:3522; duckpgq grammar :131,146; ladybug client_config.h:50, bind_graph_pattern.cpp [READ]; cognee [SURVEY] |
| 5 | Unbounded is only safe with **node-global uniqueness** (a visited set). Path enumeration without it is O(E!) on cycles. | age_vle.c:49-54 [READ]; neo4j Uniqueness.java:33 NODE_GLOBAL; apoc default NODE_GLOBAL [WEB] |
| 6 | Seeds: networkx/rustworkx/old-vfs exclude for directional walks; ego_graph, apoc (minLevel 0), cognee (depth 0), LightRAG, old-vfs `neighborhood` include. | networkx dag.py:60; ego.py:11; spec 004 §Method-Specific; cognee :1519 [EXECUTED] |
| 7 | Node rows + edge rows is the mature "subgraph" answer; cognee includes only edges with both endpoints returned; apoc `subgraphAll` yields `(nodes, relationships)`. | cognee :1556-1560 [SURVEY]; apoc [WEB] |
| 8 | Agent consumers bound answers with a count cap **and** a truncation flag (`truncated`, `is_truncated`); graphiti has neither and its `max_nodes` silently caps at 10. | cognee stats, LightRAG types.py:66 [EXECUTED]; graphiti server :542,600 [EXECUTED] |
| 9 | vfs already has the truncation convention: `ErrorKind.truncated` at `Severity.warning` with `data`. | glean.py:404-415 [READ] |
| 10 | Today an edge-shaped row under `graph`'s default projection renders as a blank duplicate of its source path. There is no `depth` field on `Observation`. | [EXECUTED], see §C.4 |
| 11 | No live backend implements `SupportsGraph`; the archived impl returned node rows for walks and node+edge rows (as the retired `__meta__` path grammar) for `neighborhood`. | protocol.py:326-337; src2 rustworkx.py:296-320, 512-568 [READ] |
| 12 | One tool + enum and many-tools both exist. The one anti-pattern is an enum nested inside a dict argument (cognee `code_query.operation`), which hides parameters from the schema. | [SURVEY] |

---

## Part A — naming prior art

### Gremlin (tinkerpop) [READ]
- `Direction` enum: `OUT`, `IN`, `BOTH`; `proper = {OUT, IN}`; aliases `from = OUT`, `to = IN`, and `directionValueOf("to"/"from")` (`gremlin-core/.../structure/Direction.java:35-98`). The javadoc needs an example to explain which is which: "gremlin--knows-->rexster is an OUT edge for Gremlin and an IN edge for Rexster" (:22-30). The `from`/`to` aliases are the project's own admission that `IN`/`OUT` read poorly.
- Steps: `out()`, `in()`, `both()` map to adjacent *vertices*; `outE()`, `inE()`, `bothE()` to *edges*; each takes `edgeLabels...` as the type filter (`GraphTraversal.java:541-820`). Depth is `repeat(...).times(n)` or `until(pred)`; `emit()` returns intermediate hops; `simplePath()`/`cyclicPath()` (:3596-3608, 4404-4502). `limit(n)` (:3371).
- Unbounded: a `repeat()` with neither `times()` nor `until()` "terminates on its own once `out()` produces no further traversers"; the loop counter is capped at 2,147,483,647 (`docs/src/reference/the-traversal.asciidoc:3135-3140`). Not a visited set: on a cycle it runs to the counter cap.

### openCypher and ISO GQL [READ]
- Direction is drawn: `<-[]-`, `-[]->`, `-[]-` (`openCypher/grammar/openCypher.bnf:411-417`). Variable length is `* [lower] .. [upper]` or `*n` (:438-441); "either bound can be omitted"; `*` alone "is equivalent to specifying a minimum of 1" (Neo4j 4.4 manual, `syntax/patterns`, [WEB]). The TCK uses `*1..2` (`tck/features/clauses/match/Match6.feature:305`).
- GQL (`opengql-grammar/GQL.g4`): path modes `WALK | TRAIL | SIMPLE | ACYCLIC` (:907-911): WALK repeats anything, TRAIL no repeated edge, SIMPLE no repeated node except endpoints, ACYCLIC no repeated node. Search prefixes `ALL`, `ANY [n]`, `ALL SHORTEST`, `ANY SHORTEST`, `SHORTEST n` (:914-957). Quantifiers `*`, `+`, `{n}`, `{m,n}` with either bound optional (:1125-1145). Edge-pattern names: `PointingLeft`, `PointingRight`, `Undirected`, `LeftOrUndirected`, `UndirectedOrRight`, `AnyDirection` (:1041-1062).
- Neo4j's current manual warns that quantified paths "can end up matching very large numbers of paths" and suggests "putting a finite upper bound (e.g. `{,10}`)" [WEB].

### networkx [READ]
- `DiGraph.successors(n)` / `predecessors(n)`; `neighbors = successors` (`classes/digraph.py:911-943`).
- `descendants(G, source)` / `ancestors(G, source)` — transitive, **source excluded** ("The source node is not a descendant of itself", `algorithms/dag.py:36-73`).
- Within k hops: `bfs_edges(G, source, reverse=False, depth_limit=None)` and `bfs_tree(...)` (`traversal/breadth_first_search.py:109,198`); `descendants_at_distance(G, source, distance)` (exactly k, :564); `single_source_shortest_path_length(G, source, cutoff=None)` returns `{node: distance}` (`shortest_paths/unweighted.py:22`); `bfs_layers(G, sources)` is multi-seed (:430).
- `ego_graph(G, n, radius=1, center=True, undirected=False)` — the one function with a **centre-inclusion flag** and an undirected switch; on a DiGraph it is the *out* neighbourhood unless `undirected=True` (`generators/ego.py:11-35`).
- Naming lesson: networkx says "reverse" for the direction flip and "depth_limit"/"radius"/"cutoff"/"distance" — four words for one idea.

### rustworkx [READ]
- Same nouns: `ancestors`, `descendants` (`src/traversal/mod.rs:258,300`; example at :236-244 shows the node itself excluded), `bfs_successors`/`bfs_predecessors` return `[(parent, [children])]` (:140-203), `digraph_bfs_search` / `graph_bfs_search` with a visitor (:436,582).

### neo4j (GPL — study only) [READ] + apoc [WEB]
- `Direction` enum `OUTGOING`, `INCOMING`, `BOTH`, with `reverse()`; javadoc: "A relationship has a direction from a node's point of view" (`community/graphdb-api/.../Direction.java:27-52`).
- Traversal framework: `relationships(type, direction)`, `breadthFirst()/depthFirst()` (`traversal/TraversalDescription.java:140-172`); depth evaluators `toDepth(n)`, `fromDepth(n)`, `atDepth(n)`, `includingDepths(min,max)`, `excludeStartPosition() = fromDepth(1)` (`Evaluators.java:49-136`); `Uniqueness` `NODE_GLOBAL`, `NODE_PATH`, `RELATIONSHIP_GLOBAL`, `NONE` (`Uniqueness.java:33-163`).
- `apoc.path.subgraphNodes(start, config) :: (node)` — config `minLevel` (-1), `maxLevel` (-1 = unbounded), `relationshipFilter` (`TYPE>` out, `<TYPE` in, `TYPE` both, `>`/`<` any type), `labelFilter`, `limit` (-1), `bfs` (true), `filterStartNode`, `uniqueness` (NODE_GLOBAL), `endNodes`, `terminatorNodes`, `allowlistNodes`, `denylistNodes`. `apoc.path.subgraphAll :: (nodes, relationships)` (https://neo4j.com/docs/apoc/current/overview/apoc.path/apoc.path.subgraphNodes/ and `.../apoc.path.subgraphAll/`). This is the mature neighbourhood API: one start node, a hop range, a typed+directed edge filter, a count cap, global node uniqueness, and nodes-only vs nodes+edges as two procedures.

### Kuzu / Ladybug [READ]
- Cypher grammar with `*` + `SHORTEST | ALL SHORTEST | TRAIL | ACYCLIC | WSHORTEST(prop)` + `lower..upper` (`ladybug/scripts/antlr4/Cypher.g4:764-776`; kuzu :675-683). Direction is drawn, as in Cypher.
- **An omitted upper bound is not unbounded**: it defaults to `varLengthMaxDepth` (`VAR_LENGTH_MAX_DEPTH = 30`, `src/include/main/client_config.h:50,93`) and a larger explicit bound is a `BinderException` ("Upper bound of rel … exceeds maximum", `src/binder/bind/bind_graph_pattern.cpp:663-677`). A hard cap — exactly what vfs's rule forbids *designing toward*; cited as the field's strictest stance, not as a model.

### DuckPGQ (SQL/PGQ) [READ]
- `-[e]->`, `<-[e]-`, `-[e]-` map to `MATCH_EDGE_RIGHT / LEFT / ANY` (`src/core/parser/graph_table_grammar.cpp:114-127`); quantifiers `*`, `+`, `?`, `{n}`, `{m,n}`, `{m,}`, `{,n}`; an omitted upper bound is `int64 max` (:131-146); `ANY SHORTEST`, `ALL SHORTEST`, `SHORTEST k`, and the four GQL path modes are parsed (`docs/GRAMMAR_EXTENSION.md:58-62`).

### Apache AGE [READ]
- Grammar: `*` with optional range (`src/backend/parser/cypher_gram.y:728-729`); direction enum `NONE=0, LEFT=-1, RIGHT=1` (`src/include/nodes/cypher_nodes.h:159-161`).
- A **function-style** API that is the closest cousin of a vfs verb: `age_shortest_path(graph, start, end [, edge_types [, direction [, min_hops [, max_hops]]]])` with `direction` strings `"out"`, `"in"`, `"any"` (`src/backend/utils/adt/age_vle.c:2838-2841, 2957-2967`); `max_hops` default -1 = unbounded (:3522).
- Its own warning: "Unbounded patterns have no termination guarantee other than edge-uniqueness depletion. On a cycle-rich graph the worst case is O(E!)… Users who want reachability (not full enumeration) should bound the upper length" (:49-54). vfs wants reachability, so this is the argument *for* allowing `depth=None` in vfs with node-global uniqueness.

### Jackrabbit Oak (tree store) [READ]
- `PathUtils.getParentPath`, `getAncestorPath(path, nth)` ("the ancestor level"), `getDepth`, `isAncestor(ancestor, path)`, `relativize` (`oak-commons/.../PathUtils.java:105-405`); `Tree.getParent()`, `getChild(name)`, `getChildren()`, `getChildrenCount(max)` (`oak-api/.../Tree.java:146-213`). Hierarchy vocabulary is parent/child/ancestor/ descendant with an integer *level*. On vfs's `fs` edges (parent → child), `reverse` with `depth=n` is Oak's `getAncestorPath(nth)` chain and `forward` is the subtree — the tree words fall out of the arrow words.

---

## Part B — what agents are given [SURVEY, three citations spot-checked EXECUTED]

| Project | Verb(s) | Direction / depth / limit / type params | A row of the answer | Seeds? | Bounding |
|---|---|---|---|---|---|
| graphiti | many MCP tools: `search_nodes`, `search_memory_facts`, `get_entity_edge`, … (`mcp_server/src/graphiti_mcp_server.py:402-1146`) | `center_node_uuid` (re-rank only, 1-hop adjacency, not BFS: `search_utils.py:1793-1852`), `max_nodes=10` (sliced after search, so >10 is silently 10: :542,600), `max_facts`, `entity_types`, `edge_types`; real BFS (`bfs_max_depth`, `MAX_SEARCH_DEPTH=3`, `search_utils.py:67`) is core-only, never on MCP | node `{uuid,name,labels,summary,…}`; fact = full edge dump `{uuid,fact,source_node_uuid,target_node_uuid,valid_at,…}`; **no depth/via** | only if the text search found it | count cap, min score; **no truncation flag** |
| mem0 | graph memory removed from OSS (`docs/migration/oss-v2-to-v3.mdx:19-58`); `search(top_k=20)`, `get_all` | none | memory rows with `score_details` | n/a | `[:top_k]` |
| cognee | one `recall(query, search_type=enum of 20, top_k=15, code_query={operation,…})` (`cognee-mcp/src/server.py:531-587`); code ops `explore/traverse/find_path/impact_analysis` | `direction ∈ {forward, reverse, both}` (:241-245 ✔), `relation_types`, `node_types`, `max_depth` (explore 1/max 2; traverse 5/20; impact 3/10), `max_nodes` (100/500) — all clamped by `_bounded_int` | `{nodes[{id,kind,type,name,depth}], edges[{source_id,source,target_id,target,type}], stats{nodes_visited, edges_traversed, max_depth_reached, truncated}}`; edges only between returned nodes (:1556-1560) | **included at depth 0** (:1519 ✔) | cap + `truncated` flag |
| LightRAG | `QueryParam.mode ∈ {local,global,hybrid,naive,mix,bypass}` (`lightrag/base.py:93`); `get_knowledge_graph(node_label, max_depth=3, max_nodes=1000)` (:1134-1173) over HTTP, no MCP | no direction/type filter; budgets by tokens (`max_entity_tokens` …) | `KnowledgeGraph{nodes[{id,labels,properties}], edges[{id,type,source,target}], is_truncated}` (`types.py:49-66` ✔) | included | cap + `is_truncated` |
| letta | no graph verbs; `memory(command=enum)`; `grep_files` pages 20 at a time with a next offset | — | — | — | paging |
| memori | stores triples; `recall(query, limit)` only; no traversal | — | fact rows | — | limit |
| mirage | `shell, read, write, edit, ls, grep, glob` + optional `vfs_<call>`; **no relation verb**; `explain: bool` dry-run flag on every tool (`server.py:111-125`) | — | — | — | `read limit=2000`, grep `max_count` |
| afs | `afs_list(path, depth=1, limit)`, `afs_search`, `afs_explain(path)` → prose; only relation is `linkTo` | `depth` default 1 | path tree | — | `limit` |
| mcpfs / eve / deepagents | no traversal tool | — | — | — | — |

Ergonomics lessons (from the survey, which I endorse): (1) an enum inside a dict argument hides parameters from the schema — keep every parameter top-level; (2) cap **and** flag; (3) node rows and edge rows are distinct shapes and both are wanted; seeds at depth 0 make the start of the walk legible; (4) keep rows small (strip embeddings, no per-node relation lists); (5) separate "no edges" from "node absent" from "backend error".

---

## Part C — vfs internals that bind the design [READ unless marked]

1. **`ops.py:108-112`** — `GRAPH_METHODS = {predecessors, successors, ancestors, descendants, neighborhood, meeting_subgraph, min_meeting_subgraph}`; one `graph` op in `READ_OPS` (:78); the docstring already says "traversal only … centrality is index-time" (:19-22).
2. **`params.py:286-292`** — `graph: method (str, required, choices=GRAPH_METHODS), path, observations, depth (int, minimum=1, maximum=INT_CEILING, nullable), authority`; shape rule `_ONE_TARGET` (:339-343). House style for the new params is right there: `ext`/`ext_not`, `globs`/`globs_not` as `str_seq, nullable=False, default=()` (:238-243); enums as `choices=` frozensets (:250, 264); `glean limit` as `int, nullable=False, minimum=1, default=10` (:269-277); `tree max_depth` doc "depth budget; None is unbounded" (:134).
3. **`base.py:1493-1516`** — `graph(method, path=None, observations=None, *, depth=None, authority=None)`; the path-or-observations shape means an agent can chain `glean(...)` → `graph(observations=result.observations)`, and `_dispatch_grouped_observations` (:1700-1750) groups seeds by mount and merges with `Result.merge`. Each backend walks only its own subgraph (:1503-1506).
4. **`models/entry.py:393-452`** — `Observation` fields, exactly: `path, kind, content, data, source, render_status, content_hash, mime_type, size_bytes, version, edge_type, edge_target, edge_weight, edge_distance, created_at, updated_at, deleted_at` (mirrors) and `score, matches, in_degree, out_degree, status` (query) plus `populated`. **There is no `depth` field** [EXECUTED: `"depth" in Observation.model_fields` → `False`]. `in_degree`/`out_degree` are counts a ranking signal fills (`storage/ranking.py:225`) and are right-aligned numerics in the renderer (`results/render.py:212-214`). `with_mount`/`without_mount` already rebase `edge_target` beside `path` (:482-498).
5. **Rendering** — `results/render.py` is the text surface; `src/vfs/rendering/` is document→text (docx, pdf), not rows. `graph`'s default projection is `("path", "kind")` (`results/projection.py:58`). [EXECUTED] rendering a node row and an edge row under that default:
   ```
   | path  | kind |
   | /a.md | file |
   | /a.md |      |      ← the edge row: edge_target/edge_type invisible
   ```
   With `projection=("path","edge_type","edge_target","edge_weight")` the edge row renders fully. So edge rows render **today** only when asked for; a graph answer needs its own default projection or renderer.
6. **`storage/backends/database/edges.py:519-528`** — `_observe_edge` returns `Observation(path=edge.source, edge_target=edge.target, edge_type, edge_weight, edge_distance, status)`. This is the edge-row shape the namespace already speaks; a graph edge row should be the same minus `status`.
7. **ADR 016 pin 4** (:113-118) — metadata surfaces "through entry-scoped verbs … `edges(path, direction, type)`"; "the exact verb surface — names, arguments, pagination — is a future interface spec". ADR 018 pin 9 keeps it deferred (:165-172). **ADR 018** pins 5-7: `fs` edges are `parent → child`, one per non-root entry; "`fs` behaving as an ordinary type name callers include or exclude" (Consequences); readers "use the edges table alone". ADR 065: hidden rows are absent from "edge traversals". ADR 059 pin 4: `graph` withheld from unknown dialects (to be revisited by R-other).
8. **Archived semantics** (`context/specs/archive/004-.../spec.md:91-128`): predecessors/successors one hop, ancestors/descendants transitive, seeds "not included unless they are also [reached] via another seed"; `neighborhood` bounded undirected, seed included; `meeting_subgraph` emits "the surviving node set plus … entries for surviving directed edges". `src2/vfs/graph/rustworkx.py:296-320` built those edge entries as `__meta__` edge paths — the grammar ADR 016 retired — and `neighborhood` (:512-568) started `visited` from the seeds. `neighborhood` had `depth: int = 2` (`src2/vfs/graph/protocol.py:106`).
9. **Truncation convention** — `glean.py:404-415` appends `classified(ErrorKind.truncated, severity=warning, detail=f"at the {reason}; …", data={...})` per truncation. `Result` has `ops`, `observations`, `errors` (envelope.py:316+).
10. **No live `SupportsGraph` implementation** — only the protocol (`storage/protocol.py:326-337`); `memory.py` has no `graph`. The vocabulary can change without porting cost.

---

## Part D — proposal

### D.1 Naming table

| Concept | Gremlin | Cypher / GQL | networkx | neo4j traversal / apoc | SQL/PGQ (DuckPGQ) | AGE fn API | cognee | vfs today | **vfs proposed** |
|---|---|---|---|---|---|---|---|---|---|
| one-hop outbound (seed is `source`) | `out()` | `(s)-[]->(x)` | `successors` | `OUTGOING` / `TYPE>` | `-[]->` | `"out"` | `forward`, depth 1 | `successors` | `forward`, `depth=1` |
| one-hop inbound (seed is `target`) | `in()` | `(s)<-[]-(x)` | `predecessors` | `INCOMING` / `<TYPE` | `<-[]-` | `"in"` | `reverse`, depth 1 | `predecessors` | `reverse`, `depth=1` |
| k-hop outbound | `repeat(out()).times(k)` | `-[*1..k]->` | `bfs_tree(depth_limit=k)`; all: `descendants` | `toDepth(k)` / `maxLevel` | `->{1,k}` | `max_hops` | `traverse max_depth` | `descendants` (∞ only) | `forward`, `depth=k` (`None` = ∞) |
| k-hop inbound | `repeat(in()).times(k)` | `<-[*1..k]-` | `bfs_tree(reverse=True)`; all: `ancestors` | same + `INCOMING` | `<-{1,k}` | `"in"`, `max_hops` | `impact_analysis` (reverse) | `ancestors` (∞ only) | `reverse`, `depth=k` |
| k-hop undirected | `repeat(both()).times(k)` | `-[*1..k]-` | `ego_graph(radius=k, undirected=True)` | `BOTH` / `TYPE` | `-{1,k}-` | `"any"` | `explore both` | `neighborhood(depth=2)` | `both`, `depth=k` |
| connect seeds | — | `ANY SHORTEST` per pair | — | `subgraphAll` w/ `endNodes` | `ANY SHORTEST` | `age_shortest_path` | `find_path` (pairwise) | `meeting_subgraph` | `connect` |
| connect, minimal | — | `ALL SHORTEST` | — | — | `ALL SHORTEST` | `age_all_shortest_paths` | — | `min_meeting_subgraph` | `connect_min` |

### D.2 Three candidate vocabularies

**(a) `in` / `out` / `both` + `depth`** — Gremlin's words. Pros: shortest; universal in graph-DB circles. Cons: point-of-view semantics ("an IN edge *for Rexster*") that Gremlin's own javadoc needs an example to pin down; `in` is a Python keyword (fine as a string value, impossible as a kwarg or a CLI subcommand helper function name, and `--in` reads as "inside"); an LLM reading `in` next to `in_degree` on the same row will conflate them. Rejected.

**(b) `inbound` / `outbound` / `around` + `depth`** — neo4j's `INCOMING/OUTGOING`, AGE's `in/out/any`. Pros: readable English; no keyword. Cons: still point-of-view ("inbound *to the seed*"), so the tool description must say which end the seed sits on; `around` is a new coinage. Acceptable second choice.

**(c) `upstream` / `downstream` / `neighborhood`** — flow metaphor. Pros: natural for the `fs` tree (downstream = subtree). Cons: in dependency graphs — the most common authored edge type (`depends_on`) — practitioners say "downstream" for *dependents*, i.e. the **reverse** of the arrow. The metaphor flips by domain; an agent would guess wrong half the time. Rejected.

**(d) recommended: `forward` / `reverse` / `both` + `depth`** — arrow-relative (networkx `reverse=`, cognee, AGE's internal enum). `forward` follows each edge from its `source` to its `target`; `reverse` follows it from `target` back to `source`; `both` ignores the arrow. These are defined by the words `mkedge` already uses, so the tool description is one sentence: *"`forward` from X returns the targets of edges whose source is X — the same direction you gave `mkedge`."* No keyword, no degree collision, no point of view, no domain metaphor. On `fs` edges `forward` is the subtree and `reverse` the ancestor chain, which is Oak's vocabulary for free. `connect` / `connect_min` replace `meeting_subgraph` / `min_meeting_subgraph`: "the subgraph that connects these seeds" is what an agent asks for; "meeting subgraph" is our internal algorithm name.

**Depth default and `None`.** Default `depth=1` (Gremlin's `out()`, apoc's one hop, cognee `explore`, afs `list depth=1`): the common agent question is "what points at this / what does this point at". `depth=None` is allowed and means **reachability** — the old `ancestors`/`descendants` — mirroring `tree max_depth` ("None is unbounded", params.py:134) and the house rule against designed caps. It is safe *only* because vfs answers with node **sets** under node-global uniqueness, not path enumerations: a visited-set BFS over a finite graph terminates in at most |V| rounds whatever the cycles (AGE's own docstring draws this line, age_vle.c:49-54; apoc's default `uniqueness=NODE_GLOBAL`). This is a requirement on the SQL leg (R-other): the recursive CTE must carry global node uniqueness, or `None` must be refused the way Kuzu refuses it. `limit` bounds the rows either way. `depth` on `connect`/`connect_min` is the per-seed search radius (budget before giving up on a meeting); `None` = until the wavefronts meet or exhaust.

### D.3 Parameter set (house style from `params.py`)

```
"graph": (
  ParamSpec("method", "str", required=True, choices=GRAPH_METHODS, doc="forward|reverse|both walk, or connect|connect_min the seeds"),
  ParamSpec("path", "path", doc="the seed node"),
  _OBSERVATIONS,                                     # many seeds; chain glean → graph
  ParamSpec("depth", "int", minimum=1, maximum=INT_CEILING, default=1, doc="hops from the nearest seed; None is reachability"),
  ParamSpec("edge_types", "str_seq", nullable=False, default=(), doc="follow only these edge types; empty follows every type, fs included"),
  ParamSpec("edge_types_not", "str_seq", nullable=False, default=(), doc="never follow these edge types"),
  ParamSpec("limit", "int", minimum=1, maximum=INT_CEILING, default=100, doc="node rows to return, nearest first; None returns every reachable row"),
  _COLUMNS,
  _AUTHORITY,
)
```
- `edge_types` / `edge_types_not` mirror `ext`/`ext_not`; apoc's `relationshipFilter` folds type and direction into one string, which is clever and unreadable — keep direction in `method`. ADR 018 makes `fs` an ordinary type name, so the default follows it; the tool doc tells agents `edge_types_not=("fs",)` to stay on authored relations, and the `edge_type` column on every edge row makes mixed answers legible.
- `limit` counts node rows (edge rows ride along, see D.4). A default is not a cap: `None` is lawful for pipelines. Order is BFS order — `depth` ascending, then path — so a truncated answer keeps the nearest nodes.
- **Seeds are included at depth 0** in every method. Reasons: (i) the archived rule "excluded unless reached via another seed" (spec 004) is unstable under multi-seed union; (ii) `connect` must return the seeds anyway, so one law covers all five methods; (iii) a seed the caller may not see is simply absent (ADR 065) and the agent learns it from the missing depth-0 row; (iv) cognee, LightRAG, apoc (`minLevel` 0) and `ego_graph` do this. An agent that wants only neighbours filters `depth >= 1`, which the column makes trivial.
- **Multi-seed union**: one multi-source BFS (networkx `bfs_layers(sources)`), `depth` = distance from the **nearest** seed. No `via` column: the discovering edge is an edge row (D.4), which carries more than a parent path would.

### D.4 Row shape

Every `graph` answer carries two row kinds, both already expressible by `Observation`:
- **Node rows**: `path`, `kind`, and a new query field **`depth: int | None`** (add to `OBSERVATION_QUERY_FIELDS` and `_RIGHT_ALIGN_FIELDS`). Nothing else by default; `columns` fetches more.
- **Edge rows**: the `_observe_edge` shape — `path`=source, `edge_target`, `edge_type`, `edge_weight`, `edge_distance` — with `depth` null. For a walk, the edge rows are the BFS-forest edges (one per non-seed node: how it was reached; ≤ node rows, so `limit` bounds them). For `connect`/`connect_min`, the edge rows are the surviving induced edges — they *are* the answer.
- Consumers: graphiti returns node rows and fact rows from separate tools; cognee and LightRAG return `{nodes, edges}` in one answer; apoc splits nodes-only and nodes+relationships into two procedures. vfs's `Result` is a flat list, and the two shapes are distinguishable by `edge_target is not None`, so one answer holds both.
- **ADR 016's `edges(path, direction, type)`** is `graph(method="forward"|"reverse", path, depth=1, edge_types=(type,))` read through its edge rows. Same rights, same liveness term, same chunking. No separate verb; record the fold in the ADR's amendment line.
- **Rendering**: give `graph` its own arrangement in `results/render.py` — the node table (`path | kind | depth`) followed by an edges block, one line per edge `src --[type]--> tgt` (cognee's `resolve_edges_to_text` convention, which LLMs parse reliably) — and set `_DEFAULT_PROJECTION["graph"] = ("path", "kind", "depth")`. Today's single table with blank cells (§C.5) is legal but wastes tokens.

### D.5 MCP ergonomics

Keep **one `graph` tool with the `method` enum** (ops.py already pins it; cognee `recall`, letta `memory` do the same; graphiti's thirteen tools show the cost of the alternative). Keep every parameter top-level — never cognee's enum-in-a-dict. Bound output with `limit` (default 100) and report a cut with the existing `ErrorKind.truncated` warning carrying `data={"limit": n, "depth_reached": k, "nodes_found": m}` (glean's pattern; cognee `stats.truncated`, LightRAG `is_truncated` are the field's version). Separate "seed has no edges" (empty rows beyond depth 0), "seed absent or hidden" (no depth-0 row), and backend error (classified error) — LightRAG's three-outcome contract.

---

## Open questions
1. **Does the SQL leg give node-global uniqueness?** If R-other's recursive CTE can only guarantee path-local uniqueness on some dialect, `depth=None` must be refused there (Kuzu's stance) rather than allowed with a factorial blow-up. The vocabulary above assumes a visited set.
2. **Should `connect`'s pruning be a method or a flag?** Two methods keep the enum closed and parameters uniform; a `minimal: bool` would be meaningless on walks and need a gate rule. I lean two methods.
3. **`fs` in the default type set** is ADR 018 law, but a `both` walk at depth 2 from a file sweeps in every sibling through the parent. If that proves noisy for agents, the fix is a documented recipe (`edge_types_not=("fs",)`), not a change to the law.
4. **Edge rows under `limit`**: for `connect_min` on 10,000 seeds the surviving edge set is the answer and may exceed any node `limit`; whether `limit` should also cut edge rows (and how the warning says so) is for the spec. `[NOT VERIFIED: depends on R-other's statement shape]`
5. graphiti's `max_nodes` silent cap and shared-recipe mutation are consumer bugs worth not repeating; noted, not vfs's problem.

## Final recommendation

Adopt `GRAPH_METHODS = {"forward", "reverse", "both", "connect", "connect_min"}`: `forward` follows edges from `source` to `target` (the direction `mkedge` was given), `reverse` follows them back, `both` ignores the arrow, and `connect`/`connect_min` return the subgraph joining the seeds. Drop `in_degree`/`out_degree` as names — they are counts in graph theory and already count fields on `Observation`. Parameters: `depth` (int ≥ 1, default 1; `None` = reachability, lawful only under node-global uniqueness in the SQL), `edge_types` / `edge_types_not` (`fs` is an ordinary type per ADR 018), `limit` (default 100, `None` = all, BFS order so the nearest survive), plus `columns`. Every answer is node rows with a new `depth` query field (seeds at depth 0, distance from the nearest seed under a multi-source BFS) plus edge rows in the exact `_observe_edge` shape (walks: the BFS-forest edges; connect: the surviving edges); a depth-1 `forward`/`reverse` walk's edge rows are ADR 016's deferred `edges(path, direction, type)` verb, folded in. Keep one `graph` MCP tool with the `method` enum, render node table plus `src --[type]--> tgt` edge lines, and signal a cut with the `ErrorKind.truncated` warning glean already uses.
